from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from app.gcp_clients import settings
from app.repositories import DocumentRepository
from app.services.events import EventPublisher
from app.services.pubsub import PubSubMessageError, decode_pubsub_payload, require_value
from app.services.storage import StorageService, parse_gcs_uri
from app.services.workflow import mark_step_completed, mark_step_processing


TERMINAL_SPLIT_STATUSES = {
    "SPLIT_COMPLETED",
    "PAGE_OCR_PROCESSING",
    "PAGE_OCR_COMPLETED",
    "OCR_AGGREGATE_PROCESSING",
    "OCR_COMPLETED",
    "EXTRACTION_PROCESSING",
    "EXTRACTION_COMPLETED",
    "VALIDATION_PROCESSING",
    "VALIDATION_COMPLETED",
    "VALIDATION_COMPLETED_WITH_WARNINGS",
    "NEEDS_REVIEW",
    "REVIEW_COMPLETED",
}


class SplitService:
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

        if document.get("status") in TERMINAL_SPLIT_STATUSES:
            return {"document_id": document_id, "status": document["status"]}

        started_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "SPLIT_PROCESSING",
                "updated_at": started_at,
                **mark_step_processing("split", started_at),
            },
        )

        pages = self.split_pdf(file_uri)
        completed_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "PAGE_OCR_PROCESSING",
                "updated_at": completed_at,
                "page_count": len(pages),
                "page_ocr_completed_count": 0,
                "page_ocr_failed_count": 0,
                "split": {
                    "processed_at": completed_at,
                    "method": "pymupdf_render_png_v1",
                    "page_count": len(pages),
                },
                **mark_step_completed("split", completed_at, next_step="page_ocr"),
                **mark_step_processing("page_ocr", completed_at),
            },
        )

        for page in pages:
            self.repository.create_page(
                document_id,
                page["page_id"],
                {
                    "document_id": document_id,
                    "tenant_id": document["tenant_id"],
                    "trace_id": document.get("trace_id", ""),
                    "page_id": page["page_id"],
                    "page_number": page["page_number"],
                    "page_uri": page["page_uri"],
                    "status": "OCR_REQUESTED",
                    "created_at": completed_at,
                    "updated_at": completed_at,
                },
            )
            self.event_publisher.publish_page_ocr_requested(
                topic_name=settings().pubsub_page_ocr_requested_topic,
                payload={
                    "document_id": document_id,
                    "tenant_id": document["tenant_id"],
                    "trace_id": document.get("trace_id", ""),
                    "page_id": page["page_id"],
                    "page_number": page["page_number"],
                    "page_uri": page["page_uri"],
                    "total_pages": len(pages),
                },
            )

        return {"document_id": document_id, "status": "PAGE_OCR_PROCESSING"}

    def split_pdf(self, file_uri: str) -> list[dict[str, Any]]:
        import fitz

        pdf_bytes = self.storage.download_bytes(file_uri)
        source_bucket, source_object = parse_gcs_uri(file_uri)
        page_prefix = f"{PurePosixPath(source_object).parent}/pages"
        pages: list[dict[str, Any]] = []

        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            for page_index in range(pdf.page_count):
                page_number = page_index + 1
                page_id = f"{page_number:04d}"
                page = pdf.load_page(page_index)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                page_bytes = pixmap.tobytes("png")
                object_name = f"{page_prefix}/page-{page_id}.png"
                stored_page = self.storage.upload(
                    bucket_name=source_bucket,
                    object_name=object_name,
                    content=page_bytes,
                    content_type="image/png",
                )
                pages.append(
                    {
                        "page_id": page_id,
                        "page_number": page_number,
                        "page_uri": stored_page.file_uri,
                    }
                )

        return pages
