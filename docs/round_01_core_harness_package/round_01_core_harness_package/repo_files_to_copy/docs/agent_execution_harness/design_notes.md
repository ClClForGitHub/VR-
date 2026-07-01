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
