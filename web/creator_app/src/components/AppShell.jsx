import { useMemo, useState } from 'react';
import { Button } from './Button.jsx';
import { screens } from '../data/mockProject.js';

export function AppShell({ screenId, onChangeScreen, viewModel, runtimeState, onSelectRun, onRefreshRuntime, onOpenAssetMemory, children }) {
  const project = viewModel.project;
  const runs = runtimeState.runs || [];
  const [projectCenterOpen, setProjectCenterOpen] = useState(false);
  const [projectSearch, setProjectSearch] = useState('');
  const sourceLabel = viewModel.source === 'backend'
    ? viewModel.publicPhaseLabel
    : viewModel.source === 'mock-fallback'
      ? 'Mock Fallback'
      : 'Mock';
  const currentRun = runs.find((run) => run.runKey === runtimeState.selectedRunKey) || runs[0] || null;
  const filteredRuns = useMemo(() => {
    const query = projectSearch.trim().toLowerCase();
    if (!query) return runs;
    return runs.filter((run) => [
      run.displayName,
      run.relativePath,
      run.phase,
      run.status,
      run.collectionId,
      run.runKey,
      run.collectionRank ? `case ${run.collectionRank}` : '',
    ].filter(Boolean).join(' ').toLowerCase().includes(query));
  }, [projectSearch, runs]);
  const collectionLabel = formatCollectionLabel(runtimeState.runCollection);

  function handleSelectRun(runKey) {
    if (!runKey || runKey === runtimeState.selectedRunKey) {
      setProjectCenterOpen(false);
      return;
    }
    onSelectRun(runKey);
    setProjectCenterOpen(false);
  }

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
          <div className={`project-center ${projectCenterOpen ? 'is-open' : ''}`}>
            <Button
              className="project-center__trigger"
              aria-haspopup="dialog"
              aria-expanded={projectCenterOpen}
              onClick={() => setProjectCenterOpen((open) => !open)}
            >
              <span className="project-center__trigger-main">项目中心</span>
              <span className="project-center__trigger-meta">
                {runs.length > 0 ? `${runs.length} 个样例` : '未连接'}
              </span>
            </Button>
            {runs.length > 0 && (
              <select
                className="project-center-native-select"
                value={runtimeState.selectedRunKey || currentRun?.runKey || ''}
                onChange={(event) => handleSelectRun(event.target.value)}
                aria-label="选择运行项目"
                tabIndex={-1}
              >
                {runs.map((run) => (
                  <option key={run.runKey} value={run.runKey}>
                    {run.displayName}
                  </option>
                ))}
              </select>
            )}
            {projectCenterOpen && (
              <section className="project-center__popover" role="dialog" aria-label="项目中心">
                <header className="project-center__header">
                  <div>
                    <span>{collectionLabel}</span>
                    <strong>后端样例项目</strong>
                  </div>
                  <button type="button" onClick={() => setProjectCenterOpen(false)} aria-label="关闭项目中心">×</button>
                </header>
                <div className="project-center__tools">
                  <input
                    value={projectSearch}
                    onChange={(event) => setProjectSearch(event.target.value)}
                    placeholder="搜索样例、阶段、路径..."
                    aria-label="搜索项目样例"
                  />
                  <button type="button" onClick={onRefreshRuntime}>
                    {runtimeState.loading ? '同步中' : '刷新'}
                  </button>
                </div>
                {currentRun && (
                  <div className="project-center__current">
                    <span>当前运行</span>
                    <strong>{currentRun.displayName}</strong>
                    <small>{currentRun.relativePath || currentRun.runKey}</small>
                  </div>
                )}
                <div className="project-center__list" role="listbox" aria-label="后端项目样例列表">
                  {filteredRuns.length > 0 ? filteredRuns.map((run, index) => (
                    <button
                      key={run.runKey}
                      type="button"
                      className={`project-run-card ${run.runKey === runtimeState.selectedRunKey ? 'is-active' : ''}`}
                      onClick={() => handleSelectRun(run.runKey)}
                      role="option"
                      aria-selected={run.runKey === runtimeState.selectedRunKey}
                    >
                      <span className="project-run-card__rank">
                        {String(run.collectionRank || index + 1).padStart(2, '0')}
                      </span>
                      <span className="project-run-card__body">
                        <strong>{run.displayName}</strong>
                        <small>{run.relativePath || run.runKey}</small>
                        <span className="project-run-card__badges">
                          <em>{formatPhase(run.phase)}</em>
                          <em>{formatStatus(run.status)}</em>
                          {run.hasViewerScene && <em>viewer</em>}
                          {run.hasSceneState && <em>scene_state</em>}
                        </span>
                      </span>
                    </button>
                  )) : (
                    <div className="project-center__empty">没有匹配的样例项目</div>
                  )}
                </div>
              </section>
            )}
          </div>
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

function formatCollectionLabel(collection) {
  if (!collection) return '全部运行';
  if (collection === 'round04d_concepts') return 'Round04D 12 样例';
  return collection;
}

function formatPhase(phase) {
  const phaseLabels = {
    INTAKE: '需求输入',
    SCENE_SPEC_DRAFT: '需求整理',
    SCENE_SPEC_READY: '需求就绪',
    CONCEPT_GENERATION: '概念生成',
    CONCEPT_REVIEW: '概念审稿',
    CONCEPT_APPROVED: '概念通过',
    SUBJECT_ASSET_GENERATION: '模型生成',
    SCENE_ASSET_GENERATION: '场景生成',
    SUBJECT_ASSET_QA: '模型验收',
    SCENE_ASSET_ADAPTATION: '场景适配',
    BLENDER_ASSEMBLY_PLANNING: '组装规划',
    BLENDER_ASSEMBLY_EXECUTION: '组装执行',
    BLENDER_PREVIEW: '最终验收',
    BLENDER_EDIT: '最终调整',
    DELIVERY: '交付',
  };
  return phaseLabels[phase] || phase || '未知阶段';
}

function formatStatus(status) {
  const statusLabels = {
    concept_ready: '概念就绪',
    needs_user_action: '待用户确认',
    ready: '就绪',
    running: '运行中',
    blocked: '阻塞',
    failed: '失败',
    completed: '完成',
  };
  return statusLabels[status] || status || '状态待同步';
}
