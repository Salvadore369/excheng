from __future__ import annotations

import numpy as np
import pandas as pd


def ema(values: pd.Series, period: int) -> pd.Series:
    if period < 1:
        raise ValueError("EMA period must be positive")
    return values.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(values: pd.Series, period: int = 14) -> pd.Series:
    delta = values.astype(float).diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative = avg_gain / avg_loss.replace(0, np.nan)
    output = 100 - (100 / (1 + relative))
    output = output.where(avg_loss != 0, 100.0)
    output = output.where(avg_gain != 0, 0.0)
    return output


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = frame["close"].astype(float).shift(1)
    ranges = pd.concat(
        [(frame["high"] - frame["low"]).abs(), (frame["high"] - previous).abs(), (frame["low"] - previous).abs()],
        axis=1,
    )
    return ranges.max(axis=1).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def enrich_indicators(frame: pd.DataFrame, fast: int, slow: int, rsi_period: int, atr_period: int) -> pd.DataFrame:
    result = frame.copy()
    result["ema_fast"] = ema(result["close"], fast)
    result["ema_slow"] = ema(result["close"], slow)
    result["rsi"] = rsi(result["close"], rsi_period)
    result["atr"] = atr(result, atr_period)
    return result

