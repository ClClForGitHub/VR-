# image23D Creator App v0.5.2 全流程修正规格

更新时间：2026-07-01  
状态：用于修正 `web/creator_app` 的前端产品流、布局、交互和数据契约。  
版本规则：前端版本继续沿用 `v0.x`；`round04b-live-concept-executor` 仅作为 GitHub 分支/后端计划名，不作为前端版本名。

---

## 0. 本轮核心判断

当前 v0.5 / round04b 的视觉方向可以保留，但产品流转、信息架构、组件比例、GLB 能力和多主体数据组织必须大改。

主要问题：

1. 把 `reveal`、`feedback-compare`、`asset-memory` 做成主流程页面，导致真实流程混乱。
2. 顶部/左侧导航重复，占用空间，导致主按钮和内容需要滚动才能看到。
3. 输入/绑定页没有严格表达“最多 5 主体 + 1 场景”的参考图规则。
4. 聊天输入过重，应该只有 `@` 和上传入口；`@` 插入引用，而不是固定 `@图片1` 按钮。
5. 概念生成中的百分比是体验进度，不应快速跳完；需要按平均耗时推进，后端完成后立即进入揭幕。
6. 概念审稿要支持“整体图 / 多主体图 / 场景图”混选，不是单一概念卡选择。
7. 反馈应是面向“整体图 / 主体 X / 场景图”的反馈抽屉，并支持重新上传参考图。
8. 模型验收要按“主体实体 -> 模型版本”组织，选择左侧模型时中间 GLB viewer 必须切换。
9. 当前 GLB viewer 只是 poster 图，按钮是死的；必须接真实 `model-viewer`。
10. 自由组合和导演台可以保留，但要基于实体 ID 和资产版本，不要把主体、版本、截图混在一起。
11. 最终导演台的对象列表必须由后端 `scene_state.json` 提供；没有对象语义就不能假装可精确控制。

---

## 1. 参考图规则：最多 5 主体 + 1 场景

### 1.1 前端约束

默认规则：

```ts
const MAX_SUBJECT_REFERENCES = 5;
const MAX_SCENE_REFERENCES = 1;
const MAX_REFERENCE_SLOTS = MAX_SUBJECT_REFERENCES + MAX_SCENE_REFERENCES; // 6
```

注意：用户多次强调“5 主体 + 1 场景”，因此先按 6 个槽位设计。若后续确认“总数最多 5 张”，只改配置，不改 UI 架构。

### 1.2 不显示文件名

浏览器虽然能拿到上传文件名，但产品上不要依赖用户文件名。右侧参考图统一显示：

```text
主体 1
主体 2
主体 3
主体 4
主体 5
场景 1
```

可选副标题来自用户文本或后端解析：

```text
主体 1 · 机械灵兽
场景 1 · 古老遗迹
```

如果没有解析结果，只显示槽位名。

### 1.3 不再显示“用途”下拉

当前截图里的“用途：造型、比例、材质方向”要去掉。  
图片槽只需要绑定为：

```text
主体参考
场景参考
```

风格/光影/氛围由用户文字描述，不在图片槽里做“用途”选择。后续如果需要风格参考图，可以作为扩展槽，不进入当前 V1。

### 1.4 “重新绑定”改名

不要用“重新绑定”。改成：

```text
替换图片
移除
```

替换图片就是重新上传到当前槽位。绑定关系不需要用户反复配置。

### 1.5 右侧 Reference Tray

输入页右侧保留 Reference Tray，但结构改成：

```text
Reference Tray
  主体参考 0/5
    + 上传主体参考
    主体 1 card
    主体 2 card
  场景参考 0/1
    + 上传场景参考
    场景 1 card
```

每张卡显示：

```text
槽位：主体 1 / 场景 1
缩略图
状态：已上传 / 等待上传 / 替换中
操作：替换、移除
```

---

## 2. 聊天输入与 @ 引用

### 2.1 输入框只保留两个快捷按钮

输入框右侧只保留：

```text
@
上传
发送 / 开始生成
```

不要固定显示 `@图片1`。用户按 `@` 后，前端：

