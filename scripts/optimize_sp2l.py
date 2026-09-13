from __future__ import annotations

import argparse
import json
import math
import os
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from backtesting.backtester import Backtester
from config.settings import AppSettings, ConfigStore
from models.domain import Instrument
from strategies.sp2l import SP2LStrategy


ENTRY_PATH = Path("cache/BTCUSDT_5m_1780073700000_1788048000000.csv")
HIGHER_PATH = Path("cache/BTCUSDT_15m_1780022700000_1788048000000.csv")
START = datetime(2026, 5, 30, tzinfo=UTC)
DEV_END = datetime(2026, 8, 1, tzinfo=UTC)
END = datetime(2026, 8, 30, tzinfo=UTC)
FOLDS = (
    (datetime(2026, 5, 30, tzinfo=UTC), datetime(2026, 6, 20, tzinfo=UTC)),
    (datetime(2026, 6, 20, tzinfo=UTC), datetime(2026, 7, 11, tzinfo=UTC)),
    (datetime(2026, 7, 11, tzinfo=UTC), DEV_END),
)

_ENTRY: pd.DataFrame | None = None
_HIGHER: pd.DataFrame | None = None
_BASE: AppSettings | None = None
_INSTRUMENT = Instrument("BTCUSDT", 3, 1, Decimal("0.001"), Decimal("1000"), 1, 125)


@dataclass(frozen=True)
class Trial:
    number: int
    params: dict[str, object]


def _init_worker() -> None:
    global _ENTRY, _HIGHER, _BASE
    _ENTRY = pd.read_csv(ENTRY_PATH)
    _ENTRY["timestamp"] = pd.to_datetime(_ENTRY.timestamp, utc=True)
    _HIGHER = pd.read_csv(HIGHER_PATH)
    _HIGHER["timestamp"] = pd.to_datetime(_HIGHER.timestamp, utc=True)
    _BASE = ConfigStore("config.json").load()


def _run_period(settings: AppSettings, start: datetime, end: datetime) -> dict[str, float]:
    assert _ENTRY is not None and _HIGHER is not None
    entry = _ENTRY[_ENTRY.timestamp < end]
    higher = _HIGHER[_HIGHER.timestamp < end]
    result = Backtester(settings, SP2LStrategy(settings), _INSTRUMENT).run(
        entry, higher, Decimal("10000"), start_at=start
    )
    return {key: float(value) for key, value in result.metrics.items()}


def _evaluate_dev(trial: Trial) -> dict[str, object]:
    assert _BASE is not None
    settings = _BASE.model_copy(update=trial.params)
    folds = [_run_period(settings, start, end) for start, end in FOLDS]
    returns = [fold["Total Return %"] for fold in folds]
    drawdowns = [fold["Maximum Drawdown %"] for fold in folds]
    trades = sum(fold["Total Trades"] for fold in folds)
    profit_factors = [min(fold["Profit Factor"], 5.0) for fold in folds]
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
    # Stability-first objective: reward returns and PF while explicitly
    # penalizing dispersion, drawdown, negative folds, and tiny samples.
    score = (
        mean_return
        + 0.45 * min(returns)
        - 0.35 * math.sqrt(variance)
        - 0.20 * (sum(drawdowns) / len(drawdowns))
        + 0.20 * (sum(profit_factors) / len(profit_factors) - 1.0)
        - max(0.0, 12.0 - trades) * 0.15
    )
    return {
        "trial": trial.number,
        "score": score,
        "params": trial.params,
        "fold_returns": returns,
        "fold_drawdowns": drawdowns,
        "fold_profit_factors": profit_factors,
        "trades": trades,
    }


def _evaluate_final(candidate: dict[str, object]) -> dict[str, object]:
    assert _BASE is not None
    settings = _BASE.model_copy(update=candidate["params"])
    candidate = dict(candidate)
    candidate["development"] = _run_period(settings, START, DEV_END)
    candidate["holdout"] = _run_period(settings, DEV_END, END)
    candidate["full_period"] = _run_period(settings, START, END)
    return candidate


