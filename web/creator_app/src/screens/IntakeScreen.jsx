import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Composer } from '../components/Composer.jsx';
import { Button } from '../components/Button.jsx';

export function IntakeScreen({ onNavigate, viewModel }) {
  const { references } = viewModel;
  return (
    <>
      <ScreenHeading title="聊天输入与参考图绑定" subtitle="用自然语言描述你的世界，上传参考图，智能理解你的创作意图" />
      <div className="layout-2">
        <Panel className="chat-panel">
          <div className="chat-message assistant">
            <strong>image23D 助手</strong>
            <p>你好！请描述你想要生成的场景或主体，我将帮你生成精美的 3D 概念图。你也可以上传参考图。</p>
          </div>
          <div className="chat-message user">
            创建一个古老遗迹中的机械巨兽守护者，场景在日落时分，光线穿透破损的拱门，地面有反射水洼，氛围史诗、神秘、宏大。
            <span className="mention">@图片1</span> 作为主体参考，<span className="mention">@图片2</span> 作为场景参考。
          </div>
          <section className="reference-binding">
            <h2>参考图绑定 <small>（{references.length}/6）</small></h2>
            <div className="reference-grid">
              {references.map((item) => (
                <article key={item.id} className="reference-card">
                  <img src={item.image} alt={item.title} />
                  <div>
                    <strong>{item.alias} · {item.title}</strong>
                    <span className="pill">{item.role}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
          <Composer />
        </Panel>
        <aside className="stack">
          <Panel title="已绑定参考图">
            <div className="binding-orb">∞</div>
            <div className="center-copy">
              <h3>主体参考 {references.filter((item) => item.bindingRole === 'subject').length || 1} 张</h3>
              <h3>场景参考 {references.filter((item) => item.bindingRole === 'scene').length || 1} 张</h3>
              <Button>管理参考图</Button>
            </div>
          </Panel>
          <Button variant="primary" className="big-action" onClick={() => onNavigate('reveal')}>
            进入概念确认 →
          </Button>
        </aside>
      </div>
    </>
  );
}
