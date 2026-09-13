from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from config.settings import AppSettings

from .base_strategy import BaseStrategy
from .candle_confirmation import FourHourCandleConfirmationStrategy
from .four_hour_breakout import FourHourDailyBreakoutStrategy
from .trend_pullback import TrendPullbackStrategy
from .sp2l import SP2LStrategy
from .test_strategy import TestStrategy
from .grid_strategy import GridStrategy


@dataclass(frozen=True)
class StrategySpec:
    key: str
    name: str
    entry_timeframe: str
    higher_timeframe: str
    atr_multiplier: float
    risk_reward: float
    risk_percent: float
    leverage: int
    trading_fee: float
    slippage: float
    factory: Callable[[AppSettings], BaseStrategy]
    research_status: str


STRATEGIES = {
    spec.key: spec
    for spec in (
        StrategySpec(
            "test_strategy",
            TestStrategy.name,
            "1m",
            "5m",
            1.0,
            2.0,
            0.1,
            1,
            0.0006,
            0.0003,
            TestStrategy,
            "Diagnostic only: deterministically requests one protected market entry per bot run; no profitability claim.",
        ),
        StrategySpec(
            "grid_strategy",
            GridStrategy.name,
            "15m",
            "4h",
            1.0,
            2.0,
            0.5,
            2,
            0.0006,
            0.0003,
            GridStrategy,
            "Bounded equal-weight ATR pullback grid with completed-4H trend, volume, and volatility filters; requires walk-forward validation.",
        ),
        StrategySpec(
            "sp2l",
            SP2LStrategy.name,
            "1m",
            "5m",
            1.0,
            2.0,
            0.5,
            2,
            0.0006,
            0.0003,
            SP2LStrategy,
            "Rule-based implementation from Poursamadi and TradingFinder public documentation; requires personal backtesting.",
        ),
        StrategySpec(
            "ema_trend_pullback",
            TrendPullbackStrategy.name,
            "15m",
            "1h",
            1.5,
            2.0,
            1.0,
            5,
            0.0006,
            0.0002,
            TrendPullbackStrategy,
            "Baseline strategy; no positive holdout claim.",
        ),
        StrategySpec(
            "vibe_4h_daily_breakout",
            FourHourDailyBreakoutStrategy.name,
            "4h",
            "1d",
            2.0,
            2.0,
            0.5,
            1,
            0.0006,
            0.0003,
            FourHourDailyBreakoutStrategy,
            "Positive long-history result in VibeCode; newest slice was slightly negative.",
        ),
        StrategySpec(
            "vibe_4h_candle_confirmation",
            FourHourCandleConfirmationStrategy.name,
            "15m",
            "4h",
            1.5,
            3.0,
            0.5,
            3,
            0.0006,
            0.0003,
            FourHourCandleConfirmationStrategy,
            "Market-entry adaptation; must be revalidated in CodexBot before live use.",
        ),
    )
}


def strategy_spec(key: str) -> StrategySpec:
    try:
        return STRATEGIES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown strategy: {key}") from exc


def create_strategy(settings: AppSettings) -> BaseStrategy:
    spec = strategy_spec(settings.strategy)
    if settings.strategy == "sp2l":
        allowed = {"1m": "5m", "5m": "15m"}
        if settings.entry_timeframe not in allowed:
            raise ValueError("SP2L requires entry timeframe 1m or 5m")
        expected_higher = allowed[settings.entry_timeframe]
        if settings.higher_timeframe != expected_higher:
            raise ValueError(
                f"SP2L on {settings.entry_timeframe} requires higher timeframe {expected_higher}, "
                f"not {settings.higher_timeframe}"
            )
        return spec.factory(settings)
    if settings.entry_timeframe != spec.entry_timeframe:
        raise ValueError(
            f"{spec.name} requires entry timeframe {spec.entry_timeframe}, "
            f"not {settings.entry_timeframe}"
        )
    if settings.higher_timeframe != spec.higher_timeframe:
        raise ValueError(
            f"{spec.name} requires higher timeframe {spec.higher_timeframe}, "
            f"not {settings.higher_timeframe}"
        )
    return spec.factory(settings)
