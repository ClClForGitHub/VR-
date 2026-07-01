import { Panel } from './Panel.jsx';
import { Button } from './Button.jsx';

export function AssetMemoryPanel({ viewModel, onOpen }) {
  const concepts = viewModel.assetMemory.concepts;
  const references = viewModel.assetMemory.references;
  return (
    <Panel title="创作记忆" eyebrow="Asset Memory" action={<Button variant="icon" onClick={onOpen}>↗</Button>} className="memory-panel">
      <MemorySection title="本次方案迭代" items={concepts.slice(0, 3)} />
      <MemorySection title="参考来源" items={references} />
      <MemorySection title="已排除方案" items={concepts.filter((item) => item.status === '已拒绝')} muted />
      <Button className="full-width" onClick={onOpen}>查看全部记忆 →</Button>
    </Panel>
  );
}

function MemorySection({ title, items, muted = false }) {
  return (
    <div className="memory-section">
      <h3>{title}</h3>
      <div className="memory-grid">
        {items.map((item) => (
          <figure key={item.id} className={muted ? 'is-muted' : ''}>
            <img src={item.image} alt={item.title} />
            <figcaption>{item.title}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}
