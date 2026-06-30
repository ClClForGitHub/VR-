# DOC-007：Hunyuan3D / Hunyuan Mirror 生成链路规范

**文档编号：** DOC-007  
**文档名称：** Hunyuan3D / Hunyuan Mirror 生成链路规范  
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

本文档定义 V1 中主体级 2D→3D 和场景级 3D 生成的工程链路，包括输入图片规范、服务抽象、API 调用、任务状态、输出适配、质量检查、失败重试和返修策略。

V1 包含两条生成线：

```text
主体生成线：subject_concept_image → Hunyuan3D-2.1 → subject 3D asset
场景生成线：scene_concept_image / scene prompt → Hunyuan Mirror / HY-World → scene 3D output → SceneAssetAdapter → Blender-consumable scene asset
```

---

## 2. 设计原则

```text
1. 主体和场景分开生成。
2. 主体生成优先稳定、清晰、可导入 Blender。
3. 场景生成不假设输出一定是 mesh。
4. 所有生成结果必须进入 ArtifactStore。
5. 所有生成任务必须有 job_id、status、params、lineage。
6. 所有失败必须有可追踪原因和返修路径。
7. 3D asset 默认不增加用户确认点，由系统 QA 判断；不确定时才抛给用户。
8. Hunyuan3D 输出的主体资产在 V1 中按静态 GLB/mesh 处理，不假设包含骨架、蒙皮权重或动画 clip。
```

---

## 3. 主体生成线

### 3.1 输入

主体生成输入为 `subject_concept_image`。

默认规范：

```text
单主体
3/4 视图
完整轮廓
无遮挡
居中
干净背景
均匀光照
不要复杂场景背景
不要多主体同图
不要大面积遮挡
```

### 3.2 为什么默认 3/4 视图

V1 采用 3/4 视图作为默认主体图规范，因为它通常比纯正面图包含更多侧面几何信息，同时比多视图拼图更简单、更适合单图 img2 3D 工作流。

三视图不作为 V1 默认方案。后续通过 spike 判断是否作为 fallback：

```text
单张 3/4 图失败 → 尝试三视图或多视角图
复杂道具 → 可尝试三视图
角色类主体 → 先保持单张 3/4 图
```

### 3.3 SubjectImageSpec

```python
class SubjectImageSpec(BaseModel):
    subject_id: str
    image_id: str
    view_type: Literal["three_quarter", "front", "side", "multi_view", "unknown"] = "three_quarter"
    background_type: Literal["clean", "transparent", "white", "simple_scene"] = "clean"
    full_body_or_full_object: bool = True
    occlusion_level: Literal["none", "minor", "major"] = "none"
    suitability_score: float | None = None
    notes: str | None = None
```

---

## 4. Hunyuan3DSubjectService

### 4.1 服务职责

`Hunyuan3DSubjectService` 负责：

```text
读取 subject_concept_image
调用本地 Hunyuan3D-2.1 服务
轮询任务状态
保存 GLB / OBJ / texture / preview
生成 Asset3DRecord
处理失败和重试
```

### 4.2 接口草案

```python
class Hunyuan3DSubjectService:
    async def submit_subject_job(self, request: Subject3DRequest) -> Subject3DJob: ...
    async def get_job_status(self, job_id: str) -> Subject3DJobStatus: ...
    async def collect_outputs(self, job_id: str) -> Subject3DOutput: ...
```

### 4.3 Subject3DRequest

```python
class Subject3DRequest(BaseModel):
    project_id: str
    subject_id: str
    source_image_id: str
    generation_mode: Literal["image_to_3d"] = "image_to_3d"
    remove_background: bool = True
    generate_texture: bool = True
    output_format: Literal["glb", "obj", "both"] = "glb"
    seed: int | None = None
    face_count: int | None = None
    quality_preset: Literal["draft", "standard", "high"] = "standard"
```

具体参数名称需要根据本地部署 API 确认。上层业务不直接依赖原始 Hunyuan 参数名，而是通过 `Hunyuan3DClient` 做映射。

---

## 5. Hunyuan3D 输出

期望输出：

```text
初始 mesh
带纹理 GLB
OBJ / MTL / texture，可选
asset preview render，可选
metadata JSON
```

`Subject3DOutput`：

