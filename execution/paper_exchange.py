from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from models.domain import Direction, Instrument, Order, OrderSide, Position
from .base_exchange import BaseExchange, ExchangeError


class PaperExchange(BaseExchange):
    def __init__(self, market: BaseExchange, balance: Decimal = Decimal("10000"), fee_rate: Decimal = Decimal("0.0006"), slippage: Decimal = Decimal("0.0002"), leverage: Decimal = Decimal("5")) -> None:
        self.market = market
        self.balance = balance
        self.available_balance = balance
        self.fee_rate, self.slippage = fee_rate, slippage
        self.leverage = leverage
        self.positions: list[Position] = []
        self.orders: list[Order] = []
        self._margins: dict[str, Decimal] = {}
        self._order_reservations: dict[str, Decimal] = {}
        self.realized_pnl = Decimal("0")
        self._lock = RLock()

    def get_instrument(self, symbol: str) -> Instrument: return self.market.get_instrument(symbol)
    def get_last_price(self, symbol: str) -> Decimal: return self.market.get_last_price(symbol)
    def get_positions(self, symbol: str | None = None) -> list[Position]:
        with self._lock:
            return [p for p in self.positions if not symbol or p.symbol == symbol]

    def unrealized_pnl(self, prices: dict[str, Decimal] | None = None) -> Decimal:
        prices = prices or {}
        with self._lock:
            return sum((p.unrealized_pnl(prices.get(p.symbol, p.entry_price)) for p in self.positions), Decimal("0"))

    def place_order(self, order: Order) -> Order:
        with self._lock:
            if order.quantity <= 0:
                raise ExchangeError("Paper order quantity must be positive")
            price = order.price or self.get_last_price(order.symbol)
            if order.order_type == "LIMIT" and order.price is None:
                raise ExchangeError("Paper limit order requires a price")
            adverse = Decimal("1") + self.slippage if order.side == OrderSide.BUY else Decimal("1") - self.slippage
            fill = price if order.order_type == "LIMIT" else price * adverse
            notional, fee = fill * order.quantity, fill * order.quantity * self.fee_rate
            margin = notional / self.leverage if not order.reduce_only else Decimal("0")
            if not order.reduce_only and fee + margin > self.available_balance:
                raise ExchangeError("Insufficient paper balance")
            order.id = f"paper-{len(self.orders)+1}"
            if order.order_type == "LIMIT" and not order.reduce_only:
                order.status = "NEW"
                self.orders.append(order)
                reservation = fee + margin
                self.available_balance -= reservation
                self._order_reservations[order.id] = reservation
                return order
            order.status = "FILLED"
            self.orders.append(order)
            if not order.reduce_only:
                direction = Direction.LONG if order.side == OrderSide.BUY else Direction.SHORT
                self.positions.append(Position(order.symbol, direction, order.quantity, fill, order.stop_loss or Decimal("0"), order.take_profit or Decimal("0"), datetime.now(timezone.utc), fee, order.id))
                self.balance -= fee
                self.available_balance -= fee + margin
                self._margins[order.id] = margin
            else:
                candidates = [p for p in self.positions if p.symbol == order.symbol and (not order.client_id or p.id == order.client_id)]
                if not candidates: raise ExchangeError("No paper position to reduce")
                position = candidates[0]
                if order.quantity != position.quantity:
                    raise ExchangeError("Initial paper model only supports closing the full position")
                expected_side = OrderSide.SELL if position.direction == Direction.LONG else OrderSide.BUY
                if order.side != expected_side:
                    raise ExchangeError("Reduce-only order side does not close the paper position")
                gross = (fill - position.entry_price) * position.quantity * (Decimal("1") if position.direction == Direction.LONG else Decimal("-1"))
                margin = self._margins.pop(position.id or "", Decimal("0"))
                net = gross - position.fees - fee
                self.realized_pnl += net
                self.balance += gross - fee
                self.available_balance += margin + gross - fee
                self.positions.remove(position)
            return order

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        with self._lock:
            for order in self.orders:
                if order.id == order_id and order.symbol == symbol and order.status not in {"FILLED", "CANCELED"}:
                    order.status = "CANCELED"
                    self.available_balance += self._order_reservations.pop(order_id, Decimal("0"))
                    return True
            return False

    def _fill_limit(self, order: Order) -> None:
        assert order.id and order.price is not None
        fill = order.price
        fee = fill * order.quantity * self.fee_rate
        margin = fill * order.quantity / self.leverage
        reservation = self._order_reservations.pop(order.id, Decimal("0"))
        self.available_balance += reservation - fee - margin
        self.balance -= fee
        direction = Direction.LONG if order.side == OrderSide.BUY else Direction.SHORT
        self.positions.append(Position(order.symbol, direction, order.quantity, fill,
            order.stop_loss or Decimal("0"), order.take_profit or Decimal("0"),
            datetime.now(timezone.utc), fee, order.id))
        self._margins[order.id] = margin
        order.status = "FILLED"

    def process_price(self, symbol: str, high: Decimal, low: Decimal) -> list[str]:
        events: list[str] = []
        with self._lock:
            newly_filled: set[str] = set()
            for order in self.orders:
                if order.symbol != symbol or order.status != "NEW" or order.order_type != "LIMIT":
                    continue
                touched = low <= order.price if order.side == OrderSide.BUY else high >= order.price
                if touched:
                    self._fill_limit(order)
                    if order.id:
                        newly_filled.add(order.id)
                    events.append("LIMIT_FILL")
            for position in list(self.positions):
                if position.symbol != symbol: continue
                if position.direction == Direction.LONG:
                    stop_hit, target_hit = low <= position.stop_loss, high >= position.take_profit
                else:
                    stop_hit, target_hit = high >= position.stop_loss, low <= position.take_profit
                if stop_hit or target_hit:
                    # A stop is always honored on the fill bar. A favorable
                    # target is deferred because OHLC cannot prove it occurred
                    # after the resting limit filled.
                    if position.id in newly_filled and target_hit and not stop_hit:
                        continue
                    # Conservative and deterministic: SL wins if both occur without ticks.
                    exit_price, reason = (position.stop_loss, "STOP_LOSS") if stop_hit else (position.take_profit, "TAKE_PROFIT")
                    side = OrderSide.SELL if position.direction == Direction.LONG else OrderSide.BUY
                    self.place_order(Order(symbol, side, position.quantity, price=exit_price,
                        reduce_only=True, client_id=position.id))
                    events.append(reason)
        return events
