import { useEffect, useMemo, useState } from 'react';
import { Button } from './Button.jsx';
import { Panel } from './Panel.jsx';

export function ReferenceTray({ referenceSlots = [] }) {
  const [slots, setSlots] = useState(referenceSlots);
  const subjectSlots = slots.filter((slot) => slot.slot_kind === 'subject');
  const sceneSlots = slots.filter((slot) => slot.slot_kind === 'scene');
  const counts = useMemo(() => ({
    subject: subjectSlots.filter((slot) => slot.status === 'uploaded').length,
    scene: sceneSlots.filter((slot) => slot.status === 'uploaded').length,
  }), [sceneSlots, subjectSlots]);

  useEffect(() => {
    setSlots(referenceSlots);
  }, [referenceSlots]);

  function replaceSlot(slotId) {
    setSlots((current) => current.map((slot) => (
      slot.slot_id === slotId
        ? { ...slot, status: 'replacing' }
        : slot
    )));
    window.setTimeout(() => {
      setSlots((current) => current.map((slot) => (
        slot.slot_id === slotId
          ? { ...slot, status: 'uploaded', image_url: slot.image_url || fallbackImage(slot), resolved_name: slot.resolved_name || slot.display_label }
          : slot
      )));
    }, 500);
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
      className="reference-tray"
    >
      <ReferenceSection
        title={`主体参考 ${counts.subject}/5`}
        uploadLabel="+ 上传主体参考"
        slots={subjectSlots}
        onReplace={replaceSlot}
        onRemove={removeSlot}
      />
      <ReferenceSection
        title={`场景参考 ${counts.scene}/1`}
        uploadLabel="+ 上传场景参考"
        slots={sceneSlots}
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
    <article className={`reference-slot-card ${uploaded ? 'is-uploaded' : 'is-empty'}`}>
      <div className="reference-slot-card__media">
        {uploaded ? <img src={slot.image_url} alt={slot.display_label} /> : <span>{slot.display_label}</span>}
      </div>
      <div className="reference-slot-card__body">
        <div>
          <strong>{slot.display_label}</strong>
          {slot.resolved_name && <span>{slot.resolved_name}</span>}
        </div>
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
  if (status === 'replacing') return '替换中';
  if (status === 'removed') return '已移除';
  return '等待上传';
}
