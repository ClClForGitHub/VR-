import { useMemo, useRef, useState } from 'react';
import { Button } from './Button.jsx';
import {
  buildConceptFeedbackPayload,
  buildFeedbackMentionOptions,
  buildModelFeedbackPayload,
  MentionKind,
} from '../api/contracts.js';

export function FeedbackDrawer({
  open,
  mode = 'concept',
  selection,
  selectedModelCombination,
  selectedModel,
  selectedEntity,
  entities = [],
  assetVersions = [],
  referenceSlots = [],
  onClose,
  onSubmit,
  onRegenerate,
  onOpenCompare,
}) {
  const [feedbackText, setFeedbackText] = useState('');
  const [newReferenceOptions, setNewReferenceOptions] = useState([]);
  const textareaRef = useRef(null);
  const baseMentionOptions = useMemo(() => buildFeedbackMentionOptions({
    mode,
    entities,
    assetVersions,
    referenceSlots,
    selection,
    selectedModel,
    selectedEntity,
  }), [assetVersions, entities, mode, referenceSlots, selectedEntity, selectedModel, selection]);
  const mentionOptions = [...baseMentionOptions, ...newReferenceOptions];
  const title = mode === 'model' ? '模型修改意见' : '概念修改意见';
  const submitLabel = mode === 'model' ? '提交模型反馈' : '发送反馈并重生成';

  if (!open) return null;

  function insertToken(token) {
    const textarea = textareaRef.current;
    if (!textarea) {
      setFeedbackText((current) => `${current}${current ? ' ' : ''}${token} `);
      return;
    }
    const start = textarea.selectionStart ?? feedbackText.length;
    const end = textarea.selectionEnd ?? feedbackText.length;
    const next = `${feedbackText.slice(0, start)}${token} ${feedbackText.slice(end)}`;
    setFeedbackText(next);
    window.requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(start + token.length + 1, start + token.length + 1);
    });
  }

  function addReferenceUpload() {
    const nextIndex = referenceSlots.filter((slot) => slot.status === 'uploaded').length + newReferenceOptions.length + 1;
    const token = `@参考图${nextIndex}`;
    const option = {
      token,
      kind: MentionKind.REFERENCE_IMAGE,
      referenceId: `draft_feedback_ref_${nextIndex}`,
      displayLabel: `${token} · 新上传参考`,
    };
    setNewReferenceOptions((current) => [...current, option]);
    insertToken(token);
  }

  function submit() {
    const payload = mode === 'model'
      ? buildModelFeedbackPayload({
        feedbackText,
        mentionOptions,
        selectedModelCombination,
        newReferenceUploadIds: newReferenceOptions.map((option) => option.referenceId),
      })
      : buildConceptFeedbackPayload({
        feedbackText,
        mentionOptions,
        selectedConceptCombination: selection,
        newReferenceUploadIds: newReferenceOptions.map((option) => option.referenceId),
      });
    onSubmit?.(payload);
    onRegenerate?.(payload);
  }

  return (
    <aside className="feedback-drawer" role="dialog" aria-modal="true" aria-label={title}>
      <div className="feedback-drawer__scrim" onClick={onClose} />
      <div className="feedback-drawer__panel feedback-drawer__panel--unified">
        <header>
          <div>
            <span className="eyebrow">{mode === 'model' ? 'Model Feedback' : 'Concept Feedback'}</span>
            <h2>{title}</h2>
          </div>
          <Button variant="icon" onClick={onClose}>×</Button>
        </header>
        <section className="drawer-section">
          <h3>@ 引用目标</h3>
          <div className="mention-chip-grid">
            {mentionOptions.map((option) => (
              <button key={`${option.kind}-${option.token}-${option.versionId || option.referenceId || option.entityId || ''}`} type="button" onClick={() => insertToken(option.token)}>
                <strong>{option.token}</strong>
                <span>{option.displayLabel}</span>
              </button>
            ))}
          </div>
        </section>
        <section className="drawer-section">
          <h3>反馈正文</h3>
          <textarea
            ref={textareaRef}
            value={feedbackText}
            placeholder={mode === 'model'
              ? '@主体1模型v2 金属角不够锋利。@场景1模型v1 地面比例太大。'
              : '@主体1 头部太小。@场景1 建筑再高一点。@整体图 增加暖光。'}
            onChange={(event) => setFeedbackText(event.target.value)}
          />
        </section>
        <div className="feedback-drawer__toolbar">
          <Button onClick={addReferenceUpload}>上传新参考</Button>
          {onOpenCompare && <Button onClick={onOpenCompare}>查看已选择</Button>}
          <Button variant="primary" onClick={submit} disabled={feedbackText.trim().length === 0}>{submitLabel}</Button>
        </div>
      </div>
    </aside>
  );
}
