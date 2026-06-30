# DOC-005：产物与版本管理规范

**文档编号：** DOC-005  
**文档名称：** 产物与版本管理规范  
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

本文档定义 V1 中图片、3D 模型、场景资产、Blender 文件、Web 端实时预览场景、预览渲染图、metadata 和用户修改记录的存储、引用、版本化、回滚与交付规则。

核心原则：

```text
Agent state 不存大文件。
Agent state 只存 artifact_id、uri、metadata、version 和 lineage。
所有真实文件由 ArtifactStore 管理。
所有状态变化由 EventLog 记录。
所有用户可见结果必须可追溯到输入、prompt、工具调用和版本。
```

---

## 2. 需要管理的产物类型

V1 产物分为以下几类。

```text
InputImageArtifact             用户上传图片
ConceptImageArtifact           2D 概念图
SubjectConceptImageArtifact    主体概念图
SceneConceptImageArtifact      场景概念图
Subject3DAssetArtifact         主体 3D 资产
Scene3DAssetArtifact           场景 3D 输出
SceneAdapterArtifact           场景适配中间产物
BlenderFileArtifact            .blend 文件
BlenderPreviewArtifact         Blender 高质量预览渲染图
ViewerSceneArtifact            前端实时 3D 场景快照，通常为 GLB/glTF
ViewerSceneStateArtifact       前端实时 3D Viewer 使用的 scene_state.json
DeliveryPackageArtifact        交付包
MetadataArtifact               JSON metadata
LogArtifact                    日志和调试信息
```

---

## 3. Artifact 基础模型

所有产物统一使用 `ArtifactRecord` 表示。

```python
class ArtifactRecord(BaseModel):
    artifact_id: str
    project_id: str
    artifact_type: ArtifactType
    uri: str
    storage_backend: Literal["local", "s3", "gcs", "azure_blob", "custom"]
    mime_type: str | None = None
    file_ext: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    created_at: datetime
    created_by: Literal["user", "agent", "tool", "system"]
    version: int = 1
    status: Literal["created", "processing", "ready", "failed", "archived"]
    metadata: dict[str, Any] = {}
    lineage: ArtifactLineage | None = None
```

### 3.1 URI 规则

本地开发环境推荐：

```text
/artifacts/{project_id}/{artifact_type}/{artifact_id}.{ext}
```

示例：

```text
/artifacts/project_001/input_images/img_001.png
/artifacts/project_001/concepts/concept_v003_final.png
/artifacts/project_001/subject_assets/subject_001_asset_v002.glb
/artifacts/project_001/blender/blend_v005.blend
```

生产环境可以替换为对象存储 URI。

---

## 4. ID 命名规范

### 4.1 项目与线程

```text
project_id: project_20260627_0001
thread_id: thread_20260627_0001
```

### 4.2 图片

```text
image_001
image_002
image_003
```

用户上传图片必须在前端显示稳定 `image_id`。

### 4.3 主体

```text
subject_001
subject_002
subject_003
```

### 4.4 2D 概念版本

```text
concept_v001
concept_v002
concept_v003
```

### 4.5 3D 主体资产

```text
asset_subject_001_v001
asset_subject_001_v002
asset_subject_002_v001
```

### 4.6 场景资产

```text
scene_asset_v001
scene_asset_v002
scene_adapter_v001
```

### 4.7 Blender 文件版本

```text
blend_v001
blend_v002
blend_v003
```

### 4.8 前端实时 3D 预览版本

```text
viewer_scene_v001
viewer_scene_v002
viewer_state_v001
viewer_state_v002
```


---

## 5. 版本层级

V1 有 5 个主要版本层级。

```text
Project Version       项目级快照
Concept Version       2D 概念版本
Subject Asset Version 主体资产版本
Scene Asset Version   场景资产版本
Blender Scene Version Blender 场景版本
Viewer Scene Version  前端实时 3D 预览快照版本
```

### 5.1 ProjectVersion

项目级版本用于记录某个时间点的整体状态。

```python
class ProjectVersion(BaseModel):
    project_id: str
    version_id: str
    phase: WorkflowPhase
    state_snapshot_uri: str
    created_at: datetime
    reason: str
    parent_version_id: str | None = None
    important_artifacts: list[str]
```

触发时机：

```text
用户确认 2D 概念
主体 3D 资产全部完成
场景资产适配完成
Web 端 3D 预览快照导出
Blender 高质量预览生成
用户确认交付
用户显式保存版本
```

---

## 6. 2D 概念版本管理

每次 2D 概念生成或重生成都会生成一个新的 `ConceptBundle`。

