from datetime import datetime, timezone
from typing import Any

from app.gcp_clients import settings
from app.repositories import DocumentRepository
from app.services.events import EventPublisher
from app.services.pubsub import PubSubMessageError, decode_pubsub_payload, require_value
from app.services.workflow import mark_step_completed, mark_step_processing


TERMINAL_AGGREGATE_STATUSES = {
    "OCR_COMPLETED",
    "EXTRACTION_PROCESSING",
    "EXTRACTION_COMPLETED",
    "VALIDATION_PROCESSING",
    "VALIDATION_COMPLETED",
    "VALIDATION_COMPLETED_WITH_WARNINGS",
    "NEEDS_REVIEW",
    "REVIEW_COMPLETED",
}


class OcrAggregateService:
    def __init__(self) -> None:
        self.repository = DocumentRepository()
        self.event_publisher = EventPublisher()

    def handle_pubsub_push(self, envelope: dict[str, Any]) -> dict[str, str]:
        payload = decode_pubsub_payload(envelope)
        document_id = require_value(payload, "document_id")

        document = self.repository.get(document_id)
        if document is None:
            raise PubSubMessageError(f"Document not found: {document_id}")

        if document.get("status") in TERMINAL_AGGREGATE_STATUSES:
            return {"document_id": document_id, "status": document["status"]}

        started_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "OCR_AGGREGATE_PROCESSING",
                "updated_at": started_at,
                **mark_step_processing("ocr_aggregate", started_at),
            },
        )

        pages = self.repository.list_pages(document_id)
        page_count = document.get("page_count")
        if not isinstance(page_count, int) or len(pages) < page_count:
            raise PubSubMessageError(f"Not all OCR pages are available for document: {document_id}")

        full_text = aggregate_page_text(pages)
        completed_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "OCR_COMPLETED",
                "updated_at": completed_at,
                "ocr": {
                    "processed_at": completed_at,
                    "provider": "google_cloud_vision",
                    "mode": "page_fan_out",
                    "page_count": page_count,
                    "text": full_text,
                    "text_length": len(full_text),
                },
                **mark_step_completed("ocr_aggregate", completed_at, next_step="extraction"),
            },
        )

        self.event_publisher.publish_extraction_requested(
            topic_name=settings().pubsub_extraction_requested_topic,
            payload={
                "document_id": document_id,
                "tenant_id": document["tenant_id"],
                "file_uri": document.get("file_uri", ""),
                "trace_id": document.get("trace_id", ""),
            },
        )

        return {"document_id": document_id, "status": "OCR_COMPLETED"}


def aggregate_page_text(pages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for page in sorted(pages, key=lambda item: item.get("page_number", 0)):
        ocr = page.get("ocr")
        if not isinstance(ocr, dict) or not isinstance(ocr.get("text"), str):
            raise PubSubMessageError(f"OCR text missing for page: {page.get('page_id')}")

        page_number = page.get("page_number")
        parts.append(f"--- Page {page_number} ---\n{ocr['text']}")

    return "\n\n".join(parts)
