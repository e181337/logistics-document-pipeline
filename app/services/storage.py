import hashlib
from dataclasses import dataclass
from urllib.parse import urlparse

from app.gcp_clients import storage_client


@dataclass(frozen=True)
class StoredFile:
    file_uri: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class StorageObjectMetadata:
    file_uri: str
    bucket_name: str
    object_name: str
    size_bytes: int
    content_type: str | None
    generation: str | None
    updated_at: str | None


class StorageService:
    def upload(
        self,
        bucket_name: str,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile:
        bucket = storage_client().bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(content, content_type=content_type)

        return StoredFile(
            file_uri=f"gs://{bucket_name}/{object_name}",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def get_metadata(self, file_uri: str) -> StorageObjectMetadata:
        bucket_name, object_name = parse_gcs_uri(file_uri)
        bucket = storage_client().bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.reload()

        updated_at = blob.updated.isoformat() if blob.updated else None
        return StorageObjectMetadata(
            file_uri=file_uri,
            bucket_name=bucket_name,
            object_name=object_name,
            size_bytes=blob.size or 0,
            content_type=blob.content_type,
            generation=str(blob.generation) if blob.generation else None,
            updated_at=updated_at,
        )

    def download_bytes(self, file_uri: str) -> bytes:
        bucket_name, object_name = parse_gcs_uri(file_uri)
        bucket = storage_client().bucket(bucket_name)
        blob = bucket.blob(object_name)
        return blob.download_as_bytes()


def parse_gcs_uri(file_uri: str) -> tuple[str, str]:
    parsed = urlparse(file_uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path:
        raise ValueError(f"Invalid GCS URI: {file_uri}")

    return parsed.netloc, parsed.path.lstrip("/")
