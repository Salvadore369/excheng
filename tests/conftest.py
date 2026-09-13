from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest

from models.domain import Instrument


@pytest.fixture
def instrument():
    return Instrument("BTCUSDT", 3, 1, Decimal("0.001"), Decimal("100"), 1, 125)


def candles(prices, start=None, minutes=15):
    start = start or datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows=[]
    for i,p in enumerate(prices):
        p=float(p); rows.append({"timestamp":start+timedelta(minutes=minutes*i),"open":p,"high":p+1,"low":p-1,"close":p,"volume":10})
    return pd.DataFrame(rows)

