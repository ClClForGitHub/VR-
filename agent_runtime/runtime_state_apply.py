"""Apply validated runtime LLM candidates to AgentProjectState.

Runtime execution records prompts, provider results, and parsed candidates.
This module is the controlled mutation boundary: only supported node outputs
may update the authoritative state, and every successful update is checkpointed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.agent_prompts import (
    BlenderAssemblyPlan,
    BlenderEditRouterOutput,
    ConceptPromptPlannerOutput,
    FeedbackPatchParserOutput,
    ReferenceBindingValidatorOutput,
    RegenerationRouterOutput,
)
from agent_runtime.artifacts import utc_now_iso
from agent_runtime.concept_planning import apply_concept_prompt_planner_output
from agent_runtime.domain_tools import allowed_tool_names
from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.persistence import FileStateCheckpointStore, StateCheckpointRecord
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.runtime_execution import RuntimeJobExecutionRecord, read_runtime_execution_records
from agent_runtime.state import (
    AgentProjectState,
    ArtifactType,
    BlenderObjectRecord,
    PendingAction,
    ReferenceBinding,
    ReviewPatch,
    SceneSpec,
    TransformSpec,
    WorkflowPhase,
)
from agent_runtime.state_views import apply_state_updates


RuntimeApplyStatus = Literal["applied", "skipped", "blocked", "failed"]


class RuntimeStateApplyRecord(BaseModel):
    apply_id: str
    execution_id: str | None = None
    job_id: str | None = None
    node_name: str | None = None
    status: RuntimeApplyStatus
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


class RuntimeStateApplySummary(BaseModel):
    run_dir: str
    generated_at: str
    apply_log_jsonl: str
    total_records: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    latest_record: RuntimeStateApplyRecord | None = None
    applied_execution_ids: list[str] = Field(default_factory=list)


class RuntimeStateApplyResult(BaseModel):
    ok: bool
    run_dir: str
    state_json: str
    apply_log_jsonl: str
    apply_summary_json: str
    selected_execution_id: str | None = None
    record: RuntimeStateApplyRecord | None = None
    summary: RuntimeStateApplySummary
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


APPLIED_STATUSES = {"applied", "blocked", "skipped"}


def apply_next_runtime_candidate(
    run_dir: str | Path,
    *,
    rebuild_plan: bool = True,
) -> RuntimeStateApplyResult:
    """Apply the next unapplied parsed candidate from runtime execution output."""

    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for runtime state apply: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    apply_records = read_runtime_apply_records(path)
    applied_execution_ids = _applied_execution_ids(apply_records)
    execution_records = read_runtime_execution_records(path)
    selected = _select_candidate_execution(execution_records, applied_execution_ids)
    if selected is None:
        summary = _write_apply_summary(path, apply_records)
        return RuntimeStateApplyResult(
            ok=True,
            run_dir=str(path),
            state_json=str(state_path),
            apply_log_jsonl=str(_apply_log_path(path)),
            apply_summary_json=str(_apply_summary_path(path)),
            summary=summary,
            message="no_unapplied_runtime_candidate",
        )

    record = _apply_execution_candidate(
        run_dir=path,
        state=state,
        execution=selected,
        rebuild_plan=rebuild_plan,
    )
    _append_jsonl(_apply_log_path(path), _model_to_dict(record))
    apply_records.append(record)
    summary = _write_apply_summary(path, apply_records)
    return RuntimeStateApplyResult(
        ok=record.ok,
        run_dir=str(path),
        state_json=str(state_path),
        apply_log_jsonl=str(_apply_log_path(path)),
        apply_summary_json=str(_apply_summary_path(path)),
        selected_execution_id=selected.execution_id,
        record=record,
        summary=summary,
        message=record.status,
        issues=list(record.issues),
    )


def read_runtime_apply_records(run_dir: str | Path, *, limit: int | None = None) -> list[RuntimeStateApplyRecord]:
    path = _apply_log_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return []
    records = [
        RuntimeStateApplyRecord(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:] if limit is not None else records


def read_runtime_apply_summary(run_dir: str | Path) -> dict[str, Any] | None:
    path = _apply_summary_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_execution_candidate(
    *,
    run_dir: Path,
    state: AgentProjectState,
    execution: RuntimeJobExecutionRecord,
    rebuild_plan: bool,
) -> RuntimeStateApplyRecord:
    common = _record_common(run_dir=run_dir, execution=execution)
    if not execution.output_json:
        return RuntimeStateApplyRecord(
            **common,
            status="skipped",
            ok=True,
            issues=["execution_has_no_output_json"],
        )
    output_path = Path(execution.output_json).expanduser().resolve()
    if not output_path.exists() or not _is_relative_to(output_path, run_dir):
        return RuntimeStateApplyRecord(
            **common,
            status="failed",
            ok=False,
            issues=["execution_output_json_missing_or_outside_run"],
            error=str(output_path),
        )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    llm_result = payload.get("llm_result") if isinstance(payload, dict) else None
    parsed = llm_result.get("parsed_output") if isinstance(llm_result, dict) else None
    if parsed is None:
        return RuntimeStateApplyRecord(
            **common,
            status="skipped",
            ok=True,
            issues=["execution_has_no_parsed_output"],
        )

    try:
        updated, applied_fields, result_summary = _apply_node_output(
            state=state,
            node_name=execution.node_name,
            parsed_output=parsed,
        )
    except Exception as exc:
        return RuntimeStateApplyRecord(
            **common,
            status="failed",
            ok=False,
            issues=["runtime_state_apply_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    updated.updated_at = utc_now_iso()
    _write_json(run_dir / "state.json", _model_to_dict(updated))
    checkpoint = _save_checkpoint(run_dir, updated, execution=execution, applied_fields=applied_fields)
    summary_payload = _read_json(run_dir / "summary.json") or {}
    _append_apply_to_summary(summary_payload, checkpoint=checkpoint, execution=execution)
    _write_json(run_dir / "summary.json", summary_payload)
    _write_json(run_dir / "frontend_status.json", _model_to_dict(build_frontend_status(state=updated, summary=summary_payload)))
    plan_path = None
    if rebuild_plan:
        plan = build_and_save_runtime_dispatch_plan(run_dir)
        plan_path = plan.runtime_plan_json

    return RuntimeStateApplyRecord(
        **common,
        status="applied",
        ok=True,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_uri=checkpoint.state_snapshot_uri,
        runtime_plan_json=plan_path,
        applied_fields=applied_fields,
        result_summary=result_summary,
    )


def _apply_node_output(
    *,
    state: AgentProjectState,
    node_name: str | None,
    parsed_output: dict[str, Any],
) -> tuple[AgentProjectState, list[str], dict[str, Any]]:
    if node_name == "ReferenceBindingValidator":
        output = ReferenceBindingValidatorOutput(**parsed_output)
        clarification_blocks_flow = output.requires_clarification and bool(state.input_images or output.valid_bindings)
        if clarification_blocks_flow:
            raise ValueError(f"ReferenceBindingValidator output requires clarification: {output.open_questions or output.issues}")
        bindings = [plan.to_reference_binding(index=index) for index, plan in enumerate(output.valid_bindings, start=1)]
        updated = apply_state_updates(
            state,
            node_name="ReferenceBindingValidator",
            updates={"reference_bindings": _merge_reference_bindings(state.reference_bindings, bindings)},
        )
        return updated, ["reference_bindings"], {
            "binding_count": len(bindings),
            "nonblocking_issue_count": len(output.issues),
            "nonblocking_open_question_count": len(output.open_questions),
            "ignored_text_only_clarification": bool(output.requires_clarification and not clarification_blocks_flow),
        }

    if node_name == "SceneSpecCompiler":
        scene_spec = SceneSpec(**parsed_output)
        original_open_questions = list(scene_spec.open_questions)
        blocking_open_questions = [
            question
            for question in original_open_questions
            if not _is_nonblocking_identity_research_question(question)
        ]
        if blocking_open_questions != original_open_questions:
            scene_spec = scene_spec.model_copy(update={"open_questions": blocking_open_questions})
        next_phase = WorkflowPhase.SCENE_SPEC_DRAFT if scene_spec.open_questions else WorkflowPhase.SCENE_SPEC_READY
        updated = apply_state_updates(
            state,
            node_name="SceneSpecCompiler",
            updates={"scene_spec": scene_spec, "phase": next_phase},
        )
        return updated, ["scene_spec", "phase"], {
            "scene_id": scene_spec.scene_id,
            "subject_count": len(scene_spec.subjects),
            "open_question_count": len(scene_spec.open_questions),
            "nonblocking_identity_research_question_count": len(original_open_questions) - len(blocking_open_questions),
            "next_phase": next_phase.value,
        }

    if node_name == "ConceptPromptPlanner":
        result, updated = apply_concept_prompt_planner_output(
            state=state,
            planner_output=ConceptPromptPlannerOutput(**parsed_output),
        )
        if not result.ok:
            raise ValueError(";".join(result.issues) or "ConceptPromptPlanner output could not be applied")
        return updated, ["concept_bundle", "phase"], {
            "concept_version": result.concept_version,
            "next_phase": result.next_phase.value if result.next_phase else None,
        }

    if node_name == "FeedbackPatchParser":
        output = FeedbackPatchParserOutput(**parsed_output)
        if output.requires_clarification or output.clarification_question:
            pending = _clarification_pending_action(
                state=state,
                node_name="FeedbackPatchParser",
                question=output.clarification_question,
                payload={"patch_count": len(output.patches)},
            )
            updated = apply_state_updates(
                state,
                node_name="FeedbackPatchParser",
                updates={"pending_action": pending},
            )
            return updated, ["pending_action"], {
                "requires_clarification": True,
                "clarification_question": output.clarification_question,
            }
        if not output.patches:
            raise ValueError("FeedbackPatchParser output did not contain patches or clarification")
        updated = apply_state_updates(
            state,
            node_name="FeedbackPatchParser",
            updates={
                "review_patches": _merge_review_patches(state.review_patches, output.patches),
                "phase": WorkflowPhase.CONCEPT_REVIEW,
            },
        )
        return updated, ["review_patches", "phase"], {
            "patch_ids": [patch.patch_id for patch in output.patches],
            "patch_count": len(output.patches),
            "next_phase": WorkflowPhase.CONCEPT_REVIEW.value,
        }

    if node_name == "RegenerationRouter":
        output = RegenerationRouterOutput(**parsed_output)
        if output.route == "ask_user":
            pending = _clarification_pending_action(
                state=state,
                node_name="RegenerationRouter",
                question=output.reason,
                payload={
                    "route": output.route,
                    "affected_artifact_ids": list(output.affected_artifact_ids),
                    "next_phase": output.next_phase.value,
                },
            )
            updated = apply_state_updates(
                state,
                node_name="RegenerationRouter",
                updates={"pending_action": pending},
            )
            return updated, ["pending_action"], {
                "route": output.route,
                "next_phase": output.next_phase.value,
                "reason": output.reason,
            }
        updates: dict[str, Any] = {}
        applied_fields: list[str] = []
        # For the normal concept-regeneration path, keep CONCEPT_REVIEW so the
        # existing controller can continue the planned
        # RegenerationRouter -> ConceptPromptPlanner -> regenerate_concept_images
        # sequence. Other routes intentionally move to their requested phase.
        if output.route != "regenerate_concept" and output.next_phase != state.phase:
            updates["phase"] = output.next_phase
            applied_fields.append("phase")
        updated = (
            apply_state_updates(state, node_name="RegenerationRouter", updates=updates)
            if updates
            else state
        )
        return updated, applied_fields, {
            "route": output.route,
            "next_phase": output.next_phase.value,
            "reason": output.reason,
            "affected_artifact_ids": list(output.affected_artifact_ids),
        }

    if node_name == "BlenderAssemblyPlanner":
        output = BlenderAssemblyPlan(**parsed_output)
        updates = {
            "blender_assembly_plan": output,
            "phase": WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        }
        applied_fields = ["blender_assembly_plan"]
        if state.phase != WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION:
            applied_fields.append("phase")
        updated = apply_state_updates(state, node_name="BlenderAssemblyPlanner", updates=updates)
        return updated, applied_fields, {
            "plan_id": output.plan_id,
            "placement_plan_count": len(output.placement_plans),
            "scale_estimate_count": len(output.scale_estimates),
            "has_camera_plan": output.camera_plan is not None,
            "has_lighting_plan": output.lighting_plan is not None,
            "has_render_plan": output.render_plan is not None,
        }

    if node_name == "BlenderEditRouter":
        output = BlenderEditRouterOutput(**parsed_output)
        _validate_blender_edit_tool_calls(output)
        working_state, hydrated_summary = _ensure_blender_scene_objects_for_edit(state, output)
        routed_patches = _patches_with_blender_edit_plan(output)
        updates = {}
        applied_fields = []
        if hydrated_summary:
            updates["blender_scene"] = working_state.blender_scene
            applied_fields.append("blender_scene")
        if routed_patches:
            updates["review_patches"] = _merge_review_patches(working_state.review_patches, routed_patches)
            applied_fields.append("review_patches")
        if output.route == "ask_user":
            updates["pending_action"] = _clarification_pending_action(
                state=working_state,
                node_name="BlenderEditRouter",
                question=output.reason,
                payload={
                    "route": output.route,
                    "allowed_domain_tool_names": list(output.allowed_domain_tool_names),
                },
            )
            applied_fields.append("pending_action")
        else:
            next_phase = _next_phase_for_blender_edit_route(output.route)
            if next_phase != working_state.phase:
                updates["phase"] = next_phase
                applied_fields.append("phase")
        if not updates:
            # A pure edit route can still be a routing-only checkpoint when the
            # router only reports intent/allowed tools and has no concrete
            # patches or executable domain-tool calls to store yet.
            updated = working_state
        else:
            updated = apply_state_updates(working_state, node_name="BlenderEditRouter", updates=updates)
        return updated, applied_fields, {
            "route": output.route,
            "reason": output.reason,
            "patch_ids": [patch.patch_id for patch in routed_patches],
            "allowed_domain_tool_names": list(output.allowed_domain_tool_names),
            "domain_tool_calls": [_model_to_dict(call) for call in output.domain_tool_calls],
            "next_phase": _phase_value(updates.get("phase") or working_state.phase),
            **({"hydrated_blender_scene": hydrated_summary} if hydrated_summary else {}),
        }

    raise ValueError(f"unsupported runtime state apply node: {node_name}")


def _merge_reference_bindings(existing: list[ReferenceBinding], new_bindings: list[ReferenceBinding]) -> list[ReferenceBinding]:
    merged: dict[tuple[str, str, str, str | None], ReferenceBinding] = {
        (binding.image_id, binding.target_type, binding.usage, binding.target_id): binding
        for binding in existing
    }
    for binding in new_bindings:
        merged[(binding.image_id, binding.target_type, binding.usage, binding.target_id)] = binding
    return list(merged.values())


def _merge_review_patches(existing: list[ReviewPatch], new_patches: list[ReviewPatch]) -> list[ReviewPatch]:
    merged = {patch.patch_id: patch for patch in existing}
    for patch in new_patches:
        merged[patch.patch_id] = patch
    return list(merged.values())


def _clarification_pending_action(
    *,
    state: AgentProjectState,
    node_name: str,
    question: str | None,
    payload: dict[str, Any] | None = None,
) -> PendingAction:
    return PendingAction(
        action_id=f"pending_{uuid4().hex[:12]}",
        phase=state.phase,
        action_type="ask_user_clarification",
        payload={
            "node_name": node_name,
            "question": question or "请补充需要确认的信息。",
            **(payload or {}),
        },
    )


def _next_phase_for_blender_edit_route(route: str) -> WorkflowPhase:
    return {
        "pure_blender_edit": WorkflowPhase.BLENDER_EDIT,
        "redo_subject": WorkflowPhase.SUBJECT_ASSET_GENERATION,
        "redo_scene": WorkflowPhase.SCENE_ASSET_GENERATION,
        "return_to_concept": WorkflowPhase.CONCEPT_REVIEW,
    }.get(route, WorkflowPhase.BLENDER_EDIT)


def _phase_value(value: Any) -> str:
    return value.value if isinstance(value, WorkflowPhase) else str(value)


def _validate_blender_edit_tool_calls(output: BlenderEditRouterOutput) -> None:
    allowed = set(allowed_tool_names(WorkflowPhase.BLENDER_EDIT))
    invalid = [
        call.domain_tool_name
        for call in output.domain_tool_calls
        if call.domain_tool_name not in allowed
    ]
    if invalid:
        raise ValueError(f"BlenderEditRouter planned tools not allowed in BLENDER_EDIT: {invalid}")


def _is_nonblocking_identity_research_question(question: str) -> bool:
    lowered = question.strip().lower()
    if not lowered:
        return False
    research_terms = (
        "官方资料",
        "官方设定",
        "进一步确认",
        "网络搜索",
        "联网搜索",
        "搜索",
        "检索",
        "资料来源",
        "source",
        "web",
        "search",
        "evidence",
        "visual evidence",
    )
    identity_terms = (
        "外观",
        "发色",
        "服饰",
        "identity",
        "character",
        "appearance",
        "visual",
    )
    return any(term in lowered for term in research_terms) and any(term in lowered for term in identity_terms)


def _ensure_blender_scene_objects_for_edit(
    state: AgentProjectState,
    output: BlenderEditRouterOutput,
) -> tuple[AgentProjectState, dict[str, Any] | None]:
    if state.blender_scene is None or state.viewer_scene is None or not output.domain_tool_calls:
        return state, None
    if _blender_scene_resolves_router_calls(state, output):
        return state, None
    hydrated_objects = _blender_objects_from_viewer_scene(state=state, output=output)
    if not hydrated_objects:
        return state, None
    scene_asset_id = state.blender_scene.scene_asset_id or _first_artifact_id(state, ArtifactType.SCENE_3D_ASSET)
    updated_scene = state.blender_scene.model_copy(
        update={
            "objects": hydrated_objects,
            "scene_asset_id": scene_asset_id,
        }
    )
    updated = apply_state_updates(
        state,
        node_name="BlenderEditRouter",
        updates={"blender_scene": updated_scene},
    )
    return updated, {
        "object_count": len(hydrated_objects),
        "subject_ids": sorted({item.subject_id for item in hydrated_objects if item.subject_id}),
        "source": "viewer_scene",
    }


def _blender_scene_resolves_router_calls(state: AgentProjectState, output: BlenderEditRouterOutput) -> bool:
    objects = state.blender_scene.objects if state.blender_scene is not None else []
    if not objects:
        return False
    by_object_id = {item.object_id for item in objects}
    by_name = {item.blender_name for item in objects}
    by_subject = {item.subject_id for item in objects if item.subject_id}
    for call in output.domain_tool_calls:
        if call.domain_tool_name not in {"move_subject", "rotate_subject", "scale_subject", "delete_subject", "set_simple_material"}:
            continue
        args = dict(call.arguments)
        object_id = args.get("blender_object_id") or args.get("object_id") or args.get("blender_name")
        subject_id = args.get("subject_id")
        if object_id and (str(object_id) in by_object_id or str(object_id) in by_name):
            continue
        if subject_id and str(subject_id) in by_subject:
            continue
        return False
    return True


def _blender_objects_from_viewer_scene(
    *,
    state: AgentProjectState,
    output: BlenderEditRouterOutput,
) -> list[BlenderObjectRecord]:
    assert state.viewer_scene is not None
    requested_subject_ids = _requested_subject_ids(output) or _scene_spec_subject_ids(state)
    fallback_subject_id = requested_subject_ids[0] if len(requested_subject_ids) == 1 else None
    subject_asset_id = _first_artifact_id(state, ArtifactType.SUBJECT_3D_ASSET)
    scene_asset_id = _first_artifact_id(state, ArtifactType.SCENE_3D_ASSET)
    subject_candidate_name = _select_subject_viewer_object_name(state, requested_subject_ids=requested_subject_ids)
    seen: set[str] = set()
    objects: list[BlenderObjectRecord] = []
    for item in state.viewer_scene.objects:
        blender_name = item.blender_object_id or item.display_name or item.viewer_object_id
        if not blender_name:
            continue
        object_id = _unique_object_id(_safe_object_id(blender_name), seen)
        is_subject = (
            bool(item.subject_id)
            or (subject_candidate_name is not None and blender_name == subject_candidate_name)
        )
        subject_id = item.subject_id or (fallback_subject_id if is_subject else None)
        objects.append(
            BlenderObjectRecord(
                object_id=object_id,
                blender_name=blender_name,
                subject_id=subject_id,
                asset_id=subject_asset_id if is_subject else item.asset_id,
                scene_asset_id=scene_asset_id if _viewer_object_type(item.object_type, is_subject=is_subject) == "scene_layer" else None,
                object_type=_viewer_object_type(item.object_type, is_subject=is_subject),
                transform=item.transform if isinstance(item.transform, TransformSpec) else TransformSpec(),
                semantic_role="hero subject" if is_subject else None,
                visible=True,
            )
        )
    return objects


def _requested_subject_ids(output: BlenderEditRouterOutput) -> list[str]:
    ids = []
    for call in output.domain_tool_calls:
        subject_id = dict(call.arguments).get("subject_id")
        if isinstance(subject_id, str) and subject_id and subject_id not in ids:
            ids.append(subject_id)
    return ids


def _scene_spec_subject_ids(state: AgentProjectState) -> list[str]:
    if state.scene_spec is None:
        return []
    return [subject.subject_id for subject in state.scene_spec.subjects if subject.subject_id]


def _select_subject_viewer_object_name(state: AgentProjectState, *, requested_subject_ids: list[str]) -> str | None:
    if state.viewer_scene is None:
        return None
    for item in state.viewer_scene.objects:
        if item.subject_id and item.subject_id in requested_subject_ids:
            return item.blender_object_id or item.display_name or item.viewer_object_id
    named_candidates = []
    mesh_candidates = []
    for item in state.viewer_scene.objects:
        name = item.blender_object_id or item.display_name or item.viewer_object_id
        if not name or not item.selectable:
            continue
        object_type = str(item.object_type or "").lower()
        if object_type == "mesh":
            mesh_candidates.append(name)
        lowered = name.lower()
        if "hunyuan" in lowered or "subject" in lowered:
            named_candidates.append(name)
    if named_candidates:
        return named_candidates[0]
    if len(mesh_candidates) == 1 and requested_subject_ids:
        return mesh_candidates[0]
    return None


def _viewer_object_type(value: str | None, *, is_subject: bool) -> str:
    if is_subject:
        return "subject_asset"
    lowered = str(value or "").lower()
    if lowered == "camera":
        return "camera"
    if lowered == "light":
        return "light"
    if lowered == "empty":
        return "helper"
    if lowered == "mesh":
        return "scene_layer"
    return "unknown"


def _first_artifact_id(state: AgentProjectState, artifact_type: ArtifactType) -> str | None:
    for artifact in state.artifacts:
        if artifact.artifact_type == artifact_type:
            return artifact.artifact_id
    return None


def _safe_object_id(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return safe or "object"


def _unique_object_id(value: str, seen: set[str]) -> str:
    base = value
    index = 1
    while value in seen:
        index += 1
        value = f"{base}_{index}"
    seen.add(value)
    return value


def _patches_with_blender_edit_plan(output: BlenderEditRouterOutput) -> list[ReviewPatch]:
    if not output.domain_tool_calls:
        return list(output.patches)
    plan = {
        "route": output.route,
        "reason": output.reason,
        "allowed_domain_tool_names": list(output.allowed_domain_tool_names),
        "domain_tool_calls": [_model_to_dict(call) for call in output.domain_tool_calls],
    }
    if not output.patches:
        patch = _synthesized_blender_edit_patch(output=output, plan=plan)
        return [patch]
    planned_by_patch = {
        call.patch_id
        for call in output.domain_tool_calls
        if call.patch_id
    }
    routed = []
    for patch in output.patches:
        delta = dict(patch.structured_delta)
        if not planned_by_patch or patch.patch_id in planned_by_patch:
            delta["blender_edit_plan"] = plan
        routed.append(
            ReviewPatch(
                **{
                    **_model_to_dict(patch),
                    "structured_delta": delta,
                }
            )
        )
    return routed


def _synthesized_blender_edit_patch(*, output: BlenderEditRouterOutput, plan: dict[str, Any]) -> ReviewPatch:
    first_call = output.domain_tool_calls[0]
    arguments = dict(first_call.arguments)
    plan_hash = hashlib.sha1(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    target_id = (
        arguments.get("blender_object_id")
        or arguments.get("object_id")
        or arguments.get("subject_id")
        or arguments.get("camera_name")
    )
    patch_type = {
        "move_subject": "move_object",
        "rotate_subject": "rotate_object",
        "scale_subject": "scale_object",
        "delete_subject": "remove_subject",
        "replace_subject_asset": "replace_subject",
        "update_camera": "camera_change",
        "update_lighting": "lighting_change",
        "set_simple_material": "material_change",
    }.get(first_call.domain_tool_name, "layout_change")
    target_type = "camera" if first_call.domain_tool_name == "update_camera" else "blender_object"
    return ReviewPatch(
        patch_id=f"patch_blender_edit_{plan_hash}",
        source_turn_id="synthetic_blender_edit_router",
        phase_created=WorkflowPhase.BLENDER_EDIT,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        patch_type=patch_type,
        instruction=first_call.reason or output.reason,
        structured_delta={"blender_edit_plan": plan},
    )


def _save_checkpoint(
    run_dir: Path,
    state: AgentProjectState,
    *,
    execution: RuntimeJobExecutionRecord,
    applied_fields: list[str],
) -> StateCheckpointRecord:
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    return store.save_checkpoint(
        state,
        reason="runtime_state_apply",
        node_name=execution.node_name,
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={
            "stage": "runtime_state_apply",
            "execution_id": execution.execution_id,
            "job_id": execution.job_id,
            "applied_fields": applied_fields,
            "ok": True,
        },
    )


def _append_apply_to_summary(
    summary: dict[str, Any],
    *,
    checkpoint: StateCheckpointRecord,
    execution: RuntimeJobExecutionRecord,
) -> None:
    summary.setdefault("ok", True)
    summary.setdefault("workflow", "runtime-console")
    executed = summary.setdefault("executed_stages", [])
    if "runtime_state_apply" not in executed:
        executed.append("runtime_state_apply")
    requested = summary.setdefault("requested_stages", [])
    if "runtime_state_apply" not in requested:
        requested.append("runtime_state_apply")
    stage_records = summary.setdefault("stage_checkpoints", [])
    stage_records.append(_model_to_dict(checkpoint))
    runtime_apply = summary.setdefault("runtime_apply", [])
    runtime_apply.append({"execution_id": execution.execution_id, "job_id": execution.job_id, "node_name": execution.node_name})


def _select_candidate_execution(
    records: list[RuntimeJobExecutionRecord],
    applied_execution_ids: set[str],
) -> RuntimeJobExecutionRecord | None:
    for record in records:
        if record.execution_id in applied_execution_ids:
            continue
        if record.status != "completed":
            continue
        if record.output_json and record.node_name in {
            "ReferenceBindingValidator",
            "SceneSpecCompiler",
            "ConceptPromptPlanner",
            "FeedbackPatchParser",
            "RegenerationRouter",
            "BlenderAssemblyPlanner",
            "BlenderEditRouter",
        }:
            return record
    return None


def _write_apply_summary(run_dir: Path, records: list[RuntimeStateApplyRecord]) -> RuntimeStateApplySummary:
    counts: dict[str, int] = {}
    applied_ids = []
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        if record.status in APPLIED_STATUSES and record.execution_id:
            applied_ids.append(record.execution_id)
    summary = RuntimeStateApplySummary(
        run_dir=str(run_dir),
        generated_at=utc_now_iso(),
        apply_log_jsonl=str(_apply_log_path(run_dir)),
        total_records=len(records),
        status_counts=counts,
        latest_record=records[-1] if records else None,
        applied_execution_ids=applied_ids,
    )
    _write_json(_apply_summary_path(run_dir), _model_to_dict(summary))
    return summary


def _applied_execution_ids(records: list[RuntimeStateApplyRecord]) -> set[str]:
    return {record.execution_id for record in records if record.execution_id and record.status in APPLIED_STATUSES}


def _record_common(*, run_dir: Path, execution: RuntimeJobExecutionRecord) -> dict[str, Any]:
    return {
        "apply_id": f"apply_{uuid4().hex[:12]}",
        "execution_id": execution.execution_id,
        "job_id": execution.job_id,
        "node_name": execution.node_name,
        "created_at": utc_now_iso(),
        "state_json": str(run_dir / "state.json"),
    }


def _apply_log_path(run_dir: Path) -> Path:
    return run_dir / "runtime_apply.jsonl"


def _apply_summary_path(run_dir: Path) -> Path:
    return run_dir / "runtime_apply_summary.json"


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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
