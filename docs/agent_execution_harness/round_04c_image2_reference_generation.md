# Round04C Image2 Reference Generation

Round04C closes the Round04B concept-generation blocker by proving a local
reference-image path that reaches the child Codex visual context before image
generation.

## Implemented Boundary

- Added `agent_runtime/image2_reference_adapter.py` as the reusable image2
  adapter for codex-self reference generation.
- Kept the existing `ConceptImageBackend` and `runtime_worker` `live_image`
  path; the default live backend is now `codex_self_mcp_image2`.
- Kept `codex_self_mcp` as the legacy prompt-only guarded backend.
- Did not modify the external `/home/team/zouzhiyuan/codex-self-mcp` helper.

The official codex MCP tool still has only a string `prompt` entrypoint and no
native `images[]` field. Round04C therefore uses a fresh child Codex session per
concept requirement. The child session must call `view_image` for every
attachment `view_path` before generating the image.

## Attachment Contract

Every live generation call records an `attachment_manifest` with:

- `label`
- original `path`
- `mime_type`
- `sha256`
- `role`
- optional `image_id`
- optional `source_requirement_id`
- `view_path`
- `view_mime_type`
- `view_sha256`

The original uploaded file remains the user input path. If the original file is
not reliably accepted by the child visual tool, the adapter creates a PNG
`view_path` under:

```text
<run_dir>/runtime_worker/live_image/reference_views/<requirement_id>/
```

For the lunar-rover canary, the uploaded AVIF remains in
`input_image_paths`, while the child Codex views the converted PNG. Log parsing
requires both:

```text
view_image_tool_call
raw_response_item.function_call_output with type=input_image
```

A `view_image_tool_call` whose output says the image could not be processed is
not accepted as image-guided evidence.

## Prompt Rules

Subject concept:

```text
Image 1 is the user-provided subject reference. Preserve identity, silhouette,
proportions, major colors, materials, and defining details. Generate one clean
subject-only concept suitable as a Hunyuan3D source image, with neutral/simple
background and the full object visible.
```

Scene concept:

```text
Generate a scene-only concept with clear environment layout, ground plane,
lighting direction, and props. Do not include hero subjects unless explicitly
requested.
```

Target render:

```text
Images 1..N are generated subject and scene concept references from this same
run. Use them as visual references, not pasted collage pieces. Generate one new
coherent target render showing the intended final composition.
```

## Probe Result

Command:

```bash
python scripts/probe_live_image_backend.py --write-report outputs/runs/round04c_probe/live_image_backend_probe.json
```

Result:

```text
backend: codex_self_mcp_image2
text_to_image: true
image_guided_single_reference: true
multi_image_composite: true
structured_file_attachments: true
agent_view_image_reference: true
agent_view_image_then_generate: true
native_images_parameter: false
live_acceptance_ready: true
probe_report_path: outputs/runs/round04c_probe/live_image_backend_probe.json
```

## Canary Result

Command:

```bash
python scripts/run_round04_live_user_samples.py --case case_03_lunar_rover --live --overwrite --max-concept-regens 1
```

Result:

```text
script_ok: true
case_status: partial
concept_worker_status: completed
successful_call_count: 3
subject_concept_images: 1
scene_concept_images: 1
target_render_images: 1
handoff_apply_status: applied
asset_library_count: 3
frontend_current_stage: concept_approval
```

The case status remains `partial` only because this Round04B/Round04C canary
does not start downstream Hunyuan3D, HY-World/WorldMirror, or Blender stages.
That downstream non-execution is not an image2 concept-generation blocker.

Evidence:

```text
outputs/runs/round04_live_user_samples/case_03_lunar_rover/live_generation_calls.jsonl
outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_worker_summary.json
outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_handoff_apply_summary.json
outputs/runs/round04_live_user_samples/case_03_lunar_rover/state.json
outputs/runs/round04_live_user_samples/case_03_lunar_rover/frontend_status.json
outputs/runs/round04_live_user_samples/case_03_lunar_rover/case_live_report.json
outputs/runs/round04_live_user_samples/case_03_lunar_rover/case_report.md
```

## Final Canary Call Summary

```text
subject_concept:subject_lunar_rover
  generation_mode: image_guided
  input_image_paths: runtime_console/uploads/upload_03ee3dc61d7e_image_001.avif
  attachment role: subject_reference
  mime_type: image/avif
  view_path: runtime_worker/live_image/reference_views/...png
  output_image_path: runtime_worker/live_image/01_subject_concept_subject_lunar_rover.png
  ok: true

scene_concept:1
  generation_mode: text_to_image
  output_image_path: runtime_worker/live_image/02_scene_concept_1.png
  ok: true

target_render:final_preview
  generation_mode: multi_image_composite
  source_requirement_ids: subject_concept:subject_lunar_rover, scene_concept:1
  source_image_paths: 01_subject_concept_subject_lunar_rover.png, 02_scene_concept_1.png
  output_image_path: runtime_worker/live_image/03_target_render_final_preview.png
  ok: true
```

Child Codex log evidence:

```text
subject log: view_image payload_count=1, image_generation_end=1
scene log: image_generation_end=1
target log: view_image payload_count=2, image_generation_end=1
```

## Verification

```bash
python -m py_compile agent_runtime/image2_reference_adapter.py agent_runtime/concept_image_execution.py agent_runtime/runtime_worker.py scripts/probe_live_image_backend.py tests/test_image2_reference_attachment_live_contract.py
python -m pytest tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py tests/test_image2_reference_attachment_live_contract.py -q
python scripts/probe_live_image_backend.py --write-report outputs/runs/round04c_probe/live_image_backend_probe.json
python scripts/run_round04_live_user_samples.py --case case_03_lunar_rover --live --overwrite --max-concept-regens 1
```

Results:

```text
py_compile: passed
targeted Round04C tests: 10 passed
probe: exit 0, live_acceptance_ready=true
real canary: exit 0, ok=true, status=partial, concept worker completed
```

