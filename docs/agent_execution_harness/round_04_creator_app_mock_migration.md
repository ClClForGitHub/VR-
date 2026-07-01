# Round 04: Creator App Mock Migration

## Objective

Migrate the locked v0.5 React/Vite frontend prototype into the repository as the
new Creator App mock. This advances the user-facing frontend reset from design
handoff to runnable project code while keeping backend APIs, model-viewer, and
public UI replacement for later slices.

## Required Reading

```text
AGENTS.md
docs/README.md
docs/olddocs/repo_layout.md
docs/agent_execution_harness/README.md
docs/agent_execution_harness/task_packet_template.md
docs/agent_execution_harness/runtime_flow_rules.md
docs/agent_execution_harness/live_test_policy.md
docs/agent_execution_harness/documentation_maintenance.md
docs/image23d_frontend_FULL_design_handoff_v0_5/image23d_frontend_design_research/README_INDEX.md
docs/image23d_frontend_FULL_design_handoff_v0_5/image23d_frontend_design_research/10_react_prototype/v0_1_componentized/README.md
docs/image23d_frontend_FULL_design_handoff_v0_5/image23d_frontend_design_research/10_react_prototype/v0_1_componentized/docs/FRONTEND_IMPLEMENTATION_REPORT_v0_5.md
docs/image23d_frontend_FULL_design_handoff_v0_5/image23d_frontend_design_research/10_react_prototype/v0_1_componentized/docs/PROTOTYPE_USAGE_GUIDE_v0_5.md
docs/image23d_frontend_FULL_design_handoff_v0_5/image23d_frontend_design_research/10_react_prototype/v0_1_componentized/docs/BACKEND_INTEGRATION_PLAN_v0_5.md
docs/image23d_frontend_FULL_design_handoff_v0_5/image23d_frontend_design_research/10_react_prototype/v0_1_componentized/docs/CODEX_REACT_IMPLEMENTATION_PROMPTS_v0_5.md
```

## Allowed File Scope

```text
web/creator_app/
docs/README.md
docs/agent_execution_harness/round_04_creator_app_mock_migration.md
docs/agent_execution_harness/progress_log.md
```

## Forbidden Shortcuts

- Do not modify `web/runtime_console/` or replace the public UI in this round.
- Do not connect real backend APIs in this round.
- Do not replace `GlbViewerShell` with model-viewer in this round.
- Do not directly edit runtime `state.json`, `summary.json`,
  `frontend_status.json`, or runtime logs to fake progress.
- Do not treat mock UI or fixture assets as live backend/model evidence.
- Do not add a parallel runtime state store, artifact store, queue, viewer, or
  service wrapper.
- Do not run live model generation or non-dry-run Blender MCP calls.

## Concrete Tasks

1. Copy the componentized v0.5 React prototype into `web/creator_app/`.
2. Preserve the planned structure: `src/api`, `src/components`, `src/screens`,
   `src/data`, `src/styles`, `public/mock-assets`, and `public/design-renders`.
3. Keep the app on mock data and keep `RuntimeAdapter` as a future integration
   boundary only.
4. Install frontend dependencies for `web/creator_app/` and generate the local
   lockfile if needed.
5. Run a build or static check to prove the migrated mock project compiles.
6. Start the local dev server and verify that the mock app can be served.
7. Update documentation with the current migration status and commands.

## Tests

Mandatory:

```bash
cd web/creator_app
npm install
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

Optional if the dev server is running:

```bash
curl -I http://127.0.0.1:5173/
```

## Live-Test Plan

No live model call is allowed in this packet.

This round may run only local frontend dependency installation, static build,
and local Vite dev-server smoke checks.

## Acceptance Criteria

- [x] `web/creator_app/package.json` exists.
- [x] `web/creator_app/src/` contains the componentized prototype.
- [x] `web/creator_app/public/mock-assets/` and
  `web/creator_app/public/design-renders/` exist.
- [x] `npm run build` passes from `web/creator_app/`.
- [x] A local Vite mock server can serve the app.
- [x] Documentation records that this is mock-only and does not replace the old
  public UI yet.

## Completion Notes

Completed on 2026-07-01.

Verification:

```text
cd web/creator_app && npm install -> added 64 packages, audited 65 packages, found 0 vulnerabilities
cd web/creator_app && npm run build -> vite build passed, 47 modules transformed
cd web/creator_app && npm run dev -- --host 127.0.0.1 --port 5173 -> served at http://127.0.0.1:5173/
curl -I http://127.0.0.1:5173/ -> HTTP/1.1 200 OK
```

Live calls:

```text
No live model calls or non-dry-run Blender MCP calls were run.
```

## Final Report Requirements

Report:

- summary;
- changed files;
- `git diff --stat`;
- `git status --short`;
- test commands and outputs;
- live calls run, or explicitly no live calls;
- errors/blockers;
- next recommended step.
