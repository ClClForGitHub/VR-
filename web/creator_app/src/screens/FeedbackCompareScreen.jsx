import { Button } from '../components/Button.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';

export function FeedbackCompareScreen({ onNavigate, viewModel }) {
  const { concepts, references } = viewModel;
  return (
    <>
      <ScreenHeading title="概念图反馈 / 重生成版本对比" subtitle="左右版本对比，提出修改意见，或拒绝当前方案并重生成" />
      <div className="compare-layout">
        <Panel title="当前版本" action={<span className="pill">V2</span>} className="compare-card">
          <img src={concepts[1].image} alt="当前版本" />
          <Button>设为当前基准</Button>
        </Panel>
        <Panel title="新版本" action={<span className="pill pill-ok">V3 待确认</span>} className="compare-card">
          <img src={concepts[0].image} alt="新版本" />
          <Button>设为当前基准</Button>
        </Panel>
        <Panel title="提出修改反馈" className="feedback-panel">
          <div className="tag-row">
            {['构图布局', '主体设计', '光影氛围', '色彩风格', '细节丰富度'].map((tag) => <Button key={tag} variant="chip">{tag}</Button>)}
          </div>
          <textarea placeholder="例如：希望机械兽更具压迫感，整体氛围更明亮，背景建筑比例更大..." />
          <div className="tag-row">
            {references.map((reference) => <Button key={reference.id} variant="chip">{reference.alias}</Button>)}
          </div>
          <div className="split-actions">
            <Button variant="danger">拒绝当前方案</Button>
            <Button variant="primary" onClick={() => onNavigate('concept-review')}>提交反馈并重生成 →</Button>
          </div>
        </Panel>
      </div>
    </>
  );
}
