# Round 06: Creator App Read-Only Backend API

## Objective

Connect the v0.5 Creator App on port 5173 to the real Creator App read-only
backend mounted under the same origin at `/api/creator`, while preserving mock
fallback. This round ends at real backend API display: project list, selected
project bundle, file URL normalization, and product-facing ViewModel mapping.
Write operations, model-viewer, and public UI replacement remain later slices.

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
web/creator_app/server/creatorBackendPlugin.js
web/creator_app/src/api/runtimeAdapter.js
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

1. Implement `RuntimeAdapter` read-only methods for projects, bundles, and
   file URLs, with robust JSON/error handling.
2. Add `normalizeRuntimeBundle(rawBundle, adapter)` to produce a
   CreatorRunViewModel consumed by UI components.
3. Keep mock fallback when no backend is configured or the backend is
   unreachable.
4. Wire `App` / shell/screens to receive ViewModel data without changing
   workflow semantics.
5. Add a backend smoke script that verifies the 5173 same-origin read-only
   endpoints and verifies the Creator App renders real project metadata.
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

Read-only 5173 same-origin API checks are allowed. They do not mutate runtime
state and do not count as live generation.

## Acceptance Criteria

- [x] Creator App still runs on mock data without a backend.
- [x] With the 5173 same-origin Creator App backend available, Creator App can
  show a real project list and normalized selected-project metadata.
- [x] Creator App can request the real Round04D concept collection with
  `GET /api/creator/projects?collection=round04d_concepts` so the project
  center shows the 12 concept cases instead of legacy all-runs discovery.
- [x] File links in normalized data use
  `/api/creator/projects/<project_key>/file?path=...`
  when relative file paths exist.
- [x] `npm run build` passes.
- [x] `npm run smoke:screenshots` passes.
- [x] `npm run smoke:backend-readonly` passes or explains a read-only backend
  availability blocker.
- [x] Documentation records that no POST/write/model-viewer/public-entrypoint
  work was done.

## Completion Notes

Completed on 2026-07-01.

Superseded on 2026-07-02: the current Creator App user backend is no longer the
old runtime-console service. The active entrypoint is 5173 with same-origin
`/api/creator`; the historical notes below are retained only as prior-round
evidence and must not be used as the current frontend contract.

Verification:

```text
cd web/creator_app && npm run build -> passed; Vite transformed 53 modules
cd web/creator_app && npm run smoke:screenshots -> passed; 8 mock screenshots checked
  output: run_logs/frontend_checks/creator_app_round05_20260701T104232Z
CREATOR_APP_BASE_URL=http://127.0.0.1:5173 npm run smoke:backend-readonly -> passed
  backend: http://127.0.0.1:5173/api/creator
  project count: 12
  output: run_logs/frontend_checks/creator_app_backend_readonly_20260702T093937Z
Playwright check against 5173 same-origin backend:
  http://127.0.0.1:5173/#concept-review
  source=backend, project options=12, concept images load through /api/creator
```

Follow-up on 2026-07-02:

```text
Creator App default run collection -> round04d_concepts
GET /api/creator/projects?collection=round04d_concepts -> 12 Round04D concept sample cases
direct project_key loading no longer requires the project to appear in the current list
FINAL_PREVIEW_IMAGE is consumed as a concept/final-preview image artifact
```

Live calls:

```text
No live model calls, write API calls, or non-dry-run Blender MCP calls were run.
Only read-only GET checks against the 5173 same-origin Creator App API were
used.
```

## Final Report Requirements

Report:

- summary;
- changed files;
- `git diff --stat`;
- `git status --short`;
- test commands and outputs;
- backend smoke endpoint and project key used;
- live calls run, or explicitly no live calls;
- errors/blockers;
- next recommended step.
