# V1 Codex-Self Robot Demo Report - 2026-06-28

## Summary

This run proved a more realistic concept-to-delivery path than the first sample
demo:

```text
Qwen ConceptPromptPlanner smoke
  -> ConceptPromptPack state application
  -> codex-self-mcp image generation
  -> project image extraction and concept registration
  -> live Hunyuan3D subject GLB
  -> existing HY-World scene GLB
  -> Blender compose
  -> viewer export/check
  -> delivery package
```

Run root:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/
```

Important boundary:

- The concept image is a real generated file extracted from
  `codex-self-mcp` JSONL output.
- The subject asset is a real Hunyuan3D shape-only GLB.
- The scene asset is still an existing HY-World output, not a fresh live
  HY-World generation.
- Blender placement is still smoke-level, not final layout intelligence.

## Concept Planning

Live Qwen smoke:

```text
provider=qwen
model=qwen3.7-max
endpoint=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
response_format_json=true
summary=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_llm_node_qwen_smoke/summary.json
```

Applied prompt-pack state:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_llm_node_qwen_smoke/state_with_prompt_pack.json
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_llm_node_qwen_smoke/prompt_pack_apply_summary.json
```

## Generated Concept Image

Source image extracted from codex MCP log:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/generated_robot_concept.png
```

Registered concept artifact:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/concept_seed/artifacts/subject_concept_image/codex_self_robot_concept_001.png
```

Concept seed summary:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/concept_seed/summary.json
```

## Live Hunyuan3D Subject Asset

Job:

```text
job_id=9c8c6a2a-b637-4180-a27b-2ebfcde9e974
status=completed_shape_only
```

Output:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/subject_asset_status_save/subject_assets/codex_self_robot_asset_001.glb
```

Result:

```text
ok=true
qa_ok=true
qa_score=1.0
size=37MB
summary=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/subject_asset_status_save/summary.json
```

## Blender And Viewer

Scene input:

```text
/home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb
```

Result:

```text
local-e2e ok=true
executed_stages=compose,export_viewer,viewer_check
viewer_model_ok=true
viewer_runtime_ok=true
viewer_scene_object_count=7
```

Artifacts:

```text
blend=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/compose/composed_scene.blend
preview=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/compose/composed_preview.png
viewer_scene=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/viewer_export/viewer_scene.glb
scene_state=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/viewer_export/scene_state.json
```

Viewer URL:

```text
http://127.0.0.1:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/viewer_export/viewer_scene.glb
```

## Delivery Package

Result:

```text
ok=true
issues=[]
zip=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/delivery_package/package/codex_self_robot_demo_20260628.zip
```

The package contains the `.blend`, preview PNG, viewer GLB, viewer state JSON,
subject GLB, scene GLB, metadata, and version manifest.

## Known Issues

- Hunyuan3D was run shape-only and untextured.
- The scene asset was reused from an existing HY-World output.
- The robot appears in the composed scene, but automatic placement/scale is
  still basic.
- The run is not yet one continuous LangGraph agent graph.
- User approval gates and a polished review UI are still represented as state
  contracts and files, not an end-user interface.
