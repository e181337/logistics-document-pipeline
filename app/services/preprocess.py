import base64
import io
import json
from datetime import datetime, timezone
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.repositories import DocumentRepository
from app.services.storage import StorageService


TERMINAL_PREPROCESS_STATUSES = {"PREPROCESSED"}


class PubSubMessageError(ValueError):
    pass


class PreprocessService:
    def __init__(self) -> None:
        self.repository = DocumentRepository()
        self.storage = StorageService()

    def handle_pubsub_push(self, envelope: dict[str, Any]) -> dict[str, str]:
        payload = decode_pubsub_payload(envelope)
        document_id = require_value(payload, "document_id")
        file_uri = require_value(payload, "file_uri")

        document = self.repository.get(document_id)
        if document is None:
            raise PubSubMessageError(f"Document not found: {document_id}")

        if document.get("status") in TERMINAL_PREPROCESS_STATUSES:
            return {"document_id": document_id, "status": document["status"]}

        now = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "PREPROCESSING",
                "updated_at": now,
            },
        )

        metadata = self.storage.get_metadata(file_uri)
        document_shape = self.inspect_document(file_uri, metadata.content_type)
        completed_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "PREPROCESSED",
                "updated_at": completed_at,
                "preprocess": {
                    "checked_at": completed_at,
                    "file_uri": metadata.file_uri,
                    "bucket_name": metadata.bucket_name,
                    "object_name": metadata.object_name,
                    "size_bytes": metadata.size_bytes,
                    "content_type": metadata.content_type,
                    "generation": metadata.generation,
                    "storage_updated_at": metadata.updated_at,
                    **document_shape,
                },
            },
        )

        return {"document_id": document_id, "status": "PREPROCESSED"}

    def inspect_document(self, file_uri: str, content_type: str | None) -> dict[str, Any]:
        if content_type and content_type.startswith("image/"):
            image_bytes = self.storage.download_bytes(file_uri)
            try:
                with Image.open(io.BytesIO(image_bytes)) as image:
                    return {
                        "document_kind": "image",
                        "image_width": image.width,
                        "image_height": image.height,
                        "image_format": image.format,
                        "page_count": 1,
                    }
            except UnidentifiedImageError:
                return {
                    "document_kind": "image",
                    "image_read_error": "unidentified_image",
                }

        if content_type == "application/pdf":
            return {
                "document_kind": "pdf",
                "page_count": None,
            }

        return {
            "document_kind": "unknown",
        }


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
