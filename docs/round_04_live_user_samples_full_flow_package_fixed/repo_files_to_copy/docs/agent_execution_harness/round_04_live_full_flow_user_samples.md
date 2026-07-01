# Round 04: Live Full-Flow User Samples

## Purpose

Round 04 turns the Round 03 semantic/runtime contract into a real user-sample execution flow. The goal is not another dry-run proof. The goal is to run the provided scripted user samples through the actual backend workflow and produce inspectable artifacts, reports, and frontend-visible state.

## Required Flow

```text
sample markdown + reference images
  -> runtime run
  -> chat/user turns + upload/reference bindings
  -> identity research evidence when named IP/characters appear
  -> SceneSpec
  -> ConceptPromptPack + typed image requirements
  -> live image generation calls with actual image inputs
  -> asset_library concept records
  -> scripted concept approval/rejection/rework
  -> selected concept -> live subject model generation
  -> selected scene concept/target -> live scene asset generation/adaptation
  -> scripted model approval/rejection/rework
  -> active_assembly_selection
  -> live Blender assembly/export/preview
  -> frontend_status/runtime API snapshot
  -> per-case report with counts and issues
```

## What Counts As Live Evidence

A case can be marked `completed` only if it has real output artifacts from the actual configured services or explicitly approved real runtime adapters:

- generated concept image files;
- Hunyuan3D subject GLB files when the case needs subject assets;
- scene asset output directory / scene GLB / adapter output;
- Blender `.blend` or equivalent saved scene;
- `viewer_scene.glb` and `scene_state.json`;
- preview render PNG;
- `frontend_status.json` and runtime API snapshot;
- `case_live_report.json` and `case_report.md`.

Dry-run, fixture output, delegated-only records, or manually written JSON cannot be counted as completion.

## Model Review Gate

The user samples include model-stage approval/rejection. If the current runtime has no model-review gate, implement the smallest controlled backend path that supports it. The implementation must:

- keep state mutation behind runtime/user/action functions;
- record user feedback as structured state and logs;
- route rejection to regeneration or asset re-generation without restarting intake;
- expose the pending action and available payloads through `frontend_status.json` and runtime API.

## Reference Image Handling

All references from the sample markdown must be placed in the prescribed input location and registered through upload/reference-binding flow. Image generation calls must record the actual file paths passed as image inputs. Text-only mention of `@图片1` is not sufficient.

## Case Reports

Each case must produce:

```text
outputs/runs/round04_live_user_samples/<case_id>/case_live_report.json
outputs/runs/round04_live_user_samples/<case_id>/case_report.md
```

The report must include counts for concept images, subject models, scene assets, Blender/viewer outputs, frontend visibility, and failure/blocker notes.

