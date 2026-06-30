# DOC-003：Agent 工作流设计

**文档编号：** DOC-003  
**文档名称：** Agent 工作流设计  
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

本文档定义 V1 Agent 工作流。它把产品路线映射成与 LangGraph 兼容的有状态工作流，内容包括阶段、节点、路由逻辑、LLM/MLLM 职责、工具执行职责、MCP 集成边界、用户反馈循环和失败处理。

该设计采用 workflow-first。系统不应作为不受约束的通用 ReAct Agent 运行。LLM/MLLM 只在受控节点内部用于理解、规划、视觉 QA 和结构化输出。

---

## 2. 顶层架构

```text
Frontend / API
  ↓
Project API + Upload API + Feedback API
  ↓
SceneWorkflowOrchestrator / LangGraph
  ↓
State + Artifact Store + Event Log
  ↓
LLM/MLLM Nodes
  ↓
Domain Tool Nodes
  ↓
ImageGenerationService
Hunyuan3DSubjectService
SceneGenerationService
BlenderDomainTools
ScenePreviewExporter
ViewerSyncService
  ↓
MCP/API Adapters
  ↓
Blender / 本地 Hunyuan 服务 / 图像生成工具
```

### 2.1 主要工程原则

工作流使用结构化 `AgentProjectState` 作为事实源。

不要把原始聊天历史当成事实源。

不要在 graph state 中存储图片字节、GLB 字节、`.blend` 二进制数据或大型 base64 数据。graph state 只存 artifact 引用。

---

## 3. V1 工作流阶段

```python
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
```

---

## 4. 主工作流图

```text
START
  ↓
IntakeRouter
  ↓
ReferenceBindingValidator
  ↓
SceneInterpreter
  ↓
SceneSpecCompiler
  ↓
ConceptPromptPlanner
  ↓
ImageGenerationExecutor
  ↓
ConceptVisualQA
  ↓
ConceptReviewGate
  ├─ 用户要求修改 → FeedbackPatchParser → RegenerationRouter → ConceptPromptPlanner
  └─ 用户批准 → SubjectAssetPlanner
  ↓
SubjectAssetGenerationExecutor
  ↓
SubjectAssetQualityEvaluator
  ├─ 资产失败 → SubjectAssetRepairRouter → ConceptPromptPlanner 或 SubjectAssetGenerationExecutor
  └─ 资产通过 → SceneGenerationPlanner
  ↓
SceneGenerationExecutor
  ↓
SceneAssetAdapter
  ↓
BlenderAssemblyPlanner
  ↓
BlenderCommandExecutor
  ↓
SceneStateSynchronizer
  ↓
ScenePreviewExporter
  ↓
ViewerSyncService
  ↓
BlenderPreviewRenderer（按需/高质量确认）
  ↓
BlenderPreviewReviewGate
  ├─ 用户要求 Blender 编辑 → BlenderEditRouter → BlenderCommandExecutor
  ├─ 用户要求重做主体 → FeedbackPatchParser → ConceptPromptPlanner → SubjectAssetGenerationExecutor
  ├─ 用户要求重做场景 → SceneGenerationPlanner
  └─ 用户批准 → DeliveryPackager
  ↓
END
```

---

## 5. 节点目录

### 5.1 IntakeRouter / 输入路由器

**类型：** LLM 辅助路由 + 确定性阶段规则  
**输入：** `user_input`, `current_phase`, `uploaded_images`  
**输出：** `intent`, `phase_next_candidate`  

职责：

```text
将用户当前回合分类为：
- NEW_SCENE_REQUEST
- CONCEPT_FEEDBACK
- CONCEPT_APPROVAL
- BLENDER_EDIT
- BLENDER_APPROVAL
- SUBJECT_REDO_REQUEST
- SCENE_REDO_REQUEST
- GENERAL_QUESTION
```

规则：

```text
同一句话在不同阶段可能表示不同含义。
“看起来不错”在 CONCEPT_REVIEW 中表示概念已批准。
“看起来不错”在 BLENDER_PREVIEW 中表示 Blender 预览已批准。
```

---

### 5.2 ReferenceBindingValidator / 参考图绑定校验器

**类型：** 确定性校验 + 可选 MLLM 辅助  
**输入：** 用户文本、上传图片、声明的图片绑定  
**输出：** `reference_bindings`, `open_questions`  

职责：

```text
检查 image_id 是否存在。
检查主体编号是否存在或是否可以创建。
检查图片用途是否显式说明。
当绑定含糊时拒绝或要求澄清。
```

V1 要求用户在文本中显式绑定图片用途。

---

### 5.3 SceneInterpreter / 场景理解器

