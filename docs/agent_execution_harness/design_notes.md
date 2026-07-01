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

## Round 03 core pipeline semantics landed

The dry-run/delegated backend now has a clearer business-chain contract:

- `ConceptImageRequirement` separates `subject_concept`, `scene_concept`, and
  `target_render`.
- Subject references and scene references are scoped separately and validated as
  `image_guided` requirements.
- `target_render` is a `multi_image_composite` that depends on generated
  subject/scene requirement ids.
- Named identity subjects require explicit `identity_notes` evidence or
  clarification/blocking before generation prompts are accepted.
- Concept feedback creates `ReviewPatch` records and routes to regeneration
  without restarting intake/SceneSpec work.
- Rejected/old concept assets stay in `asset_library` and can still be selected
  for subject model generation.
- Subject-asset and scene-asset handoff JSON now has explicit selected inputs,
  upload rules, runtime tool args, and apply-result schemas.
- Blender assembly payloads continue to prefer `active_assembly_selection`.
- `frontend_status.json` exposes action payload examples for backend review and
  selection actions, but remains derived from state.

Open design for Round04:

- exact live smoke sample and reference-image files;
- provider/model profile choices for live LLM and image generation;
- Hunyuan3D profile and timeout policy for first live GLB;
- HY-World/WorldMirror or proxy-scene decision for first live scene asset;
- whether frontend UI controls land before or after the first live smoke.
