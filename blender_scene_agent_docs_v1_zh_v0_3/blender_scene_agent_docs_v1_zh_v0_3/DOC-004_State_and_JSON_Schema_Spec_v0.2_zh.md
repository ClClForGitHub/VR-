# DOC-004：状态与 JSON Schema 规范

**文档编号：** DOC-004  
**文档名称：** 状态与 JSON Schema 规范  
**版本：** v0.2  
**状态：** 工程草案  
**项目：** 文本+图像到 Blender 场景 Agent  
**最后更新：** 2026-06-27  


---

## 本轮修订摘要

本版本根据最新工程决策完成以下修订：

```text
1. V1 前端必须包含 Web 端实时 3D 预览能力，不能只依赖 Blender 渲染图片。
2. Blender 服务器仍作为权威场景编辑与最终渲染环境，但前端通过 GLB/glTF + scene_state.json 加载可交互预览。
3. 用户在前端需要能够 orbit / zoom / pan 查看场景；V1 不要求专业级 3D 编辑器，但必须能实时查看场景。
4. Blender 渲染图用于高质量确认和最终交付，不作为日常实时查看的唯一手段。
5. Hunyuan3D 生成的主体模型在 V1 中视为静态资产，不假设包含骨架、蒙皮权重或动画 clip。
6. 自动上骨架、角色动作、动作重定向和复杂动画全部移出 V1，后续单独设计动画管线。
```

## 1. 文档目的

本文档定义文本+图像到 Blender 场景 Agent 的 V1 状态模型和 JSON 契约。

核心原则是：

```text
State 存储结构化事实和 artifact 引用。
ArtifactStore 存储大型二进制数据。
LLM 节点只接收从 state 派生出的最小上下文视图。
```

---

## 2. 设计原则

### 2.1 事实源

事实源不是聊天历史，而是：

```text
AgentProjectState
SceneSpec
ReferenceBinding[]
ConceptBundle
ReviewPatch[]
Asset3DRecord[]
Scene3DRecord
BlenderSceneState
ViewerSceneState
Artifact metadata
```

### 2.2 只存 artifact 引用

不要在 graph state 中存储原始图片字节、base64 GLB、`.blend` 二进制文件或大型模型输出 blob。

State 存储：

```text
artifact_id
uri
mime_type
semantic_role
version
metadata
```

### 2.3 Pydantic-first 实现

实现应使用 Pydantic models 进行校验、序列化和 LLM 结构化输出。

---

## 3. 核心枚举

```python
from enum import Enum

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
```

---

## 4. AgentProjectState

顶层 graph state。

```python
from pydantic import BaseModel, Field
from typing import Any, Literal

class AgentProjectState(BaseModel):
    project_id: str
    user_id: str | None = None
    session_id: str | None = None
    thread_id: str
    phase: WorkflowPhase

    user_turns: list["UserTurn"] = Field(default_factory=list)
    conversation_summary: str | None = None

    input_images: list["InputImage"] = Field(default_factory=list)
    reference_bindings: list["ReferenceBinding"] = Field(default_factory=list)

    scene_spec: "SceneSpec" | None = None
    concept_bundle: "ConceptBundle" | None = None
    review_patches: list["ReviewPatch"] = Field(default_factory=list)

    subject_assets: list["Asset3DRecord"] = Field(default_factory=list)
    scene_asset: "Scene3DRecord" | None = None
    blender_scene: "BlenderSceneState" | None = None
    viewer_scene: "ViewerSceneState" | None = None

    pending_action: "PendingAction" | None = None
    last_error: "WorkflowError" | None = None
    tool_call_log: list["ToolCallRecord"] = Field(default_factory=list)

    version: int = 1
    created_at: str | None = None
    updated_at: str | None = None
```

---

## 5. 用户输入模型

### 5.1 UserTurn

```python
class UserTurn(BaseModel):
    turn_id: str
    text: str
    image_ids: list[str] = Field(default_factory=list)
    detected_intent: UserIntent | None = None
    phase_at_turn: WorkflowPhase
    created_at: str
```

### 5.2 InputImage

```python
class InputImage(BaseModel):
    image_id: str
    artifact_id: str
    uri: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    user_declared_label: str | None = None
    notes: str | None = None
```

