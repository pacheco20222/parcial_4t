import json
import logging
import sys

from telemetry_service.logging import JSONFormatter


def test_library_log_formats_arguments_and_exception():
    try:
        raise ValueError("invalid reading")
    except ValueError:
        record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 12, "Failed %s", ("reading",), sys.exc_info())
    data = json.loads(JSONFormatter().format(record))
    assert data["event"] == "Failed reading"
    assert data["msg"] == "Failed reading"
    assert data["exc"]["type"] == "ValueError"
    assert data["exc"]["message"] == "invalid reading"
    assert "raise ValueError" in data["exc"]["traceback"]


def test_structured_event_context_preserved():
    record = logging.LogRecord("telemetry", logging.INFO, __file__, 1, "telemetry.ingested", (), None)
    record.context = {"point_id": "P01"}
    data = json.loads(JSONFormatter().format(record))
    assert data["event"] == "telemetry.ingested"
    assert data["point_id"] == "P01"
    assert "exc" not in data
