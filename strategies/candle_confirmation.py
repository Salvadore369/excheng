from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import AppSettings
from indicators.indicators import atr, ema, rsi
from models.domain import SignalType

from .base_strategy import BaseStrategy
from .trend_pullback import align_completed_higher_timeframe


class FourHourCandleConfirmationStrategy(BaseStrategy):
    """Market-entry adaptation of VibeCode v0.4's 4H/15m confirmation model."""

    name = "Vibe 4H Candle Confirmation (Market)"
    warmup_bars = 200

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def prepare(self, entry: pd.DataFrame, higher: pd.DataFrame) -> pd.DataFrame:
        bars = entry.copy().sort_values("timestamp")
        regime = higher.copy().sort_values("timestamp")

        bars["entry_fast"] = ema(bars["close"], 20)
        bars["entry_slow"] = ema(bars["close"], 50)
        bars["rsi"] = rsi(bars["close"], self.settings.rsi_period)
        bars["atr"] = atr(bars, self.settings.atr_period)
        bars["atr_pct"] = bars["atr"] / bars["close"]
        bars["trigger_high"] = bars["high"].shift(1).rolling(3).max()
        bars["trigger_low"] = bars["low"].shift(1).rolling(3).min()
        bars["pullback_long"] = (
            bars["low"].shift(1).rolling(6).min()
            <= bars["entry_fast"].shift(1) * 1.001
        )
        bars["pullback_short"] = (
            bars["high"].shift(1).rolling(6).max()
            >= bars["entry_fast"].shift(1) * 0.999
        )
        bars["volume_baseline"] = bars["volume"].shift(1).rolling(32).median()
        candle_range = (bars["high"] - bars["low"]).replace(0, np.nan)
        bars["close_location"] = (bars["close"] - bars["low"]) / candle_range
        bars["body_fraction"] = (bars["close"] - bars["open"]).abs() / candle_range

        regime["regime_close"] = regime["close"]
        regime["regime_open"] = regime["open"]
        regime["regime_micro"] = ema(regime["close"], 20)
        regime["regime_fast"] = ema(regime["close"], 50)
        regime["regime_slow"] = ema(regime["close"], 200)
        regime["regime_atr"] = atr(regime, self.settings.atr_period)
        regime["regime_rsi"] = rsi(regime["close"], self.settings.rsi_period)
        regime["regime_body_atr"] = (
            (regime["close"] - regime["open"]) / regime["regime_atr"]
        )
        regime["regime_strength"] = (
            (regime["regime_micro"] - regime["regime_fast"]).abs()
            / regime["regime_atr"]
        )

        merged = align_completed_higher_timeframe(
            bars,
            regime,
            self.settings.higher_timeframe,
            self.settings.entry_timeframe,
        )
        merged["trend"] = "NEUTRAL"
        bullish = (
            (merged["htf_regime_close"] > merged["htf_regime_micro"])
            & (merged["htf_regime_micro"] > merged["htf_regime_fast"])
        )
        bearish = (
            (merged["htf_regime_close"] < merged["htf_regime_micro"])
            & (merged["htf_regime_micro"] < merged["htf_regime_fast"])
        )
        merged.loc[bullish, "trend"] = "BULLISH"
        merged.loc[bearish, "trend"] = "BEARISH"

        common = (
            merged["atr_pct"].between(0.0015, 0.012)
            & (merged["volume"] >= merged["volume_baseline"] * 0.8)
            & (merged["body_fraction"] >= 0.30)
            & (merged["htf_regime_strength"] >= 0.25)
        )
        long_signal = (
            common
            & (merged["htf_regime_body_atr"] >= 0.5)
            & bullish
            & merged["htf_regime_rsi"].between(50, 74)
            & (merged["entry_fast"] > merged["entry_slow"])
            & merged["pullback_long"].fillna(False)
            & (merged["close"] > merged["trigger_high"])
            & merged["rsi"].between(52, 74)
            & (merged["close_location"] >= 0.60)
        )
        short_signal = (
            common
            & (merged["htf_regime_body_atr"] <= -0.5)
            & bearish
            & merged["htf_regime_rsi"].between(26, 50)
            & (merged["entry_fast"] < merged["entry_slow"])
            & merged["pullback_short"].fillna(False)
            & (merged["close"] < merged["trigger_low"])
            & merged["rsi"].between(26, 48)
            & (merged["close_location"] <= 0.40)
        )
        merged["signal"] = SignalType.NONE.value
        merged.loc[long_signal, "signal"] = SignalType.LONG.value
        merged.loc[short_signal, "signal"] = SignalType.SHORT.value
        merged["signal_reason"] = "No setup"
        merged.loc[long_signal, "signal_reason"] = (
            "Bullish completed 4H candle confirmation and 15m pullback breakout"
        )
        merged.loc[short_signal, "signal_reason"] = (
            "Bearish completed 4H candle confirmation and 15m pullback breakdown"
        )
        return merged
