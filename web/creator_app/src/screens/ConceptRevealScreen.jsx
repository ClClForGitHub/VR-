import { AssetMemoryPanel } from '../components/AssetMemoryPanel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Button } from '../components/Button.jsx';

export function ConceptRevealScreen({ onNavigate, viewModel }) {
  const hero = viewModel.concepts[0];
  return (
    <>
      <ScreenHeading title="概念图生成完成" subtitle="整体概念图揭幕成功，已为你生成高清视觉方案" />
      <div className="reveal-layout">
        <section className="reveal-stage">
          <div className="reveal-ring" />
          <img src={hero.image} alt={hero.title} />
          <p>“ {hero.note} ”</p>
        </section>
        <AssetMemoryPanel viewModel={viewModel} onOpen={() => onNavigate('asset-memory')} />
      </div>
      <div className="floating-actions">
        <Button>跳过动画</Button>
        <Button variant="primary" onClick={() => onNavigate('concept-review')}>
          进入概念图审阅 →
        </Button>
      </div>
    </>
  );
}