**类型：** LLM/MLLM 结构化抽取  
**输入：** 用户文本、参考图 metadata、可选图像观察结果  
**输出：** 初步场景理解结果  

抽取：

```text
场景主题
环境
主体
外观
姿态/状态
风格
灯光
相机/构图
空间关系
约束条件
```

---

### 5.4 SceneSpecCompiler / 场景规格编译器

**类型：** 确定性合并 + LLM 归一化  
**输入：** interpretation、reference bindings、可选上一版 SceneSpec  
**输出：** `SceneSpec`  

职责：

```text
生成稳定的 subject_ids。
生成归一化空间关系。
合并显式图片绑定。
必要时创建 open_questions。
输出机器可校验的 JSON。
```

---

### 5.5 ConceptPromptPlanner / 概念图提示规划器

**类型：** LLM 结构化规划  
**输入：** `SceneSpec`, `ReviewPatch[]`, reference bindings  
**输出：** `ConceptPromptPack`  

为三种固定输出类别生成 prompt：

```text
final_preview_image prompt
subject_concept_image prompts
scene_concept_image prompts
```

主体图默认规范：

```text
单主体
3/4 视图
完整轮廓
干净背景
居中
均匀光照
```

---

### 5.6 ImageGenerationExecutor / 图像生成执行器

**类型：** 确定性工具执行器  
**输入：** `ConceptPromptPack`  
**输出：** `ConceptBundle` artifacts  

职责：

```text
调用图像生成服务/工具。
将图片存入 ArtifactStore。
记录生成参数。
更新 ConceptBundle。
```

该节点可以通过本地服务或 MCP adapter 调用图像生成工具。它本身不做艺术决策。

---

### 5.7 ConceptVisualQA / 概念图视觉质检器

**类型：** MLLM + 规则检查  
**输入：** `SceneSpec`、生成的概念图  
**输出：** `VisualQAResult`  

检查：

```text
主体数量
参考一致性
风格不匹配
主要空间关系不匹配
缺失 hero subject
主体图是否适合 Hunyuan3D
```

如果输出严重错误，该节点可以自动触发一次重试。它不应进入无限重试。

---

### 5.8 ConceptReviewGate / 2D 概念审查门

**类型：** 用户 interrupt / 外部输入门  
**输入：** `ConceptBundle`  
**输出：** 用户批准或反馈  

这是 V1 默认用户确认点 #1。

用户可以：

```text
批准概念
要求修改
提出问题
```

---

### 5.9 FeedbackPatchParser / 反馈补丁解析器

**类型：** LLM 结构化输出  
**输入：** 用户反馈、当前阶段、当前 SceneSpec、当前预览图  
**输出：** `ReviewPatch[]`  

补丁目标类别：

```text
GLOBAL_STYLE_CHANGE
LIGHTING_CHANGE
CAMERA_CHANGE
SCENE_LAYOUT_CHANGE
SUBJECT_APPEARANCE_CHANGE
SUBJECT_POSE_CHANGE
ADD_SUBJECT
REMOVE_SUBJECT
REPLACE_SUBJECT
MATERIAL_CHANGE
```

---

### 5.10 RegenerationRouter / 重生成路由器

**类型：** 确定性路由 + 可选 LLM 辅助  
**输入：** `ReviewPatch[]`, current phase  
**输出：** 下一阶段 / 受影响 artifacts  

决定：

```text
只重生成 final_preview
重生成某个主体图
重生成场景概念图
重生成所有概念图
重做某个主体资产
重做场景生成
只做纯 Blender 编辑
```

---

### 5.11 SubjectAssetPlanner / 主体资产规划器

**类型：** 确定性规则  
**输入：** 已批准的 ConceptBundle、SceneSpec  
**输出：** `SubjectAssetJob[]`  

规则：

```text
只有 needs_3d_asset=true 的主体进入 Hunyuan3D。
使用 subject_concept_image 作为输入。
默认图片策略：干净的单主体 3/4 图。
每个主体一个 job。
```

---

### 5.12 SubjectAssetGenerationExecutor / 主体 3D 生成执行器

**类型：** 确定性 API 执行器  
**输入：** `SubjectAssetJob[]`  
**输出：** `Asset3DRecord[]`  

调用：

```text
Hunyuan3D-2.1 local service
```

职责：

```text
提交 job
轮询状态
获取 GLB/OBJ/texture
存储 artifacts
写入 Asset3DRecord
```

---

### 5.13 SubjectAssetQualityEvaluator / 主体资产质检器

**类型：** 确定性检查 + Blender 预览 + MLLM 视觉 QA  
**输入：** `Asset3DRecord`、源主体图  
**输出：** 质量状态 / 返修建议  

