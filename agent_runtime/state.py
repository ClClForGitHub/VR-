"""Pydantic state contracts derived from the V1 Chinese design docs.

Large binaries stay in the artifact store and are represented here only by
artifact ids, URIs, metadata, and small structured state snapshots.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field, field_validator
except ImportError:  # pragma: no cover - compatibility for Pydantic v1 environments
    from pydantic import BaseModel, Field, validator as field_validator


class WorkflowPhase(str, Enum):
    INTAKE = "INTAKE"
    SCENE_SPEC_DRAFT = "SCENE_SPEC_DRAFT"
    SCENE_SPEC_READY = "SCENE_SPEC_READY"
    CONCEPT_GENERATION = "CONCEPT_GENERATION"
    CONCEPT_REVIEW = "CONCEPT_REVIEW"
    CONCEPT_APPROVED = "CONCEPT_APPROVED"
    SUBJECT_ASSET_GENERATION = "SUBJECT_ASSET_GENERATION"
    SUBJECT_ASSET_QA = "SUBJECT_ASSET_QA"
    SCENE_ASSET_GENERATION = "SCENE_ASSET_GENERATION"
    SCENE_ASSET_ADAPTATION = "SCENE_ASSET_ADAPTATION"
    BLENDER_ASSEMBLY_PLANNING = "BLENDER_ASSEMBLY_PLANNING"
    BLENDER_ASSEMBLY_EXECUTION = "BLENDER_ASSEMBLY_EXECUTION"
    BLENDER_PREVIEW = "BLENDER_PREVIEW"
    BLENDER_EDIT = "BLENDER_EDIT"
    DELIVERY = "DELIVERY"
    FAILED = "FAILED"


class UserIntent(str, Enum):
    NEW_SCENE_REQUEST = "NEW_SCENE_REQUEST"
    CONCEPT_FEEDBACK = "CONCEPT_FEEDBACK"
    CONCEPT_APPROVAL = "CONCEPT_APPROVAL"
    BLENDER_EDIT = "BLENDER_EDIT"
    BLENDER_APPROVAL = "BLENDER_APPROVAL"
    SUBJECT_REDO_REQUEST = "SUBJECT_REDO_REQUEST"
    SCENE_REDO_REQUEST = "SCENE_REDO_REQUEST"
    GENERAL_QUESTION = "GENERAL_QUESTION"


class ArtifactType(str, Enum):
    INPUT_IMAGE = "INPUT_IMAGE"
    FINAL_PREVIEW_IMAGE = "FINAL_PREVIEW_IMAGE"
    SUBJECT_CONCEPT_IMAGE = "SUBJECT_CONCEPT_IMAGE"
    SCENE_CONCEPT_IMAGE = "SCENE_CONCEPT_IMAGE"
    SUBJECT_3D_ASSET = "SUBJECT_3D_ASSET"
    SCENE_3D_ASSET = "SCENE_3D_ASSET"
    BLENDER_FILE = "BLENDER_FILE"
    BLENDER_PREVIEW_RENDER = "BLENDER_PREVIEW_RENDER"
    VIEWER_SCENE_GLB = "VIEWER_SCENE_GLB"
    VIEWER_SCENE_GLTF = "VIEWER_SCENE_GLTF"
    VIEWER_SCENE_STATE_JSON = "VIEWER_SCENE_STATE_JSON"
    EXPORT_PACKAGE = "EXPORT_PACKAGE"


class ToolCallStatus(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRIED = "retried"


class UserTurn(BaseModel):
    turn_id: str
    text: str
    image_ids: list[str] = Field(default_factory=list)
    detected_intent: UserIntent | None = None
    phase_at_turn: WorkflowPhase
    created_at: str


class InputImage(BaseModel):
    image_id: str
    artifact_id: str
    uri: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    user_declared_label: str | None = None
    notes: str | None = None


class ReferenceBinding(BaseModel):
    binding_id: str
    image_id: str
    target_type: Literal["subject", "scene", "style", "pose", "texture", "layout"]
    target_id: str | None = None
    usage: Literal[
        "subject_reference",
        "scene_reference",
        "style_reference",
        "pose_reference",
        "texture_reference",
        "layout_reference",
    ]
    explicit_in_user_text: bool = True
    confidence: float = 1.0
    notes: str | None = None

    @field_validator("confidence")
    def confidence_in_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class ArtifactRecord(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    uri: str
    mime_type: str
    project_id: str | None = None
    semantic_role: str | None = None
    linked_subject_id: str | None = None
    linked_scene_id: str | None = None
    created_by_node: str | None = None
    version: int = 1
    size_bytes: int | None = None
    sha256: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("version")
    def version_is_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("version must be positive")
        return value


def _validate_unit_interval(value: float | None, *, field_name: str) -> float | None:
    if value is not None and not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return value


def _validate_positive_version(value: int) -> int:
    if value < 1:
        raise ValueError("version must be positive")
    return value


class StyleSpec(BaseModel):
    style_keywords: list[str] = Field(default_factory=list)
    mood: str | None = None
    color_palette: str | None = None
    rendering_style: str | None = None
    realism_level: Literal[
        "realistic",
        "semi_realistic",
        "stylized",
        "cartoon",
        "illustrative",
    ] | None = None
    notes: str | None = None


class EnvironmentSpec(BaseModel):
    environment_type: str
    description: str
    time_of_day: str | None = None
    weather: str | None = None
    background_elements: list[str] = Field(default_factory=list)
    ground_surface: str | None = None
    scene_reference_image_ids: list[str] = Field(default_factory=list)


class LightingSpec(BaseModel):
    description: str | None = None
    key_light: str | None = None
    fill_light: str | None = None
    rim_light: str | None = None
    ambient: str | None = None
    intensity_hint: str | None = None
    color_temperature: str | None = None


class CameraSpec(BaseModel):
    shot_type: str | None = None
    angle: str | None = None
    lens_hint: str | None = None
    framing: str | None = None
    movement: str | None = None
    target_subject_ids: list[str] = Field(default_factory=list)


class SubjectSpec(BaseModel):
    subject_id: str
    display_name: str
    category: Literal[
        "character",
        "animal",
        "prop",
        "vehicle",
        "furniture",
        "architecture_part",
        "environment_asset",
    ]
    role_in_scene: str | None = None
    description: str
    appearance: str | None = None
    pose_or_state: str | None = None
    reference_image_ids: list[str] = Field(default_factory=list)
    priority: Literal["hero", "important", "background"] = "important"
    needs_2d_concept: bool = True
    needs_3d_asset: bool = True
    asset_strategy: Literal[
        "hunyuan3d_img2asset",
        "blender_primitive",
        "procedural_blender",
        "scene_service_component",
        "existing_asset",
    ] = "hunyuan3d_img2asset"
    preferred_subject_image_view: Literal[
        "three_quarter",
        "front",
        "side",
        "multi_view",
        "unspecified",
    ] = "three_quarter"
    scale_hint: str | None = None
    placement_hint: str | None = None


class SpatialRelation(BaseModel):
    relation_id: str
    source_subject_id: str
    relation: Literal[
        "left_of",
        "right_of",
        "in_front_of",
        "behind",
        "on_top_of",
        "under",
        "near",
        "far_from",
        "inside",
        "surrounding",
        "facing",
        "beside",
        "centered_in",
    ]
    target_subject_id: str | None = None
    target_region: str | None = None
    distance_hint: str | None = None
    scale_hint: str | None = None
    notes: str | None = None


class SceneSpec(BaseModel):
    scene_id: str
    title: str
    user_goal: str
    style: StyleSpec
    environment: EnvironmentSpec
    lighting: LightingSpec
    camera: CameraSpec
    subjects: list[SubjectSpec] = Field(default_factory=list)
    spatial_relations: list[SpatialRelation] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    version: int = 1

    @field_validator("version")
    def version_is_positive(cls, value: int) -> int:
        return _validate_positive_version(value)


class ConceptPromptPack(BaseModel):
    final_preview_prompt: str
    subject_prompts: dict[str, str] = Field(default_factory=dict)
    scene_prompts: list[str] = Field(default_factory=list)
    negative_prompt: str | None = None
    generation_settings: dict[str, Any] = Field(default_factory=dict)


class VisualQAResult(BaseModel):
    ok: bool
    score: float | None = None
    issues: list[str] = Field(default_factory=list)
    missing_subject_ids: list[str] = Field(default_factory=list)
    mismatched_subject_ids: list[str] = Field(default_factory=list)
    recommendation: Literal[
        "accept",
        "retry_generation",
        "ask_user",
        "continue_with_warning",
    ] = "accept"

    @field_validator("score")
    def score_in_unit_interval(cls, value: float | None) -> float | None:
        return _validate_unit_interval(value, field_name="score")


class ConceptBundle(BaseModel):
    concept_version: int
    final_preview_image_id: str | None = None
    subject_concept_images: dict[str, list[str]] = Field(default_factory=dict)
    scene_concept_image_ids: list[str] = Field(default_factory=list)
    prompt_pack: ConceptPromptPack | None = None
    visual_qa: VisualQAResult | None = None
    approved: bool = False
    approved_at: str | None = None

    @field_validator("concept_version")
    def concept_version_is_positive(cls, value: int) -> int:
        return _validate_positive_version(value)


class ReviewPatch(BaseModel):
    patch_id: str
    source_turn_id: str
    phase_created: WorkflowPhase
    target_type: Literal[
        "global",
        "scene",
        "subject",
        "camera",
        "lighting",
        "material",
        "blender_object",
    ]
    target_id: str | None = None
    patch_type: Literal[
        "appearance_change",
        "pose_change",
        "style_change",
        "lighting_change",
        "camera_change",
        "layout_change",
        "add_subject",
        "remove_subject",
        "replace_subject",
        "material_change",
        "move_object",
        "rotate_object",
        "scale_object",
        "redo_subject",
        "redo_scene",
    ]
    instruction: str
    structured_delta: dict[str, Any] = Field(default_factory=dict)
    affected_artifact_ids: list[str] = Field(default_factory=list)
    status: Literal["pending", "applied", "rejected", "superseded"] = "pending"


class Asset3DRecord(BaseModel):
    asset_id: str
    subject_id: str
    source_image_id: str
    service: Literal["hunyuan3d_2_1", "manual", "existing_asset"] = "hunyuan3d_2_1"
    job_id: str | None = None
    mesh_uri: str | None = None
    glb_uri: str | None = None
    obj_uri: str | None = None
    texture_uris: list[str] = Field(default_factory=list)
    preview_image_id: str | None = None
    status: Literal[
        "pending",
        "running",
        "succeeded",
        "failed",
        "uncertain",
        "distorted",
        "needs_regen",
        "accepted_with_warning",
    ] = "pending"
    quality_score: float | None = None
    quality_notes: str | None = None
    generation_params: dict[str, Any] = Field(default_factory=dict)
    version: int = 1

    @field_validator("quality_score")
    def quality_score_in_unit_interval(cls, value: float | None) -> float | None:
        return _validate_unit_interval(value, field_name="quality_score")

    @field_validator("version")
    def version_is_positive(cls, value: int) -> int:
        return _validate_positive_version(value)


class Scene3DRecord(BaseModel):
    scene_asset_id: str
    source_scene_concept_image_ids: list[str] = Field(default_factory=list)
    source_prompt: str | None = None
    service: Literal[
        "hunyuan_world_mirror",
        "hy_world",
        "custom_scene_service",
        "proxy_blender_scene",
    ]
    raw_output_type: Literal[
        "mesh",
        "3dgs",
        "point_cloud",
        "depth_camera_normals",
        "colmap_package",
        "scene_package",
        "unknown",
    ] = "unknown"
    raw_artifact_ids: list[str] = Field(default_factory=list)
    adapted_artifact_ids: list[str] = Field(default_factory=list)
    blender_import_mode: Literal[
        "mesh_import",
        "3dgs_layer",
        "point_cloud_proxy",
        "depth_camera_scaffold",
        "visual_reference_only",
        "procedural_proxy",
    ]
    status: Literal[
        "pending",
        "running",
        "adapted",
        "failed",
        "accepted_with_warning",
    ] = "pending"
    quality_notes: str | None = None
    adapter_notes: str | None = None
    generation_params: dict[str, Any] = Field(default_factory=dict)
    version: int = 1

    @field_validator("version")
    def version_is_positive(cls, value: int) -> int:
        return _validate_positive_version(value)


class TransformSpec(BaseModel):
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_euler: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


class BoundsSpec(BaseModel):
    min: tuple[float, float, float]
    max: tuple[float, float, float]


class BlenderObjectRecord(BaseModel):
    object_id: str
    blender_name: str
    subject_id: str | None = None
    asset_id: str | None = None
    scene_asset_id: str | None = None
    object_type: Literal[
        "subject_asset",
        "scene_layer",
        "proxy_geometry",
        "camera",
        "light",
        "helper",
        "unknown",
    ] = "unknown"
    transform: TransformSpec = Field(default_factory=TransformSpec)
    semantic_role: str | None = None
    visible: bool = True
    locked: bool = False
    notes: str | None = None


class RenderSettings(BaseModel):
    engine: Literal["cycles", "eevee", "workbench", "unknown"] = "unknown"
    resolution_x: int = 1280
    resolution_y: int = 720
    samples: int | None = None
    frame_start: int = 1
    frame_end: int = 1
    output_format: str = "PNG"
    notes: str | None = None


class BlenderSceneState(BaseModel):
    blender_scene_id: str
    blend_file_artifact_id: str | None = None
    preview_image_id: str | None = None
    objects: list[BlenderObjectRecord] = Field(default_factory=list)
    camera: CameraSpec | None = None
    lighting: LightingSpec | None = None
    render_settings: RenderSettings | None = None
    scene_asset_id: str | None = None
    version: int = 1
    last_synced_at: str | None = None

    @field_validator("version")
    def version_is_positive(cls, value: int) -> int:
        return _validate_positive_version(value)


class ViewerCameraState(BaseModel):
    """Concrete camera snapshot emitted by the existing Blender export helper."""

    name: str | None = None
    type: str | None = None
    transform: TransformSpec | None = None
    focal_length: float | None = None
    ortho_scale: float | None = None
    clip_start: float | None = None
    clip_end: float | None = None


class ViewerSceneObjectRecord(BaseModel):
    viewer_object_id: str
    subject_id: str | None = None
    blender_object_id: str | None = None
    asset_id: str | None = None
    display_name: str | None = None
    selectable: bool = True
    highlighted: bool = False
    transform: TransformSpec = Field(default_factory=TransformSpec)
    object_type: str | None = None
    bounds: BoundsSpec | None = None


class ViewerSceneState(BaseModel):
    viewer_scene_id: str
    source_blend_version_id: str | None = None
    viewer_scene_artifact_id: str | None = None
    viewer_state_artifact_id: str | None = None
    objects: list[ViewerSceneObjectRecord] = Field(default_factory=list)
    camera: ViewerCameraState | CameraSpec | None = None
    active_object_id: str | None = None
    version: int = 1
    last_exported_at: str | None = None
    source_blend_path: str | None = None
    viewer_scene_path: str | None = None

    @field_validator("version")
    def version_is_positive(cls, value: int) -> int:
        return _validate_positive_version(value)


class ScaleEstimate(BaseModel):
    subject_id: str
    relative_scale_description: str
    scale_factor_hint: float | None = None
    confidence: float | None = None
    reasoning_summary: str | None = None

    @field_validator("confidence")
    def confidence_in_unit_interval(cls, value: float | None) -> float | None:
        return _validate_unit_interval(value, field_name="confidence")


class PlacementPlan(BaseModel):
    subject_id: str
    target_region: str | None = None
    relation_to_subject_id: str | None = None
    relation: str | None = None
    transform_hint: TransformSpec | None = None
    composition_notes: str | None = None


class BlenderAssemblyPlan(BaseModel):
    plan_id: str
    import_operations: list[dict[str, Any]] = Field(default_factory=list)
    placement_plans: list[PlacementPlan] = Field(default_factory=list)
    scale_estimates: list[ScaleEstimate] = Field(default_factory=list)
    camera_plan: CameraSpec | None = None
    lighting_plan: LightingSpec | None = None
    render_plan: RenderSettings | None = None
    notes: str | None = None


class SceneInterpreterContext(BaseModel):
    user_text: str
    input_images: list[InputImage]
    declared_bindings: list[ReferenceBinding]


class ConceptPromptPlannerContext(BaseModel):
    scene_spec: SceneSpec
    active_review_patches: list[ReviewPatch] = Field(default_factory=list)
    prior_prompt_pack_summary: str | None = None


class BlenderAssemblyPlannerContext(BaseModel):
    scene_spec: SceneSpec
    subject_assets: list[Asset3DRecord]
    scene_asset: Scene3DRecord | None = None
    concept_bundle_summary: str | None = None
    latest_preview_image_id: str | None = None
    latest_viewer_scene_id: str | None = None
    allowed_domain_tools: list[str] = Field(default_factory=list)


class BlenderEditRouterContext(BaseModel):
    user_edit_text: str
    blender_scene: BlenderSceneState
    scene_spec: SceneSpec
    latest_preview_image_id: str | None = None
    latest_viewer_scene_id: str | None = None
    allowed_edit_tools: list[str] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    tool_call_id: str
    project_id: str
    phase: WorkflowPhase
    domain_tool_name: str
    tool_name: str | None = None
    raw_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] | None = None
    status: ToolCallStatus
    error: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: str
    ended_at: str | None = None
    finished_at: str | None = None


class PendingAction(BaseModel):
    action_id: str
    phase: WorkflowPhase
    action_type: Literal[
        "concept_review",
        "blender_preview_review",
        "ask_user_clarification",
        "surface_failed_asset",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowError(BaseModel):
    error_id: str
    phase: WorkflowPhase
    message: str
    node_name: str | None = None
    code: str | None = None
    recoverable: bool = True
    retriable: bool | None = None
    retry_count: int = 0
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class AgentProjectState(BaseModel):
    project_id: str
    thread_id: str
    phase: WorkflowPhase
    user_id: str | None = None
    session_id: str | None = None
    user_turns: list[UserTurn] = Field(default_factory=list)
    conversation_summary: str | None = None
    input_images: list[InputImage] = Field(default_factory=list)
    reference_bindings: list[ReferenceBinding] = Field(default_factory=list)
    scene_spec: SceneSpec | None = None
    concept_bundle: ConceptBundle | None = None
    blender_assembly_plan: BlenderAssemblyPlan | None = None
    review_patches: list[ReviewPatch] = Field(default_factory=list)
    subject_assets: list[Asset3DRecord] = Field(default_factory=list)
    scene_asset: Scene3DRecord | None = None
    blender_scene: BlenderSceneState | None = None
    viewer_scene: ViewerSceneState | None = None
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    pending_action: PendingAction | None = None
    last_error: WorkflowError | None = None
    tool_call_log: list[ToolCallRecord] = Field(default_factory=list)
    version: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("version")
    def version_is_positive(cls, value: int) -> int:
        return _validate_positive_version(value)

    def artifact_ids(self) -> set[str]:
        return {artifact.artifact_id for artifact in self.artifacts}

    def assert_reference_bindings_are_explicit(self) -> None:
        implicit = [
            binding.binding_id
            for binding in self.reference_bindings
            if not binding.explicit_in_user_text
        ]
        if implicit:
            raise ValueError(f"implicit reference bindings are not allowed in V1: {implicit}")
