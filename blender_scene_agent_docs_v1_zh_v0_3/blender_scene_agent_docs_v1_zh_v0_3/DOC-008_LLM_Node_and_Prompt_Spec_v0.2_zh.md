# DOC-008：LLM 节点与提示词规范

**文档编号：** DOC-008  
**文档名称：** LLM 节点与提示词规范  
**版本：** v0.2  
**状态：** V1 工程草案  
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

本文档定义 V1 中所有 LLM/MLLM 节点的职责、输入、输出、提示词策略和失败兜底。它回答：

```text
哪些节点需要 LLM
哪些节点需要 MLLM
每个节点输入什么上下文
输出什么 JSON
如何避免自然语言结果进入状态
如何让 LLM 只做理解和规划，不直接执行工具
```

---

## 2. 总体原则

### 2.1 结构化输出优先

所有关键 LLM 节点必须输出 JSON，并通过 Pydantic 校验。

不允许关键节点只输出自由文本。

### 2.2 LLM 不是真实状态源

LLM 输出是候选解释或候选计划。真实状态由：

```text
AgentProjectState
SceneSpec
ArtifactRecord
ToolCallRecord
BlenderSceneState
```

保存。

### 2.3 每个节点只看必要上下文

不要把全部历史、全部图片、全部工具一次性塞给 LLM。

`ContextAssembler` 应按节点构造最小上下文。

### 2.4 工具执行由代码完成

LLM 可以输出：

```text
想调用什么 domain tool
参数建议是什么
为什么需要调用
```

但真正调用工具由：

```text
ToolExecutor
BlenderDomainTools
MCPClientManager
```

完成。

---

## 3. LLM/MLLM 节点清单

V1 需要以下节点：

```text
IntentRouter
ReferenceBindingValidator
SceneInterpreter
SceneSpecCompiler
ConceptPromptPlanner
ConceptVisualQA
FeedbackPatchParser
RegenerationRouter
SubjectAssetQualityEvaluator
SceneAssetAdapterPlanner
BlenderAssemblyPlanner
ViewerSceneSummaryBuilder
BlenderEditRouter
BlenderPreviewQA
UserResponseGenerator
```

---

## 4. IntentRouter / 意图路由器

### 4.1 职责

根据当前 phase 和用户输入判断意图：

```text
新建场景
2D 反馈
2D 确认
Blender 修改
Blender 确认
重做主体
新增主体
删除主体
导出
新建聊天/项目
```

### 4.2 输入

```text
current_phase
latest_user_message
available_artifacts_summary
current_project_summary
```

### 4.3 输出

```python
class IntentRouterOutput(BaseModel):
    intent: UserIntent
    confidence: float
    target_phase: WorkflowPhase | None
    target_subject_ids: list[str] = []
    requires_clarification: bool = False
    clarification_question: str | None = None
```

### 4.4 提示词要点

```text
你必须结合 current_phase 判断用户意图。
同一句“可以了”在 CONCEPT_REVIEW 表示确认 2D，在 BLENDER_PREVIEW 表示确认 Blender 结果。
如果用户说法不明确，输出 requires_clarification=true。
```

---

## 5. ReferenceBindingValidator / 参考图绑定校验器

### 5.1 职责

校验用户是否在文字中明确说明图片用途。

### 5.2 输入

```text
uploaded_images
user_text
existing_subjects(optional)
```

### 5.3 输出

```python
class ReferenceBindingValidatorOutput(BaseModel):
    bindings: list[ReferenceBinding]
    missing_bindings: list[str]
    invalid_references: list[str]
    requires_user_fix: bool
    message_to_user: str | None
```

### 5.4 规则

V1 不默认自动猜图像用途。LLM 可以辅助识别用户文本中的绑定声明，但不能把不明确图片强行绑定到主体。

---

## 6. SceneInterpreter / 场景理解器

### 6.1 职责

从用户描述中提取场景核心信息。

包括：

```text
主体
场景
空间关系
光线
风格
镜头
材质
参考图用途
约束
开放问题
```

### 6.2 输入

```text
latest_user_message
validated_reference_bindings
image_descriptions(optional from MLLM)
conversation_summary
```

### 6.3 输出

```python
class SceneInterpreterOutput(BaseModel):
    title: str
    user_goal: str
    subjects: list[SubjectSpec]
    environment: EnvironmentSpec
    style: StyleSpec
    lighting: LightingSpec
    camera: CameraSpec
    spatial_relations: list[SpatialRelation]
    open_questions: list[str]
```

### 6.4 提示词要点

```text
将用户描述拆成可执行的场景规格。
不要发挥用户没有要求的关键主体。
空间关系必须尽量结构化。
如果图片绑定不明确，不要猜，写入 open_questions。
```

---

## 7. SceneSpecCompiler / 场景规格编译器

### 7.1 职责

