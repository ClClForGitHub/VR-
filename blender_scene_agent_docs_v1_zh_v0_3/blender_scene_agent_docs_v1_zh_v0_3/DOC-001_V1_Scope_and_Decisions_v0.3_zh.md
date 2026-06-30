# DOC-001：V1 范围与决策

**文档编号：** DOC-001  
**文档名称：** V1 范围与决策  
**版本：** v0.3  
**状态：** V1 工程草案冻结版  
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

本文档用于冻结 **文本+图像到 Blender 场景 Agent** 项目的 V1 范围、核心路线、已确认决策、非目标、技术假设、未解决问题和成功标准。

该 Agent 会把自然语言场景描述和用户明确绑定用途的参考图片转换为 Blender 场景。系统会生成 2D 概念图、主体级 3D 静态资产、场景级 3D 环境输出、Blender 装配结果、Web 端实时 3D 预览、Blender 高质量渲染图，并支持用户迭代编辑。

---

## 2. V1 目标

V1 应交付一条稳定的静态场景工作流：

```text
用户自然语言 + 明确引用的图片
→ 结构化 SceneSpec
→ 2D 概念生成
→ 用户概念审查
→ 主体级 Hunyuan3D img2asset
→ 场景级 Hunyuan Mirror / HY-World 场景生成
→ 通过 Blender MCP wrapper 进行 Blender 场景装配
→ LLM 引导的摆放、灯光、相机和场景状态同步
→ 导出 Web 端 GLB/glTF 预览快照 + 按需 Blender 渲染预览
→ 用户在 Web 端实时 3D 预览和 Blender 渲染结果上进行编辑循环
→ 交付包
```

V1 的成功原则不是一次性完美生成。目标是：

```text
可分解
可编辑
可恢复
可版本化
可局部重生成
可导入 Blender
可由 LLM Agent 调整
可被 Web 端实时 3D Viewer 查看
```

---

## 3. V1 核心路线

V1 采用以下路线：

```text
主体级 Hunyuan3D img2 3D
+
场景级 Hunyuan Mirror / HY-World 本地场景生成
+
基于 Blender MCP wrapper 的场景装配
+
LLM/MLLM 引导的布局、修正和审查
```

### 3.1 主体路线

角色、动物、道具、家具、载具和重要环境物体等主体，会作为独立 3D 资产生成：

```text
subject_concept_image
→ Hunyuan3D-2.1 本地服务
→ subject GLB / OBJ / mesh / texture
→ 导入 Blender
```

### 3.2 场景路线

场景/环境生成交给本地部署的 Hunyuan Mirror / HunyuanWorld / HY-World 类型服务完成，并在系统中抽象为：

```text
SceneGenerationService
```

系统不能假设场景服务总是返回可编辑 mesh。根据当前公开的 HunyuanWorld-Mirror / HY-World 文档，可能输出包括：

```text
mesh
3D Gaussian Splatting / 3DGS
point cloud
depth maps
surface normals
camera parameters
COLMAP-style camera/points package
scene package
```

因此 V1 引入：

```text
SceneAssetAdapter
```

该适配器负责把场景输出转换为 Blender 可消费的内容，例如场景层、背景、代理几何体、导入 mesh、3DGS 图层、点云参考，或用于摆放/参考的脚手架。

### 3.3 Blender 路线

Blender 阶段不是原始的“让 LLM 自由运行 Blender Python”的阶段，而是：

```text
LLM/MLLM 规划
→ 领域级 Blender 工具
→ 内部 Blender MCP adapter
→ 一个或多个原始 Blender MCP server
→ Blender 场景操作
```

业务层调用稳定的领域工具，例如：

```text
import_asset_to_scene
place_subject
move_subject
rotate_subject
scale_subject
replace_subject
delete_subject
setup_camera
setup_lighting
render_preview
save_blend_file
export_scene_package
```

原始 Blender MCP 工具隐藏在 wrapper 后面。

---

## 4. V1 用户输入

V1 支持：

```text
1. 自然语言场景描述
2. 上传的参考图片
3. 用户文本中明确声明的图片用途绑定
4. 用户对 2D 概念结果的反馈
5. 用户对 Blender 预览结果的反馈
```

### 4.1 必须显式绑定图片用途

V1 要求用户在文本中明确说明图片用途。示例：

```text
主体 1 参考图：image_001
主体 2 参考图：image_002
场景参考图：image_003
风格参考图：image_004
主体 1 姿态参考图：image_005
```

支持的用途标签：

```text
subject_reference
scene_reference
style_reference
pose_reference
texture_reference
layout_reference
```

系统会校验绑定关系，但默认不会静默猜测绑定关系。