```python
class Subject3DOutput(BaseModel):
    job_id: str
    subject_id: str
    status: Literal["succeeded", "failed", "partial"]
    glb_artifact_id: str | None
    obj_artifact_id: str | None
    texture_artifact_ids: list[str]
    preview_artifact_id: str | None
    raw_output_artifact_ids: list[str]
    generation_params: dict
    error: dict | None = None
```

---

## 6. 主体 3D 质量检查

### 6.1 系统默认检查，不默认用户确认

V1 不把 3D asset preview 作为默认用户确认点。系统自动检查：

```text
文件是否存在
文件大小是否异常
是否能导入 Blender
mesh 是否为空
是否能渲染 preview
纹理是否丢失
主体是否严重变形
是否明显与 subject_concept_image 不一致
```

只有当质量不确定、明显失败或用户主动要求查看时，才展示给用户。

### 6.2 AssetQualityEvaluator

```python
class AssetQualityResult(BaseModel):
    subject_id: str
    asset_version_id: str
    status: Literal["pass", "fail", "uncertain"]
    score: float
    issues: list[AssetQualityIssue]
    suggested_action: Literal[
        "accept",
        "rerun_hunyuan3d",
        "regenerate_subject_image",
        "ask_user",
        "manual_review"
    ]
```

常见问题类型：

```text
empty_mesh
import_failed
missing_texture
severe_distortion
wrong_shape
wrong_color
broken_geometry
bad_scale_hint
uncertain_similarity
```

---

## 7. 主体生成失败返修策略

```text
Hunyuan3D API 失败
  → 自动重试一次
  → 仍失败则标记 failed，进入人工/系统处理

导入 Blender 失败
  → 检查格式
  → 尝试转换
  → 失败则重跑 Hunyuan3D

几何严重失真
  → 先重跑 Hunyuan3D
  → 多次失败则回到 subject_concept_image 重生

主体不像用户要求
  → 回到 2D 主体图重生
  → 再走 Hunyuan3D

纹理问题轻微
  → 可先接受，后续 Blender 材质调整
```

---

## 8. 场景生成线

### 8.1 输入

场景生成输入可包括：

```text
scene_concept_image
scene prompt
SceneSpec.environment
SceneSpec.spatial_relations
camera / lighting / style hints
用户场景参考图
```

### 8.2 SceneGenerationService

场景生成服务统一抽象为：

```python
class SceneGenerationService:
    async def submit_scene_job(self, request: Scene3DRequest) -> Scene3DJob: ...
    async def get_job_status(self, job_id: str) -> Scene3DJobStatus: ...
    async def collect_outputs(self, job_id: str) -> Scene3DOutput: ...
```

### 8.3 Scene3DRequest

```python
class Scene3DRequest(BaseModel):
    project_id: str
    source_scene_concept_image_ids: list[str]
    scene_prompt: str
    scene_spec_ref: str
    requested_outputs: list[Literal[
        "mesh",
        "point_cloud",
        "3dgs",
        "depth",
        "normal",
        "camera",
        "scene_package"
    ]]
    quality_preset: Literal["draft", "standard", "high"] = "standard"
```

---

## 9. Hunyuan Mirror / HY-World 输出形态

V1 不假设场景服务固定输出 mesh。根据公开说明，HunyuanWorld-Mirror / HY-World 类型服务可能输出：

```text
point clouds
3D Gaussian Splatting / 3DGS
depth maps
surface normals
camera parameters
COLMAP-style package
multi-view images
mesh 或可转换 mesh
```

因此必须引入：

```text
SceneAssetAdapter
```

---

## 10. SceneAssetAdapter

### 10.1 职责

`SceneAssetAdapter` 负责把场景生成结果转换成 Blender 装配流程可消费的内容。

可能策略：

```text
mesh → 直接导入 Blender
point cloud → 作为参考层 / 转代理几何 / 可视化点云
3DGS → 作为背景/参考/插件可视化层，或转换为辅助视图
深度图 + 相机 → 生成粗略代理几何或参考平面
多视图图像 → 生成背景板 / 投影参考 / 布局参考
camera parameters → 用于初始化 Blender 相机
normals → 用于材质/几何参考
```

### 10.2 Adapter 输出

