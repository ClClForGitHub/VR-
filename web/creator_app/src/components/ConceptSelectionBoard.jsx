import { useEffect, useMemo, useState } from 'react';
import { Button } from './Button.jsx';
import { HeroStage } from './HeroStage.jsx';
import { Panel } from './Panel.jsx';

export function ConceptSelectionBoard({ entities = [], assetVersions = [], approvedSelection, onApprove, onFeedback, onConfirmSelection }) {
  const conceptVersions = assetVersions.filter((asset) => asset.asset_kind === 'concept_image');
  const conceptEntities = useMemo(() => conceptEntityList(entities, conceptVersions), [conceptVersions, entities]);
  const [activeEntityId, setActiveEntityId] = useState('overall');
  const [selection, setSelection] = useState(() => initialSelection(conceptEntities, conceptVersions, approvedSelection));
  const conceptEntitySignature = conceptEntities.map((entity) => entity.entity_id).join('|');
  const conceptVersionSignature = conceptVersions.map((asset) => `${asset.asset_id}:${asset.entity_id}:${asset.status}`).join('|');
  const approvedSignature = JSON.stringify(approvedSelection || {});
  const activeEntity = conceptEntities.find((entity) => entity.entity_id === activeEntityId) || conceptEntities[0];
  const activeVersions = conceptVersions.filter((asset) => asset.entity_id === activeEntity?.entity_id);
  const activeAsset = activeVersions.find((asset) => asset.asset_id === selection[activeEntity?.entity_id]) || activeVersions[0] || conceptVersions[0];
  const approvedPayload = selectionToApproved(selection, conceptVersions);

  useEffect(() => {
    setSelection(initialSelection(conceptEntities, conceptVersions, approvedSelection));
    setActiveEntityId((current) => (
      conceptEntities.some((entity) => entity.entity_id === current)
        ? current
        : conceptEntities[0]?.entity_id || 'overall'
    ));
  }, [conceptEntitySignature, conceptVersionSignature, approvedSignature]);

  function selectAsset(asset) {
    setSelection((current) => ({ ...current, [asset.entity_id]: asset.asset_id }));
  }

  return (
    <div className="concept-review-layout">
      <Panel title="概念实体" eyebrow="Overall / Subjects / Scene" className="concept-selection-panel">
        <EntityNav
          title="整体图"
          entities={conceptEntities.filter((entity) => entity.entity_type === 'overall')}
          activeEntityId={activeEntityId}
          onSelect={setActiveEntityId}
        />
        <EntityNav
          title="主体图"
          entities={conceptEntities.filter((entity) => entity.entity_type === 'subject')}
          activeEntityId={activeEntityId}
          onSelect={setActiveEntityId}
        />
        <EntityNav
          title="场景图"
          entities={conceptEntities.filter((entity) => entity.entity_type === 'scene')}
          activeEntityId={activeEntityId}
          onSelect={setActiveEntityId}
        />
        <section className="concept-group">
          <header>
            <h3>{activeEntity?.display_label || '概念图'}版本</h3>
            <p>{activeEntity?.resolved_name || '选择当前实体的概念版本'}</p>
          </header>
          <div className="concept-group__grid">
            {activeVersions.map((asset) => (
              <button
                type="button"
                key={asset.asset_id}
                className={`concept-option ${selection[asset.entity_id] === asset.asset_id ? 'is-selected' : ''} ${asset.status === 'rejected' ? 'is-muted' : ''}`}
                onClick={() => selectAsset(asset)}
              >
                <img src={asset.image_url} alt={asset.title} />
                <span>{asset.version_label} · {asset.title}</span>
                <small>{statusLabel(asset.status)}</small>
              </button>
            ))}
          </div>
        </section>
      </Panel>

      <HeroStage image={activeAsset?.image_url} title={activeAsset?.title} caption={activeAsset?.note} className="concept-hero">
        <div className="concept-hero__badge">
          <span className="pill pill-ok">{activeEntity?.display_label}</span>
          <strong>{activeAsset?.version_label} · {activeAsset?.title}</strong>
        </div>
      </HeroStage>

      <aside className="concept-review-sidepanel">
        <Panel title="当前已选组合" className="selection-summary-panel concept-side-summary">
          {conceptEntities.map((entity) => {
            const asset = conceptVersions.find((item) => item.asset_id === selection[entity.entity_id]);
            return (
              <article key={entity.entity_id} className="selection-summary-row">
                <span>{entity.display_label}</span>
                <strong>{asset ? `${asset.version_label} · ${asset.title}` : '未选择'}</strong>
                <small>{asset?.note || entity.resolved_name || '等待选择'}</small>
              </article>
            );
          })}
        </Panel>

        <Panel title="审稿动作" eyebrow="Review Actions" className="concept-action-panel">
          <p className="panel-copy">
            接受后会按“整体 + 多主体 + 场景”的混选组合提交模型生成。
          </p>
          <Button className="full-width" onClick={() => onFeedback?.(approvedPayload)}>提出修改意见</Button>
          <Button className="full-width" onClick={() => onConfirmSelection?.(approvedPayload)}>查看已选组合</Button>
          <Button variant="primary" className="full-width big-action" onClick={() => onApprove?.(approvedPayload)}>
            接受组合，生成模型
          </Button>
        </Panel>
      </aside>
    </div>
  );
}

