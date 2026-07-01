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
