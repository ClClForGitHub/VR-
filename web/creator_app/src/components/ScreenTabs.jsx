import { screens } from '../data/mockProject.js';

export function ScreenTabs({ current, onChange }) {
  return (
    <aside className="screen-tabs" aria-label="原型页面">
      {screens.map((screen) => (
        <button
          key={screen.id}
          type="button"
          className={current === screen.id ? 'is-active' : ''}
          onClick={() => onChange(screen.id)}
        >
          {screen.label}
        </button>
      ))}
    </aside>
  );
}
