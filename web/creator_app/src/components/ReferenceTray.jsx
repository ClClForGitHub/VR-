import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from './Button.jsx';
import { Panel } from './Panel.jsx';

export function ReferenceTray({ referenceSlots = [], onUploadReference }) {
  const [slots, setSlots] = useState(referenceSlots);
  const [activeKind, setActiveKind] = useState('subject');
  const [pendingSlotId, setPendingSlotId] = useState(null);
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef(null);
  const subjectSlots = slots.filter((slot) => slot.slot_kind === 'subject');
  const sceneSlots = slots.filter((slot) => slot.slot_kind === 'scene');
  const activeSlots = activeKind === 'scene' ? sceneSlots : subjectSlots;
  const counts = useMemo(() => ({
    subject: subjectSlots.filter((slot) => slot.status === 'uploaded').length,
    scene: sceneSlots.filter((slot) => slot.status === 'uploaded').length,
  }), [sceneSlots, subjectSlots]);

  useEffect(() => {
    setSlots(referenceSlots);
  }, [referenceSlots]);

  function replaceSlot(slotId) {
    setPendingSlotId(slotId);
    setUploadError('');
    fileInputRef.current?.click();
  }

  async function handleFileSelected(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !pendingSlotId) return;
    const slot = slots.find((item) => item.slot_id === pendingSlotId);
    if (!slot) return;
    const previewUrl = URL.createObjectURL(file);
    setSlots((current) => current.map((slot) => (
      slot.slot_id === pendingSlotId
        ? { ...slot, status: 'uploading', image_url: previewUrl, resolved_name: file.name }
        : slot
    )));
    try {
      const result = await onUploadReference?.({ file, slot });
      setSlots((current) => current.map((slot) => (
        slot.slot_id === pendingSlotId
          ? {
            ...slot,
            status: 'uploaded',
            image_url: previewUrl,
            artifact_id: result?.artifact_id || slot.artifact_id,
            image_id: result?.image_id || slot.image_id,
            resolved_name: result?.filename || file.name,
          }
          : slot
      )));
    } catch (error) {
      setUploadError(error.message || '上传失败');
      setSlots((current) => current.map((slot) => (
        slot.slot_id === pendingSlotId
          ? { ...slot, status: 'upload_failed', image_url: null, resolved_name: slot.resolved_name }
          : slot
      )));
      URL.revokeObjectURL(previewUrl);
    } finally {
      setPendingSlotId(null);
    }
  }

  function removeSlot(slotId) {
    setSlots((current) => current.map((slot) => (
      slot.slot_id === slotId
        ? { ...slot, status: 'removed', image_url: null, artifact_id: null, resolved_name: null }
        : slot
    )));
  }

  return (
    <Panel
      title="Reference Tray"
      eyebrow="最多 5 主体 + 1 场景"
      className="reference-tray reference-tray--slots"
    >
      <div className="reference-resource-switch" role="tablist" aria-label="参考资源类型">
        <button
          type="button"
          className={activeKind === 'subject' ? 'is-active' : ''}
          onClick={() => setActiveKind('subject')}
          role="tab"
          aria-selected={activeKind === 'subject'}
        >
          <strong>主体资源</strong>
          <span>{counts.subject}/5 已上传</span>
        </button>
        <button
          type="button"
          className={activeKind === 'scene' ? 'is-active' : ''}
          onClick={() => setActiveKind('scene')}
          role="tab"
          aria-selected={activeKind === 'scene'}
        >
          <strong>场景资源</strong>
          <span>{counts.scene}/1 已上传</span>
        </button>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={handleFileSelected}
      />
      {uploadError && <div className="reference-upload-error">{uploadError}</div>}
      <ReferenceSection
        title={activeKind === 'scene' ? `场景资源 ${counts.scene}/1` : `主体资源 ${counts.subject}/5`}
        uploadLabel={activeKind === 'scene' ? '+ 上传场景参考' : '+ 上传主体参考'}
        slots={activeSlots}
        onReplace={replaceSlot}
        onRemove={removeSlot}
      />
    </Panel>
  );
}

function ReferenceSection({ title, uploadLabel, slots, onReplace, onRemove }) {
  return (
    <section className="reference-section">
      <header>
        <h3>{title}</h3>
        <Button variant="chip" onClick={() => slots[0] && onReplace(slots.find((slot) => slot.status !== 'uploaded')?.slot_id || slots[0].slot_id)}>
          {uploadLabel}
        </Button>
      </header>
      <div className="reference-tray__list">
        {slots.map((slot) => <ReferenceSlotCard key={slot.slot_id} slot={slot} onReplace={onReplace} onRemove={onRemove} />)}
      </div>
    </section>
  );
}

function ReferenceSlotCard({ slot, onReplace, onRemove }) {
  const uploaded = slot.status === 'uploaded' && slot.image_url;
  return (
    <article className={`reference-slot-card ${uploaded ? 'is-uploaded' : 'is-empty'} is-${slot.slot_kind}`}>
      <div className="reference-slot-card__media">
        {uploaded ? <img src={slot.image_url} alt={slot.display_label} /> : <span>{slot.display_label}</span>}
      </div>
      <div className="reference-slot-card__body">
        <div className="reference-slot-card__title">
          <strong>{slot.display_label}</strong>
          <span>{slot.mention}</span>
        </div>
        <p>{slot.resolved_name || (slot.slot_kind === 'scene' ? '等待场景参考图' : '等待主体参考图')}</p>
        <small>{statusLabel(slot.status)}</small>
        <div className="reference-slot-card__actions">
          <Button variant="chip" onClick={() => onReplace(slot.slot_id)}>替换图片</Button>
          <Button variant="chip" onClick={() => onRemove(slot.slot_id)}>移除</Button>
        </div>
      </div>
    </article>
  );
}

function fallbackImage(slot) {
  return slot.slot_kind === 'scene' ? '/mock-assets/scene_ruins_sunset.jpg' : '/mock-assets/subject_mecha_beast.jpg';
}

function statusLabel(status) {
  if (status === 'uploaded') return '已上传';
  if (status === 'uploading') return '上传中';
  if (status === 'upload_failed') return '上传失败';
  if (status === 'replacing') return '替换中';
  if (status === 'removed') return '已移除';
  return '等待上传';
}
