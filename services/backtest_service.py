from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from threading import Event

from backtesting.backtester import Backtester
from config.settings import AppSettings
from data.historical_data import HistoricalDataService, timeframe_milliseconds
from strategies.registry import create_strategy


class BacktestService:
    def __init__(self, client, settings: AppSettings) -> None:
        self.client, self.settings = client, settings
        self.data = HistoricalDataService(client, settings.cache_directory)

    def run(self, start: datetime, end: datetime, initial_balance: Decimal, cancel: Event | None = None, progress=None):
        strategy = create_strategy(self.settings)
        warmup = strategy.warmup_bars + 5
        entry_start = start - timedelta(milliseconds=timeframe_milliseconds(self.settings.entry_timeframe) * warmup)
        higher_start = start - timedelta(milliseconds=timeframe_milliseconds(self.settings.higher_timeframe) * warmup)
        entry = self.data.load(self.settings.symbol, self.settings.entry_timeframe, entry_start, end, progress, cancel)
        higher = self.data.load(self.settings.symbol, self.settings.higher_timeframe, higher_start, end, progress, cancel)
        if cancel and cancel.is_set():
            raise InterruptedError("Backtest cancelled")
        instrument = self.client.get_instrument(self.settings.symbol)
        return Backtester(self.settings, strategy, instrument).run(
            entry, higher, initial_balance, cancel, progress, start
        )
