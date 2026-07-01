import { useMemo, useState } from 'react';
import { Button } from '../components/Button.jsx';
import { ModelViewerStage } from '../components/ModelViewerStage.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Composer } from '../components/Composer.jsx';

export function CompositionScreen({ viewModel, onStartGeneration }) {
  const { assetVersions = [], entities = [], referenceSlots = [] } = viewModel;
  const modelAssets = assetVersions.filter((asset) => ['subject_model', 'scene_model'].includes(asset.asset_kind));
  const finalSceneAsset = assetVersions.find((asset) => asset.asset_kind === 'final_scene');
  const finalScene = viewModel.finalScene || finalSceneAsset || {};
  const compositionEntities = useMemo(
    () => entities.filter((entity) => modelAssets.some((asset) => asset.entity_id === entity.entity_id)),
    [entities, modelAssets],
  );
  const [selection, setSelection] = useState(() => initialModelSelection(compositionEntities, modelAssets));

  const subjectEntities = compositionEntities.filter((entity) => entity.entity_type === 'subject');
  const sceneEntities = compositionEntities.filter((entity) => entity.entity_type === 'scene');
  const selectedAssets = compositionEntities.map((entity) => ({
    entity,
    asset: modelAssets.find((asset) => asset.asset_id === selection[entity.entity_id])
      || modelAssets.find((asset) => asset.entity_id === entity.entity_id),
  })).filter((item) => item.asset);

  function selectVersion(entityId, assetId) {
    setSelection((current) => ({ ...current, [entityId]: assetId }));
  }

  function submitAssembly() {
    onStartGeneration?.('assembly', {
      selected_asset_versions: selectedAssets.map(({ entity, asset }) => ({
        entity_id: entity.entity_id,
        version_id: asset.version_id || asset.asset_id,
        asset_id: asset.asset_id,
      })),
    });
  }

  return (
    <>
      <ScreenHeading title="自由组合与场景编排" subtitle="保留导演台能力，但所有选择都按 entity_id / version_id 记录，不混淆主体实体和模型版本" />
      <div className="composition-layout">
        <aside className="stack">
          <Panel title="主体模型版本">
            <EntityVersionList
              entities={subjectEntities}
              modelAssets={modelAssets}
              selection={selection}
              onSelect={selectVersion}
            />
          </Panel>
          <Panel title="场景模型版本">
            <EntityVersionList
              entities={sceneEntities}
              modelAssets={modelAssets}
              selection={selection}
              onSelect={selectVersion}
            />
          </Panel>
        </aside>
        <section className="stack">
          <ModelViewerStage
            src={finalScene.viewerSceneUrl || finalScene.glb_url || finalScene.url}
            poster={finalScene.image || finalScene.image_url}
            title={finalScene.title || '组合预览'}
            fallbackLabel="等待组合 GLB 生成"
          />
          <Composer
            referenceSlots={referenceSlots}
            placeholder="描述摆放调整，例如：@主体1 靠近镜头，@场景1 增强水面反光..."
          />
        </section>
        <Panel title="组合参数" className="control-panel">
          {selectedAssets.length > 0 ? selectedAssets.map(({ entity, asset }, index) => (
            <div className="control-group" key={`${entity.entity_id}-${asset.asset_id}`}>
              <h3>{entity.display_label}</h3>
              <small className="entity-version-line">
                entity_id: {entity.entity_id} · version_id: {asset.version_id || asset.asset_id}
              </small>
              <label>位置 X <input defaultValue={index ? '2.35' : '-3.52'} /></label>
              <label>旋转 Y <input defaultValue={index ? '12°' : '-18°'} /></label>
              <label>缩放 <input defaultValue="1.00" /></label>
            </div>
          )) : (
            <div className="empty-state">等待模型验收后选择主体和场景版本。</div>
          )}
          <Button>保存为草稿</Button>
          <Button variant="primary" className="full-width" onClick={submitAssembly}>确认组合，进入最终生成</Button>
        </Panel>
      </div>
    </>
  );
}

function EntityVersionList({ entities, modelAssets, selection, onSelect }) {
  if (entities.length === 0) return <div className="empty-state">暂无可选模型版本</div>;
  return (
    <div className="entity-version-list">
      {entities.map((entity) => {
        const versions = modelAssets.filter((asset) => asset.entity_id === entity.entity_id);
        return (
          <section key={entity.entity_id} className="entity-version-group">
            <header>
              <strong>{entity.display_label}</strong>
              <span>{entity.resolved_name}</span>
            </header>
            <div>
              {versions.map((asset) => (
                <button
                  type="button"
                  key={asset.asset_id}
                  className={selection[entity.entity_id] === asset.asset_id ? 'is-selected' : ''}
                  onClick={() => onSelect(entity.entity_id, asset.asset_id)}
                >
                  <span>{asset.version_label}</span>
                  <small>{asset.version_id || asset.asset_id}</small>
                </button>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function initialModelSelection(entities, modelAssets) {
  const next = {};
  entities.forEach((entity) => {
    const selected = modelAssets.find((asset) => asset.entity_id === entity.entity_id && ['selected', 'accepted'].includes(asset.status));
    const first = modelAssets.find((asset) => asset.entity_id === entity.entity_id);
    if (selected || first) next[entity.entity_id] = (selected || first).asset_id;
  });
  return next;
}
