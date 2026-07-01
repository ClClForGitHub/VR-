"""Prompt contracts for controlled V1 LLM/MLLM nodes."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.domain_tools import allowed_tool_names
from agent_runtime.reference_intake import ReferenceBindingPlan
from agent_runtime.state import (
    BlenderAssemblyPlan,
    ConceptImageRequirement,
    ConceptPromptPack,
    ReviewPatch,
    SceneSpec,
    UserIntent,
    VisualQAResult,
    WorkflowPhase,
)


class UserIntentRouterOutput(BaseModel):
    intent: UserIntent | None = None
    confidence: float | None = None
    requires_clarification: bool = False
    clarification_question: str | None = None
    route_reason: str | None = None


class ReferenceBindingValidatorOutput(BaseModel):
    valid_bindings: list[ReferenceBindingPlan] = Field(default_factory=list)
    requires_clarification: bool = False
    open_questions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class SceneInterpreterOutput(BaseModel):
    user_goal: str
    subject_summaries: list[str] = Field(default_factory=list)
    environment_summary: str | None = None
    style_summary: str | None = None
    open_questions: list[str] = Field(default_factory=list)


class ConceptPromptPlannerOutput(BaseModel):
    final_preview_prompt: str
    subject_prompts: dict[str, str] = Field(default_factory=dict)
    scene_prompts: list[str] = Field(default_factory=list)
    image_requirements: list[ConceptImageRequirement] = Field(default_factory=list)
    negative_prompt: str | None = None
    requires_clarification: bool = False
    open_questions: list[str] = Field(default_factory=list)
    identity_notes: list[str] = Field(default_factory=list)


class FeedbackPatchParserOutput(BaseModel):
    patches: list[ReviewPatch] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_question: str | None = None


class RegenerationRouterOutput(BaseModel):
    route: Literal[
        "regenerate_concept",
        "redo_subject_asset",
        "redo_scene_asset",
        "blender_edit",
        "ask_user",
    ]
    affected_artifact_ids: list[str] = Field(default_factory=list)
    next_phase: WorkflowPhase
    reason: str


class SceneAssetAdapterPlannerOutput(BaseModel):
    import_mode: Literal[
        "mesh_import",
        "3dgs_layer",
        "point_cloud_proxy",
        "depth_camera_scaffold",
        "visual_reference_only",
        "procedural_proxy",
    ]
    notes: str | None = None
    requires_proxy_scene: bool = False


class BlenderPreviewReviewGateOutput(BaseModel):
    approved: bool = False
    route: Literal["deliver", "blender_edit", "redo_subject", "redo_scene", "ask_user"]
    patches: list[ReviewPatch] = Field(default_factory=list)
    requires_clarification: bool = False
    reason: str | None = None


class BlenderEditDomainToolCall(BaseModel):
    domain_tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    patch_id: str | None = None


class BlenderEditRouterOutput(BaseModel):
    route: Literal["pure_blender_edit", "redo_subject", "redo_scene", "return_to_concept", "ask_user"]
    patches: list[ReviewPatch] = Field(default_factory=list)
    allowed_domain_tool_names: list[str] = Field(default_factory=list)
    domain_tool_calls: list[BlenderEditDomainToolCall] = Field(default_factory=list)
    reason: str


class PromptNodeSpec(BaseModel):
    node_name: str
    phase: WorkflowPhase
    responsibility: str
    output_model_name: str
    context_keys: list[str] = Field(default_factory=list)
    uses_mllm: bool = False
    user_gate: bool = False
    may_execute_tools: bool = False
    allowed_domain_tools: list[str] = Field(default_factory=list)


class BuiltNodePrompt(BaseModel):
    node_name: str
    phase: WorkflowPhase
    system_prompt: str
    output_schema: dict[str, Any]
    allowed_domain_tools: list[str] = Field(default_factory=list)


OUTPUT_MODELS_BY_NODE: dict[str, type[BaseModel]] = {
    "UserIntentRouter": UserIntentRouterOutput,
    "ReferenceBindingValidator": ReferenceBindingValidatorOutput,
    "SceneInterpreter": SceneInterpreterOutput,
    "SceneSpecCompiler": SceneSpec,
    "ConceptPromptPlanner": ConceptPromptPlannerOutput,
    "ConceptVisualQA": VisualQAResult,
    "FeedbackPatchParser": FeedbackPatchParserOutput,
    "RegenerationRouter": RegenerationRouterOutput,
    "SceneAssetAdapterPlanner": SceneAssetAdapterPlannerOutput,
    "BlenderAssemblyPlanner": BlenderAssemblyPlan,
    "BlenderPreviewReviewGate": BlenderPreviewReviewGateOutput,
    "BlenderEditRouter": BlenderEditRouterOutput,
}


NODE_SPECS: dict[str, PromptNodeSpec] = {
    "UserIntentRouter": PromptNodeSpec(
        node_name="UserIntentRouter",
        phase=WorkflowPhase.INTAKE,
        responsibility="Classify the user turn under the current phase without changing state.",
        output_model_name="UserIntentRouterOutput",
        context_keys=["phase", "latest_user_turn", "pending_action"],
    ),
    "ReferenceBindingValidator": PromptNodeSpec(
        node_name="ReferenceBindingValidator",
        phase=WorkflowPhase.INTAKE,
        responsibility="Validate explicit image-purpose declarations and request clarification when missing.",
        output_model_name="ReferenceBindingValidatorOutput",
        context_keys=["user_text", "input_images", "declared_bindings"],
    ),
    "SceneInterpreter": PromptNodeSpec(
        node_name="SceneInterpreter",
        phase=WorkflowPhase.SCENE_SPEC_DRAFT,
        responsibility="Extract scene intent, subjects, environment, style, and open questions.",
        output_model_name="SceneInterpreterOutput",
        context_keys=["user_text", "input_images", "reference_bindings"],
        uses_mllm=True,
    ),
    "SceneSpecCompiler": PromptNodeSpec(
        node_name="SceneSpecCompiler",
        phase=WorkflowPhase.SCENE_SPEC_DRAFT,
        responsibility="Normalize interpretation and bindings into a validated SceneSpec candidate.",
        output_model_name="SceneSpec",
        context_keys=["interpretation", "reference_bindings", "previous_scene_spec"],
        allowed_domain_tools=allowed_tool_names(WorkflowPhase.SCENE_SPEC_DRAFT),
    ),
    "ConceptPromptPlanner": PromptNodeSpec(
        node_name="ConceptPromptPlanner",
        phase=WorkflowPhase.CONCEPT_GENERATION,
        responsibility=(
            "Create prompts and review requirements for subject concept images, scene concept images, "
            "and the final target render composition."
        ),
        output_model_name="ConceptPromptPlannerOutput",
        context_keys=["scene_spec", "active_review_patches", "reference_bindings"],
        allowed_domain_tools=allowed_tool_names(WorkflowPhase.CONCEPT_GENERATION),
    ),
    "ConceptVisualQA": PromptNodeSpec(
        node_name="ConceptVisualQA",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        responsibility="Check generated concept images against the SceneSpec and references.",
        output_model_name="VisualQAResult",
        context_keys=["scene_spec", "concept_bundle", "reference_bindings"],
        uses_mllm=True,
    ),
    "FeedbackPatchParser": PromptNodeSpec(
        node_name="FeedbackPatchParser",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        responsibility="Parse user feedback into ReviewPatch records without applying them.",
        output_model_name="FeedbackPatchParserOutput",
        context_keys=["user_feedback", "phase", "scene_spec", "concept_bundle"],
        user_gate=True,
        allowed_domain_tools=allowed_tool_names(WorkflowPhase.CONCEPT_REVIEW),
    ),
    "RegenerationRouter": PromptNodeSpec(
        node_name="RegenerationRouter",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        responsibility="Route ReviewPatch records to concept regeneration, 3D redo, Blender edit, or clarification.",
        output_model_name="RegenerationRouterOutput",
        context_keys=["review_patches", "current_phase", "artifact_summary"],
    ),
    "SceneAssetAdapterPlanner": PromptNodeSpec(
        node_name="SceneAssetAdapterPlanner",
        phase=WorkflowPhase.SCENE_ASSET_ADAPTATION,
        responsibility="Plan how a scene service output should be adapted into Blender-consumable artifacts.",
        output_model_name="SceneAssetAdapterPlannerOutput",
        context_keys=["scene_spec", "scene_generation_output_summary"],
        allowed_domain_tools=allowed_tool_names(WorkflowPhase.SCENE_ASSET_GENERATION),
    ),
    "BlenderAssemblyPlanner": PromptNodeSpec(
        node_name="BlenderAssemblyPlanner",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_PLANNING,
        responsibility="Plan imports, placement, camera, and lighting for the authoritative Blender scene.",
        output_model_name="BlenderAssemblyPlan",
        context_keys=["scene_spec", "subject_assets", "scene_asset", "concept_bundle_summary"],
        allowed_domain_tools=allowed_tool_names(WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION),
    ),
    "BlenderPreviewReviewGate": PromptNodeSpec(
        node_name="BlenderPreviewReviewGate",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        responsibility="Decide whether user preview feedback approves delivery or routes edits/redos.",
        output_model_name="BlenderPreviewReviewGateOutput",
        context_keys=["user_feedback", "viewer_scene", "blender_preview", "scene_spec"],
        user_gate=True,
    ),
    "BlenderEditRouter": PromptNodeSpec(
        node_name="BlenderEditRouter",
        phase=WorkflowPhase.BLENDER_EDIT,
        responsibility="Route a user edit request to safe Blender domain tools or upstream regeneration.",
        output_model_name="BlenderEditRouterOutput",
        context_keys=["user_edit_text", "blender_scene", "scene_spec", "allowed_edit_tools"],
        allowed_domain_tools=allowed_tool_names(WorkflowPhase.BLENDER_EDIT),
    ),
}


def get_prompt_node_spec(node_name: str) -> PromptNodeSpec:
    try:
        return NODE_SPECS[node_name]
    except KeyError as exc:
        raise KeyError(f"unknown prompt node: {node_name}") from exc


def build_node_prompt(
    node_name: str,
    *,
    context_json: dict[str, Any],
    output_model: type[BaseModel] | None = None,
) -> BuiltNodePrompt:
    spec = get_prompt_node_spec(node_name)
    model = output_model or OUTPUT_MODELS_BY_NODE[node_name]
    output_schema = _schema_for_model(model)
    context_text = json.dumps(context_json, ensure_ascii=False, sort_keys=True, indent=2)
    schema_text = json.dumps(output_schema, ensure_ascii=False, sort_keys=True, indent=2)
    allowed_tools_text = ", ".join(spec.allowed_domain_tools) if spec.allowed_domain_tools else "none"
    system_prompt = (
        f"You are {spec.node_name}.\n"
        f"Current task: {spec.responsibility}\n"
        f"Current WorkflowPhase: {spec.phase.value}.\n"
        f"Allowed domain tools for planning only: {allowed_tools_text}.\n"
        "Use only the supplied context_json. Do not use hidden conversation memory as fact.\n"
        "Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, "
        "file paths, or tool results.\n"
        "If required information is missing, set the model's clarification/open-question fields "
        "instead of guessing.\n"
        f"{_node_specific_prompt_rules(spec.node_name)}"
        "Output only one JSON object. Do not include Markdown or extra natural language.\n"
        "context_json:\n"
        f"{context_text}\n"
        "output_json_schema:\n"
        f"{schema_text}\n"
    )
    return BuiltNodePrompt(
        node_name=spec.node_name,
        phase=spec.phase,
        system_prompt=system_prompt,
        output_schema=output_schema,
        allowed_domain_tools=list(spec.allowed_domain_tools),
    )


def _node_specific_prompt_rules(node_name: str) -> str:
    if node_name != "ConceptPromptPlanner":
        return ""
    return (
        "ConceptPromptPlanner rules:\n"
        "- Treat scene_spec as the source of truth for subjects, environment, camera, lighting, "
        "props, and constraints.\n"
        "- For any subject that names an IP, franchise, game, anime, brand, or specific "
        "character, require explicit identity research evidence before writing generation "
        "prompts. If this node is delegated to an agent/MCP channel with web-search capability, "
        "that agent must search the web for the character/IP, prefer official sources, and "
        "summarize the verified identity in context before prompt writing. If no search evidence "
        "is present in context_json, do not rely on model memory; set requires_clarification=true "
        "or add identity_notes describing the missing research.\n"
        "- Preserve exact subject identity. Use display_name, canonical_identity, identity_aliases, "
        "source_text_span, and reference_image_ids when present. Do not silently substitute or "
        "rename a character. If identity is uncertain, set requires_clarification=true and add "
        "open_questions.\n"
        "- For every scene_spec subject with needs_2d_concept=true, create exactly one "
        "subject_prompts entry keyed by subject_id. Do not create subject prompts for procedural "
        "props or scene-service components.\n"
        "- Subject concept prompts must be subject-only: clean studio/neutral background, full "
        "body or whole vehicle, readable silhouette, no scene environment, no unrelated props. "
        "When the subject has reference_image_ids or a subject_reference binding, the matching "
        "image_requirement must list those ids in input_reference_image_ids, set "
        "generation_mode='image_guided', and the prompt must explicitly preserve identity from "
        "those input images. Downstream image-generation MCP calls must attach/upload those "
        "reference image files as actual image inputs, not merely mention them in text.\n"
        "- Scene concept prompts must be scene-only: environment, terrain, props, layout, "
        "lighting direction, and camera staging. They must exclude hero subjects and characters. "
        "When scene_reference images exist, list them in input_reference_image_ids.\n"
        "- The final_preview_prompt is not a substitute for subject/scene prompts. It must be an "
        "art-directed target render prompt that combines the generated subject_concept image(s) "
        "and scene_concept image(s) as visual references. Its target_render image_requirement "
        "must set generation_mode='multi_image_composite' and source_requirement_ids to the "
        "subject_concept and scene_concept requirements it depends on. Downstream MCP calls must "
        "attach/upload the resolved source images for those source_requirement_ids.\n"
        "- Use a higher beauty bar for the final target render: polished composition, appealing "
        "camera, coherent light direction, clear face/front orientation for characters, and "
        "enough scale to inspect the main subject.\n"
        "- Keep uploaded user references scoped to their declared binding. A subject reference "
        "must not become scene content; a scene reference must not overwrite subject identity.\n"
    )


def concept_prompt_pack_from_planner_output(
    output: ConceptPromptPlannerOutput,
    *,
    scene_spec: SceneSpec | None = None,
) -> ConceptPromptPack:
    default_requirements = _default_concept_image_requirements(
        output=output,
        scene_spec=scene_spec,
    )
    image_requirements = _enrich_concept_image_requirements(
        provided=list(output.image_requirements),
        defaults=default_requirements,
        scene_spec=scene_spec,
    )
    return ConceptPromptPack(
        final_preview_prompt=output.final_preview_prompt,
        subject_prompts=output.subject_prompts,
        scene_prompts=output.scene_prompts,
        image_requirements=image_requirements,
        negative_prompt=output.negative_prompt,
    )


def _enrich_concept_image_requirements(
    *,
    provided: list[ConceptImageRequirement],
    defaults: list[ConceptImageRequirement],
    scene_spec: SceneSpec | None,
) -> list[ConceptImageRequirement]:
    if not provided:
        return defaults

    defaults_by_id = {item.requirement_id: item for item in defaults}
    enriched: list[ConceptImageRequirement] = []
    for item in provided:
        default = defaults_by_id.get(item.requirement_id)
        if default is None:
            enriched.append(item)
            continue
        updates: dict[str, Any] = {}
        if not item.input_reference_image_ids and default.input_reference_image_ids:
            updates["input_reference_image_ids"] = list(default.input_reference_image_ids)
        if not item.source_requirement_ids and default.source_requirement_ids:
            updates["source_requirement_ids"] = list(default.source_requirement_ids)
        if item.generation_mode == "text_to_image" and default.generation_mode != "text_to_image":
            updates["generation_mode"] = default.generation_mode
        if not item.must_use_image_inputs and default.must_use_image_inputs:
            updates["must_use_image_inputs"] = True
        if item.quality_bar is None and default.quality_bar is not None:
            updates["quality_bar"] = default.quality_bar
        enriched.append(item.model_copy(update=updates) if hasattr(item, "model_copy") else item.copy(update=updates))

    provided_ids = {item.requirement_id for item in enriched}
    enriched.extend(item for item in defaults if item.requirement_id not in provided_ids)
    return _with_target_render_dependencies(enriched, scene_spec=scene_spec)


def _default_concept_image_requirements(
    *,
    output: ConceptPromptPlannerOutput,
    scene_spec: SceneSpec | None,
) -> list[ConceptImageRequirement]:
    requirements: list[ConceptImageRequirement] = []
    required_subject_ids = _required_subject_concept_ids(scene_spec, output)
    for subject_id in required_subject_ids:
        reference_image_ids = _subject_reference_image_ids(scene_spec, subject_id)
        requirements.append(
            ConceptImageRequirement(
                requirement_id=f"subject_concept:{subject_id}",
                output_type="subject_concept",
                target_id=subject_id,
                prompt_key=f"subject_prompts.{subject_id}",
                user_review_label=f"主体概念图：{_subject_display_name(scene_spec, subject_id)}",
                purpose="Lock the subject identity, proportions, and image-to-3D source view before asset generation.",
                generation_mode="image_guided" if reference_image_ids else "text_to_image",
                input_reference_image_ids=reference_image_ids,
                must_use_image_inputs=bool(reference_image_ids),
                quality_bar="identity-preserving, clean full-body/whole-subject source image for 3D",
            )
        )
    for index, _prompt in enumerate(output.scene_prompts, start=1):
        scene_reference_image_ids = _scene_reference_image_ids(scene_spec)
        requirements.append(
            ConceptImageRequirement(
                requirement_id=f"scene_concept:{index}",
                output_type="scene_concept",
                target_id=scene_spec.scene_id if scene_spec is not None else None,
                prompt_key=f"scene_prompts.{index - 1}",
                user_review_label="场景概念图" if len(output.scene_prompts) == 1 else f"场景概念图 {index}",
                purpose="Lock the environment, props, lighting direction, and spatial layout separate from subject identity.",
                generation_mode="image_guided" if scene_reference_image_ids else "text_to_image",
                input_reference_image_ids=scene_reference_image_ids,
                must_use_image_inputs=bool(scene_reference_image_ids),
                quality_bar="scene-only layout reference with coherent ground, props, lighting, and empty subject placement space",
            )
        )
    requirements.append(
        ConceptImageRequirement(
            requirement_id="target_render:final_preview",
            output_type="target_render",
            target_id=scene_spec.scene_id if scene_spec is not None else None,
            prompt_key="final_preview_prompt",
            user_review_label="最终渲染构图图",
            purpose="Show the intended final composition for user review before 3D generation and Blender assembly.",
            generation_mode="multi_image_composite",
            source_requirement_ids=[
                item.requirement_id
                for item in requirements
                if item.output_type in {"subject_concept", "scene_concept"}
            ],
            must_use_image_inputs=True,
            quality_bar="high-artistry target render using generated subject and scene concepts as references",
        )
    )
    return requirements


def _required_subject_concept_ids(
    scene_spec: SceneSpec | None,
    output: ConceptPromptPlannerOutput,
) -> list[str]:
    if scene_spec is None:
        return list(output.subject_prompts)
    return [
        subject.subject_id
        for subject in scene_spec.subjects
        if subject.needs_2d_concept and subject.subject_id in output.subject_prompts
    ]


def _subject_display_name(scene_spec: SceneSpec | None, subject_id: str) -> str:
    if scene_spec is not None:
        for subject in scene_spec.subjects:
            if subject.subject_id == subject_id:
                return subject.display_name
    return subject_id


def _subject_reference_image_ids(scene_spec: SceneSpec | None, subject_id: str) -> list[str]:
    if scene_spec is None:
        return []
    for subject in scene_spec.subjects:
        if subject.subject_id == subject_id:
            return list(subject.reference_image_ids)
    return []


def _scene_reference_image_ids(scene_spec: SceneSpec | None) -> list[str]:
    if scene_spec is None:
        return []
    return list(scene_spec.environment.scene_reference_image_ids)


def _with_target_render_dependencies(
    requirements: list[ConceptImageRequirement],
    *,
    scene_spec: SceneSpec | None,
) -> list[ConceptImageRequirement]:
    dependency_ids = [
        item.requirement_id
        for item in requirements
        if item.output_type in {"subject_concept", "scene_concept"}
    ]
    if not dependency_ids:
        return requirements
    updated: list[ConceptImageRequirement] = []
    for item in requirements:
        if item.output_type != "target_render":
            updated.append(item)
            continue
        updates: dict[str, Any] = {
            "source_requirement_ids": list(item.source_requirement_ids or dependency_ids),
            "generation_mode": "multi_image_composite",
            "must_use_image_inputs": True,
        }
        if item.quality_bar is None:
            updates["quality_bar"] = "high-artistry target render using generated subject and scene concepts as references"
        updated.append(item.model_copy(update=updates) if hasattr(item, "model_copy") else item.copy(update=updates))
    return updated


def _schema_for_model(model: type[BaseModel]) -> dict[str, Any]:
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()
    return model.schema()
