import { useEffect, useMemo, useState } from 'react';
import { AppShell } from './components/AppShell.jsx';
import { CinematicRevealOverlay } from './components/CinematicRevealOverlay.jsx';
import { GenerationStatusDock } from './components/GenerationStatusDock.jsx';
import {
  RuntimeAdapter,
  createMockViewModel,
  normalizeRunIndex,
  normalizeRuntimeBundle,
} from './api/runtimeAdapter.js';
import { IntakeScreen } from './screens/IntakeScreen.jsx';
import { ConceptReviewScreen } from './screens/ConceptReviewScreen.jsx';
import { ModelReviewScreen } from './screens/ModelReviewScreen.jsx';
import { AssetMemoryScreen } from './screens/AssetMemoryScreen.jsx';
import { CompositionScreen } from './screens/CompositionScreen.jsx';
import { FinalReviewScreen } from './screens/FinalReviewScreen.jsx';
import { DeliveryScreen } from './screens/DeliveryScreen.jsx';

const screenMap = {
  intake: IntakeScreen,
  'concept-review': ConceptReviewScreen,
  'model-review': ModelReviewScreen,
  'asset-memory': AssetMemoryScreen,
  composition: CompositionScreen,
  'final-review': FinalReviewScreen,
  delivery: DeliveryScreen,
};

function initialScreenFromHash() {
  const hash = window.location.hash.replace('#', '');
  if (hash === 'reveal' || hash === 'feedback-compare') return 'concept-review';
  return screenMap[hash] ? hash : 'intake';
}

export default function App() {
  const [screen, setScreen] = useState(initialScreenFromHash);
  const [viewModel, setViewModel] = useState(() => createMockViewModel());
  const [runtimeState, setRuntimeState] = useState({
    loading: false,
    baseUrl: runtimeApiBaseUrl(),
    selectedRunKey: runtimeRunKeyFromUrl(),
    runs: [],
  });
  const [generationTask, setGenerationTask] = useState(null);
  const [revealConcept, setRevealConcept] = useState(null);

  const Screen = useMemo(() => screenMap[screen] ?? IntakeScreen, [screen]);

  function navigate(nextScreen) {
    const safeScreen = screenMap[nextScreen] ? nextScreen : 'concept-review';
    setScreen(safeScreen);
    window.history.replaceState(null, '', `#${safeScreen}`);
  }

  function startGeneration(kind, options = {}) {
    setGenerationTask({
      id: `${kind}-${Date.now()}`,
      kind,
      ...options,
    });
  }

  function completeGeneration(task) {
    setGenerationTask(null);
    if (task.kind === 'concept' || task.kind === 'concept-feedback') {
      setRevealConcept(viewModel.concepts[0]);
      return;
    }
    if (task.kind === 'model') {
      navigate('model-review');
      return;
    }
    if (task.kind === 'assembly') {
      navigate('final-review');
    }
  }

  async function loadRuntime({ runKey = runtimeState.selectedRunKey } = {}) {
    const baseUrl = runtimeApiBaseUrl();
    if (!baseUrl) {
      const mock = createMockViewModel();
      setViewModel(mock);
      setRuntimeState((current) => ({ ...current, loading: false, baseUrl: '', selectedRunKey: null, runs: [] }));
      return;
    }

    const adapter = new RuntimeAdapter({ baseUrl });
    setRuntimeState((current) => ({ ...current, loading: true, baseUrl }));
    try {
      const rawRuns = await adapter.listRuns();
      const runs = normalizeRunIndex(rawRuns);
      const selectedRunKey = runKey && runs.some((run) => run.runKey === runKey)
        ? runKey
        : runs[0]?.runKey;
      if (!selectedRunKey) {
        throw new Error('Runtime backend returned no runs');
      }
      const rawBundle = await adapter.getRunBundle(selectedRunKey);
      const nextViewModel = normalizeRuntimeBundle(rawBundle, adapter, { runs });
      setViewModel(nextViewModel);
      setRuntimeState({ loading: false, baseUrl, selectedRunKey, runs });
      if (!window.location.hash) {
        setScreen(nextViewModel.currentScreen);
        window.history.replaceState(null, '', `#${nextViewModel.currentScreen}`);
      }
    } catch (error) {
      setViewModel(createMockViewModel({ source: 'mock-fallback', error: error.message }));
      setRuntimeState({ loading: false, baseUrl, selectedRunKey: null, runs: [] });
    }
  }

  function selectRun(runKey) {
    const url = new URL(window.location.href);
    url.searchParams.set('run_key', runKey);
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
    loadRuntime({ runKey });
  }

  useEffect(() => {
    loadRuntime();
  }, []);

  const runtimeGenerationTask = !generationTask && viewModel.runtime?.generationStatus
    ? { id: `runtime-${viewModel.phase}`, kind: generationKindForPhase(viewModel.phase), autoComplete: false, progress: 64, ...viewModel.runtime.generationStatus }
    : null;

  return (
    <>
      <AppShell
        screenId={screen}
        onChangeScreen={navigate}
        viewModel={viewModel}
        runtimeState={runtimeState}
        onSelectRun={selectRun}
        onRefreshRuntime={() => loadRuntime({ runKey: runtimeState.selectedRunKey })}
      >
        <Screen onNavigate={navigate} viewModel={viewModel} onStartGeneration={startGeneration} />
      </AppShell>
      <GenerationStatusDock
        task={generationTask || runtimeGenerationTask}
        onComplete={completeGeneration}
        onCancel={() => setGenerationTask(null)}
      />
      <CinematicRevealOverlay
        open={Boolean(revealConcept)}
        concept={revealConcept}
        onClose={() => setRevealConcept(null)}
        onEnterReview={() => {
          setRevealConcept(null);
          navigate('concept-review');
        }}
      />
    </>
  );
}

function generationKindForPhase(phase) {
  if (phase === 'CONCEPT_GENERATION') return 'concept';
  if (phase === 'BLENDER_ASSEMBLY_EXECUTION') return 'assembly';
  return 'model';
}

function runtimeApiBaseUrl() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get('api_base') || params.get('api');
  return (fromQuery || import.meta.env.VITE_RUNTIME_API_BASE_URL || '').replace(/\/$/, '');
}

function runtimeRunKeyFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get('run_key');
}