def _sample_trials(count: int, seed: int, *, focused: bool = False) -> list[Trial]:
    rng = random.Random(seed)
    trials: list[Trial] = []
    seen: set[str] = set()
    while len(trials) < count:
        minimum = rng.choice([3, 4, 4, 5] if focused else [3, 3, 3, 4, 5])
        maximum_choices = [7, 9] if focused else [5, 7, 9]
        maximum = rng.choice([value for value in maximum_choices if value >= minimum])
        ema_filter = rng.choice([True, True, False] if focused else [False, False, True])
        params: dict[str, object] = {
            "sp2l_min_spike_bars": minimum,
            "sp2l_max_spike_bars": maximum,
            "sp2l_breakout_lookback": rng.choice([10, 15, 20] if focused else [10, 15, 20, 30, 40]),
            "sp2l_movement_atr": rng.choice([1.0, 1.25, 1.5] if focused else [0.75, 1.0, 1.25, 1.5, 2.0, 2.5]),
            "sp2l_strong_body_ratio": rng.choice([0.65, 0.75] if focused else [0.45, 0.55, 0.65, 0.75]),
            "sp2l_max_doji_ratio": rng.choice([0.35, 0.5] if focused else [0.0, 0.2, 0.35, 0.5]),
            "sp2l_dirty_lookback": rng.choice([10, 15, 20] if focused else [5, 10, 15, 20]),
            "sp2l_dirty_overlap_ratio": rng.choice([0.60, 0.70] if focused else [0.60, 0.70, 0.80, 0.90]),
            "sp2l_session_filter": rng.choice([False, False, True] if focused else [False, True, True]),
            "sp2l_ema_origin_filter": ema_filter,
            "sp2l_ema_origin_atr": rng.choice([2.0, 3.0, 4.0] if focused else [0.5, 1.0, 1.5, 2.0, 3.0]) if ema_filter else 1.0,
            "sp2l_direction_filter": rng.choice(["BOTH", "BOTH", "SHORT"] if focused else ["BOTH", "BOTH", "LONG", "SHORT"]),
            "sp2l_trend_filter": rng.choice(["HTF_EMA60", "HTF_EMA60", "EMA60"] if focused else ["NONE", "EMA60", "HTF_EMA60"]),
            "sp2l_stop_mode": rng.choice(["SPIKE_ORIGIN"] if focused else ["SPIKE_ORIGIN", "FOLLOW_THROUGH"]),
            "sp2l_stop_buffer_atr": rng.choice([0.05, 0.10] if focused else [0.0, 0.05, 0.10, 0.20]),
            "sp2l_entry2_mode": rng.choice(["EMA60", "EMA60", "ENTRY_STOP_MIDPOINT"] if focused else ["ENTRY_STOP_MIDPOINT", "SPIKE_50", "EMA60"]),
            "sp2l_enable_third_entry": rng.choice([False] if focused else [False, False, True]),
            "sp2l_tp1_rr": rng.choice([1.0, 1.5, 2.0] if focused else [1.0, 1.5, 2.0, 2.5]),
            "sp2l_tp1_fraction": rng.choice([0.3, 0.5, 0.7] if focused else [0.0, 0.3, 0.5, 0.7]),
            "risk_reward": rng.choice([2.0, 2.5, 3.0] if focused else [2.0, 2.5, 3.0, 4.0]),
            "sp2l_time_stop_bars": rng.choice([15, 20, 30] if focused else [5, 10, 15, 20, 30, 40]),
            "sp2l_limit_expiry_bars": rng.choice([3, 5, 8] if focused else [2, 3, 5, 8, 12]),
        }
        key = json.dumps(params, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        trials.append(Trial(len(trials), params))
    return trials


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic walk-forward SP2L hyperparameter search")
    parser.add_argument("--trials", type=int, default=768)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--workers", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--focused", action="store_true", help="Search the robust neighborhood found by the broad pass")
    args = parser.parse_args()
    if not ENTRY_PATH.exists() or not HIGHER_PATH.exists():
        raise SystemExit("Required cached BTCUSDT 5m/15m files are missing")

    trials = _sample_trials(args.trials, args.seed, focused=args.focused)
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker) as pool:
        development = list(pool.map(_evaluate_dev, trials, chunksize=1))
    development.sort(key=lambda item: float(item["score"]), reverse=True)
    finalists = development[: args.top]
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker) as pool:
        validated = list(pool.map(_evaluate_final, finalists, chunksize=1))
    validated.sort(key=lambda item: float(item["score"]), reverse=True)

    output = Path("optimization")
    output.mkdir(exist_ok=True)
    payload = {
        "method": "three chronological development folds; untouched 2026-08-01 through 2026-08-30 holdout",
        "trials": args.trials,
        "seed": args.seed,
        "fixed": {"risk_per_trade": 0.5, "trading_fee": 0.0006, "slippage": 0.0003, "gap_filter": True},
        "results": validated,
    }
    path = output / ("sp2l_walk_forward_focused.json" if args.focused else "sp2l_walk_forward.json")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(path), "best": validated[0]}, indent=2))


if __name__ == "__main__":
    main()
