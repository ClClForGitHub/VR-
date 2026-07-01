# image23D Creator App v0.5

这是从已锁定视觉风格转译并迁入仓库的 React/Vite Creator App mock。
当前目录是新公共前端的工程落点，旧 `web/runtime_console/` 仍保留为
dev/debug 入口。

## 快速运行

```bash
npm install
npm run dev
```

打开：

```text
http://10.134.142.143:5173/
```

真实后端只读数据入口：

```text
http://10.134.142.143:5173/?api_base=%2Fruntime-api#delivery
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

- 默认使用 mock 数据；配置 `VITE_RUNTIME_API_BASE_URL` 或 URL 参数
  `?api_base=/runtime-api` 后可通过 Vite proxy 读取真实 runtime-console 只读 API。
- 已接入只读后端：run list、run bundle、file manifest/file URL。
- `ModelViewerStage` 使用 `<model-viewer>`；存在 `model.url` 或
  `finalScene.viewerSceneUrl` 时加载真实 GLB，否则显示明确等待状态。
- 最终导演台的对象聚焦、镜头预设、显示/隐藏是前端真实状态行为；
  有 `scene_state.json` bounds/camera preset 时会驱动 viewer camera。
- 未接入写操作：chat、upload、user-action、loop。
- 没有替换旧 public UI。
- 顶部工作区导航是 Creator App 的产品导航，不再是窄左侧原型 tabs。