把 `SceneInterpreterOutput`、参考图绑定和已有状态合并成正式 `SceneSpec`。

### 7.2 实现方式

主要由代码完成，LLM 只在需要补全语义字段时参与。

### 7.3 输出

```text
SceneSpec
```

---

## 8. ConceptPromptPlanner / 概念图提示规划器

### 8.1 职责

生成三类图像 prompt：

```text
final_preview_prompt
subject_concept_prompts
scene_concept_prompts
```

### 8.2 输入

```text
SceneSpec
ReferenceBinding
ReviewPatch(optional)
previous_concept_summary(optional)
```

### 8.3 输出

```python
class ConceptPromptPlannerOutput(BaseModel):
    final_preview_prompt: str
    subject_prompts: dict[str, str]
    scene_prompts: list[str]
    negative_prompt: str | None = None
    image_reference_usage: dict[str, list[str]] = {}
```

### 8.4 主体图提示原则

```text
单主体
完整轮廓
3/4 视图
居中
无遮挡
背景干净
光照均匀
适合 img2 3D
```

---

## 9. ConceptVisualQA / 概念图视觉质检器

### 9.1 职责

用 MLLM 检查 2D 概念图是否符合 SceneSpec。

### 9.2 输入

```text
SceneSpec
final_preview_image
subject_concept_images
scene_concept_images
```

### 9.3 输出

```python
class ConceptVisualQAOutput(BaseModel):
    passed: bool
    score: float
    issues: list[str]
    missing_subjects: list[str]
    wrong_relations: list[str]
    suggested_regeneration_targets: list[str]
```

### 9.4 检查项

```text
主体数量是否正确
主体外观是否合理
参考图是否被遵守
空间关系是否大体正确
风格/光线是否一致
主体图是否适合 Hunyuan3D
```

---

## 10. FeedbackPatchParser / 反馈补丁解析器

### 10.1 职责

把用户反馈转成结构化 patch。

### 10.2 输入

```text
current_phase
user_feedback
SceneSpec
ConceptBundle or BlenderSceneState
artifact_summary
```

### 10.3 输出

```python
class FeedbackPatchParserOutput(BaseModel):
    patches: list[ReviewPatch]
    affected_layers: list[Literal["scene_spec", "concept", "subject_asset", "scene_asset", "blender"]]
    requires_clarification: bool = False
    clarification_question: str | None = None
```

### 10.4 示例

用户：

```text
把猫放到女孩脚边，镜头再近一点。
```

输出：

```json
{
  "patches": [
    {
      "target_type": "subject",
      "target_id": "subject_cat",
      "change_type": "placement_change",
      "instruction": "放到女孩脚边"
    },
    {
      "target_type": "camera",
      "target_id": "main_camera",
      "change_type": "camera_change",
      "instruction": "镜头再近一点"
    }
  ],
  "affected_layers": ["blender"]
}
```

---

## 11. RegenerationRouter / 重生成路由器

### 11.1 职责

判断反馈需要回到哪里。

### 11.2 输出

```python
class RegenerationRouterOutput(BaseModel):
    route: Literal[
        "regenerate_final_preview",
        "regenerate_subject_concept",
        "regenerate_scene_concept",
        "regenerate_subject_asset",
        "regenerate_scene_asset",
        "blender_edit_only",
        "full_replan"
    ]
    target_subject_ids: list[str] = []
    reason: str
```

### 11.3 规则优先级

```text
位置、相机、灯光 → blender_edit_only
主体外观不像 → regenerate_subject_concept → regenerate_subject_asset
场景环境不像 → regenerate_scene_concept → regenerate_scene_asset
全局风格错 → regenerate_final_preview / full_replan
```

---

## 12. SubjectAssetQualityEvaluator / 主体资产质检器

### 12.1 职责

检查 Hunyuan3D 生成资产是否可用。

### 12.2 输入

```text
SubjectSpec
subject_concept_image
asset_preview_render
Blender import report
```

### 12.3 输出

```python
class SubjectAssetQualityEvaluatorOutput(BaseModel):
    status: Literal["succeeded", "distorted", "needs_regen", "uncertain"]
    score: float
    issues: list[str]
    recommended_action: Literal["accept", "rerun_hunyuan", "regenerate_subject_image", "ask_user"]
```

---

## 13. SceneAssetAdapterPlanner / 场景资产适配规划器

### 13.1 职责

根据 Hunyuan Mirror / HY-World 的实际输出，决定如何适配到 Blender。

### 13.2 输出

```python
class SceneAssetAdapterPlannerOutput(BaseModel):
    import_mode: Literal["mesh", "point_cloud", "gaussian_proxy", "background_cards", "proxy_geometry"]
    adapter_steps: list[str]
    limitations: list[str]
    needs_manual_fallback: bool = False
```

---

