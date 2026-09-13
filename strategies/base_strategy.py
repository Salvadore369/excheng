from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    name = "Unnamed Strategy"
    warmup_bars = 200

    @abstractmethod
    def prepare(self, entry: pd.DataFrame, higher: pd.DataFrame) -> pd.DataFrame: ...
