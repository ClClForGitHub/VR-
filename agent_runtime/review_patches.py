"""ReviewPatch handoff helpers for explicit user feedback.

V1 requires user feedback to be stored as structured review patches. These
helpers convert an existing PendingAction plus a user-provided instruction into
the existing ReviewPatch state model without calling an LLM or adding another
queue/state store.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.state import AgentProjectState, ReviewPatch, WorkflowPhase
from agent_runtime.state_views import apply_state_updates


class ReviewPatchHandoffResult(BaseModel):
    ok: bool
    patch: ReviewPatch | None = None
    pending_action_id: str | None = None
    cleared_pending_action: bool = False
    next_phase: WorkflowPhase | None = None
    issues: list[str] = Field(default_factory=list)


def create_review_patch_from_pending_action(
    *,
    state: AgentProjectState,
    user_feedback: str,
    source_turn_id: str | None = None,
    patch_id: str | None = None,
    patch_type: str | None = None,
    clear_pending_action: bool = True,
    next_phase: WorkflowPhase = WorkflowPhase.CONCEPT_REVIEW,
) -> tuple[ReviewPatchHandoffResult, AgentProjectState]:
    """Create a structured ReviewPatch from the current PendingAction."""

    feedback = user_feedback.strip()
    if not feedback:
        return ReviewPatchHandoffResult(ok=False, issues=["empty_user_feedback"]), state
    pending = state.pending_action
    if pending is None:
        return ReviewPatchHandoffResult(ok=False, issues=["missing_pending_action"]), state

    payload = pending.payload or {}
    if payload.get("kind") != "subject_asset_repair":
        return (
            ReviewPatchHandoffResult(
                ok=False,
                pending_action_id=pending.action_id,
                issues=[f"unsupported_pending_action_kind:{payload.get('kind')}"],
            ),
            state,
        )

    subject_id = payload.get("subject_id")
    if not subject_id:
        return (
            ReviewPatchHandoffResult(
                ok=False,
                pending_action_id=pending.action_id,
                issues=["pending_action_missing_subject_id"],
            ),
            state,
        )

    resolved_patch = ReviewPatch(
        patch_id=patch_id or f"patch_{uuid4().hex[:12]}",
        source_turn_id=source_turn_id or pending.action_id,
        phase_created=pending.phase,
        target_type="subject",
        target_id=str(subject_id),
        patch_type=_resolve_patch_type(patch_type),
        instruction=feedback,
        structured_delta={
            "kind": "subject_asset_repair_feedback",
            "pending_action_id": pending.action_id,
            "pending_action_type": pending.action_type,
            "asset_id": payload.get("asset_id"),
            "subject_id": payload.get("subject_id"),
            "source_image_id": payload.get("source_image_id"),
            "repair_decision": _safe_dict(payload.get("repair_decision")),
        },
        affected_artifact_ids=_affected_artifact_ids(payload),
        status="pending",
    )
    updates: dict[str, Any] = {
        "review_patches": [*state.review_patches, resolved_patch],
        "phase": next_phase,
    }
    if clear_pending_action:
        updates["pending_action"] = None
    updated_state = apply_state_updates(
        state,
        node_name="FeedbackPatchParser",
        updates=updates,
    )
    return (
        ReviewPatchHandoffResult(
            ok=True,
            patch=resolved_patch,
            pending_action_id=pending.action_id,
            cleared_pending_action=clear_pending_action,
            next_phase=next_phase,
        ),
        updated_state,
    )


def _resolve_patch_type(value: str | None) -> str:
    allowed = {
        "appearance_change",
        "pose_change",
        "style_change",
        "lighting_change",
        "camera_change",
        "layout_change",
        "add_subject",
        "remove_subject",
        "replace_subject",
        "material_change",
        "move_object",
        "rotate_object",
        "scale_object",
        "redo_subject",
        "redo_scene",
    }
    return value if value in allowed else "redo_subject"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _affected_artifact_ids(payload: dict[str, Any]) -> list[str]:
    values = []
    for key in ("asset_id", "source_image_id"):
        value = payload.get(key)
        if value and value not in values:
            values.append(str(value))
    return values
