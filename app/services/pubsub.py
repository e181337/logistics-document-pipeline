import base64
import json
from typing import Any

from app.services.errors import NonRetryablePipelineError


class PubSubMessageError(NonRetryablePipelineError, ValueError):
    pass


def decode_pubsub_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    message = envelope.get("message")
    if not isinstance(message, dict):
        raise PubSubMessageError("Missing Pub/Sub message")

    encoded_data = message.get("data")
    if not isinstance(encoded_data, str):
        raise PubSubMessageError("Missing Pub/Sub message data")

    try:
        decoded = base64.b64decode(encoded_data).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise PubSubMessageError("Invalid Pub/Sub message data") from exc

    if not isinstance(payload, dict):
        raise PubSubMessageError("Pub/Sub payload must be an object")

    return payload


def require_value(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise PubSubMessageError(f"Missing required field: {key}")

    return value
