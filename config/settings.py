from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TIMEFRAMES = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}


class AppSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    symbol: str = "BTCUSDT"
    strategy: Literal[
        "ema_trend_pullback",
        "vibe_4h_daily_breakout",
        "vibe_4h_candle_confirmation",
        "sp2l",
        "test_strategy",
        "grid_strategy",
    ] = "ema_trend_pullback"
    higher_timeframe: str = "1h"
    entry_timeframe: str = "15m"
    ema_fast: int = Field(50, ge=2, le=500)
    ema_slow: int = Field(200, ge=3, le=1000)
    rsi_period: int = Field(14, ge=2, le=100)
    rsi_long_min: float = Field(35, ge=0, le=100)
    rsi_long_max: float = Field(60, ge=0, le=100)
    rsi_short_min: float = Field(40, ge=0, le=100)
    rsi_short_max: float = Field(65, ge=0, le=100)
    atr_period: int = Field(14, ge=2, le=100)
    atr_stop_multiplier: float = Field(1.5, gt=0, le=20)
    risk_per_trade: float = Field(1.0, gt=0, le=1)
    risk_reward: float = Field(2.0, ge=2, le=20)
    max_open_positions: int = Field(1, ge=1, le=20)
    trading_fee: float = Field(0.0006, ge=0, le=0.02)
    slippage: float = Field(0.0002, ge=0, le=0.02)
    trailing_stop: bool = False
    leverage: int = Field(5, ge=1, le=125)
    margin_mode: Literal["ISOLATION", "CROSS"] = "ISOLATION"
    position_mode: Literal["ONE_WAY", "HEDGE"] = "ONE_WAY"
    paper_initial_balance: float = Field(10_000, gt=0)
    cache_directory: str = "cache"
    close_positions_on_stop: bool = False
    block_weekends: bool = True
    macro_event_blackout: bool = False
    # Diagnostic TestStrategy direction. It emits one immediate protected
    # market-entry request per bot run and is not intended as an alpha strategy.
    test_strategy_direction: Literal["LONG", "SHORT"] = "LONG"
    # Bounded ATR trend-grid profile. Equal layer weights intentionally avoid
    # martingale exposure; total risk remains governed by risk_per_trade.
    grid_levels: int = Field(2, ge=2, le=5)
    grid_spacing_atr: float = Field(1.0, ge=0.25, le=3)
    grid_stop_buffer_atr: float = Field(1.0, ge=0.5, le=5)
    grid_tp1_fraction: float = Field(0.5, ge=0.1, le=0.9)
    grid_limit_expiry_bars: int = Field(6, ge=1, le=50)
    grid_time_stop_bars: int = Field(24, ge=1, le=200)
    grid_min_atr_percent: float = Field(0.2, ge=0.05, le=5)
    grid_max_atr_percent: float = Field(3.0, ge=0.1, le=20)
    grid_min_trend_gap_percent: float = Field(1.0, ge=0, le=20)
    grid_max_trend_gap_percent: float = Field(3.0, ge=0.1, le=30)
    # SP2L (Spike-2Leg) price-action profile. The documented two-layer model is
    # the safe default; the aggressive 1x/2x/4x third layer is explicit opt-in.
    sp2l_min_spike_bars: int = Field(3, ge=3, le=9)
    sp2l_max_spike_bars: int = Field(9, ge=3, le=9)
    sp2l_breakout_lookback: int = Field(20, ge=5, le=200)
    sp2l_movement_atr: float = Field(1.5, gt=0, le=20)
    sp2l_strong_body_ratio: float = Field(0.65, ge=0.1, le=1)
    sp2l_gap_filter: bool = True
    sp2l_max_doji_body_ratio: float = Field(0.2, ge=0, le=1)
    sp2l_max_doji_ratio: float = Field(0.35, ge=0, le=1)
    sp2l_dirty_lookback: int = Field(20, ge=3, le=100)
    sp2l_dirty_overlap_ratio: float = Field(0.60, ge=0, le=1)
    sp2l_session_filter: bool = False
    sp2l_ema_origin_filter: bool = False
    sp2l_ema_origin_atr: float = Field(1.0, gt=0, le=10)
    sp2l_direction_filter: Literal["BOTH", "LONG", "SHORT"] = "SHORT"
    sp2l_trend_filter: Literal["NONE", "EMA60", "HTF_EMA60"] = "HTF_EMA60"
    sp2l_stop_mode: Literal["SPIKE_ORIGIN", "FOLLOW_THROUGH", "SPIKE_50"] = "SPIKE_ORIGIN"
    sp2l_stop_buffer_atr: float = Field(0.10, ge=0, le=2)
    sp2l_entry2_mode: Literal["ENTRY_STOP_MIDPOINT", "SPIKE_50", "EMA60"] = "EMA60"
    sp2l_enable_third_entry: bool = False
    sp2l_entry_weights: tuple[float, float, float] = (1.0, 2.0, 4.0)
    sp2l_tp1_rr: float = Field(1.0, ge=1, le=10)
    sp2l_tp1_fraction: float = Field(0.7, ge=0, le=0.9)
    sp2l_time_stop_bars: int = Field(30, ge=1, le=200)
    sp2l_limit_expiry_bars: int = Field(5, ge=1, le=50)

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.endswith("USDT") or not value.isalnum():
            raise ValueError("symbol must be an alphanumeric USDT perpetual pair, e.g. BTCUSDT")
        return value

    @field_validator("higher_timeframe", "entry_timeframe")
    @classmethod
    def valid_timeframe(cls, value: str) -> str:
        if value not in TIMEFRAMES:
            raise ValueError(f"unsupported timeframe: {value}")
        return value

    @model_validator(mode="after")
    def validate_ranges(self) -> "AppSettings":
        if self.ema_fast >= self.ema_slow:
            raise ValueError("EMA Fast must be less than EMA Slow")
        if self.rsi_long_min > self.rsi_long_max or self.rsi_short_min > self.rsi_short_max:
            raise ValueError("RSI minimum must not exceed maximum")
        if self.sp2l_min_spike_bars > self.sp2l_max_spike_bars:
            raise ValueError("SP2L minimum spike bars must not exceed maximum spike bars")
        if len(self.sp2l_entry_weights) != 3 or any(weight <= 0 for weight in self.sp2l_entry_weights):
            raise ValueError("SP2L entry weights must contain three positive values")
        if self.grid_min_atr_percent >= self.grid_max_atr_percent:
            raise ValueError("Grid minimum ATR percent must be below maximum ATR percent")
        if self.grid_min_trend_gap_percent >= self.grid_max_trend_gap_percent:
            raise ValueError("Grid minimum trend gap percent must be below maximum trend gap percent")
        return self


class ConfigStore:
    def __init__(self, path: str | Path = "config.json") -> None:
        self.path = Path(path)

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        settings = AppSettings.model_validate_json(self.path.read_text(encoding="utf-8"))
        # Older GUI builds allowed an SP2L entry timeframe to be saved with an
        # incompatible HTF. Normalize that stale pair before services are built,
        # so the user can open the application and save the corrected settings.
        if settings.strategy == "sp2l":
            required_higher = {"1m": "5m", "5m": "15m"}.get(settings.entry_timeframe)
            if required_higher and settings.higher_timeframe != required_higher:
                settings = settings.model_copy(update={"higher_timeframe": required_higher})
        return settings

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Replace atomically so a power loss cannot leave a partial JSON file.
        handle, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent, text=True)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(settings.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def load_credentials() -> tuple[str | None, str | None]:
    load_dotenv(override=False)
    return os.getenv("BITUNIX_API_KEY"), os.getenv("BITUNIX_API_SECRET")
