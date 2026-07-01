# Task Packet Template

Use this template for every non-trivial coding-agent task.

## Title

`Round NN: <short task name>`

## Objective

State the product outcome in one paragraph. Explain which user workflow phase this advances.

## Required reading

List exact files the agent must read before making changes.

```text
AGENTS.md
docs/agent_execution_harness/README.md
...
```

## Allowed file scope

List files or directories that may be changed. If a change outside the scope is needed, the agent must stop and report it instead of changing it silently.

```text
docs/...
agent_runtime/...
tests/...
```

## Forbidden shortcuts

Every task packet must include relevant forbidden shortcuts. Use at least these defaults when applicable:

- Do not directly edit `state.json`, `summary.json`, `frontend_status.json`, or runtime logs to fake progress.
- Do not treat `dry-run`, fixture, or `delegated` evidence as live completion.
- Do not bypass `user-action` at concept review or Blender preview gates.
- Do not bypass `handoff-apply` or a controlled apply path for worker results.
- Do not mention reference images only in text when an image-guided generation requires actual `input_image_paths`.
- Do not add a parallel state store, artifact store, queue, viewer, or service wrapper without documenting why the existing path is insufficient.
- Do not run live model generation unless this packet includes an explicit live command boundary and the user has approved it.

## Concrete tasks

Use numbered steps. Each step should produce a file, test, state field, artifact, or documented decision.

1. ...
2. ...
3. ...

## Tests

List mandatory tests and expected evidence. Include at least one user-flow or state-transition test when the task changes workflow behavior.

```bash
python -m pytest <targeted tests> -q
```

If full test suite is practical:

```bash
python -m pytest -q
```

## Live-test plan

If no live model call is allowed, write:

```text
No live model call is allowed in this packet.
```

If a live call is expected, specify:

```text
Approval required: yes
Service status checks:
  - <command>
Live command:
  - <exact command>
Output directory:
  - outputs/runs/<run_id>/...
Required artifacts:
  - state.json
  - summary.json
  - frontend_status.json
  - logs / generation_calls.jsonl / tool_call_log.json
Success criteria:
  - ...
Stop criteria:
  - ...
```

## Acceptance criteria

A task is accepted only when each criterion is satisfied.

- [ ] Required files changed.
- [ ] Required tests pass or failures are explained.
- [ ] State / artifact / frontend status changes are documented.
- [ ] Documentation updated.
- [ ] Final report completed.

## Final report requirements

The agent must report:

- summary;
- changed files;
- `git diff --stat`;
- `git status --short`;
- test commands and outputs;
- live calls run or explicitly not run;
- errors/blockers;
- next recommended step.
