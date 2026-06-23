"""
JSON structured log formatter for MedQueue.
Each log line is a single JSON object with consistent fields,
making logs easy to parse by Grafana Loki, ELK, or any log aggregator.
"""

import json
import logging
import traceback
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Example output:
    {"ts": "2024-01-15T10:30:00.123Z", "level": "INFO", "env": "production",
     "logger": "appointments.views", "msg": "Payment ok",
     "user_id": 42, "amount": 2990, "gateway": "paypal"}
    """

    def format(self, record: logging.LogRecord) -> str:
        # Base fields always present
        log_obj: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Extra fields passed via logger.info("...", extra={"user_id": 1})
        skip_fields = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in skip_fields:
                try:
                    json.dumps(value)  # only include JSON-serialisable values
                    log_obj[key] = value
                except (TypeError, ValueError):
                    log_obj[key] = str(value)

        # Exception information
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)
