"""Structured logging configuration with request correlation support."""

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

# Context variable to hold the current request ID across async tasks
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    """Retrieve the current request ID from context or generate a fallback."""
    req_id = request_id_ctx.get()
    return req_id if req_id else "system"


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter for production log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "system"),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


class DevelopmentFormatter(logging.Formatter):
    """Human-readable formatter with timestamp and request correlation ID for local dev."""

    COLOR_RESET = "\033[0m"
    COLOR_MAP = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLOR_MAP.get(record.levelno, self.COLOR_RESET)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        req_id = getattr(record, "request_id", "system")
        prefix = f"{timestamp} [{req_id}] {color}{record.levelname:<8}{self.COLOR_RESET} [{record.name}]"
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        return f"{prefix} {message}"


def setup_logging(log_level: str = "INFO", json_format: bool = False) -> logging.Logger:
    """Initialize root and application loggers with appropriate formatters.

    Args:
        log_level: Desired minimum log level (DEBUG, INFO, etc.).
        json_format: Whether to output logs in structured JSON format.

    Returns:
        The configured application root logger.
    """
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.addFilter(RequestIdFilter())

    if json_format:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(DevelopmentFormatter())

    root_logger.addHandler(console_handler)

    # Silence overly verbose third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger("childtrack")
    logger.info("Logging initialized with level=%s, json_format=%s", log_level, json_format)
    return logger
