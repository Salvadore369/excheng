from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from backtesting.backtester import Backtester
from config.settings import AppSettings
from execution.base_exchange import ExchangeError
from models.domain import AppState, Direction, Instrument, Order, OrderSide, Position
from services.trading_service import TradingService
from strategies.base_strategy import BaseStrategy
from strategies.registry import create_strategy
from strategies.sp2l import SP2LStrategy
from strategies.grid_strategy import GridStrategy


def _settings(**updates) -> AppSettings:
    values = {
        "strategy": "sp2l",
        "entry_timeframe": "1m",
        "higher_timeframe": "5m",
        "atr_period": 14,
        "block_weekends": False,
        "sp2l_direction_filter": "BOTH",
        "sp2l_trend_filter": "NONE",
    }
    values.update(updates)
    return AppSettings(**values)


def _base_rows(count: int = 95) -> list[dict]:
    start = datetime(2025, 1, 6, 8, tzinfo=UTC)
    rows = []
    for index in range(count):
        open_ = 99.3 if index % 2 == 0 else 100.4
        close = 100.3 if index % 2 == 0 else 99.4
        rows.append({
            "timestamp": start + timedelta(minutes=index),
            "open": open_, "high": 100.8, "low": 98.9,
            "close": close, "volume": 100,
        })
    return rows


def bullish_setup(*, gap: bool = True, pullback: bool = True, spike_bars: int = 3) -> pd.DataFrame:
    rows = _base_rows(110)
    first = 80
    # First bar breaks the static range while dipping below the pre-spike low,
    # which makes the beginning of the consecutive-HL run unambiguous.
    spike = [
        (99.5, 104.2, 98.7, 103.9),
        (103.7, 105.4, 101.2 if gap else 100.7, 105.0),
        (105.0, 106.7, 104.4, 106.3),
    ]
    for offset in range(spike_bars):
        if offset < len(spike):
            values = spike[offset]
        else:
            prior_low = 104.4 + (offset - 2) * 0.5
            values = (106 + offset * 0.4, 107 + offset * 0.5, prior_low, 106.7 + offset * 0.5)
        rows[first + offset].update(zip(("open", "high", "low", "close"), values, strict=True))
    trigger = first + spike_bars
    previous = rows[trigger - 1]
    trigger_low = previous["low"] - 0.2 if pullback else previous["low"]
    rows[trigger].update(open=previous["close"] - 0.1, high=previous["high"] - 0.2,
                         low=trigger_low, close=previous["close"] - 0.5)
    return pd.DataFrame(rows[: trigger + 1])


def bearish_setup() -> pd.DataFrame:
    rows = _base_rows(95)
    rows[80].update(open=100.2, high=101.0, low=95.8, close=96.1)
    rows[81].update(open=96.2, high=98.5, low=94.5, close=94.9)
    rows[82].update(open=94.8, high=95.5, low=93.2, close=93.6)
    rows[83].update(open=93.8, high=95.7, low=93.4, close=94.2)
    return pd.DataFrame(rows[:84])


def test_registry_creates_sp2l_profile():
    strategy = create_strategy(_settings())
    assert isinstance(strategy, SP2LStrategy)
    assert strategy.uses_limit_plans is True
    assert isinstance(create_strategy(_settings(entry_timeframe="5m", higher_timeframe="15m")), SP2LStrategy)


def test_sp2l_research_defaults_are_the_walk_forward_profile():
    settings = AppSettings()
    assert settings.sp2l_direction_filter == "SHORT"
    assert settings.sp2l_trend_filter == "HTF_EMA60"
    assert settings.sp2l_strong_body_ratio == 0.65
    assert settings.sp2l_entry2_mode == "EMA60"
    assert settings.sp2l_enable_third_entry is False
    assert (settings.sp2l_tp1_rr, settings.sp2l_tp1_fraction) == (1.0, 0.7)
    assert settings.sp2l_time_stop_bars == 30