```python
class ConceptVersion(BaseModel):
    concept_version_id: str
    project_id: str
    version: int
    final_preview_image_id: str
    subject_concept_image_ids: dict[str, str]
    scene_concept_image_ids: list[str]
    prompt_pack_artifact_id: str
    review_patch_ids: list[str]
    parent_concept_version_id: str | None = None
    approved: bool = False
    created_at: datetime
```

### 6.1 局部重生成规则

用户修改某个主体时：

```text
只生成该主体的新 subject_concept_image
必要时重新生成 final_preview_image
不强制重生成其他主体图
```

用户修改全局风格时：

```text
生成新的 final_preview_image
可能重新生成全部 subject_concept_images
生成新的 scene_concept_images
```

用户修改场景布局时：

```text
生成新的 final_preview_image
生成新的 scene_concept_images
主体图可复用，除非主体姿态受布局影响
```

---

## 7. 主体 3D 资产版本管理

每个主体独立维护资产版本。

```python
class SubjectAssetVersion(BaseModel):
    asset_version_id: str
    subject_id: str
    project_id: str
    source_concept_version_id: str
    source_image_id: str
    glb_artifact_id: str | None
    obj_artifact_id: str | None
    texture_artifact_ids: list[str]
    preview_artifact_id: str | None
    hunyuan_job_id: str | None
    generation_params: dict
    quality_status: Literal["pending", "ready", "failed", "uncertain", "rejected"]
    parent_asset_version_id: str | None = None
    created_at: datetime
```

### 7.1 单主体重做

如果用户说：

```text
重做主体2
这个猫不像
把桌子重新生成
```

系统应：

```text
1. 判断反馈是否影响 2D 概念图。
2. 如果影响，先重生成 subject_concept_image。
3. 调用 Hunyuan3D 生成新的 SubjectAssetVersion。
4. 在 Blender 中替换对应对象。
5. 生成新的 blend_version。
```

其他主体资产不应被无故重生成。

---

## 8. 场景资产版本管理

场景资产由 `SceneGenerationService` 和 `SceneAssetAdapter` 产生。

```python
class SceneAssetVersion(BaseModel):
    scene_asset_version_id: str
    project_id: str
    source_scene_concept_image_ids: list[str]
    source_scene_spec_version: int
    raw_scene_output_artifact_ids: list[str]
    adapted_scene_artifact_ids: list[str]
    output_types: list[Literal["mesh", "point_cloud", "3dgs", "depth", "normal", "camera", "scene_package"]]
    adapter_status: Literal["pending", "adapted", "partial", "failed"]
    created_at: datetime
    parent_scene_asset_version_id: str | None = None
```

### 8.1 场景输出不做固定假设

V1 不假设场景生成服务一定返回 mesh。可能输出：

```text
mesh
point cloud
3DGS
depth maps
surface normals
camera parameters
COLMAP package
multi-view images
```

因此必须保存原始输出和适配输出。

---

## 9. Blender 场景版本管理

每次 Blender 装配或编辑都会产生新的 `BlenderSceneVersion`。

```python
class BlenderSceneVersion(BaseModel):
    blend_version_id: str
    project_id: str
    blend_file_artifact_id: str
    preview_artifact_id: str | None
    source_subject_asset_version_ids: list[str]
    source_scene_asset_version_id: str | None
    blender_scene_state_artifact_id: str
    operation_log_ids: list[str]
    parent_blend_version_id: str | None = None
    created_at: datetime
    reason: str
```

### 9.1 版本产生时机

```text
初次导入主体和场景资产
初次完成摆放和打光
每次用户修改 Blender 场景
每次替换主体资产
每次重新生成场景资产并导入
每次渲染最终预览
```

### 9.2 回滚

V1 至少支持内部回滚，不一定暴露复杂 UI。

```text
回滚到上一个 2D concept_version
回滚到上一个 subject asset version
回滚到上一个 blend_version
```

回滚不删除新版本，只是把当前 active pointer 指向旧版本。

---


## 9A. 前端实时 3D 预览版本管理

每次 Blender 权威场景发生可见变化后，应导出或更新前端可加载的实时 3D 预览产物。

```python
class ViewerSceneVersion(BaseModel):
    viewer_scene_version_id: str
    project_id: str
    source_blend_version_id: str
    viewer_scene_artifact_id: str  # viewer_scene.glb / viewer_scene.gltf
    viewer_state_artifact_id: str  # scene_state.json
    included_subject_ids: list[str]
    included_asset_ids: list[str]
    object_mapping: dict[str, str]  # subject_id/blender_object_id -> viewer_object_id
    created_at: datetime
    parent_viewer_scene_version_id: str | None = None
```