1. 在输入框插入 `@`；
2. 打开引用选择菜单；
3. 用户选择 `主体 1 / 主体 2 / 场景 1`；
4. 文本里插入 `@主体1` 或 `@场景1`。

### 2.2 数据提交

提交给后端时，不依赖文本里的人类字面名称，而是同时提交结构化绑定：

```json
{
  "message": "让 @主体1 在 @场景1 的遗迹里...",
  "reference_mentions": [
    {
      "mention": "@主体1",
      "entity_id": "subject_1",
      "slot_id": "subject_slot_1",
      "artifact_id": "artifact_xxx"
    },
    {
      "mention": "@场景1",
      "entity_id": "scene_1",
      "slot_id": "scene_slot_1",
      "artifact_id": "artifact_yyy"
    }
  ]
}
```

---

## 3. 布局重排：去掉重复顶部大导航

### 3.1 保留一个主流程导航

当前截图同时存在顶部 stepper 和上方横向大框，太占空间。  
v0.5.2 改为：

```text
顶部 Header：logo / 当前项目 / 资产记忆按钮 / 项目中心 / 用户
左侧流程导航：输入/绑定、概念选择、模型验收、自由组合、导演台、交付下载
主舞台：从顶部明显上移，首屏必须看到主按钮
右侧：当前阶段上下文面板，如 Reference Tray 或 Review Action
```

### 3.2 左侧主流程

左侧主流程只保留：

```text
1 输入/绑定
2 概念选择
3 模型验收
4 自由组合
5 导演台
6 交付下载
```

不要把以下内容作为左侧主流程：

```text
揭幕动画
反馈对比
资产记忆
生成中
```

它们分别是：

```text
揭幕动画 = overlay
反馈 = drawer/modal
资产记忆 = 右侧按钮 + 抽屉/完整页面
生成中 = background task dock
```

---

## 4. 后台生成状态与揭幕动画

### 4.1 生成中不是独立页面

用户点击“开始生成概念图”后：

1. 任务提交给后端；
2. 留在输入页或跳到项目任务面板；
3. 显示一个 `GenerationStatusDock`；
4. 用户可以继续修改草稿、查看资产记忆、切项目；
5. 后端返回完成后，自动弹出 `CinematicRevealOverlay`；
6. 动画结束或用户跳过后进入“概念选择”。

### 4.2 伪百分比规则

百分比不是后端真实进度，而是体验进度。按平均耗时推进：

```ts
function displayedProgress(elapsedMs, expectedMs, backendDone) {
  if (backendDone) return 100;
  const ratio = elapsedMs / expectedMs;
  if (ratio < 0.72) return Math.floor(ratio * 90);
  if (ratio < 1.0) return 90 + Math.floor((ratio - 0.72) / 0.28 * 5); // 90-95
  return Math.min(99, 95 + Math.floor(Math.log1p(ratio - 1) * 2)); // 95-99 slow crawl
}
```

### 4.3 阶段文案

概念生成阶段：

```text
解析自然语言需求
绑定参考图语义
生成 SceneSpec
渲染概念候选
写入创作记忆
准备揭幕动画
```

模型生成阶段：

```text
读取已选概念组合
提交主体模型生成
提交场景模型生成
等待 GLB 产出
模型质量检查
准备模型验收
```

Blender 组装阶段：

```text
读取主体/场景模型
生成组合方案
提交 Blender 组装
导出 viewer_scene.glb
生成 preview.png
同步 scene_state.json
```

---

## 5. 概念选择界面重做

### 5.1 概念图要放在前面

概念选择页首屏优先展示整体概念图。  
推荐结构：

```text
左侧：概念类别与实体选择
  整体图
  主体图：主体1 主体2 主体3 主体4 主体5
  场景图：场景1

中间：当前选择的大图预览
  当前类别 / 实体 / 版本
  图片查看控件：适应窗口、下载、全屏

下方：当前已选组合摘要
  整体图：V3
  主体1：V2
  主体2：V1
  场景1：V1

右侧：审稿动作
  提出修改意见
  查看已选组合
  接受组合，生成模型
```

### 5.2 多主体支持