### 5.3 ReferenceBinding

```python
class ReferenceBinding(BaseModel):
    binding_id: str
    image_id: str
    target_type: Literal[
        "subject",
        "scene",
        "style",
        "pose",
        "texture",
        "layout"
    ]
    target_id: str | None = None
    usage: Literal[
        "subject_reference",
        "scene_reference",
        "style_reference",
        "pose_reference",
        "texture_reference",
        "layout_reference"
    ]
    explicit_in_user_text: bool = True
    confidence: float = 1.0
    notes: str | None = None
```

V1 校验规则：

```text
除非使用 operator override，否则 explicit_in_user_text 必须为 true。
```

---

## 6. SceneSpec

### 6.1 SceneSpec

```python
class SceneSpec(BaseModel):
    scene_id: str
    title: str
    user_goal: str

    style: "StyleSpec"
    environment: "EnvironmentSpec"
    lighting: "LightingSpec"
    camera: "CameraSpec"

    subjects: list["SubjectSpec"] = Field(default_factory=list)
    spatial_relations: list["SpatialRelation"] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    version: int = 1
```

### 6.2 StyleSpec

```python
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
        "illustrative"
    ] | None = None
    notes: str | None = None
```

### 6.3 EnvironmentSpec

```python
class EnvironmentSpec(BaseModel):
    environment_type: str
    description: str
    time_of_day: str | None = None
    weather: str | None = None
    background_elements: list[str] = Field(default_factory=list)
    ground_surface: str | None = None
    scene_reference_image_ids: list[str] = Field(default_factory=list)
```

### 6.4 LightingSpec

```python
class LightingSpec(BaseModel):
    description: str | None = None
    key_light: str | None = None
    fill_light: str | None = None
    rim_light: str | None = None
    ambient: str | None = None
    intensity_hint: str | None = None
    color_temperature: str | None = None
```

### 6.5 CameraSpec

```python
class CameraSpec(BaseModel):
    shot_type: str | None = None
    angle: str | None = None
    lens_hint: str | None = None
    framing: str | None = None
    movement: str | None = None
    target_subject_ids: list[str] = Field(default_factory=list)
```

### 6.6 SubjectSpec

```python
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
        "environment_asset"
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
        "existing_asset"
    ] = "hunyuan3d_img2asset"

    preferred_subject_image_view: Literal[
        "three_quarter",
        "front",
        "side",
        "multi_view",
        "unspecified"
    ] = "three_quarter"

    scale_hint: str | None = None
    placement_hint: str | None = None
```

### 6.7 SpatialRelation

```python
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
        "centered_in"
    ]
    target_subject_id: str | None = None
    target_region: str | None = None
    distance_hint: str | None = None
    scale_hint: str | None = None
    notes: str | None = None
```

---

## 7. 概念图模型

### 7.1 ConceptBundle

```python
class ConceptBundle(BaseModel):
    concept_version: int
    final_preview_image_id: str | None = None
    subject_concept_images: dict[str, list[str]] = Field(default_factory=dict)
    scene_concept_image_ids: list[str] = Field(default_factory=list)
    prompt_pack: "ConceptPromptPack" | None = None
    visual_qa: "VisualQAResult" | None = None
    approved: bool = False
    approved_at: str | None = None
```

`subject_concept_images` 使用：

```text
subject_id -> list[artifact_id]
```

V1 通常每个主体使用一张图片。list 用于支持重试和未来的多视图 fallback。

### 7.2 ConceptPromptPack

```python
class ConceptPromptPack(BaseModel):
    final_preview_prompt: str
    subject_prompts: dict[str, str] = Field(default_factory=dict)
    scene_prompts: list[str] = Field(default_factory=list)
    negative_prompt: str | None = None
    generation_settings: dict[str, Any] = Field(default_factory=dict)
```

### 7.3 VisualQAResult

```python
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
        "continue_with_warning"
    ] = "accept"
```

---

## 8. ReviewPatch

用户反馈表示为结构化补丁。

