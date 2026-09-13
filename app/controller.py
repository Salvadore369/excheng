from __future__ import annotations

from config.settings import AppSettings, ConfigStore, load_credentials
from execution.bitunix_client import BitunixClient
from services.backtest_service import BacktestService
from services.trading_service import TradingService


class ApplicationController:
    def __init__(self, log_callback=lambda category, message: None, config_path="config.json") -> None:
        self.store = ConfigStore(config_path)
        self.settings = self.store.load()
        key, secret = load_credentials()
        self.client = BitunixClient(key, secret)
        self.backtests = BacktestService(self.client, self.settings)
        self.trading = TradingService(self.client, self.settings, log_callback)

    def update_settings(self, settings: AppSettings) -> None:
        self.store.save(settings)
        self.settings = settings
        self.backtests = BacktestService(self.client, settings)
        if self.trading.state.state.value == "STOPPED":
            self.trading = TradingService(self.client, settings, self.trading.log)

    def close(self) -> None:
        self.trading.stop()
        self.client.close()

