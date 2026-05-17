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

    def create_page(self, document_id: str, page_id: str, payload: dict) -> None:
        self.collection.document(document_id).collection("pages").document(page_id).set(payload)

    def get_page(self, document_id: str, page_id: str) -> dict | None:
        snapshot = self.collection.document(document_id).collection("pages").document(page_id).get()
        if not snapshot.exists:
            return None

        page = snapshot.to_dict()
        if page is None:
            return None

        return page

    def list_pages(self, document_id: str) -> list[dict]:
        snapshots = (
            self.collection.document(document_id)
            .collection("pages")
            .order_by("page_number")
            .stream()
        )
        return [snapshot.to_dict() or {} for snapshot in snapshots]


class ReviewTaskRepository:
    def __init__(self) -> None:
        self.collection_name = settings().firestore_review_task_collection
        self.collection = firestore_client().collection(self.collection_name)

    def create(self, review_task_id: str, payload: dict) -> None:
        self.collection.document(review_task_id).set(payload)

    def update(self, review_task_id: str, payload: dict) -> None:
        self.collection.document(review_task_id).update(payload)

    def get(self, review_task_id: str) -> dict | None:
        snapshot = self.collection.document(review_task_id).get()
        if not snapshot.exists:
            return None

        task = snapshot.to_dict()
        if task is None:
            return None

        return task


class PipelineFailureRepository:
    def __init__(self) -> None:
        self.collection_name = settings().firestore_pipeline_failure_collection
        self.collection = firestore_client().collection(self.collection_name)

    def create(self, failure_id: str, payload: dict) -> None:
        self.collection.document(failure_id).set(payload)
