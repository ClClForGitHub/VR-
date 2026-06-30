from pathlib import Path

from agent_runtime.infra_inventory import collect_infrastructure_inventory, summarize_inventory


def _touch(path: Path, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    if executable:
        path.chmod(0o755)


def test_inventory_detects_reusable_project_files(tmp_path: Path) -> None:
    _touch(tmp_path / "docs/runtime_environment_plan.md")
    _touch(tmp_path / "docs/blender_asset_pipeline_contract.md")
    for script in [
        "start_a40_services.sh",
        "status_a40_services.sh",
        "start_blender51_lab_mcp_bridge.sh",
        "status_blender51_lab_mcp_bridge.sh",
        "status_glb_viewer.sh",
        "start_runtime_console.sh",
        "status_runtime_console.sh",
        "stop_runtime_console.sh",
    ]:
        _touch(tmp_path / "scripts" / script, executable=True)
    for tool in [
        "compose_blender_scene.py",
        "render_glb_preview.py",
        "export_viewer_scene.py",
        "glb_viewer_server.py",
        "runtime_console_server.py",
    ]:
        _touch(tmp_path / "tools" / tool)
    for directory in ["Hunyuan3D-2.1", "HY-World-2.0", "third_party", "web/runtime_console"]:
        (tmp_path / directory).mkdir(parents=True)

    items = collect_infrastructure_inventory(
        tmp_path,
        codex_self_mcp_path=tmp_path / "missing_codex_self_mcp",
        blender_path=tmp_path / "missing_blender",
    )
    summary = summarize_inventory(items)

    assert summary["ok"] is True
    assert summary["missing_required"] == []
    assert {item.name for item in items if item.exists} >= {
        "runtime_plan",
        "asset_pipeline_contract",
        "compose_blender_scene",
        "render_glb_preview",
        "export_viewer_scene",
        "glb_viewer_server",
        "runtime_console_server",
        "runtime_console_web",
    }


def test_inventory_reports_missing_required_files(tmp_path: Path) -> None:
    items = collect_infrastructure_inventory(
        tmp_path,
        codex_self_mcp_path=tmp_path / "missing_codex_self_mcp",
        blender_path=tmp_path / "missing_blender",
    )
    summary = summarize_inventory(items)

    assert summary["ok"] is False
    assert "runtime_plan" in summary["missing_required"]