```python
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
        "blender_object"
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
        "redo_scene"
    ]

    instruction: str
    structured_delta: dict[str, Any] = Field(default_factory=dict)
    affected_artifact_ids: list[str] = Field(default_factory=list)
    status: Literal["pending", "applied", "rejected", "superseded"] = "pending"
```

---

## 9. 主体 3D 资产模型

### 9.1 Asset3DRecord

```python
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
        "distorted",
        "needs_regen",
        "accepted_with_warning"
    ] = "pending"

    quality_score: float | None = None
    quality_notes: str | None = None
    generation_params: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
```

---

## 10. 场景 3D 模型

### 10.1 Scene3DRecord

```python
class Scene3DRecord(BaseModel):
    scene_asset_id: str
    source_scene_concept_image_ids: list[str] = Field(default_factory=list)
    source_prompt: str | None = None

    service: Literal[
        "hunyuan_world_mirror",
        "hy_world",
        "custom_scene_service",
        "proxy_blender_scene"
    ]

    raw_output_type: Literal[
        "mesh",
        "3dgs",
        "point_cloud",
        "depth_camera_normals",
        "colmap_package",
        "scene_package",
        "unknown"
    ] = "unknown"

    raw_artifact_ids: list[str] = Field(default_factory=list)
    adapted_artifact_ids: list[str] = Field(default_factory=list)

    blender_import_mode: Literal[
        "mesh_import",
        "3dgs_layer",
        "point_cloud_proxy",
        "depth_camera_scaffold",
        "visual_reference_only",
        "procedural_proxy"
    ]

    status: Literal[
        "pending",
        "running",
        "adapted",
        "failed",
        "accepted_with_warning"
    ] = "pending"

    quality_notes: str | None = None
    adapter_notes: str | None = None
    generation_params: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
```

### 10.2 SceneAssetAdapter 行为

适配器应按如下方式映射输出：

```text
mesh
  → blender_import_mode = mesh_import

3DGS / gaussians.ply
  → blender_import_mode = 3dgs_layer

point cloud
  → blender_import_mode = point_cloud_proxy

depth maps + camera params + normals
  → blender_import_mode = depth_camera_scaffold 或 visual_reference_only

COLMAP package
  → blender_import_mode = 3dgs_layer 或 depth_camera_scaffold
```

---

## 11. Blender 场景状态

### 11.1 TransformSpec

```python
class TransformSpec(BaseModel):
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_euler: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
```

### 11.2 BlenderObjectRecord

```python
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
        "unknown"
    ] = "unknown"

    transform: TransformSpec = Field(default_factory=TransformSpec)
    semantic_role: str | None = None
    visible: bool = True
    locked: bool = False
    notes: str | None = None
```

### 11.3 BlenderSceneState

```python
class BlenderSceneState(BaseModel):
    blender_scene_id: str
    blend_file_artifact_id: str | None = None
    preview_image_id: str | None = None

    objects: list[BlenderObjectRecord] = Field(default_factory=list)
    camera: CameraSpec | None = None
    lighting: LightingSpec | None = None
    render_settings: "RenderSettings" | None = None

    scene_asset_id: str | None = None
    version: int = 1
    last_synced_at: str | None = None
```

### 11.4 ViewerSceneObjectRecord

```python
class ViewerSceneObjectRecord(BaseModel):
    viewer_object_id: str
    subject_id: str | None = None
    blender_object_id: str | None = None
    asset_id: str | None = None
    display_name: str | None = None
    selectable: bool = True
    highlighted: bool = False
    transform: TransformSpec = Field(default_factory=TransformSpec)
```

### 11.5 ViewerSceneState

前端实时 3D Viewer 使用该结构加载和展示当前场景。它是 Blender 权威场景的可视化快照，不替代 `.blend` 文件。

```python
class ViewerSceneState(BaseModel):
    viewer_scene_id: str
    source_blend_version_id: str | None = None
    viewer_scene_artifact_id: str | None = None  # GLB / glTF
    viewer_state_artifact_id: str | None = None  # scene_state.json
    objects: list[ViewerSceneObjectRecord] = Field(default_factory=list)
    camera: CameraSpec | None = None
    active_object_id: str | None = None
    version: int = 1
    last_exported_at: str | None = None
```

### 11.6 RenderSettings

