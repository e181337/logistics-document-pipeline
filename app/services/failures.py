import uuid
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from app.repositories import DocumentRepository, PipelineFailureRepository
from app.services.pubsub import decode_pubsub_payload
from app.services.workflow import mark_step_failed


class PipelineFailureRecorder:
    def __init__(self) -> None:
        self.documents = DocumentRepository()
        self.failures = PipelineFailureRepository()

    def record(self, step: str, envelope: dict[str, Any], exc: Exception, retryable: bool) -> None:
        failed_at = datetime.now(timezone.utc)
        payload = safe_decode_payload(envelope)
        document_id = string_value(payload, "document_id")
        tenant_id = string_value(payload, "tenant_id")
        trace_id = string_value(payload, "trace_id")
        failure_id = f"failure_{uuid.uuid4().hex}"

        self.failures.create(
            failure_id,
            {
                "failure_id": failure_id,
                "document_id": document_id,
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "step": step,
                "retryable": retryable,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "payload": payload,
                "created_at": failed_at,
            },
        )

        if document_id:
            try:
                self.documents.update(
                    document_id,
                    {
                        "status": worker_failed_status(step, retryable),
                        "updated_at": failed_at,
                        f"{step}_error_count": firestore.Increment(1),
                        **mark_step_failed(step, failed_at, str(exc), retryable=retryable),
                    },
                )
            except Exception:
                return


def safe_decode_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    try:
        return decode_pubsub_payload(envelope)
    except Exception:
        return {}


def string_value(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    return value if isinstance(value, str) and value else None


def worker_failed_status(step: str, retryable: bool) -> str:
    suffix = "FAILED" if retryable else "FAILED_NON_RETRYABLE"
    if step == "ocr":
        return f"OCR_{suffix}"
    return f"{step.upper()}_{suffix}"
