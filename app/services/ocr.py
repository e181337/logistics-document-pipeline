from datetime import datetime, timezone
from typing import Any

from google.cloud import vision

from app.gcp_clients import settings
from app.gcp_clients import vision_client
from app.repositories import DocumentRepository
from app.services.events import EventPublisher
from app.services.pubsub import PubSubMessageError, decode_pubsub_payload, require_value


TERMINAL_OCR_STATUSES = {
    "OCR_COMPLETED",
    "OCR_SKIPPED",
    "EXTRACTION_PROCESSING",
    "EXTRACTION_COMPLETED",
}
SUPPORTED_OCR_CONTENT_TYPES = {"image/png", "image/jpeg", "image/tiff"}


class OcrService:
    def __init__(self) -> None:
        self.repository = DocumentRepository()
        self.vision = vision_client()
        self.event_publisher = EventPublisher()

    def handle_pubsub_push(self, envelope: dict[str, Any]) -> dict[str, str]:
        payload = decode_pubsub_payload(envelope)
        document_id = require_value(payload, "document_id")
        file_uri = require_value(payload, "file_uri")

        document = self.repository.get(document_id)
        if document is None:
            raise PubSubMessageError(f"Document not found: {document_id}")

        if document.get("status") in TERMINAL_OCR_STATUSES:
            return {"document_id": document_id, "status": document["status"]}

        content_type = payload.get("content_type") or document.get("content_type")
        if content_type not in SUPPORTED_OCR_CONTENT_TYPES:
            completed_at = datetime.now(timezone.utc)
            self.repository.update(
                document_id,
                {
                    "status": "OCR_SKIPPED",
                    "updated_at": completed_at,
                    "ocr": {
                        "processed_at": completed_at,
                        "provider": "google_cloud_vision",
                        "skipped_reason": f"Unsupported OCR content type: {content_type}",
                    },
                },
            )
            return {"document_id": document_id, "status": "OCR_SKIPPED"}

        self.repository.update(
            document_id,
            {
                "status": "OCR_PROCESSING",
                "updated_at": datetime.now(timezone.utc),
            },
        )

        text = self.extract_text(file_uri)
        completed_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "OCR_COMPLETED",
                "updated_at": completed_at,
                "ocr": {
                    "processed_at": completed_at,
                    "provider": "google_cloud_vision",
                    "text": text,
                    "text_length": len(text),
                },
            },
        )

        self.event_publisher.publish_extraction_requested(
            topic_name=settings().pubsub_extraction_requested_topic,
            payload={
                "document_id": document_id,
                "tenant_id": document["tenant_id"],
                "file_uri": file_uri,
                "trace_id": document.get("trace_id", ""),
            },
        )

        return {"document_id": document_id, "status": "OCR_COMPLETED"}

    def extract_text(self, file_uri: str) -> str:
        image = vision.Image(source=vision.ImageSource(image_uri=file_uri))
        response = self.vision.document_text_detection(image=image)
        if response.error.message:
            raise RuntimeError(response.error.message)

        return response.full_text_annotation.text or ""