检查：

```text
文件存在
文件大小非零
Blender 导入成功
mesh/scene object 存在
asset 预览渲染存在
与源图的视觉相似度
严重变形
严重纹理问题
```

V1 不要求用户批准每个资产。只有当资产质量不确定或失败时，才展示给用户。

---

### 5.14 SubjectAssetRepairRouter / 主体资产返修路由器

**类型：** 确定性路由 + MLLM 建议  
**输入：** asset QA result  
**输出：** 返修路线  

路线：

```text
用同一 Hunyuan3D job 策略重试
重生成 subject_concept_image
当质量不确定时询问用户
将非关键背景资产标记为可接受
```

---

### 5.15 SceneGenerationPlanner / 场景生成规划器

**类型：** LLM/MLLM 结构化规划  
**输入：** `SceneSpec`, `scene_concept_images`, final preview  
**输出：** `SceneGenerationRequest`  

职责：

```text
选择场景输入图/prompt。
准备场景生成 prompt。
如果服务支持选项，则选择期望输出策略。
捕获对 adapter/placement 有用的语义标签。
```

---

### 5.16 SceneGenerationExecutor / 场景生成执行器

**类型：** 确定性 API 执行器  
**输入：** `SceneGenerationRequest`  
**输出：** 原始场景输出 artifact  

调用：

```text
SceneGenerationService
```

本地服务可能是 Hunyuan Mirror / HunyuanWorld / HY-World 的变体。执行器不应假设固定的原始格式。

---

### 5.17 SceneAssetAdapter / 场景资产适配器

**类型：** 确定性转换器/适配器  
**输入：** 原始场景输出  
**输出：** `Scene3DRecord`、Blender 可消费 artifact  

适配矩阵：

```text
mesh output
  → 可导入 mesh artifact

3DGS / gaussians.ply
  → 3DGS 图层或插件兼容 artifact

point cloud
  → 点云/代理/参考层

depth maps + camera params
  → 重建/参考包；可选代理 mesh 生成

COLMAP package
  → 3DGS/场景重建包或相机/点云脚手架
```

如果非可编辑场景层能帮助视觉构图和 Blender 预览，V1 可以接受。主体资产仍然单独可编辑。

---

### 5.18 BlenderAssemblyPlanner / Blender 装配规划器

**类型：** LLM/MLLM 结构化规划 + 代码校验  
**输入：** `SceneSpec`、主体资产、场景资产记录、概念图  
**输出：** `BlenderAssemblyPlan`  

职责：

```text
决定导入哪些资产。
生成近似摆放计划。
用语义估计相对尺度。
规划相机和灯光。
必要时规划基础材质覆盖。
```

重要规则：

```text
V1 不强制刚性的全局尺寸归一化。
尺度是近似的、语义驱动的。
```

尺度估计来源：

```text
主体类别
场景上下文
用户描述
参考图线索
视觉预览修正
```

---

### 5.19 BlenderCommandExecutor / Blender 命令执行器

**类型：** 确定性领域工具执行器  
**输入：** `BlenderAssemblyPlan` 或编辑操作计划  
**输出：** 工具结果、更新后的 Blender artifacts  

只调用：

```text
BlenderDomainTools
```

它不会把原始 Blender MCP 工具暴露给 LLM 节点。

---

### 5.20 SceneStateSynchronizer / 场景状态同步器

**类型：** 确定性 MCP 读回  
**输入：** Blender 当前场景  
**输出：** `BlenderSceneState`  

读取：

```text
对象列表
对象 transform
相机状态
灯光状态
渲染设置
blend 文件路径
```

---


### 5.21 ScenePreviewExporter / Web 端场景预览导出器

**类型：** 确定性导出器
**输入：** `BlenderSceneState`, `.blend` 权威场景
**输出：** `viewer_scene.glb` / `viewer_scene.gltf`、`scene_state.json`、`ViewerSceneState`

职责：

```text
从 Blender 权威场景导出前端可加载的 GLB/glTF 场景快照。
生成或更新 scene_state.json。
保持 subject_id、asset_id、blender_object_id 和前端 object_id 的映射。
必要时对贴图和路径做前端可访问化处理。
```

说明：V1 不能只依赖 Blender 渲染图片给用户查看。该节点是前端实时 3D Viewer 的数据来源。

### 5.22 ViewerSyncService / 前端预览同步服务

**类型：** 确定性事件推送服务
**输入：** `ViewerSceneState`, artifact 更新、workflow event
**输出：** WebSocket/SSE 事件

职责：

