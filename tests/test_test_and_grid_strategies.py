from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from config.settings import AppSettings
from models.domain import Instrument
from services.trading_service import TradingService
from strategies.grid_strategy import GridStrategy
from strategies.registry import create_strategy, strategy_spec
from strategies.test_strategy import TestStrategy as DiagnosticStrategy


def candles(count=240, *, start=None, step=timedelta(minutes=1), price=100.0):
    start = start or datetime(2025, 1, 6, tzinfo=UTC)
    rows = []
    for index in range(count):
        close = price + index * 0.02
        rows.append({
            "timestamp": start + step * index,
            "open": close - 0.02,
            "high": close + 0.15,
            "low": close - 0.15,
            "close": close,
            "volume": 1000,
        })
    return pd.DataFrame(rows)


def test_new_strategies_are_registered_with_fixed_profiles():
    test_settings = AppSettings(strategy="test_strategy", entry_timeframe="1m", higher_timeframe="5m")
    grid_settings = AppSettings(strategy="grid_strategy", entry_timeframe="15m", higher_timeframe="4h")

    assert isinstance(create_strategy(test_settings), DiagnosticStrategy)
    assert isinstance(create_strategy(grid_settings), GridStrategy)
    assert strategy_spec("test_strategy").risk_percent == 0.1
    assert strategy_spec("grid_strategy").risk_percent == 0.5


def test_test_strategy_emits_configured_direction_on_every_ready_row():
    settings = AppSettings(strategy="test_strategy", entry_timeframe="1m", higher_timeframe="5m", test_strategy_direction="SHORT")
    prepared = DiagnosticStrategy(settings).prepare(candles(), candles(step=timedelta(minutes=5)))

    assert prepared.iloc[-1].signal == "SHORT"
    assert prepared.iloc[-1].trend == "DIAGNOSTIC"
    assert prepared.iloc[-1].atr > 0


def test_test_strategy_submits_only_one_protected_order_per_bot_run():
    class Market:
        instrument = Instrument("BTCUSDT", 3, 1, Decimal("0.001"), Decimal("1000"), 1, 125)

        def get_instrument(self, _symbol):
            return self.instrument

        def get_last_price(self, _symbol):
            return Decimal("100")

    settings = AppSettings(
        strategy="test_strategy", entry_timeframe="1m", higher_timeframe="5m",
        test_strategy_direction="LONG", block_weekends=False,
    )
    frame = candles()
    service = TradingService(Market(), settings, lambda *_args: None)
    service.last_price = Decimal("100")
    service._recent_frame = lambda _timeframe: frame

    service._evaluate()
    service._evaluate()

    assert len(service.paper.orders) == 1
    assert len(service.paper.get_positions("BTCUSDT")) == 1
    assert service.paper.orders[0].stop_loss is not None
    assert service.paper.orders[0].take_profit is not None
    assert service._diagnostic_order_submitted is True


def test_grid_strategy_builds_equal_weight_bounded_long_grid():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    higher = []
    for index in range(260):
        close = 100 + index * 0.2
        higher.append({"timestamp": start + timedelta(hours=4 * index), "open": close - 0.1,
            "high": close + 0.4, "low": close - 0.4, "close": close, "volume": 1000})

    entry_start = start + timedelta(hours=4 * 225)
    entry, price = [], 143.0
    for index in range(240):
        if index < 236:
            price += 0.06
        elif index == 236:
            price += 0.3
        elif index == 237:
            price += 0.2
        elif index == 238:
            price -= 0.2
        else:
            price -= 0.8
        entry.append({"timestamp": entry_start + timedelta(minutes=15 * index), "open": price - 0.03,
            "high": price + 0.15, "low": price - 0.15, "close": price,
            "volume": 2000 if index == 239 else 1000})

    settings = AppSettings(strategy="grid_strategy", entry_timeframe="15m", higher_timeframe="4h", grid_levels=3, grid_max_trend_gap_percent=20)
    signal = GridStrategy(settings).prepare(pd.DataFrame(entry), pd.DataFrame(higher)).iloc[-1]

    assert signal.signal == "LONG"
    assert len(signal.entry_levels) == settings.grid_levels
    assert signal.entry_weights == (1.0, 1.0, 1.0)
    assert signal.strategy_stop < min(signal.entry_levels)
    shallow_risk = signal.entry_levels[0] - signal.strategy_stop
    assert signal.strategy_tp1 >= signal.entry_levels[0] + shallow_risk * settings.risk_reward
    assert signal.limit_expiry_bars == settings.grid_limit_expiry_bars
    assert signal.time_stop_bars == settings.grid_time_stop_bars
