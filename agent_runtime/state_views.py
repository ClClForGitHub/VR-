"""Context views and state mutation guards from DOC-004.

This module derives small, node-specific views from AgentProjectState. It does
not introduce another fact source: all data comes from the project state, and
updates to controlled fact-source fields pass through node ownership guards.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_runtime.domain_tools import allowed_tool_names
from agent_runtime.state import (
    AgentProjectState,
    BlenderAssemblyPlannerContext,
    BlenderEditRouterContext,
    ConceptBundle,
    ConceptPromptPlannerContext,
    InputImage,
    ReferenceBinding,
    ReviewPatch,
    SceneInterpreterContext,
    WorkflowPhase,
)


CONTROLLED_STATE_FIELD_OWNERS: dict[str, frozenset[str]] = {
    "scene_spec": frozenset(
        {
            "SceneSpecCompiler",
            "FeedbackPatchParser",
            "RegenerationRouter",
            "OperatorRepairTool",
        }
    ),
    "concept_bundle": frozenset(
        {
            "ConceptPromptPlanner",
            "ImageGenerationExecutor",
            "ConceptVisualQA",
            "ConceptReviewGate",
        }
    ),
    "subject_assets": frozenset(
        {
            "SubjectAssetGenerationExecutor",
            "SubjectAssetQualityEvaluator",
            "SubjectAssetRepairRouter",
        }
    ),
    "scene_asset": frozenset(
        {
            "SceneGenerationExecutor",
            "SceneAssetAdapter",
            "SceneAssetQA",
        }
    ),
    "blender_scene": frozenset(
        {
            "BlenderCommandExecutor",
            "SceneStateSynchronizer",
            "BlenderPreviewRenderer",
            "BlenderEditRouter",
        }
    ),
    "blender_assembly_plan": frozenset(
        {
            "BlenderAssemblyPlanner",
        }
    ),
    "viewer_scene": frozenset(
        {
            "ScenePreviewExporter",
            "ViewerSyncService",
            "FrontendInteractionAdapter",
        }
    ),
}


class MissingStateContextError(ValueError):
    """Raised when a context view cannot be built from the current state."""


class StateMutationError(ValueError):
    """Raised when a node attempts to update a field it does not own."""


def build_scene_interpreter_context(
    state: AgentProjectState,
    *,
    user_text: str | None = None,
    turn_id: str | None = None,
) -> SceneInterpreterContext:
    """Build DOC-004 SceneInterpreterContext from the latest or selected turn."""

    state.assert_reference_bindings_are_explicit()
    turn = _select_user_turn(state, turn_id=turn_id) if user_text is None or turn_id else None
    resolved_text = user_text if user_text is not None else turn.text if turn is not None else None
    if not resolved_text:
        raise MissingStateContextError("SceneInterpreterContext requires user_text or at least one user turn")

    selected_image_ids = turn.image_ids if turn is not None and turn.image_ids else None
    input_images = _select_input_images(state.input_images, selected_image_ids)
    declared_bindings = _select_reference_bindings(state.reference_bindings, selected_image_ids)
    return SceneInterpreterContext(
        user_text=resolved_text,
        input_images=input_images,
        declared_bindings=declared_bindings,
    )


def build_concept_prompt_planner_context(
    state: AgentProjectState,
) -> ConceptPromptPlannerContext:
    if state.scene_spec is None:
        raise MissingStateContextError("ConceptPromptPlannerContext requires state.scene_spec")
    return ConceptPromptPlannerContext(
        scene_spec=state.scene_spec,
        active_review_patches=_active_review_patches(state.review_patches),
        prior_prompt_pack_summary=summarize_prompt_pack(state.concept_bundle),
        reference_bindings=_select_reference_bindings(
            state.reference_bindings,
            _scene_spec_reference_image_ids(state.scene_spec),
        ),
    )


def build_blender_assembly_planner_context(
    state: AgentProjectState,
    *,
    tool_phase: WorkflowPhase = WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
) -> BlenderAssemblyPlannerContext:
    if state.scene_spec is None:
        raise MissingStateContextError("BlenderAssemblyPlannerContext requires state.scene_spec")
    return BlenderAssemblyPlannerContext(
        scene_spec=state.scene_spec,
        subject_assets=list(state.subject_assets),
        scene_asset=state.scene_asset,
        concept_bundle_summary=summarize_concept_bundle(state.concept_bundle),
        latest_preview_image_id=_latest_preview_image_id(state),
        latest_viewer_scene_id=state.viewer_scene.viewer_scene_id if state.viewer_scene is not None else None,
        allowed_domain_tools=allowed_tool_names(tool_phase),
    )


def build_blender_edit_router_context(
    state: AgentProjectState,
    *,
    user_edit_text: str | None = None,
    turn_id: str | None = None,
) -> BlenderEditRouterContext:
    if state.scene_spec is None:
        raise MissingStateContextError("BlenderEditRouterContext requires state.scene_spec")
    if state.blender_scene is None:
        raise MissingStateContextError("BlenderEditRouterContext requires state.blender_scene")

    turn = _select_user_turn(state, turn_id=turn_id) if user_edit_text is None or turn_id else None
    resolved_text = user_edit_text if user_edit_text is not None else turn.text if turn is not None else None
    if not resolved_text:
        raise MissingStateContextError("BlenderEditRouterContext requires user_edit_text or a user turn")

    return BlenderEditRouterContext(
        user_edit_text=resolved_text,
        blender_scene=state.blender_scene,
        scene_spec=state.scene_spec,
        latest_preview_image_id=_latest_preview_image_id(state),
        latest_viewer_scene_id=state.viewer_scene.viewer_scene_id if state.viewer_scene is not None else None,
        allowed_edit_tools=allowed_tool_names(WorkflowPhase.BLENDER_EDIT),
    )


def summarize_prompt_pack(concept_bundle: ConceptBundle | None) -> str | None:
    if concept_bundle is None or concept_bundle.prompt_pack is None:
        return None
    prompt_pack = concept_bundle.prompt_pack
    return (
        f"concept_version={concept_bundle.concept_version}; "
        f"final_preview_prompt_chars={len(prompt_pack.final_preview_prompt)}; "
        f"subject_prompt_count={len(prompt_pack.subject_prompts)}; "
        f"scene_prompt_count={len(prompt_pack.scene_prompts)}; "
        f"has_negative_prompt={bool(prompt_pack.negative_prompt)}; "
        f"approved={concept_bundle.approved}"
    )


def summarize_concept_bundle(concept_bundle: ConceptBundle | None) -> str | None:
    if concept_bundle is None:
        return None
    visual_qa = concept_bundle.visual_qa
    qa_summary = "visual_qa=none"
    if visual_qa is not None:
        qa_summary = f"visual_qa_ok={visual_qa.ok}; visual_qa_score={visual_qa.score}"
    return (
        f"concept_version={concept_bundle.concept_version}; "
        f"approved={concept_bundle.approved}; "
        f"final_preview_image_id={concept_bundle.final_preview_image_id}; "
        f"subject_concept_subject_count={len(concept_bundle.subject_concept_images)}; "
        f"scene_concept_image_count={len(concept_bundle.scene_concept_image_ids)}; "
        f"{qa_summary}"
    )


def controlled_state_fields() -> frozenset[str]:
    return frozenset(CONTROLLED_STATE_FIELD_OWNERS)


def allowed_state_fields_for_node(node_name: str) -> frozenset[str]:
    return frozenset(
        field_name
        for field_name, owners in CONTROLLED_STATE_FIELD_OWNERS.items()
        if node_name in owners
    )


def assert_state_update_allowed(node_name: str, field_name: str) -> None:
    if field_name not in _agent_project_state_field_names():
        raise KeyError(f"unknown AgentProjectState field: {field_name}")
    owners = CONTROLLED_STATE_FIELD_OWNERS.get(field_name)
    if owners is not None and node_name not in owners:
        raise StateMutationError(
            f"{node_name} is not allowed to update {field_name}; "
            f"allowed owners: {sorted(owners)}"
        )


def assert_state_updates_allowed(node_name: str, updates: Mapping[str, Any]) -> None:
    for field_name in updates:
        assert_state_update_allowed(node_name, field_name)


def apply_state_updates(
    state: AgentProjectState,
    *,
    node_name: str,
    updates: Mapping[str, Any],
) -> AgentProjectState:
    """Return a validated copy of state after DOC-004 mutation checks."""

    assert_state_updates_allowed(node_name, updates)
    payload = _model_dump_python(state)
    payload.update(dict(updates))
    return AgentProjectState(**payload)


def _select_user_turn(state: AgentProjectState, *, turn_id: str | None) -> Any:
    if not state.user_turns:
        return None
    if turn_id is None:
        return state.user_turns[-1]
    for turn in state.user_turns:
        if turn.turn_id == turn_id:
            return turn
    raise MissingStateContextError(f"user turn not found: {turn_id}")


def _select_input_images(
    input_images: list[InputImage],
    image_ids: list[str] | None,
) -> list[InputImage]:
    if not image_ids:
        return list(input_images)
    by_id = {image.image_id: image for image in input_images}
    return [by_id[image_id] for image_id in image_ids if image_id in by_id]


def _select_reference_bindings(
    reference_bindings: list[ReferenceBinding],
    image_ids: list[str] | None,
) -> list[ReferenceBinding]:
    selected = [
        binding
        for binding in reference_bindings
        if binding.explicit_in_user_text and (not image_ids or binding.image_id in image_ids)
    ]
    return selected


def _scene_spec_reference_image_ids(scene_spec: SceneSpec | None) -> list[str] | None:
    if scene_spec is None:
        return None
    image_ids: list[str] = []
    image_ids.extend(scene_spec.environment.scene_reference_image_ids)
    for subject in scene_spec.subjects:
        image_ids.extend(subject.reference_image_ids)
    return image_ids or None


def _active_review_patches(review_patches: list[ReviewPatch]) -> list[ReviewPatch]:
    return [patch for patch in review_patches if patch.status == "pending"]


def _latest_preview_image_id(state: AgentProjectState) -> str | None:
    if state.blender_scene is not None and state.blender_scene.preview_image_id:
        return state.blender_scene.preview_image_id
    if state.concept_bundle is not None:
        return state.concept_bundle.final_preview_image_id
    return None


def _agent_project_state_field_names() -> frozenset[str]:
    if hasattr(AgentProjectState, "model_fields"):
        return frozenset(AgentProjectState.model_fields)
    return frozenset(AgentProjectState.__fields__)


def _model_dump_python(state: AgentProjectState) -> dict[str, Any]:
    if hasattr(state, "model_dump"):
        return state.model_dump(mode="python")
    return state.dict()
