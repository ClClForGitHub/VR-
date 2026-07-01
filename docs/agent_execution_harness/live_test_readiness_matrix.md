# Live Test Readiness Matrix

Status: Round04B added the structured live concept executor and backend probe.
The current default backend (`codex_self_mcp`) is not live-acceptance ready for
image-guided or multi-image concept generation because local-file attachment and
multi-image composition support are not proven.

| Live stage | Required approval | Inputs | Required output evidence | Ready? | Notes |
| --- | --- | --- | --- | --- | --- |
| Live LLM SceneSpec / ConceptPromptPack | User approval for live provider call. | User text, reference bindings, identity research evidence when needed. | Provider request/response JSON, parsed Pydantic output, state candidate/apply evidence, errors if any. | Prepared, not executed. | Prompt rules and planner validation now require reference-scope and identity evidence boundaries. |
| Image MCP `subject_concept` | User approval for image generation. | Subject prompt and required input image paths for `image_guided` requirements. | `live_generation_calls.jsonl`, output image file, artifact record, sha256, metadata input image paths. | Blocked by backend capability. | Round04B executor resolves real input paths and blocks when backend cannot attach them. |
| Image MCP `scene_concept` | User approval for image generation. | Scene-only prompt and scene refs if present. | `live_generation_calls.jsonl`, scene concept artifact, metadata input image paths. | Executor ready; mixed canary blocked preflight. | Prompt-only text-to-image is supported by codex-self, but mixed structured handoffs do not run partial text-only generation when required image/multi support is missing. |
| Image MCP `target_render` | User approval for image generation. | Generated subject/scene concept image paths from `source_requirement_ids`. | `live_generation_calls.jsonl`, final preview artifact, source requirement mapping, metadata input image paths. | Blocked by backend capability. | Target render requires `multi_image_composite`; codex-self helper has no proven multi-image attachment API. |
| Hunyuan3D subject GLB | User approval for model generation. | Selected subject concept artifact URI/path, subject id, Hunyuan3D profile/tool args. | Service job id/status logs, saved GLB, QA evidence, handoff-apply record, updated state/checkpoint/frontend status. | Prepared, not executed. | Subject handoff now has `subject_asset_generation` with selected concepts and apply schema. |
| HY-World / WorldMirror scene asset | User approval for scene generation. | Active scene concept / target render selection, environment SceneSpec, tool args. | Upload/reconstruct event ids, output directory, scene GLB/metadata, handoff-apply record, updated state/checkpoint/frontend status. | Prepared, not executed. | Scene handoff now has `scene_asset_generation` with selected source images and apply schema. |
| Blender assembly | User approval for non-dry-run Blender compose/export when applicable. | `active_assembly_selection`, selected subject GLBs, selected scene asset, placement hints. | `.blend`, viewer GLB/glTF, `scene_state.json`, preview render, tool-call log, updated `frontend_status.json`. | Prepared, not executed. | Controller payload prefers active selection; raw Blender MCP remains behind domain/runtime tool boundaries. |
| Frontend action submission | UI/API approval for frontend slice. | `frontend_status.json` action payload examples. | `runtime_asset_action.jsonl`, checkpoint, rebuilt `runtime_plan.json`, updated `frontend_status.json`. | Backend prepared, UI not implemented. | Round03 added derived backend payload examples only; no UI controls were added. |

Round04 minimum live smoke should run in this order:

1. live LLM or controlled fixture-to-state apply for one approved sample;
2. image generation for subject/scene/target render with recorded image inputs;
3. selected concept to Hunyuan3D GLB;
4. selected scene/target reference to scene asset or registered proxy scene;
5. Blender assembly/export/preview through existing domain/runtime paths.

Round04B evidence:

- Probe: `outputs/runs/round04b_probe/live_image_backend_probe.json`.
- Canary: `outputs/runs/round04_live_user_samples/case_03_lunar_rover/`.
- The canary status is `blocked`, with 3 structured call records and no fake
  output image paths.

Do not count any stage complete without command boundary, output directory,
state/checkpoint update, summary/frontend status, and verification result.
