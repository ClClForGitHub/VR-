# image23D 前端工程落地报告 v0.5

更新时间：2026-07-01  
当前阶段：主视觉已锁定，进入 React 组件化原型与后端接线准备阶段。  
主风格：Premium Cinematic Dark Creation Studio / 高级电影感 AI 3D 创作工作台。

---

## 1. 当前结论

本项目的前端不再沿用旧 runtime console 的布局和视觉。旧代码只作为后端状态、文件路径、API 边界和调试入口参考。

新的前端目标是：

```text
自然语言 + 参考图绑定
  -> 概念图揭幕
  -> 概念图审稿
  -> 反馈/重生成
  -> 主体/场景 GLB 验收
  -> 创作记忆资产库
  -> 自由组合与场景编排
  -> Blender 最终导演台
  -> 交付下载
```

当前已锁定的 UI 气质是深色电影级创作产品，不是后台管理系统，不是普通聊天机器人，也不是古板工程控制台。

---

## 2. 设计原则

### 2.1 视觉原则

- 深色电影舞台作为主背景。
- 青蓝光效作为主要交互强调，但避免廉价霓虹。
- 生成结果必须是视觉中心，而不是被信息面板淹没。
- 图片、模型、最终场景使用大画幅展示。
- 所有按钮、卡片、进度条、资产库、面板必须统一比例和圆角。
- 允许轻微科技感，但整体必须保持成熟、克制、高级。
- 字体优先使用成熟中文体系：Source Han Sans SC / Noto Sans CJK SC / 思源黑体一类，英文数字可使用 Inter。

### 2.2 产品原则

- 前端是单用户创作工作台，不做多用户/多会话复杂协作。
- 聊天是创作入口，不是客服聊天。
- 上传参考图后，需要支持 `@图片1` / `@图片2` 的引用绑定。
- 前端只整理输入和反馈；分析、SceneSpec、生成、Blender 执行在后端。
- 所有被接受或拒绝的概念图、模型、场景都进入创作记忆，不丢失。
- 最终 Blender 是权威场景，前端是交互验收和轻量编排界面。

---

## 3. 页面范围

当前 React 原型覆盖 9 个页面状态：

| Hash | 页面 | 对应后端阶段 | 说明 |
|---|---|---|---|
| `#intake` | 聊天输入与参考图绑定 | `INTAKE` | 输入自然语言、上传图、绑定图片角色 |
| `#reveal` | 概念图揭幕 | `CONCEPT_GENERATION -> CONCEPT_REVIEW` | 生成完成后的揭幕动画/仪式感 |
| `#concept-review` | 概念图审稿 | `CONCEPT_REVIEW` | 整体图、主体图、场景图审稿 |
| `#feedback-compare` | 反馈/重生成对比 | `CONCEPT_REVIEW` | 版本对比、拒绝、重新生成 |
| `#model-review` | 主体/场景模型验收 | `SUBJECT_ASSET_QA` / `SCENE_ASSET_ADAPTATION` | GLB 预览与 QA |
| `#asset-memory` | 创作记忆资产库 | 跨阶段 | 历史图、被拒绝图、可复用资产 |
| `#composition` | 自由组合与场景编排 | `BLENDER_ASSEMBLY_PLANNING` | 选择主体、场景、位置、镜头 |
| `#final-review` | 最终 Blender 导演台 | `BLENDER_PREVIEW` | 对象聚焦、镜头调整、最终验收 |
| `#delivery` | 交付下载 | `DELIVERY` | zip、blend、glb、scene_state、预览图 |

---

## 4. 核心组件

当前 React 原型组件拆分如下：

```text
src/components/
  AppShell.jsx              全局壳：顶部项目、阶段、左侧状态导航
  Stepper.jsx               五阶段流程条
  ScreenTabs.jsx            原型状态切换，后续生产环境可隐藏或转 dev
  ScreenHeading.jsx         页面标题区
  Button.jsx                按钮系统
  Panel.jsx                 玻璃质感信息面板
  Composer.jsx              聊天输入 / 反馈输入
  AssetCard.jsx             概念图、模型、场景资产卡
  AssetMemoryPanel.jsx      右侧/侧边资产记忆组件
  HeroStage.jsx             大画幅概念图/场景展示
  ReviewDock.jsx            接受 / 修改动作栏
  GlbViewerShell.jsx        GLB 展示壳，后续替换 model-viewer/R3F
```

---

## 5. 数据预留

