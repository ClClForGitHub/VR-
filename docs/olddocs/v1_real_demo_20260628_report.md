# V1 Real Demo Report - 2026-06-28

## Summary

This run moved from scaffold-only validation to a real local artifact chain.

Run root:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/
```

What actually ran:

- concept image artifact registration through `concept-seed`;
- live Hunyuan3D submit/status/save for one subject GLB;
- deterministic subject-asset QA;
- Blender compose with an existing HY-World scene GLB and the live Hunyuan3D subject GLB;
- viewer export and viewer runtime/model check;
- delivery package zip creation.

Important boundary:

- A ChatGPT/session image generation call was made in the conversation, but the tool did not expose a local file path for project ingestion.
- The project artifact chain therefore used the existing local sample image at `Hunyuan3D-2.1/assets/example_images/example_000.png` for the first reproducible P1 run.
- The Hunyuan3D run was `shape_only` / no texture for speed.

## Service Snapshot

Before live generation:

- Hunyuan3D FastAPI: `http://127.0.0.1:8091`, health/openapi reachable.
- HY-World/WorldMirror: `http://127.0.0.1:8081`, config reachable.
- GLB viewer: `http://127.0.0.1:8092`, index and API reachable.
- CUDA visible device: A40, about 29GB free out of 44GB reported by the project status script.

## P1 Concept Seed

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner concept-seed \
  --image-path /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/example_images/example_000.png \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/concept_seed \
  --subject-id demo_robot \
  --source-image-id demo_robot_concept_001 \
  --project-id v1_real_demo \
  --thread-id 20260628_p0_real_demo \
  --prompt "single stylized robot character, white background, full body, three-quarter view"
```

Result:

- `ok=true`
- phase: `SUBJECT_ASSET_GENERATION`
- artifact: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/concept_seed/artifacts/subject_concept_image/demo_robot_concept_001.png`
- state: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/concept_seed/state.json`
- summary: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/concept_seed/summary.json`
- frontend status: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/concept_seed/frontend_status.json`

## P2 Live Hunyuan3D Subject Asset

Submit command:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner subject-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/subject_asset_live \
  --subject-id demo_robot \
  --source-image-id demo_robot_concept_001 \
  --image-path /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/concept_seed/artifacts/subject_concept_image/demo_robot_concept_001.png \
  --asset-id demo_robot_asset_001 \
  --hunyuan-base-url http://127.0.0.1:8091 \
  --timeout 300 \
  --stages submit \
  --num-inference-steps 30 \
  --face-count 50000 \
  --no-texture \
  --no-randomize-seed
```

Job id:

```text
f72e91e2-e600-40a2-8f37-4f44f817f87f
```

Final save/QA result:

- Hunyuan3D status: `completed_shape_only`
- output GLB: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/subject_asset_live_save/subject_assets/demo_robot_asset_001.glb`
- GLB size: about 22MB
- deterministic QA: `pass`
- QA score: `1.0`
- suggested action: `accept`
- summary: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/subject_asset_live_save/summary.json`

## P4 Blender And Viewer

Scene input:

```text
/home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb
```

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/subject_asset_live_save/subject_assets/demo_robot_asset_001.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer \
  --viewer-base-url http://127.0.0.1:8092 \
  --compose-timeout 300 \
  --export-timeout 180 \
  --viewer-timeout 10
```

Result:

- `ok=true`
- executed stages: `compose`, `export_viewer`, `viewer_check`
- `.blend`: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/compose/composed_scene.blend`
- preview PNG: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/compose/composed_preview.png`
- viewer GLB: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/viewer_export/viewer_scene.glb`
- scene state: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/viewer_export/scene_state.json`
- viewer URL: `http://127.0.0.1:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/viewer_export/viewer_scene.glb`
- viewer model check: passed
- viewer scene object count: 7

## P6 Delivery Package

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner delivery-package \
  --state-json /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/state.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/delivery_package \
  --package-id delivery_20260628_p0_real_demo
```

Result:

- `ok=true`
- package zip: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/delivery_package/package/delivery_20260628_p0_real_demo.zip`
- package checks: all true
- package includes `.blend`, preview PNG, viewer GLB, viewer state JSON, subject GLB, and scene GLB.

## Known Issues

- The first ChatGPT/session-generated concept image was visible in chat but not available as a local file, so it was not registered as a project artifact.
- The reproducible concept seed used an existing local sample image, not a newly saved ChatGPT image.
- The Hunyuan3D subject GLB is shape-only and untextured.
- The assembled preview is a technical proof of pipeline execution, not a polished final scene.
- The scene asset was an existing HY-World output, not a fresh HY-World live generation from this run.
- `local-e2e` does not yet carry the earlier `ConceptBundle` state through to the Blender workflow; it starts a local assembly state from scene/subject GLBs.

## Next Concrete Fixes

1. Add a proper project image-generation provider or export path so ChatGPT/Qwen-generated images land directly under `outputs/runs/.../artifacts/`.
2. Run a textured Hunyuan3D subject generation on a deliberately simple white-background concept.
3. Carry `ConceptBundle` / subject metadata into the Blender assembly workflow instead of starting a fresh local state.
4. Run one fresh HY-World live scene generation only after choosing a small input and accepting the longer runtime.
