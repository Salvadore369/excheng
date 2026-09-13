from __future__ import annotations

import pandas as pd

from config.settings import AppSettings
from data.historical_data import timeframe_milliseconds
from indicators.indicators import atr, rsi
from models.domain import SignalType

from .base_strategy import BaseStrategy


class TestStrategy(BaseStrategy):
    """Deterministic one-shot strategy for testing the live execution route.

    It intentionally contains no alpha claim. Every indicator-ready row emits
    the configured direction; the service and backtester enforce one submission
    per run. Normal risk sizing, SL/TP, blackout, position, and preflight rules
    remain active.
    """

    name = "TestStrategy"
    warmup_bars = 20
    diagnostic_one_shot = True

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def prepare(self, entry: pd.DataFrame, higher: pd.DataFrame) -> pd.DataFrame:
        frame = entry.copy().sort_values("timestamp").reset_index(drop=True)
        frame["atr"] = atr(frame, self.settings.atr_period)
        frame["rsi"] = rsi(frame.close, self.settings.rsi_period)
        frame["entry_close_time"] = pd.to_datetime(frame.timestamp, utc=True) + pd.Timedelta(
            milliseconds=timeframe_milliseconds(self.settings.entry_timeframe)
        )
        direction = SignalType.LONG.value if self.settings.test_strategy_direction == "LONG" else SignalType.SHORT.value
        frame["trend"] = "DIAGNOSTIC"
        frame["signal"] = SignalType.NONE.value
        ready = frame["atr"].notna() & (frame["atr"] > 0)
        frame.loc[ready, "signal"] = direction
        frame["signal_reason"] = "Waiting for ATR warm-up"
        frame.loc[ready, "signal_reason"] = "One-shot live execution diagnostic"
        return frame