---

## 5. V1 输出

V1 交付：

```text
1. final_preview_image
   用于用户审查的整体 2D 概念图。

2. subject_concept_images
   每个主体对应的图片，用于 Hunyuan3D 主体资产生成。

3. scene_concept_images
   场景/环境图片，用于 SceneGenerationService 和 Blender 布局参考。

4. subject_3d_assets
   来自 Hunyuan3D-2.1 的主体 GLB / OBJ / mesh / texture。

5. scene_3d_assets
   来自 Hunyuan Mirror / HY-World 类型服务的场景级输出，并由 SceneAssetAdapter 适配。

6. blender_scene_file
   .blend 文件。

7. web3d_preview_scene
   给前端实时查看使用的 GLB/glTF 场景快照和 scene_state.json。

8. blender_preview_renders
   来自 Blender 的高质量预览渲染图，用于关键确认和最终交付，不作为日常实时查看的唯一方式。

9. export_package
   包含 .blend、GLB 资产、贴图、预览图和 metadata JSON 的打包交付物。
```

---

## 6. V1 必需能力

### 6.1 场景理解

系统需要提取并结构化：

```text
场景主题
环境
主体
主体外观
主体姿态/状态
空间关系
风格
灯光
相机/构图
参考图片绑定
约束条件
```

输出为结构化的 `SceneSpec`。

### 6.2 固定 2D 输出

V1 固定三类 2D 输出：

```text
final_preview_image
subject_concept_images
scene_concept_images
```

主体图默认规范：

```text
单主体
3/4 视图
完整可见轮廓
居中
干净/简单背景
均匀光照
尽量少遮挡
适合 img2 3D
```

三视图不是 V1 默认方案。如果 Hunyuan3D 测试显示三视图能稳定提升质量，可以作为 fallback 或未来优化加入。

### 6.3 用户反馈循环

V1 支持用户对以下内容提出反馈：

```text
主体外观
主体姿态
场景风格
灯光
相机/构图
新增主体
删除主体
替换主体
重做某个主体
```

反馈必须被解析为结构化 `ReviewPatch` 记录。

### 6.4 主体 img2 3D

每个主体 3D 资产必须记录：

```text
subject_id
source_image_id
generation_job_id
mesh_uri
glb_uri
texture_uri
preview_image_id
quality_status
generation_params
```

### 6.5 场景生成

场景生成通过以下服务路由：

```text
SceneGenerationService
```

该服务可能返回 mesh、3DGS、点云、深度/相机/法线包，或其他中间表示。`SceneAssetAdapter` 会把输出转换为 Blender 可消费的 artifact。

V1 不要求生成的场景一定是完全可语义编辑的 mesh 组件。只要 Blender 装配和预览可以继续推进，场景可以是视觉/空间图层、代理环境、导入 mesh 层，或 3DGS/点云辅助背景。

### 6.6 Blender 场景装配

V1 必须支持：

```text
导入主体 3D 资产
导入/适配场景资产
必要时创建基础环境辅助元素
摆放主体
调整 location/rotation/scale
设置相机
设置灯光
设置基础材质
渲染预览
保存 .blend
导出交付包
```

### 6.7 Blender 编辑循环

V1 支持：

```text
移动主体
删除主体
新增主体
替换主体
修改相机
修改灯光
简单材质编辑
重做某个主体
重新渲染预览
```

系统必须分类用户请求应由以下哪一层处理：

```text
纯 Blender 操作
主体资产重生成
场景资产重生成
2D 概念重生成
全局重新规划
```

### 6.8 3D 资产审查策略

V1 默认有两个用户确认点：

```text
1. 2D Concept Review
2. Blender Preview Review
```

V1 **不**为每个 3D 资产增加默认用户确认点。3D 资产由系统检查和 MLLM/预览 QA 评估。只有当质量不确定、明显失败，或返修路线需要用户选择时，才把 3D 资产展示给用户。

---

## 7. V1 非目标

V1 不包含：

```text
复杂骨骼动画
自动上骨架 / auto-rigging
复杂角色 rigging
蒙皮权重 / skinning
动作重定向 / retargeting
物理仿真
高级 shader/material node 创作
自动专业级 UV 修复
自动外部资产库检索
多用户协同编辑
云渲染农场
完整游戏关卡生成
完全自主的美术总监式行为
```

V1 不承诺主体骨骼动作。Hunyuan3D 输出的主体资产默认视为静态 mesh/GLB；如果未来需要“让角色挥手、奔跑、跳舞”等动作，需要单独建设 AutoRiggingService、AnimationClipLibrary、RetargetingService 和动画 QA，不纳入 V1。

