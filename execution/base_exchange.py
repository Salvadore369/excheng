from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from models.domain import Instrument, Order, Position


class ExchangeError(RuntimeError):
    """Sanitized exchange error. It must never contain credentials."""


class AuthenticationError(ExchangeError):
    pass


class TemporaryExchangeError(ExchangeError):
    pass


class BaseExchange(ABC):
    @abstractmethod
    def get_instrument(self, symbol: str) -> Instrument: ...

    @abstractmethod
    def get_last_price(self, symbol: str) -> Decimal: ...

    @abstractmethod
    def place_order(self, order: Order) -> Order: ...

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool: ...

    @abstractmethod
    def get_positions(self, symbol: str | None = None) -> list[Position]: ...

