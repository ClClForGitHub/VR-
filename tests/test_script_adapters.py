from pathlib import Path

import pytest

from agent_runtime.script_adapters import (
    build_compose_blender_scene_command,
    build_export_viewer_scene_command,
    build_render_glb_preview_command,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"placeholder")


def _make_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _touch(root / "tools/render_glb_preview.py")
    _touch(root / "tools/compose_blender_scene.py")
    _touch(root / "tools/export_viewer_scene.py")
    return root


def test_render_command_wraps_existing_preview_script(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    glb = tmp_path / "asset.glb"
    _touch(blender)
    _touch(glb)

    command = build_render_glb_preview_command(
        root,
        glb,
        tmp_path / "preview.png",
        tmp_path / "preview.blend",
        blender_path=blender,
    )

    assert command.cwd == str(root.resolve())
    assert command.argv[:4] == [
        str(blender.resolve()),
        "-b",
        "--python",
        str((root / "tools/render_glb_preview.py").resolve()),
    ]
    assert str(glb.resolve()) in command.argv


def test_compose_command_wraps_existing_compose_script(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    scene = tmp_path / "scene.glb"
    asset = tmp_path / "asset.glb"
    _touch(blender)
    _touch(scene)
    _touch(asset)

    command = build_compose_blender_scene_command(
        root,
        scene,
        asset,
        tmp_path / "composed.png",
        tmp_path / "composed.blend",
        blender_path=blender,
    )

    assert command.argv[3] == str((root / "tools/compose_blender_scene.py").resolve())
    assert str(scene.resolve()) in command.argv
    assert str(asset.resolve()) in command.argv


def test_compose_command_accepts_optional_assembly_plan_json(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    scene = tmp_path / "scene.glb"
    asset = tmp_path / "asset.glb"
    plan = tmp_path / "assembly_plan.json"
    _touch(blender)
    _touch(scene)
    _touch(asset)

    command = build_compose_blender_scene_command(
        root,
        scene,
        asset,
        tmp_path / "composed.png",
        tmp_path / "composed.blend",
        assembly_plan_json=plan,
        blender_path=blender,
    )

    assert command.argv[-1] == str(plan.resolve())


def test_render_command_requires_existing_input_glb(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    _touch(blender)

    with pytest.raises(FileNotFoundError):
        build_render_glb_preview_command(
            root,
            tmp_path / "missing.glb",
            tmp_path / "preview.png",
            tmp_path / "preview.blend",
            blender_path=blender,
        )


def test_export_viewer_scene_command_wraps_existing_export_script(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    blend = tmp_path / "scene.blend"
    _touch(blender)
    _touch(blend)

    command = build_export_viewer_scene_command(
        root,
        blend,
        tmp_path / "viewer_scene.glb",
        tmp_path / "scene_state.json",
        blender_path=blender,
    )

    assert command.argv[3] == str((root / "tools/export_viewer_scene.py").resolve())
    assert str(blend.resolve()) in command.argv
    assert str((tmp_path / "viewer_scene.glb").resolve()) in command.argv
    assert str((tmp_path / "scene_state.json").resolve()) in command.argv
