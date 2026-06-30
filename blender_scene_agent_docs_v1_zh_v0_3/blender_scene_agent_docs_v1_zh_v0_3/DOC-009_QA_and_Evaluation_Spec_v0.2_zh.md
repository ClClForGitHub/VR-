# DOC-009：质量评估与验收规范

**文档编号：** DOC-009  
**文档名称：** 质量评估与验收规范  
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

本文档定义 V1 的质量检查、自动评估、人工验收和回归测试标准。它回答：

```text
2D 概念图怎样算合格
主体 3D 资产怎样算合格
场景 3D 资产怎样算可用
Blender 装配怎样算可用
前端交互怎样算可用
哪些失败需要自动返修
哪些失败需要交给用户确认
```

---

## 2. 质量门禁总览

V1 有以下质量门禁：

```text
QG-001 输入与参考图绑定检查
QG-002 SceneSpec 结构化质量检查
QG-003 2D 概念图质量检查
QG-004 主体 3D 资产质量检查
QG-005 场景 3D 资产可用性检查
QG-006 Blender 装配质量检查
QG-007 Web 端实时 3D 预览可用性检查
QG-008 Blender 高质量预览用户审查
QG-009 交付包完整性检查
QG-010 端到端回归测试
```

---

## 3. QG-001 输入与参考图绑定检查

### 3.1 检查目标

确认用户上传图片都被明确说明用途。

### 3.2 检查项

```text
图片 ID 是否存在
图片用途是否明确
subject_id 是否存在
是否存在冲突绑定
是否缺少必要参考图
```

### 3.3 失败处理

```text
阻塞工作流
向用户请求补充说明
不进入 SceneSpec 生成
```

---

## 4. QG-002 SceneSpec 结构化质量检查

### 4.1 检查目标

确认 `SceneSpec` 足够驱动后续图像生成、3D 生成和 Blender 装配。

### 4.2 检查项

```text
至少有一个主体
场景环境不为空
主体描述不为空
风格/光线/相机有默认值或明确值
空间关系可选但不能自相矛盾
参考图绑定有效
open_questions 为空才能进入概念图生成
```

### 4.3 自动修复

可以自动补默认值：

```text
默认相机：中景，轻微 3/4 角度
默认光线：柔和主光 + 环境光
默认风格：写实/半写实，跟随用户描述
```

---

## 5. QG-003 2D 概念图质量检查

### 5.1 检查对象

```text
final_preview_image
subject_concept_images
scene_concept_images
```

### 5.2 final_preview_image 检查项

```text
主体数量是否正确
主要主体是否可见
整体风格是否符合用户描述
光线是否符合要求
构图是否大体合理
空间关系是否大体符合 SceneSpec
参考图中的关键外观是否被体现
```

### 5.3 subject_concept_images 检查项

```text
单主体
主体完整
3/4 视图优先
轮廓清晰
无遮挡
背景干净
适合 img2 3D
与 SubjectSpec 外观一致
```

### 5.4 scene_concept_images 检查项

```text
场景环境清楚
光线和风格明确
没有过度拥挤的主体混杂
可作为 Hunyuan Mirror / Blender 装配参考
```

### 5.5 失败处理

```text
缺主体 → 重生 final preview 或相关主体图
主体图不适合 3D → 重生 subject_concept_image
风格跑偏 → 重生 final preview 和 scene concept
空间关系错 → 重生 final preview 或修改 SceneSpec
```

---

## 6. QG-004 主体 3D 资产质量检查

### 6.1 检查对象

```text
Hunyuan3D 输出的 GLB/OBJ/mesh/texture
Blender asset preview render
```

### 6.2 确定性检查

```text
文件存在
文件大小合理
可被 Blender 导入
mesh 非空
材质/贴图文件存在或可缺省
导入后对象可见
渲染 preview 成功
```

### 6.3 视觉检查

使用 MLLM 对比：

```text
subject_concept_image
asset_preview_render
SubjectSpec
```

检查：

```text
主体是否严重变形
关键部件是否缺失
外观颜色是否大体一致
纹理是否严重错位
比例是否极端异常
是否无法用于场景装配
```

### 6.4 判定状态

```text
succeeded：可继续
uncertain：系统不确定，必要时展示给用户
needs_regen：重跑 Hunyuan3D
distorted：回到主体图重生或改变输入图规范
failed：记录错误并停止该主体资产流程
```

### 6.5 用户确认策略

V1 默认不增加 3D asset 用户确认点。只有 `uncertain`、`distorted` 或多次失败时才展示给用户。

---

## 7. QG-005 场景 3D 资产可用性检查

### 7.1 检查对象

```text
Hunyuan Mirror / HY-World 原始输出
SceneAssetAdapter 输出
Blender import preview
```

### 7.2 检查项

```text
是否有可消费输出
输出类型是否被识别
是否能转换或导入 Blender
是否提供基础空间参考
是否能承载主体摆放
是否能渲染预览
```

### 7.3 判定状态

```text
usable：可用
usable_with_limitations：可用但有局限
adapter_failed：适配失败
regenerate_needed：需要重新生成场景
fallback_needed：使用 Blender primitives/background cards 兜底
```

### 7.4 兜底方案

如果场景 3D 输出不可用，V1 可兜底为：

```text
使用 scene_concept_image 做背景板
使用 Blender primitives 搭建地面/墙体/基本结构
使用主体/环境物件补充场景
```