```python
class RenderSettings(BaseModel):
    engine: Literal["cycles", "eevee", "workbench", "unknown"] = "unknown"
    resolution_x: int = 1280
    resolution_y: int = 720
    samples: int | None = None
    frame_start: int = 1
    frame_end: int = 1
    output_format: str = "PNG"
    notes: str | None = None
```

---

## 12. 摆放模型

### 12.1 ScaleEstimate

```python
class ScaleEstimate(BaseModel):
    subject_id: str
    relative_scale_description: str
    scale_factor_hint: float | None = None
    confidence: float | None = None
    reasoning_summary: str | None = None
```

重要说明：V1 不要求全局正确的物理尺寸。该模型是美学/语义估计。

### 12.2 PlacementPlan

```python
class PlacementPlan(BaseModel):
    subject_id: str
    target_region: str | None = None
    relation_to_subject_id: str | None = None
    relation: str | None = None
    transform_hint: TransformSpec | None = None
    composition_notes: str | None = None
```

### 12.3 BlenderAssemblyPlan

```python
class BlenderAssemblyPlan(BaseModel):
    plan_id: str
    import_operations: list[dict[str, Any]] = Field(default_factory=list)
    placement_plans: list[PlacementPlan] = Field(default_factory=list)
    scale_estimates: list[ScaleEstimate] = Field(default_factory=list)
    camera_plan: CameraSpec | None = None
    lighting_plan: LightingSpec | None = None
    render_plan: RenderSettings | None = None
    notes: str | None = None
```

---

## 13. 工具与错误模型

### 13.1 ToolCallRecord

```python
class ToolCallRecord(BaseModel):
    tool_call_id: str
    tool_name: str
    phase: WorkflowPhase
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "succeeded", "failed"]
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
```

### 13.2 PendingAction

```python
class PendingAction(BaseModel):
    action_id: str
    phase: WorkflowPhase
    action_type: Literal[
        "concept_review",
        "blender_preview_review",
        "ask_user_clarification",
        "surface_failed_asset"
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
```

### 13.3 WorkflowError

```python
class WorkflowError(BaseModel):
    error_id: str
    phase: WorkflowPhase
    node_name: str
    message: str
    recoverable: bool = True
    retry_count: int = 0
    details: dict[str, Any] = Field(default_factory=dict)
```

---

## 14. Artifact Metadata

Artifact metadata 存储在 graph state 外部，但由 state 引用。

```python
class ArtifactRecord(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    uri: str
    mime_type: str
    project_id: str
    version: int = 1

    semantic_role: str | None = None
    linked_subject_id: str | None = None
    linked_scene_id: str | None = None
    created_by_node: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
```

---

## 15. 最小状态 JSON 示例

```json
{
  "project_id": "proj_001",
  "thread_id": "thread_001",
  "phase": "CONCEPT_REVIEW",
  "input_images": [
    {
      "image_id": "image_001",
      "artifact_id": "art_input_001",
      "uri": "s3://bucket/proj_001/input/image_001.png",
      "mime_type": "image/png",
      "user_declared_label": "主体 1 参考图"
    }
  ],
  "reference_bindings": [
    {
      "binding_id": "bind_001",
      "image_id": "image_001",
      "target_type": "subject",
      "target_id": "subject_001",
      "usage": "subject_reference",
      "explicit_in_user_text": true,
      "confidence": 1.0
    }
  ],
  "scene_spec": {
    "scene_id": "scene_001",
    "title": "温暖的室内猫咖",
    "user_goal": "创建一个温暖、风格化的猫咖场景，包含一个女孩和一只猫。",
    "style": {
      "style_keywords": ["warm", "stylized", "soft lighting"],
      "realism_level": "stylized"
    },
    "environment": {
      "environment_type": "indoor cafe",
      "description": "一个舒适的咖啡馆室内场景，有木地板和温暖灯光。"
    },
    "lighting": {
      "description": "温暖的傍晚光线。"
    },
    "camera": {
      "shot_type": "medium wide shot",
      "angle": "slightly low angle"
    },
    "subjects": [
      {
        "subject_id": "subject_001",
        "display_name": "girl",
        "category": "character",
        "description": "一个穿蓝色外套的年轻女孩。",
        "priority": "hero",
        "preferred_subject_image_view": "three_quarter"
      },
      {
        "subject_id": "subject_002",
        "display_name": "cat",
        "category": "animal",
        "description": "一只靠近女孩的小橘猫。",
        "priority": "important",
        "preferred_subject_image_view": "three_quarter"
      }
    ],
    "spatial_relations": [
      {
        "relation_id": "rel_001",
        "source_subject_id": "subject_002",
        "relation": "near",
        "target_subject_id": "subject_001",
        "distance_hint": "靠近女孩脚边"
      }
    ],
    "constraints": [],
    "open_questions": [],
    "version": 1
  }
}
```