## 14. BlenderAssemblyPlanner
ViewerSceneSummaryBuilder / Blender 装配规划器

### 14.1 职责

根据 `SceneSpec`、主体资产、场景资产和空间关系生成 Blender 装配计划。

### 14.2 输入

```text
SceneSpec
Asset3DRecord list
Scene3DRecord
BlenderImportableSceneAsset
current BlenderSceneState(optional)
```

### 14.3 输出

```python
class BlenderAssemblyPlanner
ViewerSceneSummaryBuilderOutput(BaseModel):
    operations: list[BlenderOperation]
    scale_estimates: list[ScaleEstimate]
    placement_notes: list[str]
    camera_plan: dict
    lighting_plan: dict
```

### 14.4 摆放原则

V1 不要求严格物理真实比例。目标是：

```text
视觉美观
主体关系清楚
符合用户语义描述
主角突出
镜头能看清重点
```

尺度由 LLM/MLLM 根据语义估计，并通过 Blender preview 迭代修正。

---

## 15. BlenderEditRouter / Blender 编辑路由器

### 15.1 职责

判断用户对 Blender preview 的反馈属于哪一层：

```text
纯 Blender 操作
主体重做
场景重做
2D 概念重做
全局重规划
```

### 15.2 输出

```python
class BlenderEditRouterOutput(BaseModel):
    edit_type: Literal[
        "transform_edit",
        "camera_edit",
        "lighting_edit",
        "material_edit",
        "add_subject",
        "remove_subject",
        "replace_subject",
        "regenerate_subject",
        "regenerate_scene",
        "replan"
    ]
    target_subject_ids: list[str] = []
    domain_tool_calls: list[dict] = []
```

---

## 16. BlenderPreviewQA / Blender 预览质检器

### 16.1 职责

检查 Web 端实时 3D 场景快照和按需生成的 Blender 渲染预览是否大体符合 SceneSpec。

### 16.2 检查项

```text
主体是否可见
主体数量是否正确
大致空间关系是否正确
相机是否看见关键主体
光线是否过暗或过曝
场景和主体是否严重不协调
```

### 16.3 输出

```python
class BlenderPreviewQAOutput(BaseModel):
    passed: bool
    score: float
    issues: list[str]
    suggested_edits: list[str]
```

---

## 17. UserResponseGenerator / 用户响应生成器

### 17.1 职责

生成给用户看的简短说明。

例如：

```text
已生成 2D 概念图，请确认整体构图和主体是否符合要求。
主体 2 的 3D 模型质量不稳定，我会尝试重新生成一版。
Blender 场景已完成初步装配，你可以继续修改主体位置、相机或灯光。
```

### 17.2 约束

不能编造不存在的工具结果。必须基于当前状态和 artifact。

---

## 18. 通用提示词模板结构

每个 LLM 节点建议使用统一结构：

```text
你是 {节点名称}。
当前任务：{节点职责}。
当前阶段：{phase}。
输入上下文：{context_json}。
你必须输出符合以下 JSON Schema 的结果：{schema}。
禁止输出额外自然语言。
如果信息不足，设置 requires_clarification=true。
```

---

## 19. 失败兜底

### 19.1 JSON 解析失败

```text
要求模型重试一次
再次失败则进入 WorkflowError
```

### 19.2 输出字段缺失

```text
Pydantic 校验失败
自动修复可选字段
关键字段缺失则重试
```

### 19.3 视觉判断不确定

```text
标记 uncertain
交给规则或用户确认
不默认推进高风险阶段
```

---

## 20. 验收标准

```text
1. 每个 LLM 节点都有明确输入和输出 schema。
2. 关键节点输出都能被 Pydantic 校验。
3. 用户反馈能被解析为 ReviewPatch。
4. Blender 修改能被路由到正确层级。
5. LLM 不直接执行 raw MCP tool。
6. LLM 只看到当前阶段允许的 Domain Tools。
```


---

## 18. 动画与角色动作相关 Prompt 暂不进入 V1

V1 不实现用户自然语言驱动的角色骨骼动作。LLM 节点不应把“让角色挥手、跑步、跳舞”等请求错误地路由为普通 Blender MCP 操作。

如果用户提出角色动作请求，V1 应输出边界说明或记录为后续需求：

```json
{
  "intent": "ANIMATION_REQUEST",
  "supported_in_v1": false,
  "reason": "当前主体资产默认没有骨架、蒙皮权重和动画 clip。角色动作需要自动上骨架、动作库和重定向管线。",
  "suggested_response": "当前版本先支持静态场景和镜头/摆放调整，角色骨骼动作会作为后续动画管线处理。"
}
```

V1 可接受的“动作类”请求只限于静态编辑语义，例如：

```text
把角色放到桌子旁边
让镜头靠近角色
把猫移到女孩脚边
```

这些请求本质是摆放和相机调整，不是骨骼动画。