主体图区域必须按主体实体组织：

```text
主体 1 · 机械灵兽
  概念图 v1
  概念图 v2
  概念图 v3

主体 2 · 重装机甲
  概念图 v1
  概念图 v2
```

UI：

- 上方横向实体按钮：`主体1`、`主体2`、`主体3`...
- 点哪个主体，中间展示对应主体的当前版本。
- 每个主体内部可切换版本。
- 场景图也使用类似结构，只是通常只有 `场景1`。

### 5.3 混合选择

用户可以混合选择：

```text
整体图：V3 当前方案
主体1：V2 机械灵兽概念
主体2：V1 重装机甲概念
场景1：V3 古老遗迹场景
```

提交给后端：

```json
{
  "approved_concept_selection": {
    "overall_concept_asset_id": "concept_overall_v3",
    "subject_concept_asset_ids": {
      "subject_1": "concept_subject_1_v2",
      "subject_2": "concept_subject_2_v1"
    },
    "scene_concept_asset_ids": {
      "scene_1": "concept_scene_1_v3"
    }
  }
}
```

### 5.4 去掉主流程里的“版本对比”

“打开版本对比”不是主操作。  
改为“查看已选组合”，打开一个确认弹窗，防止用户选错：

```text
已选组合确认
  整体图：V3 缩略图
  主体1：V2 缩略图
  主体2：V1 缩略图
  场景1：V3 缩略图
操作：
  返回修改
  确认生成模型
```

---

## 6. 概念反馈抽屉

### 6.1 反馈对象

反馈抽屉不是选择“光影/风格”等标签，而是先选反馈目标：

```text
整体图
主体1
主体2
主体3
主体4
主体5
场景1
```

每个目标有独立文本：

```text
主体1哪里不好？
主体2哪里不好？
场景图哪里不好？
整体图哪里不好？
```

光影、风格、构图、氛围这些由用户自然语言描述，不做强制标签。

### 6.2 支持重新上传参考图

反馈抽屉内必须有：

```text
上传新参考图
@
发送反馈并重生成
```

新上传图进入 Reference Tray，产生新引用，例如：

```text
@主体1-新参考
@场景1-新参考
```

提交给后端时关联反馈目标：

```json
{
  "action_type": "request_concept_changes",
  "feedback_targets": [
    {
      "target_type": "subject",
      "entity_id": "subject_1",
      "feedback_text": "主体1头部太小，机械感不够强",
      "new_reference_artifact_ids": ["artifact_new_ref_001"]
    },
    {
      "target_type": "scene",
      "entity_id": "scene_1",
      "feedback_text": "场景图希望更开阔，主光更强",
      "new_reference_artifact_ids": []
    }
  ]
}
```

---

## 7. 模型验收重做

### 7.1 生成中状态

模型生成也使用 `GenerationStatusDock`，不是静止等待页。  
后端每生成一个主体模型或场景模型，前端可以逐个更新卡片状态：

```text
主体1 模型 v1 生成中
主体2 模型 v1 已完成
场景1 模型 v1 生成中
```

### 7.2 左侧模型选择

左侧按实体组织：

```text
主体模型
  主体1 · 机械灵兽
    模型 v1
    模型 v2
  主体2 · 重装机甲
    模型 v1

场景模型
  场景1 · 古老遗迹
    模型 v1
    模型 v2
```

点选某个模型，中间 viewer 必须切换。

### 7.3 中间是真 GLB viewer

如果模型有 `.glb` URL：

```text
用 <model-viewer> 加载
支持旋转、缩放、平移视角、全屏
```

如果没有 GLB：

```text
显示 poster fallback
明确写：等待主体1 模型 v1 GLB 生成
按钮全部 disabled，不假装能旋转
```

### 7.4 概念图与模型对比改为弹窗

不要固定放在下方。  
中间 viewer 边上加按钮：

```text
概念对比
```

点击打开 modal：

```text
左：对应概念图
右：当前模型 viewer/poster
底部：差异备注 / 提出反馈
```

### 7.5 模型反馈

“提出修改意见”打开模型反馈抽屉：

