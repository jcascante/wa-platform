import logging

import structlog


def configure_logging() -> None:
    """Structured JSON logs with tenant_id bindable per-request (SPEC §10: every log line
    needs tenant_id so we can alert on repeated webhook forward failures per tenant)."""
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def get_logger(*args, **kwargs):
    return structlog.get_logger(*args, **kwargs)
