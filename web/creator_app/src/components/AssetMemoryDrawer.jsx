import { Button } from './Button.jsx';
import { AssetCard } from './AssetCard.jsx';

export function AssetMemoryDrawer({ open, viewModel, onClose }) {
  if (!open) return null;
  const assets = viewModel.assetMemory?.allAssets || [];
  const concepts = viewModel.assetMemory?.concepts || [];
  const references = viewModel.assetMemory?.references || [];
  const groups = [
    ['本次概念', concepts.slice(0, 6)],
    ['参考来源', references],
    ['可复用资产', assets.filter((asset) => asset.fileFormat || asset.modelType).slice(0, 6)],
  ];

  return (
    <aside className="asset-memory-drawer" role="dialog" aria-modal="true" aria-label="资产记忆">
      <div className="asset-memory-drawer__scrim" onClick={onClose} />
      <div className="asset-memory-drawer__panel">
        <header>
          <div>
            <span className="eyebrow">Asset Memory</span>
            <h2>创作记忆</h2>
          </div>
          <Button variant="icon" onClick={onClose}>×</Button>
        </header>
        {groups.map(([title, items]) => (
          <section key={title} className="asset-memory-drawer__section">
            <h3>{title}</h3>
            <div className="asset-memory-drawer__grid">
              {items.map((asset) => (
                <AssetCard key={asset.id || asset.asset_id} asset={asset} muted={asset.status === '已拒绝'} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </aside>
  );
}
