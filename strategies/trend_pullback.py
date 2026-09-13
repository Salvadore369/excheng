from __future__ import annotations

import pandas as pd

from config.settings import AppSettings
from data.historical_data import timeframe_milliseconds
from indicators.indicators import enrich_indicators
from models.domain import SignalType

from .base_strategy import BaseStrategy


def align_completed_higher_timeframe(entry: pd.DataFrame, higher: pd.DataFrame, higher_timeframe: str, entry_timeframe: str = "15m") -> pd.DataFrame:
    """Align HTF values only after that HTF candle has closed (strict no-lookahead)."""
    left = entry.copy().sort_values("timestamp")
    right = higher.copy().sort_values("timestamp")
    left["entry_close_time"] = pd.to_datetime(left["timestamp"], utc=True) + pd.Timedelta(milliseconds=timeframe_milliseconds(entry_timeframe))
    right["higher_close_time"] = pd.to_datetime(right["timestamp"], utc=True) + pd.Timedelta(milliseconds=timeframe_milliseconds(higher_timeframe))
    fields = [c for c in right.columns if c not in {"timestamp", "higher_close_time"}]
    right = right[["higher_close_time", *fields]].rename(columns={c: f"htf_{c}" for c in fields})
    return pd.merge_asof(left, right, left_on="entry_close_time", right_on="higher_close_time", direction="backward")


class TrendPullbackStrategy(BaseStrategy):
    name = "EMA Trend Pullback"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def prepare(self, entry: pd.DataFrame, higher: pd.DataFrame) -> pd.DataFrame:
        e = enrich_indicators(entry, self.settings.ema_fast, self.settings.ema_slow, self.settings.rsi_period, self.settings.atr_period)
        h = enrich_indicators(higher, self.settings.ema_fast, self.settings.ema_slow, self.settings.rsi_period, self.settings.atr_period)
        merged = align_completed_higher_timeframe(e, h, self.settings.higher_timeframe, self.settings.entry_timeframe)
        merged["trend"] = "NEUTRAL"
        merged.loc[merged["htf_ema_fast"] > merged["htf_ema_slow"], "trend"] = "BULLISH"
        merged.loc[merged["htf_ema_fast"] < merged["htf_ema_slow"], "trend"] = "BEARISH"
        merged["signal"] = SignalType.NONE.value
        long_condition = (
            (merged["trend"] == "BULLISH") & (merged["close"] >= merged["ema_fast"])
            & merged["rsi"].between(self.settings.rsi_long_min, self.settings.rsi_long_max)
        )
        short_condition = (
            (merged["trend"] == "BEARISH") & (merged["close"] <= merged["ema_fast"])
            & merged["rsi"].between(self.settings.rsi_short_min, self.settings.rsi_short_max)
        )
        merged.loc[long_condition, "signal"] = SignalType.LONG.value
        merged.loc[short_condition, "signal"] = SignalType.SHORT.value
        merged["signal_reason"] = "No setup"
        merged.loc[long_condition, "signal_reason"] = "Bullish completed-HTF trend and RSI pullback confirmed"
        merged.loc[short_condition, "signal_reason"] = "Bearish completed-HTF trend and RSI pullback confirmed"
        return merged
