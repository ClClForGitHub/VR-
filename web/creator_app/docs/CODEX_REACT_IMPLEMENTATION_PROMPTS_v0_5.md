# Codex / AI 前端实现任务包 v0.5

本文件用于后续把 React 原型真正迁入 GitHub 仓库。不要一次性让 AI “照图重写前端”，按下面任务切片执行。

---

## Task 0：阅读边界

Prompt:

```text
你正在实现 image23D 新前端。请先阅读：
- AGENTS.md
- docs/repo_layout.md
- image23d 前端工程报告 v0.5
- React prototype v0_1_componentized/README.md
- BACKEND_INTEGRATION_PLAN_v0_5.md

只确认理解，不改代码。
关键边界：
1. 旧 runtime console 只保留为 dev/debug，不作为公共用户界面。
2. 新前端风格必须遵循 Premium Cinematic Dark Creation Studio。
3. 先使用 mock 数据实现 UI，不直接接真实后端。
4. 不要把 debug JSON、raw path、internal run id 暴露给公共 UI。
```

---

## Task 1：创建前端骨架

Prompt:

```text
在仓库中创建 web/creator_app/，迁入 v0_1_componentized React/Vite 原型。
保持文件结构：
src/api
src/components
src/screens
src/data
src/styles
public/mock-assets
public/design-renders

先不要接后端。
执行 npm build 或可用的静态检查。
记录验证结果。
```

验收：

```text
web/creator_app/package.json 存在
npm run dev 可启动
所有 hash 页面可打开
```

---

## Task 2：设计 token 和基础组件稳定

Prompt:

```text
优化 web/creator_app/src/styles/tokens.css 和 app.css。
目标：
1. 保持锁定风格。
2. 保持组件比例统一。
3. 修正小屏滚动问题。
4. 不改变业务状态和页面结构。
5. 不接后端。

更新后截图检查 intake、concept-review、final-review、delivery 四个页面。
```

---

## Task 3：接入只读后端 bundle

Prompt:

```text
实现 RuntimeAdapter 的只读能力：
- GET /api/creator/projects
- GET /api/creator/projects?collection=round04d_concepts
- GET /api/creator/projects/<project_key>/bundle
- GET /api/creator/projects/<project_key>/file?path=...

新增 normalizeRuntimeBundle(rawBundle)，把 raw bundle 转为 CreatorRunViewModel。
UI 仍保留 mock fallback。
不要实现写操作。
```

验收：

```text
没有后端时 mock 正常
有后端时可展示真实 run 列表/当前 run 文件
```

---

## Task 4：接入聊天和上传

Prompt:

```text
实现 ChatComposer 的真实提交：
- POST /api/creator/projects/<project_key>/chat
- POST /api/creator/projects/<project_key>/upload

实现 @图片引用选择：
- 上传后生成 alias：@图片1、@图片2...
- 用户输入时可插入 alias
- 提交时把 alias 映射到 image_id/artifact_id/binding_role

不要让后端分析逻辑进入前端。
```

---

## Task 5：接入概念确认 user-action

Prompt:

```text
接入概念图审稿按钮：
- approve_concept
- request_concept_changes

点击接受：POST user-action，然后刷新 bundle 或监听 SSE。
点击修改：提交 feedback_text 和参考图绑定。
```

---

## Task 6：接入 model-viewer

Prompt:

```text
把 GlbViewerShell 替换为 ModelViewerShell。
优先使用 <model-viewer>：
- src = viewer_scene.glb 或 subject GLB
- poster = preview.png
- camera-controls
- auto-rotate 可选
- exposure / shadow / environment image 后续再做
保留静态 poster fallback。
```

---

## Task 7：最终 Blender 导演台对象聚焦

Prompt:

```text
读取 scene_state.json，生成 sceneObjects 和 cameraPresets。
在 final-review 页面：
- 点击对象 -> 高亮对象卡
- 点击镜头预设 -> 更新 viewer camera target/orbit
- 修改意见 -> request_blender_changes
- 确认交付 -> approve_blender_preview
```

---

## Task 8：交付下载

Prompt:

```text
在 delivery 页面读取 delivery_handoff / file_manifest。
显示：
- .blend
- viewer_scene.glb
- preview.png
- scene_state.json
- camera_presets
- manifest/readme
- package zip

所有下载链接走 /api/creator/projects/<project_key>/file?path=...
```

---

## Task 9：生产切换

Prompt:

```text
将公共入口切换到 web/creator_app 构建产物。
旧 runtime_console 保留 dev/debug 入口。
公共 UI 禁止展示 raw JSON、绝对路径、internal run id。
添加一个 hydrated smoke 或 screenshot smoke 检查关键页面。
```

---

## 总原则

- 每个任务单独提交/记录。
- 每次任务只改目标范围内的文件。
- 每个页面先 mock 后真实。
- 后端变化只改 adapter/normalizer，不让 UI 大面积重写。