function EntityNav({ title, entities, activeEntityId, onSelect }) {
  if (entities.length === 0) return null;
  return (
    <section className="entity-nav-section">
      <h3>{title}</h3>
      <div className="entity-chip-grid">
        {entities.map((entity) => (
          <button
            type="button"
            key={entity.entity_id}
            className={entity.entity_id === activeEntityId ? 'is-selected' : ''}
            onClick={() => onSelect(entity.entity_id)}
          >
            <strong>{entity.display_label}</strong>
            {entity.resolved_name && <span>{entity.resolved_name}</span>}
          </button>
        ))}
      </div>
    </section>
  );
}

function conceptEntityList(entities, conceptVersions) {
  return entities.filter((entity) => (
    entity.entity_type === 'overall'
    || conceptVersions.some((asset) => asset.entity_id === entity.entity_id)
  ));
}

function initialSelection(entities, conceptVersions, approvedSelection) {
  const next = {};
  entities.forEach((entity) => {
    if (entity.entity_type === 'overall') {
      next[entity.entity_id] = approvedSelection?.overall_concept_asset_id;
    } else if (entity.entity_type === 'subject') {
      next[entity.entity_id] = approvedSelection?.subject_concept_asset_ids?.[entity.entity_id];
    } else if (entity.entity_type === 'scene') {
      next[entity.entity_id] = approvedSelection?.scene_concept_asset_ids?.[entity.entity_id];
    }
    if (!next[entity.entity_id]) {
      next[entity.entity_id] = conceptVersions.find((asset) => asset.entity_id === entity.entity_id && ['selected', 'accepted'].includes(asset.status))?.asset_id
        || conceptVersions.find((asset) => asset.entity_id === entity.entity_id)?.asset_id;
    }
  });
  return next;
}

function selectionToApproved(selection, conceptVersions) {
  const subject_concept_asset_ids = {};
  const scene_concept_asset_ids = {};
  Object.entries(selection).forEach(([entityId, assetId]) => {
    const asset = conceptVersions.find((item) => item.asset_id === assetId);
    if (!asset) return;
    if (entityId === 'overall') return;
    if (entityId.startsWith('subject_')) subject_concept_asset_ids[entityId] = assetId;
    if (entityId.startsWith('scene_')) scene_concept_asset_ids[entityId] = assetId;
  });
  return {
    overall_concept_asset_id: selection.overall,
    subject_concept_asset_ids,
    scene_concept_asset_ids,
  };
}

function statusLabel(status) {
  if (status === 'selected') return '已选';
  if (status === 'accepted') return '已验收';
  if (status === 'rejected') return '已拒绝';
  if (status === 'generating') return '生成中';
  return '候选';
}
