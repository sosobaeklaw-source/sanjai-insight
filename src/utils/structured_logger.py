"""
Structured JSON Logging
High-quality logging with correlation IDs and context.
Integrates with Sentry for error tracking.
"""

import json
import logging
import os
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

# Context variables for correlation tracking
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class JSONFormatter(logging.Formatter):
    """Format logs as JSON with structured fields"""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Add correlation IDs if available
        correlation_id = _correlation_id.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        request_id = _request_id.get()
        if request_id:
            log_data["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": "".join(traceback.format_exception(*record.exc_info))
            }

        # Add extra fields
        if hasattr(record, "context"):
            log_data["context"] = record.context

        # Add custom fields from record
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info", "context"
            ]:
                if not key.startswith("_"):
                    log_data[key] = value

        return json.dumps(log_data, default=str)


def setup_logging(
    level: str = None,
    json_format: bool = True,
    sentry_dsn: Optional[str] = None
) -> logging.Logger:
    """
    Setup structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatting (default True)
        sentry_dsn: Sentry DSN for error tracking (optional)

    Returns:
        Root logger
    """
    # Get log level from environment or parameter
    level = level or os.getenv("LOG_LEVEL", "INFO").upper()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level))

    # Set formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Setup Sentry if DSN provided
    if sentry_dsn or os.getenv("SENTRY_DSN"):
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration

            sentry_logging = LoggingIntegration(
                level=logging.INFO,  # Capture info and above
                event_level=logging.ERROR  # Send errors as events
            )

            sentry_sdk.init(
                dsn=sentry_dsn or os.getenv("SENTRY_DSN"),
                integrations=[sentry_logging],
                traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                environment=os.getenv("ENVIRONMENT", "production"),
                release=os.getenv("RELEASE_VERSION", "unknown")
            )

            root_logger.info("Sentry error tracking enabled")

        except ImportError:
            root_logger.warning("sentry-sdk not installed, error tracking disabled")
        except Exception as e:
            root_logger.error("Failed to initialize Sentry: %s", e)

    return root_logger


def set_correlation_id(correlation_id: str):
    """Set correlation ID for current context"""
    _correlation_id.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get correlation ID from current context"""
    return _correlation_id.get()


def set_request_id(request_id: str):
    """Set request ID for current context"""
    _request_id.set(request_id)


def get_request_id() -> Optional[str]:
    """Get request ID from current context"""
    return _request_id.get()


def clear_context():
    """Clear all context variables"""
    _correlation_id.set(None)
    _request_id.set(None)


class StructuredLogger:
    """Logger with structured context support"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _log(
        self,
        level: int,
        msg: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Internal log method with context"""
        extra = {"context": context} if context else {}
        extra.update(kwargs)
        self.logger.log(level, msg, extra=extra)

    def debug(self, msg: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log debug message"""
        self._log(logging.DEBUG, msg, context, **kwargs)

    def info(self, msg: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log info message"""
        self._log(logging.INFO, msg, context, **kwargs)

    def warning(self, msg: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log warning message"""
        self._log(logging.WARNING, msg, context, **kwargs)

    def error(
        self,
        msg: str,
        context: Optional[Dict[str, Any]] = None,
        exc_info: bool = True,
        **kwargs
    ):
        """Log error message"""
        if exc_info:
            kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, context, **kwargs)

    def critical(
        self,
        msg: str,
        context: Optional[Dict[str, Any]] = None,
        exc_info: bool = True,
        **kwargs
    ):
        """Log critical message"""
        if exc_info:
            kwargs["exc_info"] = True
        self._log(logging.CRITICAL, msg, context, **kwargs)


def get_logger(name: str) -> StructuredLogger:
    """Get structured logger instance"""
    return StructuredLogger(name)


# Context manager for correlation tracking
class correlation_context:
    """Context manager for correlation ID tracking"""

    def __init__(self, correlation_id: str):
        self.correlation_id = correlation_id
        self.prev_correlation_id = None

    def __enter__(self):
        self.prev_correlation_id = get_correlation_id()
        set_correlation_id(self.correlation_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.prev_correlation_id:
            set_correlation_id(self.prev_correlation_id)
        else:
            clear_context()


# FastAPI integration
def create_logging_middleware():
    """Create FastAPI logging middleware"""
    from fastapi import Request, Response
    from uuid import uuid4

    logger = get_logger("middleware")

    async def logging_middleware(request: Request, call_next):
        # Generate request ID
        request_id = str(uuid4())
        set_request_id(request_id)

        # Log request
        logger.info(
            "Request received",
            context={
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent")
            }
        )

        # Process request
        try:
            response: Response = await call_next(request)

            # Log response
            logger.info(
                "Request completed",
                context={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code
                }
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            logger.error(
                "Request failed",
                context={
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e)
                }
            )
            raise

        finally:
            clear_context()

    return logging_middleware


# Example usage
if __name__ == "__main__":
    # Setup logging
    setup_logging(level="DEBUG", json_format=True)

    logger = get_logger(__name__)

    # Simple log
    logger.info("Application started")

    # Log with context
    logger.info(
        "Processing request",
        context={
            "user_id": "12345",
            "action": "create_proposal"
        }
    )

    # Log with correlation ID
    with correlation_context("DAILY_WATCH:2026-03-03"):
        logger.info("Watch job started")
        logger.debug("Fetching sources", context={"source_count": 5})

        try:
            raise ValueError("Example error")
        except Exception:
            logger.error("Watch job failed", context={"stage": "FETCH"})

    logger.info("Application stopped")
