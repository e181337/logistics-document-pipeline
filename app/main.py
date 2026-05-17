import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.gcp_clients import settings
from app.repositories import DocumentRepository, ReviewTaskRepository
from app.services.errors import NonRetryablePipelineError
from app.services.events import EventPublisher
from app.services.extraction import ExtractionService
from app.services.failures import PipelineFailureRecorder
from app.services.metrics import SLA_TARGET_MS, percentile, processing_metric_from_document
from app.services.ocr import OcrService
from app.services.ocr_aggregate import OcrAggregateService
from app.services.page_ocr import PageOcrService
from app.services.preprocess import PreprocessService
from app.services.review import ReviewTaskError, ReviewTaskService
from app.services.retry import RetryRequestError, RetryService
from app.services.split import SplitService
from app.services.storage import StorageService
from app.services.validation import ValidationService
from app.services.workflow import initial_workflow


app = FastAPI(title="Document Pipeline Lab")

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/invoices", status_code=202)
async def upload_invoice(
    file: UploadFile = File(...),
    tenant_id: str = Form("demo-tenant"),
) -> dict[str, str]:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type: {file.content_type}",
        )

    try:
        current_settings = settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    document_id = f"doc_{uuid.uuid4().hex}"
    trace_id = f"trace_{uuid.uuid4().hex}"
    uploaded_at = datetime.now(timezone.utc)
    safe_filename = PurePosixPath(file.filename or "invoice").name
    object_name = f"tenants/{tenant_id}/invoices/{document_id}/{safe_filename}"
    file_bytes = await file.read()

    storage_service = StorageService()
    repository = DocumentRepository()
    event_publisher = EventPublisher()

    stored_file = storage_service.upload(
        bucket_name=current_settings.gcs_upload_bucket,
        object_name=object_name,
        content=file_bytes,
        content_type=file.content_type or "application/octet-stream",
    )

    repository.create(
        document_id=document_id,
        payload={
            "document_id": document_id,
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "status": "UPLOADED",
            "file_uri": stored_file.file_uri,
            "filename": safe_filename,
            "content_type": file.content_type,
            "size_bytes": stored_file.size_bytes,
            "sha256": stored_file.sha256,
            "created_at": uploaded_at,
            "updated_at": uploaded_at,
            "workflow": initial_workflow(uploaded_at),
        },
    )

    event_publisher.publish_document_uploaded(
        topic_name=current_settings.pubsub_document_uploaded_topic,
        payload={
            "document_id": document_id,
            "tenant_id": tenant_id,
            "file_uri": stored_file.file_uri,
            "content_type": file.content_type,
            "trace_id": trace_id,
        },
    )

    return {
        "document_id": document_id,
        "status": "UPLOADED",
        "file_uri": stored_file.file_uri,
    }


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> dict:
    try:
        settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    document = DocumentRepository().get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return document


@app.get("/metrics/processing")
def get_processing_metrics(
    metric_name: str = "validation_completed",
    limit: int = 100,
) -> dict[str, int | str | None]:
    try:
        settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    bounded_limit = max(1, min(limit, 500))
    documents = DocumentRepository().list_recent_with_metric(metric_name, bounded_limit)
    durations = [
        duration
        for document in documents
        if (duration := processing_metric_from_document(document, metric_name)) is not None
    ]
    p95_ms = percentile(durations, 0.95)
    return {
        "metric_name": metric_name,
        "sample_size": len(durations),
        "p95_ms": p95_ms,
        "sla_target_ms": SLA_TARGET_MS,
        "sla_met": p95_ms <= SLA_TARGET_MS if p95_ms is not None else None,
    }


@app.post("/documents/{document_id}/retry")
def retry_document_step(document_id: str, payload: dict) -> dict[str, str]:
    try:
        settings()
        return RetryService().retry(document_id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RetryRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/review-tasks/{review_task_id}")
def get_review_task(review_task_id: str) -> dict:
    try:
        settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    review_task = ReviewTaskRepository().get(review_task_id)
    if review_task is None:
        raise HTTPException(status_code=404, detail="Review task not found")

    return review_task


@app.post("/review-tasks/{review_task_id}/resolve")
def resolve_review_task(review_task_id: str, payload: dict) -> dict[str, str]:
    try:
        settings()
        return ReviewTaskService().resolve(review_task_id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ReviewTaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/workers/preprocess")
def preprocess_document(envelope: dict) -> dict[str, str]:
    return run_worker("preprocess", envelope, lambda: PreprocessService().handle_pubsub_push(envelope))


@app.post("/workers/ocr")
def ocr_document(envelope: dict) -> dict[str, str]:
    return run_worker("ocr", envelope, lambda: OcrService().handle_pubsub_push(envelope))


@app.post("/workers/split")
def split_document(envelope: dict) -> dict[str, str]:
    return run_worker("split", envelope, lambda: SplitService().handle_pubsub_push(envelope))


@app.post("/workers/page-ocr")
def ocr_document_page(envelope: dict) -> dict[str, str]:
    return run_worker("page_ocr", envelope, lambda: PageOcrService().handle_pubsub_push(envelope))


@app.post("/workers/ocr-aggregate")
def aggregate_document_ocr(envelope: dict) -> dict[str, str]:
    return run_worker(
        "ocr_aggregate",
        envelope,
        lambda: OcrAggregateService().handle_pubsub_push(envelope),
    )


@app.post("/workers/extract")
def extract_document(envelope: dict) -> dict[str, str]:
    return run_worker("extraction", envelope, lambda: ExtractionService().handle_pubsub_push(envelope))


@app.post("/workers/validate")
def validate_document(envelope: dict) -> dict[str, str]:
    return run_worker("validation", envelope, lambda: ValidationService().handle_pubsub_push(envelope))


def run_worker(step: str, envelope: dict, handler: Callable[[], dict[str, str]]) -> dict[str, str]:
    try:
        settings()
        return handler()
    except NonRetryablePipelineError as exc:
        record_worker_failure(step, envelope, exc, retryable=False)
        return {"status": worker_failed_status(step, retryable=False)}
    except RuntimeError as exc:
        record_worker_failure(step, envelope, exc, retryable=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        record_worker_failure(step, envelope, exc, retryable=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def record_worker_failure(
    step: str,
    envelope: dict,
    exc: Exception,
    retryable: bool,
) -> None:
    try:
        PipelineFailureRecorder().record(step, envelope, exc, retryable)
    except Exception:
        return


def worker_failed_status(step: str, retryable: bool) -> str:
    suffix = "FAILED" if retryable else "FAILED_NON_RETRYABLE"
    if step == "ocr":
        return f"OCR_{suffix}"
    return f"{step.upper()}_{suffix}"
