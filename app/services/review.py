import uuid
from datetime import datetime, timezone
from typing import Any

from app.repositories import ReviewTaskRepository


class ReviewTaskService:
    def __init__(self) -> None:
        self.repository = ReviewTaskRepository()

    def create_for_validation_issues(
        self,
        document: dict[str, Any],
        issues: list[dict[str, str]],
    ) -> str | None:
        if not issues:
            return None

        review_task_id = f"review_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc)
        error_count = sum(1 for issue in issues if issue["severity"] == "error")
        warning_count = sum(1 for issue in issues if issue["severity"] == "warning")

        self.repository.create(
            review_task_id,
            {
                "review_task_id": review_task_id,
                "document_id": document["document_id"],
                "tenant_id": document["tenant_id"],
                "trace_id": document.get("trace_id"),
                "status": "OPEN",
                "priority": review_priority(error_count, warning_count),
                "reason": "validation_issues",
                "error_count": error_count,
                "warning_count": warning_count,
                "issues": issues,
                "file_uri": document.get("file_uri"),
                "created_at": now,
                "updated_at": now,
            },
        )

        return review_task_id


def review_priority(error_count: int, warning_count: int) -> str:
    if error_count:
        return "high"
    if warning_count:
        return "normal"
    return "low"
