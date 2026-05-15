from functools import lru_cache

from google import genai
from google.cloud import firestore
from google.cloud import pubsub_v1
from google.cloud import storage
from google.cloud import vision
from google.genai.types import HttpOptions

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


@lru_cache
def genai_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=settings().gcp_project_id,
        location=settings().vertex_ai_location,
        http_options=HttpOptions(api_version="v1"),
    )


def topic_path(topic_name: str) -> str:
    return pubsub_publisher().topic_path(settings().gcp_project_id, topic_name)
