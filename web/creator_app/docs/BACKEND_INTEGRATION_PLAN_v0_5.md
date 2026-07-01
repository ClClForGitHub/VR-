# image23D 前后端接线计划 v0.5

当前定位：后端还在同步改动，因此本阶段只定义前端预留口和接线策略，不强行绑定最终字段。

---

## 0. 当前仓库落地状态（2026-07-01）

已落地：

```text
GET /api/runs
GET /api/runs/<run_key>/bundle
GET /api/runs/<run_key>/file?path=...
RuntimeAdapter
normalizeRuntimeBundle(rawBundle)
mock fallback
```

验证：

```text
npm run build
npm run smoke:screenshots
npm run smoke:backend-readonly
```

仍未落地：

```text
POST /chat
POST /upload
POST /user-action
POST /loop
model-viewer
旧 public UI 替换
```

当前只读接线可通过以下方式手动查看：

```text
http://10.134.142.143:5173/?api_base=%2Fruntime-api#delivery
```

---

## 1. 接线原则

1. 前端 UI 组件不直接读取原始 `state.json`。
2. 所有后端读取通过 `RuntimeAdapter`。
3. 所有后端结果先进入 `normalizeRuntimeBundle()`。
4. 组件只消费稳定的 UI ViewModel。
5. 旧 runtime console 可以继续作为 dev/debug，不作为用户主界面。
6. 后端字段变化时，只改 adapter/normalizer，不改所有 UI 组件。

---

## 2. 预期后端文件

前端需要后端逐步稳定这些文件或 API 返回：

```text
state.json
frontend_status.json
summary.json
runtime_plan.json
runtime_user_action_summary.json
runtime_loop_summary.json
delivery_handoff.json
viewer_export/viewer_scene.glb
viewer_export/scene_state.json
preview_render/preview.png
delivery_package/package/*.zip
runtime_console/chat.jsonl
runtime_console/uploads.jsonl
```

---

## 3. 预期 API

沿用当前 runtime console API 方向：

```text
GET  /api/runs
GET  /api/runs/<run_key>
GET  /api/runs/<run_key>/bundle
GET  /api/runs/<run_key>/file?path=...
GET  /api/runs/<run_key>/events

POST /api/runs
POST /api/runs/<run_key>/chat
POST /api/runs/<run_key>/upload
POST /api/runs/<run_key>/plan
POST /api/runs/<run_key>/loop
POST /api/runs/<run_key>/user-action
```

---

## 4. UI ViewModel 建议

前端最终不要直接展示 raw state，而是整理成：

```ts
type CreatorRunViewModel = {
  runKey: string
  phase: string
  publicPhaseLabel: string
  currentScreen: string
  nextAction: {
    type: string
    label: string
    enabled: boolean
  }
  project: {
    title: string
    createdAt: string
    updatedAt: string
  }
  references: ReferenceView[]
  concepts: ConceptAssetView[]
  subjectAssets: ModelAssetView[]
  sceneAssets: ModelAssetView[]
  finalScene?: FinalSceneView
  assetMemory: AssetMemoryView
  delivery?: DeliveryView
  files: FileManifestView[]
}
```

---

## 5. 后端阶段到前端页面

| 后端 phase | 前端页面 |
|---|---|
| `INTAKE` | `#intake` |
| `SCENE_SPEC_DRAFT` / `SCENE_SPEC_READY` | `#intake` + `GenerationStatusDock` |
| `CONCEPT_GENERATION` | `#intake` 或 `#concept-review` + `GenerationStatusDock`；完成后弹出 `CinematicRevealOverlay` |
| `CONCEPT_REVIEW` | `#concept-review` |
| `CONCEPT_APPROVED` | `#model-review` + `GenerationStatusDock` |
| `SUBJECT_ASSET_GENERATION` / `SCENE_ASSET_GENERATION` | `#model-review` + `GenerationStatusDock` |
| `SUBJECT_ASSET_QA` / `SCENE_ASSET_ADAPTATION` | `#model-review` |
| `BLENDER_ASSEMBLY_PLANNING` | `#composition` |
| `BLENDER_ASSEMBLY_EXECUTION` | `#composition` + `GenerationStatusDock` |
| `BLENDER_PREVIEW` | `#final-review` |
| `BLENDER_EDIT` | `#final-review` with edit pending |
| `DELIVERY` | `#delivery` |

---

## 6. 用户动作映射

### 接受概念图

```json
{
  "action_type": "approve_concept",
  "note": "用户接受当前概念图方案",
  "rebuild_plan": true
}
```

### 请求概念修改

```json
{
  "action_type": "request_concept_changes",
  "feedback_text": "增强天空光照，主体更有压迫感。",
  "source_turn_id": "msg_xxx",
  "rebuild_plan": true
}
```

### 接受最终 Blender 预览

```json
{
  "action_type": "approve_blender_preview",
  "note": "用户接受最终场景",
  "rebuild_plan": true
}
```

### 请求 Blender 修改

```json
{
  "action_type": "request_blender_changes",
  "feedback_text": "让机械兽更靠近镜头，背景拱门稍微变大。",
  "source_turn_id": "msg_xxx",
  "rebuild_plan": true
}
```

---

## 7. 自由组合 payload

当前新增设计需要后端接收一个组合/编排意图：

```json
{
  "selected_subject_assets": [
    {
      "subject_id": "subject_beast",
      "model_asset_id": "subject_beast_v12",
      "source_concept_id": "concept_v3",
      "placement_hint": "front_left",
      "transform": {
        "position": [-3.52, 0, 1.28],
        "rotation": [0, -18, 0],
        "scale": 1.0
      }
    }
  ],
  "selected_scene_asset": {
    "scene_id": "scene_ruins",
    "model_asset_id": "scene_ruins_v12"
  },
  "camera_intent": {
    "preset": "director",
    "target_subject_id": "subject_beast"
  },
  "feedback_text": "整体构图更靠近低机位电影镜头。"
}
```

这部分可以先作为 `request_blender_changes.feedback_text` 的结构化 metadata，后续再独立成新的 endpoint。

---

## 8. GLB viewer 接入顺序

### 第一步：model-viewer

前端需要后端给：

```json
{
  "viewer_scene_url": "/api/runs/<run_key>/file?path=viewer_export/viewer_scene.glb",
  "poster_url": "/api/runs/<run_key>/file?path=preview_render/preview.png",
  "scene_state_url": "/api/runs/<run_key>/file?path=viewer_export/scene_state.json"
}
```

### 第二步：对象聚焦

从 `scene_state.json` 中读：

```json
{
  "objects": [
    {
      "object_id": "obj_subject_beast",
      "label": "机械灵兽 · 霜牙",
      "type": "subject",
      "bounds": {
        "center": [0, 1.2, 0],
        "size": [2.8, 1.7, 4.2]
      }
    }
  ],
  "camera_presets": [
    {
      "id": "director",
      "label": "导演镜头",
      "target": [0, 1.1, 0],
      "orbit": "45deg 65deg 8m"
    }
  ]
}
```

---

## 9. 接线时机建议

当前后端仍在变化，因此建议分三步：

1. React mock 原型稳定。
2. 接只读 API：runs / bundle / file manifest / viewer_scene。
3. 再接写操作：chat / upload / user-action / loop。

这样能避免前端设计被后端接口变动拖慢。
