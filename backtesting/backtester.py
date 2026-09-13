from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from threading import Event

import pandas as pd

from config.settings import AppSettings
from models.domain import (
    BacktestResult,
    Direction,
    Instrument,
    Position,
    SignalType,
    Trade,
)
from risk.risk_manager import RiskError, RiskManager
from strategies.base_strategy import BaseStrategy

from .metrics import calculate_metrics


@dataclass
class _LimitFill:
    price: Decimal
    quantity: Decimal
    fee: Decimal
    opened_at: object


@dataclass
class _LimitPlan:
    direction: Direction
    levels: list[Decimal]
    quantities: list[Decimal]
    stop: Decimal
    tp1: Decimal
    tp2: Decimal
    tp1_fraction: Decimal
    signal_index: int
    expires_after: int
    time_stop_bars: int
    fills: list[_LimitFill] = field(default_factory=list)
    first_fill_index: int | None = None
    tp1_taken: bool = False

    @property
    def quantity(self) -> Decimal:
        return sum((fill.quantity for fill in self.fills), Decimal(0))

    @property
    def entry_fees(self) -> Decimal:
        return sum((fill.fee for fill in self.fills), Decimal(0))

    @property
    def average_entry(self) -> Decimal:
        quantity = self.quantity
        return sum((fill.price * fill.quantity for fill in self.fills), Decimal(0)) / quantity