---

## 8. 已确认决策

### D1. V1 使用 LangGraph

V1 使用 LangGraph 作为工作流编排层。系统是 workflow-first agent，不是自由形态的多 agent 聊天系统。

### D2. V1 不做通用多 agent 群体

采用：

```text
LangGraph workflow
+ 结构化状态
+ LLM/MLLM 节点
+ 确定性执行节点
+ MCP/API 工具节点
```

V1 不使用多个自主 agent 互相聊天的设计。

### D3. Hunyuan3D-2.1 处理主体资产

角色、道具、家具、载具、动物和重要场景物件使用 Hunyuan3D-2.1 做主体级 img2asset。

### D4. Hunyuan Mirror / HY-World 本地服务处理场景生成

场景级生成抽象为 `SceneGenerationService`。

### D5. Blender 装配仍由 Agent 控制

即使场景服务生成了场景层或 3D 世界表示，Blender 装配仍然需要 LLM/MLLM + 领域工具来完成：

```text
导入/转换场景输出
摆放主体资产
大致对齐主体与场景尺度
设置视觉构图
调整灯光/相机
渲染和迭代
```

### D6. 2D 生成有三种固定输出类别

```text
final_preview_image
subject_concept_images
scene_concept_images
```

### D7. 用户必须在文本中显式绑定图片

V1 不做静默自动绑定。

### D8. Blender MCP 必须被封装

团队可以测试多个现有 Blender MCP server，但面向生产的代码使用：

```text
BlenderDomainTools
BlenderMCPAdapter
```

### D9. V1 支持实用的 Blender 编辑

```text
移动/删除/新增/替换主体
相机编辑
灯光编辑
简单材质编辑
重做某个主体
```

### D10. 主体图默认 3/4 视图

V1 默认 `subject_concept_image` 是干净、单主体、3/4 视图的资产图。

### D11. 摆放由美学引导，不做刚性归一化

V1 不强加统一的全局尺寸归一化规则。相对物体尺度从以下信息估计：

```text
场景语义
主体类别
用户描述
参考图片
LLM/MLLM 视觉判断
Blender 预览反馈
```

系统采用近似摆放和美学构图，然后依赖预览迭代。

### D12. V1 必须提供 Web 端实时 3D 预览

V1 不能只通过 Blender 渲染图片让用户查看场景。Blender 运行在 Linux 服务器上，作为权威场景编辑、装配、保存和最终渲染环境；前端需要通过导出的 GLB/glTF 场景快照和 `scene_state.json` 提供实时 3D 查看。

```text
Blender 权威场景
→ ScenePreviewExporter 导出 viewer_scene.glb / viewer_scene.gltf
→ ViewerSyncService 推送 scene_state.json 和 artifact 更新
→ Web3DPreviewRuntime 在浏览器中加载并实时查看
```

V1 前端至少支持：

```text
orbit 旋转查看
zoom 缩放查看
pan 平移查看
主体选择和高亮
当前对象信息展示
根据后端事件刷新场景快照
```

Blender 渲染图用于高质量确认、QA 和最终交付，不承担每一次用户查看和相机浏览。

### D13. 角色骨骼动画不进入 V1

V1 只处理静态主体资产和静态场景装配。Hunyuan3D 生成的 GLB 默认不含骨架、蒙皮权重和动画 clip。MCP 可以调用 Blender 执行工具，但不能让无骨架 mesh 自动变成可挥手、跑步或跳舞的角色。

角色动作相关能力推迟到后续版本，届时需要单独设计：

```text
inspect_glb_rig_info
AutoRiggingService
Skinning / Weight Binding
AnimationClipLibrary
RetargetingService
AnimationPreview / Export
```

---

## 9. 剩余未决问题

### Q1. 本地场景服务的精确输出契约

必须确认本地 Hunyuan Mirror / HY-World 服务契约：

```text
输入模态
输出格式
文件格式
运行时画像
是否输出 mesh，还是只输出 3DGS/点云/深度/相机结果
```

### Q2. 每种场景输出类型的 Blender 导入路径

V1 需要具体适配矩阵：

```text
mesh → 作为 mesh 导入
3DGS → 通过 3DGS 插件或转换器导入/使用
point cloud → 作为点云/代理/参考导入
深度 + 相机 → 用于重建/参考/脚手架
COLMAP package → 用于 3DGS/场景重建工作流
```

### Q3. 主 Blender MCP server

项目会测试现有 Blender MCP server，但生产访问统一通过 `BlenderMCPAdapter`。能力测试后应选择一个主 MCP 和一个 fallback MCP。

### Q4. Hunyuan3D 质量阈值

