# image23D Creator App v0.5

这是从已锁定视觉风格转译并迁入仓库的 React/Vite Creator App。
当前目录是新公共前端的工程落点。5173 自带同源只读后端
`/api/creator`，用于读取真实 Round04D 概念样例。

## 快速运行

```bash
npm install
npm run dev
```

打开：

```text
http://10.2.16.106:5173/
```

真实后端数据默认同源挂在 5173 下，不需要另开 8093：

```text
http://10.2.16.106:5173/#concept-review
```

项目中心读取：

```text
GET /api/creator/projects?collection=round04d_concepts
```

## 页面

- `#intake`：输入创作需求与 ReferenceTray
- `#concept-review`：整体图 / 主体图 / 场景图混选审稿
- `#model-review`：主体/场景 GLB 验收
- `#asset-memory`：创作记忆资产库
- `#composition`：自由组合与场景编排
- `#final-review`：最终 Blender 场景导演台
- `#delivery`：交付下载

`#reveal` 和 `#feedback-compare` 已不再是公开章节。旧链接会回落到
`#concept-review`；揭幕由 `CinematicRevealOverlay` 承担，反馈由
`FeedbackDrawer` + `VersionCompareModal` 承担。

## 关键文档

- `docs/FRONTEND_IMPLEMENTATION_REPORT_v0_5.md`
- `docs/BACKEND_INTEGRATION_PLAN_v0_5.md`
- `docs/PROTOTYPE_USAGE_GUIDE_v0_5.md`

## 当前边界

- 默认读取同源 `/api/creator`。配置 `?mock=1` 时才回到 mock fallback。
- Creator App 默认请求 `GET /api/creator/projects?collection=round04d_concepts`，
  项目中心展示 `outputs/runs/round04d_live_12_samples/case_*` 的 12 个真实概念样例。
- 已接入后端读接口：project list、project bundle、file manifest/file URL。
- 聊天、上传、user-action、loop 仍需在 `/api/creator/projects/<project_key>/...`
  写接口下继续联调。
- `ModelViewerStage` 使用 `<model-viewer>`；存在 `model.url` 或
  `finalScene.viewerSceneUrl` 时加载真实 GLB，否则显示明确等待状态。
- 最终导演台的对象聚焦、镜头预设、显示/隐藏是前端真实状态行为；
  有 `scene_state.json` bounds/camera preset 时会驱动 viewer camera。
- 待继续联调写操作：concept/model/final user-action、asset-action、loop。
- 没有替换旧 public UI。
- 顶部工作区导航是 Creator App 的产品导航，不再是窄左侧原型 tabs。