---

## 16. 状态更新规则

### 16.1 SceneSpec 更新

只有这些节点应修改 `scene_spec`：

```text
SceneSpecCompiler
FeedbackPatchParser + RegenerationRouter
Operator repair tool, if added later
```

### 16.2 ConceptBundle 更新

只有这些节点应修改 `concept_bundle`：

```text
ConceptPromptPlanner
ImageGenerationExecutor
ConceptVisualQA
ConceptReviewGate
```

### 16.3 主体资产更新

只有这些节点应修改 `subject_assets`：

```text
SubjectAssetGenerationExecutor
SubjectAssetQualityEvaluator
SubjectAssetRepairRouter
```

### 16.4 场景资产更新

只有这些节点应修改 `scene_asset`：

```text
SceneGenerationExecutor
SceneAssetAdapter
SceneAssetQA, if added later
```

### 16.5 Blender 场景更新

只有这些节点应修改 `blender_scene`：

```text
BlenderCommandExecutor
SceneStateSynchronizer
BlenderPreviewRenderer
BlenderEditRouter, only as planned deltas
```

### 16.6 ViewerSceneState 更新

只有这些节点应修改 `viewer_scene`：

```text
ScenePreviewExporter
ViewerSyncService
FrontendInteractionAdapter, if added later
```

`viewer_scene` 是前端实时 3D 预览快照。它必须能追溯到某个 `blend_version_id` 或 `BlenderSceneState.version`。


---

## 17. 上下文视图契约

### 17.1 SceneInterpreterContext

```python
class SceneInterpreterContext(BaseModel):
    user_text: str
    input_images: list[InputImage]
    declared_bindings: list[ReferenceBinding]
```

### 17.2 ConceptPromptPlannerContext

```python
class ConceptPromptPlannerContext(BaseModel):
    scene_spec: SceneSpec
    active_review_patches: list[ReviewPatch] = Field(default_factory=list)
    prior_prompt_pack_summary: str | None = None
```

### 17.3 BlenderAssemblyPlannerContext

```python
class BlenderAssemblyPlannerContext(BaseModel):
    scene_spec: SceneSpec
    subject_assets: list[Asset3DRecord]
    scene_asset: Scene3DRecord | None = None
    concept_bundle_summary: str | None = None
    latest_preview_image_id: str | None = None
    latest_viewer_scene_id: str | None = None
    allowed_domain_tools: list[str] = Field(default_factory=list)
```

### 17.4 BlenderEditRouterContext

```python
class BlenderEditRouterContext(BaseModel):
    user_edit_text: str
    blender_scene: BlenderSceneState
    scene_spec: SceneSpec
    latest_preview_image_id: str | None = None
    latest_viewer_scene_id: str | None = None
    allowed_edit_tools: list[str] = Field(default_factory=list)
```

---

## 18. 迁移说明

状态 schema 应从一开始就版本化：

```text
project_state.version
scene_spec.version
concept_bundle.concept_version
asset records version
blender_scene.version
```

当 schema 变化时，编写显式迁移函数：

```python
def migrate_project_state_v1_to_v2(state: dict) -> dict:
    ...
```

---

## 19. 研究依据

本版本使用的关键外部技术参考：

```text
HunyuanWorld-Mirror GitHub:
https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

HY-World 2.0 GitHub:
https://github.com/Tencent-Hunyuan/HY-World-2.0

LangGraph persistence docs:
https://docs.langchain.com/oss/python/langgraph/persistence
```
