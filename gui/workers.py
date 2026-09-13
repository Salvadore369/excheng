from __future__ import annotations

import traceback
from datetime import datetime
from decimal import Decimal
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot


class BacktestWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)

    def __init__(self, service, start: datetime, end: datetime, balance: Decimal) -> None:
        super().__init__(); self.service, self.start, self.end, self.balance = service, start, end, balance
        self.cancel_event = Event()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run(self.start, self.end, self.balance, self.cancel_event, self.progress.emit)
            if self.cancel_event.is_set(): self.cancelled.emit()
            else: self.finished.emit(result)
        except InterruptedError:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())

    @Slot()
    def cancel(self) -> None: self.cancel_event.set()
