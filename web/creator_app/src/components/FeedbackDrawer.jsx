import { useMemo, useState } from 'react';
import { Button } from './Button.jsx';
import { Composer } from './Composer.jsx';

export function FeedbackDrawer({ open, selection, entities = [], referenceSlots = [], onClose, onRegenerate, onOpenCompare }) {
  const targets = useMemo(() => feedbackTargets(entities), [entities]);
  const [activeTargetId, setActiveTargetId] = useState(targets[0]?.id || 'overall');
  const [feedbackByTarget, setFeedbackByTarget] = useState({});

  if (!open) return null;

  function submit() {
    const feedback_targets = targets
      .map((target) => ({
        target_type: target.target_type,
        entity_id: target.entity_id,
        asset_id: selectedAssetForTarget(selection, target),
        feedback_text: feedbackByTarget[target.id] || '',
        new_reference_artifact_ids: [],
      }))
      .filter((target) => target.feedback_text.trim().length > 0);
    onRegenerate?.({ action_type: 'request_concept_changes', feedback_targets });
  }

  return (
    <aside className="feedback-drawer" role="dialog" aria-modal="true" aria-label="概念反馈">
      <div className="feedback-drawer__scrim" onClick={onClose} />
      <div className="feedback-drawer__panel">
        <header>
          <div>
            <span className="eyebrow">Concept Feedback</span>
            <h2>针对实体提出修改</h2>
          </div>
          <Button variant="icon" onClick={onClose}>×</Button>
        </header>
        <section className="drawer-section">
          <h3>反馈目标</h3>
          <div className="entity-chip-grid">
            {targets.map((target) => (
              <button
                key={target.id}
                type="button"
                className={target.id === activeTargetId ? 'is-selected' : ''}
                onClick={() => setActiveTargetId(target.id)}
              >
                <strong>{target.label}</strong>
                {target.name && <span>{target.name}</span>}
              </button>
            ))}
          </div>
        </section>
        <section className="drawer-section">
          <h3>{targets.find((target) => target.id === activeTargetId)?.label || '反馈'}哪里不好？</h3>
          <textarea
            value={feedbackByTarget[activeTargetId] || ''}
            placeholder="用自然语言描述问题，例如：主体1头部太小，机械感不够强。"
            onChange={(event) => setFeedbackByTarget((current) => ({ ...current, [activeTargetId]: event.target.value }))}
          />
        </section>
        <section className="drawer-section">
          <h3>上传新参考 / @ 引用</h3>
          <Composer
            compact
            referenceSlots={referenceSlots}
            placeholder="补充说明或插入 @主体1 / @场景1..."
            onSend={({ message }) => setFeedbackByTarget((current) => ({
              ...current,
              [activeTargetId]: `${current[activeTargetId] || ''}${current[activeTargetId] ? '\n' : ''}${message}`,
            }))}
          />
        </section>
        <div className="split-actions">
          <Button onClick={onOpenCompare}>查看已选组合</Button>
          <Button variant="primary" onClick={submit}>发送反馈并重生成</Button>
        </div>
      </div>
    </aside>
  );
}

function feedbackTargets(entities) {
  return entities
    .filter((entity) => ['overall', 'subject', 'scene'].includes(entity.entity_type))
    .map((entity) => ({
      id: entity.entity_id,
      label: entity.display_label,
      name: entity.resolved_name,
      target_type: entity.entity_type,
      entity_id: entity.entity_id === 'overall' ? undefined : entity.entity_id,
    }));
}

function selectedAssetForTarget(selection, target) {
  if (!selection) return undefined;
  if (target.target_type === 'overall') return selection.overall_concept_asset_id;
  if (target.target_type === 'subject') return selection.subject_concept_asset_ids?.[target.entity_id];
  if (target.target_type === 'scene') return selection.scene_concept_asset_ids?.[target.entity_id];
  return undefined;
}
