# Runtime Environment Plan

## Current Decision

Use one compatible conda environment for GPU model services, and keep Blender as a separate executable runtime.

Do not force Blender into the same conda environment as WorldMirror and Hunyuan3D. Blender ships its own Python runtime and add-on ABI expectations. The stable boundary between model services and Blender should be files, primarily `.glb`.

## GPU Selection

Use:

```bash
CUDA_VISIBLE_DEVICES=0
```

On this server, the physical `nvidia-smi -i 0` device handle is broken, so `nvidia-smi` physical indices are misleading. CUDA/PyTorch confirms that `CUDA_VISIBLE_DEVICES=0` maps to the idle A40:

```text
device0 NVIDIA A40
free_total_gb approximately 44.05 / 44.34 before services
```

Use `scripts/status_a40_services.sh` for status checks because it validates the CUDA-visible device with PyTorch.

## Runtime Layout

| Component | Runtime | GPU | Port | Primary role |
| --- | --- | --- | --- | --- |
| WorldMirror | conda `hunyuan3d21` | `CUDA_VISIBLE_DEVICES=0` | `8081` | image/video to scene reconstruction |
| Hunyuan3D-2.1 FastAPI texture service | conda `hunyuan3d21` | `CUDA_VISIBLE_DEVICES=0` | `8091` | image to textured object GLB |
| Blender | `/home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender` | usually CPU/offscreen render unless needed | local MCP bridge `127.0.0.1:9876` | import GLBs, compose scene, save `.blend` |

## Existing Infrastructure Reuse Rule

Before implementing new orchestration, service wrappers, MCP clients, viewers, or Blender scripts, first inspect the existing project infrastructure and reuse it where it fits.

Minimum inventory for any non-trivial implementation:

- `docs/runtime_environment_plan.md`
- `docs/blender_asset_pipeline_contract.md`
- `scripts/start_a40_services.sh`
- `scripts/status_a40_services.sh`
- `scripts/start_blender51_lab_mcp_bridge.sh`
- `scripts/status_blender51_lab_mcp_bridge.sh`
- `scripts/status_glb_viewer.sh`
- `tools/compose_blender_scene.py`
- `tools/render_glb_preview.py`
- `tools/export_viewer_scene.py`
- `tools/glb_viewer_server.py`
- existing `Hunyuan3D-2.1`, `HY-World-2.0`, `third_party/`, `web/`, `outputs/`, and `run_logs/` evidence

If a new component overlaps with this inventory, document why reuse is insufficient before adding another implementation.

## Why This Split

WorldMirror and Hunyuan3D can share the same conda env because the currently verified stack is compatible:

```text
conda env: hunyuan3d21
Python: 3.10.20
Torch: 2.5.1+cu124
CUDA: 12.4
```

Blender should stay outside this env because:

- current local Blender is 5.1.2 with Python 3.13.9;
- the model env is Python 3.10 and PyTorch/CUDA-heavy;
- mixing Blender Python packages and model packages increases dependency risk;
- GLB import/export already provides a clean, tested interface.

## GLB Conversion Boundary

Hunyuan3D can optionally use Blender Python `bpy` for OBJ to GLB conversion, but `bpy` is not required for texture generation itself.

Current service path:

```text
Hunyuan3D texture generation -> textured OBJ + PBR texture maps -> create_glb_with_pbr_materials -> GLB
```

Blender path:

```text
OBJ/GLB -> Blender Python `bpy` import/export -> GLB or .blend
```

Practical difference:

- `bpy` gives Blender-native import/export behavior and is useful for final scene composition.
- The service-side PBR GLB conversion keeps the model conda environment independent from Blender's Python runtime.
- Geometry precision should not materially degrade just because `bpy` is absent. The main quality risks are mesh simplification, UV unwrap/baking, generated texture quality, and material-map conversion.
- Final validation should always import the produced GLB into Blender and render a preview.

## Model and Weight Paths

WorldMirror:

