import { useEffect, useRef, useState } from 'react';
import { Button } from './Button.jsx';

const defaultOrbit = '35deg 72deg 6m';
const defaultTarget = '0m 1m 0m';

export function ModelViewerStage({
  src,
  poster,
  title = '3D 预览',
  cameraPreset,
  focusObject,
  visibleObjects = [],
  fallbackLabel = '等待 GLB 生成',
}) {
  const viewerRef = useRef(null);
  const [autoRotate, setAutoRotate] = useState(Boolean(src));
  const [selectedLabel, setSelectedLabel] = useState('');
  const hasModel = Boolean(src);
  const visibleCount = visibleObjects.filter((object) => object.visible !== false).length;
  const hiddenCount = Math.max(0, visibleObjects.length - visibleCount);

  useEffect(() => {
    if (!hasModel || window.customElements?.get('model-viewer')) return undefined;
    let cancelled = false;
    import('@google/model-viewer').then(() => {
      if (cancelled) return;
      viewerRef.current?.updateComplete?.catch?.(() => {});
    });
    return () => {
      cancelled = true;
    };
  }, [hasModel]);

  useEffect(() => {
    if (!hasModel || !cameraPreset) return;
    applyCamera(viewerRef.current, cameraPreset);
  }, [cameraPreset, hasModel]);

  useEffect(() => {
    if (!hasModel || !focusObject) return;
    const focused = focusViewerObject(viewerRef.current, focusObject);
    setSelectedLabel(focusObject.label || focusObject.display_name || '');
    if (!focused && cameraPreset) applyCamera(viewerRef.current, cameraPreset);
  }, [cameraPreset, focusObject, hasModel]);

  function toggleAutoRotate() {
    const next = !autoRotate;
    setAutoRotate(next);
    if (viewerRef.current) viewerRef.current.autoRotate = next;
  }

  function resetCamera() {
    applyCamera(viewerRef.current, cameraPreset || { orbit: defaultOrbit, target: defaultTarget });
  }

  async function captureScreenshot() {
    const viewer = viewerRef.current;
    if (!viewer || typeof viewer.toDataURL !== 'function') return;
    const dataUrl = await viewer.toDataURL('image/png');
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = `${title.replace(/\s+/g, '_') || 'model_viewer'}.png`;
    link.click();
  }

  function openFullscreen() {
    viewerRef.current?.requestFullscreen?.();
  }

  function downloadModel() {
    if (!src) return;
    const link = document.createElement('a');
    link.href = src;
    link.download = `${title.replace(/\s+/g, '_') || 'model'}.glb`;
    link.rel = 'noreferrer';
    link.click();
  }

  return (
    <section className={`model-viewer-stage ${hasModel ? 'has-model' : 'is-waiting'}`}>
      {hasModel ? (
        <model-viewer
          ref={viewerRef}
          src={src}
          poster={poster}
          alt={title}
          camera-controls
          auto-rotate={autoRotate}
          shadow-intensity="0.85"
          exposure={cameraPreset?.exposure || '1'}
          environment-image="neutral"
          camera-orbit={cameraPreset?.orbit || defaultOrbit}
          camera-target={cameraPreset?.target || defaultTarget}
          interaction-prompt="auto"
        />
      ) : (
        <div className="model-viewer-fallback">
          {poster && <img src={poster} alt={title} />}
          <div className="model-viewer-fallback__copy">
            <span className="pill">{fallbackLabel}</span>
            <h3>{title}</h3>
            <p>当前运行还没有可加载的 GLB。真实后端产出 model.url 或 viewer_scene.glb 后，这里会切换为可旋转、缩放、截图的 3D viewer。</p>
          </div>
        </div>
      )}
      <div className="model-viewer-toolbar">
        <Button variant="chip" disabled={!hasModel} onClick={toggleAutoRotate}>{autoRotate ? '暂停旋转' : '自动旋转'}</Button>
        <Button variant="chip" disabled={!hasModel} onClick={resetCamera}>重置镜头</Button>
        <Button variant="chip" disabled={!hasModel} onClick={captureScreenshot}>截图</Button>
        <Button variant="chip" disabled={!hasModel} onClick={downloadModel}>下载</Button>
        <Button variant="chip" disabled={!hasModel} onClick={openFullscreen}>全屏</Button>
      </div>
      <div className="model-viewer-status">
        <span>{hasModel ? 'GLB 已连接' : 'GLB 未就绪'}</span>
        {visibleObjects.length > 0 && <span>显示 {visibleCount} / 隐藏 {hiddenCount}</span>}
        {selectedLabel && <span>焦点：{selectedLabel}</span>}
      </div>
    </section>
  );
}

function applyCamera(viewer, preset) {
  if (!viewer) return;
  if (preset?.orbit) viewer.cameraOrbit = preset.orbit;
  if (preset?.target) viewer.cameraTarget = preset.target;
  viewer.jumpCameraToGoal?.();
}

function focusViewerObject(viewer, object) {
  if (!viewer || !object?.bounds) return false;
  const focus = focusForBounds(object.bounds);
  if (!focus) return false;
  viewer.cameraTarget = `${focus.target[0].toFixed(4)}m ${focus.target[1].toFixed(4)}m ${focus.target[2].toFixed(4)}m`;
  viewer.cameraOrbit = `35deg 72deg ${focus.radius.toFixed(4)}m`;
  viewer.jumpCameraToGoal?.();
  return true;
}

function focusForBounds(bounds) {
  const min = bounds?.min;
  const max = bounds?.max;
  if (!Array.isArray(min) || !Array.isArray(max) || min.length !== 3 || max.length !== 3) return null;
  const target = min.map((value, index) => (Number(value) + Number(max[index])) / 2);
  const diagonal = Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
  if (target.some((value) => !Number.isFinite(value)) || !Number.isFinite(diagonal)) return null;
  return { target, radius: Math.max(0.35, diagonal * 2.6) };
}
