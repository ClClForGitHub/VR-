import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Composer } from '../components/Composer.jsx';
import { Button } from '../components/Button.jsx';
import { ReferenceTray } from '../components/ReferenceTray.jsx';

export function IntakeScreen({ viewModel, onStartGeneration }) {
  const { referenceSlots } = viewModel;
  return (
    <>
      <ScreenHeading title="输入创作需求" subtitle="用自然语言描述世界，明确绑定参考图，后台会生成概念候选并在完成后揭幕" />
      <div className="intake-layout">
        <Panel className="chat-panel">
          <div className="chat-message assistant">
            <strong>image23D 助手</strong>
            <p>你好！请描述你想要生成的场景或主体，我将帮你生成精美的 3D 概念图。你也可以上传参考图。</p>
          </div>
          <div className="chat-message user">
            创建一个古老遗迹中的机械巨兽守护者，场景在日落时分，光线穿透破损的拱门，地面有反射水洼，氛围史诗、神秘、宏大。
            <span className="mention">@主体1</span> 和 <span className="mention">@主体2</span> 作为主体参考，<span className="mention">@场景1</span> 作为场景参考。
          </div>
          <Composer referenceSlots={referenceSlots} onSend={() => onStartGeneration?.('concept')} />
          <div className="intake-submit-row">
            <div>
              <strong>后台生成任务</strong>
              <span>提交后显示进度，不再进入独立等待页。</span>
            </div>
            <Button variant="primary" className="big-action" onClick={() => onStartGeneration?.('concept')}>
              开始生成概念图
            </Button>
          </div>
        </Panel>
        <ReferenceTray referenceSlots={referenceSlots} />
      </div>
    </>
  );
}
