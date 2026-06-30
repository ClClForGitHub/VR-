# Repository Layout And Tracking Rules

Updated: 2026-06-28

## Goal

Keep this workspace usable as an engineering project, not a pile of generated assets.
Git should track source, tests, lightweight docs, scripts, and small reusable assets.
Git should not track models, generated outputs, local environments, API keys, or service caches.

## Top-Level Directory Roles

- `agent_runtime/`
  - Project-owned runtime code.
  - Track in git.

- `tests/`
  - Project-owned unit/workflow tests.
  - Track in git.

- `tools/`
  - Project-owned scripts/tools for Blender preview, composition, export, and viewer helpers.
  - Track in git.

- `scripts/`
  - Project-owned service start/status helpers.
  - Track in git.

- `web/`
  - Project-owned viewer/runtime web code.
  - Track in git unless large generated assets appear.

- `docs/`
  - Project-owned planning, progress, contracts, and evidence summaries.
  - Track in git.

- `assets/`
  - Small reusable project assets.
  - Track only if assets are lightweight and intentionally reusable.

- `third_party/`
  - External reference/source snapshots needed for implementation.
  - Track only lightweight source/reference files that are actually needed.
  - Do not track third-party build outputs, caches, dist folders, or vendored model weights.

- `blender_scene_agent_docs_v1_zh_v0_3/`
  - User-provided design docs/source plan.
  - Track if this repo is meant to preserve the V1 design package.

- `Hunyuan3D-2.1/`, `HY-World-2.0/`
  - External service repositories.
  - Do not track in this repo. They have their own source/provenance.

- `models/`
  - Local model weights/cache.
  - Never track in this repo.

- `outputs/`
  - Generated smoke outputs, run artifacts, previews, packages, checkpoints.
  - Never track in this repo.

- `run_logs/`
  - Runtime logs.
  - Never track in this repo.

- `.venv*/`, `.venv-*/`
  - Local Python environments.
  - Never track in this repo.

## Output Placement Rule

New runs should use:

```text
outputs/runs/<YYYYMMDD>_<short_task>/
  state.json
  summary.json
  frontend_status.json
  tool_call_log.json
  checkpoints/
  artifacts/
  logs/
```

Existing historical `outputs/v1_landing_*` directories are left in place for evidence continuity.
Do not move or delete them without a separate cleanup decision.

## Commit Rule

First commit should include only:

- `.gitignore`
- `agent_runtime/`
- `tests/`
- `tools/`
- `scripts/`
- `web/`
- `docs/`
- selected small `assets/`
- selected lightweight `third_party/` sources if intentionally needed
- `blender_scene_agent_docs_v1_zh_v0_3/` if the design package should be versioned here

Before first commit:

```bash
git status --short
git status --ignored --short
git check-ignore -v <path>
```

Do not commit:

- `.env*`
- API keys
- `.venv*`
- `models/`
- `outputs/`
- `run_logs/`
- Hunyuan3D/HY-World service repos
- `.ckpt`, `.bin`, `.safetensors`, `.pt`, `.pth`, `.onnx`, `.engine`
- service caches, dist/build outputs, `__pycache__`

## Immediate Directory Cleanup Policy

No automatic deletion.

Current large generated/service areas are intentionally ignored:

- `models/` around 23G
- `outputs/` around 2.4G
- `Hunyuan3D-2.1/` around 1.1G
- `HY-World-2.0/` around 1.1G
- root model files around 500M each

Only clean these after a separate evidence-first cleanup request.
