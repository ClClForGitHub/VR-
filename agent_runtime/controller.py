"""State-driven controller gates for the V1 workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agent_runtime.domain_tools import allowed_tool_names
from agent_runtime.state import AgentProjectState, ArtifactRecord, ArtifactType, Asset3DRecord, WorkflowPhase


ControllerActionType = Literal[
    "run_node",
    "run_domain_tool",
    "ask_user",
    "await_user_approval",
    "deliver",
    "stop",
]


class ControllerAction(BaseModel):
    action_type: ControllerActionType
    reason: str
    phase: WorkflowPhase
    node_name: str | None = None
    domain_tool_name: str | None = None
    allowed_domain_tools: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)


class ControllerPlan(BaseModel):
    phase: WorkflowPhase
    actions: list[ControllerAction] = Field(default_factory=list)
    next_phase: WorkflowPhase | None = None
    requires_user: bool = False
    blocked: bool = False
    issues: list[str] = Field(default_factory=list)


def build_controller_plan(state: AgentProjectState) -> ControllerPlan:
    """Return the next safe V1 action from current AgentProjectState."""

    if state.phase == WorkflowPhase.FAILED:
        return _blocked_stop(state, "workflow_phase_failed")
    if state.last_error is not None and not state.last_error.recoverable:
        return _blocked_stop(state, f"unrecoverable_error:{state.last_error.error_id}")
    if state.pending_action is not None:
        return _pending_action_plan(state)

    unbound_image_ids = _unbound_image_ids(state)
    if state.phase == WorkflowPhase.INTAKE and unbound_image_ids:
        return _ask_user_plan(
            state,
            reason="reference_images_missing_explicit_bindings",
            issues=[f"image_missing_binding:{image_id}" for image_id in unbound_image_ids],
            payload={"image_ids": unbound_image_ids},
        )

    if state.scene_spec is not None and state.scene_spec.open_questions:
        return _ask_user_plan(
            state,
            reason="scene_spec_has_open_questions",
            issues=list(state.scene_spec.open_questions),
            payload={"open_questions": list(state.scene_spec.open_questions)},
        )

    phase = state.phase
    if phase == WorkflowPhase.INTAKE:
        return ControllerPlan(
            phase=phase,
            next_phase=WorkflowPhase.SCENE_SPEC_DRAFT,
            actions=[
                _node_action(phase, "ReferenceBindingValidator", "validate_explicit_reference_bindings"),
                _node_action(phase, "SceneInterpreter", "extract_scene_intent"),
                _node_action(phase, "SceneSpecCompiler", "compile_scene_spec"),
            ],
        )

    if phase in {WorkflowPhase.SCENE_SPEC_DRAFT, WorkflowPhase.SCENE_SPEC_READY}:
        if state.scene_spec is None:
            return ControllerPlan(
                phase=phase,
                next_phase=WorkflowPhase.SCENE_SPEC_DRAFT,
                actions=[_node_action(phase, "SceneSpecCompiler", "scene_spec_missing")],
                issues=["missing_scene_spec"],
            )
        return _concept_generation_plan(state, phase)

    if phase == WorkflowPhase.CONCEPT_GENERATION:
        if not _concept_has_outputs(state):
            return _concept_generation_plan(state, phase, reason="concept_outputs_missing")
        return _concept_review_plan(state, reason="concept_outputs_ready")

    if phase == WorkflowPhase.CONCEPT_REVIEW:
        pending_patches = [patch.patch_id for patch in state.review_patches if patch.status == "pending"]
        if pending_patches:
            return ControllerPlan(
                phase=phase,
                next_phase=WorkflowPhase.CONCEPT_GENERATION,
                actions=[
                    _node_action(phase, "RegenerationRouter", "pending_review_patches"),
                    _node_action(phase, "ConceptPromptPlanner", "plan_regenerated_concepts"),
                    _tool_action(phase, "regenerate_concept_images", "apply_review_patch_regeneration"),
                ],
                issues=[f"pending_review_patch:{patch_id}" for patch_id in pending_patches],
            )
        if not _concept_approved(state):
            return _concept_review_plan(state, reason="concept_requires_user_approval")
        return _subject_asset_plan(state, phase)

    if phase == WorkflowPhase.CONCEPT_APPROVED:
        return _subject_asset_plan(state, phase)

    if phase in {WorkflowPhase.SUBJECT_ASSET_GENERATION, WorkflowPhase.SUBJECT_ASSET_QA}:
        if not _concept_approved(state):
            return _concept_review_plan(state, reason="subject_generation_requires_concept_approval")
        problem_assets = _problem_subject_assets(state.subject_assets)
        if problem_assets:
            return _ask_user_plan(
                state,
                reason="subject_asset_quality_uncertain_or_failed",
                issues=[f"subject_asset_problem:{asset.asset_id}:{asset.status}" for asset in problem_assets],
                payload={"asset_ids": [asset.asset_id for asset in problem_assets]},
            )
        missing_subject_ids = _missing_subject_asset_ids(state)
        if missing_subject_ids:
            return _subject_asset_plan(
                state,
                phase,
                reason="missing_subject_assets",
                payload={"subject_ids": missing_subject_ids},
            )
        return _scene_asset_plan(state, phase)

    if phase in {WorkflowPhase.SCENE_ASSET_GENERATION, WorkflowPhase.SCENE_ASSET_ADAPTATION}:
        if state.scene_asset is None or state.scene_asset.status not in {"adapted", "accepted_with_warning"}:
            return _scene_asset_plan(state, phase)
        return _blender_assembly_plan(state, phase)

    if phase in {WorkflowPhase.BLENDER_ASSEMBLY_PLANNING, WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION}:
        return _blender_assembly_plan(state, phase)

    if phase == WorkflowPhase.BLENDER_EDIT:
        planned_edit_actions = _planned_blender_edit_actions(state)
        actions = [
            *planned_edit_actions,
            _tool_action(phase, "export_viewer_scene", "refresh_viewer_after_edit"),
            _tool_action(phase, "render_preview", "refresh_high_quality_preview_if_needed"),
        ]
        if not planned_edit_actions:
            actions.insert(0, _node_action(phase, "BlenderEditRouter", "route_user_blender_edit"))
        return ControllerPlan(
            phase=phase,
            next_phase=WorkflowPhase.BLENDER_PREVIEW,
            actions=actions,
        )

    if phase == WorkflowPhase.BLENDER_PREVIEW:
        if state.viewer_scene is None:
            return _blender_assembly_plan(state, phase, reason="viewer_scene_missing")
        return _await_user_approval_plan(
            state,
            reason="blender_preview_requires_user_approval",
            payload={"viewer_scene_id": state.viewer_scene.viewer_scene_id},
        )

    if phase == WorkflowPhase.DELIVERY:
        if state.blender_scene is None or state.viewer_scene is None:
            return ControllerPlan(
                phase=phase,
                blocked=True,
                issues=["delivery_requires_blender_scene_and_viewer_scene"],
                actions=[_node_action(phase, "DeliveryPackager", "delivery_artifacts_missing")],
            )
        if _completed_delivery_package(state) is not None:
            return ControllerPlan(phase=phase, actions=[])
        return ControllerPlan(
            phase=phase,
            actions=[
                ControllerAction(
                    action_type="deliver",
                    phase=phase,
                    reason="delivery_artifacts_ready",
                    required_outputs=[
                        "state.json",
                        "summary.json",
                        "tool_call_log.json",
                        "frontend_status.json",
                        "delivery_package.zip",
                    ],
                )
            ],
        )

    return _blocked_stop(state, f"unsupported_phase:{phase.value}")


def _concept_generation_plan(
    state: AgentProjectState,
    phase: WorkflowPhase,
    *,
    reason: str = "scene_spec_ready_for_concept_generation",
) -> ControllerPlan:
    generation_tool = "regenerate_concept_images" if _has_pending_review_patches(state) else "generate_concept_images"
    generation_reason = "apply_review_patch_regeneration" if generation_tool == "regenerate_concept_images" else "create_concept_bundle"
    if state.concept_bundle is not None and state.concept_bundle.prompt_pack is not None:
        return ControllerPlan(
            phase=phase,
            next_phase=WorkflowPhase.CONCEPT_GENERATION,
            actions=[
                _tool_action(WorkflowPhase.CONCEPT_GENERATION, generation_tool, generation_reason),
            ],
        )
    return ControllerPlan(
        phase=phase,
        next_phase=WorkflowPhase.CONCEPT_GENERATION,
        actions=[
            _node_action(phase, "ConceptPromptPlanner", reason),
            _tool_action(WorkflowPhase.CONCEPT_GENERATION, generation_tool, generation_reason),
        ],
    )


def _concept_review_plan(state: AgentProjectState, *, reason: str) -> ControllerPlan:
    payload = {}
    if state.concept_bundle is not None:
        payload["concept_version"] = state.concept_bundle.concept_version
        payload["final_preview_image_id"] = state.concept_bundle.final_preview_image_id
    return _await_user_approval_plan(state, reason=reason, payload=payload, phase=WorkflowPhase.CONCEPT_REVIEW)


def _subject_asset_plan(
    state: AgentProjectState,
    phase: WorkflowPhase,
    *,
    reason: str = "concept_approved_for_subject_generation",
    payload: dict[str, object] | None = None,
) -> ControllerPlan:
    effective_payload = dict(payload or {})
    subject_ids = _missing_subject_asset_ids(state) or _needed_subject_ids(state)
    effective_payload.setdefault("subject_ids", subject_ids)
    selected_concepts = _selected_subject_concept_artifacts_by_subject(state, subject_ids=subject_ids)
    if selected_concepts:
        effective_payload.setdefault("selected_concept_artifact_ids_by_subject", selected_concepts)
        effective_payload.setdefault("selected_source_image_ids", list(selected_concepts.values()))
    return ControllerPlan(
        phase=phase,
        next_phase=WorkflowPhase.SUBJECT_ASSET_GENERATION,
        actions=[
            _tool_action(
                WorkflowPhase.SUBJECT_ASSET_GENERATION,
                "build_subject_asset",
                reason,
                payload=effective_payload,
            ),
            _tool_action(
                WorkflowPhase.SUBJECT_ASSET_GENERATION,
                "check_subject_asset_quality",
                "qa_generated_subject_assets",
            ),
        ],
    )


def _scene_asset_plan(state: AgentProjectState, phase: WorkflowPhase) -> ControllerPlan:
    return ControllerPlan(
        phase=phase,
        next_phase=WorkflowPhase.SCENE_ASSET_GENERATION,
        actions=[
            _tool_action(WorkflowPhase.SCENE_ASSET_GENERATION, "build_scene_asset", "create_or_register_scene_asset"),
            _tool_action(WorkflowPhase.SCENE_ASSET_GENERATION, "adapt_scene_asset", "adapt_scene_asset_for_blender"),
        ],
    )


def _blender_assembly_plan(
    state: AgentProjectState,
    phase: WorkflowPhase,
    *,
    reason: str = "assets_ready_for_blender_assembly",
) -> ControllerPlan:
    actions: list[ControllerAction] = []
    if state.blender_scene is None:
        if state.blender_assembly_plan is None:
            actions.append(_node_action(WorkflowPhase.BLENDER_ASSEMBLY_PLANNING, "BlenderAssemblyPlanner", reason))
        else:
            actions.append(
                _tool_action(
                    WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
                    "import_scene_asset",
                    "execute_blender_assembly_plan",
                    payload=_blender_assembly_tool_payload(state),
                )
            )
    if state.viewer_scene is None:
        actions.append(
            _tool_action(
                WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
                "export_viewer_scene",
                "export_web_viewer_snapshot",
            )
        )
    actions.append(
        _tool_action(
            WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
            "render_preview",
            "render_high_quality_preview_if_needed",
        )
    )
    return ControllerPlan(
        phase=phase,
        next_phase=WorkflowPhase.BLENDER_PREVIEW,
        actions=actions,
    )


def _blender_assembly_tool_payload(state: AgentProjectState) -> dict[str, object]:
    payload: dict[str, object] = {}
    if state.blender_assembly_plan is not None:
        payload["assembly_plan_id"] = state.blender_assembly_plan.plan_id
    selection = state.active_assembly_selection
    if selection is not None:
        payload["active_assembly_selection_id"] = selection.selection_id
        payload["selected_subject_assets"] = dict(selection.selected_subject_assets)
        if selection.selected_scene_concept_image_id:
            payload["selected_scene_concept_image_id"] = selection.selected_scene_concept_image_id
        if selection.selected_target_render_image_id:
            payload["selected_target_render_image_id"] = selection.selected_target_render_image_id
        if selection.object_placements:
            payload["object_placements"] = [
                placement.model_dump(mode="json") if hasattr(placement, "model_dump") else placement.dict()
                for placement in selection.object_placements
            ]
    if selection is not None and selection.selected_scene_asset_id:
        payload["scene_asset_id"] = selection.selected_scene_asset_id
    elif state.scene_asset is not None:
        payload["scene_asset_id"] = state.scene_asset.scene_asset_id
    subject_id = _primary_assembly_subject_id(state)
    if subject_id is not None:
        payload["subject_id"] = subject_id
    subject_asset_id = _subject_asset_id_for_subject(state, subject_id)
    if subject_asset_id is not None:
        payload["subject_asset_id"] = subject_asset_id
    return payload


def _primary_assembly_subject_id(state: AgentProjectState) -> str | None:
    selection = state.active_assembly_selection
    if selection is not None:
        for placement in selection.object_placements:
            if placement.subject_id:
                return placement.subject_id
        for subject_id in selection.selected_subject_assets:
            return subject_id
    if state.blender_assembly_plan is not None:
        for placement in state.blender_assembly_plan.placement_plans:
            if placement.subject_id:
                return placement.subject_id
    if state.scene_spec is not None and state.scene_spec.subjects:
        return state.scene_spec.subjects[0].subject_id
    if state.subject_assets:
        return state.subject_assets[0].subject_id
    return None


def _subject_asset_id_for_subject(state: AgentProjectState, subject_id: str | None) -> str | None:
    selection = state.active_assembly_selection
    if selection is not None:
        if subject_id is not None and subject_id in selection.selected_subject_assets:
            return selection.selected_subject_assets[subject_id]
        for placement in selection.object_placements:
            if placement.selected_subject_asset_id and (subject_id is None or placement.subject_id == subject_id):
                return placement.selected_subject_asset_id
        for asset_id in selection.selected_subject_assets.values():
            return asset_id
    if subject_id is not None:
        for asset in state.subject_assets:
            if asset.subject_id == subject_id and (asset.glb_uri or asset.mesh_uri or asset.obj_uri):
                return asset.asset_id
    for asset in state.subject_assets:
        if asset.glb_uri or asset.mesh_uri or asset.obj_uri:
            return asset.asset_id
    return None


def _pending_action_plan(state: AgentProjectState) -> ControllerPlan:
    pending = state.pending_action
    assert pending is not None
    return ControllerPlan(
        phase=state.phase,
        requires_user=True,
        blocked=True,
        issues=[f"pending_action:{pending.action_type}:{pending.action_id}"],
        actions=[
            ControllerAction(
                action_type="ask_user",
                phase=state.phase,
                reason="pending_action_requires_user_or_operator_input",
                payload={"pending_action_id": pending.action_id, "pending_action_type": pending.action_type},
            )
        ],
    )


def _ask_user_plan(
    state: AgentProjectState,
    *,
    reason: str,
    issues: list[str],
    payload: dict[str, object] | None = None,
) -> ControllerPlan:
    return ControllerPlan(
        phase=state.phase,
        requires_user=True,
        blocked=True,
        issues=issues,
        actions=[
            ControllerAction(
                action_type="ask_user",
                phase=state.phase,
                reason=reason,
                payload=payload or {},
            )
        ],
    )


def _await_user_approval_plan(
    state: AgentProjectState,
    *,
    reason: str,
    payload: dict[str, object] | None = None,
    phase: WorkflowPhase | None = None,
) -> ControllerPlan:
    action_phase = phase or state.phase
    return ControllerPlan(
        phase=state.phase,
        next_phase=action_phase,
        requires_user=True,
        blocked=True,
        actions=[
            ControllerAction(
                action_type="await_user_approval",
                phase=action_phase,
                reason=reason,
                payload=payload or {},
            )
        ],
    )


def _blocked_stop(state: AgentProjectState, reason: str) -> ControllerPlan:
    return ControllerPlan(
        phase=state.phase,
        blocked=True,
        issues=[reason],
        actions=[ControllerAction(action_type="stop", phase=state.phase, reason=reason)],
    )


def _node_action(phase: WorkflowPhase, node_name: str, reason: str) -> ControllerAction:
    return ControllerAction(
        action_type="run_node",
        phase=phase,
        node_name=node_name,
        reason=reason,
        allowed_domain_tools=allowed_tool_names(phase),
    )


def _tool_action(
    phase: WorkflowPhase,
    domain_tool_name: str,
    reason: str,
    *,
    payload: dict[str, object] | None = None,
) -> ControllerAction:
    return ControllerAction(
        action_type="run_domain_tool",
        phase=phase,
        domain_tool_name=domain_tool_name,
        reason=reason,
        allowed_domain_tools=allowed_tool_names(phase),
        payload=payload or {},
    )


def _unbound_image_ids(state: AgentProjectState) -> list[str]:
    image_ids = {image.image_id for image in state.input_images}
    bound_image_ids = {binding.image_id for binding in state.reference_bindings if binding.explicit_in_user_text}
    return sorted(image_ids - bound_image_ids)


def _concept_has_outputs(state: AgentProjectState) -> bool:
    concept = state.concept_bundle
    if concept is None:
        return False
    return bool(
        concept.final_preview_image_id
        or concept.subject_concept_images
        or concept.scene_concept_image_ids
    )


def _has_pending_review_patches(state: AgentProjectState) -> bool:
    return any(patch.status == "pending" for patch in state.review_patches)


def _concept_approved(state: AgentProjectState) -> bool:
    return state.concept_bundle is not None and state.concept_bundle.approved


def _needed_subject_ids(state: AgentProjectState) -> list[str]:
    if state.scene_spec is None:
        return []
    return [
        subject.subject_id
        for subject in state.scene_spec.subjects
        if subject.needs_3d_asset and subject.asset_strategy in {"hunyuan3d_img2asset", "existing_asset"}
    ]


def _accepted_subject_asset_ids_by_subject(state: AgentProjectState) -> set[str]:
    accepted_statuses = {"succeeded", "accepted_with_warning"}
    return {
        asset.subject_id
        for asset in state.subject_assets
        if asset.status in accepted_statuses and (asset.glb_uri or asset.mesh_uri or asset.obj_uri)
    }


def _missing_subject_asset_ids(state: AgentProjectState) -> list[str]:
    accepted_subject_ids = _accepted_subject_asset_ids_by_subject(state)
    return [subject_id for subject_id in _needed_subject_ids(state) if subject_id not in accepted_subject_ids]


def _selected_subject_concept_artifacts_by_subject(
    state: AgentProjectState,
    *,
    subject_ids: list[str],
) -> dict[str, str]:
    subject_id_set = set(subject_ids)
    selected: dict[str, str] = {}
    for item in state.asset_library:
        if item.asset_kind != "subject_concept":
            continue
        if item.selection_status != "selected_for_model_generation":
            continue
        if item.subject_id is None:
            continue
        if subject_id_set and item.subject_id not in subject_id_set:
            continue
        selected[item.subject_id] = item.artifact_id
    return selected


def _problem_subject_assets(assets: list[Asset3DRecord]) -> list[Asset3DRecord]:
    problem_statuses = {"failed", "uncertain", "distorted", "needs_regen"}
    return [asset for asset in assets if asset.status in problem_statuses]


def _planned_blender_edit_actions(state: AgentProjectState) -> list[ControllerAction]:
    actions: list[ControllerAction] = []
    skip_tools = {"export_viewer_scene", "render_preview"}
    allowed = set(allowed_tool_names(WorkflowPhase.BLENDER_EDIT))
    for patch in state.review_patches:
        if patch.status != "pending":
            continue
        plan = patch.structured_delta.get("blender_edit_plan")
        if not isinstance(plan, dict):
            continue
        calls = plan.get("domain_tool_calls")
        if not isinstance(calls, list):
            continue
        for index, call in enumerate(calls, start=1):
            if not isinstance(call, dict):
                continue
            tool_name = call.get("domain_tool_name")
            if not isinstance(tool_name, str) or tool_name in skip_tools or tool_name not in allowed:
                continue
            arguments = call.get("arguments")
            actions.append(
                _tool_action(
                    WorkflowPhase.BLENDER_EDIT,
                    tool_name,
                    call.get("reason") if isinstance(call.get("reason"), str) else f"planned_blender_edit:{patch.patch_id}:{index}",
                    payload=arguments if isinstance(arguments, dict) else {},
                )
            )
    return actions


def _completed_delivery_package(state: AgentProjectState) -> ArtifactRecord | None:
    for artifact in reversed(state.artifacts):
        if artifact.artifact_type != ArtifactType.EXPORT_PACKAGE:
            continue
        if artifact.metadata.get("ok") is not True:
            continue
        if Path(artifact.uri).expanduser().is_file():
            return artifact
    return None
