# v0.5.2 修正进度记录

## 当前状态

主视觉方向保留，但当前 `web/creator_app` 产品流转和实现需要大改。

## 本次新增文档

- FRONTEND_V0_5_2_FULL_FLOW_FIX_SPEC.md
- REFERENCE_ENTITY_VERSION_CONTRACT_v0_5_2.md
- CODEX_PATCH_BRIEF_v0_5_2.md

## 下次执行建议

让 Codex 按 `CODEX_PATCH_BRIEF_v0_5_2.md` 直接修改 `web/creator_app`，优先级：

1. 导航/布局
2. Reference Tray
3. GenerationStatusDock
4. ConceptSelectionScreen
5. FeedbackDrawer
6. ModelReview + model-viewer
7. RuntimeAdapter 实体/版本 normalizer

## 2026-07-01 执行记录

已按 Patch 1-10 修正 `web/creator_app`：

- 导航改为左侧流程栏，扩大主舞台与输入页比例，首屏“开始生成概念图”按钮在桌面和移动端可见。
- Reference Tray 改为固定 5 个主体槽 + 1 个场景槽，仅显示主体/场景槽位，不再依赖文件名或用途下拉。
- Composer 只保留 `@`、上传、发送；`@` 打开主体/场景引用选择并插入 `@主体1`、`@场景1`。
- GenerationStatusDock 改为后台进度 Dock，使用慢推伪百分比，完成后触发 CinematicRevealOverlay。
- 概念审稿支持整体图、主体、场景分组与混选组合，反馈改为抽屉并支持按实体写意见。
- 模型验收改为实体 -> 版本结构，选择左侧模型版本会切换中间 viewer。
- `ModelViewerStage` 接 `@google/model-viewer`；有 GLB 时加载真实模型，无 GLB 时显示 fallback，并提供重置镜头、截图、下载、全屏入口。
- 自由组合改为基于 `entity_id` / `version_id` 的版本选择。
- 最终导演台对象列表只消费后端 `scene_state.json.objects`；缺失时显示等待对象语义空态，不再伪造对象。
- RuntimeAdapter 增加 reference slot、entity、asset version、approved concept selection normalizer。

验证结果：

- `npm run build`：通过；仅保留 `model-viewer` 动态 chunk 大小 warning。
- `CREATOR_APP_BASE_URL=http://10.2.16.106:5173 npm run smoke:screenshots`：通过，8 个桌面/移动页面无水平溢出。
- `CREATOR_APP_BASE_URL=http://10.2.16.106:5173 npm run smoke:backend-readonly`：通过；当前后端为 5173 同源 `/api/creator`。
- Playwright 聚焦交互检查：通过，覆盖 `@` 选择、概念揭幕 overlay、概念组合弹窗、反馈抽屉、模型反馈抽屉、导演台 scene_state 空态。

访问说明：

- Vite 开发服务绑定 `0.0.0.0:5173`。
- 本机内部验证地址为 `http://10.2.16.106:5173/`。
- 给用户侧访问应使用外层地址 `http://10.134.142.143:5173/`。
