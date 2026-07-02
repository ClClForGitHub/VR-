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


class IdentitySearchEvidence(BaseModel):
    subject_id: str
    requested_name: str | None = None
    resolved_identity: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    source_titles: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    visual_traits: list[str] = Field(default_factory=list)
    confidence: float | None = None
    issues: list[str] = Field(default_factory=list)


class ConceptPromptPlannerOutput(BaseModel):
    final_preview_prompt: str
    subject_prompts: dict[str, str] = Field(default_factory=dict)
    scene_prompts: list[str] = Field(default_factory=list)
    image_requirements: list[ConceptImageRequirement] = Field(default_factory=list)
    negative_prompt: str | None = None
    requires_clarification: bool = False
    open_questions: list[str] = Field(default_factory=list)
    identity_notes: list[str] = Field(default_factory=list)
    identity_search_evidence: list[IdentitySearchEvidence] = Field(default_factory=list)


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
        responsibility=(
            "Validate explicit purpose declarations for already uploaded reference images. "
            "If no images were uploaded, return no bindings and do not block text-only generation."
        ),
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
        "Use supplied context_json as project/runtime fact. For nodes that explicitly require "
        "provider web search, use provider-returned public search evidence only for external "
        "identity/appearance facts; do not use hidden conversation memory as fact.\n"
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
    if node_name == "ReferenceBindingValidator":
        return (
            "ReferenceBindingValidator rules:\n"
            "- This node only validates uploaded/reference image bindings. It must not request optional "
            "reference images for a text-only request.\n"
            "- If context_json.input_images is empty, output valid_bindings=[], requires_clarification=false, "
            "open_questions=[], and issues=[]. Let SceneSpecCompiler and ConceptPromptPlanner handle "
            "named character identity through provider web search.\n"
            "- Set requires_clarification=true only when an uploaded image exists but its user-declared "
            "purpose or target is ambiguous, missing, or contradictory.\n"
        )
    if node_name == "SceneInterpreter":
        return (
            "SceneInterpreter rules:\n"
            "- Do not turn ordinary missing art-direction details into open_questions. If the user omits "
            "pose, time of day, exact prop placement, camera, or mood, summarize a sensible default instead.\n"
            "- For named IP/game/anime/brand characters, preserve the exact user-written names and IP in "
            "subject_summaries. Do not ask the user to describe official appearances when identity research "
            "can be supplied downstream.\n"
        )
    if node_name == "SceneSpecCompiler":
        return (
            "SceneSpecCompiler rules:\n"
            "- For named IP/game/anime/brand characters, provider-level web search is allowed and expected "
            "when available. Search the exact user name plus IP/game title before writing appearance notes.\n"
            "- Treat context_json.identity_research as hints only. Verify them against provider web search; "
            "if search evidence conflicts with context_json.identity_research, prefer the search evidence "
            "and preserve the user's requested subject identity.\n"
            "- Use verified evidence to resolve canonical_identity, aliases, and concrete appearance notes "
            "for named IP/game/anime/brand characters.\n"
            "- Do not put 'needs official source/search confirmation' or incomplete visual research into "
            "open_questions. Preserve the requested character identity with lower identity_confidence and "
            "let ConceptPromptPlanner perform stricter identity_search_evidence collection.\n"
            "- If an identity_research row provides subject_id_hint for a requested subject, use that stable "
            "subject_id unless it conflicts with another subject.\n"
            "- Preserve user text spans and stable subject ids derived from the user names when possible. "
            "Do not silently rename a character to a different role.\n"
            "- Do not create open_questions for optional creative choices such as pose, time of day, exact "
            "prop placement, camera, or mood; choose clear defaults that fit the request.\n"
            "- For primary requested character, vehicle, prop, furniture, or architecture subjects that the "
            "user expects to appear as individual Blender assets, set needs_3d_asset=true. Set needs_3d_asset=false "
            "only for background environment details that should remain part of the scene/world asset.\n"
            "- Only keep open_questions for information the user must answer, such as ambiguous image "
            "bindings, multiple possible requested subjects, or contradictory user intent.\n"
        )
    if node_name != "ConceptPromptPlanner":
        return ""
    return (
        "ConceptPromptPlanner rules:\n"
        "- Treat scene_spec as the source of truth for subjects, environment, camera, lighting, "
        "props, and constraints.\n"
        "- For any subject that names an IP, franchise, game, anime, brand, or specific "
        "character, provider-level web search is allowed and expected when available. Search the web "
        "for the exact character name plus IP/game title before writing subject_prompts. Prefer official "
        "publisher pages; if official pages lack visual details, add a reliable secondary source and "
        "record both URLs.\n"
        "- In live runtime, provider web search may already be enabled for this node. Do not claim "
        "'no provider web search available' unless context_json.provider_web_search explicitly says it "
        "is disabled or unavailable.\n"
        "- Treat context_json.identity_research rows with ok=true, source_urls, and visual_traits as "
        "explicit Codex/web-search evidence. If fresh provider search is unavailable or source snippets "
        "are not exposed by the provider, copy and normalize those rows into identity_search_evidence "
        "instead of asking the user to describe official appearances.\n"
        "- If fresh provider search conflicts with context_json.identity_research, prefer the fresh "
        "search evidence and mention the conflict in identity_notes.\n"
        "- For every named/IP subject, populate identity_search_evidence with subject_id, requested_name, "
        "resolved_identity, source_urls, source_titles when available, search_queries, and concrete "
        "visual_traits used in the prompt. Visual traits must be specific enough to draw: hair color/style, "
        "eye color, outfit colors/materials, silhouette/accessories, weapon/instrument/motif when visible. "
        "Generic traits such as 'female character' or 'official design' are not enough.\n"
        "- Also include an identity_notes entry summarizing the evidence and any conflict resolution. If "
        "no web/search evidence can be produced for a named/IP subject, set requires_clarification=true "
        "and add an open_question instead of generating that subject from memory.\n"
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
    matched_defaults: dict[str, ConceptImageRequirement] = {}
    used_default_ids: set[str] = set()
    id_aliases: dict[str, str] = {}
    for item in provided:
        default = defaults_by_id.get(item.requirement_id)
        if default is None:
            default = _semantic_default_for_requirement(item, defaults, used_default_ids)
        if default is None:
            continue
        matched_defaults[item.requirement_id] = default
        used_default_ids.add(default.requirement_id)
        if item.requirement_id != default.requirement_id:
            id_aliases[item.requirement_id] = default.requirement_id

    enriched: list[ConceptImageRequirement] = []
    for item in provided:
        default = matched_defaults.get(item.requirement_id)
        if default is None:
            enriched.append(item)
            continue
        updates: dict[str, Any] = {
            "requirement_id": default.requirement_id,
            "target_id": default.target_id,
            "prompt_key": default.prompt_key,
        }
        mapped_sources = _map_requirement_ids(item.source_requirement_ids, id_aliases)
        if not item.input_reference_image_ids and default.input_reference_image_ids:
            updates["input_reference_image_ids"] = list(default.input_reference_image_ids)
        if mapped_sources:
            updates["source_requirement_ids"] = mapped_sources
        elif default.source_requirement_ids:
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


def _semantic_default_for_requirement(
    item: ConceptImageRequirement,
    defaults: list[ConceptImageRequirement],
    used_default_ids: set[str],
) -> ConceptImageRequirement | None:
    candidates = [default for default in defaults if default.requirement_id not in used_default_ids]
    if item.output_type == "subject_concept" and item.target_id:
        for default in candidates:
            if default.output_type == "subject_concept" and default.target_id == item.target_id:
                return default
    if item.output_type == "scene_concept":
        for default in candidates:
            if default.output_type != "scene_concept":
                continue
            if item.target_id and default.target_id == item.target_id:
                return default
            if item.prompt_key == default.prompt_key:
                return default
        for default in candidates:
            if default.output_type == "scene_concept":
                return default
    if item.output_type == "target_render":
        for default in candidates:
            if default.output_type == "target_render":
                return default
    return None


def _map_requirement_ids(requirement_ids: list[str], aliases: dict[str, str]) -> list[str]:
    mapped: list[str] = []
    seen: set[str] = set()
    for requirement_id in requirement_ids:
        resolved = aliases.get(requirement_id, requirement_id)
        if resolved in seen:
            continue
        mapped.append(resolved)
        seen.add(resolved)
    return mapped


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
