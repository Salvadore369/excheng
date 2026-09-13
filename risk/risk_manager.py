from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from models.domain import Direction, Instrument


class RiskError(ValueError):
    pass


class RiskManager:
    @staticmethod
    def stop_loss(entry: Decimal, atr: Decimal, multiplier: Decimal, direction: Direction) -> Decimal:
        distance = atr * multiplier
        if distance <= 0:
            raise RiskError("ATR stop distance must be positive")
        return entry - distance if direction == Direction.LONG else entry + distance

    @staticmethod
    def take_profit(entry: Decimal, stop: Decimal, risk_reward: Decimal, direction: Direction) -> Decimal:
        distance = abs(entry - stop) * risk_reward
        return entry + distance if direction == Direction.LONG else entry - distance

    @staticmethod
    def position_size(balance: Decimal, risk_percent: Decimal, entry: Decimal, stop: Decimal, instrument: Instrument, leverage: Decimal | None = None, fee_rate: Decimal = Decimal("0")) -> Decimal:
        if balance <= 0 or not (Decimal("0") < risk_percent <= Decimal("1")):
            raise RiskError("Balance and risk percentage are invalid")
        distance = abs(entry - stop)
        if distance <= 0:
            raise RiskError("Stop must differ from entry")
        raw = balance * (risk_percent / Decimal("100")) / distance
        if leverage is not None:
            if leverage < 1 or fee_rate < 0:
                raise RiskError("Leverage and fee rate are invalid")
            per_unit_cash = entry / leverage + entry * fee_rate
            if per_unit_cash <= 0:
                raise RiskError("Entry price is invalid")
            raw = min(raw, balance / per_unit_cash)
        quantum = Decimal(1).scaleb(-instrument.base_precision)
        quantity = raw.quantize(quantum, rounding=ROUND_DOWN)
        if quantity < instrument.min_trade_volume:
            raise RiskError(f"Quantity {quantity} is below minimum {instrument.min_trade_volume}")
        if quantity > instrument.max_market_volume:
            quantity = instrument.max_market_volume.quantize(quantum, rounding=ROUND_DOWN)
        if instrument.min_notional and quantity * entry < instrument.min_notional:
            raise RiskError("Order is below minimum notional")
        return quantity

    @staticmethod
    def validate_order(quantity: Decimal, price: Decimal | None, instrument: Instrument, *, market: bool = True) -> None:
        quantity_quantum = Decimal(1).scaleb(-instrument.base_precision)
        if quantity <= 0 or quantity != quantity.quantize(quantity_quantum):
            raise RiskError(f"Quantity must be positive with at most {instrument.base_precision} decimals")
        if quantity < instrument.min_trade_volume:
            raise RiskError(f"Quantity {quantity} is below minimum {instrument.min_trade_volume}")
        if market and quantity > instrument.max_market_volume:
            raise RiskError(f"Quantity {quantity} exceeds maximum market quantity {instrument.max_market_volume}")
        if price is not None:
            price_quantum = Decimal(1).scaleb(-instrument.quote_precision)
            if price <= 0 or price != price.quantize(price_quantum):
                raise RiskError(f"Price must be positive with at most {instrument.quote_precision} decimals")
            if instrument.min_notional and quantity * price < instrument.min_notional:
                raise RiskError("Order is below minimum notional")

    @staticmethod
    def quantize_price(price: Decimal, instrument: Instrument) -> Decimal:
        return price.quantize(Decimal(1).scaleb(-instrument.quote_precision), rounding=ROUND_DOWN)
