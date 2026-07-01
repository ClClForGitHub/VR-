import { stages } from '../data/mockProject.js';

export function Stepper({ activeStage }) {
  return (
    <nav className="stepper" aria-label="创作阶段">
      {stages.map((stage) => (
        <div key={stage.id} className={`step ${stage.id === activeStage ? 'is-active' : ''}`}>
          <span className="step__dot">{stage.id}</span>
          <span className="step__label">{stage.label}</span>
        </div>
      ))}
    </nav>
  );
}
