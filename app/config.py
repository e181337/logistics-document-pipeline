import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    gcp_project_id: str
    gcs_upload_bucket: str
    pubsub_document_uploaded_topic: str
    pubsub_ocr_requested_topic: str
    pubsub_document_split_requested_topic: str
    pubsub_page_ocr_requested_topic: str
    pubsub_ocr_aggregate_requested_topic: str
    pubsub_extraction_requested_topic: str
    pubsub_validation_requested_topic: str
    firestore_document_collection: str = "documents"
    firestore_review_task_collection: str = "review_tasks"
    firestore_pipeline_failure_collection: str = "pipeline_failures"
    firestore_database: str = "(default)"
    vertex_ai_location: str = "global"
    gemini_extraction_model: str = "gemini-2.5-flash"



def get_settings() -> Settings:
    return Settings(
        gcp_project_id=os.getenv("GCP_PROJECT_ID", ""),
        gcs_upload_bucket=os.getenv("GCS_UPLOAD_BUCKET", ""),
        pubsub_document_uploaded_topic=os.getenv(
            "PUBSUB_DOCUMENT_UPLOADED_TOPIC",
            "document.uploaded",
        ),
        pubsub_ocr_requested_topic=os.getenv(
            "PUBSUB_OCR_REQUESTED_TOPIC",
            "ocr.requested",
        ),
        pubsub_document_split_requested_topic=os.getenv(
            "PUBSUB_DOCUMENT_SPLIT_REQUESTED_TOPIC",
            "document.split.requested",
        ),
        pubsub_page_ocr_requested_topic=os.getenv(
            "PUBSUB_PAGE_OCR_REQUESTED_TOPIC",
            "page.ocr.requested",
        ),
        pubsub_ocr_aggregate_requested_topic=os.getenv(
            "PUBSUB_OCR_AGGREGATE_REQUESTED_TOPIC",
            "ocr.aggregate.requested",
        ),
        pubsub_extraction_requested_topic=os.getenv(
            "PUBSUB_EXTRACTION_REQUESTED_TOPIC",
            "extraction.requested",
        ),
        pubsub_validation_requested_topic=os.getenv(
            "PUBSUB_VALIDATION_REQUESTED_TOPIC",
            "validation.requested",
        ),
        firestore_document_collection=os.getenv(
            "FIRESTORE_DOCUMENT_COLLECTION",
            "documents",
        ),
        firestore_review_task_collection=os.getenv(
            "FIRESTORE_REVIEW_TASK_COLLECTION",
            "review_tasks",
        ),
        firestore_pipeline_failure_collection=os.getenv(
            "FIRESTORE_PIPELINE_FAILURE_COLLECTION",
            "pipeline_failures",
        ),
        firestore_database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        vertex_ai_location=os.getenv("VERTEX_AI_LOCATION", "global"),
        gemini_extraction_model=os.getenv("GEMINI_EXTRACTION_MODEL", "gemini-2.5-flash"),
    )


def validate_settings(settings: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("GCP_PROJECT_ID", settings.gcp_project_id),
            ("GCS_UPLOAD_BUCKET", settings.gcs_upload_bucket),
            ("PUBSUB_DOCUMENT_UPLOADED_TOPIC", settings.pubsub_document_uploaded_topic),
            ("PUBSUB_OCR_REQUESTED_TOPIC", settings.pubsub_ocr_requested_topic),
            ("PUBSUB_DOCUMENT_SPLIT_REQUESTED_TOPIC", settings.pubsub_document_split_requested_topic),
            ("PUBSUB_PAGE_OCR_REQUESTED_TOPIC", settings.pubsub_page_ocr_requested_topic),
            ("PUBSUB_OCR_AGGREGATE_REQUESTED_TOPIC", settings.pubsub_ocr_aggregate_requested_topic),
            ("PUBSUB_EXTRACTION_REQUESTED_TOPIC", settings.pubsub_extraction_requested_topic),
            ("PUBSUB_VALIDATION_REQUESTED_TOPIC", settings.pubsub_validation_requested_topic),
        )
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {joined}")
