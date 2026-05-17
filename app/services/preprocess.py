import io
from datetime import datetime, timezone
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.gcp_clients import settings
from app.repositories import DocumentRepository
from app.services.events import EventPublisher
from app.services.pubsub import PubSubMessageError, decode_pubsub_payload, require_value
from app.services.storage import StorageService
from app.services.workflow import mark_step_completed, mark_step_processing


TERMINAL_PREPROCESS_STATUSES = {
    "PREPROCESSED",
    "OCR_PROCESSING",
    "OCR_COMPLETED",
    "OCR_SKIPPED",
    "EXTRACTION_PROCESSING",
    "EXTRACTION_COMPLETED",
    "VALIDATION_PROCESSING",
    "VALIDATION_COMPLETED",
    "VALIDATION_COMPLETED_WITH_WARNINGS",
    "NEEDS_REVIEW",
    "REVIEW_COMPLETED",
    "OCR_RETRY_REQUESTED",
    "EXTRACTION_RETRY_REQUESTED",
    "VALIDATION_RETRY_REQUESTED",
}

PDF_SPLIT_PAGE_THRESHOLD = 1


class PreprocessService:
    def __init__(self) -> None:
        self.repository = DocumentRepository()
        self.storage = StorageService()
        self.event_publisher = EventPublisher()

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
                **mark_step_processing("preprocess", now),
            },
        )

        metadata = self.storage.get_metadata(file_uri)
        document_shape = self.inspect_document(file_uri, metadata.content_type)
        next_step = next_step_after_preprocess(document_shape)
        completed_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "PREPROCESSED",
                "updated_at": completed_at,
                **mark_step_completed("preprocess", completed_at, next_step=next_step),
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

        event_payload = {
            "document_id": document_id,
            "tenant_id": document["tenant_id"],
            "file_uri": file_uri,
            "content_type": metadata.content_type,
            "trace_id": document.get("trace_id", ""),
        }
        if next_step == "split":
            self.event_publisher.publish_document_split_requested(
                topic_name=settings().pubsub_document_split_requested_topic,
                payload=event_payload,
            )
        else:
            self.event_publisher.publish_ocr_requested(
                topic_name=settings().pubsub_ocr_requested_topic,
                payload=event_payload,
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
            import fitz

            pdf_bytes = self.storage.download_bytes(file_uri)
            with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
                page_count = pdf.page_count

            return {
                "document_kind": "pdf",
                "page_count": page_count,
            }

        return {
            "document_kind": "unknown",
        }


def next_step_after_preprocess(document_shape: dict[str, Any]) -> str:
    if (
        document_shape.get("document_kind") == "pdf"
        and isinstance(document_shape.get("page_count"), int)
        and document_shape["page_count"] > PDF_SPLIT_PAGE_THRESHOLD
    ):
        return "split"
    return "ocr"
