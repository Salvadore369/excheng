from decimal import Decimal

import pandas as pd

from backtesting.backtester import Backtester
from config.settings import AppSettings
from strategies.base_strategy import BaseStrategy
from tests.conftest import candles


class PreparedStrategy(BaseStrategy):
    def __init__(self,direction,conflict=False): self.direction,self.conflict=direction,conflict
    def prepare(self,entry,higher):
        f=entry.copy(); f["entry_close_time"]=pd.to_datetime(f["timestamp"],utc=True)+pd.Timedelta(minutes=15); f["atr"]=2.0; f["signal"]="NONE"; f.loc[0,"signal"]=self.direction
        if self.conflict: f.loc[1,"high"],f.loc[1,"low"]=110,90
        elif self.direction=="LONG": f.loc[1,"high"],f.loc[1,"low"]=110,99
        else: f.loc[1,"high"],f.loc[1,"low"]=101,90
        return f


def run(direction,instrument,conflict=False):
    settings=AppSettings(ema_fast=2,ema_slow=3,atr_period=2,rsi_period=2,trading_fee=.001,slippage=.001,atr_stop_multiplier=1,risk_reward=2)
    frame=candles([100,100,100]); return Backtester(settings,PreparedStrategy(direction,conflict),instrument).run(frame,frame,Decimal(10000))


def test_long_backtest_execution_fees_and_slippage(instrument):
    result=run("LONG",instrument); assert len(result.trades)==1; trade=result.trades[0]; assert trade.direction.value=="LONG"; assert trade.entry_price>100; assert trade.fees>0; assert trade.exit_reason=="TAKE_PROFIT"
    assert trade.entry_time == candles([100,100,100]).iloc[1]["timestamp"]


def test_short_backtest_execution(instrument):
    result=run("SHORT",instrument); assert len(result.trades)==1; trade=result.trades[0]; assert trade.direction.value=="SHORT"; assert trade.entry_price<100; assert trade.pnl>0


def test_same_candle_sl_tp_conflict_is_conservative(instrument):
    result=run("LONG",instrument,True); assert result.trades[0].exit_reason=="STOP_LOSS"; assert result.trades[0].pnl<0


class LockedAtrStrategy(BaseStrategy):
    def prepare(self,entry,higher):
        frame=entry.copy(); frame["entry_close_time"]=pd.to_datetime(frame["timestamp"],utc=True)+pd.Timedelta(minutes=15)
        frame["atr"]=[2.0,20.0,20.0]; frame["signal"]=["LONG","NONE","NONE"]
        frame.loc[1,"high"]=110
        return frame


def test_signal_candle_atr_is_locked_for_next_open_execution(instrument):
    settings=AppSettings(ema_fast=2,ema_slow=3,atr_period=2,rsi_period=2,trading_fee=0,slippage=0,atr_stop_multiplier=1,risk_reward=2)
    frame=candles([100,100,100])
    result=Backtester(settings,LockedAtrStrategy(),instrument).run(frame,frame,Decimal(10000))
    assert result.trades[0].stop_loss==Decimal("98.0")
    assert result.trades[0].take_profit==Decimal("104.0")


class GapStopStrategy(BaseStrategy):
    def prepare(self,entry,higher):
        frame=entry.copy(); frame["entry_close_time"]=pd.to_datetime(frame["timestamp"],utc=True)+pd.Timedelta(minutes=15)
        frame["atr"]=2.0; frame["signal"]=["LONG","NONE","NONE"]
        frame.loc[1,["high","low"]]=[101,99]
        frame.loc[2,["open","high","low","close"]]=[90,91,89,90]
        return frame


def test_stop_gap_uses_adverse_open_not_unavailable_stop_price(instrument):
    settings=AppSettings(ema_fast=2,ema_slow=3,atr_period=2,rsi_period=2,trading_fee=0,slippage=.001,atr_stop_multiplier=1,risk_reward=2)
    frame=candles([100,100,100])
    result=Backtester(settings,GapStopStrategy(),instrument).run(frame,frame,Decimal(10000))
    assert result.trades[0].exit_reason=="STOP_LOSS"
    assert result.trades[0].exit_price==Decimal("89.910")