def test_bullish_spike_first_pullback_emits_scaled_limit_plan():
    prepared = SP2LStrategy(_settings()).prepare(bullish_setup(), pd.DataFrame())
    signal = prepared.iloc[-1]
    assert signal.signal == "LONG"
    assert signal.entry_levels[0] == prepared.iloc[-2].low
    assert len(signal.entry_levels) == 2
    assert signal.entry_weights == (1.0, 2.0)
    assert signal.strategy_stop < min(signal.entry_levels)
    assert signal.strategy_tp1 > max(signal.entry_levels)
    assert signal.strategy_tp2 >= signal.strategy_tp1


def test_bearish_spike_first_pullback_emits_short_plan():
    signal = SP2LStrategy(_settings()).prepare(bearish_setup(), pd.DataFrame()).iloc[-1]
    assert signal.signal == "SHORT"
    assert signal.strategy_stop > max(signal.entry_levels)
    assert signal.strategy_tp2 < min(signal.entry_levels)


def test_gap_and_strict_first_pullback_are_required():
    no_gap = SP2LStrategy(_settings()).prepare(bullish_setup(gap=False), pd.DataFrame())
    no_pullback = SP2LStrategy(_settings()).prepare(bullish_setup(pullback=False), pd.DataFrame())
    assert no_gap.iloc[-1].signal == "NONE"
    assert no_pullback.iloc[-1].signal == "NONE"


def test_more_than_nine_spike_bars_is_rejected_as_exhaustion():
    prepared = SP2LStrategy(_settings()).prepare(bullish_setup(spike_bars=10), pd.DataFrame())
    assert prepared.iloc[-1].signal == "NONE"


class LimitPlanStrategy(BaseStrategy):
    uses_limit_plans = True

    def prepare(self, entry, higher):
        frame = entry.copy()
        frame["entry_close_time"] = pd.to_datetime(frame.timestamp, utc=True) + pd.Timedelta(minutes=1)
        frame["signal"] = "NONE"
        frame["entry_levels"] = pd.Series([None] * len(frame), dtype=object)
        frame["entry_weights"] = pd.Series([None] * len(frame), dtype=object)
        frame.loc[0, "signal"] = "LONG"
        frame.at[0, "entry_levels"] = (100.0, 98.0)
        frame.at[0, "entry_weights"] = (1.0, 2.0)
        frame["strategy_stop"] = 95.0
        frame["strategy_tp1"] = 103.0
        frame["strategy_tp2"] = 107.0
        frame["tp1_fraction"] = 0.7
        frame["limit_expiry_bars"] = 5
        frame["time_stop_bars"] = 20
        return frame


def test_limit_backtester_scales_in_and_takes_partial_then_final_profit():
    start = datetime(2025, 1, 6, tzinfo=UTC)
    frame = pd.DataFrame([
        {"timestamp": start, "open": 101, "high": 102, "low": 100.5, "close": 101, "volume": 1},
        {"timestamp": start + timedelta(minutes=1), "open": 101, "high": 101, "low": 97.5, "close": 99, "volume": 1},
        {"timestamp": start + timedelta(minutes=2), "open": 99, "high": 104, "low": 98, "close": 103, "volume": 1},
        {"timestamp": start + timedelta(minutes=3), "open": 103, "high": 108, "low": 102, "close": 107, "volume": 1},
    ])
    instrument = Instrument("BTCUSDT", 3, 1, Decimal("0.001"), Decimal("1000"), 1, 125)
    settings = _settings(trading_fee=0, slippage=0, risk_per_trade=1, leverage=2)
    result = Backtester(settings, LimitPlanStrategy(), instrument).run(frame, frame, Decimal("10000"))
    assert [trade.exit_reason for trade in result.trades] == ["TAKE_PROFIT_1", "TAKE_PROFIT_2"]
    assert sum((trade.size for trade in result.trades), Decimal(0)) > 0
    assert result.final_balance > result.starting_balance


