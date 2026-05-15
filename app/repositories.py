from app.gcp_clients import firestore_client, settings


class DocumentRepository:
    def __init__(self) -> None:
        self.collection_name = settings().firestore_document_collection
        self.collection = firestore_client().collection(self.collection_name)

    def create(self, document_id: str, payload: dict) -> None:
        self.collection.document(document_id).set(payload)

    def update(self, document_id: str, payload: dict) -> None:
        self.collection.document(document_id).update(payload)

    def get(self, document_id: str) -> dict | None:
        snapshot = self.collection.document(document_id).get()
        if not snapshot.exists:
            return None

        document = snapshot.to_dict()
        if document is None:
            return None

        return document
