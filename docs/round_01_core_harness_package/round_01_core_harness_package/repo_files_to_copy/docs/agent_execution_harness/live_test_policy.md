# Live Test Policy

The project should move toward real user-flow tests and real model-service checks. However, live calls must be explicit, bounded, and recorded.

## Default rule

Do not run live Hunyuan3D, HY-World/WorldMirror, image generation, or non-dry-run Blender MCP calls unless the active task packet explicitly allows it and the user has approved that run.

## Required live command boundary

A live-test task packet must specify:

```text
Approval required: yes
Service status checks:
  - exact command(s)
Live command:
  - exact command(s)
Output directory:
  - outputs/runs/<date>_<short_goal>/...
Expected files:
  - state.json
  - summary.json
  - frontend_status.json
  - relevant artifacts
  - relevant JSONL logs
Success criteria:
  - concrete artifact and verification criteria
Stop criteria:
  - timeout, missing service, missing input, user gate, or error condition
```

## Preferred test ladder

Each implementation slice should choose the strongest practical test level:

1. Static/doc/schema test.
2. Unit test.
3. Runtime state-transition test.
4. Simulated user journey with fixture outputs.
5. Dry-run with real runtime entrypoint.
6. Live service smoke after explicit approval.
7. Full artifact-chain acceptance after explicit approval.

Do not jump to expensive live runs before a targeted state-transition or fixture user-journey test exists.

## Live evidence requirements

A live service result must record:

- exact command or API path;
- run directory;
- input files;
- output files;
- service job IDs or event IDs when available;
- generation parameters or profile ID;
- `state.json` and/or controlled apply result;
- `frontend_status.json` after apply;
- verification command and result;
- known issues.

## Status checks

Status checks are allowed when read-only. They do not count as live generation.

Useful read-only checks may include:

```bash
scripts/status_a40_services.sh || true
scripts/status_glb_viewer.sh || true
scripts/status_runtime_console.sh || true
scripts/status_blender51_lab_mcp_bridge.sh || true
```

## This harness round

Round 01 is documentation-only. It must not submit live generation jobs. It may define how future live tests are requested and recorded.
