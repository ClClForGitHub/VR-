import { screens } from '../data/mockProject.js';

export function ScreenTabs({ current, onChange }) {
  return (
    <nav className="screen-tabs" aria-label="Creator App 工作区">
      {screens.map((screen) => (
        <button
          key={screen.id}
          type="button"
          className={current === screen.id ? 'is-active' : ''}
          onClick={() => onChange(screen.id)}
        >
          <span>0{screen.stage}</span>
          {screen.label}
        </button>
      ))}
    </nav>
  );
}
