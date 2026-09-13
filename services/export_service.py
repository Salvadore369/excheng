from __future__ import annotations

import csv
from pathlib import Path

from models.domain import Trade


TRADE_COLUMNS = ["entry_time", "exit_time", "symbol", "direction", "size", "entry_price", "exit_price", "stop_loss", "take_profit", "fees", "pnl", "exit_reason"]


def export_trades_csv(path: str | Path, trades: list[Trade]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(TRADE_COLUMNS)
        for trade in trades:
            writer.writerow([trade.entry_time.isoformat(), trade.exit_time.isoformat(), trade.symbol, trade.direction.value, trade.size, trade.entry_price, trade.exit_price, trade.stop_loss, trade.take_profit, trade.fees, trade.pnl, trade.exit_reason])
    return destination
