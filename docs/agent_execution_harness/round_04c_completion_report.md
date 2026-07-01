# Round04C Completion Report

## 1. Summary

- Completed:
  - Added a reusable codex-self image2 adapter that passes local reference
    images through child-agent `view_image` before image generation.
  - Added attachment manifests with original paths, MIME, sha256, roles, and
    separate `view_path`/`view_sha256` for image formats that need conversion.
  - Updated the live image backend to `codex_self_mcp_image2`.
  - Proved `case_03_lunar_rover` generates subject concept, scene concept, and
    target render images with handoff-apply artifacts, asset-library lineage,
    and frontend ready evidence.
- Not completed:
  - Hunyuan3D, HY-World/WorldMirror, and Blender downstream stages were not
    started by this concept canary.
- Scope deviations:
  - No external codex-self-mcp helper files were modified.
  - No new state store, artifact store, viewer, Hunyuan3D wrapper, HY-World
    wrapper, or Blender path was added.

## 2. Branch / Commit / Push

```text
branch: round04c-image2-reference-generation
implementation_commit_sha: to be filled after commit
github_branch_url: https://github.com/ClClForGitHub/VR-/tree/round04c-image2-reference-generation
github_commit_url: final pushed commit URL will be provided after commit
pushed: pending at report write time
```

## 3. Image2 Backend Used

```text
backend_name: codex_self_mcp_image2
backend_path_or_command: agent_runtime/image2_reference_adapter.py via /home/team/zouzhiyuan/codex-self-mcp/scripts/call_codex_mcp.py/codex mcp-server
modified_external_helper: no
external_helper_files_modified: none
native_images_parameter: false
agent_view_image_reference: true
agent_view_image_then_generate: true
```

## 4. Attachment Contract Evidence

Subject concept call:

```json
{
  "requirement_id": "subject_concept:subject_lunar_rover",
  "output_type": "subject_concept",
  "generation_mode": "image_guided",
  "input_image_paths": [
    "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_console/uploads/upload_03ee3dc61d7e_image_001.avif"
  ],
  "attachment_manifest": [
    {
      "label": "Image 1",
      "role": "subject_reference",
      "mime_type": "image/avif",
      "view_mime_type": "image/png"
    }
  ],
  "output_image_path": "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_worker/live_image/01_subject_concept_subject_lunar_rover.png",
  "ok": true
}
```

Scene concept call:

```json
{
  "requirement_id": "scene_concept:1",
  "output_type": "scene_concept",
  "generation_mode": "text_to_image",
  "attachment_manifest": [],
  "output_image_path": "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_worker/live_image/02_scene_concept_1.png",
  "ok": true
}
```

Target render call:

```json
{
  "requirement_id": "target_render:final_preview",
  "output_type": "target_render",
  "generation_mode": "multi_image_composite",
  "source_requirement_ids": [
    "subject_concept:subject_lunar_rover",
    "scene_concept:1"
  ],
  "source_image_paths": [
    "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_worker/live_image/01_subject_concept_subject_lunar_rover.png",
    "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_worker/live_image/02_scene_concept_1.png"
  ],
  "attachment_manifest_count": 2,
  "output_image_path": "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_worker/live_image/03_target_render_final_preview.png",
  "ok": true
}
```

## 5. Canary Result

```text
case_id: case_03_lunar_rover
run_dir: /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover
status: partial
concept_worker_status: completed
subject_concepts: 1
scene_concepts: 1
target_renders: 1
artifact_ids: live_subject_concept_subject_lunar_rover, live_scene_concept_1, live_target_render_final_preview
asset_library_count: 3
frontend_status_ready: true; current_stage=concept_approval; ready_artifact_ids present for all 3 concept requirements
```

## 6. Output Files

```text
live_generation_calls_jsonl: /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/live_generation_calls.jsonl
state_json: /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/state.json
frontend_status_json: /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/frontend_status.json
case_live_report_json: /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/case_live_report.json
case_report_md: /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/case_03_lunar_rover/case_report.md
probe_report_json: /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04c_probe/live_image_backend_probe.json
```

## 7. Tests

```bash
python -m py_compile agent_runtime/image2_reference_adapter.py agent_runtime/concept_image_execution.py agent_runtime/runtime_worker.py scripts/probe_live_image_backend.py tests/test_image2_reference_attachment_live_contract.py
python -m pytest tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py tests/test_image2_reference_attachment_live_contract.py -q
python scripts/probe_live_image_backend.py --write-report outputs/runs/round04c_probe/live_image_backend_probe.json
python scripts/run_round04_live_user_samples.py --case case_03_lunar_rover --live --overwrite --max-concept-regens 1
python -m pytest -q
```

Results:

```text
py_compile: passed
targeted Round04C tests: 10 passed
probe: exit 0, live_acceptance_ready=true
real canary: exit 0, ok=true, status=partial, concept worker completed
full pytest: 410 passed
```

## 8. Downstream Status

Concept generation succeeded. The live sample script reports case status
`partial` because the Round04B/Round04C concept canary does not start downstream
Hunyuan3D, HY-World/WorldMirror, or Blender assembly stages. This is recorded in
`case_live_report.json` as:

```text
live_execution_blocked: downstream Hunyuan3D/HY-World/Blender stages are not started by the Round04B concept canary
```

## 9. Remaining Risks

- The official codex MCP tool still has no native `images[]` parameter; the
  accepted boundary is agent-mediated `view_image` attachment evidence.
- Live image generation quality still needs human review at the concept approval
  gate before downstream Hunyuan3D/HY-World/Blender work.
- The 12-sample live run should start only after this Round04C concept path is
  accepted and the downstream command boundary is explicitly requested.
