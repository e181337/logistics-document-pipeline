import json
import logging
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger("document_pipeline")
logging.basicConfig(level=logging.INFO)


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **clean_fields(fields),
    }
    logger.info(json.dumps(payload, default=str))


def clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}
