import logging

logger = logging.getLogger(__name__)


def record_event(event: str, *, request_id: str | None = None) -> None:
    """Write an operational event without payloads or credentials."""
    if not event.strip():
        raise ValueError("event must not be empty")
    extra = {"request_id": request_id} if request_id else {}
    logger.info(event, extra=extra)
