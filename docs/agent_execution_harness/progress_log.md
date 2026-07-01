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
