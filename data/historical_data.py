from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable

import pandas as pd


_TIMEFRAME_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000,
    "1w": 604_800_000, "1M": 2_592_000_000,
}


def timeframe_milliseconds(timeframe: str) -> int:
    try:
        return _TIMEFRAME_MS[timeframe]
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe: {timeframe}") from exc


def validate_candles(frame: pd.DataFrame, timeframe: str, *, allow_gaps: bool = False) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing candle columns: {', '.join(sorted(missing))}")
    clean = frame.copy()
    clean["timestamp"] = pd.to_datetime(clean["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        clean[column] = pd.to_numeric(clean[column], errors="raise")
    clean = clean.sort_values("timestamp").reset_index(drop=True)
    if clean["timestamp"].duplicated().any():
        raise ValueError("Duplicate candle timestamps detected")
    if ((clean["high"] < clean[["open", "close"]].max(axis=1)) | (clean["low"] > clean[["open", "close"]].min(axis=1))).any():
        raise ValueError("Malformed OHLC candle detected")
    if len(clean) > 1:
        expected = pd.Timedelta(milliseconds=timeframe_milliseconds(timeframe))
        gaps = clean["timestamp"].diff().dropna()
        if not (gaps % expected == pd.Timedelta(0)).all():
            raise ValueError("Candle timestamps are not aligned to the requested timeframe")
        if not allow_gaps and not (gaps == expected).all():
            raise ValueError("Missing candles or inconsistent timeframe detected")
    return clean


class HistoricalDataService:
    def __init__(self, client: object, cache_dir: str | Path = "cache") -> None:
        self.client = client
        self.cache_dir = Path(cache_dir)

    def _cache_path(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> Path:
        return self.cache_dir / f"{symbol}_{timeframe}_{start_ms}_{end_ms}.csv"

    def load(self, symbol: str, timeframe: str, start: datetime, end: datetime, progress: Callable[[int], None] | None = None, cancel: Event | None = None) -> pd.DataFrame:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Historical date range must be timezone-aware")
        if start >= end:
            raise ValueError("Historical start must be before end")
        start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        path = self._cache_path(symbol, timeframe, start_ms, end_ms)
        if path.exists():
            return validate_candles(pd.read_csv(path), timeframe, allow_gaps=True)
        rows: list[dict] = []
        cursor_end = end_ms
        step = timeframe_milliseconds(timeframe)
        while cursor_end >= start_ms:
            if cancel and cancel.is_set():
                break
            batch = self.client.get_klines(symbol, timeframe, start_ms, cursor_end, 200)
            if not batch:
                break
            rows.extend(batch)
            oldest = min(int(item["time"]) for item in batch)
            next_end = oldest - 1
            if next_end >= cursor_end:
                raise ValueError("Historical API cursor did not advance")
            cursor_end = next_end
            if progress:
                progress(min(100, int((end_ms - cursor_end) / max(1, end_ms - start_ms) * 100)))
            if oldest <= start_ms or len(batch) < 200:
                break
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        unique = {int(item["time"]): item for item in rows}
        normalized = []
        for item in unique.values():
            candle_time = int(item["time"])
            if not (start_ms <= candle_time and candle_time + step <= min(end_ms, now_ms)):
                continue
            open_, high, low, close = map(float, (item["open"], item["high"], item["low"], item["close"]))
            # Bitunix occasionally reports high/low a tick inside its own open/close;
            # clamp only the envelope at the exchange-adapter boundary.
            normalized.append({
                "timestamp": pd.to_datetime(candle_time, unit="ms", utc=True),
                "open": open_, "high": max(high, open_, close), "low": min(low, open_, close), "close": close,
                "volume": item.get("baseVol", item.get("volume", 0)),
            })
        frame = validate_candles(pd.DataFrame(normalized), timeframe, allow_gaps=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return frame