```text
通知前端新的 viewer_scene 可用。
通知前端当前 phase、node 和 progress。
通知前端对象列表、选中对象、版本号和可用操作。
在用户修改后推送更新后的场景快照。
```

### 5.23 BlenderPreviewRenderer / Blender 高质量预览渲染器


**类型：** 确定性 Blender 领域工具  
**输入：** `BlenderSceneState`, render preset  
**输出：** 预览渲染 artifact  

职责：

```text
按需生成 Blender 高质量预览渲染图。
存储预览图片。
更新 blender_scene.preview_image_id。
该节点不承担前端日常 orbit/zoom/pan 查看；实时查看由 ScenePreviewExporter 和 Web3DPreviewRuntime 支持。
```

---

### 5.24 BlenderPreviewReviewGate / Blender 预览审查门

**类型：** 用户 interrupt / 外部输入门  
**输入：** Web 端实时 3D 场景、按需生成的 Blender 高质量预览图片  
**输出：** 批准或编辑请求  

这是 V1 默认用户确认点 #2。

---

### 5.25 BlenderEditRouter / Blender 编辑路由器

**类型：** LLM 结构化路由 + 确定性阶段规则  
**输入：** 用户编辑请求、当前 BlenderSceneState、SceneSpec  
**输出：** 编辑路线  

路线：

```text
纯 transform 编辑
相机编辑
灯光编辑
材质编辑
新增主体
删除主体
替换主体
从 2D 概念重做主体
重做场景生成
```

---

### 5.26 DeliveryPackager / 交付打包器

**类型：** 确定性交付打包器  
**输入：** project state、artifacts  
**输出：** 交付包  

交付包包含：

```text
.blend
viewer_scene.glb / viewer_scene.gltf
scene_state.json
预览渲染图
主体 GLB/贴图
场景 artifacts
metadata JSON
```

---

## 6. 工具暴露策略

### 6.1 原始 MCP 工具

原始 MCP 工具来自现有 Blender MCP server。它们可能包括低层对象变换、渲染调用、Python 执行、材质更新、导出和场景检查。

LLM 不应直接看到所有原始工具。

### 6.2 领域工具

工作流暴露稳定的领域级工具：

```text
scene.import_asset_to_scene
scene.import_scene_layer
scene.place_subject
scene.move_subject
scene.rotate_subject
scene.scale_subject
scene.replace_subject
scene.delete_subject
scene.setup_camera
scene.setup_lighting
scene.export_viewer_scene
scene.render_preview
scene.save_blend_file
scene.export_scene_package
```

### 6.3 按阶段限定工具白名单

```python
TOOLS_BY_PHASE = {
    "CONCEPT_GENERATION": [
        "image.generate_final_preview",
        "image.generate_subject_concept",
        "image.generate_scene_concept",
    ],
    "SUBJECT_ASSET_GENERATION": [
        "hunyuan3d.generate_subject_asset",
        "hunyuan3d.check_job_status",
    ],
    "SCENE_ASSET_GENERATION": [
        "scene_generation.generate_scene_asset",
    ],
    "SCENE_ASSET_ADAPTATION": [
        "scene_adapter.convert_scene_output",
    ],
    "BLENDER_ASSEMBLY_EXECUTION": [
        "scene.import_asset_to_scene",
        "scene.import_scene_layer",
        "scene.place_subject",
        "scene.setup_camera",
        "scene.setup_lighting",
        "scene.export_viewer_scene
scene.render_preview",
    ],
    "BLENDER_EDIT": [
        "scene.move_subject",
        "scene.rotate_subject",
        "scene.scale_subject",
        "scene.replace_subject",
        "scene.delete_subject",
        "scene.setup_camera",
        "scene.setup_lighting",
        "scene.export_viewer_scene
scene.render_preview",
    ],
}
```

---

## 7. 上下文管理

### 7.1 事实源

事实源是：

```text
AgentProjectState
SceneSpec
ConceptBundle
ReviewPatch[]
Asset3DRecord[]
Scene3DRecord
BlenderSceneState
Artifact metadata
```

### 7.2 LLM 上下文视图

不要把完整 project state 发送给每个 LLM 节点。每个节点只接收最小上下文视图。

示例：

```text
SceneInterpreterContext
  用户输入
  图片绑定声明
  图片 metadata

ConceptPromptPlannerContext
  SceneSpec
  active ReviewPatch list
  prior prompt pack summary

BlenderAssemblyPlannerContext
  SceneSpec
  asset manifest summary
  scene asset summary
  concept preview thumbnail/description
  allowed domain operations

BlenderEditRouterContext
  current BlenderSceneState summary
  user edit request
  latest preview image
  allowed edit operations
```

