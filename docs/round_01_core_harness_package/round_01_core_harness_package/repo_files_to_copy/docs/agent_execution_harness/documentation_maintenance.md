# Documentation Maintenance Rules

Documentation is part of the runtime handoff. Do not leave important plan, progress, or design reasoning only in chat.

## Required documentation surfaces

Use these files under `docs/agent_execution_harness/`:

- `README.md`: execution rules and entrypoint.
- `task_packet_template.md`: template for future task packets.
- `runtime_flow_rules.md`: state/runtime boundaries.
- `live_test_policy.md`: live-service testing boundaries.
- `module_checklist.md`: phase-by-phase implementation checklist.
- `progress_log.md`: append-only execution progress.
- `decision_log.md`: architectural or workflow decisions.
- `design_notes.md`: short-lived design thinking that should be preserved until promoted or superseded.

## Update rule

Every non-trivial code or workflow change must update at least one of:

- progress log;
- decision log;
- module checklist;
- relevant module documentation;
- docs index.

If code behavior and docs disagree, verify the code/runtime evidence and update the stale doc. Do not create a second conflicting truth source.

## Progress log entry format

```text
## YYYY-MM-DD - <round/task name>

Scope:
- ...

Changed:
- ...

Verification:
- command -> result

Known issues:
- ...

Next:
- ...
```

## Decision log entry format

```text
## DEC-YYYYMMDD-<short-id>: <decision title>

Decision:
- ...

Reason:
- ...

Alternatives considered:
- ...

Consequences:
- ...
```

## Design notes rule

Use `design_notes.md` for current thinking that is not yet a stable contract. Once a design becomes required behavior, promote it into a specific contract or module document.

## Report requirement

At task completion, the agent must report what documentation was updated. If no documentation changed in a non-trivial slice, the task is incomplete unless the task packet explicitly says docs are not required.
