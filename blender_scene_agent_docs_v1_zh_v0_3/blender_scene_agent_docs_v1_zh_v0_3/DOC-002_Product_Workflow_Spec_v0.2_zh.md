# DOC-002：产品流程规范

**文档编号：** DOC-002  
**文档名称：** 产品流程规范  
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

本文档从产品和交互视角定义 V1 用户流程。它说明用户如何输入自然语言和图片，如何查看 Agent 当前状态，如何审查 2D 概念图，如何进入主体 3D 与场景生成，如何在 Web 端实时 3D 查看场景、如何查看 Blender 高质量渲染预览，如何在同一个窗口继续修改，以及如何开始新的聊天或新项目。

本文档不定义底层 JSON schema、MCP 工具细节和 Hunyuan 调用参数。这些内容分别由以下文档定义：

```text
DOC-004：状态与 JSON Schema 规范
DOC-006：工具与 MCP 接入规范
DOC-007：Hunyuan3D / Hunyuan Mirror 生成链路规范
```

---

## 2. V1 产品目标

V1 产品目标是提供一个面向创作的交互式工作台，而不是单纯聊天框。用户应该能在同一个界面中完成：

```text
描述场景
上传参考图
明确图片绑定关系
查看 Agent 当前阶段
查看 2D 概念图
提出修改意见
确认 2D 概念
查看主体 3D / 场景生成进度
查看 Web 端实时 3D 场景和 Blender 高质量渲染预览
继续用自然语言修改 Blender 场景
导出结果
开始新项目或继续旧项目
```

V1 的体验重点是：

```text
可见进度
可解释状态
可局部修改
可继续迭代
可回到用户确认点
```

---

## 3. 目标用户流程总览

```text
创建项目
  ↓
输入自然语言 + 上传图片 + 明确图片用途
  ↓
Agent 解析 SceneSpec
  ↓
生成 2D 概念结果
  ↓
用户审查 2D 概念
  ├─ 不满意：自然语言反馈 → 局部重生成
  └─ 满意：确认进入 3D
  ↓
生成主体 3D 资产
  ↓
生成场景 3D 输出
  ↓
Blender 装配、摆放、打光、设置相机
  ↓
导出 Web 端实时 3D 预览场景
  ↓
按需生成 Blender 高质量渲染预览
  ↓
用户审查实时 3D 场景和 Blender 渲染预览
  ├─ 修改主体位置 / 相机 / 灯光 / 材质 / 增删主体
  ├─ 重做某个主体
  └─ 确认交付
  ↓
导出 .blend / GLB / 预览图 / metadata
```

---

## 4. 前端交互界面

V1 前端应设计为一个交互式创作窗口，包含以下区域。

### 4.1 左侧：聊天与输入区

负责：

```text
用户输入自然语言
用户上传图片
用户说明图片绑定关系
用户继续提出修改
用户确认阶段结果
用户开始新聊天 / 新项目
```

输入区应支持：

```text
多行文本输入
多图片上传
图片缩略图展示
图片 ID 展示
图片用途提示
发送按钮
重新生成按钮
确认按钮
开始新项目按钮
```

用户上传图片后，前端必须展示稳定的图片编号，例如：

```text
image_001
image_002
image_003
```

用户需要在文本中明确说明用途，例如：

```text
主体1参考图：image_001
主体2参考图：image_002
场景参考图：image_003
风格参考图：image_004
```

如果用户没有说明用途，系统应提示：

```text
请说明每张图片的用途，例如“主体1参考图：image_001，场景参考图：image_002”。
```

### 4.2 中间：可视化工作台

负责展示当前阶段的视觉结果。V1 的可视化工作台不能只展示 Blender 渲染图片，必须包含 Web 端实时 3D 查看器。

V1 至少展示：

```text
final_preview_image
subject_concept_images
scene_concept_images
Web 端实时 3D Viewer
Blender 高质量 preview render
最终交付预览
```

Web 端实时 3D Viewer 负责日常交互查看：

```text
加载 viewer_scene.glb / viewer_scene.gltf
加载 scene_state.json
支持 orbit 旋转查看
支持 zoom 缩放查看
支持 pan 平移查看
支持点击选择主体
支持高亮当前主体
展示 subject_id / object_name / 当前版本
根据后端事件刷新场景快照
```

Blender 高质量 preview render 负责关键确认：

```text
材质和灯光最终确认
高质量构图确认
QA 对比
最终交付图
```

可选展示：

```text
主体 3D asset preview
场景 3D asset preview
历史版本缩略图
```

V1 默认不把 3D asset preview 作为必经用户确认点。只有在系统质量判断不确定、失败或用户主动查看时展示。

### 4.3 右侧：Agent 状态面板

负责展示 Agent 当前正在做什么。

状态面板至少包含：

```text
当前阶段 phase
当前节点 node
阶段进度说明
已完成步骤
当前生成中的产物
错误/重试信息
当前可执行操作
当前版本号
```

示例：

