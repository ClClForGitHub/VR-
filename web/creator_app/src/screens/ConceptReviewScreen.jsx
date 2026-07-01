import { useState } from 'react';
import { AssetCard } from '../components/AssetCard.jsx';
import { AssetMemoryPanel } from '../components/AssetMemoryPanel.jsx';
import { Composer } from '../components/Composer.jsx';
import { HeroStage } from '../components/HeroStage.jsx';
import { Panel } from '../components/Panel.jsx';
import { ReviewDock } from '../components/ReviewDock.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Button } from '../components/Button.jsx';

export function ConceptReviewScreen({ onNavigate, viewModel }) {
  const { concepts, references } = viewModel;
  const [selected, setSelected] = useState(concepts[0].id);
  const current = concepts.find((concept) => concept.id === selected) ?? concepts[0];
  return (
    <>
      <ScreenHeading title="概念图审稿画廊" subtitle="概念图已生成，请确认整体效果并提出修改意见，确认后进入模型生成阶段" />
      <div className="layout-3">
        <Panel title="概念方案" eyebrow="整体 / 主体 / 场景" className="scroll-panel">
          {concepts.map((concept) => (
            <AssetCard key={concept.id} asset={concept} active={concept.id === selected} onClick={() => setSelected(concept.id)} muted={concept.status === '已拒绝'} />
          ))}
          {references.map((reference) => (
            <AssetCard key={reference.id} asset={reference} />
          ))}
        </Panel>
        <section className="stack">
          <HeroStage image={current.image} title={current.title} caption={current.note}>
            <div className="viewer-toolbar">
              <button>1:1</button>
              <button>适应窗口</button>
              <button>下载</button>
              <button>全屏</button>
            </div>
          </HeroStage>
          <div className="review-lower">
            <Composer placeholder="输入你的修改意见，例如：增强天空光照、增加体积光效..." compact />
            <Panel title="快捷建议">
              <div className="tag-row">
                {['增强主光源', '增加体积光', '优化构图', '强化氛围'].map((tag) => <Button key={tag} variant="chip">{tag}</Button>)}
              </div>
            </Panel>
          </div>
        </section>
        <aside className="stack">
          <AssetMemoryPanel viewModel={viewModel} onOpen={() => onNavigate('asset-memory')} />
          <ReviewDock
            negativeLabel="提出修改意见"
            positiveLabel="接受并进入模型生成"
            onNegative={() => onNavigate('feedback-compare')}
            onPositive={() => onNavigate('model-review')}
          />
        </aside>
      </div>
    </>
  );
}
