"""Console logging with a consistent prefix and an elapsed-time helper."""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager

_CONFIGURED = False


def setup_logging(level: str | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    resolved = (level or os.environ.get("SIDEKICK_LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(name)-28s %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)
    # These are noisy at INFO and say nothing useful about our pipeline.
    for noisy in ("matplotlib", "httpx", "urllib3", "git"):
        logging.getLogger(noisy).setLevel("WARNING")
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


@contextmanager
def timed(logger: logging.Logger, label: str):
    start = time.perf_counter()
    logger.info("%s ...", label)
    try:
        yield
    finally:
        logger.info("%s finished in %.2fs", label, time.perf_counter() - start)
