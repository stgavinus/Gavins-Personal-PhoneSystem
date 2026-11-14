"""
Structured JSON logging for the bridge server.

Every log record is emitted as a single JSON line so it can be ingested by
any log aggregator.  The session_id field ties all records for one call together.

Usage:
    from bridge.log import get_logger
    log = get_logger(__name__)
    log.info("stt_result", session_id=sid, transcript="hello", latency_ms=240)
"""
import json
import logging
import sys
import time


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        # Any keyword args passed via extra={} are merged at the top level
        extra = {k: v for k, v in record.__dict__.items()
                 if k not in logging.LogRecord.__dict__ and
                    not k.startswith("_") and
                    k not in ("args", "msg", "levelname", "name", "pathname",
                              "filename", "module", "exc_info", "exc_text",
                              "stack_info", "lineno", "funcName", "created",
                              "msecs", "relativeCreated", "thread", "threadName",
                              "processName", "process", "message", "taskName")}
        base.update(extra)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base)


def configure(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class BoundLogger:
    """A logger with pre-bound fields (e.g. session_id)."""

    def __init__(self, logger: logging.Logger, **fields):
        self._log    = logger
        self._fields = fields

    def bind(self, **fields) -> "BoundLogger":
        return BoundLogger(self._log, **{**self._fields, **fields})

    def _emit(self, level: int, msg: str, **kw) -> None:
        self._log.log(level, msg, extra={**self._fields, **kw})

    def debug(self, msg: str, **kw) -> None:  self._emit(logging.DEBUG,    msg, **kw)
    def info (self, msg: str, **kw) -> None:  self._emit(logging.INFO,     msg, **kw)
    def warning(self, msg: str, **kw) -> None: self._emit(logging.WARNING, msg, **kw)
    def error(self, msg: str, **kw) -> None:  self._emit(logging.ERROR,    msg, **kw)
    def exception(self, msg: str, **kw) -> None:
        self._log.exception(msg, extra={**self._fields, **kw})
