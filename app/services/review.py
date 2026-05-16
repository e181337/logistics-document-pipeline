import uuid
from datetime import datetime, timezone
from typing import Any

from app.repositories import DocumentRepository, ReviewTaskRepository
from app.services.workflow import mark_workflow_completed


VALID_REVIEW_RESOLUTIONS = {
    "APPROVED",
    "APPROVED_WITH_WARNINGS",
    "CORRECTED",
    "REJECTED",
}


class ReviewTaskError(ValueError):
    pass


class ReviewTaskService:
    def __init__(self) -> None:
        self.repository = ReviewTaskRepository()
        self.documents = DocumentRepository()

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

    def resolve(self, review_task_id: str, payload: dict[str, Any]) -> dict[str, str]:
        task = self.repository.get(review_task_id)
        if task is None:
            raise ReviewTaskError(f"Review task not found: {review_task_id}")

        if task.get("status") == "RESOLVED":
            return {
                "review_task_id": review_task_id,
                "document_id": task["document_id"],
                "status": "RESOLVED",
            }

        resolution = require_resolution(payload)
        reviewed_by = require_string(payload, "reviewed_by")
        notes = optional_string(payload, "notes")
        corrected_fields = payload.get("corrected_fields")
        if corrected_fields is not None and not isinstance(corrected_fields, dict):
            raise ReviewTaskError("corrected_fields must be an object when provided")

        resolved_at = datetime.now(timezone.utc)
        review_summary = {
            "review_task_id": review_task_id,
            "resolution": resolution,
            "reviewed_by": reviewed_by,
            "notes": notes,
            "corrected_fields": corrected_fields or {},
            "resolved_at": resolved_at,
        }

        self.repository.update(
            review_task_id,
            {
                "status": "RESOLVED",
                "resolution": resolution,
                "reviewed_by": reviewed_by,
                "notes": notes,
                "corrected_fields": corrected_fields or {},
                "resolved_at": resolved_at,
                "updated_at": resolved_at,
            },
        )
        self.documents.update(
            task["document_id"],
            {
                "status": "REVIEW_COMPLETED",
                "updated_at": resolved_at,
                **mark_workflow_completed("review", resolved_at),
                "review": review_summary,
            },
        )

        return {
            "review_task_id": review_task_id,
            "document_id": task["document_id"],
            "status": "RESOLVED",
        }


def review_priority(error_count: int, warning_count: int) -> str:
    if error_count:
        return "high"
    if warning_count:
        return "normal"
    return "low"


def require_resolution(payload: dict[str, Any]) -> str:
    resolution = require_string(payload, "resolution")
    if resolution not in VALID_REVIEW_RESOLUTIONS:
        allowed = ", ".join(sorted(VALID_REVIEW_RESOLUTIONS))
        raise ReviewTaskError(f"resolution must be one of: {allowed}")
    return resolution


def require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ReviewTaskError(f"Missing required field: {field}")
    return value


def optional_string(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReviewTaskError(f"{field} must be a string when provided")
    return value