主体资产质量的具体失败阈值需要通过 spike 测试确认。

### Q5. 场景/主体坐标对齐

摆放系统不应过度依赖刚性归一化。它应使用语义尺寸估计和视觉预览调整。仍然需要最小技术约定：

```text
Blender 单位约定
场景地面定义
物体原点策略
相机默认坐标约定
资产导入 transform metadata
```

---

## 10. 技术假设

V1 假设：

```text
1. 本地 Hunyuan3D-2.1 可以从干净的 3/4 主体图生成可用的主体级 GLB/mesh 资产。

2. 本地 Hunyuan Mirror / HY-World 服务可以提供可由 SceneAssetAdapter 使用的场景级 3D 输出。

3. 至少一个 Blender MCP 实现可以可靠支持导入、变换、相机、灯光、渲染、保存和导出操作。

4. LLM/MLLM 可以为 SceneSpec、ReviewPatch、BlenderAssemblyPlan 和 QA 报告稳定生成结构化 JSON。

5. 大型二进制 artifact 存储在 ArtifactStore 中，不存入 graph state。

6. LangGraph 可以支持 V1 阶段工作流、checkpoint 和用户反馈循环。
```

---

## 11. 风险

### R1. 场景输出可能不是可编辑 mesh

缓解方式：`SceneAssetAdapter` 将场景输出视为 mesh、3DGS、点云、代理层或参考层之一。

### R2. 场景和主体尺度可能不匹配

缓解方式：使用 `SemanticScaleEstimator`、预览渲染和迭代修正，而不是刚性的全局归一化。

### R3. 暴露原始 Blender MCP 可能破坏场景稳定性

缓解方式：LLM 只看到领域工具；原始 MCP 工具保留在 `BlenderMCPAdapter` 后面。

### R4. 用户反馈可能指向错误层级

缓解方式：`FeedbackPatchParser` + `RegenerationRouter` 分类反馈属于 2D 概念、主体资产、场景资产还是 Blender 操作。

### R5. 主体 3D 质量可能波动

缓解方式：系统级资产 QA、重试、必要时展示给用户，以及针对单主体的重生成。

### R6. 场景生成质量可能视觉有用但结构难编辑

缓解方式：V1 接受场景输出作为背景/代理/3DGS 层，同时让 Agent 单独摆放可编辑主体资产。

---

## 12. V1 成功标准

如果满足以下条件，V1 即视为成功：

```text
1. 用户可以通过文本和明确绑定的参考图片创建场景项目。

2. 系统可以生成有效的 SceneSpec。

3. 系统可以生成 final_preview_image、subject_concept_images 和 scene_concept_images。

4. 用户反馈可以更新 SceneSpec/ReviewPatch，并触发局部重生成。

5. 主体概念图可以转换为可导入 Blender 的主体资产。

6. 本地场景服务可以生成由 SceneAssetAdapter 消费的场景输出。

7. Blender MCP wrapper 可以导入/适配场景输出和主体资产。

8. Agent 可以用近似美学构图摆放物体，而不是依赖刚性归一化。

9. Agent 可以设置相机、灯光，并导出 Web 端实时 3D 预览快照。

10. 用户可以在前端实时 3D Viewer 中 orbit/zoom/pan 查看场景。

11. Agent 可以按需触发 Blender 高质量渲染预览。

12. 用户可以通过自然语言命令编辑 Blender 场景。

13. 系统可以交付 .blend、Web 端预览场景、Blender 渲染图、3D 资产和 metadata package。
```

---

## 13. 后续文档

本文档之后是：

```text
DOC-002 Product Workflow Spec
DOC-003 Agent Workflow Design
DOC-004 State & JSON Schema Spec
DOC-005 Artifact & Versioning Spec
DOC-006 Tool & MCP Integration Spec
DOC-007 Hunyuan3D Pipeline Spec
DOC-008 LLM Node & Prompt Spec
DOC-009 QA & Evaluation Spec
```

下一批立刻可执行的文档是：

```text
DOC-003 Agent Workflow Design
DOC-004 State & JSON Schema Spec
```

---

## 14. 研究依据

本版本使用的关键外部技术参考：

```text
HunyuanWorld-Mirror GitHub:
https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

HY-World 2.0 GitHub:
https://github.com/Tencent-Hunyuan/HY-World-2.0

HunyuanWorld-1.0 GitHub:
https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0

LangGraph persistence / interrupts / orchestration docs:
https://docs.langchain.com/oss/python/langgraph/persistence
https://docs.langchain.com/oss/python/langgraph/interrupts
https://docs.langchain.com/oss/python/langgraph/overview
```
