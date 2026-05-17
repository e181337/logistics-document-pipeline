from datetime import datetime
from typing import Any


SLA_TARGET_MS = 120_000


def mark_step_metric(
    workflow: dict[str, Any] | None,
    step: str,
    completed_at: datetime,
) -> dict[str, Any]:
    started_at = step_started_at(workflow, step)
    if started_at is None:
        return {}

    duration_ms = duration_between_ms(started_at, completed_at)
    return {
        f"metrics.steps.{step}.duration_ms": duration_ms,
        f"metrics.steps.{step}.completed_at": completed_at,
    }


def mark_processing_metric(
    document: dict[str, Any],
    completed_at: datetime,
    metric_name: str = "validation_completed",
) -> dict[str, Any]:
    created_at = value_as_datetime(document.get("created_at"))
    if created_at is None:
        return {}

    duration_ms = duration_between_ms(created_at, completed_at)
    return {
        f"metrics.{metric_name}.duration_ms": duration_ms,
        f"metrics.{metric_name}.completed_at": completed_at,
        f"metrics.{metric_name}.sla_target_ms": SLA_TARGET_MS,
        f"metrics.{metric_name}.sla_met": duration_ms <= SLA_TARGET_MS,
    }


def processing_metric_from_document(
    document: dict[str, Any],
    metric_name: str = "validation_completed",
) -> int | None:
    metrics = document.get("metrics")
    if not isinstance(metrics, dict):
        return None

    metric = metrics.get(metric_name)
    if not isinstance(metric, dict):
        return None

    duration_ms = metric.get("duration_ms")
    return duration_ms if isinstance(duration_ms, int) else None


def percentile(values: list[int], percent: float) -> int | None:
    if not values:
        return None

    sorted_values = sorted(values)
    rank = round((len(sorted_values) - 1) * percent)
    return sorted_values[rank]


def duration_between_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def step_started_at(workflow: dict[str, Any] | None, step: str) -> datetime | None:
    if not isinstance(workflow, dict):
        return None

    steps = workflow.get("steps")
    if not isinstance(steps, dict):
        return None

    step_state = steps.get(step)
    if not isinstance(step_state, dict):
        return None

    return value_as_datetime(step_state.get("started_at"))


def value_as_datetime(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None
