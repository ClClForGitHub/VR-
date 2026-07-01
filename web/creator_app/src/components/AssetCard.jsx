export function AssetCard({ asset, active = false, onClick, muted = false }) {
  return (
    <article
      className={`asset-card ${active ? 'is-active' : ''} ${muted ? 'is-muted' : ''}`.trim()}
      onClick={onClick}
    >
      <img src={asset.image} alt={asset.title} />
      <div className="asset-card__meta">
        <strong>{asset.title}</strong>
        <span className={`pill ${asset.status === '已拒绝' ? 'pill-danger' : asset.status === '已选用' || asset.status === '当前查看' ? 'pill-ok' : ''}`}>
          {asset.status || asset.role || asset.version}
        </span>
      </div>
    </article>
  );
}
