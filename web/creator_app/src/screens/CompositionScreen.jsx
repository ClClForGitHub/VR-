import { Button } from '../components/Button.jsx';
import { GlbViewerShell } from '../components/GlbViewerShell.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Composer } from '../components/Composer.jsx';

export function CompositionScreen({ onNavigate, viewModel }) {
  const { subjects, sceneAssets } = viewModel;
  return (
    <>
      <ScreenHeading title="自由组合与场景编排（预览）" subtitle="从资产库选择主体与场景，自由摆放与调整，预览最终构图" />
      <div className="composition-layout">
        <aside className="stack">
          <Panel title="主体模型" action={<Button>+ 添加主体</Button>}>
            {subjects.map((subject) => (
              <article key={subject.id} className="selected-asset-row">
                <img src={subject.image} alt={subject.title} />
                <div><strong>{subject.title}</strong><span>{subject.version}</span></div>
                <Button variant="chip">✓</Button>
              </article>
            ))}
          </Panel>
          <Panel title="场景选择" action={<Button>更换场景</Button>}>
            <img className="wide-thumb" src={sceneAssets[0].image} alt={sceneAssets[0].title} />
            <Button className="full-width">添加环境光 / 氛围</Button>
          </Panel>
        </aside>
        <section className="stack">
          <GlbViewerShell poster={(viewModel.finalScene || sceneAssets[1] || sceneAssets[0]).image} title="组合预览" />
          <Composer placeholder="描述你想要的调整，例如：让机甲更靠近镜头，灵兽向左移动一点..." />
        </section>
        <Panel title="组合与调整" className="control-panel">
          {subjects.map((subject, index) => (
            <div className="control-group" key={subject.id}>
              <h3>{subject.title}</h3>
              <label>位置 X <input defaultValue={index ? '2.35' : '-3.52'} /></label>
              <label>旋转 Y <input defaultValue={index ? '12°' : '-18°'} /></label>
              <label>缩放 <input defaultValue="1.00" /></label>
            </div>
          ))}
          <Button>保存为草稿</Button>
          <Button variant="primary" className="full-width" onClick={() => onNavigate('final-review')}>确认组合，进入最终生成 →</Button>
        </Panel>
      </div>
    </>
  );
}
