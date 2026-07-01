import { createMockViewModel } from './runtimeAdapter.js';

export async function fetchCreatorBundle() {
  return createMockViewModel();
}

export async function submitUserAction(action) {
  console.info('[mock submitUserAction]', action);
  return { ok: true, actionId: `mock_${Date.now()}`, action };
}
