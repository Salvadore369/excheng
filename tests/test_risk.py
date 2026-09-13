from decimal import Decimal

import pytest

from models.domain import Direction
from risk.risk_manager import RiskError, RiskManager


def test_position_sizing_and_limits(instrument):
    qty=RiskManager.position_size(Decimal("10000"),Decimal("1"),Decimal("100"),Decimal("95"),instrument)
    assert qty==Decimal("20.000")
    with pytest.raises(RiskError): RiskManager.position_size(Decimal("100"),Decimal("0"),Decimal("100"),Decimal("99"),instrument)
    with pytest.raises(RiskError): RiskManager.position_size(Decimal("100"),Decimal("1.01"),Decimal("100"),Decimal("99"),instrument)
    with pytest.raises(RiskError,match="at most"):
        RiskManager.validate_order(Decimal("1.0001"),Decimal("100"),instrument)
    capped=RiskManager.position_size(Decimal("100"),Decimal("1"),Decimal("100"),Decimal("99.9"),instrument,Decimal("2"),Decimal("0"))
    assert capped==Decimal("2.000")


def test_stop_loss_take_profit_long_short():
    long_sl=RiskManager.stop_loss(Decimal("100"),Decimal("2"),Decimal("1.5"),Direction.LONG); assert long_sl==Decimal("97.0")
    assert RiskManager.take_profit(Decimal("100"),long_sl,Decimal("2"),Direction.LONG)==Decimal("106.0")
    short_sl=RiskManager.stop_loss(Decimal("100"),Decimal("2"),Decimal("1.5"),Direction.SHORT); assert short_sl==Decimal("103.0")
    assert RiskManager.take_profit(Decimal("100"),short_sl,Decimal("2"),Direction.SHORT)==Decimal("94.0")
