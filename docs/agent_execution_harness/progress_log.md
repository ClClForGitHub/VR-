# Agent Execution Harness Progress Log

Use this file as an append-only progress log for harness-driven work.

## 2026-07-01 - Round 01 core harness seed

Scope:
- Create the execution harness entrypoint and templates.
- Establish documentation, reporting, and live-test policy for future coding-agent tasks.

Changed:
- Added planned files under `docs/agent_execution_harness/`.
- Added a documentation test to ensure the harness remains discoverable.
- Linked the harness from `AGENTS.md` and `docs/README.md`.

Verification:
- `python -m pytest tests/test_agent_execution_harness_docs.py -q` should pass after the files are applied.
- Full test suite should be run if the local environment supports it.

Known issues:
- This round is documentation-only and does not implement asset library or frontend state changes.

Next:
- Define the chat-thread asset library and user selection contract.

## 2026-07-01 - Round 01 core harness applied

Scope:
- Apply the Round 01 core harness package to the repository.
- Make active `docs/` the current documentation source and downgrade
  `docs/olddocs/` to historical/reference status.
- Record the reuse-first boundary for existing service, viewer, artifact, state,
  checkpoint, and review-patch paths.

Changed:
- Added `docs/agent_execution_harness/` from the Round 01 package.
- Added `tests/test_agent_execution_harness_docs.py`.
- Updated `AGENTS.md` to require the execution harness for non-trivial work.
- Replaced the active `docs/README.md` index with the new docs/harness boundary.
- Recorded the active-docs/reuse-first decision in `decision_log.md`.

Verification:
- `python -m pytest tests/test_agent_execution_harness_docs.py -q` -> 5 passed.
- `python -m pytest -q` -> 366 passed.
- Read-only service status checks were run; no live generation jobs were submitted.

Known issues:
- Historical docs are still present under `docs/olddocs/` and should remain
  reference-only unless a task packet explicitly asks to compare or recover them.

Next:
- Define the chat-thread asset library and user selection contract as the next
  product slice, using a task packet before implementation.

## 2026-07-01 - Round 02 backend asset library selection

Scope:
- Implement backend asset-library and assembly-selection state for runtime runs.
- Keep rejected assets visible and selectable.
- Add controlled backend asset actions and runtime-console API wiring.
- Ensure selected concepts/assets flow into subject generation and Blender
  assembly payloads.

Changed:
- Added `AssetLibraryItem`, `AssemblyObjectSelection`, and `AssemblySelection`
  to `agent_runtime/state.py`.
- Added `agent_runtime/runtime_asset_actions.py` for review/selection actions,
  JSONL logging, summaries, checkpoints, frontend status updates, and runtime
  plan rebuilds.
- Updated handoff apply paths to register concept, subject model, scene asset,
  Blender, viewer, and preview artifacts into the library with lineage.
- Updated controller/delegation/runtime bundle/runtime console server surfaces.
- Added Round 02 tests and user-journey fixture cases.
- Added `docs/agent_execution_harness/round_02_backend_asset_library_selection.md`
  and `round_02_completion_report.md`.

Verification:
- `python -m pytest tests/test_asset_library.py tests/test_runtime_asset_actions.py tests/test_frontend_status.py tests/test_runtime_handoff_apply.py tests/test_controller.py -q` -> 25 passed.
- `python -m pytest tests/test_runtime_delegation.py tests/test_runtime_console_server.py tests/test_runtime_runs.py tests/test_runtime_jobs.py -q` -> 26 passed.
- `python -m pytest -q` -> 377 passed.
- Read-only status scripts were run; no live generation or non-dry-run Blender
  MCP call was submitted.

Known issues:
- Frontend UI controls are not implemented in this round; the backend API and
  derived `frontend_status.json` contract are ready for a later UI slice.

Next:
- Wire runtime-console UI controls to `POST /api/runs/<run_key>/asset-action`
  and render the new asset-library/selection fields.