class LiveLimitExchange:
    def __init__(self):
        self.instrument = Instrument("BTCUSDT", 3, 1, Decimal("0.001"), Decimal("1000"), 1, 125)
        self.orders = []
        self.cancelled = []
        self.positions = []

    def get_instrument(self, _symbol):
        return self.instrument

    def get_account(self, _coin="USDT"):
        return {"available": "10000", "positionMode": "ONE_WAY"}

    def get_positions(self, _symbol=None):
        return list(self.positions)

    def get_pending_orders(self, _symbol=None):
        return [
            {"orderId": order.id, "clientId": order.client_id, "status": "NEW"}
            for order in self.orders if order.id not in self.cancelled
        ]

    def get_leverage_margin_mode(self, _symbol):
        return {"leverage": 2, "marginMode": "ISOLATION"}

    def place_order(self, order):
        order.id = str(len(self.orders) + 1)
        order.status = "INIT"
        self.orders.append(order)
        if getattr(order, "reduce_only", False):
            self.positions = []
        return order

    def cancel_order(self, _symbol, order_id):
        self.cancelled.append(order_id)
        return True

    def change_leverage(self, _symbol, _leverage):
        return None

    def change_margin_mode(self, _symbol, _mode):
        return None


def test_sp2l_live_start_and_scaled_limit_submission_are_supported():
    exchange = LiveLimitExchange()
    logs = []
    service = TradingService(exchange, _settings(risk_per_trade=1, leverage=2), lambda category, message: logs.append((category, message)))
    service._start_websockets = lambda **_kwargs: None
    service._loop = lambda: None

    service.start_live(exchange)
    assert service.state.state == AppState.RUNNING_LIVE

    signal_time = datetime(2025, 1, 6, 12, tzinfo=UTC)
    row = pd.Series({
        "signal": "LONG", "entry_levels": (100, 98), "entry_weights": (1, 2),
        "strategy_stop": 95, "strategy_tp1": 103, "strategy_tp2": 107,
        "tp1_fraction": 0.7, "limit_expiry_bars": 5,
    })
    service._execute_sp2l_plan(row, signal_time)

    assert len(exchange.orders) == 4
    assert all(order.order_type == "LIMIT" for order in exchange.orders)
    assert all(order.stop_loss == Decimal("95.0") for order in exchange.orders)
    assert {order.take_profit for order in exchange.orders} == {Decimal("103.0"), Decimal("107.0")}
    assert len({order.client_id for order in exchange.orders}) == 4
    assert any("SP2L LIVE LIMIT PLAN ARMED" in message for _, message in logs)

    service._maintain_sp2l_plan(signal_time + timedelta(minutes=6))
    assert set(exchange.cancelled) == {"1", "2", "3", "4"}
    assert not service._sp2l_order_ids
    assert any("SP2L LIVE LIMIT PLAN EXPIRED" in message for _, message in logs)

    service.stop()


def test_sp2l_live_time_stop_closes_position_and_cancels_unfilled_layers():
    exchange = LiveLimitExchange()
    service = TradingService(exchange, _settings(risk_per_trade=1, leverage=2), lambda *_args: None)
    service._executor = exchange
    signal_time = datetime(2025, 1, 6, 12, tzinfo=UTC)
    row = pd.Series({
        "signal": "LONG", "entry_levels": (100, 98), "entry_weights": (1, 2),
        "strategy_stop": 95, "strategy_tp1": 103, "strategy_tp2": 107,
        "tp1_fraction": 0.7, "limit_expiry_bars": 5,
    })
    service._execute_sp2l_plan(row, signal_time)
    exchange.positions = [Position(
        "BTCUSDT", Direction.LONG, Decimal("0.5"), Decimal(100), Decimal(95),
        Decimal(107), signal_time, id="position-1",
    )]

    service._maintain_sp2l_plan(signal_time + timedelta(minutes=1))
    service._maintain_sp2l_plan(signal_time + timedelta(minutes=40))

    close = exchange.orders[-1]
    assert close.reduce_only is True
    assert close.quantity == Decimal("0.5")
    assert set(exchange.cancelled) == {"1", "2", "3", "4"}
    assert not service._sp2l_order_ids


