from datetime import datetime, timedelta, timezone

import pandas as pd

from config.settings import AppSettings
from strategies.trend_pullback import TrendPullbackStrategy, align_completed_higher_timeframe
from tests.conftest import candles


def test_multi_timeframe_alignment_uses_only_closed_higher_candle():
    start=datetime(2025,1,1,10,0,tzinfo=timezone.utc)
    entry=candles([100]*8,start,15)
    higher=candles([10,20],start,60); higher["marker"]=[1,2]
    aligned=align_completed_higher_timeframe(entry,higher,"1h","15m")
    # Entry candle 10:45 closes at 11:00, exactly when the 10:00 HTF candle becomes known.
    assert pd.isna(aligned.iloc[2]["htf_marker"])
    assert aligned.iloc[3]["htf_marker"]==1
    assert aligned.iloc[6]["htf_marker"]==1
    assert aligned.iloc[7]["htf_marker"]==2


def test_no_lookahead_future_higher_value_cannot_change_earlier_rows():
    start=datetime(2025,1,1,tzinfo=timezone.utc); entry=candles([100]*12,start,15); higher=candles([10,20,999],start,60); higher["marker"]=[1,2,999]
    aligned=align_completed_higher_timeframe(entry,higher,"1h","15m")
    before_three_hours=aligned[aligned["entry_close_time"] < start+timedelta(hours=3)]
    assert 999 not in before_three_hours["htf_marker"].dropna().tolist()


def test_trend_classification_and_long_short_signal():
    settings=AppSettings(ema_fast=2,ema_slow=3,rsi_period=2,atr_period=2,rsi_long_min=0,rsi_long_max=100,rsi_short_min=0,rsi_short_max=100)
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    higher=candles([100,102,104,106,108,110],start,60); entry=candles([100+i*.2 for i in range(24)],start,15)
    result=TrendPullbackStrategy(settings).prepare(entry,higher)
    bullish=result[result["trend"]=="BULLISH"]; assert not bullish.empty; assert "LONG" in bullish["signal"].values
    higher2=candles([110,108,106,104,102,100],start,60); entry2=candles([110-i*.2 for i in range(24)],start,15)
    result2=TrendPullbackStrategy(settings).prepare(entry2,higher2); bearish=result2[result2["trend"]=="BEARISH"]; assert not bearish.empty; assert "SHORT" in bearish["signal"].values

