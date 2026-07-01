# image23D Creator App Mock v0.5

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
http://127.0.0.1:5173/
```

## 页面

- `#intake`：聊天输入与参考图绑定
- `#reveal`：概念图揭幕动画 mock
- `#concept-review`：概念图审稿画廊
- `#feedback-compare`：反馈 / 重生成版本对比
- `#model-review`：主体/场景 GLB 验收壳
- `#asset-memory`：创作记忆资产库
- `#composition`：自由组合与场景编排
- `#final-review`：最终 Blender 场景导演台
- `#delivery`：交付下载

## 关键文档

- `docs/FRONTEND_IMPLEMENTATION_REPORT_v0_5.md`
- `docs/BACKEND_INTEGRATION_PLAN_v0_5.md`
- `docs/PROTOTYPE_USAGE_GUIDE_v0_5.md`

## 当前边界

- 使用 mock 数据。
- 默认使用 mock 数据；配置 `VITE_RUNTIME_API_BASE_URL` 或 URL 参数
  `?api_base=http://127.0.0.1:8093` 后可读取真实 runtime-console 只读 API。
- 已接入只读后端：run list、run bundle、file manifest/file URL。
- 未接入写操作：chat、upload、user-action、loop。
- 没有替换旧 public UI。
- `GlbViewerShell` 是 viewer 壳，后续替换为 `model-viewer` 或 React Three Fiber。
- 左侧 screen tabs 是原型切换工具，生产环境可隐藏或只在 dev 模式显示。
