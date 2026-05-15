import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.gcp_clients import settings
from app.repositories import DocumentRepository
from app.services.events import EventPublisher
from app.services.preprocess import PreprocessService, PubSubMessageError
from app.services.storage import StorageService


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


@app.post("/workers/preprocess")
def preprocess_document(envelope: dict) -> dict[str, str]:
    try:
        settings()
        return PreprocessService().handle_pubsub_push(envelope)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PubSubMessageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
