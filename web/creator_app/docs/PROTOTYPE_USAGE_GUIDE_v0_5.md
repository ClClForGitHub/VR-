# image23D React 原型使用指南 v0.5

## 1. 文件位置

```text
image23d_frontend_design_research/
  10_react_prototype/
    v0_1_componentized/
      package.json
      index.html
      public/
      src/
      docs/
```

## 2. 本地启动

```bash
cd image23d_frontend_design_research/10_react_prototype/v0_1_componentized
npm install
npm run dev
```

访问：

```text
http://10.134.142.143:5173/
```

## 3. 页面 hash

```text
#intake
#concept-review
#model-review
#asset-memory
#composition
#final-review
#delivery
```

`#reveal` 和 `#feedback-compare` 已降级为兼容旧链接，不再是主流程页面。
揭幕由 `CinematicRevealOverlay` 弹层承担；反馈由 `FeedbackDrawer` 和
可选的 `VersionCompareModal` 承担。

## 4. 修改 UI 的位置

### 全局视觉 token

```text
src/styles/tokens.css
```

控制：

- 颜色；
- 线框；
- 光效；
- 字体；
- 圆角；
- 阴影。

### 全局布局和组件样式

```text
src/styles/app.css
```

控制：

- 顶部流程条；
- 工作区导航；
- 面板；
- 卡片；
- 资产库；
- model-viewer GLB stage；
- 交付页；
- 响应式。

### 页面内容

```text
src/screens/
```

每个状态一个 screen。

### mock 数据

```text
src/data/mockProject.js
```

替换这里可以快速改图片、标题、状态、资产数量。

### 后端接线

```text
src/api/runtimeAdapter.js
```

后续真实 API 只在这里接入。

## 5. 图片资源

```text
public/mock-assets/
```

用于原型内的概念图、主体图、场景图、最终场景图 mock。

```text
public/design-renders/
```

用于保存锁定风格渲染图和系统板，给后续设计/工程对照。

## 6. 不建议改动

不要在 UI 组件里直接写 fetch 后端逻辑。  
不要在 screen 里直接解析 raw state.json。  
不要把 debug 字段塞回公共主界面。  
不要重新引入旧 runtime console 的三栏后台风格。  

## 7. 生产化迁移建议

如果要合入仓库，推荐复制到：

```text
web/creator_app/
```

然后让旧 `tools/runtime_console_server.py` 或新的前端 dev server 提供静态资源。

短期也可先作为独立 Vite 项目运行，再逐步接后端。
