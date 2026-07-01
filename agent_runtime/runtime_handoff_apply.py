"""Apply worker/sub-agent handoff results back into runtime state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.artifacts import FileArtifactStore, utc_now_iso
from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.persistence import FileStateCheckpointStore
from agent_runtime.runtime_asset_actions import (
    add_derived_artifact_link,
    selected_subject_concept_artifact_id,
    upsert_asset_library_item,
)
from agent_runtime.runtime_delegation import RuntimeDelegatedHandoffRecord, read_runtime_handoff_records
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.scene_assets import register_worldmirror_output
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    Asset3DRecord,
    BlenderSceneState,
    ConceptBundle,
    ViewerSceneState,
    WorkflowPhase,
)
from agent_runtime.state_views import apply_state_updates


RuntimeHandoffApplyStatus = Literal["applied", "skipped", "failed"]


class RuntimeConceptImageResult(BaseModel):
    image_path: str
    subject_id: str | None = None
    output_type: Literal["subject_concept", "scene_concept", "target_render"] = "subject_concept"
    requirement_id: str | None = None
    target_id: str | None = None
    artifact_id: str | None = None
    final_preview: bool = False
    copy_into_store: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeSubjectAssetResult(BaseModel):
    glb_path: str
    subject_id: str
    asset_id: str | None = None
    source_image_id: str | None = None
    service: str = "hunyuan3d_2_1"
    job_id: str | None = None
    copy_into_store: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeSceneAssetResult(BaseModel):
    output_dir: str
    scene_asset_id: str | None = None
    source_scene_concept_image_ids: list[str] = Field(default_factory=list)
    source_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeBlenderAssemblyResult(BaseModel):
    blend_path: str
    viewer_scene_path: str
    scene_state_json_path: str | None = None
    preview_image_path: str | None = None
    blender_scene_id: str | None = None
    viewer_scene_id: str | None = None
    copy_into_store: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeHandoffApplyRecord(BaseModel):
    apply_id: str
    handoff_id: str | None = None
    execution_id: str | None = None
    domain_tool_name: str | None = None
    status: RuntimeHandoffApplyStatus
    ok: bool
    created_at: str
    state_json: str
    checkpoint_id: str | None = None
    runtime_plan_json: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    applied_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)


class RuntimeHandoffApplySummary(BaseModel):
    run_dir: str
    generated_at: str
    apply_log_jsonl: str
    total_records: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    latest_record: RuntimeHandoffApplyRecord | None = None
    applied_handoff_ids: list[str] = Field(default_factory=list)


class RuntimeHandoffApplyResult(BaseModel):
    ok: bool
    run_dir: str
    apply_log_jsonl: str
    apply_summary_json: str
    selected_handoff_id: str | None = None
    record: RuntimeHandoffApplyRecord | None = None
    summary: RuntimeHandoffApplySummary
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


APPLIED_STATUSES = {"applied", "skipped"}


def apply_concept_handoff_result(
    run_dir: str | Path,
    *,
    image_results: list[RuntimeConceptImageResult | dict[str, Any]],
    handoff_id: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeHandoffApplyResult:
    """Register concept images produced by a delegated handoff."""

    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for handoff apply: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    records = read_runtime_handoff_apply_records(path)
    applied = _applied_handoff_ids(records)
    handoff = _select_handoff(read_runtime_handoff_records(path), handoff_id=handoff_id, applied=applied)
    if handoff is None:
        summary = _write_apply_summary(path, records)
        return RuntimeHandoffApplyResult(
            ok=True,
            run_dir=str(path),
            apply_log_jsonl=str(_apply_log_path(path)),
            apply_summary_json=str(_apply_summary_path(path)),
            summary=summary,
            message="no_applicable_handoff",
        )

    try:
        normalized = [item if isinstance(item, RuntimeConceptImageResult) else RuntimeConceptImageResult(**item) for item in image_results]
        if not normalized:
            raise ValueError("image_results must not be empty")
        updated, artifacts = _apply_concept_images(path, state=state, image_results=normalized, handoff=handoff)
        updated.updated_at = utc_now_iso()
        _write_json(state_path, _model_to_dict(updated))
        checkpoint = _save_checkpoint(path, updated, handoff=handoff, artifact_ids=[artifact.artifact_id for artifact in artifacts])
        summary_payload = _read_json(path / "summary.json") or {}
        _append_apply_to_summary(summary_payload, handoff=handoff, checkpoint_id=checkpoint.checkpoint_id, artifact_ids=[a.artifact_id for a in artifacts])
        _write_json(path / "summary.json", summary_payload)
        _write_json(path / "frontend_status.json", _model_to_dict(build_frontend_status(state=updated, summary=summary_payload)))
        plan_path = build_and_save_runtime_dispatch_plan(path).runtime_plan_json if rebuild_plan else None
        record = RuntimeHandoffApplyRecord(
            apply_id=f"handoff_apply_{uuid4().hex[:12]}",
            handoff_id=handoff.handoff_id,
            execution_id=handoff.execution_id,
            domain_tool_name=handoff.domain_tool_name,
            status="applied",
            ok=True,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            checkpoint_id=checkpoint.checkpoint_id,
            runtime_plan_json=plan_path,
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            applied_fields=["artifacts", "concept_bundle", "asset_library", "phase"],
            result_summary={
                "artifact_count": len(artifacts),
                "asset_library_count": len(updated.asset_library),
                "next_phase": updated.phase.value,
                "concept_version": updated.concept_bundle.concept_version if updated.concept_bundle is not None else None,
            },
        )
    except Exception as exc:
        record = RuntimeHandoffApplyRecord(
            apply_id=f"handoff_apply_{uuid4().hex[:12]}",
            handoff_id=handoff.handoff_id,
            execution_id=handoff.execution_id,
            domain_tool_name=handoff.domain_tool_name,
            status="failed",
            ok=False,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            issues=["runtime_handoff_apply_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    _append_jsonl(_apply_log_path(path), _model_to_dict(record))
    records.append(record)
    summary = _write_apply_summary(path, records)
    return RuntimeHandoffApplyResult(
        ok=record.ok,
        run_dir=str(path),
        apply_log_jsonl=str(_apply_log_path(path)),
        apply_summary_json=str(_apply_summary_path(path)),
        selected_handoff_id=handoff.handoff_id,
        record=record,
        summary=summary,
        message=record.status,
        issues=list(record.issues),
    )


def apply_subject_asset_handoff_result(
    run_dir: str | Path,
    *,
    asset_results: list[RuntimeSubjectAssetResult | dict[str, Any]],
    handoff_id: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeHandoffApplyResult:
    """Register subject GLBs produced by a delegated handoff."""

    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for handoff apply: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    records = read_runtime_handoff_apply_records(path)
    applied = _applied_handoff_ids(records)
    handoff = _select_handoff(read_runtime_handoff_records(path), handoff_id=handoff_id, applied=applied)
    if handoff is None:
        summary = _write_apply_summary(path, records)
        return RuntimeHandoffApplyResult(
            ok=True,
            run_dir=str(path),
            apply_log_jsonl=str(_apply_log_path(path)),
            apply_summary_json=str(_apply_summary_path(path)),
            summary=summary,
            message="no_applicable_handoff",
        )

    try:
        normalized = [item if isinstance(item, RuntimeSubjectAssetResult) else RuntimeSubjectAssetResult(**item) for item in asset_results]
        if not normalized:
            raise ValueError("asset_results must not be empty")
        updated, artifacts = _apply_subject_assets(path, state=state, asset_results=normalized, handoff=handoff)
        updated.updated_at = utc_now_iso()
        _write_json(state_path, _model_to_dict(updated))
        checkpoint = _save_checkpoint(
            path,
            updated,
            handoff=handoff,
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            node_name="SubjectAssetGenerationExecutor",
        )
        summary_payload = _read_json(path / "summary.json") or {}
        _append_apply_to_summary(summary_payload, handoff=handoff, checkpoint_id=checkpoint.checkpoint_id, artifact_ids=[a.artifact_id for a in artifacts])
        _write_json(path / "summary.json", summary_payload)
        _write_json(path / "frontend_status.json", _model_to_dict(build_frontend_status(state=updated, summary=summary_payload)))
        plan_path = build_and_save_runtime_dispatch_plan(path).runtime_plan_json if rebuild_plan else None
        record = RuntimeHandoffApplyRecord(
            apply_id=f"handoff_apply_{uuid4().hex[:12]}",
            handoff_id=handoff.handoff_id,
            execution_id=handoff.execution_id,
            domain_tool_name=handoff.domain_tool_name,
            status="applied",
            ok=True,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            checkpoint_id=checkpoint.checkpoint_id,
            runtime_plan_json=plan_path,
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            applied_fields=["artifacts", "subject_assets", "asset_library", "phase"],
            result_summary={
                "artifact_count": len(artifacts),
                "asset_library_count": len(updated.asset_library),
                "next_phase": updated.phase.value,
                "subject_asset_count": len(updated.subject_assets),
            },
        )
    except Exception as exc:
        record = RuntimeHandoffApplyRecord(
            apply_id=f"handoff_apply_{uuid4().hex[:12]}",
            handoff_id=handoff.handoff_id,
            execution_id=handoff.execution_id,
            domain_tool_name=handoff.domain_tool_name,
            status="failed",
            ok=False,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            issues=["runtime_handoff_apply_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    _append_jsonl(_apply_log_path(path), _model_to_dict(record))
    records.append(record)
    summary = _write_apply_summary(path, records)
    return RuntimeHandoffApplyResult(
        ok=record.ok,
        run_dir=str(path),
        apply_log_jsonl=str(_apply_log_path(path)),
        apply_summary_json=str(_apply_summary_path(path)),
        selected_handoff_id=handoff.handoff_id,
        record=record,
        summary=summary,
        message=record.status,
        issues=list(record.issues),
    )


def apply_scene_asset_handoff_result(
    run_dir: str | Path,
    *,
    scene_asset_results: list[RuntimeSceneAssetResult | dict[str, Any]],
    handoff_id: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeHandoffApplyResult:
    """Register scene/world outputs produced by a delegated handoff."""

    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for handoff apply: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    records = read_runtime_handoff_apply_records(path)
    applied = _applied_handoff_ids(records)
    handoff = _select_handoff(read_runtime_handoff_records(path), handoff_id=handoff_id, applied=applied)
    if handoff is None:
        summary = _write_apply_summary(path, records)
        return RuntimeHandoffApplyResult(
            ok=True,
            run_dir=str(path),
            apply_log_jsonl=str(_apply_log_path(path)),
            apply_summary_json=str(_apply_summary_path(path)),
            summary=summary,
            message="no_applicable_handoff",
        )

    try:
        normalized = [item if isinstance(item, RuntimeSceneAssetResult) else RuntimeSceneAssetResult(**item) for item in scene_asset_results]
        if not normalized:
            raise ValueError("scene_asset_results must not be empty")
        updated, artifacts = _apply_scene_assets(path, state=state, scene_asset_results=normalized, handoff=handoff)
        updated.updated_at = utc_now_iso()
        _write_json(state_path, _model_to_dict(updated))
        checkpoint = _save_checkpoint(
            path,
            updated,
            handoff=handoff,
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            node_name="SceneAssetGenerationExecutor",
        )
        summary_payload = _read_json(path / "summary.json") or {}
        _append_apply_to_summary(summary_payload, handoff=handoff, checkpoint_id=checkpoint.checkpoint_id, artifact_ids=[a.artifact_id for a in artifacts])
        _write_json(path / "summary.json", summary_payload)
        _write_json(path / "frontend_status.json", _model_to_dict(build_frontend_status(state=updated, summary=summary_payload)))
        plan_path = build_and_save_runtime_dispatch_plan(path).runtime_plan_json if rebuild_plan else None
        record = RuntimeHandoffApplyRecord(
            apply_id=f"handoff_apply_{uuid4().hex[:12]}",
            handoff_id=handoff.handoff_id,
            execution_id=handoff.execution_id,
            domain_tool_name=handoff.domain_tool_name,
            status="applied",
            ok=True,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            checkpoint_id=checkpoint.checkpoint_id,
            runtime_plan_json=plan_path,
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            applied_fields=["artifacts", "scene_asset", "asset_library", "phase"],
            result_summary={
                "artifact_count": len(artifacts),
                "asset_library_count": len(updated.asset_library),
                "next_phase": updated.phase.value,
                "scene_asset_id": updated.scene_asset.scene_asset_id if updated.scene_asset is not None else None,
                "scene_asset_status": updated.scene_asset.status if updated.scene_asset is not None else None,
            },
        )
    except Exception as exc:
        record = RuntimeHandoffApplyRecord(
            apply_id=f"handoff_apply_{uuid4().hex[:12]}",
            handoff_id=handoff.handoff_id,
            execution_id=handoff.execution_id,
            domain_tool_name=handoff.domain_tool_name,
            status="failed",
            ok=False,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            issues=["runtime_handoff_apply_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    _append_jsonl(_apply_log_path(path), _model_to_dict(record))
    records.append(record)
    summary = _write_apply_summary(path, records)
    return RuntimeHandoffApplyResult(
        ok=record.ok,
        run_dir=str(path),
        apply_log_jsonl=str(_apply_log_path(path)),
        apply_summary_json=str(_apply_summary_path(path)),
        selected_handoff_id=handoff.handoff_id,
        record=record,
        summary=summary,
        message=record.status,
        issues=list(record.issues),
    )


def apply_blender_assembly_result(
    run_dir: str | Path,
    *,
    blender_results: list[RuntimeBlenderAssemblyResult | dict[str, Any]],
    handoff_id: str | None = None,
    rebuild_plan: bool = True,
) -> RuntimeHandoffApplyResult:
    """Register Blender/viewer outputs produced by a worker or sub-agent."""

    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for handoff apply: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    records = read_runtime_handoff_apply_records(path)
    applied = _applied_handoff_ids(records)
    handoff = _select_handoff(read_runtime_handoff_records(path), handoff_id=handoff_id, applied=applied) if handoff_id is not None else None

    try:
        normalized = [item if isinstance(item, RuntimeBlenderAssemblyResult) else RuntimeBlenderAssemblyResult(**item) for item in blender_results]
        if not normalized:
            raise ValueError("blender_results must not be empty")
        updated, artifacts = _apply_blender_outputs(path, state=state, blender_results=normalized, handoff=handoff)
        updated.updated_at = utc_now_iso()
        _write_json(state_path, _model_to_dict(updated))
        checkpoint = _save_checkpoint_optional_handoff(
            path,
            updated,
            handoff=handoff,
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            node_name="BlenderAssemblyResultIngestor",
        )
        summary_payload = _read_json(path / "summary.json") or {}
        _append_optional_apply_to_summary(
            summary_payload,
            handoff=handoff,
            checkpoint_id=checkpoint.checkpoint_id,
            artifact_ids=[a.artifact_id for a in artifacts],
            domain_tool_name="blender_assembly_result",
        )
        _write_json(path / "summary.json", summary_payload)
        _write_json(path / "frontend_status.json", _model_to_dict(build_frontend_status(state=updated, summary=summary_payload)))
        plan_path = build_and_save_runtime_dispatch_plan(path).runtime_plan_json if rebuild_plan else None
        record = RuntimeHandoffApplyRecord(
            apply_id=f"handoff_apply_{uuid4().hex[:12]}",
            handoff_id=handoff.handoff_id if handoff is not None else None,
            execution_id=handoff.execution_id if handoff is not None else None,
            domain_tool_name=handoff.domain_tool_name if handoff is not None else "blender_assembly_result",
            status="applied",
            ok=True,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            checkpoint_id=checkpoint.checkpoint_id,
            runtime_plan_json=plan_path,
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            applied_fields=["artifacts", "blender_scene", "viewer_scene", "asset_library", "phase"],
            result_summary={
                "artifact_count": len(artifacts),
                "asset_library_count": len(updated.asset_library),
                "next_phase": updated.phase.value,
                "blender_scene_id": updated.blender_scene.blender_scene_id if updated.blender_scene is not None else None,
                "viewer_scene_id": updated.viewer_scene.viewer_scene_id if updated.viewer_scene is not None else None,
            },
        )
    except Exception as exc:
        record = RuntimeHandoffApplyRecord(
            apply_id=f"handoff_apply_{uuid4().hex[:12]}",
            handoff_id=handoff.handoff_id if handoff is not None else handoff_id,
            execution_id=handoff.execution_id if handoff is not None else None,
            domain_tool_name=handoff.domain_tool_name if handoff is not None else "blender_assembly_result",
            status="failed",
            ok=False,
            created_at=utc_now_iso(),
            state_json=str(state_path),
            issues=["runtime_handoff_apply_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    _append_jsonl(_apply_log_path(path), _model_to_dict(record))
    records.append(record)
    summary = _write_apply_summary(path, records)
    return RuntimeHandoffApplyResult(
        ok=record.ok,
        run_dir=str(path),
        apply_log_jsonl=str(_apply_log_path(path)),
        apply_summary_json=str(_apply_summary_path(path)),
        selected_handoff_id=record.handoff_id,
        record=record,
        summary=summary,
        message=record.status,
        issues=list(record.issues),
    )


def read_runtime_handoff_apply_records(run_dir: str | Path, *, limit: int | None = None) -> list[RuntimeHandoffApplyRecord]:
    path = _apply_log_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return []
    records = [
        RuntimeHandoffApplyRecord(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:] if limit is not None else records


def read_runtime_handoff_apply_summary(run_dir: str | Path) -> dict[str, Any] | None:
    path = _apply_summary_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_concept_images(
    run_dir: Path,
    *,
    state: AgentProjectState,
    image_results: list[RuntimeConceptImageResult],
    handoff: RuntimeDelegatedHandoffRecord,
) -> tuple[AgentProjectState, list[ArtifactRecord]]:
    if handoff.domain_tool_name not in {"generate_concept_images", "regenerate_concept_images"}:
        raise ValueError(f"handoff is not a concept-image job: {handoff.domain_tool_name}")
    if state.concept_bundle is None:
        raise ValueError("state.concept_bundle is required before applying concept image results")
    store = FileArtifactStore(run_dir / "artifacts")
    artifacts = []
    asset_library = list(state.asset_library)
    requirement_by_id = _concept_requirement_by_id(state)
    requirement_artifact_by_id: dict[str, str] = {}
    subject_images = {key: list(value) for key, value in state.concept_bundle.subject_concept_images.items()}
    scene_images = list(state.concept_bundle.scene_concept_image_ids)
    final_preview = state.concept_bundle.final_preview_image_id
    default_subject_id = state.scene_spec.subjects[0].subject_id if state.scene_spec is not None and state.scene_spec.subjects else "subject_001"
    for index, result in enumerate(image_results, start=1):
        output_type = result.output_type
        subject_id = result.subject_id or default_subject_id
        artifact_type = _artifact_type_for_concept_output(output_type)
        artifact = store.register_file(
            result.image_path,
            artifact_type,
            artifact_id=result.artifact_id or f"{output_type}_{uuid4().hex[:12]}",
            semantic_role=_semantic_role_for_concept_output(output_type),
            copy_into_store=result.copy_into_store,
            metadata={
                "stage": "runtime_handoff_apply",
                "handoff_id": handoff.handoff_id,
                "execution_id": handoff.execution_id,
                "output_type": output_type,
                "requirement_id": result.requirement_id,
                "target_id": result.target_id,
                "subject_id": subject_id,
                "image_index": index,
                **result.metadata,
            },
        )
        if output_type == "subject_concept":
            artifact.linked_subject_id = subject_id
        elif output_type in {"scene_concept", "target_render"}:
            artifact.linked_scene_id = result.target_id or (state.scene_spec.scene_id if state.scene_spec is not None else None)
        artifacts.append(artifact)
        requirement = requirement_by_id.get(result.requirement_id or "")
        source_requirement_ids = _string_list(
            result.metadata.get("source_requirement_ids")
            if "source_requirement_ids" in result.metadata
            else requirement.source_requirement_ids if requirement is not None else []
        )
        input_reference_image_ids = _string_list(
            result.metadata.get("input_reference_image_ids")
            if "input_reference_image_ids" in result.metadata
            else requirement.input_reference_image_ids if requirement is not None else []
        )
        source_artifact_ids = _unique(
            [
                *_string_list(result.metadata.get("source_artifact_ids")),
                *_input_image_artifact_ids(state, input_reference_image_ids),
                *[
                    requirement_artifact_by_id[source_id]
                    for source_id in source_requirement_ids
                    if source_id in requirement_artifact_by_id
                ],
            ]
        )
        generation_mode = (
            result.metadata.get("generation_mode")
            or requirement.generation_mode if requirement is not None else None
        )
        asset_library = upsert_asset_library_item(
            asset_library,
            artifact_id=artifact.artifact_id,
            asset_kind=output_type,
            subject_id=subject_id if output_type == "subject_concept" else None,
            scene_id=result.target_id or (state.scene_spec.scene_id if state.scene_spec is not None else None),
            requirement_id=result.requirement_id,
            source_artifact_ids=source_artifact_ids,
            generation_round=state.concept_bundle.concept_version,
            metadata={
                "handoff_id": handoff.handoff_id,
                "execution_id": handoff.execution_id,
                "output_type": output_type,
                "generation_mode": generation_mode,
                "input_reference_image_ids": input_reference_image_ids,
                "source_requirement_ids": source_requirement_ids,
                "quality_bar": requirement.quality_bar if requirement is not None else None,
            },
        )
        for source_artifact_id in source_artifact_ids:
            asset_library = add_derived_artifact_link(
                asset_library,
                source_artifact_id=source_artifact_id,
                derived_artifact_id=artifact.artifact_id,
            )
        if result.requirement_id:
            requirement_artifact_by_id[result.requirement_id] = artifact.artifact_id
        if output_type == "subject_concept":
            subject_images.setdefault(subject_id, []).append(artifact.artifact_id)
            if result.final_preview or final_preview is None:
                final_preview = artifact.artifact_id
        elif output_type == "scene_concept":
            scene_images.append(artifact.artifact_id)
        elif output_type == "target_render":
            final_preview = artifact.artifact_id
    concept_bundle = ConceptBundle(
        concept_version=state.concept_bundle.concept_version,
        final_preview_image_id=final_preview,
        subject_concept_images=subject_images,
        scene_concept_image_ids=scene_images,
        prompt_pack=state.concept_bundle.prompt_pack,
        visual_qa=None,
        approved=False,
        approved_at=None,
    )
    updated = apply_state_updates(
        state,
        node_name="ImageGenerationExecutor",
        updates={
            "artifacts": [*state.artifacts, *artifacts],
            "concept_bundle": concept_bundle,
            "asset_library": asset_library,
            "phase": WorkflowPhase.CONCEPT_REVIEW,
        },
    )
    return updated, artifacts


def _artifact_type_for_concept_output(output_type: str) -> ArtifactType:
    if output_type == "scene_concept":
        return ArtifactType.SCENE_CONCEPT_IMAGE
    if output_type == "target_render":
        return ArtifactType.FINAL_PREVIEW_IMAGE
    return ArtifactType.SUBJECT_CONCEPT_IMAGE


def _semantic_role_for_concept_output(output_type: str) -> str:
    if output_type == "scene_concept":
        return "scene_concept_image"
    if output_type == "target_render":
        return "final_preview_image"
    return "subject_concept_image"


def _concept_requirement_by_id(state: AgentProjectState) -> dict[str, Any]:
    if state.concept_bundle is None or state.concept_bundle.prompt_pack is None:
        return {}
    return {
        requirement.requirement_id: requirement
        for requirement in state.concept_bundle.prompt_pack.image_requirements
    }


def _input_image_artifact_ids(state: AgentProjectState, image_ids: list[str]) -> list[str]:
    by_id = {image.image_id: image.artifact_id for image in state.input_images}
    return [by_id[image_id] for image_id in image_ids if image_id in by_id]


def _asset_library_with_blender_outputs(
    state: AgentProjectState,
    *,
    result_artifacts: list[ArtifactRecord],
    preview_artifact_id: str | None,
):
    source_artifact_ids = _assembly_selection_source_artifact_ids(state)
    asset_library = list(state.asset_library)
    for artifact in result_artifacts:
        if artifact.artifact_type == ArtifactType.BLENDER_FILE:
            asset_library = upsert_asset_library_item(
                asset_library,
                artifact_id=artifact.artifact_id,
                asset_kind="blender_scene",
                scene_id=state.scene_spec.scene_id if state.scene_spec is not None else None,
                source_artifact_ids=source_artifact_ids,
                metadata={"stage": "runtime_handoff_apply", "selection_source": "active_assembly_selection"},
            )
        elif artifact.artifact_type in {ArtifactType.VIEWER_SCENE_GLB, ArtifactType.VIEWER_SCENE_GLTF}:
            asset_library = upsert_asset_library_item(
                asset_library,
                artifact_id=artifact.artifact_id,
                asset_kind="viewer_scene",
                scene_id=state.scene_spec.scene_id if state.scene_spec is not None else None,
                source_artifact_ids=source_artifact_ids,
                metadata={"stage": "runtime_handoff_apply", "selection_source": "active_assembly_selection"},
            )
        elif artifact.artifact_id == preview_artifact_id:
            asset_library = upsert_asset_library_item(
                asset_library,
                artifact_id=artifact.artifact_id,
                asset_kind="target_render",
                scene_id=state.scene_spec.scene_id if state.scene_spec is not None else None,
                source_artifact_ids=source_artifact_ids,
                metadata={"stage": "runtime_handoff_apply", "preview_source": "blender_render"},
            )
        else:
            continue
        for source_artifact_id in source_artifact_ids:
            asset_library = add_derived_artifact_link(
                asset_library,
                source_artifact_id=source_artifact_id,
                derived_artifact_id=artifact.artifact_id,
            )
    return asset_library


def _assembly_selection_source_artifact_ids(state: AgentProjectState) -> list[str]:
    selection = state.active_assembly_selection
    if selection is None:
        source_ids = []
        source_ids.extend(asset.asset_id for asset in state.subject_assets if asset.asset_id)
        if state.scene_asset is not None:
            source_ids.extend(state.scene_asset.adapted_artifact_ids)
        return _unique(source_ids)
    source_ids = list(selection.selected_subject_assets.values())
    if selection.selected_scene_asset_id:
        source_ids.append(selection.selected_scene_asset_id)
    if selection.selected_scene_concept_image_id:
        source_ids.append(selection.selected_scene_concept_image_id)
    if selection.selected_target_render_image_id:
        source_ids.append(selection.selected_target_render_image_id)
    for item in selection.object_placements:
        if item.source_concept_image_id:
            source_ids.append(item.source_concept_image_id)
    return _unique(source_ids)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _unique(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        output.append(value)
        seen.add(value)
    return output


def _apply_subject_assets(
    run_dir: Path,
    *,
    state: AgentProjectState,
    asset_results: list[RuntimeSubjectAssetResult],
    handoff: RuntimeDelegatedHandoffRecord,
) -> tuple[AgentProjectState, list[ArtifactRecord]]:
    if handoff.domain_tool_name != "build_subject_asset":
        raise ValueError(f"handoff is not a subject-asset job: {handoff.domain_tool_name}")
    store = FileArtifactStore(run_dir / "artifacts")
    artifacts = []
    assets_by_id = {asset.asset_id: asset for asset in state.subject_assets}
    asset_library = list(state.asset_library)
    subject_prompt_images = state.concept_bundle.subject_concept_images if state.concept_bundle is not None else {}
    for result in asset_results:
        source_image_id = result.source_image_id or selected_subject_concept_artifact_id(state, result.subject_id)
        if source_image_id is None:
            source_image_id = (subject_prompt_images.get(result.subject_id) or ["manual_source"])[-1]
        asset_id = result.asset_id or f"asset_{result.subject_id}_{uuid4().hex[:8]}"
        artifact = store.register_file(
            result.glb_path,
            ArtifactType.SUBJECT_3D_ASSET,
            artifact_id=asset_id,
            semantic_role="subject_3d_asset",
            copy_into_store=result.copy_into_store,
            metadata={
                "stage": "runtime_handoff_apply",
                "handoff_id": handoff.handoff_id,
                "execution_id": handoff.execution_id,
                "subject_id": result.subject_id,
                **result.metadata,
            },
        )
        artifact.linked_subject_id = result.subject_id
        artifacts.append(artifact)
        asset_library = upsert_asset_library_item(
            asset_library,
            artifact_id=artifact.artifact_id,
            asset_kind="subject_model",
            subject_id=result.subject_id,
            source_artifact_ids=[source_image_id] if source_image_id else [],
            metadata={
                "handoff_id": handoff.handoff_id,
                "execution_id": handoff.execution_id,
                "service": result.service,
                "job_id": result.job_id or handoff.job_id,
            },
        )
        if source_image_id:
            asset_library = add_derived_artifact_link(
                asset_library,
                source_artifact_id=source_image_id,
                derived_artifact_id=artifact.artifact_id,
            )
        assets_by_id[asset_id] = Asset3DRecord(
            asset_id=asset_id,
            subject_id=result.subject_id,
            source_image_id=source_image_id,
            service=result.service,
            job_id=result.job_id or handoff.job_id,
            glb_uri=artifact.uri,
            status="succeeded",
            generation_params={
                "runtime_handoff_id": handoff.handoff_id,
                "runtime_execution_id": handoff.execution_id,
                **result.metadata,
            },
        )
    updated = apply_state_updates(
        state,
        node_name="SubjectAssetGenerationExecutor",
        updates={
            "artifacts": [*state.artifacts, *artifacts],
            "subject_assets": list(assets_by_id.values()),
            "asset_library": asset_library,
            "phase": WorkflowPhase.SUBJECT_ASSET_QA,
        },
    )
    return updated, artifacts


def _apply_scene_assets(
    run_dir: Path,
    *,
    state: AgentProjectState,
    scene_asset_results: list[RuntimeSceneAssetResult],
    handoff: RuntimeDelegatedHandoffRecord,
) -> tuple[AgentProjectState, list[ArtifactRecord]]:
    if handoff.domain_tool_name != "build_scene_asset":
        raise ValueError(f"handoff is not a scene-asset job: {handoff.domain_tool_name}")
    store = FileArtifactStore(run_dir / "artifacts")
    updated = state
    new_artifacts: list[ArtifactRecord] = []
    for index, result in enumerate(scene_asset_results, start=1):
        before = {artifact.artifact_id for artifact in updated.artifacts}
        scene_asset_id = result.scene_asset_id or f"scene_asset_{uuid4().hex[:8]}"
        source_prompt = result.source_prompt
        if source_prompt is None and updated.concept_bundle is not None and updated.concept_bundle.prompt_pack is not None:
            prompt_pack = updated.concept_bundle.prompt_pack
            source_prompt = prompt_pack.scene_prompts[0] if prompt_pack.scene_prompts else prompt_pack.final_preview_prompt
        summary, updated = register_worldmirror_output(
            state=updated,
            artifact_store=store,
            output_dir=result.output_dir,
            scene_asset_id=scene_asset_id,
            source_scene_concept_image_ids=result.source_scene_concept_image_ids,
            source_prompt=source_prompt,
        )
        if summary.status == "failed":
            raise ValueError(";".join(summary.issues) or "scene asset output could not be adapted")
        after_artifacts = [artifact for artifact in updated.artifacts if artifact.artifact_id not in before]
        for artifact in after_artifacts:
            artifact.metadata.update(
                {
                    "handoff_id": handoff.handoff_id,
                    "execution_id": handoff.execution_id,
                    "scene_asset_result_index": index,
                    **result.metadata,
                }
            )
            artifact.linked_scene_id = updated.scene_spec.scene_id if updated.scene_spec is not None else None
        new_artifacts.extend(after_artifacts)
        asset_library = list(updated.asset_library)
        for artifact in after_artifacts:
            if updated.scene_asset is not None and artifact.artifact_id not in updated.scene_asset.adapted_artifact_ids:
                continue
            asset_library = upsert_asset_library_item(
                asset_library,
                artifact_id=artifact.artifact_id,
                asset_kind="scene_asset",
                scene_id=updated.scene_spec.scene_id if updated.scene_spec is not None else scene_asset_id,
                source_artifact_ids=result.source_scene_concept_image_ids,
                metadata={
                    "handoff_id": handoff.handoff_id,
                    "execution_id": handoff.execution_id,
                    "scene_asset_id": scene_asset_id,
                    "source_prompt": source_prompt,
                },
            )
            for source_artifact_id in result.source_scene_concept_image_ids:
                asset_library = add_derived_artifact_link(
                    asset_library,
                    source_artifact_id=source_artifact_id,
                    derived_artifact_id=artifact.artifact_id,
                )
        updated = apply_state_updates(
            updated,
            node_name="SceneAssetAdapter",
            updates={"asset_library": asset_library},
        )
    updated = apply_state_updates(
        updated,
        node_name="SceneAssetGenerationExecutor",
        updates={"phase": WorkflowPhase.SCENE_ASSET_ADAPTATION},
    )
    return updated, new_artifacts


def _apply_blender_outputs(
    run_dir: Path,
    *,
    state: AgentProjectState,
    blender_results: list[RuntimeBlenderAssemblyResult],
    handoff: RuntimeDelegatedHandoffRecord | None,
) -> tuple[AgentProjectState, list[ArtifactRecord]]:
    store = FileArtifactStore(run_dir / "artifacts")
    updated = state
    artifacts: list[ArtifactRecord] = []
    for index, result in enumerate(blender_results, start=1):
        result_artifacts: list[ArtifactRecord] = []
        handoff_metadata = {
            "stage": "runtime_handoff_apply",
            "handoff_id": handoff.handoff_id if handoff is not None else None,
            "execution_id": handoff.execution_id if handoff is not None else None,
            "blender_result_index": index,
            **result.metadata,
        }
        blend_artifact = store.register_file(
            result.blend_path,
            ArtifactType.BLENDER_FILE,
            artifact_id=f"blend_file_{uuid4().hex[:12]}",
            semantic_role="blender_file",
            copy_into_store=result.copy_into_store,
            metadata=handoff_metadata,
        )
        viewer_glb_artifact = store.register_file(
            result.viewer_scene_path,
            ArtifactType.VIEWER_SCENE_GLB,
            artifact_id=f"viewer_scene_glb_{uuid4().hex[:12]}",
            semantic_role="viewer_scene_glb",
            copy_into_store=result.copy_into_store,
            metadata=handoff_metadata,
        )
        result_artifacts.extend([blend_artifact, viewer_glb_artifact])
        preview_artifact = None
        if result.preview_image_path:
            preview_artifact = store.register_file(
                result.preview_image_path,
                ArtifactType.BLENDER_PREVIEW_RENDER,
                artifact_id=f"blender_preview_{uuid4().hex[:12]}",
                semantic_role="blender_preview_render",
                copy_into_store=result.copy_into_store,
                metadata=handoff_metadata,
            )
            result_artifacts.append(preview_artifact)
        viewer_state_artifact = None
        viewer_scene = ViewerSceneState(
            viewer_scene_id=result.viewer_scene_id or Path(result.viewer_scene_path).stem or f"viewer_scene_{index:03d}",
            source_blend_version_id=blend_artifact.artifact_id,
            viewer_scene_artifact_id=viewer_glb_artifact.artifact_id,
            viewer_scene_path=viewer_glb_artifact.uri,
            source_blend_path=blend_artifact.uri,
            last_exported_at=utc_now_iso(),
        )
        if result.scene_state_json_path:
            viewer_state_artifact = store.register_file(
                result.scene_state_json_path,
                ArtifactType.VIEWER_SCENE_STATE_JSON,
                artifact_id=f"viewer_scene_state_{uuid4().hex[:12]}",
                semantic_role="viewer_scene_state_json",
                copy_into_store=result.copy_into_store,
                metadata=handoff_metadata,
            )
            result_artifacts.append(viewer_state_artifact)
            viewer_scene = _viewer_scene_from_json(
                result.scene_state_json_path,
                fallback=viewer_scene,
                viewer_glb_artifact_id=viewer_glb_artifact.artifact_id,
                viewer_state_artifact_id=viewer_state_artifact.artifact_id,
                viewer_scene_path=viewer_glb_artifact.uri,
                source_blend_path=blend_artifact.uri,
            )
        blender_scene = BlenderSceneState(
            blender_scene_id=result.blender_scene_id or Path(result.blend_path).stem or f"blender_scene_{index:03d}",
            blend_file_artifact_id=blend_artifact.artifact_id,
            preview_image_id=preview_artifact.artifact_id if preview_artifact is not None else None,
            scene_asset_id=updated.scene_asset.scene_asset_id if updated.scene_asset is not None else None,
            last_synced_at=utc_now_iso(),
        )
        updated = apply_state_updates(
            updated,
            node_name="ImageGenerationExecutor",
            updates={"artifacts": [*updated.artifacts, *result_artifacts]},
        )
        updated = apply_state_updates(
            updated,
            node_name="SceneStateSynchronizer",
            updates={"blender_scene": blender_scene},
        )
        updated = apply_state_updates(
            updated,
            node_name="ViewerSyncService",
            updates={
                "viewer_scene": viewer_scene,
                "phase": WorkflowPhase.BLENDER_PREVIEW,
            },
        )
        updated = apply_state_updates(
            updated,
            node_name="BlenderAssemblyResultIngestor",
            updates={
                "asset_library": _asset_library_with_blender_outputs(
                    updated,
                    result_artifacts=result_artifacts,
                    preview_artifact_id=preview_artifact.artifact_id if preview_artifact is not None else None,
                )
            },
        )
        artifacts.extend(result_artifacts)
    return updated, artifacts


def _viewer_scene_from_json(
    path: str | Path,
    *,
    fallback: ViewerSceneState,
    viewer_glb_artifact_id: str,
    viewer_state_artifact_id: str,
    viewer_scene_path: str,
    source_blend_path: str,
) -> ViewerSceneState:
    try:
        payload = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("scene_state JSON root is not an object")
        payload.setdefault("viewer_scene_id", fallback.viewer_scene_id)
        payload["viewer_scene_artifact_id"] = viewer_glb_artifact_id
        payload["viewer_state_artifact_id"] = viewer_state_artifact_id
        payload["viewer_scene_path"] = viewer_scene_path
        payload["source_blend_path"] = source_blend_path
        payload.setdefault("last_exported_at", utc_now_iso())
        return ViewerSceneState(**payload)
    except Exception:
        fallback.viewer_state_artifact_id = viewer_state_artifact_id
        return fallback


def _select_handoff(
    records: list[RuntimeDelegatedHandoffRecord],
    *,
    handoff_id: str | None,
    applied: set[str],
) -> RuntimeDelegatedHandoffRecord | None:
    for record in records:
        if record.status != "planned":
            continue
        if record.handoff_id in applied:
            continue
        if handoff_id is None or record.handoff_id == handoff_id:
            return record
    return None


def _save_checkpoint(
    run_dir: Path,
    state: AgentProjectState,
    *,
    handoff: RuntimeDelegatedHandoffRecord,
    artifact_ids: list[str],
    node_name: str = "ImageGenerationExecutor",
):
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    return store.save_checkpoint(
        state,
        reason="runtime_handoff_apply",
        node_name=node_name,
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={
            "stage": "runtime_handoff_apply",
            "handoff_id": handoff.handoff_id,
            "execution_id": handoff.execution_id,
            "artifact_ids": artifact_ids,
        },
    )


def _save_checkpoint_optional_handoff(
    run_dir: Path,
    state: AgentProjectState,
    *,
    handoff: RuntimeDelegatedHandoffRecord | None,
    artifact_ids: list[str],
    node_name: str,
):
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    return store.save_checkpoint(
        state,
        reason="runtime_handoff_apply",
        node_name=node_name,
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={
            "stage": "runtime_handoff_apply",
            "handoff_id": handoff.handoff_id if handoff is not None else None,
            "execution_id": handoff.execution_id if handoff is not None else None,
            "artifact_ids": artifact_ids,
        },
    )


def _append_apply_to_summary(summary: dict[str, Any], *, handoff: RuntimeDelegatedHandoffRecord, checkpoint_id: str, artifact_ids: list[str]) -> None:
    summary.setdefault("ok", True)
    summary.setdefault("workflow", "runtime-console")
    executed = summary.setdefault("executed_stages", [])
    if "runtime_handoff_apply" not in executed:
        executed.append("runtime_handoff_apply")
    summary.setdefault("runtime_handoff_apply", []).append(
        {
            "handoff_id": handoff.handoff_id,
            "execution_id": handoff.execution_id,
            "domain_tool_name": handoff.domain_tool_name,
            "checkpoint_id": checkpoint_id,
            "artifact_ids": artifact_ids,
        }
    )


def _append_optional_apply_to_summary(
    summary: dict[str, Any],
    *,
    handoff: RuntimeDelegatedHandoffRecord | None,
    checkpoint_id: str,
    artifact_ids: list[str],
    domain_tool_name: str,
) -> None:
    summary.setdefault("ok", True)
    summary.setdefault("workflow", "runtime-console")
    executed = summary.setdefault("executed_stages", [])
    if "runtime_handoff_apply" not in executed:
        executed.append("runtime_handoff_apply")
    summary.setdefault("runtime_handoff_apply", []).append(
        {
            "handoff_id": handoff.handoff_id if handoff is not None else None,
            "execution_id": handoff.execution_id if handoff is not None else None,
            "domain_tool_name": handoff.domain_tool_name if handoff is not None else domain_tool_name,
            "checkpoint_id": checkpoint_id,
            "artifact_ids": artifact_ids,
        }
    )


def _write_apply_summary(run_dir: Path, records: list[RuntimeHandoffApplyRecord]) -> RuntimeHandoffApplySummary:
    counts: dict[str, int] = {}
    applied = []
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        if record.status in APPLIED_STATUSES and record.handoff_id:
            applied.append(record.handoff_id)
    summary = RuntimeHandoffApplySummary(
        run_dir=str(run_dir),
        generated_at=utc_now_iso(),
        apply_log_jsonl=str(_apply_log_path(run_dir)),
        total_records=len(records),
        status_counts=counts,
        latest_record=records[-1] if records else None,
        applied_handoff_ids=applied,
    )
    _write_json(_apply_summary_path(run_dir), _model_to_dict(summary))
    return summary


def _applied_handoff_ids(records: list[RuntimeHandoffApplyRecord]) -> set[str]:
    return {record.handoff_id for record in records if record.handoff_id and record.status in APPLIED_STATUSES}


def _apply_log_path(run_dir: Path) -> Path:
    return run_dir / "runtime_handoff_apply.jsonl"


def _apply_summary_path(run_dir: Path) -> Path:
    return run_dir / "runtime_handoff_apply_summary.json"


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
