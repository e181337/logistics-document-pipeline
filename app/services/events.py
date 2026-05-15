import json

from app.gcp_clients import pubsub_publisher, topic_path


class EventPublisher:
    def publish_document_uploaded(self, topic_name: str, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        future = pubsub_publisher().publish(
            topic_path(topic_name),
            data,
            document_id=payload["document_id"],
            tenant_id=payload["tenant_id"],
        )
        future.result(timeout=10)
