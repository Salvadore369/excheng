from __future__ import annotations

import pandas as pd

from config.settings import AppSettings
from indicators.indicators import atr, ema, rsi
from models.domain import SignalType

from .base_strategy import BaseStrategy
from .trend_pullback import align_completed_higher_timeframe


class FourHourDailyBreakoutStrategy(BaseStrategy):
    """VibeCode's slow BTC trend hypothesis: 4H breakout in a daily bull regime."""

    name = "Vibe 4H / Daily Breakout"
    warmup_bars = 60

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def prepare(self, entry: pd.DataFrame, higher: pd.DataFrame) -> pd.DataFrame:
        bars = entry.copy().sort_values("timestamp")
        daily = higher.copy().sort_values("timestamp")
        bars["atr"] = atr(bars, self.settings.atr_period)
        bars["breakout"] = bars["high"].shift(1).rolling(20).max()
        daily["regime_close"] = daily["close"]
        daily["regime_ema"] = ema(daily["close"], 50)
        daily["regime_rsi"] = rsi(daily["close"], self.settings.rsi_period)

        merged = align_completed_higher_timeframe(
            bars,
            daily,
            self.settings.higher_timeframe,
            self.settings.entry_timeframe,
        )
        merged["trend"] = "NEUTRAL"
        bull_regime = (
            (merged["htf_regime_close"] > merged["htf_regime_ema"])
            & merged["htf_regime_rsi"].between(45, 70)
        )
        merged.loc[bull_regime, "trend"] = "BULLISH"
        merged["rsi"] = merged["htf_regime_rsi"]
        merged["signal"] = SignalType.NONE.value
        signal = bull_regime & (merged["close"] > merged["breakout"])
        merged.loc[signal, "signal"] = SignalType.LONG.value
        merged["signal_reason"] = "No setup"
        merged.loc[signal, "signal_reason"] = (
            "Completed daily close above EMA50, daily RSI 45-70, "
            "and 4H close above the prior 20-bar high"
        )
        return merged