```text
反馈目标：主体1 模型 v2 / 场景1 模型 v1
反馈文本
上传新参考图
@ 引用
提交反馈并重生成模型
```

删除“切换到其他模型”按钮，因为左侧选择已经承担这个功能。

---

## 8. 自由组合与导演台

### 8.1 自由组合

自由组合页保留，但要明确它是“提交 Blender 组装前的预览配置”，不是最终场景验收。

它提交：

```json
{
  "selected_subject_models": {
    "subject_1": "subject_1_model_v2",
    "subject_2": "subject_2_model_v1"
  },
  "selected_scene_model": "scene_1_model_v1",
  "placement_hints": {
    "subject_1": { "position_hint": "front_right", "scale": 1.0 },
    "subject_2": { "position_hint": "back_left", "scale": 1.0 }
  },
  "camera_intent": "hero_low_angle"
}
```

### 8.2 最终导演台

最终导演台显示的是后端 Blender 导出的结果：

```text
viewer_scene.glb
preview.png
scene_state.json
camera_presets.json
```

对象列表只有在 `scene_state.json` 有对象语义时才显示。否则显示：

```text
对象语义等待后端导出
当前可进行整体镜头查看和交付确认
```

---

## 9. 真实 GLB Viewer V1

### 9.1 model-viewer

新增依赖：

```html
<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>
```

或 npm：

```bash
npm install @google/model-viewer
```

组件：

```jsx
<model-viewer
  src={glbUrl}
  poster={posterUrl}
  camera-controls
  auto-rotate={autoRotate}
  exposure="1"
  shadow-intensity="0.35"
  environment-image="neutral"
  ar={false}
  interaction-prompt="none"
/>
```

### 9.2 控件真实化

按钮必须对应实际功能：

```text
自动旋转：toggle auto-rotate
重置镜头：调用 resetTurntableRotation 或重设 cameraOrbit
截图：toDataURL
全屏：requestFullscreen
下载：打开 GLB 文件 URL
```

没有 GLB 时：

```text
按钮 disabled
显示等待说明
```

---

## 10. 给 Codex 的执行顺序

1. 修导航和布局，去掉重复顶部大导航，让首屏按钮露出来。
2. 重做输入页 Reference Tray，执行 5 主体 + 1 场景规则。
3. 改 Composer，仅保留 `@`、上传、发送。
4. 实现 GenerationStatusDock，按预计时长伪进度推进。
5. 将 ConceptRevealScreen 改成 overlay，不作为主流程 screen。
6. 重做 ConceptReviewScreen：整体 / 主体1-5 / 场景1，支持混选。
7. 将 FeedbackCompareScreen 改为 FeedbackDrawer + 可选 CompareModal。
8. 重做 ModelReviewScreen：实体 -> 版本结构；左侧选择切中间 viewer。
9. 实现真实 GlbViewerShell with model-viewer。
10. 调整 CompositionScreen / FinalReviewScreen 的实体版本契约和空状态。
11. 调整 RuntimeAdapter normalizer，使数据结构不混淆主体和版本。
12. 更新 README / smoke，截图验证主要页面没有重叠、首屏按钮可见。

---

## 11. 验收标准

### 11.1 UI 验收

- 1440 宽度下，输入页首屏能看到“开始生成概念图”按钮。
- 左侧导航只显示主流程，不显示揭幕、反馈、资产记忆。
- 右侧参考图最多展示 5 主体 + 1 场景槽位。
- 文字不重叠，主按钮不被遮挡。
- 概念选择页可选择整体图、主体1、主体2、场景1。
- 反馈抽屉可针对主体/场景/整体分别写反馈。

### 11.2 数据验收

- 主体实体和版本分离。
- 多主体场景下，主体1/主体2不会混在一个版本列表里。
- 概念图、模型、最终场景都能追溯 source entity 和 source version。

### 11.3 GLB 验收

- 有 GLB URL 时，页面出现真实 3D viewer。
- 无 GLB URL 时，显示“等待 GLB 生成”，控制按钮 disabled。
- 最终场景使用 `viewer_scene.glb` 而不是静态截图冒充 3D。
