# DOC-006：工具与 MCP 接入规范

**文档编号：** DOC-006  
**文档名称：** 工具与 MCP 接入规范  
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

本文档定义 V1 中所有外部能力的接入方式，包括图像生成、Hunyuan3D 主体生成、Hunyuan Mirror / HY-World 场景生成、Blender MCP、内部工具封装、工具能力发现、阶段性工具白名单和 LLM 可见工具管理。

核心原则：

```text
LLM 不直接面对所有 raw tools。
LLM 只看到当前阶段允许的 domain tools。
原始 MCP 工具通过 wrapper / adapter 封装。
工具执行由确定性代码负责。
LLM 负责生成结构化工具意图和参数。
```

---

## 2. 工具分层

V1 工具分为 4 层。

```text
LLM-visible Domain Tools
  ↓
Domain Tool Implementations
  ↓
Adapters / MCP Clients / API Clients
  ↓
Raw External Tools / Services
```

### 2.1 LLM-visible Domain Tools

模型可见的业务工具，例如：

```text
generate_concept_images
build_subject_asset
build_scene_asset
import_asset_to_blender
place_subject
update_camera
update_lighting
export_viewer_scene
render_blender_preview
replace_subject
export_delivery_package
```

### 2.2 Domain Tool Implementations

由我们自己写的业务工具实现。它们负责：

```text
读取 AgentProjectState
校验参数
查询 ArtifactStore
调用 MCP/API adapter
更新状态
记录 ToolCallLog
返回结构化结果
```

### 2.3 Adapters / MCP Clients / API Clients

包括：

```text
ImageGenerationClient
Hunyuan3DClient
SceneGenerationClient
SceneAssetAdapter
BlenderMCPAdapter
ScenePreviewExporter
ViewerSyncService
MCPClientManager
```

### 2.4 Raw External Tools / Services

包括：

```text
GPT Image / 本地图像生成服务 / ComfyUI
Hunyuan3D-2.1 本地 API
Hunyuan Mirror / HY-World 本地服务
Blender MCP server
Blender Python API
```

---

## 3. MCP 接入原则

### 3.1 Host / Client / Server 划分

在本项目中：

```text
Host:
  我们的 Agent Backend / LangGraph Runtime

MCP Client:
  MCPClientManager / BlenderMCPAdapter

MCP Server:
  现成 Blender MCP server
  后续可能包括自研 MCP server
```

### 3.2 已有基础设施优先复用

V1 落地时不要默认重新实现 MCP client、Blender 控制、GLB viewer、服务管理脚本或资产检查脚本。实现前必须先检查当前工作区已有能力：

```text
Codex MCP 配置中的 blender_lab server
Blender 5.1.2 + 127.0.0.1:9876 Blender Lab MCP bridge
/home/team/zouzhiyuan/codex-self-mcp 子 agent MCP 通道
scripts/ 下的 start/status/stop 脚本
tools/ 下的 Blender/GLB helper
web/ 下的 viewer runtime
Hunyuan3D-2.1 / HY-World-2.0 本地服务与验证输出
```

只有在已有能力缺失、契约不匹配、稳定性不足或封装边界不合适时，才新增实现。新增实现必须记录：

```text
复用了哪些已有组件
替换了哪些已有组件
为什么不能直接复用
新增组件与 Domain Tool / MCPClientManager 的边界
```

代码落地时，Domain Tool 和 MCP adapter 的新增工作必须先经过 `agent_runtime.infra_inventory` 的只读盘点。若已有 `scripts/`、`tools/`、`web/`、`blender_lab` 或 `codex-self-mcp` 通道能够满足需求，优先通过 `agent_runtime.script_adapters`、`agent_runtime.domain_tools` 或后续 MCP adapter 做薄封装，不另起平行实现。

### 3.3 MCP 工具发现流程

启动时：

```text
1. 读取 mcp_servers.yaml
2. 连接 Blender MCP server
3. 调用 tools/list
4. 获取 raw tool catalog
5. 写入 ToolCatalog
6. 根据 CapabilityMapper 生成 domain tool 映射
7. 根据 phase 决定暴露哪些工具给 LLM
```

### 3.4 不直接暴露 raw tools

禁止 V1 直接把所有 raw Blender MCP tools 暴露给 LLM。

原因：

```text
工具太底层
参数过细
容易错误操作 Blender
不方便状态同步
不方便做版本管理
不方便替换 MCP 实现
```

必须通过：

```text
BlenderDomainTools
```

---

