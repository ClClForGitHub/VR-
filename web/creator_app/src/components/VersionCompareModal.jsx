import { Button } from './Button.jsx';

export function VersionCompareModal({ open, concepts = [], entities = [], assetVersions = [], selection, onClose }) {
  if (!open) return null;
  const selectedAssets = selectedCombinationAssets(selection, assetVersions, concepts);

  return (
    <div className="version-modal" role="dialog" aria-modal="true" aria-label="已选组合确认">
      <div className="version-modal__panel">
        <header>
          <div>
            <span className="eyebrow">Selected Combination</span>
            <h2>已选组合确认</h2>
          </div>
          <Button variant="icon" onClick={onClose}>×</Button>
        </header>
        <div className="version-compare-grid">
          {selectedAssets.map(({ entity, asset }) => (
            <article key={`${entity.entity_id}-${asset?.asset_id}`} className="version-card">
              {asset?.image_url && <img src={asset.image_url} alt={asset.title} />}
              <div>
                <strong>{entity.display_label}</strong>
                <span className="pill">{asset?.version_label || '未选择'}</span>
              </div>
              <p>{asset?.title || entity.resolved_name || '等待选择'}</p>
            </article>
          ))}
        </div>
        <div className="split-actions">
          <Button onClick={onClose}>返回修改</Button>
          <Button variant="primary" onClick={onClose}>确认组合</Button>
        </div>
      </div>
    </div>
  );
}

function selectedCombinationAssets(selection, assetVersions, concepts) {
  const conceptAssets = assetVersions.length > 0
    ? assetVersions.filter((asset) => asset.asset_kind === 'concept_image')
    : concepts.map((concept) => ({
      asset_id: concept.asset_id || concept.id,
      entity_id: concept.entity_id,
      image_url: concept.image,
      title: concept.title,
      version_label: concept.version_label,
    }));
  const ids = [
    ['overall', selection?.overall_concept_asset_id],
    ...Object.entries(selection?.subject_concept_asset_ids || {}),
    ...Object.entries(selection?.scene_concept_asset_ids || {}),
  ];
  return ids.map(([entityId, assetId]) => ({
    entity: {
      entity_id: entityId,
      display_label: entityId === 'overall' ? '整体图' : entityId.replace('subject_', '主体 ').replace('scene_', '场景 '),
    },
    asset: conceptAssets.find((item) => item.asset_id === assetId),
  })).filter((item) => item.asset);
}
