import { Button } from '../components/Button.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';

export function DeliveryScreen({ viewModel }) {
  const { deliveryFiles } = viewModel;
  const finalScene = viewModel.finalScene;
  return (
    <>
      <ScreenHeading title="交付完成" subtitle="项目已成功导出，感谢选择 image23D" />
      <div className="delivery-layout">
        <Panel title="最终场景预览" action={<span className="pill pill-ok">已批准版本 V1.3</span>}>
          <img className="delivery-preview" src={finalScene.image} alt={finalScene.title} />
          <div className="metadata-cards">
            {['场景名称：古老遗迹的回响', '主体模型：机械灵兽 · 霜牙', '分辨率：3840×2160', '多边形：12.8M'].map((item) => <span key={item}>{item}</span>)}
          </div>
        </Panel>
        <Panel title="交付内容包" eyebrow="共 6 项，已打包并通过校验">
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
          <Button variant="primary" className="full-width big-action">下载全部文件（ZIP 压缩包）</Button>
        </Panel>
        <Panel title="交付概览">
          <div className="score-ring">100</div>
          {['模型完整性', '材质贴图', '场景结构', '文件规范', '可预览性'].map((item) => <div key={item} className="qa-row"><span>{item}</span><span className="pill pill-ok">通过</span></div>)}
        </Panel>
      </div>
    </>
  );
}
