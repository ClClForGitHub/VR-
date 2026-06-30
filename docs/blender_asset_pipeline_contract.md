# Blender Asset Pipeline Contract

## Goal

Convert generated scene images and generated object or character assets into one Blender scene controlled by an LLM agent.

## Required Pipeline

1. GPT image model generates multiple images of the same scene.
2. WorldMirror reconstructs the scene from those images.
3. Hunyuan3D-2.1 generates object or character assets.
4. Blender imports the WorldMirror scene first, then imports Hunyuan3D assets.
5. The LLM agent places, scales, and rotates imported assets inside the Blender scene.
6. Blender saves the final `.blend` file and optional preview renders.

## Implementation Reuse Requirement

This workspace already contains working infrastructure for several parts of the pipeline. New implementation work must start by checking the existing scripts, tools, local services, outputs, and logs before creating replacement code.

Reuse candidates include:

- the current WorldMirror and Hunyuan3D local service layout;
- the Blender 5.1.2 runtime and Blender Lab MCP bridge;
- existing service status/start/stop scripts under `scripts/`;
- existing Blender import, render, and GLB inspection helpers under `tools/`;
- the viewer-scene export helper `tools/export_viewer_scene.py`;
- the GLB viewer under `web/` and `tools/glb_viewer_server.py`;
- verified artifacts under `outputs/` and runtime evidence under `run_logs/`.

Only add a new wheel when the existing one is missing, incompatible with the required contract, or too risky to adapt. Record that reason in the task plan or progress notes.

## WorldMirror Input Contract

WorldMirror should receive a folder of still images or a video.

For GPT-generated images, use same-scene multi-view images:

- Minimum: 3 images.
- Preferred: 4 to 8 images.
- Images must describe the same room, layout, and object identities.
- Camera viewpoints should be different but physically plausible.
- Avoid changing furniture geometry, object count, wall layout, lighting direction, or style between views.

The biggest quality risk is inconsistent generated views. If the input images disagree, WorldMirror will still output a scene, but geometry will contain holes, floaters, warped surfaces, or duplicated structures.

## WorldMirror Output Contract

Primary Blender input:

- `scene.glb`

Required sidecar outputs:

- `camera_params.json`
- `metadata.json` or equivalent run summary when available

Useful debug or optional outputs:

- `depth/`
- `normal/`
- `points.ply`
- `gaussians.ply`

Use `scene.glb` as the default Blender scene input. `gaussians.ply` is not the primary Blender scene input.

Recommended WorldMirror export options for clean Blender import:

- `show_camera=False`
- `show_mesh=True`
- `filter_ambiguous=True`
- `filter_sky_bg=False` for indoor scenes unless sky/background removal is needed

If cameras are needed for debugging or camera-aware placement, export a separate debug GLB with `show_camera=True`.

## Hunyuan3D-2.1 Output Contract

Primary Blender input:

- one asset `.glb` per generated object or character

Preferred final asset input:

- textured asset `.glb`

Shape-only fallback:

- white/untextured mesh `.glb`

Optional sidecars:

- source prompt
- source image
- generation metadata
- texture/material metadata if available

Import Hunyuan3D assets after the WorldMirror scene. The LLM agent should not assume the generated asset scale is meaningful. Normalize asset scale relative to the reconstructed scene before placement.

Do not treat `white_mesh.glb` or files produced by `/shape_generation` as final colored assets. These are geometry-only outputs. Use them only for shape validation, collision checks, rough layout, or as a fallback when texture generation is unavailable.

For colored assets, run the texture-enabled Hunyuan3D path. Current findings:

- Legacy service on port `8090` was launched with `--disable_tex`; it produces shape-only white meshes.
- Current service on port `8091` is the Hunyuan3D FastAPI texture service.
- Texture generation requires the Hunyuan3D Paint model and DINOv2-giant.
- Hunyuan3D Paint weights are present locally under `/home/team/zouzhiyuan/image23D_Agent/models/tencent/Hunyuan3D-2.1/hunyuan3d-paintpbr-v2-1`.
- DINOv2-giant is present locally under `/home/team/zouzhiyuan/image23D_Agent/models/facebook/dinov2-giant`.
- Texture validation passed through FastAPI and Blender import/render.

## Blender Import Contract

Current verified Blender executable:

```bash
/home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender
```

Current verified version:

```text
Blender 5.1.2
Python 3.13.9
```

Current MCP control path:

```text
Codex MCP server: blender_lab
Blender-side bridge: 127.0.0.1:9876
```

Import order:

1. Import WorldMirror `scene.glb`.
2. If scene meshes have a vertex color attribute named `Color`, connect it to material base color.
3. Import each Hunyuan3D asset `.glb`.
4. Normalize asset scale using scene bounds and asset bounds.
5. Apply requested placement transform from `assembly_plan.json` when present,
   otherwise use the conservative fallback placement.
6. Save `.blend`.
7. Render preview for verification.

Every placement action should be recorded as structured data:

