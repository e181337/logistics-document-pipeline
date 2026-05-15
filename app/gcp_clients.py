from functools import lru_cache

from google.cloud import firestore
from google.cloud import pubsub_v1
from google.cloud import storage
from google.cloud import vision

from app.config import Settings, get_settings, validate_settings


@lru_cache
def settings() -> Settings:
    current = get_settings()
    validate_settings(current)
    return current


@lru_cache
def storage_client() -> storage.Client:
    return storage.Client(project=settings().gcp_project_id)


@lru_cache
def firestore_client() -> firestore.Client:
    return firestore.Client(
        project=settings().gcp_project_id,
        database=settings().firestore_database,
)



@lru_cache
def pubsub_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


@lru_cache
def vision_client() -> vision.ImageAnnotatorClient:
    return vision.ImageAnnotatorClient()


def topic_path(topic_name: str) -> str:
    return pubsub_publisher().topic_path(settings().gcp_project_id, topic_name)
