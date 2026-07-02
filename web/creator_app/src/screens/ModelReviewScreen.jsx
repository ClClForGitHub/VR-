import { useMemo, useState } from 'react';
import { Button } from '../components/Button.jsx';
import { FeedbackDrawer } from '../components/FeedbackDrawer.jsx';
import { ModelCompareModal } from '../components/ModelCompareModal.jsx';
import { ModelViewerStage } from '../components/ModelViewerStage.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';

export function ModelReviewScreen({ onNavigate, viewModel }) {
  const { entities, assetVersions, referenceSlots } = viewModel;
  const modelAssets = assetVersions.filter((asset) => ['subject_model', 'scene_model'].includes(asset.asset_kind));
  const modelEntities = entities.filter((entity) => modelAssets.some((asset) => asset.entity_id === entity.entity_id));
  const [selectedEntityId, setSelectedEntityId] = useState(modelEntities[0]?.entity_id);
  const [selectedModelId, setSelectedModelId] = useState(() => modelAssets.find((asset) => asset.entity_id === modelEntities[0]?.entity_id)?.asset_id);
  const [compareOpen, setCompareOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  const selectedEntity = useMemo(
    () => modelEntities.find((entity) => entity.entity_id === selectedEntityId) || modelEntities[0],
    [modelEntities, selectedEntityId],
  );
  const entityModels = modelAssets.filter((asset) => asset.entity_id === selectedEntity?.entity_id);
  const selectedModel = entityModels.find((asset) => asset.asset_id === selectedModelId) || entityModels[0] || modelAssets[0];
  const relatedConcept = assetVersions.find((asset) => (
    asset.asset_kind === 'concept_image'
    && asset.entity_id === selectedModel?.entity_id
    && selectedModel?.source_asset_ids?.includes(asset.asset_id)
  )) || assetVersions.find((asset) => asset.asset_kind === 'concept_image' && asset.entity_id === selectedModel?.entity_id);

  function selectEntity(entityId) {
    setSelectedEntityId(entityId);
    setSelectedModelId(modelAssets.find((asset) => asset.entity_id === entityId)?.asset_id);
  }

  return (
    <>
      <ScreenHeading title="模型验收" subtitle="按主体实体和场景实体检查模型版本，选择左侧版本时中间 viewer 会同步切换" />
      <div className="model-layout model-layout--review">
        <Panel title="模型实体 / 版本" className="scroll-panel model-entity-list model-entity-list--preview">
          {modelEntities.map((entity) => {
            const versions = modelAssets.filter((asset) => asset.entity_id === entity.entity_id);
            const selectedEntityAsset = versions.find((asset) => asset.asset_id === selectedModel?.asset_id) || versions[0];
            return (
              <section key={entity.entity_id} className="model-entity-group model-entity-group--preview">
                <button
                  type="button"
                  className={`model-entity-summary ${entity.entity_id === selectedEntity?.entity_id ? 'is-selected' : ''}`}
                  onClick={() => selectEntity(entity.entity_id)}
                >
                  <span className="model-entity-summary__thumb">
                    {selectedEntityAsset?.image_url ? <img src={selectedEntityAsset.image_url} alt={entity.display_label} /> : entity.display_label}
                  </span>
                  <span className="model-entity-summary__copy">
                    <strong>{entity.display_label}</strong>
                    <small>{entity.resolved_name}</small>
                  </span>
                </button>
                <div className="model-version-card-grid">
                  {versions.map((asset) => (
                    <button
                      key={asset.asset_id}
                      type="button"
                      className={`model-version-card ${asset.asset_id === selectedModel?.asset_id ? 'is-selected-version' : ''}`}
                      onClick={() => {
                        setSelectedEntityId(entity.entity_id);
                        setSelectedModelId(asset.asset_id);
                      }}
                    >
                      {asset.image_url && <img src={asset.image_url} alt={asset.title} />}
                      <span>{asset.version_label} · {statusLabel(asset.status)}</span>
                      <small>{asset.title}</small>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </Panel>
        <section className="model-review-main">
          <ModelViewerStage
            src={selectedModel?.glb_url}
            poster={selectedModel?.image_url}
            title={selectedModel?.title}
            fallbackLabel={`等待 ${selectedEntity?.display_label || '模型'} ${selectedModel?.version_label || ''} GLB 生成`}
          />
          <Panel title={selectedModel?.title || '模型详情'} action={<span className="pill">{selectedModel?.version_label}</span>} className="qa-panel model-detail-panel--below">
            <dl className="metadata-list model-metadata-grid">
              <div><dt>实体</dt><dd>{selectedEntity?.display_label}</dd></div>
              <div><dt>模型类型</dt><dd>{selectedModel?.asset_kind === 'scene_model' ? '场景模型' : '主体模型'}</dd></div>
              <div><dt>版本 ID</dt><dd>{selectedModel?.version_id || selectedModel?.asset_id}</dd></div>
              <div><dt>GLB 状态</dt><dd>{selectedModel?.glb_url ? '已连接' : '等待生成'}</dd></div>
              <div><dt>文件大小</dt><dd>{selectedModel?.size || '未知大小'}</dd></div>
            </dl>
            <div className="model-qa-chip-row">
              {['实体归属', '版本记录', 'GLB 可用性', '来源概念'].map((qa) => (
                <span key={qa} className={`pill ${selectedModel?.glb_url || qa !== 'GLB 可用性' ? 'pill-ok' : ''}`}>
                  {qa} · {selectedModel?.glb_url || qa !== 'GLB 可用性' ? '通过' : '等待'}
                </span>
              ))}
            </div>
          </Panel>
        </section>
        <Panel title="验收动作" eyebrow="Model Review" className="model-review-actions-panel">
          <div className="model-review-actions-panel__summary">
            <span>{selectedEntity?.display_label}</span>
            <strong>{selectedModel?.title || '模型版本'}</strong>
            <small>{selectedModel?.glb_url ? 'GLB 已连接，可以进入组装' : 'GLB 未就绪，当前为预览/占位验收状态'}</small>
          </div>
          <Button className="full-width" onClick={() => setCompareOpen(true)}>对比概念图</Button>
          <Button className="full-width" onClick={() => setFeedbackOpen(true)}>提出修改意见</Button>
          <Button variant="primary" className="full-width" onClick={() => onNavigate('composition')}>验收通过</Button>
        </Panel>
      </div>
      <ModelCompareModal
        open={compareOpen}
        model={selectedModel}
        concept={relatedConcept}
        entity={selectedEntity}
        onClose={() => setCompareOpen(false)}
        onFeedback={() => {
          setCompareOpen(false);
          setFeedbackOpen(true);
        }}
      />
      <FeedbackDrawer
        open={feedbackOpen}
        mode="model"
        entities={entities}
        assetVersions={assetVersions}
        referenceSlots={referenceSlots}
        selectedModel={selectedModel}
        selectedEntity={selectedEntity}
        selectedModelCombination={selectedModelCombination(modelEntities, modelAssets, selectedEntity, selectedModel)}
        onClose={() => setFeedbackOpen(false)}
        onSubmit={() => setFeedbackOpen(false)}
      />
    </>
  );
}

function selectedModelCombination(modelEntities, modelAssets, selectedEntity, selectedModel) {
  const subjectModelByEntity = {};
  const sceneModelByEntity = {};
  modelEntities.forEach((entity) => {
    const currentEntityAsset = entity.entity_id === selectedEntity?.entity_id ? selectedModel : null;
    const asset = currentEntityAsset
      || modelAssets.find((item) => item.entity_id === entity.entity_id && ['selected', 'accepted'].includes(item.status))
      || modelAssets.find((item) => item.entity_id === entity.entity_id);
    if (!asset) return;
    if (entity.entity_type === 'scene') {
      sceneModelByEntity[entity.entity_id] = asset.version_id || asset.asset_id;
    } else {
      subjectModelByEntity[entity.entity_id] = asset.version_id || asset.asset_id;
    }
  });
  return { subjectModelByEntity, sceneModelByEntity };
}

function statusLabel(status) {
  if (status === 'selected') return '当前版本';
  if (status === 'accepted') return '已验收';
  if (status === 'generating') return '生成中';
  if (status === 'failed') return '失败';
  return '候选';
}
