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

## 2026-07-01 - Round 05 creator app responsive polish

Scope:
- Continue the v0.5 frontend path with Task 2: stabilize the migrated
  `web/creator_app/` mock UI before backend integration.
- Keep the slice mock-only; do not connect real APIs, model-viewer, or replace
  `web/runtime_console/`.

Changed:
- Added `web/creator_app/vite.config.js` so Vite dev/build uses the React
  plugin and the migrated JSX app hydrates correctly.
- Added `web/creator_app/scripts/screenshot-smoke.mjs` plus
  `npm run smoke:screenshots` for repeatable desktop/mobile mock screenshot
  checks.
- Tightened `tokens.css` and `app.css` for responsive columns, stable text
  sizing, no negative letter spacing, no viewport-width font scaling, internal
  scroll panels, and mobile horizontal-overflow fixes.
- Simplified `GlbViewerShell` control labels while keeping model-viewer
  integration deferred.

Verification:
- `cd web/creator_app && npm run build` -> passed; Vite transformed 52 modules.
- `cd web/creator_app && npm run smoke:screenshots` -> passed; 8 screenshots
  checked at desktop 1440x1000 and mobile 390x844.
- Screenshot evidence directory:
  `run_logs/frontend_checks/creator_app_round05_20260701T100506Z`.
- Playwright hydration/title check on
  `http://127.0.0.1:5173/#concept-review` -> true.

Known issues:
- UI still uses mock data and `GlbViewerShell`; it does not read runtime bundles
  or render real GLB/model-viewer content yet.
- Screenshot artifacts live under ignored `run_logs/` and are not tracked.

Next:
- Round 06 should implement read-only runtime bundle integration through
  `web/creator_app/src/api/runtimeAdapter.js` with mock fallback preserved.

## 2026-07-01 - Round 06 creator app read-only backend API

Scope:
- Continue v0.5 through real backend API connection, stopping before write
  actions, model-viewer, and public UI replacement.
- Connect `web/creator_app/` to runtime-console read-only APIs with mock
  fallback preserved.

Changed:
- Implemented read-only `RuntimeAdapter` for `GET /api/runs`,
  `GET /api/runs/<run_key>/bundle`, and file URLs.
- Added `normalizeRuntimeBundle(rawBundle)` to convert runtime state,
  `frontend_status.json`, `scene_state.json`, artifacts, and file manifests
  into a product-facing CreatorRunViewModel.
- Wired `App`, `AppShell`, and screens to consume ViewModel data instead of
  hard-coded mock content, while preserving mock fallback.
- Added `npm run smoke:backend-readonly` for read-only backend/API/DOM smoke.
- Updated Creator App README and backend integration plan with the landed
  read-only API boundary.

Verification:
- `cd web/creator_app && npm run build` -> passed; Vite transformed 53 modules.
- `cd web/creator_app && npm run smoke:screenshots` -> passed; 8 mock
  screenshots checked. Evidence:
  `run_logs/frontend_checks/creator_app_round05_20260701T104232Z`.
- `cd web/creator_app && npm run smoke:backend-readonly` -> passed against
  `http://127.0.0.1:18093`, selected run
  `20260630_live_user_examples_114143Z`, fileCount 26, fileCards 6. Evidence:
  `run_logs/frontend_checks/creator_app_backend_readonly_20260701T103920Z`.
- Existing runtime console `http://127.0.0.1:8093/api/runs` -> 50 runs.
- Playwright check on
  `http://127.0.0.1:5173/?api_base=http%3A%2F%2F127.0.0.1%3A8093#delivery`
  -> `source=backend`, `runOptions=50`, `fileCards=6`,
  `hasRuntimeFileLink=true`.

Known issues:
- This round did not implement POST `/chat`, `/upload`, `/user-action`, or
  `/loop`.
- `GlbViewerShell` is still a poster/viewer shell; model-viewer is the next
  separate slice.
- Existing unrelated working-tree changes and untracked doc/test packages were
  not modified.

Next:
- Round 07 should implement controlled write actions for chat/upload and
  user-action, or move to model-viewer if the API write path is intentionally
  deferred.

