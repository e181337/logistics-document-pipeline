import re
from datetime import datetime, timezone
from typing import Any

from app.repositories import DocumentRepository
from app.services.pubsub import PubSubMessageError, decode_pubsub_payload, require_value
from app.services.review import ReviewTaskService
from app.services.workflow import (
    mark_review_waiting,
    mark_step_completed,
    mark_step_processing,
    mark_workflow_completed,
)


TERMINAL_VALIDATION_STATUSES = {
    "VALIDATION_COMPLETED",
    "VALIDATION_COMPLETED_WITH_WARNINGS",
    "NEEDS_REVIEW",
    "REVIEW_COMPLETED",
}


class ValidationService:
    def __init__(self) -> None:
        self.repository = DocumentRepository()
        self.review_tasks = ReviewTaskService()

    def handle_pubsub_push(self, envelope: dict[str, Any]) -> dict[str, str]:
        payload = decode_pubsub_payload(envelope)
        document_id = require_value(payload, "document_id")

        document = self.repository.get(document_id)
        if document is None:
            raise PubSubMessageError(f"Document not found: {document_id}")

        if document.get("status") in TERMINAL_VALIDATION_STATUSES:
            return {"document_id": document_id, "status": document["status"]}

        extraction = document.get("extraction")
        if not isinstance(extraction, dict) or not isinstance(extraction.get("fields"), dict):
            raise PubSubMessageError(f"Extraction fields not found for document: {document_id}")

        started_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "VALIDATION_PROCESSING",
                "updated_at": started_at,
                **mark_step_processing("validation", started_at),
            },
        )

        issues = validate_bill_of_lading(extraction["fields"])
        final_status = validation_status(issues)
        review_task_id = self.review_tasks.create_for_validation_issues(document, issues)
        completed_at = datetime.now(timezone.utc)
        workflow_update = (
            mark_review_waiting(completed_at, review_task_id)
            if review_task_id
            else mark_workflow_completed("validation", completed_at)
        )
        self.repository.update(
            document_id,
            {
                "status": final_status,
                "updated_at": completed_at,
                "review_task_id": review_task_id,
                **mark_step_completed(
                    "validation",
                    completed_at,
                    next_step="review" if review_task_id else None,
                ),
                **workflow_update,
                "validation": {
                    "processed_at": completed_at,
                    "method": "deterministic_rules_v1",
                    "status": final_status,
                    "issues": issues,
                    "issue_count": len(issues),
                    "review_task_id": review_task_id,
                },
            },
        )

        return {"document_id": document_id, "status": final_status}


def validate_bill_of_lading(fields: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    require_field(issues, fields, "bill_of_lading_number")
    require_field(issues, fields, "ship_from.name")
    require_field(issues, fields, "ship_to.name")
    require_field(issues, fields, "carrier.name")
    require_field(issues, fields, "total_weight")
    require_field(issues, fields, "package_count")

    match_pattern(
        issues,
        "bill_of_lading_number",
        get_field(fields, "bill_of_lading_number"),
        r"^BOL-\d{4}-\d{4}-\d{4}$",
        "bol_number_invalid_format",
        "Bill of lading number does not match expected BOL-YYYY-NNNN-NNNN format.",
    )
    match_pattern(
        issues,
        "ship_from.sid",
        get_field(fields, "ship_from.sid"),
        r"^SID-[A-Z]{2}-\d+$",
        "shipper_id_invalid_format",
        "Shipper ID does not match expected SID-CC-NNN format.",
        required=False,
    )
    match_pattern(
        issues,
        "ship_to.cid",
        get_field(fields, "ship_to.cid"),
        r"^CID-[A-Z]{2}-\d+$",
        "consignee_id_invalid_format",
        "Consignee ID does not match expected CID-CC-NNN format.",
        required=False,
    )
    match_pattern(
        issues,
        "carrier.seal_number",
        get_field(fields, "carrier.seal_number"),
        r"^SEAL-\d+$",
        "seal_number_invalid_format",
        "Seal number does not match expected SEAL-NNN format.",
        required=False,
    )
    match_pattern(
        issues,
        "carrier.pro_number",
        get_field(fields, "carrier.pro_number"),
        r"^PRO-\d+$",
        "pro_number_invalid_format",
        "PRO number does not match expected PRO-NNN format.",
        required=False,
    )

    validate_weight(issues, get_field(fields, "total_weight"))
    validate_package_count(issues, get_field(fields, "package_count"))
    validate_freight_terms(issues, get_field(fields, "freight_terms"))
    validate_postal_code(issues, "ship_from.city_state_zip", get_field(fields, "ship_from.city_state_zip"))
    validate_postal_code(issues, "ship_to.city_state_zip", get_field(fields, "ship_to.city_state_zip"))
    validate_postal_code(
        issues,
        "third_party_bill_to.city_state_zip",
        get_field(fields, "third_party_bill_to.city_state_zip"),
    )

    return issues


def require_field(issues: list[dict[str, str]], fields: dict[str, Any], field: str) -> None:
    value = get_field(fields, field)
    if value is None or value == "":
        add_issue(
            issues,
            field,
            "error",
            "required_field_missing",
            f"Required field is missing: {field}.",
        )


def match_pattern(
    issues: list[dict[str, str]],
    field: str,
    value: Any,
    pattern: str,
    code: str,
    message: str,
    required: bool = True,
) -> None:
    if value is None or value == "":
        if required:
            require_field(issues, {}, field)
        return

    if not isinstance(value, str) or not re.match(pattern, value):
        add_issue(issues, field, "error", code, message)


def validate_weight(issues: list[dict[str, str]], value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not re.match(r"^\d{1,3}(,\d{3})*\s*kg$", value):
        add_issue(
            issues,
            "total_weight",
            "error",
            "weight_invalid_format",
            "Total weight must look like '2,520 kg'.",
        )


def validate_package_count(issues: list[dict[str, str]], value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, int) or value <= 0:
        add_issue(
            issues,
            "package_count",
            "error",
            "package_count_invalid",
            "Package count must be a positive integer.",
        )


def validate_freight_terms(issues: list[dict[str, str]], value: Any) -> None:
    if value is None:
        return
    if value not in {"prepaid", "collect", "third_party"}:
        add_issue(
            issues,
            "freight_terms",
            "warning",
            "freight_terms_unrecognized",
            "Freight terms should be prepaid, collect, or third_party.",
        )


def validate_postal_code(issues: list[dict[str, str]], field: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        return
    if not re.search(r"\b\d{5}\b", value):
        add_issue(
            issues,
            field,
            "warning",
            "postal_code_missing_or_suspicious",
            "Expected a 5-digit postal code in the address line.",
        )


def validation_status(issues: list[dict[str, str]]) -> str:
    if any(issue["severity"] == "error" for issue in issues):
        return "NEEDS_REVIEW"
    if issues:
        return "VALIDATION_COMPLETED_WITH_WARNINGS"
    return "VALIDATION_COMPLETED"


def add_issue(
    issues: list[dict[str, str]],
    field: str,
    severity: str,
    code: str,
    message: str,
) -> None:
    issues.append(
        {
            "field": field,
            "severity": severity,
            "code": code,
            "message": message,
        }
    )


def get_field(fields: dict[str, Any], path: str) -> Any:
    current: Any = fields
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
