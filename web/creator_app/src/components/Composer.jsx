import { useMemo, useRef, useState } from 'react';
import { Button } from './Button.jsx';

export function Composer({
  placeholder = '描述你的想法，或通过 @ 引用主体/场景...',
  compact = false,
  referenceSlots = [],
  onSend,
  onUpload,
}) {
  const [value, setValue] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const textareaRef = useRef(null);
  const mentionSlots = useMemo(
    () => referenceSlots.filter((slot) => slot.status === 'uploaded'),
    [referenceSlots],
  );

  function insertMention(slot) {
    const mention = slot.mention || `@${slot.display_label.replace(/\s+/g, '')}`;
    const textarea = textareaRef.current;
    if (!textarea) {
      setValue((current) => `${current}${current.endsWith(' ') || current.length === 0 ? '' : ' '}${mention} `);
      setPickerOpen(false);
      return;
    }
    const start = textarea.selectionStart ?? value.length;
    const end = textarea.selectionEnd ?? value.length;
    const next = `${value.slice(0, start)}${mention} ${value.slice(end)}`;
    setValue(next);
    setPickerOpen(false);
    window.requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(start + mention.length + 1, start + mention.length + 1);
    });
  }

  function send() {
    onSend?.({
      message: value,
      reference_mentions: mentionSlots
        .filter((slot) => value.includes(slot.mention))
        .map((slot) => ({
          mention: slot.mention,
          entity_id: slot.entity_id,
          slot_id: slot.slot_id,
          artifact_id: slot.artifact_id,
        })),
    });
  }

  return (
    <div className={`composer ${compact ? 'composer--compact' : ''}`}>
      <textarea
        ref={textareaRef}
        value={value}
        placeholder={placeholder}
        onChange={(event) => setValue(event.target.value)}
      />
      <div className="composer-actions">
        <div className="mention-picker-wrap">
          <Button variant="chip" onClick={() => setPickerOpen((open) => !open)}>@</Button>
          {pickerOpen && (
            <div className="mention-picker">
              {mentionSlots.length > 0 ? mentionSlots.map((slot) => (
                <button key={slot.slot_id} type="button" onClick={() => insertMention(slot)}>
                  <strong>{slot.mention}</strong>
                  <span>{slot.resolved_name || slot.display_label}</span>
                </button>
              )) : <span>暂无可引用参考图</span>}
            </div>
          )}
        </div>
        <Button variant="chip" onClick={onUpload}>上传</Button>
        <button className="send-button" aria-label="发送" onClick={send}>↗</button>
      </div>
    </div>
  );
}
