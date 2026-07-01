# Round 03 Core Pipeline Semantics

Status: implemented and verified on 2026-07-01.

## Purpose

Round 03 reconnects the Round 02 asset-library and selection work to the core image23D business chain:

```text
natural-language request + reference images
  -> explicit reference bindings
  -> SceneSpec
  -> ConceptPromptPack
  -> ConceptImageRequirement[]
  -> concept-generation handoff JSON
  -> concept image artifacts
  -> asset_library
  -> user review / reject / select / regenerate
  -> selected concept to subject model generation
  -> selected scene concept or target render to scene generation
  -> active_assembly_selection
  -> Blender assembly payload
  -> viewer/preview
  -> frontend_status
```

This round remains dry-run/delegated by default. No live LLM, image generation, Hunyuan3D, HY-World/WorldMirror, or non-dry-run Blender operation is part of the acceptance evidence.

## Verified Behavior

| Area | Expected behavior | Code evidence | Test evidence | Gap |
| --- | --- | --- | --- | --- |
| Natural language to SceneSpec | User text and explicit bindings enter typed intake and SceneSpec paths. Missing uploaded-image purpose blocks at intake. | `agent_runtime/reference_intake.py`, `agent_runtime/controller.py` | `tests/test_core_pipeline_semantics.py`, `tests/test_controller.py` | Live LLM SceneSpec compilation is Round04. |
| Concept requirements | Subject, scene, and target render are separate `ConceptImageRequirement` rows. Procedural props do not get subject prompts. | `agent_runtime/agent_prompts.py`, `agent_runtime/concept_planning.py` | `tests/test_concept_prompt_requirements.py` | None for dry-run contract. |
| Reference images | Subject refs become subject-only `image_guided` requirements; scene refs become scene-only `image_guided` requirements. | `agent_runtime/agent_prompts.py`, `agent_runtime/concept_planning.py` | `tests/test_core_pipeline_semantics.py`, `tests/test_concept_prompt_requirements.py`, `tests/test_runtime_context_and_file_contract.py` | Live MCP upload evidence is Round04. |
| Target render | `target_render` is `multi_image_composite` and depends on generated subject/scene requirements. | `agent_runtime/agent_prompts.py`, `agent_runtime/concept_planning.py` | `tests/test_core_pipeline_semantics.py`, `tests/test_concept_prompt_requirements.py` | None for dry-run contract. |
| IP/identity | Named identity subjects require `identity_notes` evidence or clarification/blocking; hidden memory is not accepted as fact. | `agent_runtime/agent_prompts.py`, `agent_runtime/concept_planning.py` | `tests/test_concept_prompt_requirements.py` | Live web/official-source evidence is Round04. |
| Concept rework | Concept feedback creates a pending `ReviewPatch`; controller routes to regeneration without restarting intake/spec. | `agent_runtime/runtime_user_actions.py`, `agent_runtime/controller.py`, `agent_runtime/concept_planning.py` | `tests/test_runtime_rework_flow.py` | No frontend UI control yet. |
| Asset selection | Rejected/old concept assets stay in `asset_library` and can be reselected. | `agent_runtime/runtime_asset_actions.py`, `agent_runtime/controller.py` | `tests/test_model_generation_selection_contract.py`, `tests/test_runtime_asset_actions.py` | No frontend UI control yet. |
| Model generation | Subject-asset runtime payload and delegated handoff prefer explicitly selected subject concept artifacts. | `agent_runtime/controller.py`, `agent_runtime/runtime_delegation.py` | `tests/test_model_generation_selection_contract.py`, `tests/test_runtime_context_and_file_contract.py`, `tests/test_runtime_delegation.py` | Live Hunyuan3D submission is Round04. |
| Scene generation | Scene-asset handoff prefers active scene concept / target render selections and exposes apply schema. | `agent_runtime/runtime_delegation.py` | `tests/test_runtime_context_and_file_contract.py` | Live HY-World/WorldMirror run is Round04. |
| Blender assembly | Controller payload uses `active_assembly_selection` for selected subject assets, scene asset, target render, and placements. | `agent_runtime/controller.py` | `tests/test_model_generation_selection_contract.py`, `tests/test_controller.py` | Non-dry-run Blender compose/export is Round04. |
| Frontend status | Derived status exposes phase/status, concept requirements, asset library, active selection, available actions, and backend payload examples. | `agent_runtime/frontend_status.py` | `tests/test_frontend_status_core_pipeline.py`, `tests/test_frontend_status.py` | Frontend UI controls are not in this round. |
| Agent context | Handoff JSON carries input files, SceneSpec, reference images/bindings, requirements, resolved image paths, source requirements, upload rules, and apply-result schemas. | `agent_runtime/runtime_delegation.py` | `tests/test_runtime_context_and_file_contract.py`, `tests/test_runtime_delegation.py` | Live worker result evidence is Round04. |

## Runtime Boundaries

- `state.json` remains authoritative.
- `frontend_status.json` remains a derived read model.
- `runtime_asset_actions.py` and `runtime_user_actions.py` are the controlled user mutation paths.
- Delegated handoff packages are context contracts, not completion evidence.
- Worker results still return through `runtime_handoff_apply.py`.

## Verification

- `python -m pytest tests/test_core_pipeline_semantics.py tests/test_concept_prompt_requirements.py tests/test_runtime_rework_flow.py tests/test_model_generation_selection_contract.py tests/test_runtime_context_and_file_contract.py tests/test_frontend_status_core_pipeline.py -q` -> 17 passed.
- `python -m pytest tests/test_concept_planning.py tests/test_runtime_delegation.py tests/test_runtime_asset_actions.py tests/test_runtime_user_actions.py tests/test_controller.py tests/test_frontend_status.py -q` -> 47 passed.
- `python -m pytest tests/test_natural_language_scene_fixtures.py::test_natural_language_scene_cases_run_to_delegated_generation -q` -> 9 passed.
- `python -m pytest -q` -> 394 passed.

Read-only status checks:

- `scripts/status_a40_services.sh` -> exit 0; torch saw one NVIDIA A40 and ports 8091/8081 were listening. `nvidia-smi` still reported an NVML device-handle error and existing logs include prior WorldMirror/Gradio path warnings.
- `scripts/status_glb_viewer.sh` -> exit 0; GLB viewer listening on 8092.
- `scripts/status_runtime_console.sh` -> exit 0; runtime console listening on 8093.
- `scripts/status_blender51_lab_mcp_bridge.sh` -> exit 0; Blender 5.1.2 MCP bridge socket open on 127.0.0.1:9876, with existing SSBO warnings in recent logs.