def test_live_stop_can_close_and_verify_current_position():
    exchange = LiveLimitExchange()
    service = TradingService(exchange, _settings(), lambda *_args: None)
    service._executor = exchange
    exchange.positions = [Position(
        "BTCUSDT", Direction.SHORT, Decimal("0.5"), Decimal(100), Decimal(105),
        Decimal(90), datetime(2025, 1, 6, 12, tzinfo=UTC), id="position-1",
    )]

    service.stop(close_positions=True)

    close = exchange.orders[-1]
    assert close.side == OrderSide.BUY
    assert close.quantity == Decimal("0.5")
    assert close.order_type == "MARKET"
    assert close.reduce_only is True
    assert exchange.positions == []
    assert service.live_positions == []


def test_live_cancellation_must_disappear_from_pending_orders(monkeypatch):
    class StickyExchange(LiveLimitExchange):
        def get_pending_orders(self, _symbol=None):
            return [
                {"orderId": order.id, "clientId": order.client_id, "status": "NEW", "symbol": order.symbol}
                for order in self.orders
            ]

    exchange = StickyExchange()
    service = TradingService(exchange, _settings(), lambda *_args: None)
    service._executor = exchange
    exchange.place_order(type("Pending", (), {"id": None, "client_id": "cb-owned", "symbol": "BTCUSDT"})())
    monkeypatch.setattr("services.trading_service.time.sleep", lambda _seconds: None)

    with pytest.raises(ExchangeError, match="did not confirm cancellation"):
        service.cancel_owned_pending_orders()


def test_grid_live_plan_uses_grid_client_ids_and_its_own_time_stop():
    exchange = LiveLimitExchange()
    settings = AppSettings(strategy="grid_strategy", entry_timeframe="15m", higher_timeframe="4h", risk_per_trade=0.5, leverage=2)
    logs = []
    service = TradingService(exchange, settings, lambda category, message: logs.append((category, message)))
    service._executor = exchange
    service.strategy = GridStrategy(settings)
    signal_time = datetime(2025, 1, 6, 12, tzinfo=UTC)
    row = pd.Series({
        "signal": "LONG", "entry_levels": (100, 98), "entry_weights": (1, 1),
        "strategy_stop": 95, "strategy_tp1": 110, "strategy_tp2": 115,
        "tp1_fraction": 0.5, "limit_expiry_bars": 6, "time_stop_bars": 24,
    })

    service._execute_sp2l_plan(row, signal_time)

    assert len(exchange.orders) == 4
    assert all(order.client_id.startswith("cbgrid") for order in exchange.orders)
    assert service._limit_plan_time_stop_bars == 24
    assert any("GRID LIVE LIMIT PLAN ARMED" in message for _, message in logs)


def test_real_test_order_is_reconciled_and_unfilled_remainder_is_cancelled(monkeypatch):
    exchange = LiveLimitExchange()
    service = TradingService(exchange, _settings(), lambda *_args: None)
    monkeypatch.setattr("services.trading_service.time.sleep", lambda _seconds: None)
    order = Order("BTCUSDT", OrderSide.BUY, Decimal("0.01"), order_type="LIMIT", price=Decimal("90"), stop_loss=Decimal("80"), take_profit=Decimal("110"))

    def get_order(*, order_id=None, client_id=None):
        return {"orderId": order_id, "status": "CANCELED" if order_id in exchange.cancelled else "NEW", "tradeQty": "0"}

    exchange.get_order = get_order
    result = service.place_test_order(exchange, order)

    assert result["order_id"] == "1"
    assert result["status"] == "CANCELED"
    assert result["may_have_position"] is False
    assert exchange.cancelled == ["1"]


def test_filled_test_order_is_reported_and_never_silently_closed():
    exchange = LiveLimitExchange()
    service = TradingService(exchange, _settings(), lambda *_args: None)
    order = Order("BTCUSDT", OrderSide.BUY, Decimal("0.01"), order_type="LIMIT", price=Decimal("100"), stop_loss=Decimal("90"), take_profit=Decimal("120"))
    exchange.get_order = lambda **_kwargs: {"orderId": "1", "status": "FILLED", "tradeQty": "0.01"}

    result = service.place_test_order(exchange, order)

    assert result["may_have_position"] is True
    assert result["cancel_attempted"] is False
    assert exchange.cancelled == []
