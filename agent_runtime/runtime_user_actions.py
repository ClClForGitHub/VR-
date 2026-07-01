"""Apply explicit user approval/retry actions at runtime gates.

This module is a controlled mutation boundary for user gates. It does not add a
second state source: actions are logged for evidence, then authoritative state
changes still go through ``AgentProjectState`` plus checkpoint/front-end status
updates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.persistence import FileStateCheckpointStore, StateCheckpointRecord
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.state import AgentProjectState, AssetLibraryItem, ConceptBundle, ReviewPatch, WorkflowPhase
from agent_runtime.state_views import apply_state_updates


RuntimeUserActionType = Literal[
    "approve_concept",
    "request_concept_changes",
    "approve_model_assets",
    "request_model_changes",
    "approve_blender_preview",
    "request_blender_changes",
]
RuntimeUserActionStatus = Literal["applied", "failed"]


class RuntimeUserActionRecord(BaseModel):
    action_id: str
    action_type: RuntimeUserActionType
    status: RuntimeUserActionStatus
    ok: bool
    created_at: str
    state_json: str
    checkpoint_id: str | None = None
    checkpoint_uri: str | None = None
    runtime_plan_json: str | None = None
    applied_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)


class RuntimeUserActionSummary(BaseModel):
    run_dir: str
    generated_at: str
    action_log_jsonl: str
    total_records: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    latest_record: RuntimeUserActionRecord | None = None


class RuntimeUserActionResult(BaseModel):
    ok: bool
    run_dir: str
    state_json: str
    action_log_jsonl: str
    action_summary_json: str
    record: RuntimeUserActionRecord
    summary: RuntimeUserActionSummary
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


def approve_concept_review(
    run_dir: str | Path,
    *,
    note: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeUserActionResult:
    """Approve the current concept bundle and advance to subject generation."""

    return _apply_user_action(
        run_dir,
        action_type="approve_concept",
        handler=lambda path, state, action_id: _approve_concept(
            path,
            state=state,
            action_id=action_id,
            note=note,
            rebuild_plan=rebuild_plan,
        ),
    )


def request_concept_changes(
    run_dir: str | Path,
    *,
    feedback_text: str,
    source_turn_id: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeUserActionResult:
    """Convert concept feedback into a pending ReviewPatch."""

    return _apply_user_action(
        run_dir,
        action_type="request_concept_changes",
        handler=lambda path, state, action_id: _request_concept_changes(
            path,
            state=state,
            action_id=action_id,
            feedback_text=feedback_text,
            source_turn_id=source_turn_id,
            rebuild_plan=rebuild_plan,
        ),
    )


def approve_model_assets(
    run_dir: str | Path,
    *,
    note: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeUserActionResult:
    """Approve generated subject model assets and advance to scene generation."""

    return _apply_user_action(
        run_dir,
        action_type="approve_model_assets",
        handler=lambda path, state, action_id: _approve_model_assets(
            path,
            state=state,
            action_id=action_id,
            note=note,
            rebuild_plan=rebuild_plan,
        ),
    )


def request_model_changes(
    run_dir: str | Path,
    *,
    feedback_text: str,
    source_turn_id: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeUserActionResult:
    """Convert model-stage feedback into a pending ReviewPatch."""

    return _apply_user_action(
        run_dir,
        action_type="request_model_changes",
        handler=lambda path, state, action_id: _request_model_changes(
            path,
            state=state,
            action_id=action_id,
            feedback_text=feedback_text,
            source_turn_id=source_turn_id,
            rebuild_plan=rebuild_plan,
        ),
    )


def approve_blender_preview(
    run_dir: str | Path,
    *,
    note: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeUserActionResult:
    """Approve the current Blender/viewer preview and advance to delivery."""

    return _apply_user_action(
        run_dir,
        action_type="approve_blender_preview",
        handler=lambda path, state, action_id: _approve_blender_preview(
            path,
            state=state,
            action_id=action_id,
            note=note,
            rebuild_plan=rebuild_plan,
        ),
    )


def request_blender_changes(
    run_dir: str | Path,
    *,
    feedback_text: str,
    source_turn_id: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeUserActionResult:
    """Route preview feedback to the Blender edit phase."""

    return _apply_user_action(
        run_dir,
        action_type="request_blender_changes",
        handler=lambda path, state, action_id: _request_blender_changes(
            path,
            state=state,
            action_id=action_id,
            feedback_text=feedback_text,
            source_turn_id=source_turn_id,
            rebuild_plan=rebuild_plan,
        ),
    )


def read_runtime_user_action_records(run_dir: str | Path, *, limit: int | None = None) -> list[RuntimeUserActionRecord]:
    path = _action_log_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return []
    records = [
        RuntimeUserActionRecord(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:] if limit is not None else records


def read_runtime_user_action_summary(run_dir: str | Path) -> dict[str, Any] | None:
    path = _action_summary_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_user_action(
    run_dir: str | Path,
    *,
    action_type: RuntimeUserActionType,
    handler,
) -> RuntimeUserActionResult:
    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for runtime user action: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    action_id = f"user_action_{uuid4().hex[:12]}"

    try:
        record = handler(path, state, action_id)
    except Exception as exc:
        record = RuntimeUserActionRecord(
            action_id=action_id,
            action_type=action_type,
            status="failed",
            ok=False,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            issues=["runtime_user_action_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    _append_jsonl(_action_log_path(path), _model_to_dict(record))
    records = read_runtime_user_action_records(path)
    summary = _write_action_summary(path, records)
    return RuntimeUserActionResult(
        ok=record.ok,
        run_dir=str(path),
        state_json=str(state_path),
        action_log_jsonl=str(_action_log_path(path)),
        action_summary_json=str(_action_summary_path(path)),
        record=record,
        summary=summary,
        message=record.status,
        issues=list(record.issues),
    )


def _approve_concept(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    note: str | None,
    rebuild_plan: bool,
) -> RuntimeUserActionRecord:
    _require_concept_review_state(state)
    assert state.concept_bundle is not None
    if not _concept_has_outputs(state.concept_bundle):
        raise ValueError("concept approval requires at least one concept image")

    bundle_payload = _model_to_dict(state.concept_bundle)
    bundle_payload["approved"] = True
    bundle_payload["approved_at"] = utc_now_iso()
    concept_bundle = ConceptBundle(**bundle_payload)
    updated = apply_state_updates(
        state,
        node_name="ConceptReviewGate",
        updates={"concept_bundle": concept_bundle, "phase": WorkflowPhase.CONCEPT_APPROVED},
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="approve_concept",
        updated=updated,
        checkpoint_reason="concept_approved_by_user",
        checkpoint_node_name="ConceptReviewGate",
        checkpoint_stage="concept_approval",
        applied_fields=["concept_bundle", "phase"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "concept_version": concept_bundle.concept_version,
            "final_preview_image_id": concept_bundle.final_preview_image_id,
            "note": note,
            "next_phase": WorkflowPhase.CONCEPT_APPROVED.value,
        },
    )


def _request_concept_changes(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    feedback_text: str,
    source_turn_id: str | None,
    rebuild_plan: bool,
) -> RuntimeUserActionRecord:
    _require_concept_review_state(state)
    if not feedback_text.strip():
        raise ValueError("feedback_text is required for concept changes")
    assert state.concept_bundle is not None
    patch_id = f"review_patch_{uuid4().hex[:12]}"
    affected = _concept_artifact_ids(state.concept_bundle)
    resolved_turn_id = source_turn_id or (state.user_turns[-1].turn_id if state.user_turns else action_id)
    patch = ReviewPatch(
        patch_id=patch_id,
        source_turn_id=resolved_turn_id,
        phase_created=WorkflowPhase.CONCEPT_REVIEW,
        target_type="global",
        patch_type="style_change",
        instruction=feedback_text.strip(),
        structured_delta={
            "kind": "concept_feedback",
            "user_action_id": action_id,
            "concept_version": state.concept_bundle.concept_version,
            "previous_final_preview_image_id": state.concept_bundle.final_preview_image_id,
            "feedback_text": feedback_text.strip(),
        },
        affected_artifact_ids=affected,
        status="pending",
    )
    updated = apply_state_updates(
        state,
        node_name="ConceptReviewGate",
        updates={"review_patches": [*state.review_patches, patch], "phase": WorkflowPhase.CONCEPT_REVIEW},
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="request_concept_changes",
        updated=updated,
        checkpoint_reason="concept_feedback_patch_created",
        checkpoint_node_name="ConceptReviewGate",
        checkpoint_stage="concept_feedback",
        applied_fields=["review_patches", "phase"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "patch_id": patch.patch_id,
            "source_turn_id": patch.source_turn_id,
            "affected_artifact_ids": affected,
        },
    )


def _approve_model_assets(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    note: str | None,
    rebuild_plan: bool,
) -> RuntimeUserActionRecord:
    _require_model_review_state(state)
    library = _model_asset_library_with_review_status(state, review_status="liked", note=note)
    updated = apply_state_updates(
        state,
        node_name="ModelAssetReviewGate",
        updates={"asset_library": library, "phase": WorkflowPhase.SCENE_ASSET_GENERATION},
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="approve_model_assets",
        updated=updated,
        checkpoint_reason="model_assets_approved_by_user",
        checkpoint_node_name="ModelAssetReviewGate",
        checkpoint_stage="model_asset_approval",
        applied_fields=["asset_library", "phase"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "subject_asset_ids": _model_asset_ids(state),
            "note": note,
            "next_phase": WorkflowPhase.SCENE_ASSET_GENERATION.value,
        },
    )


def _request_model_changes(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    feedback_text: str,
    source_turn_id: str | None,
    rebuild_plan: bool,
) -> RuntimeUserActionRecord:
    _require_model_review_state(state)
    if not feedback_text.strip():
        raise ValueError("feedback_text is required for model changes")
    patch_id = f"review_patch_{uuid4().hex[:12]}"
    affected = _model_asset_ids(state)
    resolved_turn_id = source_turn_id or (state.user_turns[-1].turn_id if state.user_turns else action_id)
    patch = ReviewPatch(
        patch_id=patch_id,
        source_turn_id=resolved_turn_id,
        phase_created=WorkflowPhase.SUBJECT_ASSET_QA,
        target_type="global",
        patch_type="redo_subject",
        instruction=feedback_text.strip(),
        structured_delta={
            "kind": "model_feedback",
            "user_action_id": action_id,
            "feedback_text": feedback_text.strip(),
            "subject_asset_ids": affected,
            "return_to": "concept_regeneration",
        },
        affected_artifact_ids=affected,
        status="pending",
    )
    concept_bundle = _unapprove_concept_bundle(state.concept_bundle)
    library = _model_asset_library_with_review_status(state, review_status="rejected", note=feedback_text.strip())
    updated = apply_state_updates(
        state,
        node_name="ModelAssetReviewGate",
        updates={
            "review_patches": [*state.review_patches, patch],
            "concept_bundle": concept_bundle,
            "asset_library": library,
            "phase": WorkflowPhase.CONCEPT_REVIEW,
        },
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="request_model_changes",
        updated=updated,
        checkpoint_reason="model_feedback_patch_created",
        checkpoint_node_name="ModelAssetReviewGate",
        checkpoint_stage="model_asset_feedback",
        applied_fields=["review_patches", "concept_bundle", "asset_library", "phase"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "patch_id": patch.patch_id,
            "source_turn_id": patch.source_turn_id,
            "affected_artifact_ids": affected,
            "next_phase": WorkflowPhase.CONCEPT_REVIEW.value,
        },
    )


def _approve_blender_preview(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    note: str | None,
    rebuild_plan: bool,
) -> RuntimeUserActionRecord:
    _require_blender_preview_state(state)
    updated = apply_state_updates(
        state,
        node_name="BlenderPreviewReviewGate",
        updates={"phase": WorkflowPhase.DELIVERY},
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="approve_blender_preview",
        updated=updated,
        checkpoint_reason="blender_preview_approved_by_user",
        checkpoint_node_name="BlenderPreviewReviewGate",
        checkpoint_stage="blender_preview_approval",
        applied_fields=["phase"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "viewer_scene_id": state.viewer_scene.viewer_scene_id if state.viewer_scene is not None else None,
            "blender_scene_id": state.blender_scene.blender_scene_id if state.blender_scene is not None else None,
            "note": note,
            "next_phase": WorkflowPhase.DELIVERY.value,
        },
    )


def _request_blender_changes(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    feedback_text: str,
    source_turn_id: str | None,
    rebuild_plan: bool,
) -> RuntimeUserActionRecord:
    _require_blender_preview_state(state)
    if not feedback_text.strip():
        raise ValueError("feedback_text is required for Blender preview changes")
    patch_id = f"review_patch_{uuid4().hex[:12]}"
    resolved_turn_id = source_turn_id or (state.user_turns[-1].turn_id if state.user_turns else action_id)
    patch = ReviewPatch(
        patch_id=patch_id,
        source_turn_id=resolved_turn_id,
        phase_created=WorkflowPhase.BLENDER_PREVIEW,
        target_type="global",
        patch_type="layout_change",
        instruction=feedback_text.strip(),
        structured_delta={
            "kind": "blender_preview_feedback",
            "user_action_id": action_id,
            "viewer_scene_id": state.viewer_scene.viewer_scene_id if state.viewer_scene is not None else None,
            "blender_scene_id": state.blender_scene.blender_scene_id if state.blender_scene is not None else None,
            "feedback_text": feedback_text.strip(),
        },
        affected_artifact_ids=_blender_preview_artifact_ids(state),
        status="pending",
    )
    updated = apply_state_updates(
        state,
        node_name="BlenderPreviewReviewGate",
        updates={"review_patches": [*state.review_patches, patch], "phase": WorkflowPhase.BLENDER_EDIT},
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="request_blender_changes",
        updated=updated,
        checkpoint_reason="blender_preview_feedback_patch_created",
        checkpoint_node_name="BlenderPreviewReviewGate",
        checkpoint_stage="blender_preview_feedback",
        applied_fields=["review_patches", "phase"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "patch_id": patch.patch_id,
            "source_turn_id": patch.source_turn_id,
            "affected_artifact_ids": patch.affected_artifact_ids,
            "next_phase": WorkflowPhase.BLENDER_EDIT.value,
        },
    )


def _persist_success(
    run_dir: Path,
    *,
    action_id: str,
    action_type: RuntimeUserActionType,
    updated: AgentProjectState,
    checkpoint_reason: str,
    checkpoint_node_name: str,
    checkpoint_stage: str,
    applied_fields: list[str],
    rebuild_plan: bool,
    result_summary: dict[str, Any],
) -> RuntimeUserActionRecord:
    updated.updated_at = utc_now_iso()
    _write_json(run_dir / "state.json", _model_to_dict(updated))
    checkpoint = _save_checkpoint(
        run_dir,
        updated,
        reason=checkpoint_reason,
        node_name=checkpoint_node_name,
        stage=checkpoint_stage,
        action_id=action_id,
        applied_fields=applied_fields,
    )
    summary_payload = _read_json(run_dir / "summary.json") or {}
    _append_action_to_summary(summary_payload, checkpoint=checkpoint, action_id=action_id, action_type=action_type, stage=checkpoint_stage)
    _write_json(run_dir / "summary.json", summary_payload)
    _write_json(run_dir / "frontend_status.json", _model_to_dict(build_frontend_status(state=updated, summary=summary_payload)))
    plan_path = None
    if rebuild_plan:
        plan = build_and_save_runtime_dispatch_plan(run_dir)
        plan_path = plan.runtime_plan_json
    return RuntimeUserActionRecord(
        action_id=action_id,
        action_type=action_type,
        status="applied",
        ok=True,
        created_at=utc_now_iso(),
        state_json=str(run_dir / "state.json"),
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_uri=checkpoint.state_snapshot_uri,
        runtime_plan_json=plan_path,
        applied_fields=applied_fields,
        result_summary=result_summary,
    )


def _require_concept_review_state(state: AgentProjectState) -> None:
    if state.phase != WorkflowPhase.CONCEPT_REVIEW:
        raise ValueError(f"concept user action requires CONCEPT_REVIEW, got {state.phase.value}")
    if state.concept_bundle is None:
        raise ValueError("concept user action requires state.concept_bundle")


def _require_blender_preview_state(state: AgentProjectState) -> None:
    if state.phase != WorkflowPhase.BLENDER_PREVIEW:
        raise ValueError(f"Blender preview user action requires BLENDER_PREVIEW, got {state.phase.value}")
    if state.blender_scene is None:
        raise ValueError("Blender preview user action requires state.blender_scene")
    if state.viewer_scene is None:
        raise ValueError("Blender preview user action requires state.viewer_scene")


def _require_model_review_state(state: AgentProjectState) -> None:
    if state.phase != WorkflowPhase.SUBJECT_ASSET_QA:
        raise ValueError(f"model user action requires SUBJECT_ASSET_QA, got {state.phase.value}")
    if not _model_asset_ids(state):
        raise ValueError("model user action requires generated subject model assets")


def _concept_has_outputs(concept: ConceptBundle) -> bool:
    return bool(concept.final_preview_image_id or concept.subject_concept_images or concept.scene_concept_image_ids)


def _concept_artifact_ids(concept: ConceptBundle) -> list[str]:
    artifact_ids = []
    if concept.final_preview_image_id:
        artifact_ids.append(concept.final_preview_image_id)
    for values in concept.subject_concept_images.values():
        artifact_ids.extend(values)
    artifact_ids.extend(concept.scene_concept_image_ids)
    return sorted(set(artifact_ids))


def _model_asset_ids(state: AgentProjectState) -> list[str]:
    ids = [asset.asset_id for asset in state.subject_assets if asset.asset_id]
    ids.extend(item.artifact_id for item in state.asset_library if item.asset_kind == "subject_model")
    return sorted(set(ids))


def _model_asset_library_with_review_status(
    state: AgentProjectState,
    *,
    review_status: str,
    note: str | None,
) -> list[AssetLibraryItem]:
    timestamp = utc_now_iso()
    output = []
    for item in state.asset_library:
        payload = _model_to_dict(item)
        if item.asset_kind == "subject_model":
            payload["review_status"] = review_status
            payload["user_notes"] = note if note is not None else item.user_notes
            payload["updated_at"] = timestamp
        output.append(AssetLibraryItem(**payload))
    return output


def _unapprove_concept_bundle(concept: ConceptBundle | None) -> ConceptBundle | None:
    if concept is None:
        return None
    payload = _model_to_dict(concept)
    payload["approved"] = False
    payload["approved_at"] = None
    return ConceptBundle(**payload)


def _blender_preview_artifact_ids(state: AgentProjectState) -> list[str]:
    artifact_ids = []
    if state.blender_scene is not None:
        if state.blender_scene.blend_file_artifact_id:
            artifact_ids.append(state.blender_scene.blend_file_artifact_id)
        if state.blender_scene.preview_image_id:
            artifact_ids.append(state.blender_scene.preview_image_id)
    if state.viewer_scene is not None:
        if state.viewer_scene.viewer_scene_artifact_id:
            artifact_ids.append(state.viewer_scene.viewer_scene_artifact_id)
        if state.viewer_scene.viewer_state_artifact_id:
            artifact_ids.append(state.viewer_scene.viewer_state_artifact_id)
    return sorted(set(artifact_ids))


def _save_checkpoint(
    run_dir: Path,
    state: AgentProjectState,
    *,
    reason: str,
    node_name: str,
    stage: str,
    action_id: str,
    applied_fields: list[str],
) -> StateCheckpointRecord:
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    return store.save_checkpoint(
        state,
        reason=reason,
        node_name=node_name,
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={
            "stage": stage,
            "action_id": action_id,
            "applied_fields": applied_fields,
            "ok": True,
        },
    )


def _append_action_to_summary(
    summary: dict[str, Any],
    *,
    checkpoint: StateCheckpointRecord,
    action_id: str,
    action_type: RuntimeUserActionType,
    stage: str,
) -> None:
    summary.setdefault("ok", True)
    summary.setdefault("workflow", "runtime-console")
    executed = summary.setdefault("executed_stages", [])
    if stage not in executed:
        executed.append(stage)
    requested = summary.setdefault("requested_stages", [])
    if stage not in requested:
        requested.append(stage)
    summary.setdefault("stage_checkpoints", []).append(_model_to_dict(checkpoint))
    summary.setdefault("runtime_user_actions", []).append({"action_id": action_id, "action_type": action_type, "stage": stage})


def _write_action_summary(run_dir: Path, records: list[RuntimeUserActionRecord]) -> RuntimeUserActionSummary:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    summary = RuntimeUserActionSummary(
        run_dir=str(run_dir),
        generated_at=utc_now_iso(),
        action_log_jsonl=str(_action_log_path(run_dir)),
        total_records=len(records),
        status_counts=counts,
        latest_record=records[-1] if records else None,
    )
    _write_json(_action_summary_path(run_dir), _model_to_dict(summary))
    return summary


def _action_log_path(run_dir: Path) -> Path:
    return run_dir / "runtime_user_action.jsonl"


def _action_summary_path(run_dir: Path) -> Path:
    return run_dir / "runtime_user_action_summary.json"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
