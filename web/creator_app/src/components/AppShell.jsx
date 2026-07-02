import { Button } from './Button.jsx';
import { screens } from '../data/mockProject.js';

export function AppShell({ screenId, onChangeScreen, viewModel, runtimeState, onSelectRun, onRefreshRuntime, onOpenAssetMemory, children }) {
  const project = viewModel.project;
  const runs = runtimeState.runs || [];
  const sourceLabel = viewModel.source === 'backend'
    ? viewModel.publicPhaseLabel
    : viewModel.source === 'mock-fallback'
      ? 'Mock Fallback'
      : 'Mock';
  return (
    <div className="creator-shell" data-runtime-source={viewModel.source} data-run-key={viewModel.runKey || ''}>
      <header className="topbar">
        <div className="brand-block">
          <div className="logo">image<span>23D</span></div>
          <div className="project-meta">
            当前项目 <span className="runtime-source-pill">{sourceLabel}</span>
          </div>
          <div className="project-title">{project.title}⌄</div>
          {viewModel.error && <div className="project-warning">{viewModel.error}</div>}
        </div>
        <div className="topbar-actions">
          <Button onClick={onOpenAssetMemory}>资产记忆</Button>
          {runs.length > 0 ? (
            <label className="run-select-label">
              <span>项目中心</span>
              <select
                value={runtimeState.selectedRunKey || ''}
                onChange={(event) => onSelectRun(event.target.value)}
                aria-label="选择运行项目"
              >
                {runs.map((run) => (
                  <option key={run.runKey} value={run.runKey}>
                    {run.displayName}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <Button>项目中心</Button>
          )}
          <Button onClick={onRefreshRuntime}>{runtimeState.loading ? '同步中' : project.user}⌄</Button>
        </div>
      </header>
      <div className="workspace-body">
        <aside className="process-rail" aria-label="image23D 创作流程">
          <div className="process-rail__header">
            <span>Flow</span>
            <strong>6 步创作链路</strong>
          </div>
          <nav className="process-rail__list">
            {screens.map((screen) => (
              <button
                key={screen.id}
                type="button"
                className={currentClass(screenId, screen.id)}
                onClick={() => onChangeScreen(screen.id)}
              >
                <span className="process-rail__index">0{screen.stage}</span>
                <span className="process-rail__label">{screen.label}</span>
                <span className="process-rail__state">{screenState(screenId, screen.id)}</span>
              </button>
            ))}
          </nav>
          <div className="process-rail__footer">
            <span>当前运行</span>
            <strong>{viewModel.source === 'backend' ? viewModel.runKey || 'Backend Run' : 'Mock Preview'}</strong>
          </div>
        </aside>
        <main className="main-stage">{children}</main>
      </div>
    </div>
  );
}

function currentClass(current, id) {
  return current === id ? 'is-active' : '';
}

function screenState(current, id) {
  if (current === id) return '当前';
  const currentIndex = screens.findIndex((screen) => screen.id === current);
  const itemIndex = screens.findIndex((screen) => screen.id === id);
  if (currentIndex > itemIndex) return '已完成';
  return '待处理';
}
