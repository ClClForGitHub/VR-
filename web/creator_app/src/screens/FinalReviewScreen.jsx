import { useEffect, useMemo, useState } from 'react';
import { Button } from '../components/Button.jsx';
import { ModelViewerStage } from '../components/ModelViewerStage.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';

export function FinalReviewScreen({ onNavigate, onOpenAssetMemory, viewModel }) {
  const { cameraPresets, sceneObjects } = viewModel;
  const finalScene = viewModel.finalScene || {};
  const [activeCameraId, setActiveCameraId] = useState(cameraPresets[0]?.id);
  const [objects, setObjects] = useState(sceneObjects);
  const [activeObjectId, setActiveObjectId] = useState(viewModel.activeObjectId || sceneObjects[0]?.id);
  const activeCamera = useMemo(
    () => cameraPresets.find((preset) => preset.id === activeCameraId) || cameraPresets[0],
    [activeCameraId, cameraPresets],
  );
  const activeObject = useMemo(
    () => objects.find((object) => object.id === activeObjectId),
    [activeObjectId, objects],
  );
  const hasSceneObjects = objects.length > 0;

  useEffect(() => {
    setObjects(sceneObjects);
    setActiveObjectId(viewModel.activeObjectId || sceneObjects[0]?.id);
  }, [sceneObjects, viewModel.activeObjectId]);

  useEffect(() => {
    setActiveCameraId(cameraPresets[0]?.id);
  }, [cameraPresets]);

  function toggleObject(id) {
    setObjects((current) => current.map((object) => (
      object.id === id ? { ...object, visible: !object.visible } : object
    )));
  }

  return (
    <>
      <ScreenHeading title="最终 Blender 场景验收 / 导演台" subtitle="最终场景合成已完成，请进行镜头检查、构图评审与最终验收" />
      <div className="final-review-layout">
        <aside className="stack">
          <Panel title="镜头预设">
            <div className="preset-grid">
              {cameraPresets.map((preset) => (
                <Button
                  key={preset.id}
                  variant="chip"
                  className={preset.id === activeCameraId ? 'is-active-chip' : ''}
                  onClick={() => setActiveCameraId(preset.id)}
                >
                  {preset.label}
                </Button>
              ))}
            </div>
          </Panel>
          <Panel title="资产记忆">
            <p className="panel-copy">概念、模型版本和参考来源保留在全局资产记忆中，不占用导演台主舞台。</p>
            <Button className="full-width" onClick={onOpenAssetMemory}>打开资产记忆库</Button>
          </Panel>
          <Panel title="焦点控制">
            {hasSceneObjects ? (
              <div className="thumb-strip">
                {objects.slice(0, 6).map((object) => (
                  <button
                    key={object.id}
                    className={object.id === activeObjectId ? 'is-selected' : ''}
                    disabled={object.visible === false || object.selectable === false}
                    onClick={() => setActiveObjectId(object.id)}
                  >
                    {object.label}
                  </button>
                ))}
              </div>
            ) : (
              <div className="empty-state">等待后端 scene_state.json 提供对象列表后启用聚焦。</div>
            )}
          </Panel>
        </aside>
        <section className="stack">
          <ModelViewerStage
            src={finalScene.viewerSceneUrl || finalScene.url}
            poster={finalScene.image}
            title={finalScene.title || '最终场景'}
            cameraPreset={activeCamera}
            focusObject={activeObject}
            visibleObjects={objects}
            fallbackLabel="等待 viewer_scene.glb 导出"
          />
          <Panel title="镜点时间线">
            <div className="thumb-strip">
              {cameraPresets.map((preset) => (
                <button
                  key={preset.id}
                  className={`timeline-shot ${preset.id === activeCameraId ? 'is-selected' : ''}`}
                  onClick={() => setActiveCameraId(preset.id)}
                >
                  <img src={finalScene.image} alt={preset.label} />
                  <span>{preset.label}</span>
                </button>
              ))}
              <button className="new-card">+ 添加镜头</button>
            </div>
          </Panel>
        </section>
        <aside className="stack">
          <Panel title="场景对象列表">
            {hasSceneObjects ? objects.map((object) => (
              <div className={`object-row ${object.id === activeObjectId ? 'is-active' : ''} ${object.visible === false ? 'is-hidden' : ''}`} key={object.id}>
                <input type="checkbox" checked={object.visible !== false} onChange={() => toggleObject(object.id)} />
                <span>{object.label}</span>
                <small>{object.type}</small>
                <button disabled={object.visible === false || object.selectable === false} onClick={() => setActiveObjectId(object.id)}>◎</button>
              </div>
            )) : (
              <div className="empty-state">对象语义未就绪。后端导出 scene_state.json.objects 后，这里才显示对象显示/隐藏与聚焦控制。</div>
            )}
          </Panel>
          <Panel title="最终验收操作">
            <Button className="full-width">提出最终修改</Button>
            <Button variant="primary" className="full-width" onClick={() => onNavigate('delivery')}>确认交付</Button>
            <Button className="full-width">导出 / 下载</Button>
          </Panel>
        </aside>
      </div>
    </>
  );
}