```text
当前阶段：BLENDER_ASSEMBLY_EXECUTION
当前任务：正在将主体资产导入 Blender，并根据 SceneSpec 进行初始摆放
已完成：2D 概念确认、主体 3D 资产生成、场景资产生成
当前产物：blend_version_003
可执行操作：等待渲染预览
```

### 4.4 底部或顶部：项目与产物操作区

支持：

```text
确认当前 2D 方案
重新生成当前 2D 图
进入 3D 生成
重新生成某个主体
渲染 Blender 预览
导出交付包
新建项目
打开历史项目
```

### 4.5 Web 端实时 3D 预览与 Blender 渲染的分工

V1 明确采用双预览体系：

```text
Web3DPreviewRuntime：
  用于实时查看、旋转、缩放、平移、选择主体和查看场景状态。

BlenderRenderPreview：
  用于高质量视觉确认、最终渲染和 QA，不用于每一次用户自由浏览。
```

Blender 运行在 Linux 服务器上，不需要把 Blender GUI 直接暴露给用户。后端从 Blender 权威场景导出 GLB/glTF 快照和 scene_state.json，前端用 WebGL/Three.js/Babylon.js 类 viewer 加载。

前端实时查看的场景是 Blender 权威场景的可视化副本：

```text
.blend 权威场景
→ viewer_scene.glb / viewer_scene.gltf
→ scene_state.json
→ 前端 Web 3D Viewer
```

如果用户在前端通过自然语言要求修改，仍由 Agent 解析后调用 BlenderDomainTools 更新 Blender 权威场景。如果未来支持前端拖拽，拖拽产生的 transform_delta 也必须回写后端和 BlenderSceneState。

---

## 5. 阶段化用户体验

### 5.1 项目创建阶段

用户行为：

```text
新建项目
输入场景描述
上传参考图片
说明图片用途
```

系统行为：

```text
创建 project_id
创建 thread_id
保存上传图片 artifact
生成 input_image_id
进入 INTAKE 阶段
```

前端展示：

```text
图片缩略图
图片 ID
绑定说明提示
当前阶段：等待解析
```

### 5.2 场景理解阶段

系统行为：

```text
解析用户文本
校验图片绑定
生成 SceneSpec 草案
如果缺少必要绑定或描述，向用户追问
```

前端展示：

```text
正在理解场景
主体列表草案
场景风格草案
图片绑定表
open_questions
```

用户可操作：

```text
补充缺失信息
修改主体描述
修改图片绑定
```

### 5.3 2D 概念生成阶段

系统行为：

```text
生成 final_preview_image
生成 subject_concept_images
生成 scene_concept_images
```

前端展示：

```text
整体预览图
每个主体的概念图
场景概念图
当前 concept_version
```

用户可操作：

```text
确认 2D 方案
要求局部修改
要求整体重做
修改某个主体
新增/删除主体
```

### 5.4 2D 概念审查阶段

用户反馈示例：

```text
主体1衣服改成黑色
猫再小一点
场景更像黄昏
镜头再低一些
删掉背景里的树
```

系统行为：

```text
将用户反馈解析为 ReviewPatch
判断影响范围
决定局部重生成还是整体重生成
生成新 concept_version
```

前端展示：

```text
修改前/修改后对比
当前 patch 摘要
可确认按钮
```

### 5.5 主体 3D 资产生成阶段

系统行为：

```text
对每个 subject_concept_image 调用 Hunyuan3D
生成 GLB / OBJ / mesh / texture
保存 Asset3DRecord
执行系统质量检查
```

前端展示：

```text
主体生成进度
每个主体状态
成功/失败/重试
```

默认不要求用户逐个确认 3D asset。

仅当出现以下情况时展示给用户：

```text
资产质量不确定
资产明显失真
多次重试失败
系统无法判断是否可接受
用户主动点击查看
```

### 5.6 场景生成阶段

系统行为：

```text
调用 SceneGenerationService
生成场景级 3D 输出
调用 SceneAssetAdapter 转换或包装为 Blender 可消费结果
```

前端展示：

```text
场景生成中
输出类型
适配进度
是否可进入 Blender 装配
```

注意：场景输出可能是 mesh、3DGS、point cloud、depth maps、camera parameters 或 scene package。前端不需要直接理解这些底层格式，只展示“场景资产已生成/适配中/适配失败”。

### 5.7 Blender 装配阶段

系统行为：

```text
导入主体资产
导入或适配场景资产
根据 SceneSpec 和空间关系进行摆放
根据 LLM/MLLM 估计语义尺度与美观布局
设置相机
设置灯光
导出实时 3D 预览快照，并按需渲染 preview
```

前端展示：

```text
Blender 装配进度
当前操作说明
Web 端实时 3D 场景
Blender 高质量 preview render
```

### 5.8 Blender 预览审查阶段

用户反馈示例：

```text
把主体1往左一点
镜头拉近一些
灯光更暖
删掉桌子
重做猫
增加一盏路灯
```

系统行为：

