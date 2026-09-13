"""Safe offscreen GUI/backtest acceptance check; it never enables live trading."""
from __future__ import annotations

import os
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    start, end = date.today() - timedelta(days=14), date.today()
    window.bt_start.setDate(QDate(start.year, start.month, start.day))
    window.bt_end.setDate(QDate(end.year, end.month, end.day))
    window.start_backtest()
    checks = 0

    def poll() -> None:
        nonlocal checks
        checks += 1
        if window.result is not None or checks >= 600:
            app.quit()

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(100)
    app.exec()
    if window.result and window.result.trades:
        trade = window.result.trades[0]
        values = [float(trade.entry_price), float(trade.exit_price)]
        chart_frame = pd.DataFrame({
            "timestamp": [trade.entry_time, trade.exit_time],
            "open": values, "high": [value * 1.01 for value in values],
            "low": [value * 0.99 for value in values], "close": values,
            "volume": [1.0, 1.0], "ema_fast": values, "ema_slow": values,
        })
        window.market_chart.set_candles(chart_frame, [trade])
    success = window.result is not None and window.metrics.count() == 13
    print(f"gui_backtest_success={success} trade_rows={window.trade_table.rowCount()} metrics={window.metrics.count()}")
    window.controller.close()
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
