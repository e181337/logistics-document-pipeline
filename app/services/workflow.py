from datetime import datetime
from typing import Any


def initial_workflow(now: datetime) -> dict[str, Any]:
    return {
        "current_step": "preprocess",
        "status": "running",
        "started_at": now,
        "updated_at": now,
        "steps": {
            "upload": {
                "status": "completed",
                "started_at": now,
                "completed_at": now,
                "updated_at": now,
            },
            "preprocess": {
                "status": "pending",
                "updated_at": now,
            }
        },
    }


def mark_step_processing(step: str, now: datetime) -> dict[str, Any]:
    return {
        "workflow.current_step": step,
        "workflow.status": "running",
        "workflow.updated_at": now,
        f"workflow.steps.{step}.status": "processing",
        f"workflow.steps.{step}.started_at": now,
        f"workflow.steps.{step}.updated_at": now,
    }


def mark_step_completed(step: str, now: datetime, next_step: str | None = None) -> dict[str, Any]:
    workflow_status = "waiting" if next_step == "review" else "running"
    update = {
        "workflow.current_step": next_step or step,
        "workflow.status": workflow_status,
        "workflow.updated_at": now,
        f"workflow.steps.{step}.status": "completed",
        f"workflow.steps.{step}.completed_at": now,
        f"workflow.steps.{step}.updated_at": now,
    }
    if next_step and next_step != "review":
        update[f"workflow.steps.{next_step}.status"] = "pending"
        update[f"workflow.steps.{next_step}.updated_at"] = now
    return update


def mark_step_skipped(step: str, now: datetime, reason: str) -> dict[str, Any]:
    return {
        "workflow.current_step": step,
        "workflow.status": "completed",
        "workflow.updated_at": now,
        f"workflow.steps.{step}.status": "skipped",
        f"workflow.steps.{step}.skipped_at": now,
        f"workflow.steps.{step}.updated_at": now,
        f"workflow.steps.{step}.reason": reason,
    }


def mark_review_waiting(now: datetime, review_task_id: str | None) -> dict[str, Any]:
    return {
        "workflow.current_step": "review",
        "workflow.status": "waiting",
        "workflow.updated_at": now,
        "workflow.steps.review.status": "waiting",
        "workflow.steps.review.started_at": now,
        "workflow.steps.review.updated_at": now,
        "workflow.steps.review.review_task_id": review_task_id,
    }


def mark_workflow_completed(final_step: str, now: datetime) -> dict[str, Any]:
    return {
        "workflow.current_step": final_step,
        "workflow.status": "completed",
        "workflow.completed_at": now,
        "workflow.updated_at": now,
        f"workflow.steps.{final_step}.status": "completed",
        f"workflow.steps.{final_step}.completed_at": now,
        f"workflow.steps.{final_step}.updated_at": now,
    }