当前用 `src/data/mockProject.js` 做 mock 数据，后续接入后端时不应让 UI 组件直接读取后端原始结构。

建议数据流：

```text
Python runtime files/API
  -> RuntimeAdapter
  -> normalizeRuntimeBundle()
  -> UI ViewModel
  -> React components
```

保留适配层的原因：

1. 后端状态仍在改动，前端不要被后端字段变化频繁打断。
2. UI 需要的是产品视图，不是原始 state.json。
3. 资产记忆、版本血缘、当前方案、已拒绝资产，都需要在 ViewModel 层整理。
4. 后续 GLB viewer 也需要统一处理文件 URL、poster、scene_state、camera_presets。

---

## 6. 重要交互

### 6.1 `@图片` 引用绑定

前端需要把自然语言输入中的 `@图片1`、`@图片2` 与上传图片 id 对应起来。

预期 payload：

```json
{
  "text": "让 @图片1 的机械灵兽在 @图片2 的遗迹场景中，黄昏打光。",
  "references": [
    {
      "alias": "@图片1",
      "image_id": "image_upload_subject",
      "artifact_id": "artifact_subject",
      "binding_role": "subject"
    },
    {
      "alias": "@图片2",
      "image_id": "image_upload_scene",
      "artifact_id": "artifact_scene",
      "binding_role": "scene"
    }
  ]
}
```

### 6.2 概念图揭幕

揭幕动画不是独立页面的必需结构，而是概念生成完成后的状态效果：

```text
生成中
  -> 背景压暗
  -> 能量/扫描/光束聚焦
  -> 主概念图出现
  -> 停留在概念审稿画廊
```

代码落地可以先用 CSS animation + Framer Motion，后续可增强为 Three.js 粒子。

### 6.3 创作记忆

资产状态必须支持：

```text
已选用
历史版本
已拒绝
可复用归档
当前查看
最终场景
```

被拒绝资产不可丢失。用户可以重新启用，或从旧概念图重新生成模型。

### 6.4 自由组合

用户在最终组装前可以选择：

- 哪些主体模型进入场景；
- 选择哪个场景模型；
- 选择模型版本；
- 输入位置、旋转、缩放或用简化控件调整；
- 选择镜头意图；
- 提交给后端 Blender 重新组装。

前端仅做预览和结构化指令；权威结果由 Blender 后端导出。

---

## 7. GLB / Blender 展示策略

### V1

- `GlbViewerShell` 替换为 `<model-viewer>`。
- 用 `preview.png` 作为 poster。
- 用 `viewer_scene.glb` 或主体/场景 GLB 作为模型。
- 支持 rotate / zoom / fullscreen / screenshot / camera presets。
- 对象语义从 `scene_state.json` 读取。

### V2

- 最终导演台升级为 React Three Fiber。
- 支持对象 hover、选中、高亮、聚焦、镜头轨道、轻量 transform preview。
- 前端保存 preview transform，提交给后端 Blender 执行真实修改。

---

## 8. 文件结构建议

生产代码建议单独放在新目录，不直接改旧 UI：

```text
web/creator_app/
  package.json
  src/
    api/
    components/
    screens/
    data/
    styles/
    viewer/
```

旧 `web/runtime_console/` 可保留为 dev/debug，公共入口切到新 Creator App。

---

## 9. 使用方式

### 查看当前 React 原型

```bash
cd image23d_frontend_design_research/10_react_prototype/v0_1_componentized
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173/
```

页面 hash：

```text
#intake
#reveal
#concept-review
#feedback-compare
#model-review
#asset-memory
#composition
#final-review
#delivery
```

---

## 10. 后续工程顺序

推荐执行顺序：

1. React 原型本地跑通。
2. 补齐响应式和组件比例。
3. 接入真实图片 URL 和静态资源。
4. 接入 RuntimeAdapter，先读 `GET /api/creator/projects/<project_key>/bundle`。
5. 做 ViewModel normalization。
6. 接入聊天、上传、用户动作。
7. 接入 model-viewer。
8. 接入最终 Blender scene_state / camera presets / delivery manifest。
9. 替换旧公共 UI，旧 UI 收进 dev 模式。
10. 建立 smoke 测试和截图验收。

---

## 11. 给后续 AI / Codex 的原则

不要给 Codex 一句“照图做”。

应该按任务给：

```text
目标
涉及文件
参考设计图
输入数据
组件列表
不能做什么
验收标准
```

Codex 第一阶段只做静态 React mock，不接真实后端。第二阶段才接 RuntimeAdapter。第三阶段接 viewer。