## 4. MCPClientManager

职责：

```text
管理多个 MCP server 连接
缓存 tools/list 结果
检测 server 健康状态
提供统一 call_tool 接口
记录 raw tool 调用日志
处理 timeout / retry / reconnect
```

接口草案：

```python
class MCPClientManager:
    async def connect_all(self) -> None: ...
    async def list_tools(self, server_name: str) -> list[RawToolSpec]: ...
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> dict: ...
    async def health_check(self, server_name: str) -> MCPHealthStatus: ...
```

配置示例：

```yaml
mcp_servers:
  blender_primary:
    transport: stdio
    command: /path/to/blender-mcp-server
    enabled: true
    role: primary

  blender_fallback:
    transport: stdio
    command: /path/to/another-blender-mcp-server
    enabled: false
    role: fallback
```

---

## 5. ToolCatalog

`ToolCatalog` 保存 raw tools 和 domain tools。

```python
class RawToolSpec(BaseModel):
    server_name: str
    tool_name: str
    description: str
    input_schema: dict
    output_schema: dict | None = None
    risk_level: Literal["low", "medium", "high"] = "medium"
    enabled: bool = True
```

```python
class DomainToolSpec(BaseModel):
    domain_tool_name: str
    description: str
    input_schema: dict
    output_schema: dict
    implementation: str
    allowed_phases: list[WorkflowPhase]
    underlying_raw_tools: list[str]
    llm_visible: bool
    risk_level: Literal["low", "medium", "high"]
```

---

## 6. BlenderDomainTools

### 6.1 设计目标

`BlenderDomainTools` 是业务层稳定接口。即使底层换 Blender MCP 实现，上层工作流和 LLM 节点不应改变。

### 6.2 V1 必需 domain tools

```text
import_subject_asset
import_scene_asset
place_subject
move_subject
rotate_subject
scale_subject
delete_subject
replace_subject_asset
create_basic_environment
setup_camera
update_camera
setup_lighting
update_lighting
set_simple_material
export_viewer_scene
render_preview
save_blend_file
export_scene_package
get_blender_scene_summary
```

### 6.3 V1 可选 domain tools

```text
create_background_plane
create_ground_plane
add_area_light
add_sun_light
set_world_background
set_render_resolution
set_render_engine
apply_auto_layout_refinement
```

### 6.4 动画 domain tools 暂不进入 V1

V1 不做角色骨骼动画，也不承诺 Hunyuan3D 主体资产可自动上骨架。以下工具只作为未来独立动画管线的预留方向，不进入 V1 实施范围：

```text
inspect_glb_rig_info
auto_rig_character
apply_animation_clip
retarget_animation
add_object_keyframes
add_camera_keyframes
render_animation_preview
```

说明：MCP 可以作为调用 Blender 或外部动画工具的通道，但自动上骨架、蒙皮权重、动作 clip、动作重定向需要独立服务管线，不属于 Blender MCP 本身的直接能力。

---

## 7. Domain Tool 详细定义

### 7.1 import_subject_asset

职责：把主体 GLB/OBJ 导入 Blender，并建立 `subject_id → blender_object_id` 映射。

输入：

```json
{
  "subject_id": "subject_001",
  "asset_version_id": "asset_subject_001_v001",
  "object_name": "HeroGirl"
}
```

输出：

```json
{
  "ok": true,
  "blender_object_id": "obj_hero_girl_001",
  "blender_name": "HeroGirl",
  "created_objects": ["HeroGirl", "HeroGirl_mesh"]
}
```

底层可能调用：

```text
blender_python_exec
blender_scene_list_objects
blender_object_get_transform
```

### 7.2 place_subject

职责：根据语义关系、美观布局和 LLM/MLLM 估计，把主体放到合适位置。

输入：

```json
{
  "subject_id": "subject_002",
  "placement_intent": "放在主体1右侧，靠近桌子",
  "target_subject_id": "subject_001",
  "style_hint": "自然、平衡、画面中心偏右"
}
```

说明：V1 不做刚性尺寸归一化。不同主体与场景的尺度由 LLM/MLLM 结合语义、场景内容和预览效果估计，工具层只执行经过校验的 transform。

### 7.3 update_camera

输入：

```json
{
  "camera_change": "镜头拉近，略微降低视角，让主体1和主体2都在画面中心",
  "preserve_subjects": ["subject_001", "subject_002"]
}
```

输出：

```json
{
  "ok": true,
  "camera": {
    "location": [0, -6, 2.2],
    "rotation": [65, 0, 0],
    "focal_length": 45
  }
}
```

