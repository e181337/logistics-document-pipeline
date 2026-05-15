import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    gcp_project_id: str
    gcs_upload_bucket: str
    pubsub_document_uploaded_topic: str
    firestore_document_collection: str = "documents"
    firestore_database: str = "(default)"



def get_settings() -> Settings:
    return Settings(
        gcp_project_id=os.getenv("GCP_PROJECT_ID", ""),
        gcs_upload_bucket=os.getenv("GCS_UPLOAD_BUCKET", ""),
        pubsub_document_uploaded_topic=os.getenv(
            "PUBSUB_DOCUMENT_UPLOADED_TOPIC",
            "document.uploaded",
        ),
        firestore_document_collection=os.getenv(
            "FIRESTORE_DOCUMENT_COLLECTION",
            "documents",
        ),
        firestore_database=os.getenv("FIRESTORE_DATABASE", "(default)"),
    )


def validate_settings(settings: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("GCP_PROJECT_ID", settings.gcp_project_id),
            ("GCS_UPLOAD_BUCKET", settings.gcs_upload_bucket),
            ("PUBSUB_DOCUMENT_UPLOADED_TOPIC", settings.pubsub_document_uploaded_topic),
        )
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {joined}")

