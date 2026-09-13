from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from config.settings import AppSettings
from strategies.candle_confirmation import FourHourCandleConfirmationStrategy
from strategies.four_hour_breakout import FourHourDailyBreakoutStrategy
from strategies.registry import create_strategy, strategy_spec


def test_registry_enforces_strategy_timeframe_profiles():
    settings = AppSettings(
        strategy="vibe_4h_daily_breakout",
        entry_timeframe="4h",
        higher_timeframe="1d",
    )
    assert isinstance(create_strategy(settings), FourHourDailyBreakoutStrategy)
    spec = strategy_spec(settings.strategy)
    assert (spec.risk_reward, spec.risk_percent, spec.leverage) == (2.0, 0.5, 1)
    assert (spec.trading_fee, spec.slippage) == (0.0006, 0.0003)
    with pytest.raises(ValueError, match="requires entry timeframe 4h"):
        create_strategy(settings.model_copy(update={"entry_timeframe": "15m"}))


def test_four_hour_daily_breakout_emits_long_only_after_prior_high_breaks():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    daily, price = [], 100.0
    for index in range(70):
        price += 0.8 if index % 2 == 0 else -0.5
        daily.append(
            {
                "timestamp": start + timedelta(days=index),
                "open": price - 0.1,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 100,
            }
        )
    entry = []
    for index in range(430):
        close = 100 + index * 0.01
        entry.append(
            {
                "timestamp": start + timedelta(hours=4 * index),
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": 100,
            }
        )
    entry[-1].update(close=120, high=121)
    settings = AppSettings(
        strategy="vibe_4h_daily_breakout",
        entry_timeframe="4h",
        higher_timeframe="1d",
    )
    prepared = FourHourDailyBreakoutStrategy(settings).prepare(
        pd.DataFrame(entry), pd.DataFrame(daily)
    )
    assert prepared.iloc[-2]["signal"] == "NONE"
    assert prepared.iloc[-1]["signal"] == "LONG"
    assert prepared.iloc[-1]["close"] > prepared.iloc[-1]["breakout"]


def test_candle_confirmation_market_adaptation_emits_long_signal():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    higher, price = [], 100.0
    for index in range(230):
        change = 2 if index % 2 == 0 else -1
        price += change
        higher.append(
            {
                "timestamp": start + timedelta(hours=4 * index),
                "open": price - change,
                "high": max(price, price - change) + 0.2,
                "low": min(price, price - change) - 0.2,
                "close": price,
                "volume": 100,
            }
        )
    higher[-1].update(
        open=higher[-1]["close"] - 2,
        high=higher[-1]["close"] + 0.2,
        low=higher[-1]["close"] - 2.2,
    )

    entry, price = [], 100.0
    for index in range(3680):
        change = 0.4 if index % 2 == 0 else -0.2
        price += change
        entry.append(
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "open": price - change,
                "high": max(price, price - change) + 0.4,
                "low": min(price, price - change) - 0.4,
                "close": price,
                "volume": 100,
            }
        )
    entry[-1].update(open=468.1, close=468.7, high=468.9, low=467.6)
    settings = AppSettings(
        strategy="vibe_4h_candle_confirmation",
        entry_timeframe="15m",
        higher_timeframe="4h",
    )
    prepared = FourHourCandleConfirmationStrategy(settings).prepare(
        pd.DataFrame(entry), pd.DataFrame(higher)
    )
    assert prepared.iloc[-1]["signal"] == "LONG"
    assert prepared.iloc[-1]["htf_regime_body_atr"] >= 0.5
    assert prepared.iloc[-1]["entry_close_time"] == higher[-1]["timestamp"] + timedelta(hours=4)
