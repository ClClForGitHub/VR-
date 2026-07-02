import { Button } from '../components/Button.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';

export function DeliveryScreen({ viewModel }) {
  const { deliveryFiles } = viewModel;
  const finalScene = viewModel.finalScene || {};
  return (
    <>
      <ScreenHeading title="交付完成" subtitle="预览、文件包、质检和版本信息集中在同一工作面，不留空白交付栏" />
      <div className="delivery-layout delivery-layout--dense">
        <section className="stack">
          <Panel title="最终预览" action={<span className="pill pill-ok">已批准 V1.3</span>} className="delivery-preview-panel">
            <img className="delivery-preview" src={finalScene.image} alt={finalScene.title || '最终场景预览'} />
            <div className="metadata-cards">
              {['场景：古老遗迹的回响', '主体：机械灵兽 · 霜牙', '预览：3840×2160', '资产：GLB + BLEND'].map((item) => <span key={item}>{item}</span>)}
            </div>
          </Panel>
          <Panel title="质量检查">
            {['模型完整性', '材质贴图', '场景结构', '文件规范', '可预览性'].map((item) => (
              <div key={item} className="qa-row"><span>{item}</span><span className="pill pill-ok">通过</span></div>
            ))}
          </Panel>
        </section>
        <section className="stack">
          <Panel title="交付内容包" eyebrow={`${deliveryFiles.length} 项文件，已打包并通过校验`}>
            <div className="delivery-file-grid">
              {deliveryFiles.map((file) => (
                <article key={file.id} className="delivery-file-card">
                  <div className="file-icon">{file.id.toUpperCase().slice(0, 3)}</div>
                  <strong>{file.label}</strong>
                  <span>{file.type}</span>
                  <small>{file.size}</small>
                  {file.url && <a className="file-link" href={file.url}>打开</a>}
                </article>
              ))}
            </div>
            <Button variant="primary" className="full-width big-action">下载全部文件（ZIP）</Button>
          </Panel>
          <Panel title="版本历史">
            {['概念组合 v3 / 主体1 v3 / 主体2 v1 / 场景1 v3', '模型验收：主体1 v2，主体2 v1，场景1 v1', '导演台：等待 scene_state 对象语义后开放对象级编辑'].map((item) => (
              <div key={item} className="qa-row"><span>{item}</span><span className="pill">记录</span></div>
            ))}
          </Panel>
        </section>
      </div>
    </>
  );
}