```json
{
  "asset_id": "character_001",
  "source_glb": "/absolute/path/to/asset.glb",
  "location": [0.0, 0.0, 0.0],
  "rotation_euler": [0.0, 0.0, 0.0],
  "scale": [1.0, 1.0, 1.0],
  "placement_note": "Placed on floor near dining table"
}
```

Current local compose contract:

```json
{
  "plan_id": "compose_plan_subject_001_v1",
  "planner": "deterministic_v1",
  "subject_id": "subject_001",
  "scene_asset_id": "workflow_scene_glb",
  "subject_asset_id": "workflow_subject_glb",
  "target_region": "front_left",
  "target_region_normalized": [-0.18, 0.18],
  "target_height_ratio": 0.42,
  "camera_direction": [1.25, -1.55, 0.85],
  "camera_distance_multiplier": 2.8,
  "camera_ortho_scale_factor": 1.55,
  "render_resolution": [1400, 900]
}
```

`workflow_runner local-e2e` writes this as `compose/assembly_plan.json` and
passes it to `tools/compose_blender_scene.py`. The plan is recorded in
`summary.json`, tool-call arguments, and compose-stage checkpoint metadata.

Do not assume WorldMirror coordinates are metric. Treat the scene coordinate system as arbitrary unless a calibration step is added.

## 3DGS Boundary

WorldMirror also outputs Gaussian Splatting PLY files.

Use 3DGS only as an optional visual asset path:

- `gaussians.ply`
- `gaussians_kiri.ply`

Blender can import these PLY files as mesh/point data with attributes, but it will not render them as Gaussian splats without a compatible 3DGS plugin.

The downloaded KIRI plugin requires Blender 5.1.0 or newer, so it is now compatible with the current Blender 5.1.2 runtime. It is still optional; `scene.glb` remains the default Blender scene asset.

For this pipeline, `scene.glb` is the default scene asset. 3DGS is optional.

## MMD/VMD Animation Boundary

Hunyuan3D textured GLB assets are static by default. They do not have armatures, skinning weights, MMD bone names, VMD-compatible morphs, or facial shape keys.

The current V0 GLB-to-VMD bridge is documented in:

```text
/home/team/zouzhiyuan/image23D_Agent/docs/glb_to_mmd_rigging_notes.md
```

Verified V0 path:

```text
static Hunyuan3D GLB
-> coarse generated armature
-> coarse spatial vertex groups
-> optional MMD-style bone names
-> MMD Tools VMD import
-> animated GLB export
```

This proves the route is technically open, but it should not be treated as production animation quality. The current rough result can move, but hats, props, hair, skirts, and dense single-mesh accessories may deform incorrectly because the source GLB lacks semantic part separation and proper skinning.

For production-quality dance animation, prefer an already rigged MMD `.pmx/.pmd` model. If Hunyuan3D GLB must be used, add a dedicated rigging stage with better skeleton placement, weight transfer, accessory separation, IK, and expression shape keys before expecting VMD dance quality.

## Verified Artifacts

WorldMirror scene imported into Blender:

```text
/home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_152539_953073/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb
```

Hunyuan3D asset imported into the same Blender scene:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/doro_hunyuan3d/doro_dororong_hunyuan3d_shape.glb
```

Combined Blender scene:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/blender_preview/dining_table_with_hunyuan3d_asset.blend
```

Combined preview render:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/blender_preview/dining_table_with_hunyuan3d_asset.png
```

## Current Verified Runtime

WorldMirror/Hunyuan environment:

```text
conda env: hunyuan3d21
Python: 3.10.20
Torch: 2.5.1+cu124
CUDA: 12.4
```

WorldMirror Gradio service:

```text
CUDA_VISIBLE_DEVICES=0
URL: http://10.2.16.106:8081/
```

Hunyuan3D-2.1 FastAPI texture service:

```text
CUDA_VISIBLE_DEVICES=0
URL: http://10.2.16.106:8091/
```

Verified Hunyuan3D FastAPI textured asset:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/hunyuan3d_api_textured_smoke/doro_api_textured_after_load_mesh_fix.glb
/home/team/zouzhiyuan/image23D_Agent/outputs/hunyuan3d_api_textured_smoke/doro_api_textured_after_load_mesh_fix_preview.png
```

GPU selector note:

```text
Use CUDA_VISIBLE_DEVICES=0 for the idle A40.
On this server, the physical nvidia-smi index 0 has a bad device handle, so nvidia-smi physical indices are misleading.
Validate the service GPU with PyTorch/CUDA rather than trusting nvidia-smi -i 0.
```

Service scripts:

```bash
/home/team/zouzhiyuan/image23D_Agent/scripts/start_a40_services.sh
/home/team/zouzhiyuan/image23D_Agent/scripts/status_a40_services.sh
/home/team/zouzhiyuan/image23D_Agent/scripts/stop_a40_services.sh
```

Blender validation:

- WorldMirror GLB import passed.
- Hunyuan3D GLB import passed.
- Combined scene save passed.
- Combined preview render passed.