### 7.4 export_viewer_scene

职责：从当前 Blender 权威场景导出前端实时 3D Viewer 可加载的 GLB/glTF 快照，并生成 scene_state.json。

输入：

```json
{
  "source_blend_version_id": "blend_v003",
  "include_textures": true,
  "include_object_mapping": true
}
```

输出：

```json
{
  "ok": true,
  "viewer_scene_artifact_id": "viewer_scene_v003_glb",
  "viewer_state_artifact_id": "viewer_state_v003_json"
}
```

底层可能调用：

```text
blender_python_exec
Blender glTF/GLB export
blender_scene_list_objects
blender_object_get_transform
```

### 7.5 render_preview

职责：渲染当前 Blender 场景的高质量预览图，并保存 artifact。该工具不用于日常实时查看，日常实时查看由 `export_viewer_scene` 产物驱动。

输入：

```json
{
  "render_preset": "preview",
  "resolution": [1280, 720]
}
```

输出：

```json
{
  "ok": true,
  "preview_artifact_id": "blender_preview_v003"
}
```

---

## 8. 阶段性工具白名单

LLM 每次只看到当前阶段允许工具。

```python
TOOLS_BY_PHASE = {
    "SCENE_SPEC_DRAFT": [
        "compile_scene_spec",
        "bind_reference_images"
    ],
    "CONCEPT_GENERATION": [
        "generate_concept_images"
    ],
    "CONCEPT_REVIEW": [
        "parse_review_patch",
        "regenerate_concept_images",
        "approve_concept"
    ],
    "SUBJECT_ASSET_GENERATION": [
        "build_subject_asset",
        "check_subject_asset_quality"
    ],
    "SCENE_ASSET_GENERATION": [
        "build_scene_asset",
        "adapt_scene_asset"
    ],
    "BLENDER_ASSEMBLY_EXECUTION": [
        "import_subject_asset",
        "import_scene_asset",
        "place_subject",
        "setup_camera",
        "setup_lighting",
        "export_viewer_scene",
        "render_preview"
    ],
    "BLENDER_EDIT": [
        "move_subject",
        "rotate_subject",
        "scale_subject",
        "delete_subject",
        "replace_subject_asset",
        "update_camera",
        "update_lighting",
        "set_simple_material",
        "export_viewer_scene",
        "render_preview"
    ],
    "DELIVERY": [
        "save_blend_file",
        "export_scene_package"
    ]
}
```

---

## 9. LLM 如何知道 MCP 能力

LLM 不直接学习 MCP server 的全部能力，而是通过 `ContextAssembler` 获得当前阶段的 domain tool 摘要。

示例上下文：

```text
当前阶段：BLENDER_EDIT

当前可用操作：
1. move_subject：移动某个主体。
2. update_camera：调整相机位置、角度和焦距。
3. update_lighting：调整灯光风格。
4. replace_subject_asset：重做并替换某个主体。
5. export_viewer_scene：刷新前端实时 3D 场景快照。
6. render_preview：按需生成 Blender 高质量渲染预览图。

当前场景对象：
- subject_001：女孩，Blender 对象 HeroGirl
- subject_002：猫，Blender 对象 Cat
- subject_003：木桌，Blender 对象 WoodTable
```

模型输出的是结构化操作计划，而不是直接调用 raw MCP：

```json
{
  "operations": [
    {
      "tool": "move_subject",
      "arguments": {
        "subject_id": "subject_002",
        "placement_intent": "移动到女孩脚边，略靠右"
      }
    },
    {
      "tool": "update_camera",
      "arguments": {
        "camera_change": "镜头拉近，保持女孩和猫都清晰可见"
      }
    }
  ]
}
```

---

## 10. MCP 上下文管理

MCP 工具上下文不等于聊天上下文。

系统应维护三种上下文：

```text
ToolCatalogContext       当前连接的 MCP server 和 raw tools
DomainToolContext        当前阶段允许的 domain tools
SceneContext             当前 SceneSpec、BlenderSceneState 和 artifact 摘要
```

LLM 只看到：

```text
当前阶段
当前场景摘要
当前可操作对象
当前允许的 domain tools
必须输出的 JSON schema
```

LLM 不看到：

```text
全部 raw MCP tools
全部 Blender Python API
全部历史消息
图片 base64
GLB 二进制
viewer_scene 的大文件内容
.blend 文件内容
```

---

## 11. Blender MCP 能力矩阵

