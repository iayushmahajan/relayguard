import json

import structlog
from pytest import CaptureFixture
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.logging import configure_logging


def test_structlog_json_logging_merges_contextvars(capsys: CaptureFixture[str]) -> None:
    configure_logging()
    clear_contextvars()
    bind_contextvars(correlation_id="0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db")

    structlog.get_logger("test").info("health_checked")

    clear_contextvars()
    log_entry = json.loads(capsys.readouterr().out)
    assert log_entry["event"] == "health_checked"
    assert log_entry["correlation_id"] == "0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db"