### 7.3 Artifact 引用

图片和 3D 资产以以下形式传递：

```text
artifact_id
uri
mime_type
semantic_role
version
metadata
```

不要在 state 中传递原始字节。

---

## 8. 摆放策略

V1 不尝试严格的物理/世界尺度归一化。

摆放基于：

```text
语义尺度估计
美学构图
SceneSpec 中的空间关系
LLM/MLLM 推理
Blender 预览反馈
可用时的基础碰撞/可见性检查
```

### 8.1 SemanticScaleEstimator / 语义尺度估计器

**类型：** LLM 辅助启发式  
**输入：** 主体类别、场景上下文、描述、参考图片  
**输出：** 近似相对尺度提示  

示例：

```text
站立女孩旁边的猫应明显小于女孩。
桌子相对人物应大约在腰部高度。
建筑立面相对角色应占主导尺度。
```

### 8.2 PlacementSolver / 摆放求解器

**类型：** 确定性 + LLM 计划校验  

该求解器把语义摆放转换为 Blender transforms。它可能使用：

```text
相对位置
前/后/左/右关系
锚点区域
相机可见性
主体优先级
预览美学
```

---

## 9. 错误处理

### 9.1 图像生成失败

```text
重试一次
如果重复失败 → 将节点标记为失败，并询问用户/系统操作员
```

### 9.2 主体资产失败

```text
重试 Hunyuan3D
如果仍然失败 → 重生成 subject_concept_image
如果仍然失败 → 展示给用户，或将背景对象标记为可选
```

### 9.3 场景生成失败

```text
重试 SceneGenerationService
如果输出类型无法适配 → 使用 scene_concept_image 作为视觉参考，并创建代理 Blender 环境
```

### 9.4 Blender 装配失败

```text
检查原始 MCP 错误
重试安全操作
同步 BlenderSceneState
如果对象导入失败 → 标记具体资产失败
如果场景损坏 → 恢复上一个 checkpoint / 上一个 .blend 版本
```

---

## 10. Checkpoints

工作流应在以下节点之后 checkpoint：

```text
SceneSpec 创建完成
ConceptBundle 生成完成
Concept 获得批准
每个主体资产生成完成
场景资产适配完成
Blender 装配计划创建完成
Web 端预览场景导出完成
Blender 高质量预览渲染完成
用户编辑应用完成
交付包生成完成
```

---

## 11. V1 最小实现顺序

每次进入落地实现前，先执行一次已有基础设施盘点，不允许默认从零重写已存在能力。盘点范围至少包括：

```text
docs/runtime_environment_plan.md
docs/blender_asset_pipeline_contract.md
scripts/ 下的服务启动、停止、状态检查脚本
tools/ 下的 Blender/GLB 导入、渲染、检查工具
web/ 下的 GLB viewer
Hunyuan3D-2.1、HY-World-2.0、third_party/、outputs/、run_logs/
Codex MCP 配置中的 blender_lab 与可用的 codex-self-mcp 子 agent 通道
```

如果新实现与已有基础设施重叠，必须先说明为什么不能复用或轻量改造已有实现。

当前代码侧已有只读盘点入口，后续实现前应优先运行并按结果更新计划：

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.infra_inventory --root /home/team/zouzhiyuan/image23D_Agent --json
```

计划或进度记录中必须写清：

```text
本步检查了哪些已有基础设施
复用了哪些脚本、服务、工具或 MCP 通道
哪些能力只补 thin adapter
哪些能力确实需要新增实现，以及不能复用的原因
```

```text
0. 已有基础设施盘点与复用决策
1. 状态 schema + artifact store
2. Hunyuan3D client + 单主体 GLB 测试
3. Blender MCP wrapper + 导入/导出 GLB 场景快照/渲染/保存测试
4. SceneSpec 生成
5. 2D 概念生成循环
6. 主体资产 pipeline
7. SceneGenerationService adapter stub
8. Blender 装配 pipeline
9. Web 端 3D Viewer 场景快照同步
10. Blender 编辑循环
11. 交付包
```

---

## 12. 研究依据

本版本使用的关键外部技术参考：

```text
HunyuanWorld-Mirror GitHub:
https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

HY-World 2.0 GitHub:
https://github.com/Tencent-Hunyuan/HY-World-2.0

HunyuanWorld-1.0 GitHub:
https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0

LangGraph graph/persistence/interrupt docs:
https://docs.langchain.com/oss/python/langgraph/overview
https://docs.langchain.com/oss/python/langgraph/persistence
https://docs.langchain.com/oss/python/langgraph/interrupts
```
