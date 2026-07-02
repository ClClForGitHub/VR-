"""Command builders that wrap existing Blender/GLB scripts.

These helpers do not run Blender by themselves. They centralize command
construction so workflow nodes can reuse existing scripts instead of inventing
parallel execution paths.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


DEFAULT_BLENDER_PATH = Path("/home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender")


class ScriptCommand(BaseModel):
    argv: list[str] = Field(min_length=1)
    cwd: str
    description: str


def _resolve_root(root: str | Path) -> Path:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    return root_path


def _require_file(path: str | Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} does not exist or is not a file: {resolved}")
    return resolved


def _resolve_output(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def build_render_glb_preview_command(
    root: str | Path,
    input_glb: str | Path,
    output_png: str | Path,
    output_blend: str | Path,
    *,
    blender_path: str | Path = DEFAULT_BLENDER_PATH,
) -> ScriptCommand:
    root_path = _resolve_root(root)
    blender = _require_file(blender_path, "Blender executable")
    script = _require_file(root_path / "tools/render_glb_preview.py", "render_glb_preview.py")
    glb = _require_file(input_glb, "input GLB")
    png = _resolve_output(output_png)
    blend = _resolve_output(output_blend)
    return ScriptCommand(
        cwd=str(root_path),
        description="Render an existing GLB preview through tools/render_glb_preview.py",
        argv=[
            str(blender),
            "-b",
            "--python",
            str(script),
            "--",
            str(glb),
            str(png),
            str(blend),
        ],
    )


def build_compose_blender_scene_command(
    root: str | Path,
    scene_glb: str | Path,
    asset_glb: str | Path,
    output_png: str | Path,
    output_blend: str | Path,
    *,
    assembly_plan_json: str | Path | None = None,
    asset_glbs: list[str | Path] | tuple[str | Path, ...] | None = None,
    blender_path: str | Path = DEFAULT_BLENDER_PATH,
) -> ScriptCommand:
    root_path = _resolve_root(root)
    blender = _require_file(blender_path, "Blender executable")
    script = _require_file(root_path / "tools/compose_blender_scene.py", "compose_blender_scene.py")
    scene = _require_file(scene_glb, "scene GLB")
    asset = _require_file(asset_glb, "asset GLB")
    extra_assets = [_require_file(path, "asset GLB") for path in (asset_glbs or [])]
    if not extra_assets:
        extra_assets = [asset]
    png = _resolve_output(output_png)
    blend = _resolve_output(output_blend)
    plan = _resolve_output(assembly_plan_json) if assembly_plan_json is not None else None
    argv = [
        str(blender),
        "-b",
        "--python",
        str(script),
        "--",
        str(scene),
        str(asset),
        str(png),
        str(blend),
    ]
    if plan is not None:
        argv.append(str(plan))
    if len(extra_assets) > 1:
        argv.extend(["--asset-glbs-json", json.dumps([str(path) for path in extra_assets], ensure_ascii=True)])
    return ScriptCommand(
        cwd=str(root_path),
        description="Compose an existing scene GLB and subject GLB(s) through tools/compose_blender_scene.py",
        argv=argv,
    )


def build_export_viewer_scene_command(
    root: str | Path,
    input_blend: str | Path,
    viewer_glb: str | Path,
    scene_state_json: str | Path,
    *,
    blender_path: str | Path = DEFAULT_BLENDER_PATH,
) -> ScriptCommand:
    root_path = _resolve_root(root)
    blender = _require_file(blender_path, "Blender executable")
    script = _require_file(root_path / "tools/export_viewer_scene.py", "export_viewer_scene.py")
    blend = _require_file(input_blend, "input blend")
    glb = _resolve_output(viewer_glb)
    state_json = _resolve_output(scene_state_json)
    return ScriptCommand(
        cwd=str(root_path),
        description="Export viewer_scene.glb and scene_state.json through tools/export_viewer_scene.py",
        argv=[
            str(blender),
            "-b",
            "--python",
            str(script),
            "--",
            str(blend),
            str(glb),
            str(state_json),
        ],
    )