---

## 8. QG-006 Blender 装配质量检查

### 8.1 检查对象

```text
BlenderSceneState
Blender preview render
对象列表
相机/灯光设置
```

### 8.2 检查项

```text
主要主体是否全部导入
主要主体是否可见
主体是否大致摆放在合理位置
主体之间空间关系是否大体符合 SceneSpec
相机是否能看见主要主体
光线是否不过暗不过曝
场景和主体是否严重比例不协调
是否有明显穿模或悬空
渲染是否成功
```

### 8.3 摆放标准

V1 不以物理精确尺寸作为硬标准。摆放目标是：

```text
语义合理
视觉美观
主体关系清楚
主次明确
可被用户继续修改
```

### 8.4 失败处理

```text
主体不可见 → 调整相机或对象位置
光线异常 → 重设 lighting
对象位置错 → 重新运行 PlacementSolver
导入失败 → 检查 asset 或 MCP
```

---


## 9. QG-007 Web 端实时 3D 预览可用性检查

### 9.1 检查对象

```text
viewer_scene.glb / viewer_scene.gltf
scene_state.json
前端 Web3DPreviewRuntime
对象映射表
```

### 9.2 检查项

```text
前端能加载当前场景快照
前端支持 orbit / zoom / pan
主要主体可见
主体可被点击选择或高亮
subject_id 与 viewer_object_id 映射正确
用户修改后能刷新场景快照
不需要每次查看都重新调用 Blender 渲染
```

### 9.3 失败处理

```text
viewer_scene 导出失败 → 回到 ScenePreviewExporter 重试
贴图路径错误 → 修复 ArtifactStore 公开路径或相对路径
对象映射错误 → 重新同步 BlenderSceneState
前端加载失败 → 回退展示 Blender preview render，同时标记 viewer 失败
```

## 10. QG-008 Blender 高质量预览用户审查

### 10.1 用户确认点

V1 的第二个主要用户确认点是“Web 端实时 3D 预览 + 按需 Blender 高质量预览”。用户日常查看以实时 3D Viewer 为主，Blender 渲染图用于关键视觉确认。

用户可以：

```text
确认交付
修改位置
修改相机
修改灯光
重做主体
新增主体
删除主体
修改简单材质
```

### 10.2 用户反馈路由

```text
位置/相机/灯光 → Blender edit
主体不像 → subject concept / subject asset regen
场景不像 → scene concept / scene asset regen
全局不对 → 回到 2D concept 或 SceneSpec
```

---

## 11. QG-009 交付包完整性检查

交付前检查：

```text
.blend 文件存在
最终 preview render 存在
viewer_scene.glb / viewer_scene.gltf 存在
scene_state.json 存在
主体资产存在
场景资产或兜底场景存在
贴图文件存在或已内嵌
metadata.json 存在
version_manifest.json 存在
```

交付包必须能被下载并打开。

---

## 12. QG-010 端到端回归测试

### 11.1 最小测试集

```text
1. 单主体 + 简单场景
2. 两个主体 + 明确空间关系
3. 主体带参考图
4. 场景带参考图
5. 用户修改主体外观
6. 用户修改 Blender 位置
7. 用户重做某个主体
8. 用户新增主体
9. 场景生成失败兜底
10. Blender MCP 失败重试
```

### 11.2 每个测试记录

```text
输入文本
上传图片
期望 SceneSpec
期望产物类型
关键工具调用
实际输出
失败点
修复建议
```

---

## 13. 自动评估与人工评估

### 12.1 自动评估

包括：

```text
JSON schema 校验
artifact 文件检查
Blender 导入检查
渲染成功检查
MCP 工具调用结果检查
```

### 12.2 MLLM 评估

用于：

```text
2D 图是否符合描述
主体 3D 预览是否明显失真
Blender preview 是否大体符合场景
```

### 12.3 人工评估

用于 V1 早期：

```text
主观美观度
场景是否符合用户意图
生成是否可接受
失败是否可解释
```

---

## 14. 评分建议

每个阶段可以采用 0 到 5 分：

```text
5：完全符合，可以继续
4：轻微问题，但不阻塞
3：可用但需要用户确认
2：明显问题，建议自动返修
1：严重失败
0：工具或流程失败
```

V1 推进规则：

```text
分数 >= 4：自动继续
分数 = 3：继续但标记 uncertain，必要时展示给用户
分数 <= 2：自动返修
```

---

## 15. Release 验收标准

V1 发布前必须满足：

```text
1. 10 条端到端测试中至少 7 条完整跑通。
2. 所有核心 JSON 输出可被 schema 校验。
3. 至少一种 Blender MCP 能跑通导入、摆放、渲染、保存。
4. Hunyuan3D 主体通道能生成可导入 Blender 的资产。
5. Hunyuan Mirror / HY-World 场景通道至少能输出一种可被 SceneAssetAdapter 消费的表示。
6. 前端能展示当前阶段、产物、Web 端实时 3D 场景和按需 Blender preview。
7. 交付包可下载并包含必要文件。
8. V1 测试中不包含角色骨骼动画、自动上骨架或动作重定向验收。
```

---

## 16. 后续增强

V2 可增加：

```text
更细粒度材质评估
骨骼/动画 QA（独立动画管线后再加入）
自动资产库替换
更复杂场景重建质量指标
更大规模回归测试集
```