V1 可以并行测试多个现成 MCP server，但业务层必须统一。

| 能力 | V1 重要性 | Blender Lab MCP | ahujasid/blender-mcp | djeada/blender-mcp-server | 自研 wrapper 是否需要 |
|---|---:|---|---|---|---|
| 获取场景信息 | 必须 | 待实测 | 支持 | 支持 | 需要统一输出 |
| 列出对象 | 必须 | 待实测 | 支持 | 支持 | 需要统一输出 |
| 导入 GLB/OBJ | 必须 | 待实测 | 可通过 Python | 可通过 Python/导出工具组合 | 需要封装 |
| 移动物体 | 必须 | 待实测 | 支持 | 支持 | 需要封装 |
| 旋转物体 | 必须 | 待实测 | 支持 | 支持 | 需要封装 |
| 缩放物体 | 必须 | 待实测 | 支持 | 支持 | 需要封装 |
| 创建基础几何体 | 必须 | 待实测 | 支持 | 支持 | 需要封装 |
| 材质创建/赋值 | 必须 | 待实测 | 支持 | 支持 | 需要封装 |
| 贴图设置 | 可选 | 待实测 | 支持程度待测 | 支持程度待测 | 需要封装 |
| 相机设置 | 必须 | 待实测 | 可通过 Python | 可通过脚本 | 需要封装 |
| 灯光设置 | 必须 | 待实测 | 可通过 Python | 可通过脚本 | 需要封装 |
| 静态渲染 | 必须 | 待实测 | 支持 | 支持 | 需要封装 |
| 保存 .blend | 必须 | 待实测 | 可通过 Python | 可通过脚本 | 需要封装 |
| 导出 glTF/OBJ/FBX | 必须 | 待实测 | 部分支持/可通过 Python | 支持 | 需要封装 |
| 任意 Python 执行 | 内部高风险 | 待实测 | 支持 | 支持 | 只能内部使用 |
| 异步任务 | 可选 | 待实测 | 待实测 | 支持 | 可封装 |
| 关键帧动画 | 暂缓 | 待实测 | 可通过 Python | 有脚本支持 | 不进入 V1 |
| 动画渲染 | 暂缓 | 待实测 | 可通过 Python | 支持 | 不进入 V1 |
| 自动上骨架/rigging | 暂缓 | 不适用 | 需额外管线 | 需额外管线 | 不进入 V1 |

说明：该矩阵需要在技术 spike 后补实测结果。

---

## 12. 工具调用日志

每次工具调用必须记录。

```python
class ToolCallLog(BaseModel):
    tool_call_id: str
    project_id: str
    phase: WorkflowPhase
    domain_tool_name: str
    raw_tool_calls: list[dict]
    arguments: dict
    result_summary: dict | None
    status: Literal["started", "succeeded", "failed", "retried"]
    error: dict | None
    started_at: datetime
    ended_at: datetime | None
```

---

## 13. 错误处理

常见错误：

```text
MCP server 未连接
raw tool 不存在
raw tool schema 改变
Blender 未启动
Blender 场景状态不同步
导入资产失败
渲染失败
Hunyuan API 超时
SceneAssetAdapter 无法转换
```

处理策略：

```text
1. 记录 ToolCallLog。
2. 返回结构化错误。
3. 标记项目状态 last_error。
4. 可重试错误自动重试。
5. 不可重试错误进入 FAILED 或等待用户处理。
```

---

## 14. 验收标准

```text
1. 系统能连接至少一个 Blender MCP server。
2. 系统能获取 raw tool catalog。
3. 系统能把 raw tools 包装为 domain tools。
4. LLM 只看到当前阶段允许的 domain tools。
5. 系统能通过 domain tools 导入 GLB、移动对象、设置相机、设置灯光、导出前端实时 3D viewer 场景快照，并按需渲染 Blender preview。
6. 每次工具调用都有 ToolCallLog。
7. 替换 Blender MCP 实现时，上层工作流不需要修改。
8. 任意 Python 执行不直接暴露给 LLM。
```

---

## 15. 参考资料

```text
LangGraph persistence / interrupts：
https://docs.langchain.com/oss/python/langgraph/persistence
https://docs.langchain.com/oss/python/langgraph/interrupts

Hunyuan3D-2.1：
https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1

HunyuanWorld-Mirror：
https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

Blender MCP 候选：
https://www.blender.org/lab/mcp-server/
https://github.com/ahujasid/blender-mcp
https://github.com/djeada/blender-mcp-server
```
