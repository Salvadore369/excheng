from __future__ import annotations

import math
from decimal import Decimal

import numpy as np

from models.domain import Trade


def calculate_metrics(starting: Decimal, final: Decimal, trades: list[Trade], equity: list[tuple]) -> dict[str, float]:
    pnls = np.array([float(t.pnl) for t in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    values = np.array([float(v) for _, v in equity], dtype=float)
    peaks = np.maximum.accumulate(values) if len(values) else np.array([float(starting)])
    drawdowns = (peaks - values) / np.where(peaks == 0, 1, peaks) if len(values) else np.array([0.0])
    returns = np.diff(values) / values[:-1] if len(values) > 1 else np.array([])
    periods_per_year = 0.0
    if len(equity) > 1:
        seconds = [(equity[i][0] - equity[i - 1][0]).total_seconds() for i in range(1, len(equity))]
        median_seconds = float(np.median([value for value in seconds if value > 0])) if any(value > 0 for value in seconds) else 0.0
        periods_per_year = 365.25 * 24 * 3600 / median_seconds if median_seconds else 0.0
    sharpe = float(np.mean(returns) / np.std(returns) * math.sqrt(periods_per_year)) if len(returns) > 2 and np.std(returns) > 0 and periods_per_year else 0.0
    gross_profit, gross_loss = wins.sum() if len(wins) else 0.0, abs(losses.sum()) if len(losses) else 0.0
    average_rr = float(np.mean([float(t.pnl) / max(float(abs(t.entry_price - t.stop_loss) * t.size), 1e-12) for t in trades])) if trades else 0.0
    return {
        "Starting Balance": float(starting), "Final Balance": float(final),
        "Total Return %": float((final / starting - 1) * 100), "Total Trades": float(len(trades)),
        "Wins": float(len(wins)), "Losses": float(len(losses)), "Win Rate %": float(len(wins) / len(trades) * 100) if trades else 0.0,
        "Profit Factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
        "Maximum Drawdown %": float(drawdowns.max() * 100), "Average Win": float(wins.mean()) if len(wins) else 0.0,
        "Average Loss": float(losses.mean()) if len(losses) else 0.0, "Average Risk/Reward": average_rr, "Sharpe Ratio": sharpe,
    }
