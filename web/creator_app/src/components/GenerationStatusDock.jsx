import { useEffect, useMemo, useState } from 'react';
import { Button } from './Button.jsx';

const taskCopy = {
  concept: {
    title: '概念图生成中',
    subtitle: '后台正在理解提示词、参考图绑定和 SceneSpec。',
    expectedMs: 14000,
    steps: ['解析自然语言需求', '绑定参考图语义', '生成 SceneSpec', '渲染概念候选', '写入创作记忆', '准备揭幕动画'],
    completeLabel: '概念图已生成',
  },
  'concept-feedback': {
    title: '反馈重生成中',
    subtitle: '正在把你的修改意见绑定到整体、主体和场景目标。',
    expectedMs: 14000,
    steps: ['读取反馈目标', '保留已选版本', '生成替代方案', '对齐风格与光影', '写入创作记忆', '准备揭幕动画'],
    completeLabel: '新版本已生成',
  },
  model: {
    title: '模型生成中',
    subtitle: '概念组合已确认，后台正在生成主体和场景 GLB。',
    expectedMs: 18000,
    steps: ['读取已选概念组合', '提交主体模型生成', '提交场景模型生成', '等待 GLB 产出', '模型质量检查', '准备模型验收'],
    completeLabel: '模型已进入验收',
  },
  assembly: {
    title: 'Blender 组合渲染中',
    subtitle: '自由组合请求已提交，后台正在摆放、导出 viewer_scene.glb。',
    expectedMs: 16000,
    steps: ['读取主体/场景模型', '生成组合方案', '提交 Blender 组装', '导出 viewer_scene.glb', '生成 preview.png', '同步 scene_state.json'],
    completeLabel: '导演台已准备',
  },
};

export function GenerationStatusDock({ task, onComplete, onCancel }) {
  const [progress, setProgress] = useState(task?.progress ?? 8);
  const [startedAt, setStartedAt] = useState(() => Date.now());
  const [backendDone, setBackendDone] = useState(Boolean(task?.backendDone));
  const copy = useMemo(() => taskCopy[task?.kind] || taskCopy.concept, [task?.kind]);
  const autoComplete = task?.autoComplete !== false;
  const expectedMs = task?.expectedMs || copy.expectedMs || 14000;
  const activeStep = Math.min(copy.steps.length - 1, Math.floor(progress / (100 / copy.steps.length)));

  useEffect(() => {
    if (!task) return undefined;
    const nextStartedAt = Date.now();
    setStartedAt(nextStartedAt);
    setBackendDone(Boolean(task.backendDone));
    setProgress(displayedProgress(0, expectedMs, Boolean(task.backendDone)));
    return undefined;
  }, [expectedMs, task?.backendDone, task?.id]);

  useEffect(() => {
    if (!task) return undefined;
    const timer = window.setInterval(() => {
      const elapsed = Date.now() - startedAt;
      setProgress(displayedProgress(elapsed, expectedMs, backendDone));
    }, 400);
    return () => window.clearInterval(timer);
  }, [backendDone, expectedMs, startedAt, task?.id]);

  useEffect(() => {
    if (!task || !autoComplete) return undefined;
    let doneTimer;
    doneTimer = window.setTimeout(() => setBackendDone(true), task.mockDoneAfterMs || expectedMs);
    return () => {
      if (doneTimer) window.clearTimeout(doneTimer);
    };
  }, [autoComplete, expectedMs, task?.id, task?.mockDoneAfterMs]);

  useEffect(() => {
    if (!task) return;
    setProgress(displayedProgress(Date.now() - startedAt, expectedMs, backendDone));
  }, [backendDone, expectedMs, startedAt, task?.id]);

  useEffect(() => {
    if (!task || !backendDone || progress < 100) return undefined;
    const timer = window.setTimeout(() => onComplete?.(task), 500);
    return () => window.clearTimeout(timer);
  }, [backendDone, onComplete, progress, task]);

  if (!task) return null;

  return (
    <div className="generation-dock" role="status" aria-live="polite">
      <div className="generation-dock__panel">
        <div className="generation-dock__header">
          <span className="generation-dock__pulse" />
          <div>
            <h2>{task.title || copy.title}</h2>
            <p>{task.subtitle || copy.subtitle}</p>
          </div>
          <strong>{Math.round(progress)}%</strong>
        </div>
        <div className="generation-progress">
          <span style={{ width: `${progress}%` }} />
        </div>
        <ol className="generation-steps">
          {copy.steps.map((step, index) => (
            <li key={step} className={index <= activeStep ? 'is-active' : ''}>
              <span>{index + 1}</span>
              {step}
            </li>
          ))}
        </ol>
        <div className="generation-dock__footer">
          <span>{progress >= 100 ? copy.completeLabel : '后台任务运行中，可以继续停留在当前项目。'}</span>
          <Button variant="chip" onClick={onCancel}>收起</Button>
        </div>
      </div>
    </div>
  );
}

function displayedProgress(elapsedMs, expectedMs, backendDone) {
  if (backendDone) return 100;
  const ratio = elapsedMs / Math.max(1, expectedMs);
  if (ratio < 0.72) return Math.max(3, Math.floor(ratio * 85));
  if (ratio < 1.0) return 85 + Math.floor(((ratio - 0.72) / 0.28) * 10);
  return Math.min(99, 95 + Math.floor(Math.log1p(ratio - 1) * 2));
}
