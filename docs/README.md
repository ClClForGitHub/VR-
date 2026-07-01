# Project Docs Index

This directory contains the current active project documentation for
`image23D_Agent`.

## Current Source Priority

Use current active docs under `docs/` as the project documentation source.
`docs/olddocs/` is a historical/reference archive and is not the governing plan
unless the user explicitly asks for history, comparison, or recovery from old
notes.

When docs and runtime evidence disagree, inspect current code, tests, run
artifacts, and logs first. Update the stale active doc after verification
instead of creating a second conflicting source of truth.

## Execution Harness

The Round 01 execution harness is the required entrypoint for non-trivial
coding-agent work:

- `agent_execution_harness/README.md`: execution rules and entrypoint.
- `agent_execution_harness/task_packet_template.md`: required task packet format.
- `agent_execution_harness/runtime_flow_rules.md`: runtime state and gate rules.
- `agent_execution_harness/live_test_policy.md`: live-service command boundary.
- `agent_execution_harness/documentation_maintenance.md`: doc update rules.
- `agent_execution_harness/module_checklist.md`: product workflow checklist.
- `agent_execution_harness/progress_log.md`: append-only harness progress.
- `agent_execution_harness/decision_log.md`: durable harness decisions.
- `agent_execution_harness/design_notes.md`: current design notes.
- `agent_execution_harness/round_02_backend_asset_library_selection.md`: backend asset library and user-selection contract.
- `agent_execution_harness/round_03_core_pipeline_semantics.md`: core pipeline semantic contract from intake through handoff/frontend status.
- `agent_execution_harness/core_pipeline_test_matrix.md`: Round 03 dry-run/delegated semantic test matrix.
- `agent_execution_harness/live_test_readiness_matrix.md`: Round 04 live-call readiness checklist.
- `agent_execution_harness/round_04_live_full_flow_user_samples.md`: Round 04 real user-sample full-flow execution contract.
- `agent_execution_harness/live_user_sample_manifest_contract.md`: manifest schema for scripted live user samples.
- `agent_execution_harness/frontend_live_review_checklist.md`: frontend/runtime observability checklist for live sample runs.
- `agent_execution_harness/round04_live_execution_report_template.md`: per-case live execution report schema.

## Frontend Reset

The locked v0.5 frontend reset package is under
`image23d_frontend_FULL_design_handoff_v0_5/`.

The migrated mock Creator App lives at `../web/creator_app/`. It is the new
React/Vite frontend landing directory for the Premium Cinematic Dark Creation
Studio design. It currently runs on mock data only; `web/runtime_console/`
remains the dev/debug UI until a later task explicitly replaces the public
entrypoint.

## Current Operating Rules

- Build a real image/text-to-Blender-scene agent, not only scaffolding.
- Reuse existing Hunyuan3D, HY-World/WorldMirror, Blender compose/export, GLB
  viewer, artifact store, state/checkpoint, and review-patch paths.
- `state.json` is the authoritative run state.
- `frontend_status.json` is a derived UI handoff, not a second state source.
- Dry-run, fixture, and delegated evidence must stay labelled as such.
- Live model or Blender calls need an explicit command boundary and user
  approval when required by the active task packet.
- Generated binaries and run outputs stay under `outputs/runs/<run_id>/` and
  must not be committed.

## Historical Docs

Archived prior docs are under `olddocs/`. Use them only as reference material
when an active task packet permits or asks for historical comparison.