```text
解析反馈
判断是纯 Blender 修改还是需要回到 2D/3D
执行 BlenderDomainTools
重新导出实时 3D 预览快照，并按需渲染 preview
生成新 blend_version
```

前端展示：

```text
修改后的 Web 端实时 3D 场景
按需更新的 Blender preview
操作记录
版本号
确认交付按钮
```

### 5.9 交付阶段

系统行为：

```text
保存最终 .blend
导出资产包
生成 metadata JSON
生成最终 preview
```

交付物：

```text
.blend
preview renders
subject GLB assets
scene assets
textures
metadata JSON
操作日志摘要
```

---

## 6. 同一窗口继续修改与新聊天

### 6.1 继续修改

用户可以在同一窗口继续发消息。

系统必须根据当前 `phase` 判断用户意图。例如：

```text
用户说“可以了”
```

在不同阶段含义不同：

```text
CONCEPT_REVIEW：确认 2D 概念，进入 3D 生成
BLENDER_PREVIEW：确认 Blender 场景，进入交付
DELIVERY：表示交付完成或准备新项目
```

### 6.2 开始新聊天 / 新项目

前端应提供：

```text
新建项目
复制当前项目为新项目
从当前版本 fork
打开历史项目
```

V1 最小要求：

```text
新建项目
打开历史项目
继续当前项目
```

`fork` 可以作为 V1.1 或 V2 能力。

---

## 7. 前端事件与状态展示协议

后端应向前端推送结构化事件。V1 推荐使用 WebSocket 或 Server-Sent Events。

### 7.1 WorkflowEvent

```json
{
  "event_id": "evt_001",
  "project_id": "project_001",
  "thread_id": "thread_001",
  "event_type": "phase_changed",
  "phase": "CONCEPT_GENERATION",
  "node": "ConceptImageExecutor",
  "message": "正在生成整体预览图和主体概念图",
  "progress": {
    "current": 2,
    "total": 5,
    "label": "生成主体概念图"
  },
  "artifacts": [],
  "available_actions": [],
  "created_at": "2026-06-27T10:00:00-07:00"
}
```

### 7.2 常见事件类型

```text
project_created
image_uploaded
binding_required
scene_spec_drafted
phase_changed
node_started
node_completed
artifact_created
artifact_updated
concept_ready
user_action_required
tool_call_started
tool_call_completed
tool_call_failed
asset_generation_started
asset_generation_completed
viewer_scene_ready
blender_render_ready
error
retrying
delivery_ready
```

### 7.3 可用操作按钮

前端按钮不应该硬编码，而应由后端根据阶段返回：

```json
{
  "available_actions": [
    {
      "action_id": "approve_concept",
      "label": "确认 2D 方案",
      "style": "primary"
    },
    {
      "action_id": "request_concept_revision",
      "label": "继续修改",
      "style": "secondary"
    }
  ]
}
```

---

## 8. API 概览

V1 前端至少需要以下 API。

```text
POST /projects
GET  /projects/{project_id}
POST /projects/{project_id}/messages
POST /projects/{project_id}/uploads
GET  /projects/{project_id}/events
GET  /projects/{project_id}/artifacts
POST /projects/{project_id}/actions/{action_id}
GET  /projects/{project_id}/versions
GET  /projects/{project_id}/delivery
GET  /projects/{project_id}/viewer-scene
POST /projects/{project_id}/viewer-actions
```

其中：

```text
/messages 用于自然语言输入
/uploads 用于图片上传
/events 用于前端状态流
/actions 用于确认、重生、导出等显式动作
/viewer-scene 用于获取前端实时 3D 场景快照和 scene_state
/viewer-actions 用于未来接收前端选择、聚焦、拖拽等交互事件
```

---

## 9. V1 非目标

V1 前端不要求：

```text
专业 DCC 级 Web 3D 编辑器
Blender 视口实时流
多人协同编辑
复杂 timeline 动画编辑器
完整节点式材质编辑器
前端直接编辑骨骼/动画
```

V1 必须提供 Web 端实时 3D 查看能力，但不要求它达到 Blender/Unity 级编辑器能力。V1 只要求：

```text
orbit
zoom
pan
对象选择/高亮
状态展示
场景快照刷新
```

Blender render preview image 是高质量确认手段，不是唯一预览手段。

---

## 10. 验收标准

DOC-002 对应的产品验收标准：

```text
1. 用户可以创建项目并上传多张图片。
2. 前端能稳定显示 image_id。
3. 用户可以在文本中绑定图片用途。
4. 前端能展示 Agent 当前阶段、当前节点和进度说明。
5. 前端能展示 2D final preview、subject concept images、scene concept images。
6. 用户可以确认或修改 2D 概念。
7. 前端能展示主体 3D 和场景生成进度。
8. 前端能通过实时 3D Viewer 展示当前场景，并支持 orbit/zoom/pan。
9. 前端能展示按需生成的 Blender preview render。
10. 用户可以在同一窗口继续提出 Blender 修改。
11. 用户可以导出最终交付包。
12. 用户可以开始新项目或继续当前项目。
```