## 2026-07-01 - Round 03 core pipeline semantics

Scope:
- Verify and harden the core dry-run/delegated chain from explicit reference
  binding through SceneSpec, concept requirements, rework, selection, worker
  handoff context, Blender assembly payload, and frontend status.
- Keep live LLM/image/Hunyuan3D/HY-World/Blender calls out of this round.

Changed:
- Added scene-reference and identity-evidence validation to
  `agent_runtime/concept_planning.py`.
- Extended `agent_runtime/runtime_delegation.py` so concept, subject-asset, and
  scene-asset handoff JSON carries explicit context and apply-result schemas.
- Extended `agent_runtime/frontend_status.py` with backend asset-action payload
  examples while keeping it a derived state view.
- Added Round 03 tests and `core_pipeline_semantic_cases.json`.
- Added `round_03_core_pipeline_semantics.md`,
  `core_pipeline_test_matrix.md`, and `live_test_readiness_matrix.md`.

Verification:
- `python -m pytest tests/test_core_pipeline_semantics.py tests/test_concept_prompt_requirements.py tests/test_runtime_rework_flow.py tests/test_model_generation_selection_contract.py tests/test_runtime_context_and_file_contract.py tests/test_frontend_status_core_pipeline.py -q` -> 17 passed.
- `python -m pytest tests/test_concept_planning.py tests/test_runtime_delegation.py tests/test_runtime_asset_actions.py tests/test_runtime_user_actions.py tests/test_controller.py tests/test_frontend_status.py -q` -> 47 passed.
- `python -m pytest tests/test_natural_language_scene_fixtures.py::test_natural_language_scene_cases_run_to_delegated_generation -q` -> 9 passed.
- `python -m pytest -q` -> 394 passed.
- Read-only status scripts returned 0 for A40/Hunyuan3D/HY-World ports, GLB
  viewer, runtime console, and Blender 5.1 MCP bridge; existing service logs
  still show NVML, Gradio path, and Blender SSBO warnings.

Known issues:
- No live generation/service call was run in Round 03.
- Frontend UI controls are still not implemented; only derived payload examples
  are exposed for the later UI/API slice.

Next:
- Round04 should run an explicitly approved live smoke using the readiness
  matrix: live LLM/image generation, selected concept to Hunyuan3D, selected
  scene/target reference to scene asset, Blender assembly/export/preview, and
  delivery evidence.

## 2026-07-01 - Round 04 creator app mock migration

Scope:
- Migrate the locked v0.5 React/Vite frontend prototype into
  `web/creator_app/` as the new Creator App mock.
- Keep this slice mock-only; do not connect real backend APIs, model-viewer, or
  replace the old public UI.

Changed:
- Added `web/creator_app/` with the componentized React/Vite app, mock assets,
  design renders, API adapter boundary, screens, components, and styles.
- Added `docs/agent_execution_harness/round_04_creator_app_mock_migration.md`
  as the task packet and completion record.
- Updated `docs/README.md` with the new frontend reset and Creator App entry.

Verification:
- `cd web/creator_app && npm install` -> added 64 packages, audited 65
  packages, found 0 vulnerabilities.
- `cd web/creator_app && npm run build` -> passed; Vite transformed 47 modules
  and wrote ignored `dist/` output.
- `cd web/creator_app && npm run dev -- --host 127.0.0.1 --port 5173` ->
  local Vite server ready at `http://127.0.0.1:5173/`.
- `curl -I http://127.0.0.1:5173/` -> `HTTP/1.1 200 OK`.

Known issues:
- This is still a mock UI. It does not read real runtime bundles, submit chat or
  user-action requests, use model-viewer, or replace `web/runtime_console/`.
- Existing unrelated working-tree changes were present before this slice and
  were not modified.

Next:
- Round 05 should harden responsive layout/screenshots if needed, then connect
  read-only runtime bundle data through `src/api/runtimeAdapter.js`.