class Backtester:
    """Sequential OHLC backtester: close-N signal, open-(N+1) execution."""

    def __init__(self, settings: AppSettings, strategy: BaseStrategy, instrument: Instrument) -> None:
        self.settings, self.strategy, self.instrument = settings, strategy, instrument

    def run(self, entry: pd.DataFrame, higher: pd.DataFrame, initial_balance: Decimal, cancel: Event | None = None, progress=None, start_at=None) -> BacktestResult:
        prepared = self.strategy.prepare(entry, higher)
        if start_at is not None:
            prepared = prepared[pd.to_datetime(prepared["entry_close_time"], utc=True) >= pd.Timestamp(start_at)].reset_index(drop=True)
        if getattr(self.strategy, "uses_limit_plans", False):
            return self._run_limit_plans(prepared, initial_balance, cancel, progress)
        balance = initial_balance
        position: Position | None = None
        pending: tuple[Direction, Decimal] | None = None
        trades: list[Trade] = []
        equity: list[tuple] = []
        diagnostic_signal_consumed = False
        fee_rate, slippage = Decimal(str(self.settings.trading_fee)), Decimal(str(self.settings.slippage))
        for i, row in prepared.iterrows():
            if cancel and cancel.is_set(): break
            timestamp = pd.Timestamp(row["entry_close_time"]).to_pydatetime()
            open_timestamp = pd.Timestamp(row["timestamp"]).to_pydatetime()
            open_price, high, low, close = (
                Decimal(str(value))
                for value in (row["open"], row["high"], row["low"], row["close"])
            )
            if pending and position is None and pd.notna(row.get("atr")):
                direction, signal_atr = pending
                fill = open_price * (Decimal(1) + slippage if direction == Direction.LONG else Decimal(1) - slippage)
                stop = RiskManager.stop_loss(fill, signal_atr, Decimal(str(self.settings.atr_stop_multiplier)), direction)
                target = RiskManager.take_profit(fill, stop, Decimal(str(self.settings.risk_reward)), direction)
                stop = RiskManager.quantize_price(stop, self.instrument)
                target = RiskManager.quantize_price(target, self.instrument)
                try:
                    quantity = RiskManager.position_size(balance, Decimal(str(self.settings.risk_per_trade)), fill, stop, self.instrument, Decimal(str(self.settings.leverage)), fee_rate)
                    entry_fee = fill * quantity * fee_rate
                    balance -= entry_fee
                    position = Position(self.settings.symbol, direction, quantity, fill, stop, target, open_timestamp, entry_fee)
                except RiskError:
                    pass
                pending = None
            if position is not None:
                if position.direction == Direction.LONG:
                    stop_hit, target_hit = low <= position.stop_loss, high >= position.take_profit
                else:
                    stop_hit, target_hit = high >= position.stop_loss, low <= position.take_profit
                if stop_hit or target_hit:
                    if stop_hit and position.direction == Direction.LONG:
                        raw_exit = min(position.stop_loss, open_price)
                    elif stop_hit:
                        raw_exit = max(position.stop_loss, open_price)
                    else:
                        raw_exit = position.take_profit
                    reason = "STOP_LOSS" if stop_hit else "TAKE_PROFIT"
                    exit_fill = raw_exit * (Decimal(1) - slippage if position.direction == Direction.LONG else Decimal(1) + slippage)
                    gross = (exit_fill - position.entry_price) * position.quantity
                    if position.direction == Direction.SHORT: gross = -gross
                    exit_fee = exit_fill * position.quantity * fee_rate
                    net = gross - position.fees - exit_fee
                    # Entry fee was debited at entry; credit gross less exit fee here.
                    balance += gross - exit_fee
                    trades.append(Trade(position.opened_at, timestamp, position.symbol, position.direction, position.quantity,
                        position.entry_price, exit_fill, position.stop_loss, position.take_profit, position.fees + exit_fee, net, reason))
                    position = None
            if position:
                gross_unrealized = (close - position.entry_price) * position.quantity * (Decimal(1) if position.direction == Direction.LONG else Decimal(-1))
            else:
                gross_unrealized = Decimal(0)
            marked = balance + gross_unrealized
            equity.append((timestamp, marked))
            if (
                position is None
                and row.get("signal") in {SignalType.LONG.value, SignalType.SHORT.value}
                and not (getattr(self.strategy, "diagnostic_one_shot", False) and diagnostic_signal_consumed)
                and (not self.settings.block_weekends or timestamp.weekday() < 5)
                and pd.notna(row.get("atr"))
            ):
                pending = (Direction(str(row["signal"])), Decimal(str(row["atr"])))
                if getattr(self.strategy, "diagnostic_one_shot", False):
                    diagnostic_signal_consumed = True
            if progress and i % 50 == 0: progress(int((i + 1) / len(prepared) * 100))
        if position is not None and len(prepared):
            row = prepared.iloc[-1]
            timestamp = pd.Timestamp(row["entry_close_time"]).to_pydatetime()
            close = Decimal(str(row["close"]))
            fill = close * (Decimal(1) - slippage if position.direction == Direction.LONG else Decimal(1) + slippage)
            gross = (fill - position.entry_price) * position.quantity * (Decimal(1) if position.direction == Direction.LONG else Decimal(-1))
            exit_fee = fill * position.quantity * fee_rate
            net = gross - position.fees - exit_fee
            balance += gross - exit_fee
            trades.append(Trade(position.opened_at, timestamp, position.symbol, position.direction, position.quantity, position.entry_price, fill,
                position.stop_loss, position.take_profit, position.fees + exit_fee, net, "END_OF_DATA"))
            equity[-1] = (timestamp, balance)
        result = BacktestResult(initial_balance, balance, trades, equity)
        result.metrics = calculate_metrics(initial_balance, balance, trades, equity)
        return result

    def _run_limit_plans(self, prepared: pd.DataFrame, initial_balance: Decimal, cancel: Event | None, progress) -> BacktestResult:
        """Sequential simulator for SP2L resting limits and scaled exits.

        Signals arm after candle close. Limits can fill only from the next bar.
        A same-bar stop always wins; profit targets are not credited on the bar
        of the first fill because OHLC data cannot prove the favorable ordering.
        """
        balance = initial_balance
        plan: _LimitPlan | None = None
        trades: list[Trade] = []
        equity: list[tuple] = []
        fee_rate = Decimal(str(self.settings.trading_fee))
        slippage = Decimal(str(self.settings.slippage))
        quantum = Decimal(1).scaleb(-self.instrument.base_precision)

        def close_quantity(row, quantity: Decimal, raw_exit: Decimal, reason: str) -> None:
            nonlocal balance, plan
            assert plan is not None and plan.fills
            quantity = min(quantity, plan.quantity).quantize(quantum, rounding=ROUND_DOWN)
            if quantity <= 0:
                return
            average = plan.average_entry
            entry_fee = plan.entry_fees * quantity / plan.quantity
            exit_fill = raw_exit * (
                Decimal(1) - slippage if plan.direction == Direction.LONG else Decimal(1) + slippage
            )
            gross = (exit_fill - average) * quantity
            if plan.direction == Direction.SHORT:
                gross = -gross
            exit_fee = exit_fill * quantity * fee_rate
            balance += gross - exit_fee
            opened_at = min(fill.opened_at for fill in plan.fills)
            timestamp = pd.Timestamp(row["entry_close_time"]).to_pydatetime()
            trades.append(Trade(opened_at, timestamp, self.settings.symbol, plan.direction, quantity,
                average, exit_fill, plan.stop, plan.tp2, entry_fee + exit_fee,
                gross - entry_fee - exit_fee, reason))
            remaining = quantity
            new_fills: list[_LimitFill] = []
            for fill in plan.fills:
                if remaining <= 0:
                    new_fills.append(fill)
                    continue
                taken = min(fill.quantity, remaining)
                leftover = fill.quantity - taken
                remaining -= taken
                if leftover > 0:
                    new_fills.append(_LimitFill(fill.price, leftover, fill.fee * leftover / fill.quantity, fill.opened_at))
            plan.fills = new_fills

        for i, row in prepared.iterrows():
            if cancel and cancel.is_set():
                break
            timestamp = pd.Timestamp(row["entry_close_time"]).to_pydatetime()
            open_timestamp = pd.Timestamp(row["timestamp"]).to_pydatetime()
            open_price, high, low, close = (Decimal(str(row[name])) for name in ("open", "high", "low", "close"))

            if plan is not None:
                had_position_before_bar = bool(plan.fills)
                if i > plan.signal_index:
                    remaining_levels: list[Decimal] = []
                    remaining_quantities: list[Decimal] = []
                    for level, quantity in zip(plan.levels, plan.quantities, strict=True):
                        touched = low <= level if plan.direction == Direction.LONG else high >= level
                        if touched:
                            fill_price = min(level, open_price) if plan.direction == Direction.LONG else max(level, open_price)
                            fee = fill_price * quantity * fee_rate
                            if fee < balance:
                                balance -= fee
                                plan.fills.append(_LimitFill(fill_price, quantity, fee, open_timestamp))
                                if plan.first_fill_index is None:
                                    plan.first_fill_index = i
                            continue
                        remaining_levels.append(level)
                        remaining_quantities.append(quantity)
                    plan.levels, plan.quantities = remaining_levels, remaining_quantities

                if plan.fills:
                    stop_hit = low <= plan.stop if plan.direction == Direction.LONG else high >= plan.stop
                    if stop_hit:
                        raw_exit = min(plan.stop, open_price) if plan.direction == Direction.LONG else max(plan.stop, open_price)
                        close_quantity(row, plan.quantity, raw_exit, "STOP_LOSS")
                        plan = None
                    elif had_position_before_bar:
                        tp2_hit = high >= plan.tp2 if plan.direction == Direction.LONG else low <= plan.tp2
                        tp1_hit = high >= plan.tp1 if plan.direction == Direction.LONG else low <= plan.tp1
                        if tp2_hit:
                            close_quantity(row, plan.quantity, plan.tp2, "TAKE_PROFIT_2")
                            plan = None
                        elif tp1_hit and not plan.tp1_taken:
                            partial = (plan.quantity * plan.tp1_fraction).quantize(quantum, rounding=ROUND_DOWN)
                            close_quantity(row, partial, plan.tp1, "TAKE_PROFIT_1")
                            if plan is not None:
                                plan.tp1_taken = True
                                plan.levels, plan.quantities = [], []
                        elif plan.first_fill_index is not None and i - plan.first_fill_index >= plan.time_stop_bars:
                            close_quantity(row, plan.quantity, close, "TIME_STOP")
                            plan = None

                if plan is not None and i - plan.signal_index >= plan.expires_after:
                    plan.levels, plan.quantities = [], []
                    if not plan.fills:
                        plan = None

            unrealized = Decimal(0)
            if plan is not None and plan.fills:
                unrealized = (close - plan.average_entry) * plan.quantity
                if plan.direction == Direction.SHORT:
                    unrealized = -unrealized
            equity.append((timestamp, balance + unrealized))

            if plan is None and row.get("signal") in {SignalType.LONG.value, SignalType.SHORT.value}:
                if self.settings.block_weekends and timestamp.weekday() >= 5:
                    continue
                levels_raw, weights_raw = row.get("entry_levels"), row.get("entry_weights")
                if not isinstance(levels_raw, (tuple, list)) or not isinstance(weights_raw, (tuple, list)):
                    continue
                direction = Direction(str(row["signal"]))
                levels = [RiskManager.quantize_price(Decimal(str(value)), self.instrument) for value in levels_raw]
                weights = [Decimal(str(value)) for value in weights_raw]
                weighted_entry = sum((level * weight for level, weight in zip(levels, weights, strict=True)), Decimal(0)) / sum(weights)
                stop = RiskManager.quantize_price(Decimal(str(row["strategy_stop"])), self.instrument)
                try:
                    total_quantity = RiskManager.position_size(balance, Decimal(str(self.settings.risk_per_trade)), weighted_entry,
                        stop, self.instrument, Decimal(str(self.settings.leverage)), fee_rate)
                except RiskError:
                    continue
                quantities = [
                    (total_quantity * weight / sum(weights)).quantize(quantum, rounding=ROUND_DOWN)
                    for weight in weights
                ]
                valid = [(level, quantity) for level, quantity in zip(levels, quantities, strict=True) if quantity >= self.instrument.min_trade_volume]
                if not valid:
                    continue
                levels, quantities = map(list, zip(*valid, strict=True))
                plan = _LimitPlan(direction, levels, quantities, stop,
                    RiskManager.quantize_price(Decimal(str(row["strategy_tp1"])), self.instrument),
                    RiskManager.quantize_price(Decimal(str(row["strategy_tp2"])), self.instrument),
                    Decimal(str(row["tp1_fraction"])), i, int(row["limit_expiry_bars"]), int(row["time_stop_bars"]))
            if progress and i % 50 == 0:
                progress(int((i + 1) / len(prepared) * 100))

        if plan is not None and plan.fills and len(prepared):
            row = prepared.iloc[-1]
            close_quantity(row, plan.quantity, Decimal(str(row["close"])), "END_OF_DATA")
            timestamp = pd.Timestamp(row["entry_close_time"]).to_pydatetime()
            equity[-1] = (timestamp, balance)
        result = BacktestResult(initial_balance, balance, trades, equity)
        result.metrics = calculate_metrics(initial_balance, balance, trades, equity)
        return result
