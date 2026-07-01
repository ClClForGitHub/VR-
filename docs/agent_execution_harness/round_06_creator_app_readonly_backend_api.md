# Round 06: Creator App Read-Only Backend API

## Objective

Connect the v0.5 Creator App to the real runtime-console read-only backend API
while preserving mock fallback. This round ends at real backend API display:
run list, selected run bundle, file URL normalization, and product-facing
ViewModel mapping. Write operations, model-viewer, and public UI replacement
remain later slices.

## Required Reading

```text
AGENTS.md
docs/README.md
docs/agent_execution_harness/README.md
docs/agent_execution_harness/task_packet_template.md
docs/agent_execution_harness/runtime_flow_rules.md
docs/agent_execution_harness/live_test_policy.md
docs/agent_execution_harness/documentation_maintenance.md
docs/agent_execution_harness/round_04_creator_app_mock_migration.md
docs/agent_execution_harness/round_05_creator_app_responsive_polish.md
web/creator_app/docs/BACKEND_INTEGRATION_PLAN_v0_5.md
web/creator_app/docs/CODEX_REACT_IMPLEMENTATION_PROMPTS_v0_5.md
tools/runtime_console_server.py
agent_runtime/runtime_runs.py
```

## Allowed File Scope

```text
web/creator_app/package.json
web/creator_app/package-lock.json
web/creator_app/index.html
web/creator_app/src/
web/creator_app/scripts/
web/creator_app/docs/
docs/agent_execution_harness/round_06_creator_app_readonly_backend_api.md
docs/agent_execution_harness/progress_log.md
```

## Forbidden Shortcuts

- Do not implement chat, upload, user-action, loop, or any POST write path.
- Do not replace `GlbViewerShell` with model-viewer in this round.
- Do not modify `web/runtime_console/` or switch the public entrypoint.
- Do not let UI components read raw `state.json` directly; use
  `RuntimeAdapter` and a normalized ViewModel.
- Do not edit runtime `state.json`, `summary.json`, `frontend_status.json`, or
  logs to fake backend progress.
- Do not run live model generation or non-dry-run Blender MCP calls.

## Concrete Tasks

1. Implement `RuntimeAdapter` read-only methods for runs, bundles, and file
   URLs, with robust JSON/error handling.
2. Add `normalizeRuntimeBundle(rawBundle, adapter)` to produce a
   CreatorRunViewModel consumed by UI components.
3. Keep mock fallback when no backend is configured or the backend is
   unreachable.
4. Wire `App` / shell/screens to receive ViewModel data without changing
   workflow semantics.
5. Add a backend smoke script that can start or use the runtime console, verify
   read-only endpoints, and verify the Creator App renders real run metadata.
6. Run build, screenshot smoke, and backend read-only smoke.
7. Record the mock/live backend boundary and verification evidence.

## Tests

Mandatory:

```bash
cd web/creator_app
npm run build
npm run smoke:screenshots
npm run smoke:backend-readonly
```

## Live-Test Plan

No live model call is allowed in this packet.

Read-only runtime-console status/API checks are allowed. They do not mutate
runtime state and do not count as live generation.

## Acceptance Criteria

- [x] Creator App still runs on mock data without a backend.
- [x] With runtime-console API available, Creator App can show a real run list
  and normalized selected-run metadata.
- [x] File links in normalized data use `/api/runs/<run_key>/file?path=...`
  when relative file paths exist.
- [x] `npm run build` passes.
- [x] `npm run smoke:screenshots` passes.
- [x] `npm run smoke:backend-readonly` passes or explains a read-only backend
  availability blocker.
- [x] Documentation records that no POST/write/model-viewer/public-entrypoint
  work was done.

## Completion Notes

Completed on 2026-07-01.

Verification:

```text
cd web/creator_app && npm run build -> passed; Vite transformed 53 modules
cd web/creator_app && npm run smoke:screenshots -> passed; 8 mock screenshots checked
  output: run_logs/frontend_checks/creator_app_round05_20260701T104232Z
cd web/creator_app && npm run smoke:backend-readonly -> passed
  backend: http://127.0.0.1:18093
  selected run: 20260630_live_user_examples_114143Z
  output: run_logs/frontend_checks/creator_app_backend_readonly_20260701T103920Z
Playwright check against existing runtime console:
  http://127.0.0.1:5173/?api_base=http%3A%2F%2F127.0.0.1%3A8093#delivery
  source=backend, run options=50, file cards=6, has runtime file link=true
```

Live calls:

```text
No live model calls, write API calls, or non-dry-run Blender MCP calls were run.
Only read-only GET checks against runtime-console API were used.
```

## Final Report Requirements

Report:

- summary;
- changed files;
- `git diff --stat`;
- `git status --short`;
- test commands and outputs;
- backend smoke endpoint and run key used;
- live calls run, or explicitly no live calls;
- errors/blockers;
- next recommended step.
