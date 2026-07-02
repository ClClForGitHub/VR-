# Round 02 Backend Asset Library Selection

Date: 2026-07-01

## Objective

Implement the backend fact source for a chat-thread asset library and user asset
selection, without adding a parallel artifact store, service client, queue, or
frontend-only state.

This round lands the backend contract for:

- keeping generated/reference assets visible in `AgentProjectState.asset_library`;
- preserving rejected assets for later reuse;
- selecting a subject concept image for Hunyuan3D subject generation;
- selecting subject model(s), scene asset, target render, and placement hints
  for Blender assembly;
- exposing the derived view through `frontend_status.json`;
- writing controlled runtime action logs, summaries, checkpoints, and rebuilt
  runtime plans.

## Implemented State Contract

`agent_runtime/state.py` now defines:

- `AssetLibraryItem`
- `AssemblyObjectSelection`
- `AssemblySelection`

`AgentProjectState` now owns:

- `asset_library: list[AssetLibraryItem]`
- `active_assembly_selection: AssemblySelection | None`

These fields stay in the existing state/checkpoint path. They are not separate
files and they do not replace `ArtifactRecord`.

## Controlled State Writers

`agent_runtime/state_views.py` allows the new fields only through bounded nodes:

- `ImageGenerationExecutor`
- `SubjectAssetGenerationExecutor`
- `SceneAssetAdapter`
- `BlenderAssemblyResultIngestor`
- `RuntimeAssetAction`

This keeps selection/edit state out of raw frontend mutation and direct manual
`state.json` editing.

## Runtime Asset Actions

New module: `agent_runtime/runtime_asset_actions.py`.

Supported actions:

- `set_asset_review_status`
- `select_concept_for_subject_generation`
- `select_asset_for_assembly`

Persisted outputs:

- `state.json`
- `summary.json`
- `frontend_status.json`
- `runtime_asset_action.jsonl`
- `runtime_asset_action_summary.json`
- `checkpoints/`
- rebuilt `runtime_plan.json` unless disabled by caller

The current Creator App backend exposes this through 5173 same-origin routes:

```text
POST /api/creator/projects/<project_key>/asset-action
GET  /api/creator/projects/<project_key>/runtime-asset-action
```

## Handoff Apply Integration

Existing handoff-apply paths now populate and extend the asset library:

- concept image apply registers `subject_concept`, `scene_concept`, and
  `target_render` library items;
- subject asset apply registers `subject_model` and links back to the selected
  subject concept image when present;
- scene asset apply registers adapted `scene_asset` artifacts;
- Blender apply registers `blender_scene`, `viewer_scene`, and preview
  `target_render` artifacts with active assembly selection lineage.

## Controller And Delegation Behavior

Controller behavior:

- subject asset payload includes
  `selected_concept_artifact_ids_by_subject` and `selected_source_image_ids`
  when the user selected concepts;
- Blender import payload prefers `active_assembly_selection` over default
  first-available subject/scene assets;
- legacy `subject_id`, `subject_asset_id`, and `scene_asset_id` fields remain
  present for the existing script executor.

Delegated subject-asset handoff behavior:

- handoff JSON and prompt inputs include `selected_subject_concepts`;
- workers are instructed to use selected concepts first, then fall back to
  approved concept artifacts.

## Frontend Status Contract

`frontend_status.json` now exposes:

- `asset_library`
- `active_assembly_selection`
- `available_asset_actions`

This is a derived UI handoff. The authoritative source remains `state.json`.

## Test Evidence

Targeted Round 02 command:

```bash
python -m pytest tests/test_asset_library.py tests/test_runtime_asset_actions.py tests/test_frontend_status.py tests/test_runtime_handoff_apply.py tests/test_controller.py -q
```

Result:

```text
25 passed in 0.43s
```

Adjacent runtime/API checks:

```bash
python -m pytest tests/test_runtime_delegation.py tests/test_runtime_console_server.py tests/test_runtime_runs.py tests/test_runtime_jobs.py -q
```

Result:

```text
26 passed in 1.76s
```

Full suite:

```bash
python -m pytest -q
```

Result:

```text
377 passed in 5.71s
```

## Live Service Boundary

No live image generation, Hunyuan3D generation, HY-World generation, or non-dry-run
Blender MCP call was run for this round.

Read-only status scripts were run and recorded in the Round 02 completion
report.
