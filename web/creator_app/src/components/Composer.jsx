import { useMemo, useRef, useState } from 'react';
import { Button } from './Button.jsx';

export function Composer({
  placeholder = '描述你的想法，或通过 @ 引用主体/场景...',
  compact = false,
  className = '',
  referenceSlots = [],
  onSend,
  onUpload,
}) {
  const [value, setValue] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const mentionSlots = useMemo(
    () => referenceSlots.filter((slot) => slot.status === 'uploaded'),
    [referenceSlots],
  );
  const mentionOptions = useMemo(() => mentionSlots.map((slot) => (
    {
      token: slot.mention,
      label: slot.mention,
      detail: slot.resolved_name || slot.display_label,
      slot,
    }
  )), [mentionSlots]);

  function insertMention(option) {
    const mention = option.token;
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
    const message = value.trim();
    if (!message) return;
    onSend?.({
      message,
      reference_mentions: mentionSlots
        .map((slot) => ({ token: slot.mention, slot }))
        .filter((option) => value.includes(option.token))
        .map((option) => ({
          mention: option.token,
          entity_id: option.slot.entity_id,
          slot_id: option.slot.slot_id,
          artifact_id: option.slot.artifact_id,
        })),
    });
    setValue('');
  }

  async function handleUploadSelected(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setUploading(true);
    try {
      await onUpload?.(file);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className={`composer ${compact ? 'composer--compact' : ''} ${className}`.trim()}>
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
              {mentionOptions.length > 0 ? mentionOptions.map((option) => (
                <button key={`${option.slot.slot_id}-${option.token}`} type="button" onClick={() => insertMention(option)}>
                  <strong>{option.label}</strong>
                  <span>{option.detail}</span>
                </button>
              )) : <span>暂无可引用参考图</span>}
            </div>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          hidden
          onChange={handleUploadSelected}
        />
        <Button variant="chip" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
          {uploading ? '上传中' : '上传'}
        </Button>
        <button className="send-button" aria-label="发送" onClick={send}>↗</button>
      </div>
    </div>
  );
}
