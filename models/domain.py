from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class SignalType(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class AppState(StrEnum):
    STOPPED = "STOPPED"
    CONNECTING = "CONNECTING"
    RUNNING_BACKTEST = "RUNNING_BACKTEST"
    RUNNING_PAPER = "RUNNING_PAPER"
    RUNNING_LIVE = "RUNNING_LIVE"
    ERROR = "ERROR"


@dataclass(slots=True)
class Instrument:
    symbol: str
    base_precision: int
    quote_precision: int
    min_trade_volume: Decimal
    max_market_volume: Decimal
    min_leverage: int
    max_leverage: int
    status: str = "OPEN"
    api_supported: bool = True
    min_notional: Decimal | None = None


@dataclass(slots=True)
class Signal:
    timestamp: datetime
    symbol: str
    type: SignalType
    price: Decimal
    atr: Decimal
    reason: str
    trend: str


@dataclass(slots=True)
class Order:
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: str = "MARKET"
    price: Decimal | None = None
    reduce_only: bool = False
    client_id: str | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    id: str | None = None
    status: str = "NEW"


@dataclass(slots=True)
class Position:
    symbol: str
    direction: Direction
    quantity: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    opened_at: datetime
    fees: Decimal = Decimal("0")
    id: str | None = None

    def unrealized_pnl(self, price: Decimal) -> Decimal:
        delta = price - self.entry_price
        if self.direction == Direction.SHORT:
            delta = -delta
        return delta * self.quantity - self.fees


@dataclass(slots=True)
class Trade:
    entry_time: datetime
    exit_time: datetime
    symbol: str
    direction: Direction
    size: Decimal
    entry_price: Decimal
    exit_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    fees: Decimal
    pnl: Decimal
    exit_reason: str


@dataclass(slots=True)
class BacktestResult:
    starting_balance: Decimal
    final_balance: Decimal
    trades: list[Trade]
    equity_curve: list[tuple[datetime, Decimal]]
    metrics: dict[str, float] = field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def decimalize(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))

