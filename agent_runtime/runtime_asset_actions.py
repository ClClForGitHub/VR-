"""Controlled asset-library selection actions for runtime runs."""

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
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    AssemblyObjectSelection,
    AssemblySelection,
    AssetLibraryItem,
)
from agent_runtime.state_views import apply_state_updates


RuntimeAssetActionType = Literal[
    "set_asset_review_status",
    "select_concept_for_subject_generation",
    "select_asset_for_assembly",
]
RuntimeAssetActionStatus = Literal["applied", "failed"]


class RuntimeAssetActionRecord(BaseModel):
    action_id: str
    action_type: RuntimeAssetActionType
    status: RuntimeAssetActionStatus
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


class RuntimeAssetActionSummary(BaseModel):
    run_dir: str
    generated_at: str
    action_log_jsonl: str
    total_records: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    latest_record: RuntimeAssetActionRecord | None = None


class RuntimeAssetActionResult(BaseModel):
    ok: bool
    run_dir: str
    state_json: str
    action_log_jsonl: str
    action_summary_json: str
    record: RuntimeAssetActionRecord
    summary: RuntimeAssetActionSummary
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


def set_asset_review_status(
    run_dir: str | Path,
    *,
    artifact_id: str,
    review_status: Literal["new", "liked", "rejected", "archived", "superseded"],
    note: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeAssetActionResult:
    return _apply_asset_action(
        run_dir,
        action_type="set_asset_review_status",
        handler=lambda path, state, action_id: _set_asset_review_status(
            path,
            state=state,
            action_id=action_id,
            artifact_id=artifact_id,
            review_status=review_status,
            note=note,
            rebuild_plan=rebuild_plan,
        ),
    )


def select_concept_for_subject_generation(
    run_dir: str | Path,
    *,
    subject_id: str,
    concept_artifact_id: str,
    note: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeAssetActionResult:
    return _apply_asset_action(
        run_dir,
        action_type="select_concept_for_subject_generation",
        handler=lambda path, state, action_id: _select_concept_for_subject_generation(
            path,
            state=state,
            action_id=action_id,
            subject_id=subject_id,
            concept_artifact_id=concept_artifact_id,
            note=note,
            rebuild_plan=rebuild_plan,
        ),
    )


def select_asset_for_assembly(
    run_dir: str | Path,
    *,
    subject_asset_ids_by_subject: dict[str, str],
    scene_asset_id: str | None = None,
    scene_concept_image_id: str | None = None,
    target_render_image_id: str | None = None,
    placement_hints: list[dict[str, Any]] | None = None,
    source_turn_id: str | None = None,
    note: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeAssetActionResult:
    return _apply_asset_action(
        run_dir,
        action_type="select_asset_for_assembly",
        handler=lambda path, state, action_id: _select_asset_for_assembly(
            path,
            state=state,
            action_id=action_id,
            subject_asset_ids_by_subject=subject_asset_ids_by_subject,
            scene_asset_id=scene_asset_id,
            scene_concept_image_id=scene_concept_image_id,
            target_render_image_id=target_render_image_id,
            placement_hints=placement_hints or [],
            source_turn_id=source_turn_id,
            note=note,
            rebuild_plan=rebuild_plan,
        ),
    )


def apply_runtime_asset_action(
    run_dir: str | Path,
    *,
    payload: dict[str, Any],
    rebuild_plan: bool = True,
) -> RuntimeAssetActionResult:
    action_type = payload.get("action_type")
    if action_type == "set_asset_review_status":
        return set_asset_review_status(
            run_dir,
            artifact_id=str(payload.get("artifact_id") or ""),
            review_status=payload.get("review_status") or "new",
            note=payload.get("note") or payload.get("user_notes"),
            rebuild_plan=bool(payload.get("rebuild_plan", rebuild_plan)),
        )
    if action_type == "select_concept_for_subject_generation":
        return select_concept_for_subject_generation(
            run_dir,
            subject_id=str(payload.get("subject_id") or ""),
            concept_artifact_id=str(payload.get("concept_artifact_id") or payload.get("artifact_id") or ""),
            note=payload.get("note") or payload.get("user_notes"),
            rebuild_plan=bool(payload.get("rebuild_plan", rebuild_plan)),
        )
    if action_type == "select_asset_for_assembly":
        subject_assets = payload.get("subject_asset_ids_by_subject") or payload.get("selected_subject_assets") or {}
        if not isinstance(subject_assets, dict):
            subject_assets = {}
        return select_asset_for_assembly(
            run_dir,
            subject_asset_ids_by_subject={str(key): str(value) for key, value in subject_assets.items()},
            scene_asset_id=payload.get("scene_asset_id"),
            scene_concept_image_id=payload.get("scene_concept_image_id"),
            target_render_image_id=payload.get("target_render_image_id"),
            placement_hints=payload.get("placement_hints") or [],
            source_turn_id=payload.get("source_turn_id"),
            note=payload.get("note") or payload.get("user_notes"),
            rebuild_plan=bool(payload.get("rebuild_plan", rebuild_plan)),
        )
    raise ValueError(f"unknown asset action: {action_type}")


def read_runtime_asset_action_records(run_dir: str | Path, *, limit: int | None = None) -> list[RuntimeAssetActionRecord]:
    path = _action_log_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return []
    records = [
        RuntimeAssetActionRecord(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:] if limit is not None else records


def read_runtime_asset_action_summary(run_dir: str | Path) -> dict[str, Any] | None:
    path = _action_summary_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_asset_library_item(
    items: list[AssetLibraryItem],
    *,
    artifact_id: str,
    asset_kind: str,
    subject_id: str | None = None,
    scene_id: str | None = None,
    requirement_id: str | None = None,
    source_artifact_ids: list[str] | None = None,
    derived_artifact_ids: list[str] | None = None,
    generation_round: int = 1,
    review_status: str | None = None,
    selection_status: str | None = None,
    user_notes: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: str | None = None,
) -> list[AssetLibraryItem]:
    """Return a copy of items with one artifact-backed library row upserted."""

    timestamp = now or utc_now_iso()
    output = list(items)
    existing_index = next((index for index, item in enumerate(output) if item.artifact_id == artifact_id and item.asset_kind == asset_kind), None)
    source_ids = _unique([*(source_artifact_ids or [])])
    derived_ids = _unique([*(derived_artifact_ids or [])])
    if existing_index is None:
        output.append(
            AssetLibraryItem(
                library_item_id=f"library_{artifact_id}",
                artifact_id=artifact_id,
                asset_kind=asset_kind,  # type: ignore[arg-type]
                subject_id=subject_id,
                scene_id=scene_id,
                requirement_id=requirement_id,
                source_artifact_ids=source_ids,
                derived_artifact_ids=derived_ids,
                generation_round=generation_round,
                review_status=review_status or "new",  # type: ignore[arg-type]
                selection_status=selection_status or "available",  # type: ignore[arg-type]
                user_notes=user_notes,
                created_at=timestamp,
                updated_at=timestamp,
                metadata=metadata or {},
            )
        )
        return output

    current = output[existing_index]
    payload = _model_to_dict(current)
    payload.update(
        {
            "subject_id": subject_id if subject_id is not None else current.subject_id,
            "scene_id": scene_id if scene_id is not None else current.scene_id,
            "requirement_id": requirement_id if requirement_id is not None else current.requirement_id,
            "source_artifact_ids": _unique([*current.source_artifact_ids, *source_ids]),
            "derived_artifact_ids": _unique([*current.derived_artifact_ids, *derived_ids]),
            "generation_round": generation_round or current.generation_round,
            "review_status": review_status or current.review_status,
            "selection_status": selection_status or current.selection_status,
            "user_notes": user_notes if user_notes is not None else current.user_notes,
            "updated_at": timestamp,
            "metadata": {**current.metadata, **(metadata or {})},
        }
    )
    output[existing_index] = AssetLibraryItem(**payload)
    return output


def add_derived_artifact_link(
    items: list[AssetLibraryItem],
    *,
    source_artifact_id: str,
    derived_artifact_id: str,
    now: str | None = None,
) -> list[AssetLibraryItem]:
    timestamp = now or utc_now_iso()
    output = []
    for item in items:
        if item.artifact_id != source_artifact_id:
            output.append(item)
            continue
        payload = _model_to_dict(item)
        payload["derived_artifact_ids"] = _unique([*item.derived_artifact_ids, derived_artifact_id])
        payload["updated_at"] = timestamp
        output.append(AssetLibraryItem(**payload))
    return output


def selected_subject_concept_artifact_id(state: AgentProjectState, subject_id: str) -> str | None:
    for item in state.asset_library:
        if (
            item.asset_kind == "subject_concept"
            and item.subject_id == subject_id
            and item.selection_status == "selected_for_model_generation"
        ):
            return item.artifact_id
    return None


def asset_kind_for_artifact(artifact: ArtifactRecord) -> str | None:
    mapping = {
        ArtifactType.INPUT_IMAGE: "input_image",
        ArtifactType.SUBJECT_CONCEPT_IMAGE: "subject_concept",
        ArtifactType.SCENE_CONCEPT_IMAGE: "scene_concept",
        ArtifactType.FINAL_PREVIEW_IMAGE: "target_render",
        ArtifactType.SUBJECT_3D_ASSET: "subject_model",
        ArtifactType.SCENE_3D_ASSET: "scene_asset",
        ArtifactType.BLENDER_FILE: "blender_scene",
        ArtifactType.BLENDER_PREVIEW_RENDER: "target_render",
        ArtifactType.VIEWER_SCENE_GLB: "viewer_scene",
        ArtifactType.VIEWER_SCENE_GLTF: "viewer_scene",
        ArtifactType.EXPORT_PACKAGE: "delivery_package",
    }
    return mapping.get(artifact.artifact_type)


def _apply_asset_action(
    run_dir: str | Path,
    *,
    action_type: RuntimeAssetActionType,
    handler,
) -> RuntimeAssetActionResult:
    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for runtime asset action: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    action_id = f"asset_action_{uuid4().hex[:12]}"

    try:
        record = handler(path, state, action_id)
    except Exception as exc:
        record = RuntimeAssetActionRecord(
            action_id=action_id,
            action_type=action_type,
            status="failed",
            ok=False,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            issues=["runtime_asset_action_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    _append_jsonl(_action_log_path(path), _model_to_dict(record))
    records = read_runtime_asset_action_records(path)
    summary = _write_action_summary(path, records)
    return RuntimeAssetActionResult(
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


def _set_asset_review_status(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    artifact_id: str,
    review_status: str,
    note: str | None,
    rebuild_plan: bool,
) -> RuntimeAssetActionRecord:
    if not artifact_id:
        raise ValueError("artifact_id is required")
    item = _asset_library_item(state, artifact_id)
    if item is None:
        artifact = _artifact_by_id(state, artifact_id)
        if artifact is None:
            raise ValueError(f"asset library item or artifact not found: {artifact_id}")
        kind = asset_kind_for_artifact(artifact)
        if kind is None:
            raise ValueError(f"artifact cannot be represented in asset library: {artifact_id}")
        library = upsert_asset_library_item(
            state.asset_library,
            artifact_id=artifact.artifact_id,
            asset_kind=kind,
            subject_id=artifact.linked_subject_id,
            scene_id=artifact.linked_scene_id,
            user_notes=note,
        )
    else:
        library = list(state.asset_library)
    updated_library = _replace_item(
        library,
        artifact_id=artifact_id,
        updates={"review_status": review_status, "user_notes": note, "updated_at": utc_now_iso()},
    )
    updated = apply_state_updates(
        state,
        node_name="RuntimeAssetAction",
        updates={"asset_library": updated_library},
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="set_asset_review_status",
        updated=updated,
        checkpoint_reason="asset_review_status_updated",
        applied_fields=["asset_library"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "artifact_id": artifact_id,
            "review_status": review_status,
            "note": note,
        },
    )


def _select_concept_for_subject_generation(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    subject_id: str,
    concept_artifact_id: str,
    note: str | None,
    rebuild_plan: bool,
) -> RuntimeAssetActionRecord:
    if not subject_id:
        raise ValueError("subject_id is required")
    if not concept_artifact_id:
        raise ValueError("concept_artifact_id is required")
    artifact = _artifact_by_id(state, concept_artifact_id)
    item = _asset_library_item(state, concept_artifact_id)
    if item is None:
        if artifact is None:
            raise ValueError(f"concept artifact not found: {concept_artifact_id}")
        if artifact.artifact_type != ArtifactType.SUBJECT_CONCEPT_IMAGE:
            raise ValueError(f"artifact is not a subject concept image: {concept_artifact_id}")
        library = upsert_asset_library_item(
            state.asset_library,
            artifact_id=concept_artifact_id,
            asset_kind="subject_concept",
            subject_id=subject_id,
            user_notes=note,
        )
    else:
        if item.asset_kind != "subject_concept":
            raise ValueError(f"asset library item is not a subject concept: {concept_artifact_id}")
        library = list(state.asset_library)

    timestamp = utc_now_iso()
    output = []
    for candidate in library:
        payload = _model_to_dict(candidate)
        if candidate.asset_kind == "subject_concept" and candidate.subject_id == subject_id:
            payload["selection_status"] = "available"
            payload["updated_at"] = timestamp
        if candidate.artifact_id == concept_artifact_id:
            payload["subject_id"] = subject_id
            payload["selection_status"] = "selected_for_model_generation"
            payload["user_notes"] = note if note is not None else candidate.user_notes
            payload["updated_at"] = timestamp
        output.append(AssetLibraryItem(**payload))
    updated = apply_state_updates(
        state,
        node_name="RuntimeAssetAction",
        updates={"asset_library": output},
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="select_concept_for_subject_generation",
        updated=updated,
        checkpoint_reason="concept_selected_for_subject_generation",
        applied_fields=["asset_library"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "subject_id": subject_id,
            "concept_artifact_id": concept_artifact_id,
            "note": note,
        },
    )


def _select_asset_for_assembly(
    run_dir: Path,
    *,
    state: AgentProjectState,
    action_id: str,
    subject_asset_ids_by_subject: dict[str, str],
    scene_asset_id: str | None,
    scene_concept_image_id: str | None,
    target_render_image_id: str | None,
    placement_hints: list[dict[str, Any]],
    source_turn_id: str | None,
    note: str | None,
    rebuild_plan: bool,
) -> RuntimeAssetActionRecord:
    if not subject_asset_ids_by_subject:
        raise ValueError("subject_asset_ids_by_subject is required")
    for subject_id, asset_id in subject_asset_ids_by_subject.items():
        if not _subject_asset_reference_exists(state, subject_id=subject_id, asset_id=asset_id):
            raise ValueError(f"subject asset not found for assembly selection: {subject_id}:{asset_id}")
    if scene_asset_id and not _scene_asset_reference_exists(state, scene_asset_id):
        raise ValueError(f"scene asset not found for assembly selection: {scene_asset_id}")
    if scene_concept_image_id and not _artifact_or_library_kind_exists(state, scene_concept_image_id, {"scene_concept"}):
        raise ValueError(f"scene concept image not found for assembly selection: {scene_concept_image_id}")
    if target_render_image_id and not _artifact_or_library_kind_exists(state, target_render_image_id, {"target_render"}):
        raise ValueError(f"target render image not found for assembly selection: {target_render_image_id}")

    timestamp = utc_now_iso()
    object_placements = []
    placement_by_subject = {
        str(item.get("subject_id")): item
        for item in placement_hints
        if isinstance(item, dict) and item.get("subject_id")
    }
    for subject_id, asset_id in subject_asset_ids_by_subject.items():
        source_concept_id = _source_concept_for_subject_asset(state, asset_id)
        object_placements.append(
            AssemblyObjectSelection(
                subject_id=subject_id,
                selected_subject_asset_id=asset_id,
                source_concept_image_id=source_concept_id,
                placement_hint=placement_by_subject.get(subject_id, {}),
            )
        )
    selection = AssemblySelection(
        selection_id=f"assembly_selection_{uuid4().hex[:12]}",
        selected_subject_assets=dict(subject_asset_ids_by_subject),
        selected_scene_asset_id=scene_asset_id,
        selected_scene_concept_image_id=scene_concept_image_id,
        selected_target_render_image_id=target_render_image_id,
        object_placements=object_placements,
        source_turn_id=source_turn_id,
        updated_at=timestamp,
        metadata={"note": note, "user_action_id": action_id},
    )
    selected_artifact_ids = set(subject_asset_ids_by_subject.values())
    if scene_asset_id:
        selected_artifact_ids.add(scene_asset_id)
    if scene_concept_image_id:
        selected_artifact_ids.add(scene_concept_image_id)
    if target_render_image_id:
        selected_artifact_ids.add(target_render_image_id)

    library = _ensure_selected_assembly_items(state, selected_artifact_ids, timestamp=timestamp, note=note)
    updated = apply_state_updates(
        state,
        node_name="RuntimeAssetAction",
        updates={
            "asset_library": library,
            "active_assembly_selection": selection,
        },
    )
    return _persist_success(
        run_dir,
        action_id=action_id,
        action_type="select_asset_for_assembly",
        updated=updated,
        checkpoint_reason="assets_selected_for_blender_assembly",
        applied_fields=["asset_library", "active_assembly_selection"],
        rebuild_plan=rebuild_plan,
        result_summary={
            "selection_id": selection.selection_id,
            "selected_subject_assets": dict(subject_asset_ids_by_subject),
            "selected_scene_asset_id": scene_asset_id,
            "selected_target_render_image_id": target_render_image_id,
        },
    )


def _ensure_selected_assembly_items(
    state: AgentProjectState,
    selected_artifact_ids: set[str],
    *,
    timestamp: str,
    note: str | None,
) -> list[AssetLibraryItem]:
    library = list(state.asset_library)
    for artifact_id in selected_artifact_ids:
        if _asset_library_item_in(library, artifact_id) is None:
            artifact = _artifact_by_id(state, artifact_id)
            if artifact is None:
                continue
            kind = asset_kind_for_artifact(artifact)
            if kind is None:
                continue
            library = upsert_asset_library_item(
                library,
                artifact_id=artifact_id,
                asset_kind=kind,
                subject_id=artifact.linked_subject_id,
                scene_id=artifact.linked_scene_id,
                now=timestamp,
            )

    output = []
    for item in library:
        payload = _model_to_dict(item)
        if item.selection_status == "selected_for_assembly" and item.artifact_id not in selected_artifact_ids:
            payload["selection_status"] = "available"
            payload["updated_at"] = timestamp
        if item.artifact_id in selected_artifact_ids:
            payload["selection_status"] = "selected_for_assembly"
            payload["user_notes"] = note if note is not None else item.user_notes
            payload["updated_at"] = timestamp
        output.append(AssetLibraryItem(**payload))
    return output


def _persist_success(
    run_dir: Path,
    *,
    action_id: str,
    action_type: RuntimeAssetActionType,
    updated: AgentProjectState,
    checkpoint_reason: str,
    applied_fields: list[str],
    rebuild_plan: bool,
    result_summary: dict[str, Any],
) -> RuntimeAssetActionRecord:
    updated.updated_at = utc_now_iso()
    _write_json(run_dir / "state.json", _model_to_dict(updated))
    checkpoint = _save_checkpoint(
        run_dir,
        updated,
        reason=checkpoint_reason,
        action_id=action_id,
        applied_fields=applied_fields,
    )
    summary_payload = _read_json(run_dir / "summary.json") or {}
    _append_action_to_summary(summary_payload, checkpoint=checkpoint, action_id=action_id, action_type=action_type)
    _write_json(run_dir / "summary.json", summary_payload)
    _write_json(run_dir / "frontend_status.json", _model_to_dict(build_frontend_status(state=updated, summary=summary_payload)))
    plan_path = None
    if rebuild_plan:
        plan = build_and_save_runtime_dispatch_plan(run_dir)
        plan_path = plan.runtime_plan_json
    return RuntimeAssetActionRecord(
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


def _save_checkpoint(
    run_dir: Path,
    state: AgentProjectState,
    *,
    reason: str,
    action_id: str,
    applied_fields: list[str],
) -> StateCheckpointRecord:
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    return store.save_checkpoint(
        state,
        reason=reason,
        node_name="RuntimeAssetAction",
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={
            "stage": "runtime_asset_action",
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
    action_type: str,
) -> None:
    summary.setdefault("ok", True)
    summary.setdefault("workflow", "runtime-console")
    executed = summary.setdefault("executed_stages", [])
    if "runtime_asset_action" not in executed:
        executed.append("runtime_asset_action")
    summary.setdefault("runtime_asset_action", []).append(
        {
            "action_id": action_id,
            "action_type": action_type,
            "checkpoint_id": checkpoint.checkpoint_id,
        }
    )


def _write_action_summary(run_dir: Path, records: list[RuntimeAssetActionRecord]) -> RuntimeAssetActionSummary:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    summary = RuntimeAssetActionSummary(
        run_dir=str(run_dir),
        generated_at=utc_now_iso(),
        action_log_jsonl=str(_action_log_path(run_dir)),
        total_records=len(records),
        status_counts=counts,
        latest_record=records[-1] if records else None,
    )
    _write_json(_action_summary_path(run_dir), _model_to_dict(summary))
    return summary


def _source_concept_for_subject_asset(state: AgentProjectState, asset_id: str) -> str | None:
    for asset in state.subject_assets:
        if asset.asset_id == asset_id:
            return asset.source_image_id
    return None


def _subject_asset_reference_exists(state: AgentProjectState, *, subject_id: str, asset_id: str) -> bool:
    for asset in state.subject_assets:
        if asset.asset_id == asset_id and asset.subject_id == subject_id:
            return True
    for item in state.asset_library:
        if item.artifact_id == asset_id and item.asset_kind == "subject_model" and item.subject_id == subject_id:
            return True
    artifact = _artifact_by_id(state, asset_id)
    return artifact is not None and artifact.artifact_type == ArtifactType.SUBJECT_3D_ASSET and artifact.linked_subject_id == subject_id


def _scene_asset_reference_exists(state: AgentProjectState, scene_asset_id: str) -> bool:
    if state.scene_asset is not None:
        if state.scene_asset.scene_asset_id == scene_asset_id:
            return True
        if scene_asset_id in state.scene_asset.adapted_artifact_ids:
            return True
    return _artifact_or_library_kind_exists(state, scene_asset_id, {"scene_asset"})


def _artifact_or_library_kind_exists(state: AgentProjectState, artifact_id: str, asset_kinds: set[str]) -> bool:
    artifact_kind = {
        ArtifactType.SCENE_CONCEPT_IMAGE: "scene_concept",
        ArtifactType.FINAL_PREVIEW_IMAGE: "target_render",
        ArtifactType.SCENE_3D_ASSET: "scene_asset",
    }
    for item in state.asset_library:
        if item.artifact_id == artifact_id and item.asset_kind in asset_kinds:
            return True
    artifact = _artifact_by_id(state, artifact_id)
    if artifact is None:
        return False
    return artifact_kind.get(artifact.artifact_type) in asset_kinds


def _artifact_by_id(state: AgentProjectState, artifact_id: str) -> ArtifactRecord | None:
    for artifact in state.artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    return None


def _asset_library_item(state: AgentProjectState, artifact_id: str) -> AssetLibraryItem | None:
    return _asset_library_item_in(state.asset_library, artifact_id)


def _asset_library_item_in(items: list[AssetLibraryItem], artifact_id: str) -> AssetLibraryItem | None:
    for item in items:
        if item.artifact_id == artifact_id:
            return item
    return None


def _replace_item(items: list[AssetLibraryItem], *, artifact_id: str, updates: dict[str, Any]) -> list[AssetLibraryItem]:
    output = []
    found = False
    for item in items:
        if item.artifact_id != artifact_id:
            output.append(item)
            continue
        payload = _model_to_dict(item)
        payload.update(updates)
        output.append(AssetLibraryItem(**payload))
        found = True
    if not found:
        raise ValueError(f"asset library item not found: {artifact_id}")
    return output


def _unique(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        output.append(value)
        seen.add(value)
    return output


def _action_log_path(run_dir: Path) -> Path:
    return run_dir / "runtime_asset_action.jsonl"


def _action_summary_path(run_dir: Path) -> Path:
    return run_dir / "runtime_asset_action_summary.json"


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
