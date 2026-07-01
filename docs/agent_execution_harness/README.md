# Agent Execution Harness

This directory is the execution harness for coding agents working on the image23D Blender scene agent. It is intentionally short, operational, and stricter than broad design notes.

## Purpose

The project is a user-facing workflow, not a pile of scaffolding. Every non-trivial implementation slice must move through the real business chain or clearly state that it is only a dry-run, fixture, or design-only slice.

Core product chain:

```text
user chat + uploaded/reference images
  -> explicit reference bindings
  -> SceneSpec
  -> ConceptPromptPack + ConceptImageRequirement[]
  -> concept images for review
  -> user approval or feedback
  -> selected subject concept image(s)
  -> subject GLB assets
  -> selected scene concept / scene asset
  -> Blender assembly
  -> viewer export + preview render
  -> frontend_status.json
  -> delivery package
```

## Non-negotiable execution rules

1. `state.json` is the authoritative state file for a run.
2. `frontend_status.json` is a derived UI handoff, not a second state source.
3. Long jobs that are delegated are not completed. `delegated` means waiting for worker/sub-agent/model evidence.
4. `dry-run` and fixture results must be labelled as dry-run/fixture evidence. They do not prove a live model or Blender run.
5. User gates must use the runtime user-action path, not direct state mutation.
6. Worker results must come back through handoff-apply or an equivalent controlled apply path, not direct edits to `state.json`.
7. Image-guided generation must record actual image input paths, such as `input_image_paths`; text saying “use image 1” is insufficient.
8. Generated binaries and outputs stay under `outputs/runs/<run_id>/` and must not be committed.
9. A slice is not done until it records what the frontend can show and how the next phase is reached.
10. When live services are used, the command boundary, output directory, artifacts, and verification result must be recorded.

## Required work style

Each task must be expressed as a task packet using `task_packet_template.md`. The task packet must define:

- objective;
- required reading;
- allowed file scope;
- forbidden shortcuts;
- concrete steps;
- tests and live-test policy;
- acceptance criteria;
- required final report.

## Documentation requirements

Every non-trivial slice must update at least one relevant documentation surface:

- `docs/agent_execution_harness/progress_log.md` for execution progress;
- `docs/agent_execution_harness/decision_log.md` for choices that affect architecture or workflow;
- `docs/agent_execution_harness/design_notes.md` for temporary design reasoning that should not be hidden in chat only;
- the specific module document when one exists;
- `docs/README.md` when a new doc entrypoint is added.

## Current Harness Module Docs

- `round_02_backend_asset_library_selection.md`: backend asset review and selection state contract.
- `round_03_core_pipeline_semantics.md`: core pipeline semantic contract from intake through handoff/frontend status.
- `core_pipeline_test_matrix.md`: dry-run/delegated semantic test matrix.
- `live_test_readiness_matrix.md`: Round04 live-call evidence checklist.

## Next Priority

Round04 should run an explicitly approved live smoke through the existing runtime boundaries:

```text
live LLM / fixture-backed SceneSpec
  -> real image generation with recorded image inputs
  -> selected concept to Hunyuan3D
  -> selected scene/target reference to HY-World or registered scene asset
  -> Blender assembly/export/preview
  -> frontend_status.json + delivery evidence
```

Do not treat delegated, dry-run, or fixture evidence as live generation evidence.
