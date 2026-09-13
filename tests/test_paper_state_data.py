from decimal import Decimal

import pandas as pd
import pytest

from data.historical_data import validate_candles
from engine.state import InvalidStateTransition, StateMachine
from execution.base_exchange import BaseExchange, ExchangeError
from execution.paper_exchange import PaperExchange
from models.domain import AppState, Direction, Order, OrderSide, Position
from tests.conftest import candles


class Market(BaseExchange):
    def __init__(self,instrument): self.instrument=instrument
    def get_instrument(self,s): return self.instrument
    def get_last_price(self,s): return Decimal("100")
    def place_order(self,o): raise AssertionError("Paper mode leaked an order to live exchange")
    def cancel_order(self,s,o): return True
    def get_positions(self,s=None): return []


def test_paper_order_execution_and_position_management(instrument):
    market=Market(instrument); paper=PaperExchange(market,fee_rate=Decimal("0.001"),slippage=Decimal("0")); order=paper.place_order(Order("BTCUSDT",OrderSide.BUY,Decimal("1"),stop_loss=Decimal("95"),take_profit=Decimal("105")))
    assert order.status=="FILLED" and len(paper.positions)==1 and paper.balance==Decimal("9999.900")
    events=paper.process_price("BTCUSDT",Decimal("106"),Decimal("99")); assert events==["TAKE_PROFIT"] and not paper.positions and paper.balance>Decimal("10000")


def test_paper_same_candle_conflict_uses_stop(instrument):
    paper=PaperExchange(Market(instrument),slippage=Decimal("0")); paper.place_order(Order("BTCUSDT",OrderSide.SELL,Decimal("1"),stop_loss=Decimal("105"),take_profit=Decimal("95")))
    assert paper.process_price("BTCUSDT",Decimal("106"),Decimal("94"))==["STOP_LOSS"]


def test_paper_limit_waits_for_touch_and_releases_cancelled_reservation(instrument):
    paper = PaperExchange(Market(instrument), fee_rate=Decimal("0.001"), slippage=Decimal("0"))
    available = paper.available_balance
    order = paper.place_order(Order("BTCUSDT", OrderSide.BUY, Decimal("1"),
        order_type="LIMIT", price=Decimal("98"), stop_loss=Decimal("95"), take_profit=Decimal("105")))
    assert order.status == "NEW" and not paper.positions and paper.available_balance < available
    assert paper.process_price("BTCUSDT", Decimal("101"), Decimal("99")) == []
    assert paper.process_price("BTCUSDT", Decimal("106"), Decimal("97")) == ["LIMIT_FILL"]
    assert order.status == "FILLED" and paper.positions[0].entry_price == Decimal("98")

    second = paper.place_order(Order("BTCUSDT", OrderSide.BUY, Decimal("1"),
        order_type="LIMIT", price=Decimal("90"), stop_loss=Decimal("85"), take_profit=Decimal("100")))
    reserved = paper.available_balance
    assert paper.cancel_order("BTCUSDT", second.id) is True
    assert paper.available_balance > reserved and second.status == "CANCELED"


def test_paper_rejects_bad_reduce_side_and_tracks_unrealized(instrument):
    paper=PaperExchange(Market(instrument),slippage=Decimal("0")); paper.place_order(Order("BTCUSDT",OrderSide.BUY,Decimal("1"),stop_loss=Decimal("90"),take_profit=Decimal("110")))
    assert paper.unrealized_pnl({"BTCUSDT":Decimal("105")}) > 0
    with pytest.raises(ExchangeError,match="side"):
        paper.place_order(Order("BTCUSDT",OrderSide.BUY,Decimal("1"),price=Decimal("105"),reduce_only=True))


def test_state_machine_prevents_conflicting_operations():
    state=StateMachine(); state.start(AppState.RUNNING_PAPER)
    with pytest.raises(InvalidStateTransition): state.start(AppState.RUNNING_BACKTEST)
    state.stop(); assert state.state==AppState.STOPPED


def test_historical_validation_duplicates_missing_and_malformed():
    frame=candles([100,101,102]); assert len(validate_candles(frame,"15m"))==3
    duplicate=pd.concat([frame,frame.iloc[[0]]]);
    with pytest.raises(ValueError,match="Duplicate"): validate_candles(duplicate,"15m")
    gap=frame.drop(index=1)
    with pytest.raises(ValueError,match="Missing"): validate_candles(gap,"15m")
    off_grid=frame.copy(); off_grid.loc[1,"timestamp"] += pd.Timedelta(minutes=1)
    with pytest.raises(ValueError,match="aligned"): validate_candles(off_grid,"15m",allow_gaps=True)
