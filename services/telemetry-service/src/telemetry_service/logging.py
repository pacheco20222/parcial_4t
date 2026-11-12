import json
import logging
import sys
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        fields = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "telemetry-service",
            "event": message,
            **getattr(record, "context", {}),
            "msg": message,
        }
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            fields["exc"] = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": self.formatException(record.exc_info),
            }
        return json.dumps(fields, allow_nan=False)


def configure(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(handlers=[handler], level=level, force=True)


def event(name: str, **context: object) -> None:
    logging.getLogger("telemetry").info(name, extra={"context": context})