```text
/home/team/zouzhiyuan/image23D_Agent/HY-World-2.0
/home/team/zouzhiyuan/image23D_Agent/models/tencent/HY-World-2.0
```

Hunyuan3D-2.1:

```text
/home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1
/home/team/zouzhiyuan/image23D_Agent/models/tencent/Hunyuan3D-2.1
```

Current FastAPI service-level launch parameters:

```text
--texture-resolution 768
--max-num-view 8
--low_vram_mode
--cache-path /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/api_cache_gpu0_tex
```

Per-request Hunyuan3D generation defaults are represented in
`agent_runtime.runtime_profiles`, with `hq_textured_1m_768` as the default
high-quality profile and `fast_shape_50k_768` as a smoke/profile-debug option.
Do not confuse service texture resolution with per-request octree resolution;
both are currently `768` in the high-quality profiles.

DINOv2-giant for Hunyuan3D texture generation:

```text
/home/team/zouzhiyuan/image23D_Agent/models/facebook/dinov2-giant
```

Blender:

```text
/home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender
```

Blender MCP:

```text
MCP server: blender_lab
Bridge socket: 127.0.0.1:9876
Start script: /home/team/zouzhiyuan/image23D_Agent/scripts/start_blender51_lab_mcp_bridge.sh
Status script: /home/team/zouzhiyuan/image23D_Agent/scripts/status_blender51_lab_mcp_bridge.sh
```

## Service Commands

Start both GPU services on the idle A40:

```bash
/home/team/zouzhiyuan/image23D_Agent/scripts/start_a40_services.sh
```

Check status:

```bash
/home/team/zouzhiyuan/image23D_Agent/scripts/status_a40_services.sh
```

Stop both services:

```bash
/home/team/zouzhiyuan/image23D_Agent/scripts/stop_a40_services.sh
```

Current URLs:

```text
WorldMirror: http://10.2.16.106:8081/
Hunyuan3D-2.1 FastAPI texture: http://10.2.16.106:8091/
```

## Agent Integration Contract

The LLM agent should not import model libraries directly inside Blender. Use this order:

1. Call WorldMirror service or runner.
2. Take WorldMirror `scene.glb` as the Blender scene base.
3. Call Hunyuan3D FastAPI service for each object or character.
4. Take Hunyuan3D textured `.glb` as an importable Blender asset.
5. Launch Blender with a small Python script for import, placement, render, and `.blend` save.

This keeps the orchestration layer simple and makes failures local:

- WorldMirror failure is a reconstruction service failure.
- Hunyuan3D failure is an asset generation service failure.
- Blender failure is an import, placement, material, or render failure.

## Verified State

As of the current A40 deployment:

```text
WorldMirror /config responded on 8081.
Hunyuan3D-2.1 FastAPI `/health` responded on 8091.
CUDA_VISIBLE_DEVICES=0 reports NVIDIA A40.
CUDA free memory after services: approximately 30.28 / 44.34 GB.
```

Already verified earlier:

```text
WorldMirror GLB imported into Blender.
Hunyuan3D shape-only GLB imported into Blender.
Combined scene saves as .blend and renders preview.
```

Verified after FastAPI migration:

```text
Hunyuan3D FastAPI `/generate` with texture=true completed.
Texture generation took approximately 167.7 s; total request took approximately 170.4 s.
The service produced a PBR GLB with albedo, metallic, and roughness maps.
Blender imported the API-produced GLB and rendered a preview with visible texture color.
Current Blender control is through Blender 5.1.2 plus the official Blender Lab MCP bridge.
```

Verified artifacts:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/hunyuan3d_api_textured_smoke/doro_api_textured_after_load_mesh_fix.glb
/home/team/zouzhiyuan/image23D_Agent/outputs/hunyuan3d_api_textured_smoke/doro_api_textured_after_load_mesh_fix.blend
/home/team/zouzhiyuan/image23D_Agent/outputs/hunyuan3d_api_textured_smoke/doro_api_textured_after_load_mesh_fix_preview.png
```
