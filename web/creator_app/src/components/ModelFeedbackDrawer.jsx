import { useState } from 'react';
import { Button } from './Button.jsx';
import { Composer } from './Composer.jsx';

export function ModelFeedbackDrawer({ open, model, entity, referenceSlots = [], onClose, onSubmit }) {
  const [feedbackText, setFeedbackText] = useState('');
  if (!open) return null;
  return (
    <aside className="feedback-drawer" role="dialog" aria-modal="true" aria-label="模型反馈">
      <div className="feedback-drawer__scrim" onClick={onClose} />
      <div className="feedback-drawer__panel">
        <header>
          <div>
            <span className="eyebrow">Model Feedback</span>
            <h2>{entity?.display_label || '模型'} 修改意见</h2>
          </div>
          <Button variant="icon" onClick={onClose}>×</Button>
        </header>
        <section className="drawer-section">
          <h3>反馈目标</h3>
          <div className="drawer-selection-list">
            <div>
              <span>{entity?.resolved_name || entity?.display_label}</span>
              <strong>{model?.version_label} · {model?.title}</strong>
            </div>
          </div>
        </section>
        <textarea
          value={feedbackText}
          placeholder="例如：主体1模型头部比例再大一点，材质金属感更强。"
          onChange={(event) => setFeedbackText(event.target.value)}
        />
        <Composer
          compact
          referenceSlots={referenceSlots}
          placeholder="上传新参考或插入 @主体1 / @场景1..."
          onSend={({ message }) => setFeedbackText((current) => `${current}${current ? '\n' : ''}${message}`)}
        />
        <Button
          variant="primary"
          onClick={() => onSubmit?.({
            target_type: model?.asset_kind,
            entity_id: model?.entity_id,
            version_id: model?.version_id || model?.asset_id,
            asset_id: model?.asset_id,
            feedback_text: feedbackText,
            new_reference_artifact_ids: [],
          })}
        >
          提交反馈并重生成模型
        </Button>
      </div>
    </aside>
  );
}
