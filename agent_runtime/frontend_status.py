"""Frontend-facing status snapshots derived from AgentProjectState.

This module does not introduce another workflow state source. It builds a small
display/handoff view from the authoritative project state plus a runner summary
so the UI can show current phase, node, progress, and pending user actions.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.state import AgentProjectState, ArtifactType, WorkflowPhase


FrontendRunStatus = Literal["completed", "attention_required", "needs_user_action"]
FrontendStageStatus = Literal["completed", "failed", "skipped", "pending"]


class FrontendStageProgress(BaseModel):
    stage: str
    status: FrontendStageStatus
    reason: str | None = None
    node_name: str | None = None


class FrontendPendingActionSummary(BaseModel):
    action_id: str
    action_type: str
    phase: str
    payload_kind: str | None = None
    asset_id: str | None = None
    subject_id: str | None = None
    source_image_id: str | None = None
    user_visible: bool = True


class FrontendConceptRequirementSummary(BaseModel):
    requirement_id: str
    output_type: str
    target_id: str | None = None
    user_review_label: str
    ready_artifact_ids: list[str] = Field(default_factory=list)
    generation_mode: str = "text_to_image"
    input_reference_image_ids: list[str] = Field(default_factory=list)
    source_requirement_ids: list[str] = Field(default_factory=list)
    must_use_image_inputs: bool = False
    quality_bar: str | None = None
    required_before_asset_generation: bool = True


class FrontendSceneSpecSummary(BaseModel):
    title: str
    user_goal: str
    environment_type: str
    subject_count: int
    subject_ids: list[str] = Field(default_factory=list)
    subject_asset_ids_required: list[str] = Field(default_factory=list)
    procedural_object_ids: list[str] = Field(default_factory=list)
    reference_bound_subject_ids: list[str] = Field(default_factory=list)


class FrontendAssetLibraryItemSummary(BaseModel):
    library_item_id: str
    artifact_id: str
    asset_kind: str
    subject_id: str | None = None
    scene_id: str | None = None
    requirement_id: str | None = None
    review_status: str
    selection_status: str
    source_artifact_ids: list[str] = Field(default_factory=list)
    derived_artifact_ids: list[str] = Field(default_factory=list)
    user_notes: str | None = None
    generation_round: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrontendAssetActionPayloadExample(BaseModel):
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None


class FrontendUserActionPayloadExample(BaseModel):
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None


class FrontendAssemblyObjectSelectionSummary(BaseModel):
    subject_id: str
    selected_subject_asset_id: str | None = None
    source_concept_image_id: str | None = None
    placement_hint: dict[str, Any] = Field(default_factory=dict)


class FrontendAssemblySelectionSummary(BaseModel):
    selection_id: str
    version: int
    selected_subject_assets: dict[str, str] = Field(default_factory=dict)
    selected_scene_asset_id: str | None = None
    selected_scene_concept_image_id: str | None = None
    selected_target_render_image_id: str | None = None
    object_placements: list[FrontendAssemblyObjectSelectionSummary] = Field(default_factory=list)
    source_turn_id: str | None = None
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrontendStatus(BaseModel):
    project_id: str
    thread_id: str
    phase: str
    status: FrontendRunStatus
    current_stage: str | None = None
    current_node: str | None = None
    progress_label: str
    workflow: str | None = None
    ok: bool
    dry_run: bool
    requested_stages: list[str] = Field(default_factory=list)
    executed_stages: list[str] = Field(default_factory=list)
    stage_progress: list[FrontendStageProgress] = Field(default_factory=list)
    pending_action: FrontendPendingActionSummary | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    subject_asset_ids: list[str] = Field(default_factory=list)
    concept_requirements: list[FrontendConceptRequirementSummary] = Field(default_factory=list)
    asset_library: list[FrontendAssetLibraryItemSummary] = Field(default_factory=list)
    active_assembly_selection: FrontendAssemblySelectionSummary | None = None
    available_user_actions: list[str] = Field(default_factory=list)
    available_user_action_payloads: list[FrontendUserActionPayloadExample] = Field(default_factory=list)
    available_asset_actions: list[str] = Field(default_factory=list)
    available_asset_action_payloads: list[FrontendAssetActionPayloadExample] = Field(default_factory=list)
    scene_spec_summary: FrontendSceneSpecSummary | None = None
    review_patch_ids: list[str] = Field(default_factory=list)
    scene_asset_id: str | None = None
    viewer_scene_id: str | None = None
    blender_scene_id: str | None = None
    tool_call_count: int = 0
    generated_at: str


def build_frontend_status(*, state: AgentProjectState, summary: dict[str, Any]) -> FrontendStatus:
    requested_stages = [str(item) for item in summary.get("requested_stages") or []]
    executed_stages = [str(item) for item in summary.get("executed_stages") or []]
    stage_checkpoints = [item for item in summary.get("stage_checkpoints") or [] if isinstance(item, dict)]
    current_checkpoint = stage_checkpoints[-1] if stage_checkpoints else None
    phase_gate = _phase_gate_summary(state)
    current_stage = phase_gate["stage"] if phase_gate is not None else _current_stage(executed_stages, current_checkpoint)
    current_node = phase_gate["node"] if phase_gate is not None else _current_node(current_checkpoint)
    pending_action = _pending_action_summary(state)
    ok = bool(summary.get("ok"))
    status: FrontendRunStatus
    if pending_action is not None or phase_gate is not None:
        status = "needs_user_action"
    elif ok:
        status = "completed"
    else:
        status = "attention_required"

    return FrontendStatus(
        project_id=state.project_id,
        thread_id=state.thread_id,
        phase=state.phase.value,
        status=status,
        current_stage=current_stage,
        current_node=current_node,
        progress_label=_progress_label(
            status=status,
            phase=state.phase.value,
            current_stage=current_stage,
            pending_action=pending_action,
            phase_gate=phase_gate,
        ),
        workflow=_workflow_name(summary, current_checkpoint),
        ok=ok,
        dry_run=bool(summary.get("dry_run")),
        requested_stages=requested_stages,
        executed_stages=executed_stages,
        stage_progress=_stage_progress(
            requested_stages=requested_stages,
            executed_stages=executed_stages,
            skipped_stages=summary.get("skipped_stages") or {},
            stage_checkpoints=stage_checkpoints,
        ),
        pending_action=pending_action,
        artifact_ids=sorted(state.artifact_ids()),
        subject_asset_ids=_subject_asset_ids(state),
        concept_requirements=_concept_requirements(state),
        asset_library=_asset_library(state),
        active_assembly_selection=_active_assembly_selection(state),
        available_user_actions=_available_user_actions(state),
        available_user_action_payloads=_available_user_action_payloads(state),
        available_asset_actions=_available_asset_actions(state),
        available_asset_action_payloads=_available_asset_action_payloads(state),
        scene_spec_summary=_scene_spec_summary(state),
        review_patch_ids=[patch.patch_id for patch in state.review_patches],
        scene_asset_id=_scene_asset_id(state),
        viewer_scene_id=state.viewer_scene.viewer_scene_id if state.viewer_scene is not None else None,
        blender_scene_id=state.blender_scene.blender_scene_id if state.blender_scene is not None else None,
        tool_call_count=len(state.tool_call_log),
        generated_at=utc_now_iso(),
    )


def _subject_asset_ids(state: AgentProjectState) -> list[str]:
    if state.subject_assets:
        return [asset.asset_id for asset in state.subject_assets]
    return [
        artifact.artifact_id
        for artifact in state.artifacts
        if artifact.artifact_type == ArtifactType.SUBJECT_3D_ASSET
    ]


def _scene_asset_id(state: AgentProjectState) -> str | None:
    if state.scene_asset is not None:
        return state.scene_asset.scene_asset_id
    if state.blender_scene is not None and state.blender_scene.scene_asset_id:
        return state.blender_scene.scene_asset_id
    for artifact in state.artifacts:
        if artifact.artifact_type == ArtifactType.SCENE_3D_ASSET:
            return artifact.artifact_id
    return None


def _concept_requirements(state: AgentProjectState) -> list[FrontendConceptRequirementSummary]:
    concept = state.concept_bundle
    if concept is None or concept.prompt_pack is None:
        return []
    ready_by_type_target = _concept_ready_artifacts(state)
    output = []
    for requirement in concept.prompt_pack.image_requirements:
        key = (requirement.output_type, requirement.target_id)
        output.append(
            FrontendConceptRequirementSummary(
                requirement_id=requirement.requirement_id,
                output_type=requirement.output_type,
                target_id=requirement.target_id,
                user_review_label=requirement.user_review_label,
                ready_artifact_ids=ready_by_type_target.get(key, []),
                generation_mode=requirement.generation_mode,
                input_reference_image_ids=list(requirement.input_reference_image_ids),
                source_requirement_ids=list(requirement.source_requirement_ids),
                must_use_image_inputs=requirement.must_use_image_inputs,
                quality_bar=requirement.quality_bar,
                required_before_asset_generation=requirement.required_before_asset_generation,
            )
        )
    return output


def _asset_library(state: AgentProjectState) -> list[FrontendAssetLibraryItemSummary]:
    return [
        FrontendAssetLibraryItemSummary(
            library_item_id=item.library_item_id,
            artifact_id=item.artifact_id,
            asset_kind=item.asset_kind,
            subject_id=item.subject_id,
            scene_id=item.scene_id,
            requirement_id=item.requirement_id,
            review_status=item.review_status,
            selection_status=item.selection_status,
            source_artifact_ids=list(item.source_artifact_ids),
            derived_artifact_ids=list(item.derived_artifact_ids),
            user_notes=item.user_notes,
            generation_round=item.generation_round,
            metadata=dict(item.metadata),
        )
        for item in state.asset_library
    ]


def _active_assembly_selection(state: AgentProjectState) -> FrontendAssemblySelectionSummary | None:
    selection = state.active_assembly_selection
    if selection is None:
        return None
    return FrontendAssemblySelectionSummary(
        selection_id=selection.selection_id,
        version=selection.version,
        selected_subject_assets=dict(selection.selected_subject_assets),
        selected_scene_asset_id=selection.selected_scene_asset_id,
        selected_scene_concept_image_id=selection.selected_scene_concept_image_id,
        selected_target_render_image_id=selection.selected_target_render_image_id,
        object_placements=[
            FrontendAssemblyObjectSelectionSummary(
                subject_id=item.subject_id,
                selected_subject_asset_id=item.selected_subject_asset_id,
                source_concept_image_id=item.source_concept_image_id,
                placement_hint=dict(item.placement_hint),
            )
            for item in selection.object_placements
        ],
        source_turn_id=selection.source_turn_id,
        updated_at=selection.updated_at,
        metadata=dict(selection.metadata),
    )


def _available_asset_actions(state: AgentProjectState) -> list[str]:
    actions = []
    if state.asset_library:
        actions.append("set_asset_review_status")
    if any(item.asset_kind == "subject_concept" for item in state.asset_library):
        actions.append("select_concept_for_subject_generation")
    if any(item.asset_kind == "subject_model" for item in state.asset_library):
        actions.append("select_asset_for_assembly")
    return actions


def _available_user_actions(state: AgentProjectState) -> list[str]:
    phase_gate = _phase_gate_summary(state)
    if phase_gate is None:
        return []
    action_type = phase_gate["action_type"]
    if action_type == "approve_concept":
        return ["approve_concept", "request_concept_changes"]
    if action_type == "approve_model_assets":
        return ["approve_model_assets", "request_model_changes"]
    if action_type == "approve_blender_preview":
        return ["approve_blender_preview", "request_blender_changes"]
    return [action_type]


def _available_user_action_payloads(state: AgentProjectState) -> list[FrontendUserActionPayloadExample]:
    actions = _available_user_actions(state)
    examples: list[FrontendUserActionPayloadExample] = []
    for action_type in actions:
        payload: dict[str, Any] = {"action_type": action_type, "rebuild_plan": True}
        label = action_type
        if action_type == "approve_concept":
            payload["note"] = "user accepted concept images"
            label = "Approve concept"
        elif action_type == "request_concept_changes":
            payload["feedback_text"] = "describe concept changes"
            label = "Request concept changes"
        elif action_type == "approve_model_assets":
            payload["note"] = "user accepted generated model assets"
            label = "Approve model assets"
        elif action_type == "request_model_changes":
            payload["feedback_text"] = "describe model-stage problems and requested regeneration"
            label = "Request model changes"
        elif action_type == "approve_blender_preview":
            payload["note"] = "user accepted Blender preview"
            label = "Approve Blender preview"
        elif action_type == "request_blender_changes":
            payload["feedback_text"] = "describe Blender preview changes"
            label = "Request Blender changes"
        examples.append(FrontendUserActionPayloadExample(action_type=action_type, payload=payload, label=label))
    return examples


def _available_asset_action_payloads(state: AgentProjectState) -> list[FrontendAssetActionPayloadExample]:
    examples: list[FrontendAssetActionPayloadExample] = []
    review_item = state.asset_library[0] if state.asset_library else None
    if review_item is not None:
        examples.append(
            FrontendAssetActionPayloadExample(
                action_type="set_asset_review_status",
                label="Mark asset review status",
                payload={
                    "action_type": "set_asset_review_status",
                    "artifact_id": review_item.artifact_id,
                    "review_status": "rejected",
                    "note": "short user note",
                },
            )
        )

    concept_item = next((item for item in state.asset_library if item.asset_kind == "subject_concept" and item.subject_id), None)
    if concept_item is not None:
        examples.append(
            FrontendAssetActionPayloadExample(
                action_type="select_concept_for_subject_generation",
                label="Select subject concept for model generation",
                payload={
                    "action_type": "select_concept_for_subject_generation",
                    "subject_id": concept_item.subject_id,
                    "concept_artifact_id": concept_item.artifact_id,
                    "note": "user-selected source concept",
                },
            )
        )

    subject_asset_payload = _assembly_action_payload_example(state)
    if subject_asset_payload:
        examples.append(
            FrontendAssetActionPayloadExample(
                action_type="select_asset_for_assembly",
                label="Select assets for Blender assembly",
                payload=subject_asset_payload,
            )
        )
    return examples


def _assembly_action_payload_example(state: AgentProjectState) -> dict[str, Any] | None:
    selected_subject_assets: dict[str, str] = {}
    for item in state.asset_library:
        if item.asset_kind != "subject_model" or item.subject_id is None:
            continue
        selected_subject_assets.setdefault(item.subject_id, item.artifact_id)
    for asset in state.subject_assets:
        selected_subject_assets.setdefault(asset.subject_id, asset.asset_id)
    if not selected_subject_assets:
        return None

    scene_asset_id = _scene_asset_id(state)
    scene_concept_id = _first_asset_kind_artifact_id(state, "scene_concept")
    target_render_id = _first_asset_kind_artifact_id(state, "target_render")
    payload: dict[str, Any] = {
        "action_type": "select_asset_for_assembly",
        "subject_asset_ids_by_subject": selected_subject_assets,
        "placement_hints": [
            {"subject_id": subject_id, "target_region": "front_center"}
            for subject_id in selected_subject_assets
        ],
        "note": "user-selected assembly set",
    }
    if scene_asset_id:
        payload["scene_asset_id"] = scene_asset_id
    if scene_concept_id:
        payload["scene_concept_image_id"] = scene_concept_id
    if target_render_id:
        payload["target_render_image_id"] = target_render_id
    return payload


def _first_asset_kind_artifact_id(state: AgentProjectState, asset_kind: str) -> str | None:
    for item in state.asset_library:
        if item.asset_kind == asset_kind:
            return item.artifact_id
    return None


def _concept_ready_artifacts(state: AgentProjectState) -> dict[tuple[str, str | None], list[str]]:
    concept = state.concept_bundle
    ready: dict[tuple[str, str | None], list[str]] = {}
    if concept is None:
        return ready
    if concept.final_preview_image_id:
        ready.setdefault(("target_render", state.scene_spec.scene_id if state.scene_spec is not None else None), []).append(
            concept.final_preview_image_id
        )
    for subject_id, image_ids in concept.subject_concept_images.items():
        ready.setdefault(("subject_concept", subject_id), []).extend(image_ids)
    for image_id in concept.scene_concept_image_ids:
        ready.setdefault(("scene_concept", state.scene_spec.scene_id if state.scene_spec is not None else None), []).append(
            image_id
        )
    return ready


def _scene_spec_summary(state: AgentProjectState) -> FrontendSceneSpecSummary | None:
    scene_spec = state.scene_spec
    if scene_spec is None:
        return None
    subject_asset_ids_required = [
        subject.subject_id
        for subject in scene_spec.subjects
        if subject.needs_3d_asset and subject.asset_strategy in {"hunyuan3d_img2asset", "existing_asset"}
    ]
    procedural_object_ids = [
        subject.subject_id
        for subject in scene_spec.subjects
        if subject.asset_strategy in {"procedural_blender", "scene_service_component", "blender_primitive"}
    ]
    reference_bound_subject_ids = [
        subject.subject_id
        for subject in scene_spec.subjects
        if subject.reference_image_ids
    ]
    return FrontendSceneSpecSummary(
        title=scene_spec.title,
        user_goal=scene_spec.user_goal,
        environment_type=scene_spec.environment.environment_type,
        subject_count=len(scene_spec.subjects),
        subject_ids=[subject.subject_id for subject in scene_spec.subjects],
        subject_asset_ids_required=subject_asset_ids_required,
        procedural_object_ids=procedural_object_ids,
        reference_bound_subject_ids=reference_bound_subject_ids,
    )


def _stage_progress(
    *,
    requested_stages: list[str],
    executed_stages: list[str],
    skipped_stages: dict[str, Any],
    stage_checkpoints: list[dict[str, Any]],
) -> list[FrontendStageProgress]:
    checkpoint_by_stage = {
        str((record.get("metadata") or {}).get("stage")): record
        for record in stage_checkpoints
        if isinstance(record.get("metadata"), dict) and (record.get("metadata") or {}).get("stage")
    }
    stage_names = requested_stages or executed_stages or list(skipped_stages)
    output = []
    for stage in stage_names:
        checkpoint = checkpoint_by_stage.get(stage)
        if stage in skipped_stages:
            output.append(
                FrontendStageProgress(
                    stage=stage,
                    status="skipped",
                    reason=str(skipped_stages[stage]),
                    node_name=_current_node(checkpoint),
                )
            )
        elif stage in executed_stages:
            ok = True
            if checkpoint is not None:
                metadata = checkpoint.get("metadata") or {}
                ok = bool(metadata.get("ok", True))
            output.append(
                FrontendStageProgress(
                    stage=stage,
                    status="completed" if ok else "failed",
                    reason=checkpoint.get("reason") if checkpoint is not None else None,
                    node_name=_current_node(checkpoint),
                )
            )
        else:
            output.append(FrontendStageProgress(stage=stage, status="pending"))
    return output


def _pending_action_summary(state: AgentProjectState) -> FrontendPendingActionSummary | None:
    pending = state.pending_action
    if pending is None:
        return None
    payload = pending.payload or {}
    repair_decision = payload.get("repair_decision") if isinstance(payload.get("repair_decision"), dict) else {}
    return FrontendPendingActionSummary(
        action_id=pending.action_id,
        action_type=pending.action_type,
        phase=pending.phase.value,
        payload_kind=payload.get("kind"),
        asset_id=payload.get("asset_id"),
        subject_id=payload.get("subject_id"),
        source_image_id=payload.get("source_image_id"),
        user_visible=bool(repair_decision.get("user_visible", True)),
    )


def _phase_gate_summary(state: AgentProjectState) -> dict[str, str] | None:
    if (
        state.phase == WorkflowPhase.CONCEPT_REVIEW
        and state.concept_bundle is not None
        and not state.concept_bundle.approved
        and (
            state.concept_bundle.final_preview_image_id
            or state.concept_bundle.subject_concept_images
            or state.concept_bundle.scene_concept_image_ids
        )
    ):
        return {
            "stage": "concept_approval",
            "node": "ConceptReviewGate",
            "action_type": "approve_concept",
        }
    if state.phase == WorkflowPhase.BLENDER_PREVIEW and state.blender_scene is not None and state.viewer_scene is not None:
        return {
            "stage": "blender_preview_approval",
            "node": "BlenderPreviewReviewGate",
            "action_type": "approve_blender_preview",
        }
    if state.phase == WorkflowPhase.SUBJECT_ASSET_QA and _has_subject_model_outputs(state):
        return {
            "stage": "model_asset_approval",
            "node": "ModelAssetReviewGate",
            "action_type": "approve_model_assets",
        }
    return None


def _has_subject_model_outputs(state: AgentProjectState) -> bool:
    return bool(state.subject_assets or any(item.asset_kind == "subject_model" for item in state.asset_library))


def _progress_label(
    *,
    status: FrontendRunStatus,
    phase: str,
    current_stage: str | None,
    pending_action: FrontendPendingActionSummary | None,
    phase_gate: dict[str, str] | None = None,
) -> str:
    if pending_action is not None:
        return f"Waiting for {pending_action.action_type}"
    if phase_gate is not None:
        return f"Waiting for {phase_gate['action_type']}"
    if status == "attention_required":
        return f"Needs attention at {current_stage or phase}"
    return f"Completed {current_stage or phase}"


def _current_stage(executed_stages: list[str], checkpoint: dict[str, Any] | None) -> str | None:
    if checkpoint is not None:
        metadata = checkpoint.get("metadata") or {}
        stage = metadata.get("stage")
        if stage:
            return str(stage)
    return executed_stages[-1] if executed_stages else None


def _current_node(checkpoint: dict[str, Any] | None) -> str | None:
    if checkpoint is None:
        return None
    node_name = checkpoint.get("node_name")
    return str(node_name) if node_name else None


def _workflow_name(summary: dict[str, Any], checkpoint: dict[str, Any] | None) -> str | None:
    if checkpoint is not None:
        metadata = checkpoint.get("metadata") or {}
        workflow = metadata.get("workflow")
        if workflow:
            return str(workflow)
    value = summary.get("workflow")
    return str(value) if value else None
