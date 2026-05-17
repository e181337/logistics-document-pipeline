from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from google.cloud import vision

from app.gcp_clients import firestore_client, settings, vision_client
from app.repositories import DocumentRepository
from app.services.events import EventPublisher
from app.services.pubsub import PubSubMessageError, decode_pubsub_payload, require_value
from app.services.workflow import mark_step_completed


class PageOcrService:
    def __init__(self) -> None:
        self.repository = DocumentRepository()
        self.vision = vision_client()
        self.event_publisher = EventPublisher()

    def handle_pubsub_push(self, envelope: dict[str, Any]) -> dict[str, str]:
        payload = decode_pubsub_payload(envelope)
        document_id = require_value(payload, "document_id")
        page_id = require_value(payload, "page_id")
        page_uri = require_value(payload, "page_uri")

        document = self.repository.get(document_id)
        if document is None:
            raise PubSubMessageError(f"Document not found: {document_id}")

        page = self.repository.get_page(document_id, page_id)
        if page is not None and page.get("status") == "OCR_COMPLETED":
            return {"document_id": document_id, "status": "OCR_COMPLETED"}

        started_at = datetime.now(timezone.utc)
        self.repository.create_page(
            document_id,
            page_id,
            {
                **(page or {}),
                "document_id": document_id,
                "tenant_id": payload.get("tenant_id") or document["tenant_id"],
                "trace_id": payload.get("trace_id") or document.get("trace_id", ""),
                "page_id": page_id,
                "page_number": payload.get("page_number"),
                "page_uri": page_uri,
                "status": "OCR_PROCESSING",
                "updated_at": started_at,
            },
        )

        text = self.extract_text(page_uri)
        completed_at = datetime.now(timezone.utc)
        should_aggregate = self.complete_page_ocr(
            document_id=document_id,
            page_id=page_id,
            text=text,
            completed_at=completed_at,
        )

        if should_aggregate:
            self.event_publisher.publish_ocr_aggregate_requested(
                topic_name=settings().pubsub_ocr_aggregate_requested_topic,
                payload={
                    "document_id": document_id,
                    "tenant_id": document["tenant_id"],
                    "trace_id": document.get("trace_id", ""),
                },
            )

        return {"document_id": document_id, "status": "OCR_COMPLETED"}

    def extract_text(self, page_uri: str) -> str:
        image = vision.Image(source=vision.ImageSource(image_uri=page_uri))
        response = self.vision.document_text_detection(image=image)
        if response.error.message:
            raise RuntimeError(response.error.message)

        return response.full_text_annotation.text or ""

    def complete_page_ocr(
        self,
        document_id: str,
        page_id: str,
        text: str,
        completed_at: datetime,
    ) -> bool:
        transaction = firestore_client().transaction()
        doc_ref = self.repository.collection.document(document_id)
        page_ref = doc_ref.collection("pages").document(page_id)

        @firestore.transactional
        def update_in_transaction(transaction: firestore.Transaction) -> bool:
            doc_snapshot = doc_ref.get(transaction=transaction)
            page_snapshot = page_ref.get(transaction=transaction)
            document = doc_snapshot.to_dict() or {}
            page = page_snapshot.to_dict() or {}

            if page.get("status") == "OCR_COMPLETED":
                return False

            page_count = document.get("page_count")
            if not isinstance(page_count, int) or page_count <= 0:
                raise RuntimeError(f"Invalid page_count for document: {document_id}")

            current_count = document.get("page_ocr_completed_count", 0)
            if not isinstance(current_count, int):
                current_count = 0
            new_count = current_count + 1
            all_pages_completed = new_count >= page_count

            transaction.update(
                page_ref,
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

            document_update = {
                "page_ocr_completed_count": new_count,
                "updated_at": completed_at,
            }
            if all_pages_completed:
                document_update.update(
                    {
                        "status": "PAGE_OCR_COMPLETED",
                        **mark_step_completed(
                            "page_ocr",
                            completed_at,
                            next_step="ocr_aggregate",
                        ),
                    }
                )
            transaction.update(doc_ref, document_update)
            return all_pages_completed

        return update_in_transaction(transaction)
