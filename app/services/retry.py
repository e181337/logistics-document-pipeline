from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from app.gcp_clients import settings
from app.repositories import DocumentRepository
from app.services.events import EventPublisher
from app.services.workflow import mark_step_retry_requested


RETRYABLE_STEPS = {
    "preprocess",
    "split",
    "ocr",
    "ocr_aggregate",
    "extraction",
    "validation",
}


class RetryRequestError(ValueError):
    pass


class RetryService:
    def __init__(self) -> None:
        self.repository = DocumentRepository()
        self.event_publisher = EventPublisher()

    def retry(self, document_id: str, payload: dict[str, Any]) -> dict[str, str]:
        step = require_retry_step(payload)
        document = self.repository.get(document_id)
        if document is None:
            raise RetryRequestError(f"Document not found: {document_id}")

        now = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": retry_requested_status(step),
                "updated_at": now,
                f"{step}_retry_count": firestore.Increment(1),
                **mark_step_retry_requested(step, now),
            },
        )

        event_payload = retry_event_payload(document, step)
        publish_retry_event(self.event_publisher, step, event_payload)

        return {
            "document_id": document_id,
            "step": step,
            "status": retry_requested_status(step),
        }


def require_retry_step(payload: dict[str, Any]) -> str:
    step = payload.get("step")
    if not isinstance(step, str) or not step:
        raise RetryRequestError("Missing required field: step")
    if step not in RETRYABLE_STEPS:
        allowed = ", ".join(sorted(RETRYABLE_STEPS))
        raise RetryRequestError(f"step must be one of: {allowed}")
    return step


def retry_requested_status(step: str) -> str:
    if step == "ocr":
        return "OCR_RETRY_REQUESTED"
    return f"{step.upper()}_RETRY_REQUESTED"


def retry_event_payload(document: dict[str, Any], step: str) -> dict[str, Any]:
    payload = {
        "document_id": require_document_value(document, "document_id"),
        "tenant_id": require_document_value(document, "tenant_id"),
        "trace_id": document.get("trace_id", ""),
    }

    if step in {"preprocess", "split", "ocr"}:
        payload["file_uri"] = require_document_value(document, "file_uri")
        payload["content_type"] = document.get("content_type")

    return payload


def require_document_value(document: dict[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise RetryRequestError(f"Document is missing required field for retry: {field}")
    return value


def publish_retry_event(
    event_publisher: EventPublisher,
    step: str,
    payload: dict[str, Any],
) -> None:
    current_settings = settings()
    if step == "preprocess":
        event_publisher.publish_document_uploaded(
            current_settings.pubsub_document_uploaded_topic,
            payload,
        )
    elif step == "split":
        event_publisher.publish_document_split_requested(
            current_settings.pubsub_document_split_requested_topic,
            payload,
        )
    elif step == "ocr":
        event_publisher.publish_ocr_requested(
            current_settings.pubsub_ocr_requested_topic,
            payload,
        )
    elif step == "ocr_aggregate":
        event_publisher.publish_ocr_aggregate_requested(
            current_settings.pubsub_ocr_aggregate_requested_topic,
            payload,
        )
    elif step == "extraction":
        event_publisher.publish_extraction_requested(
            current_settings.pubsub_extraction_requested_topic,
            payload,
        )
    elif step == "validation":
        event_publisher.publish_validation_requested(
            current_settings.pubsub_validation_requested_topic,
            payload,
        )
    else:
        raise RetryRequestError(f"Unsupported retry step: {step}")
