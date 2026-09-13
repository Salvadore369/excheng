from __future__ import annotations

import logging
from collections.abc import Callable


class GuiLogHandler(logging.Handler):
    def __init__(self, callback: Callable[[str, str], None]) -> None:
        super().__init__(); self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        self.callback(record.levelname, self.format(record))


def configure_logging(callback=None) -> logging.Logger:
    logger = logging.getLogger("codexbot")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(stream)
    if callback and not any(isinstance(h, GuiLogHandler) for h in logger.handlers):
        handler = GuiLogHandler(callback); handler.setFormatter(logging.Formatter("%(message)s")); logger.addHandler(handler)
    return logger

