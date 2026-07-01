export function GlbViewerShell({ poster, title = '3D 预览', children }) {
  return (
    <div className="glb-viewer-shell">
      <img className="glb-viewer-shell__poster" src={poster} alt={title} />
      <div className="viewer-toolbar">
        <button>灯光</button>
        <button>环境</button>
        <button>显示</button>
        <button>全屏</button>
      </div>
      <div className="viewer-controls">
        <span>旋转</span>
        <span>缩放</span>
        <span>平移</span>
        <span>截图</span>
      </div>
      {children}
    </div>
  );
}