```python
class AdaptedSceneAsset(BaseModel):
    scene_asset_version_id: str
    adapted_artifact_ids: list[str]
    blender_import_strategy: Literal[
        "direct_mesh_import",
        "point_cloud_reference",
        "gaussian_reference",
        "image_planes",
        "proxy_geometry",
        "hybrid"
    ]
    coordinate_hints: dict
    camera_hints: dict
    notes: str
```

---

## 11. 场景资产进入 Blender

场景资产进入 Blender 的方式由 `blender_import_strategy` 决定。

### 11.1 direct_mesh_import

适用于：

```text
场景服务输出 mesh / glTF / OBJ / GLB
```

执行：

```text
导入 mesh
设置材质
创建 collection
作为 environment root
```

### 11.2 point_cloud_reference

适用于：

```text
点云输出
```

执行：

```text
导入点云作为参考
LLM/MLLM 用于布局判断
Blender 中可作为半透明参考层
```

### 11.3 gaussian_reference

适用于：

```text
3DGS 输出
```

执行：

```text
作为视觉参考或渲染参考
不直接假设为可编辑 mesh
必要时渲染为背景/参考图
```

### 11.4 image_planes

适用于：

```text
多视角图 / 深度图 / 场景图
```

执行：

```text
创建背景板
创建远景参考
创建地面/墙面图像平面
```

### 11.5 proxy_geometry

适用于：

```text
只有深度/相机/点云，需要粗略几何场景
```

执行：

```text
生成地面、墙面、基础体块
作为主体摆放参考
```

---

## 12. 主体与场景对齐

V1 不做硬编码尺寸归一化。

原因：不同场景、主体类别、风格差异较大，固定单位比例可能产生错误。

V1 采用：

```text
LLM/MLLM 语义尺度估计
SceneSpec 中的 scale_hint
主体类别默认尺度先验
Blender preview 视觉检查
必要时自动调整
```

示例：

```text
人物：通常作为 1.6-1.8m 语义尺度参考
猫：相对人物约 0.25-0.4 高度
桌子：相对人物约腰部高度
小屋：应显著大于人物
```

这些只是语义先验，不是硬规则。最终由 `BlenderAssemblyPlanner` 和 `BlenderSceneQA` 根据预览调整。

---

## 13. 并行与异步任务

主体生成和场景生成可以并行。

推荐流程：

```text
Concept approved
  ├─ 并行生成 subject assets
  └─ 并行生成 scene asset

全部 ready 或 scene partial ready
  → SceneAssetAdapter
  → Blender assembly
```

如果场景资产生成较慢，可以先用 proxy environment 进入 Blender 装配，后续替换。

---

## 14. 技术 Spike 计划

### 14.1 Hunyuan3D 主体测试

测试样本：

```text
人物全身 3/4 视图
动物 3/4 视图
家具
复杂道具
车辆
树/石头/路灯等环境资产
复杂背景主体图
多主体同图
白底图
透明背景图
```

记录：

```text
是否成功
生成时间
输出格式
纹理质量
导入 Blender 是否成功
是否严重变形
适合的输入规范
```

### 14.2 Hunyuan Mirror 场景测试

测试样本：

```text
室内房间
街道
森林
庭院
科幻空间
多主体场景参考图
```

记录：

```text
输出类型
是否有 camera parameters
是否有 depth / normal
是否能导入 Blender
是否需要 adapter
适合作为背景、参考、proxy 还是 mesh
```

---

## 15. 验收标准

```text
1. 单个主体图可以生成 GLB 并导入 Blender。
2. 主体资产生成结果有 Asset3DRecord。
3. 主体生成失败有明确 retry / fallback。
4. 场景生成服务输出能保存为 Scene3DRecord。
5. SceneAssetAdapter 能处理至少一种场景输出。
6. 场景资产能以某种形式进入 Blender 装配流程。
7. 主体与场景能在 Blender 中共同渲染 preview。
8. 质量检查能判断 pass / fail / uncertain。
9. uncertain 的 3D asset 才会展示给用户确认。
10. 所有生成任务有 job_id、params、artifact lineage。
```

---

## 16. 参考资料

```text
Hunyuan3D-2.1：
https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1

Hunyuan3D-2.1 API 文档：
https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/API_DOCUMENTATION.md

HunyuanWorld-Mirror：
https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

HY-World 2.0：
https://github.com/Tencent-Hunyuan/HY-World-2.0
```
