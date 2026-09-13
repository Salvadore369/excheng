from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config.settings import AppSettings
from data.historical_data import timeframe_milliseconds
from indicators.indicators import atr, ema, rsi
from models.domain import SignalType

from .base_strategy import BaseStrategy


@dataclass(frozen=True)
class Spike:
    direction: str
    start: int
    end: int


class SP2LStrategy(BaseStrategy):
    """Causal Spike-2Leg setup detector.

    A signal is emitted only when the first pullback candle has closed. Entry
    levels are therefore resting limits for subsequent candles; the strategy
    never assumes an intrabar fill that was unknowable at signal time.
    """

    name = "SP2L (Poursamadi Spike-2Leg)"
    warmup_bars = 80
    uses_limit_plans = True
    plan_name = "SP2L"
    client_slug = "sp2l"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    @staticmethod
    def _overlap_ratio(left: pd.Series, right: pd.Series) -> float:
        overlap = max(0.0, min(float(left.high), float(right.high)) - max(float(left.low), float(right.low)))
        denominator = min(float(left.high - left.low), float(right.high - right.low))
        return overlap / denominator if denominator > 0 else 1.0

    def _dirty_market(self, frame: pd.DataFrame, spike_start: int) -> bool:
        start = max(0, spike_start - self.settings.sp2l_dirty_lookback)
        window = frame.iloc[start:spike_start]
        if len(window) < 3:
            return False
        ranges = (window.high - window.low).replace(0, np.nan)
        bodies = (window.close - window.open).abs()
        body_ratio = float((bodies / ranges).fillna(0).mean())
        wick_ratio = float(((ranges - bodies) / ranges).fillna(1).mean())
        overlaps = [self._overlap_ratio(window.iloc[i - 1], window.iloc[i]) for i in range(1, len(window))]
        overlap_ratio = float(np.mean(overlaps)) if overlaps else 0.0
        # "Dirty" requires at least two independent symptoms, avoiding a pause
        # merely because one healthy candle happened to have a long wick.
        symptoms = sum((body_ratio < 0.25, wick_ratio > 0.65, overlap_ratio > self.settings.sp2l_dirty_overlap_ratio))
        return symptoms >= 2

    def _active_session(self, timestamp: object) -> bool:
        if not self.settings.sp2l_session_filter:
            return True
        hour = pd.Timestamp(timestamp).tz_convert("UTC").hour
        return 7 <= hour < 21  # London and New York liquid windows, UTC.

    def _run_length(self, frame: pd.DataFrame, trigger: int, direction: str) -> int:
        length = 1
        cursor = trigger - 1
        while cursor > 0:
            continues = (
                frame.iloc[cursor].low >= frame.iloc[cursor - 1].low
                if direction == "BULLISH"
                else frame.iloc[cursor].high <= frame.iloc[cursor - 1].high
            )
            if not continues:
                break
            length += 1
            cursor -= 1
        return length

    def _valid_breakout(self, frame: pd.DataFrame, spike: Spike) -> bool:
        s = spike.start
        lookback_start = s - self.settings.sp2l_breakout_lookback
        if lookback_start < 0 or s + 1 > spike.end:
            return False
        prior = frame.iloc[lookback_start:s]
        candidates = frame.iloc[s : min(s + 2, spike.end + 1)]
        candle_range = (candidates.high - candidates.low).replace(0, np.nan)
        strong = ((candidates.close - candidates.open).abs() / candle_range).fillna(0) >= self.settings.sp2l_strong_body_ratio
        if spike.direction == "BULLISH":
            directional = candidates.close > candidates.open
            broke = candidates.close > float(prior.high.max())
        else:
            directional = candidates.close < candidates.open
            broke = candidates.close < float(prior.low.min())
        return bool((strong & directional & broke).any())

    def _valid_gap(self, frame: pd.DataFrame, spike: Spike) -> bool:
        if not self.settings.sp2l_gap_filter:
            return True
        before = frame.iloc[spike.start - 1]
        follow_through = frame.iloc[spike.start + 1]
        if spike.direction == "BULLISH":
            return bool(follow_through.low > before.high)
        return bool(follow_through.high < before.low)

    def _find_spike(self, frame: pd.DataFrame, trigger: int, direction: str) -> Spike | None:
        run_length = self._run_length(frame, trigger, direction)
        if not self.settings.sp2l_min_spike_bars <= run_length <= self.settings.sp2l_max_spike_bars:
            return None
        spike = Spike(direction, trigger - run_length, trigger - 1)
        bars = frame.iloc[spike.start : spike.end + 1]
        ranges = (bars.high - bars.low).replace(0, np.nan)
        doji_ratio = float((((bars.close - bars.open).abs() / ranges).fillna(0) <= self.settings.sp2l_max_doji_body_ratio).mean())
        if doji_ratio > self.settings.sp2l_max_doji_ratio:
            return None
        height = float(bars.high.max() - bars.low.min())
        start_atr = float(frame.iloc[spike.start].atr)
        if not np.isfinite(start_atr) or height < start_atr * self.settings.sp2l_movement_atr:
            return None
        if not self._valid_breakout(frame, spike) or not self._valid_gap(frame, spike):
            return None
        if self._dirty_market(frame, spike.start):
            return None
        if self.settings.sp2l_ema_origin_filter:
            origin = float(frame.iloc[spike.start].open)
            equilibrium = float(frame.iloc[spike.start].ema60)
            if not np.isfinite(equilibrium) or abs(origin - equilibrium) > start_atr * self.settings.sp2l_ema_origin_atr:
                return None
        return spike

    def _levels(self, frame: pd.DataFrame, spike: Spike, trigger: int) -> dict[str, object] | None:
        bars = frame.iloc[spike.start : spike.end + 1]
        spike_low, spike_high = float(bars.low.min()), float(bars.high.max())
        signal_atr = float(frame.iloc[trigger].atr)
        buffer = signal_atr * self.settings.sp2l_stop_buffer_atr
        bullish = spike.direction == "BULLISH"
        if self.settings.sp2l_stop_mode == "SPIKE_ORIGIN":
            stop = spike_low - buffer if bullish else spike_high + buffer
        elif self.settings.sp2l_stop_mode == "FOLLOW_THROUGH":
            follow = frame.iloc[spike.start + 1]
            stop = float(follow.low) - buffer if bullish else float(follow.high) + buffer
        else:
            stop = (spike_low + spike_high) / 2

        prior = frame.iloc[trigger - 1]
        entry1 = float(prior.low if bullish else prior.high)
        if self.settings.sp2l_entry2_mode == "SPIKE_50":
            entry2 = (spike_low + spike_high) / 2
        elif self.settings.sp2l_entry2_mode == "EMA60":
            entry2 = float(frame.iloc[trigger].ema60)
        else:
            entry2 = (entry1 + stop) / 2
        entry3 = stop + (entry1 - stop) * 0.15

        entries = [entry1, entry2]
        weights = list(self.settings.sp2l_entry_weights[:2])
        if self.settings.sp2l_enable_third_entry:
            entries.append(entry3)
            weights.append(self.settings.sp2l_entry_weights[2])
        valid = [(level, weight) for level, weight in zip(entries, weights, strict=True) if (level > stop if bullish else level < stop)]
        if not valid:
            return None
        entries, weights = map(list, zip(*valid, strict=True))
        # Targets must remain valid when only the first (shallowest) limit fills.
        # Using the hypothetical all-layers average silently collapses R:R when
        # deeper orders never execute. Entry 1 is the conservative risk basis;
        # any deeper fills improve the realized reward/risk.
        target_basis = entry1
        risk = abs(target_basis - stop)
        tp1 = target_basis + risk * self.settings.sp2l_tp1_rr * (1 if bullish else -1)
        pullback_extreme = float(frame.iloc[trigger].low if bullish else frame.iloc[trigger].high)
        measured = pullback_extreme + (spike_high - spike_low) * (1 if bullish else -1)
        minimum_tp2 = target_basis + risk * self.settings.risk_reward * (1 if bullish else -1)
        tp2 = max(measured, minimum_tp2) if bullish else min(measured, minimum_tp2)
        return {
            "spike_start_index": spike.start,
            "spike_end_index": spike.end,
            "spike_low": spike_low,
            "spike_high": spike_high,
            "entry_levels": tuple(entries),
            "entry_weights": tuple(float(weight) for weight in weights),
            "strategy_stop": stop,
            "strategy_tp1": tp1,
            "strategy_tp2": tp2,
            "tp1_fraction": self.settings.sp2l_tp1_fraction,
            "time_stop_bars": self.settings.sp2l_time_stop_bars,
            "limit_expiry_bars": self.settings.sp2l_limit_expiry_bars,
        }

    def prepare(self, entry: pd.DataFrame, higher: pd.DataFrame) -> pd.DataFrame:
        frame = entry.copy().sort_values("timestamp").reset_index(drop=True)
        frame["ema60"] = ema(frame.close, 60)
        frame["atr"] = atr(frame, self.settings.atr_period)
        frame["rsi"] = rsi(frame.close, self.settings.rsi_period)
        frame["entry_close_time"] = pd.to_datetime(frame.timestamp, utc=True) + pd.Timedelta(
            milliseconds=timeframe_milliseconds(self.settings.entry_timeframe)
        )
        frame["trend"] = "NEUTRAL"
        frame.loc[frame.close > frame.ema60, "trend"] = "BULLISH"
        frame.loc[frame.close < frame.ema60, "trend"] = "BEARISH"
        frame["signal"] = SignalType.NONE.value
        frame["signal_reason"] = "No first-pullback SP2L setup"
        object_columns = ["entry_levels", "entry_weights"]
        numeric_columns = [
            "spike_start_index", "spike_end_index", "spike_low", "spike_high",
            "strategy_stop", "strategy_tp1", "strategy_tp2", "tp1_fraction",
            "time_stop_bars", "limit_expiry_bars",
        ]
        for column in object_columns:
            frame[column] = pd.Series([None] * len(frame), dtype=object)
        for column in numeric_columns:
            frame[column] = np.nan

        opens = frame.open.to_numpy(dtype=float)
        highs = frame.high.to_numpy(dtype=float)
        lows = frame.low.to_numpy(dtype=float)
        closes = frame.close.to_numpy(dtype=float)
        atrs = frame.atr.to_numpy(dtype=float)
        ema60s = frame.ema60.to_numpy(dtype=float)
        ranges = highs - lows
        body_ratios = np.divide(np.abs(closes - opens), ranges, out=np.zeros_like(ranges), where=ranges > 0)
        wick_ratios = np.divide(ranges - np.abs(closes - opens), ranges, out=np.ones_like(ranges), where=ranges > 0)
        overlaps = np.zeros(len(frame), dtype=float)
        if len(frame) > 1:
            overlap_size = np.maximum(0, np.minimum(highs[1:], highs[:-1]) - np.maximum(lows[1:], lows[:-1]))
            overlap_range = np.minimum(ranges[1:], ranges[:-1])
            overlaps[1:] = np.divide(overlap_size, overlap_range, out=np.ones_like(overlap_size), where=overlap_range > 0)
        bull_runs = np.ones(len(frame), dtype=np.int16)
        bear_runs = np.ones(len(frame), dtype=np.int16)
        for index in range(1, len(frame)):
            if lows[index] >= lows[index - 1]:
                bull_runs[index] = bull_runs[index - 1] + 1
            if highs[index] <= highs[index - 1]:
                bear_runs[index] = bear_runs[index - 1] + 1
        hours = pd.to_datetime(frame.timestamp, utc=True).dt.hour.to_numpy()
        htf_trends = np.zeros(len(frame), dtype=np.int8)
        if self.settings.sp2l_trend_filter == "HTF_EMA60" and not higher.empty:
            higher_frame = higher.copy().sort_values("timestamp").reset_index(drop=True)
            higher_frame["ema60"] = ema(higher_frame.close, 60)
            higher_closes = pd.to_datetime(higher_frame.timestamp, utc=True) + pd.Timedelta(
                milliseconds=timeframe_milliseconds(self.settings.higher_timeframe)
            )
            entry_closes = pd.to_datetime(frame.entry_close_time, utc=True).astype("int64").to_numpy()
            higher_close_values = higher_closes.astype("int64").to_numpy()
            aligned = np.searchsorted(higher_close_values, entry_closes, side="right") - 1
            valid_alignment = aligned >= 0
            higher_prices = higher_frame.close.to_numpy(dtype=float)
            higher_ema = higher_frame.ema60.to_numpy(dtype=float)
            aligned_prices = np.full(len(frame), np.nan)
            aligned_ema = np.full(len(frame), np.nan)
            aligned_prices[valid_alignment] = higher_prices[aligned[valid_alignment]]
            aligned_ema[valid_alignment] = higher_ema[aligned[valid_alignment]]
            htf_trends[aligned_prices > aligned_ema] = 1
            htf_trends[aligned_prices < aligned_ema] = -1

        start = max(self.warmup_bars, self.settings.sp2l_breakout_lookback + self.settings.sp2l_max_spike_bars + 1)
        for trigger in range(start, len(frame)):
            if (self.settings.sp2l_session_filter and not 7 <= hours[trigger] < 21) or not np.isfinite(atrs[trigger]):
                continue
            bullish_pullback = lows[trigger] < lows[trigger - 1]
            bearish_pullback = highs[trigger] > highs[trigger - 1]
            candidates = []
            if bullish_pullback:
                candidates.append("BULLISH")
            if bearish_pullback:
                candidates.append("BEARISH")
            for direction in candidates:
                if self.settings.sp2l_direction_filter == "LONG" and direction != "BULLISH":
                    continue
                if self.settings.sp2l_direction_filter == "SHORT" and direction != "BEARISH":
                    continue
                run_length = int(bull_runs[trigger - 1] if direction == "BULLISH" else bear_runs[trigger - 1])
                if not self.settings.sp2l_min_spike_bars <= run_length <= self.settings.sp2l_max_spike_bars:
                    continue
                spike_start, spike_end = trigger - run_length, trigger - 1
                spike_slice = slice(spike_start, spike_end + 1)
                doji_ratio = float(np.mean(body_ratios[spike_slice] <= self.settings.sp2l_max_doji_body_ratio))
                spike_low, spike_high = float(np.min(lows[spike_slice])), float(np.max(highs[spike_slice]))
                if doji_ratio > self.settings.sp2l_max_doji_ratio or spike_high - spike_low < atrs[spike_start] * self.settings.sp2l_movement_atr:
                    continue

                prior_start = spike_start - self.settings.sp2l_breakout_lookback
                if prior_start < 0 or spike_start + 1 > spike_end:
                    continue
                candidate_slice = slice(spike_start, min(spike_start + 2, spike_end + 1))
                strong = body_ratios[candidate_slice] >= self.settings.sp2l_strong_body_ratio
                if direction == "BULLISH":
                    broke = closes[candidate_slice] > np.max(highs[prior_start:spike_start])
                    directional = closes[candidate_slice] > opens[candidate_slice]
                    gap_valid = lows[spike_start + 1] > highs[spike_start - 1]
                else:
                    broke = closes[candidate_slice] < np.min(lows[prior_start:spike_start])
                    directional = closes[candidate_slice] < opens[candidate_slice]
                    gap_valid = highs[spike_start + 1] < lows[spike_start - 1]
                if not bool(np.any(strong & broke & directional)) or (self.settings.sp2l_gap_filter and not gap_valid):
                    continue

                dirty_start = max(0, spike_start - self.settings.sp2l_dirty_lookback)
                dirty_body = float(np.mean(body_ratios[dirty_start:spike_start]))
                dirty_wick = float(np.mean(wick_ratios[dirty_start:spike_start]))
                dirty_overlap = float(np.mean(overlaps[dirty_start + 1:spike_start])) if spike_start - dirty_start > 1 else 0.0
                if sum((dirty_body < 0.25, dirty_wick > 0.65, dirty_overlap > self.settings.sp2l_dirty_overlap_ratio)) >= 2:
                    continue
                if self.settings.sp2l_ema_origin_filter and (
                    not np.isfinite(ema60s[spike_start])
                    or abs(opens[spike_start] - ema60s[spike_start]) > atrs[spike_start] * self.settings.sp2l_ema_origin_atr
                ):
                    continue

                trend_sign = 1 if direction == "BULLISH" else -1
                if self.settings.sp2l_trend_filter == "EMA60":
                    local_sign = 1 if closes[trigger] > ema60s[trigger] else -1 if closes[trigger] < ema60s[trigger] else 0
                    if local_sign != trend_sign:
                        continue
                elif self.settings.sp2l_trend_filter == "HTF_EMA60" and htf_trends[trigger] != trend_sign:
                    continue

                bullish = direction == "BULLISH"
                buffer = atrs[trigger] * self.settings.sp2l_stop_buffer_atr
                if self.settings.sp2l_stop_mode == "SPIKE_ORIGIN":
                    stop = spike_low - buffer if bullish else spike_high + buffer
                elif self.settings.sp2l_stop_mode == "FOLLOW_THROUGH":
                    stop = lows[spike_start + 1] - buffer if bullish else highs[spike_start + 1] + buffer
                else:
                    stop = (spike_low + spike_high) / 2
                entry1 = lows[trigger - 1] if bullish else highs[trigger - 1]
                if self.settings.sp2l_entry2_mode == "SPIKE_50":
                    entry2 = (spike_low + spike_high) / 2
                elif self.settings.sp2l_entry2_mode == "EMA60":
                    entry2 = ema60s[trigger]
                else:
                    entry2 = (entry1 + stop) / 2
                entry3 = stop + (entry1 - stop) * 0.15
                entries = [float(entry1), float(entry2)]
                weights = list(self.settings.sp2l_entry_weights[:2])
                if self.settings.sp2l_enable_third_entry:
                    entries.append(float(entry3)); weights.append(self.settings.sp2l_entry_weights[2])
                valid = [(level, weight) for level, weight in zip(entries, weights, strict=True) if (level > stop if bullish else level < stop)]
                if not valid:
                    continue
                entries, weights = map(list, zip(*valid, strict=True))
                risk = abs(entry1 - stop)
                direction_sign = 1 if bullish else -1
                tp1 = entry1 + risk * self.settings.sp2l_tp1_rr * direction_sign
                pullback_extreme = lows[trigger] if bullish else highs[trigger]
                measured = pullback_extreme + (spike_high - spike_low) * direction_sign
                minimum_tp2 = entry1 + risk * self.settings.risk_reward * direction_sign
                tp2 = max(measured, minimum_tp2) if bullish else min(measured, minimum_tp2)
                levels = {
                    "spike_start_index": spike_start, "spike_end_index": spike_end,
                    "spike_low": spike_low, "spike_high": spike_high,
                    "entry_levels": tuple(entries), "entry_weights": tuple(float(weight) for weight in weights),
                    "strategy_stop": stop, "strategy_tp1": tp1, "strategy_tp2": tp2,
                    "tp1_fraction": self.settings.sp2l_tp1_fraction,
                    "time_stop_bars": self.settings.sp2l_time_stop_bars,
                    "limit_expiry_bars": self.settings.sp2l_limit_expiry_bars,
                }
                signal = SignalType.LONG.value if bullish else SignalType.SHORT.value
                frame.at[trigger, "signal"] = signal
                frame.at[trigger, "trend"] = direction
                frame.at[trigger, "signal_reason"] = f"Valid {direction.lower()} spike and first pullback; resting limit plan armed"
                for column, value in levels.items():
                    frame.at[trigger, column] = value
                break
        return frame
