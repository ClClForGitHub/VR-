# Live Test Readiness Matrix

Status: Round04C proved the structured live concept executor with the
`codex_self_mcp_image2` backend. Local reference images are attached through a
fresh child Codex session that must call `view_image` and produce
`input_image` payload evidence before image generation. The official codex MCP
tool still has no native `images[]` parameter.

| Live stage | Required approval | Inputs | Required output evidence | Ready? | Notes |
| --- | --- | --- | --- | --- | --- |
| Live LLM SceneSpec / ConceptPromptPack | User approval for live provider call. | User text, reference bindings, identity research evidence when needed. | Provider request/response JSON, parsed Pydantic output, state candidate/apply evidence, errors if any. | Prepared, not executed. | Prompt rules and planner validation now require reference-scope and identity evidence boundaries. |
| Image MCP `subject_concept` | User approval for image generation. | Subject prompt and required input image paths for `image_guided` requirements. | `live_generation_calls.jsonl`, output image file, artifact record, sha256, metadata input image paths, attachment manifest, child Codex `view_image` payload evidence. | Ready for concept canary. | Round04C converts unsupported local formats such as AVIF to PNG `view_path` while preserving the original user input path and sha256. |
| Image MCP `scene_concept` | User approval for image generation. | Scene-only prompt and scene refs if present. | `live_generation_calls.jsonl`, scene concept artifact, metadata input image paths. | Ready for concept canary. | Text-to-image scene concept completed in `case_03_lunar_rover`. |
| Image MCP `target_render` | User approval for image generation. | Generated subject/scene concept image paths from `source_requirement_ids`. | `live_generation_calls.jsonl`, final preview artifact, source requirement mapping, metadata source image paths, child Codex `view_image` payload evidence for generated concept refs. | Ready for concept canary. | Round04C target render uses generated subject and scene concepts as visual references, not pasted collage inputs. |
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

Round04C evidence:

- Probe: `outputs/runs/round04c_probe/live_image_backend_probe.json`.
- Canary: `outputs/runs/round04_live_user_samples/case_03_lunar_rover/`.
- Concept worker completed with 3 successful live generation calls, 3 generated
  image artifacts, 3 asset-library rows, handoff-apply status `applied`, and
  `frontend_status.json` at `current_stage=concept_approval`.
- The case status is `partial` only because the concept canary does not start
  downstream Hunyuan3D/HY-World/Blender stages.

Do not count any stage complete without command boundary, output directory,
state/checkpoint update, summary/frontend status, and verification result.
