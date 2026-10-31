"""Structured JSON logging with a per-request request-id.

Tokens, keys and request bodies are never logged. Only method, path,
status and timing are recorded, plus the request-id that is also
returned to the caller in the X-Request-Id header.
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "savebite_request_id", default=""
)


def new_request_id() -> str:
    return str(uuid.uuid4())


def get_request_id() -> str:
    return request_id_var.get() or ""


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorn's own loggers should use the same handler, not duplicate.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
