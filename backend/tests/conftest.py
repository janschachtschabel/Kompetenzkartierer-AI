"""Fixtures shared by the backend tests."""

import logging
from collections.abc import Iterator

import pytest

from app.core.logging import QUIET_LOGGERS

TOUCHED_LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "py.warnings", *QUIET_LOGGERS)


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Undo what configure_logging does to the process-wide loggers."""
    loggers = {name: logging.getLogger(name) for name in TOUCHED_LOGGERS}
    saved = {name: (logger.handlers[:], logger.level, logger.propagate) for name, logger in loggers.items()}
    yield
    logging.captureWarnings(False)
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate
