from __future__ import annotations

from threading import RLock

from models.domain import AppState


class InvalidStateTransition(RuntimeError): pass


class StateMachine:
    def __init__(self) -> None:
        self._state, self._lock = AppState.STOPPED, RLock()

    @property
    def state(self) -> AppState: return self._state

    def start(self, target: AppState) -> None:
        with self._lock:
            if self._state != AppState.STOPPED:
                raise InvalidStateTransition(f"Cannot start {target} while {self._state}")
            if target not in {AppState.CONNECTING, AppState.RUNNING_BACKTEST, AppState.RUNNING_PAPER, AppState.RUNNING_LIVE}:
                raise InvalidStateTransition(f"Invalid running state: {target}")
            self._state = target

    def stop(self) -> None:
        with self._lock: self._state = AppState.STOPPED

    def error(self) -> None:
        with self._lock: self._state = AppState.ERROR

