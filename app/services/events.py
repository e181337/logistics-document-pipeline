import json

from app.gcp_clients import pubsub_publisher, topic_path


class EventPublisher:
    def publish(self, topic_name: str, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        future = pubsub_publisher().publish(
            topic_path(topic_name),
            data,
            document_id=payload["document_id"],
            tenant_id=payload["tenant_id"],
        )
        future.result(timeout=10)

    def publish_document_uploaded(self, topic_name: str, payload: dict) -> None:
        self.publish(topic_name, payload)

    def publish_ocr_requested(self, topic_name: str, payload: dict) -> None:
        self.publish(topic_name, payload)
