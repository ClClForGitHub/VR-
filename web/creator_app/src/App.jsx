import { useEffect, useMemo, useState } from 'react';
import { AppShell } from './components/AppShell.jsx';
import { CinematicRevealOverlay } from './components/CinematicRevealOverlay.jsx';
import { GenerationStatusDock } from './components/GenerationStatusDock.jsx';
import { AssetMemoryDrawer } from './components/AssetMemoryDrawer.jsx';
import {
  RuntimeAdapter,
  createMockViewModel,
  normalizeRunIndex,
  normalizeRunIndexItemFromBundle,
  normalizeRuntimeBundle,
} from './api/runtimeAdapter.js';
import { IntakeScreen } from './screens/IntakeScreen.jsx';
import { ConceptReviewScreen } from './screens/ConceptReviewScreen.jsx';
import { ModelReviewScreen } from './screens/ModelReviewScreen.jsx';
import { CompositionScreen } from './screens/CompositionScreen.jsx';
import { FinalReviewScreen } from './screens/FinalReviewScreen.jsx';
import { DeliveryScreen } from './screens/DeliveryScreen.jsx';

const screenMap = {
  intake: IntakeScreen,
  'concept-review': ConceptReviewScreen,
  'model-review': ModelReviewScreen,
  composition: CompositionScreen,
  'final-review': FinalReviewScreen,
  delivery: DeliveryScreen,
};

const DEFAULT_RUNTIME_RUN_COLLECTION = 'round04d_concepts';

function initialScreenFromHash() {
  const hash = window.location.hash.replace('#', '');
  return screenMap[hash] ? hash : 'intake';
}

export default function App() {
  const [screen, setScreen] = useState(initialScreenFromHash);
  const [viewModel, setViewModel] = useState(() => createMockViewModel());
  const [runtimeState, setRuntimeState] = useState({
    loading: false,
    baseUrl: runtimeApiBaseUrl(),
    selectedRunKey: runtimeRunKeyFromUrl(),
    runCollection: runtimeRunCollectionFromUrl(),
    runs: [],
  });
  const [generationTask, setGenerationTask] = useState(null);
  const [revealConcept, setRevealConcept] = useState(null);
  const [assetMemoryOpen, setAssetMemoryOpen] = useState(false);

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
    const runCollection = runtimeRunCollectionFromUrl();
    setRuntimeState((current) => ({ ...current, loading: true, baseUrl, runCollection }));
    try {
      const rawRuns = await adapter.listRuns({ collection: runCollection });
      let runs = normalizeRunIndex(rawRuns);
      const selectedRunKey = runKey || runs[0]?.runKey;
      if (!selectedRunKey) {
        throw new Error('Runtime backend returned no runs');
      }
      const rawBundle = await adapter.getRunBundle(selectedRunKey);
      if (!runs.some((run) => run.runKey === selectedRunKey)) {
        const selectedRun = normalizeRunIndexItemFromBundle(rawBundle);
        runs = selectedRun ? [selectedRun, ...runs] : runs;
      }
      const nextViewModel = normalizeRuntimeBundle(rawBundle, adapter, { runs });
      setViewModel(nextViewModel);
      setRuntimeState({ loading: false, baseUrl, selectedRunKey, runCollection, runs });
      if (!window.location.hash) {
        setScreen(nextViewModel.currentScreen);
        window.history.replaceState(null, '', `#${nextViewModel.currentScreen}`);
      }
    } catch (error) {
      setViewModel(createMockViewModel({ source: 'mock-fallback', error: error.message }));
      setRuntimeState({ loading: false, baseUrl, selectedRunKey: null, runCollection, runs: [] });
    }
  }

  function selectRun(runKey) {
    const url = new URL(window.location.href);
    url.searchParams.set('run_key', runKey);
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
    loadRuntime({ runKey });
  }

  async function uploadReference({ file, slot } = {}) {
    if (!file) throw new Error('请选择要上传的图片');
    if (!runtimeState.baseUrl || !runtimeState.selectedRunKey) {
      return {
        ok: false,
        local_only: true,
        image_id: `local_${Date.now()}`,
        artifact_id: null,
        filename: file.name,
      };
    }
    const adapter = new RuntimeAdapter({ baseUrl: runtimeState.baseUrl });
    const result = await adapter.uploadReference(runtimeState.selectedRunKey, { file, slot });
    await loadRuntime({ runKey: runtimeState.selectedRunKey });
    return result;
  }

  async function sendRuntimeChat(payload = {}) {
    if (!runtimeState.baseUrl || !runtimeState.selectedRunKey || !payload.message) return null;
    const adapter = new RuntimeAdapter({ baseUrl: runtimeState.baseUrl });
    const result = await adapter.sendChat(runtimeState.selectedRunKey, {
      text: payload.message,
      attachmentIds: payload.attachment_ids || [],
      metadata: {
        source: 'creator_app',
        reference_mentions: payload.reference_mentions || [],
      },
    });
    await loadRuntime({ runKey: runtimeState.selectedRunKey });
    return result;
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
        onOpenAssetMemory={() => setAssetMemoryOpen(true)}
      >
        <Screen
          onNavigate={navigate}
          viewModel={viewModel}
          onStartGeneration={startGeneration}
          onUploadReference={uploadReference}
          onSendRuntimeChat={sendRuntimeChat}
          onOpenAssetMemory={() => setAssetMemoryOpen(true)}
        />
      </AppShell>
      <AssetMemoryDrawer
        open={assetMemoryOpen}
        viewModel={viewModel}
        onClose={() => setAssetMemoryOpen(false)}
      />
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
  if (params.get('mock') === '1') return '';
  return (import.meta.env.VITE_RUNTIME_API_BASE_URL || '/api/creator').replace(/\/$/, '');
}

function runtimeRunKeyFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get('run_key');
}

function runtimeRunCollectionFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const value = params.get('run_collection')
    || params.get('collection')
    || import.meta.env.VITE_RUNTIME_RUN_COLLECTION
    || DEFAULT_RUNTIME_RUN_COLLECTION;
  if (!value || value === 'all') return '';
  return value;
}
