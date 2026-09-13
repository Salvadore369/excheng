from datetime import datetime, timezone
from decimal import Decimal

from models.domain import Direction, Trade
from services.export_service import TRADE_COLUMNS, export_trades_csv


def test_trade_export_csv(tmp_path):
    now=datetime.now(timezone.utc)
    trade=Trade(now,now,"BTCUSDT",Direction.LONG,Decimal("1"),Decimal("100"),Decimal("102"),Decimal("99"),Decimal("102"),Decimal("0.1"),Decimal("1.9"),"TAKE_PROFIT")
    path=export_trades_csv(tmp_path/"nested"/"trades.csv",[trade])
    lines=path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",")==TRADE_COLUMNS
    assert "BTCUSDT" in lines[1] and "TAKE_PROFIT" in lines[1]
