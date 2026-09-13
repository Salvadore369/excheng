from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from config.settings import AppSettings, ConfigStore
from indicators.indicators import atr, ema, rsi


def test_configuration_validation():
    with pytest.raises(ValidationError): AppSettings(ema_fast=200, ema_slow=50)
    with pytest.raises(ValidationError): AppSettings(symbol="BTC-USD")
    with pytest.raises(ValidationError): AppSettings(risk_per_trade=11)
    with pytest.raises(ValidationError): AppSettings(risk_per_trade=1.01)
    with pytest.raises(ValidationError): AppSettings(risk_reward=1.99)
    with pytest.raises(ValidationError): AppSettings(strategy="imaginary_alpha")


def test_configuration_persistence_excludes_secrets(tmp_path):
    path=tmp_path/"settings.json"; store=ConfigStore(path); settings=AppSettings(symbol="ETHUSDT",leverage=3); store.save(settings)
    raw=path.read_text(); assert "ETHUSDT" in raw and "API_SECRET" not in raw; assert store.load()==settings
    assert not list(tmp_path.glob("*.tmp"))


def test_stale_sp2l_timeframe_pair_is_normalized_on_load(tmp_path):
    path = tmp_path / "settings.json"
    store = ConfigStore(path)
    store.save(AppSettings(strategy="sp2l", entry_timeframe="5m", higher_timeframe="30m"))
    loaded = store.load()
    assert loaded.entry_timeframe == "5m"
    assert loaded.higher_timeframe == "15m"


def test_indicator_calculations():
    values=pd.Series(range(1,31),dtype=float); assert ema(values,5).iloc[-1] == pytest.approx(28.0,rel=0.01); assert rsi(values,14).iloc[-1]==100
    frame=pd.DataFrame({"high":values+1,"low":values-1,"close":values}); assert atr(frame,14).iloc[-1]==pytest.approx(2.0)
