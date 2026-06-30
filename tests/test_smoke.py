from pathlib import Path

from agent_runtime.smoke import (
    run_compose_existing_scene_smoke,
    run_export_viewer_scene_smoke,
    run_local_e2e_smoke,
    run_render_existing_glb_smoke,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"placeholder")


def test_render_existing_glb_smoke_dry_run_records_state(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    input_glb = tmp_path / "input.glb"
    blender = tmp_path / "blender"
    _touch(root / "tools/render_glb_preview.py")
    _touch(input_glb)
    _touch(blender)

    summary = run_render_existing_glb_smoke(
        root=root,
        input_glb=input_glb,
        output_dir=tmp_path / "smoke",
        blender_path=blender,
        dry_run=True,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert "smoke_input_glb" in summary["artifact_ids"]
    assert (tmp_path / "smoke/state.json").exists()
    assert (tmp_path / "smoke/tool_call_log.json").exists()


def test_compose_existing_scene_smoke_dry_run_records_state(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    scene_glb = tmp_path / "scene.glb"
    asset_glb = tmp_path / "asset.glb"
    blender = tmp_path / "blender"
    _touch(root / "tools/compose_blender_scene.py")
    _touch(scene_glb)
    _touch(asset_glb)
    _touch(blender)

    summary = run_compose_existing_scene_smoke(
        root=root,
        scene_glb=scene_glb,
        asset_glb=asset_glb,
        output_dir=tmp_path / "compose_smoke",
        blender_path=blender,
        dry_run=True,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert "smoke_scene_glb" in summary["artifact_ids"]
    assert "smoke_subject_glb" in summary["artifact_ids"]
    assert (tmp_path / "compose_smoke/state.json").exists()
    assert (tmp_path / "compose_smoke/tool_call_log.json").exists()


def test_export_viewer_scene_smoke_dry_run_records_state(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    input_blend = tmp_path / "scene.blend"
    blender = tmp_path / "blender"
    _touch(root / "tools/export_viewer_scene.py")
    _touch(input_blend)
    _touch(blender)

    summary = run_export_viewer_scene_smoke(
        root=root,
        input_blend=input_blend,
        output_dir=tmp_path / "viewer_smoke",
        blender_path=blender,
        dry_run=True,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert "smoke_source_blend" in summary["artifact_ids"]
    assert (tmp_path / "viewer_smoke/state.json").exists()
    assert (tmp_path / "viewer_smoke/tool_call_log.json").exists()


def test_local_e2e_smoke_dry_run_runs_compose_only(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    scene_glb = tmp_path / "scene.glb"
    asset_glb = tmp_path / "asset.glb"
    blender = tmp_path / "blender"
    _touch(root / "tools/compose_blender_scene.py")
    _touch(scene_glb)
    _touch(asset_glb)
    _touch(blender)

    summary = run_local_e2e_smoke(
        root=root,
        scene_glb=scene_glb,
        asset_glb=asset_glb,
        output_dir=tmp_path / "e2e_smoke",
        blender_path=blender,
        dry_run=True,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert summary["compose"]["ok"] is True
    assert summary["export_viewer"] is None
    assert summary["viewer_check"] is None
    assert (tmp_path / "e2e_smoke/summary.json").exists()