V1 前端实时查看依赖该版本，而不是每次调用 Blender 渲染图片。

触发时机：

```text
初次 Blender 装配完成
每次主体位置/旋转/缩放变化
每次新增/删除/替换主体
每次场景资产重新适配
每次相机或灯光发生影响预览的变化
用户显式要求刷新实时 3D 预览
```

注意：`ViewerSceneVersion` 是 `.blend` 权威场景的可视化快照，不是权威编辑文件。

## 10. ReviewPatch 版本化

用户反馈必须以结构化补丁记录。

```python
class ReviewPatchRecord(BaseModel):
    patch_id: str
    project_id: str
    source_phase: WorkflowPhase
    user_message_id: str
    target_type: Literal["global", "subject", "scene", "camera", "lighting", "material", "blender_object"]
    target_id: str | None
    patch_type: str
    natural_language: str
    structured_patch: dict
    affected_artifacts: list[str]
    created_at: datetime
    applied: bool = False
```

示例：

```json
{
  "patch_id": "patch_003",
  "target_type": "subject",
  "target_id": "subject_002",
  "patch_type": "appearance_change",
  "natural_language": "把猫的毛色改成橘色",
  "structured_patch": {
    "appearance.fur_color": "orange"
  }
}
```

---

## 11. EventLog

所有关键动作都要写入事件日志。

```python
class EventLogRecord(BaseModel):
    event_id: str
    project_id: str
    thread_id: str
    event_type: str
    phase: WorkflowPhase | None
    node_name: str | None
    message: str
    input_refs: list[str]
    output_refs: list[str]
    tool_call_id: str | None
    error: dict | None
    created_at: datetime
```

事件类型：

```text
user_message_received
image_uploaded
reference_binding_created
scene_spec_generated
concept_generation_started
concept_generation_completed
review_patch_created
hunyuan3d_job_started
hunyuan3d_job_completed
scene_generation_started
scene_generation_completed
scene_asset_adapted
blender_tool_call_started
blender_tool_call_completed
viewer_scene_exported
viewer_scene_state_updated
blender_preview_rendered
delivery_package_created
error
retry
rollback
```

---

## 12. Artifact Lineage

每个产物都应能追溯来源。

```python
class ArtifactLineage(BaseModel):
    source_artifact_ids: list[str]
    source_prompt_artifact_id: str | None
    source_tool_call_ids: list[str]
    source_state_version_id: str | None
    parent_artifact_id: str | None
```

例如主体 GLB 的 lineage：

```text
source_artifact_ids:
  - subject_concept_image_id
source_tool_call_ids:
  - hunyuan3d_job_call_id
parent_artifact_id:
  - previous_subject_asset_version_id, if regenerated
```

---

## 13. 存储目录建议

```text
artifacts/
  {project_id}/
    input_images/
    concepts/
      final_preview/
      subjects/
      scenes/
      prompt_packs/
    subject_assets/
      {subject_id}/
        v001/
        v002/
    scene_assets/
      raw/
      adapted/
    blender/
      blend_files/
      previews/
      viewer_scenes/
      viewer_states/
      exports/
    metadata/
    logs/
```

---

## 14. 数据库表建议

V1 最小表：

```text
projects
project_versions
artifacts
concept_versions
subject_asset_versions
scene_asset_versions
blender_scene_versions
viewer_scene_versions
review_patches
event_logs
tool_call_logs
```

如果初期开发简化，可以先用：

```text
projects
artifacts
event_logs
```

其中 `projects.state_json` 存当前项目状态，后续再拆表。

---

## 15. 前端版本展示

前端至少应展示：

```text
当前 concept_version
当前 blend_version
当前 viewer_scene_version
主体资产状态
场景资产状态
最近一次用户修改摘要
```

不要求 V1 展示完整版本树，但需要支持工程内部追踪。

---

## 16. 验收标准

```text
1. 每张用户上传图片都有 image_id 和 ArtifactRecord。
2. 每次 2D 概念生成都有 concept_version。
3. 每个主体 3D 资产都有独立 asset_version。
4. 场景输出和适配输出分开记录。
5. 每次 Blender 编辑生成新的 blend_version。
5.1 每次可见场景变化导出新的 viewer_scene_version 或更新 viewer_scene_state。
6. 用户反馈保存为 ReviewPatchRecord。
7. 关键工具调用保存 EventLog / ToolCallLog。
8. state 中不存大文件，只存 artifact 引用。
9. 能追溯最终 .blend 和前端 viewer_scene 来自哪些主体资产、场景资产和用户修改。
10. 能局部替换某个主体资产而不重做整个项目。
```