## 2026-07-01 - Round 04B live concept executor unblock

Scope:
- Implement the Round04B package boundary for structured live concept-image
  execution.
- Reuse existing runtime handoff and handoff-apply paths; do not add another
  state store or artifact registry.

Changed:
- Added `agent_runtime/concept_image_execution.py` with request/result/call
  contracts, backend capability reporting, and ordered requirement execution.
- Added runtime worker backend `live_image` and kept the existing
  `codex_self_mcp` structured-handoff guard intact.
- Added `scripts/probe_live_image_backend.py`.
- Updated `scripts/run_round04_live_user_samples.py --live` to run
  execution -> handoff -> `live_image` worker instead of writing static
  blockers.
- Added Round04B tests for the executor contract, runtime worker integration,
  and `case_03_lunar_rover` canary flow with a fake capable backend.

Verification:
- `python -m py_compile ...` -> passed for changed runtime/script/test files.
- `pytest -q tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py` -> 5 passed.
- `pytest -q tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py tests/test_runtime_worker.py tests/test_round04_live_runner_contract.py` -> 15 passed.
- `pytest -q` -> 405 passed.
- `python scripts/probe_live_image_backend.py --write-report outputs/runs/round04b_probe/live_image_backend_probe.json` -> wrote capability report; default backend is not live-acceptance ready for image-guided or multi-image composition.
- `python scripts/run_round04_live_user_samples.py --case case_03_lunar_rover --live --overwrite --max-concept-regens 1` -> exit 1, expected blocked; 3 call records written with no fake output image paths.

Known issues:
- `codex_self_mcp` currently reports `text_to_image=true` and
  `output_extraction=true`, but no proven local-file attachment or multi-image
  composition support.
- Full Round04 live completion still needs a backend implementing real
  image-guided and multi-image file attachment.

Next:
- Wire or prove a provider backend that satisfies `ConceptImageBackend` with
  real local file attachments, then rerun the Round04B canary before broad
  12-sample execution.

## 2026-07-01 - Round 04C image2 reference generation

Scope:
- Implement the Round04C package boundary for local reference-image generation.
- Reuse the Round04B concept executor, runtime worker, handoff-apply,
  artifact, asset-library, state, checkpoint, and frontend-status paths.

Changed:
- Added `agent_runtime/image2_reference_adapter.py` for codex-self image2
  generation with attachment manifests, PNG view copies, log evidence parsing,
  and stream extraction after `image_generation_end`.
- Updated `CodexSelfMCPImage2ConceptBackend` and the default `live_image`
  worker backend.
- Updated `scripts/probe_live_image_backend.py` to prove child-agent
  `view_image` and `input_image` payload support.
- Added `tests/test_image2_reference_attachment_live_contract.py` and extended
  concept execution tests for attachment manifests and target source images.
- Added `round_04c_image2_reference_generation.md` and
  `round_04c_completion_report.md`.

Verification:
- `python -m py_compile agent_runtime/image2_reference_adapter.py agent_runtime/concept_image_execution.py agent_runtime/runtime_worker.py scripts/probe_live_image_backend.py tests/test_image2_reference_attachment_live_contract.py` -> passed.
- `python -m pytest tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py tests/test_image2_reference_attachment_live_contract.py -q` -> 10 passed.
- `python scripts/probe_live_image_backend.py --write-report outputs/runs/round04c_probe/live_image_backend_probe.json` -> exit 0, `live_acceptance_ready=true`.
- `python scripts/run_round04_live_user_samples.py --case case_03_lunar_rover --live --overwrite --max-concept-regens 1` -> exit 0, `ok=true`, `status=partial`, concept worker completed 3/3 calls.

Known issues:
- The Round04C canary intentionally does not start downstream
  Hunyuan3D/HY-World/Blender stages; the sample report is `partial` for that
  reason.
- The official codex MCP schema still has no native `images[]` argument; this
  round accepts child-agent `view_image` payload evidence as the wrapper
  boundary.

Next:
- After user acceptance, run the broader live sample set or explicitly continue
  downstream generation with Hunyuan3D/HY-World/Blender command boundaries.
