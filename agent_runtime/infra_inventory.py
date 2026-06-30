"""Read-only inventory of reusable image23D agent infrastructure."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class InfrastructureItem:
    name: str
    kind: str
    path: str
    required: bool
    exists: bool
    executable: bool | None = None
    note: str | None = None


def _item(
    root: Path,
    name: str,
    kind: str,
    relative_path: str,
    *,
    required: bool = True,
    executable: bool | None = None,
    note: str | None = None,
) -> InfrastructureItem:
    path = (root / relative_path).resolve()
    exists = path.exists()
    executable_result = None
    if executable is not None:
        executable_result = exists and os.access(path, os.X_OK)
    return InfrastructureItem(
        name=name,
        kind=kind,
        path=str(path),
        required=required,
        exists=exists,
        executable=executable_result,
        note=note,
    )


def collect_infrastructure_inventory(
    root: str | Path = ".",
    *,
    codex_self_mcp_path: str | Path = "/home/team/zouzhiyuan/codex-self-mcp",
    blender_path: str | Path = "/home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender",
) -> list[InfrastructureItem]:
    root_path = Path(root).expanduser().resolve()
    items = [
        _item(root_path, "runtime_plan", "doc", "docs/runtime_environment_plan.md"),
        _item(root_path, "asset_pipeline_contract", "doc", "docs/blender_asset_pipeline_contract.md"),
        _item(root_path, "start_a40_services", "script", "scripts/start_a40_services.sh", executable=True),
        _item(root_path, "status_a40_services", "script", "scripts/status_a40_services.sh", executable=True),
        _item(root_path, "start_blender51_lab_mcp_bridge", "script", "scripts/start_blender51_lab_mcp_bridge.sh", executable=True),
        _item(root_path, "status_blender51_lab_mcp_bridge", "script", "scripts/status_blender51_lab_mcp_bridge.sh", executable=True),
        _item(root_path, "status_glb_viewer", "script", "scripts/status_glb_viewer.sh", executable=True),
        _item(root_path, "start_runtime_console", "script", "scripts/start_runtime_console.sh", executable=True),
        _item(root_path, "status_runtime_console", "script", "scripts/status_runtime_console.sh", executable=True),
        _item(root_path, "stop_runtime_console", "script", "scripts/stop_runtime_console.sh", executable=True),
        _item(root_path, "compose_blender_scene", "tool", "tools/compose_blender_scene.py"),
        _item(root_path, "render_glb_preview", "tool", "tools/render_glb_preview.py"),
        _item(root_path, "export_viewer_scene", "tool", "tools/export_viewer_scene.py"),
        _item(root_path, "glb_viewer_server", "tool", "tools/glb_viewer_server.py"),
        _item(root_path, "runtime_console_server", "tool", "tools/runtime_console_server.py"),
        _item(root_path, "hunyuan3d_repo", "service_repo", "Hunyuan3D-2.1"),
        _item(root_path, "hy_world_repo", "service_repo", "HY-World-2.0"),
        _item(root_path, "third_party_sources", "source_dir", "third_party"),
        _item(root_path, "web_runtime", "viewer", "web"),
        _item(root_path, "runtime_console_web", "viewer", "web/runtime_console"),
        _item(root_path, "outputs", "evidence_dir", "outputs", required=False),
        _item(root_path, "run_logs", "evidence_dir", "run_logs", required=False),
    ]

    codex_self_mcp = Path(codex_self_mcp_path).expanduser().resolve()
    items.append(
        InfrastructureItem(
            name="codex_self_mcp",
            kind="mcp_server",
            path=str(codex_self_mcp),
            required=False,
            exists=codex_self_mcp.exists(),
            note="Optional sub-agent MCP channel; smoke-tested separately when needed.",
        )
    )

    blender = Path(blender_path).expanduser().resolve()
    items.append(
        InfrastructureItem(
            name="blender_5_1_2",
            kind="runtime",
            path=str(blender),
            required=False,
            exists=blender.exists(),
            executable=blender.exists() and os.access(blender, os.X_OK),
        )
    )

    codex_exe = shutil.which("codex")
    items.append(
        InfrastructureItem(
            name="codex_cli",
            kind="runtime",
            path=codex_exe or "codex",
            required=False,
            exists=codex_exe is not None,
            executable=codex_exe is not None,
            note="Used for codex mcp list and codex-self-mcp smoke tests.",
        )
    )
    return items


def summarize_inventory(items: list[InfrastructureItem]) -> dict[str, object]:
    required = [item for item in items if item.required]
    missing_required = [item for item in required if not item.exists]
    non_executable_required = [
        item
        for item in required
        if item.executable is False
    ]
    return {
        "total": len(items),
        "required": len(required),
        "missing_required": [item.name for item in missing_required],
        "non_executable_required": [item.name for item in non_executable_required],
        "ok": not missing_required and not non_executable_required,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    items = collect_infrastructure_inventory(args.root)
    summary = summarize_inventory(items)
    payload = {
        "summary": summary,
        "items": [asdict(item) for item in items],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        for item in items:
            marker = "OK" if item.exists and item.executable is not False else "MISS"
            print(f"{marker}\t{item.kind}\t{item.name}\t{item.path}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
