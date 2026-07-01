import { useState } from 'react';
import { AssetCard } from '../components/AssetCard.jsx';
import { Button } from '../components/Button.jsx';
import { GlbViewerShell } from '../components/GlbViewerShell.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';

export function ModelReviewScreen({ onNavigate, viewModel }) {
  const { concepts, subjects } = viewModel;
  const [selected, setSelected] = useState(subjects[0].id);
  const model = subjects.find((item) => item.id === selected) ?? subjects[0];
  return (
    <>
      <ScreenHeading title="主体/场景模型验收（3D 预览）" subtitle="检查模型细节、结构与贴图质量，确认是否符合概念与技术要求" />
      <div className="model-layout">
        <Panel title="主体模型" className="scroll-panel">
          {subjects.map((subject) => (
            <AssetCard key={subject.id} asset={subject} active={subject.id === selected} onClick={() => setSelected(subject.id)} />
          ))}
          <button className="new-card">+ 生成新主体模型</button>
        </Panel>
        <section className="stack">
          <GlbViewerShell poster={model.image} title={model.title} />
          <Panel title="概念图与模型对比">
            <div className="thumb-strip">
              {[...concepts.slice(0, 3), ...subjects].map((item) => <img key={item.id} src={item.image} alt={item.title} />)}
            </div>
          </Panel>
        </section>
        <Panel title={model.title} action={<span className="pill">{model.version}</span>} className="qa-panel">
          <dl className="metadata-list">
            <div><dt>模型类型</dt><dd>{model.modelType}</dd></div>
            <div><dt>文件格式</dt><dd>{model.fileFormat}</dd></div>
            <div><dt>文件大小</dt><dd>{model.size}</dd></div>
          </dl>
          <h3>模型质量检查</h3>
          {model.qa.map((qa) => <div key={qa} className="qa-row"><span>{qa}</span><span className="pill pill-ok">通过</span></div>)}
          <Button variant="primary" className="full-width" onClick={() => onNavigate('composition')}>验收通过</Button>
          <Button variant="danger" className="full-width">提出修改意见</Button>
          <Button className="full-width" onClick={() => onNavigate('asset-memory')}>切换到其他模型</Button>
        </Panel>
      </div>
    </>
  );
}
