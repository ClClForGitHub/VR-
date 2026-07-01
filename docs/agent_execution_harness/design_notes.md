# Agent Execution Harness Design Notes

This file holds short design notes that are not yet stable contracts.

## Chat-thread asset library direction

The product should treat a chat thread as an inspectable creative workspace. All useful assets should remain visible unless intentionally archived:

- uploaded reference images;
- subject concept images;
- scene concept images;
- target render images;
- subject GLB assets;
- scene/world assets;
- Blender preview renders;
- viewer scenes;
- delivery packages.

Rejected or criticized assets should not disappear automatically. They should become available library items with review status such as `rejected`, `archived`, or `available_for_reuse`.

The next stable design should define:

- asset library item schema;
- asset lineage fields;
- per-asset review status;
- user selection status;
- assembly selection schema;
- frontend_status fields for display.

## Round 02 landed backend contract

The backend contract now exists in code:

- `AssetLibraryItem` records artifact-backed assets plus review, selection, and
  lineage metadata.
- `AssemblySelection` records the active user-selected subject models, scene
  asset, target render, and placement hints for Blender assembly.
- `runtime_asset_actions.py` is the controlled mutation path for review and
  selection actions.
- `frontend_status.json` exposes a derived `asset_library`,
  `active_assembly_selection`, and `available_asset_actions` view.

Important behavior:

- `rejected` does not delete an asset.
- Selecting a concept for subject generation does not erase its review status.
- Subject-asset workers receive selected subject concepts explicitly.
- Blender assembly payloads prefer `active_assembly_selection` when present.

Open design for the next frontend/UI round:

- card/list presentation for library items;
- action affordances for review status and selection;
- multi-subject selection ergonomics;
- visual indication of source/derived lineage;
- placement-hint editing before Blender assembly.
