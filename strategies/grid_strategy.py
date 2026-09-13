from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import AppSettings
from data.historical_data import timeframe_milliseconds
from indicators.indicators import enrich_indicators
from models.domain import SignalType

from .base_strategy import BaseStrategy
from .trend_pullback import align_completed_higher_timeframe


class GridStrategy(BaseStrategy):
    """Bounded trend-following ATR pullback grid.

    The strategy places equal-weight limits deeper into a liquid pullback only
    when the completed 4H EMA regime and slope agree. A shared hard stop beyond
    the deepest level caps the whole plan; targets are calculated from the
    shallowest fill so partial grids still preserve at least the configured R:R.
    """

    name = "GridStrategy"
    warmup_bars = 200
    uses_limit_plans = True
    plan_name = "GRID"
    client_slug = "grid"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def prepare(self, entry: pd.DataFrame, higher: pd.DataFrame) -> pd.DataFrame:
        e = enrich_indicators(entry, self.settings.ema_fast, self.settings.ema_slow, self.settings.rsi_period, self.settings.atr_period)
        h = enrich_indicators(higher, self.settings.ema_fast, self.settings.ema_slow, self.settings.rsi_period, self.settings.atr_period)
        frame = align_completed_higher_timeframe(e, h, self.settings.higher_timeframe, self.settings.entry_timeframe)
        frame["trend"] = "NEUTRAL"
        bullish = (frame.htf_ema_fast > frame.htf_ema_slow) & (frame.htf_ema_fast > frame.htf_ema_fast.shift(5))
        bearish = (frame.htf_ema_fast < frame.htf_ema_slow) & (frame.htf_ema_fast < frame.htf_ema_fast.shift(5))
        frame.loc[bullish, "trend"] = "BULLISH"
        frame.loc[bearish, "trend"] = "BEARISH"

        atr_percent = frame.atr / frame.close * 100
        liquid = frame.volume >= frame.volume.rolling(20, min_periods=20).median()
        volatility_ok = atr_percent.between(self.settings.grid_min_atr_percent, self.settings.grid_max_atr_percent)
        trend_gap_percent = (frame.htf_ema_fast - frame.htf_ema_slow).abs() / frame.close * 100
        trend_mature_not_extended = trend_gap_percent.between(
            self.settings.grid_min_trend_gap_percent,
            self.settings.grid_max_trend_gap_percent,
        )
        # Trigger only as RSI crosses into a pullback band, preventing a fresh
        # grid on every candle while the market remains oversold/overbought.
        long_setup = bullish & (frame.close > frame.ema_slow) & frame.rsi.between(40, 55) & (frame.rsi.shift(1) > 55) & liquid & volatility_ok & trend_mature_not_extended
        short_setup = bearish & (frame.close < frame.ema_slow) & frame.rsi.between(45, 60) & (frame.rsi.shift(1) < 45) & liquid & volatility_ok & trend_mature_not_extended

        frame["signal"] = SignalType.NONE.value
        frame.loc[long_setup, "signal"] = SignalType.LONG.value
        frame.loc[short_setup, "signal"] = SignalType.SHORT.value
        frame["signal_reason"] = "No bounded trend-grid setup"
        frame.loc[long_setup, "signal_reason"] = "4H bullish regime; liquid 15m RSI pullback grid armed"
        frame.loc[short_setup, "signal_reason"] = "4H bearish regime; liquid 15m RSI rally grid armed"

        for column in ("entry_levels", "entry_weights"):
            frame[column] = pd.Series([None] * len(frame), dtype=object)
        for column in ("strategy_stop", "strategy_tp1", "strategy_tp2", "tp1_fraction", "time_stop_bars", "limit_expiry_bars"):
            frame[column] = np.nan

        for index in frame.index[long_setup | short_setup]:
            row = frame.loc[index]
            bullish_signal = row.signal == SignalType.LONG.value
            sign = -1 if bullish_signal else 1
            spacing = float(row.atr) * self.settings.grid_spacing_atr
            levels = tuple(float(row.close) + sign * spacing * layer for layer in range(1, self.settings.grid_levels + 1))
            weights = tuple(1.0 for _ in levels)
            deepest = levels[-1]
            stop = deepest + sign * float(row.atr) * self.settings.grid_stop_buffer_atr
            conservative_risk = abs(levels[0] - stop)
            profit_sign = 1 if bullish_signal else -1
            tp1 = levels[0] + profit_sign * conservative_risk * self.settings.risk_reward
            tp2 = levels[0] + profit_sign * conservative_risk * max(self.settings.risk_reward + 1, 3.0)
            values = {
                "entry_levels": levels,
                "entry_weights": weights,
                "strategy_stop": stop,
                "strategy_tp1": tp1,
                "strategy_tp2": tp2,
                "tp1_fraction": self.settings.grid_tp1_fraction,
                "time_stop_bars": self.settings.grid_time_stop_bars,
                "limit_expiry_bars": self.settings.grid_limit_expiry_bars,
            }
            for column, value in values.items():
                frame.at[index, column] = value
        return frame
