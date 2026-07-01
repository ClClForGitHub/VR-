import { useEffect, useMemo, useState } from 'react';
import { AppShell } from './components/AppShell.jsx';
import {
  RuntimeAdapter,
  createMockViewModel,
  normalizeRunIndex,
  normalizeRuntimeBundle,
} from './api/runtimeAdapter.js';
import { IntakeScreen } from './screens/IntakeScreen.jsx';
import { ConceptRevealScreen } from './screens/ConceptRevealScreen.jsx';
import { ConceptReviewScreen } from './screens/ConceptReviewScreen.jsx';
import { FeedbackCompareScreen } from './screens/FeedbackCompareScreen.jsx';
import { ModelReviewScreen } from './screens/ModelReviewScreen.jsx';
import { AssetMemoryScreen } from './screens/AssetMemoryScreen.jsx';
import { CompositionScreen } from './screens/CompositionScreen.jsx';
import { FinalReviewScreen } from './screens/FinalReviewScreen.jsx';
import { DeliveryScreen } from './screens/DeliveryScreen.jsx';

const screenMap = {
  intake: IntakeScreen,
  reveal: ConceptRevealScreen,
  'concept-review': ConceptReviewScreen,
  'feedback-compare': FeedbackCompareScreen,
  'model-review': ModelReviewScreen,
  'asset-memory': AssetMemoryScreen,
  composition: CompositionScreen,
  'final-review': FinalReviewScreen,
  delivery: DeliveryScreen,
};

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
    runs: [],
  });

  const Screen = useMemo(() => screenMap[screen] ?? IntakeScreen, [screen]);

  function navigate(nextScreen) {
    setScreen(nextScreen);
    window.history.replaceState(null, '', `#${nextScreen}`);
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

  return (
    <AppShell
      screenId={screen}
      onChangeScreen={navigate}
      viewModel={viewModel}
      runtimeState={runtimeState}
      onSelectRun={selectRun}
      onRefreshRuntime={() => loadRuntime({ runKey: runtimeState.selectedRunKey })}
    >
      <Screen onNavigate={navigate} viewModel={viewModel} />
    </AppShell>
  );
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
