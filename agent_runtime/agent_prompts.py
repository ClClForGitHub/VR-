"""Prompt contracts for controlled V1 LLM/MLLM nodes."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.domain_tools import allowed_tool_names
from agent_runtime.reference_intake import ReferenceBindingPlan
from agent_runtime.state import (
    BlenderAssemblyPlan,
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
    negative_prompt: str | None = None


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
        responsibility="Create prompts for final preview, subject concepts, and scene concepts.",
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


def concept_prompt_pack_from_planner_output(output: ConceptPromptPlannerOutput) -> ConceptPromptPack:
    return ConceptPromptPack(
        final_preview_prompt=output.final_preview_prompt,
        subject_prompts=output.subject_prompts,
        scene_prompts=output.scene_prompts,
        negative_prompt=output.negative_prompt,
    )


def _schema_for_model(model: type[BaseModel]) -> dict[str, Any]:
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()
    return model.schema()
