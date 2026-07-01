import { AssetCard } from '../components/AssetCard.jsx';
import { Button } from '../components/Button.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';

export function AssetMemoryScreen({ viewModel }) {
  const allAssets = viewModel.assetMemory.allAssets;
  const groups = [
    ['概念图', allAssets.filter((asset) => asset.kind === 'overall_concept')],
    ['主体模型', allAssets.filter((asset) => asset.modelType === '主体模型')],
    ['场景模型 / 最终场景', allAssets.filter((asset) => asset.fileFormat?.includes('GLB'))],
  ];
  return (
    <>
      <ScreenHeading title="创作记忆 / 资产库" subtitle="所有已接受、被拒绝、可复用、可归档的生成物都保留在这里" />
      <div className="asset-memory-layout">
        <Panel title="资产筛选" className="memory-sidebar">
          {['全部资产 128', '概念图 42', '主体模型 18', '场景模型 25', '最终场景 12'].map((item) => <Button key={item} className="full-width">{item}</Button>)}
          <hr />
          {['已选用 23', '已拒绝 17', '可复用归档 33'].map((item) => <Button key={item} className="full-width">{item}</Button>)}
        </Panel>
        <Panel title="全部资产" className="asset-gallery-panel">
          <div className="toolbar-row">
            {['全部', '概念图', '主体模型', '场景模型', '最终场景'].map((tab) => <Button key={tab} variant="chip">{tab}</Button>)}
            <span className="spacer" />
            <Button>筛选</Button>
            <Button>创建时间⌄</Button>
          </div>
          {groups.map(([label, items]) => (
            <section key={label} className="asset-group">
              <h3>{label} <small>{items.length}</small></h3>
              <div className="asset-grid">
                {items.map((asset) => <AssetCard key={asset.id} asset={asset} muted={asset.status === '已拒绝'} />)}
                <button className="new-card">+ 生成新资产</button>
              </div>
            </section>
          ))}
        </Panel>
      </div>
    </>
  );
}
