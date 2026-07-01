import { Button } from '../components/Button.jsx';
import { GlbViewerShell } from '../components/GlbViewerShell.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';

export function FinalReviewScreen({ onNavigate, viewModel }) {
  const { cameraPresets, sceneObjects } = viewModel;
  const finalScene = viewModel.finalScene;
  return (
    <>
      <ScreenHeading title="最终 Blender 场景验收 / 导演台" subtitle="最终场景合成已完成，请进行镜头检查、构图评审与最终验收" />
      <div className="final-review-layout">
        <aside className="stack">
          <Panel title="资产记忆">
            <img className="wide-thumb" src={finalScene.image} alt={finalScene.title} />
            <Button className="full-width">打开资产记忆库 →</Button>
          </Panel>
          <Panel title="镜头预设">
            <div className="preset-grid">
              {cameraPresets.map((preset) => <Button key={preset.id} variant="chip">{preset.label}</Button>)}
            </div>
          </Panel>
          <Panel title="焦点控制">
            <div className="thumb-strip">
              {sceneObjects.slice(0, 4).map((object) => <button key={object.id}>{object.label}</button>)}
            </div>
          </Panel>
        </aside>
        <section className="stack">
          <GlbViewerShell poster={finalScene.image} title={finalScene.title} />
          <Panel title="镜点时间线">
            <div className="thumb-strip">
              {cameraPresets.map((preset) => <img key={preset.id} src={finalScene.image} alt={preset.label} />)}
              <button className="new-card">+ 添加镜头</button>
            </div>
          </Panel>
        </section>
        <aside className="stack">
          <Panel title="场景对象列表">
            {sceneObjects.map((object) => (
              <div className="object-row" key={object.id}>
                <input type="checkbox" defaultChecked={object.visible} />
                <span>{object.label}</span>
                <small>{object.type}</small>
                <button>◎</button>
              </div>
            ))}
          </Panel>
          <Panel title="最终验收操作">
            <Button className="full-width">提出最终修改</Button>
            <Button variant="primary" className="full-width" onClick={() => onNavigate('delivery')}>确认交付</Button>
            <Button className="full-width">导出 / 下载</Button>
          </Panel>
        </aside>
      </div>
    </>
  );
}
