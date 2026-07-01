import { Button } from './Button.jsx';

export function CinematicRevealOverlay({ concept, open, onEnterReview, onClose }) {
  if (!open || !concept) return null;

  return (
    <div className="cinematic-reveal" role="dialog" aria-modal="true" aria-label="概念图揭幕">
      <div className="cinematic-reveal__glow" />
      <div className="cinematic-reveal__stage">
        <div className="cinematic-reveal__ring" />
        <img src={concept.image} alt={concept.title} />
        <div className="cinematic-reveal__copy">
          <span>Concept Render Ready</span>
          <h2>{concept.title}</h2>
          <p>{concept.note}</p>
        </div>
      </div>
      <div className="cinematic-reveal__actions">
        <Button onClick={onClose}>留在当前页</Button>
        <Button variant="primary" onClick={onEnterReview}>进入概念审稿</Button>
      </div>
    </div>
  );
}
