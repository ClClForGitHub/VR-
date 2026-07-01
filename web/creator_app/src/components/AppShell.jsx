import { screens } from '../data/mockProject.js';
import { Stepper } from './Stepper.jsx';
import { ScreenTabs } from './ScreenTabs.jsx';
import { Button } from './Button.jsx';

export function AppShell({ screenId, onChangeScreen, viewModel, runtimeState, onSelectRun, onRefreshRuntime, children }) {
  const activeStage = screens.find((screen) => screen.id === screenId)?.stage ?? 1;
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
        <Stepper activeStage={activeStage} />
        <div className="topbar-actions">
          <Button onClick={() => onChangeScreen('asset-memory')}>资产记忆</Button>
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
      <ScreenTabs current={screenId} onChange={onChangeScreen} />
      <main className="main-stage">{children}</main>
    </div>
  );
}
