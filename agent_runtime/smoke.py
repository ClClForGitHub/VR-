"""Reusable smoke workflows for the V1 landing layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_runtime.artifacts import FileArtifactStore
from agent_runtime.script_adapters import (
    build_compose_blender_scene_command,
    build_export_viewer_scene_command,
    build_render_glb_preview_command,
)
from agent_runtime.state import (
    AgentProjectState,
    ArtifactType,
    ToolCallStatus,
    ViewerSceneState,
    WorkflowPhase,
)
from agent_runtime.tool_executor import CommandExecutionOptions, ToolExecutor
from agent_runtime.viewer import check_viewer_model


def model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def patch_scene_state_artifact_ids(
    scene_state_json: Path,
    *,
    viewer_scene_artifact_id: str,
    viewer_state_artifact_id: str,
) -> None:
    payload = json.loads(scene_state_json.read_text(encoding="utf-8"))
    payload["viewer_scene_artifact_id"] = viewer_scene_artifact_id
    payload["viewer_state_artifact_id"] = viewer_state_artifact_id
    write_json(scene_state_json, payload)


def run_render_existing_glb_smoke(
    *,
    root: str | Path,
    input_glb: str | Path,
    output_dir: str | Path,
    blender_path: str | Path | None = None,
    timeout_seconds: float = 300,
    dry_run: bool = False,
    reset_metadata: bool = True,
) -> dict:
    root_path = Path(root).expanduser().resolve()
    input_path = Path(input_glb).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        for relative in [
            "artifacts/artifacts.jsonl",
            "state.json",
            "tool_call_log.json",
            "summary.json",
            "preview.png",
            "preview.blend",
            "preview.blend1",
        ]:
            target = output_path / relative
            if target.exists():
                target.unlink()

    artifact_store = FileArtifactStore(output_path / "artifacts")
    state = AgentProjectState(
        project_id="v1_render_existing_glb_smoke",
        thread_id="local_smoke",
        phase=WorkflowPhase.BLENDER_EDIT,
    )
    state.artifacts.append(
        artifact_store.register_file(
            input_path,
            ArtifactType.SUBJECT_3D_ASSET,
            artifact_id="smoke_input_glb",
            semantic_role="smoke_input_glb",
        )
    )

    preview_png = output_path / "preview.png"
    preview_blend = output_path / "preview.blend"
    command = build_render_glb_preview_command(
        root_path,
        input_path,
        preview_png,
        preview_blend,
        **({"blender_path": blender_path} if blender_path is not None else {}),
    )
    record = ToolExecutor(state).run_command(
        "render_preview",
        command,
        arguments={
            "input_glb": str(input_path),
            "preview_png": str(preview_png),
            "preview_blend": str(preview_blend),
        },
        options=CommandExecutionOptions(timeout_seconds=timeout_seconds, dry_run=dry_run),
    )

    if record.status == ToolCallStatus.SUCCEEDED and not dry_run:
        if preview_png.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    preview_png,
                    ArtifactType.BLENDER_PREVIEW_RENDER,
                    artifact_id="smoke_preview_png",
                    semantic_role="blender_preview_render",
                )
            )
        if preview_blend.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    preview_blend,
                    ArtifactType.BLENDER_FILE,
                    artifact_id="smoke_preview_blend",
                    semantic_role="blender_file",
                )
            )

    summary = {
        "ok": record.status == ToolCallStatus.SUCCEEDED,
        "dry_run": dry_run,
        "input_glb": str(input_path),
        "output_dir": str(output_path),
        "preview_png_exists": preview_png.exists(),
        "preview_blend_exists": preview_blend.exists(),
        "tool_call_status": record.status.value,
        "tool_call_id": record.tool_call_id,
        "artifact_ids": sorted(state.artifact_ids()),
    }
    write_json(output_path / "state.json", model_to_dict(state))
    write_json(output_path / "tool_call_log.json", {"tool_call_log": [model_to_dict(item) for item in state.tool_call_log]})
    write_json(output_path / "summary.json", summary)
    return summary


def run_compose_existing_scene_smoke(
    *,
    root: str | Path,
    scene_glb: str | Path,
    asset_glb: str | Path,
    output_dir: str | Path,
    blender_path: str | Path | None = None,
    timeout_seconds: float = 300,
    dry_run: bool = False,
    reset_metadata: bool = True,
) -> dict:
    root_path = Path(root).expanduser().resolve()
    scene_path = Path(scene_glb).expanduser().resolve()
    asset_path = Path(asset_glb).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        for relative in [
            "artifacts/artifacts.jsonl",
            "state.json",
            "tool_call_log.json",
            "summary.json",
            "composed_preview.png",
            "composed_scene.blend",
            "composed_scene.blend1",
        ]:
            target = output_path / relative
            if target.exists():
                target.unlink()

    artifact_store = FileArtifactStore(output_path / "artifacts")
    state = AgentProjectState(
        project_id="v1_compose_existing_scene_smoke",
        thread_id="local_smoke",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
    )
    state.artifacts.append(
        artifact_store.register_file(
            scene_path,
            ArtifactType.SCENE_3D_ASSET,
            artifact_id="smoke_scene_glb",
            semantic_role="smoke_scene_glb",
        )
    )
    state.artifacts.append(
        artifact_store.register_file(
            asset_path,
            ArtifactType.SUBJECT_3D_ASSET,
            artifact_id="smoke_subject_glb",
            semantic_role="smoke_subject_glb",
        )
    )

    preview_png = output_path / "composed_preview.png"
    output_blend = output_path / "composed_scene.blend"
    command = build_compose_blender_scene_command(
        root_path,
        scene_path,
        asset_path,
        preview_png,
        output_blend,
        **({"blender_path": blender_path} if blender_path is not None else {}),
    )
    record = ToolExecutor(state).run_command(
        "import_scene_asset",
        command,
        arguments={
            "scene_glb": str(scene_path),
            "asset_glb": str(asset_path),
            "preview_png": str(preview_png),
            "output_blend": str(output_blend),
        },
        options=CommandExecutionOptions(timeout_seconds=timeout_seconds, dry_run=dry_run),
    )

    if record.status == ToolCallStatus.SUCCEEDED and not dry_run:
        if preview_png.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    preview_png,
                    ArtifactType.BLENDER_PREVIEW_RENDER,
                    artifact_id="smoke_composed_preview_png",
                    semantic_role="blender_preview_render",
                )
            )
        if output_blend.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    output_blend,
                    ArtifactType.BLENDER_FILE,
                    artifact_id="smoke_composed_blend",
                    semantic_role="blender_file",
                )
            )

    summary = {
        "ok": record.status == ToolCallStatus.SUCCEEDED,
        "dry_run": dry_run,
        "scene_glb": str(scene_path),
        "asset_glb": str(asset_path),
        "output_dir": str(output_path),
        "preview_png_exists": preview_png.exists(),
        "output_blend_exists": output_blend.exists(),
        "tool_call_status": record.status.value,
        "tool_call_id": record.tool_call_id,
        "artifact_ids": sorted(state.artifact_ids()),
    }
    write_json(output_path / "state.json", model_to_dict(state))
    write_json(output_path / "tool_call_log.json", {"tool_call_log": [model_to_dict(item) for item in state.tool_call_log]})
    write_json(output_path / "summary.json", summary)
    return summary


def run_export_viewer_scene_smoke(
    *,
    root: str | Path,
    input_blend: str | Path,
    output_dir: str | Path,
    blender_path: str | Path | None = None,
    timeout_seconds: float = 300,
    dry_run: bool = False,
    reset_metadata: bool = True,
) -> dict:
    root_path = Path(root).expanduser().resolve()
    blend_path = Path(input_blend).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        for relative in [
            "artifacts/artifacts.jsonl",
            "state.json",
            "tool_call_log.json",
            "summary.json",
            "viewer_scene.glb",
            "scene_state.json",
        ]:
            target = output_path / relative
            if target.exists():
                target.unlink()

    artifact_store = FileArtifactStore(output_path / "artifacts")
    state = AgentProjectState(
        project_id="v1_export_viewer_scene_smoke",
        thread_id="local_smoke",
        phase=WorkflowPhase.BLENDER_EDIT,
    )
    state.artifacts.append(
        artifact_store.register_file(
            blend_path,
            ArtifactType.BLENDER_FILE,
            artifact_id="smoke_source_blend",
            semantic_role="source_blend_file",
        )
    )

    viewer_glb = output_path / "viewer_scene.glb"
    scene_state_json = output_path / "scene_state.json"
    command = build_export_viewer_scene_command(
        root_path,
        blend_path,
        viewer_glb,
        scene_state_json,
        **({"blender_path": blender_path} if blender_path is not None else {}),
    )
    record = ToolExecutor(state).run_command(
        "export_viewer_scene",
        command,
        arguments={
            "input_blend": str(blend_path),
            "viewer_glb": str(viewer_glb),
            "scene_state_json": str(scene_state_json),
        },
        options=CommandExecutionOptions(timeout_seconds=timeout_seconds, dry_run=dry_run),
    )

    if record.status == ToolCallStatus.SUCCEEDED and not dry_run:
        viewer_scene_artifact_id = "smoke_viewer_scene_glb"
        viewer_state_artifact_id = "smoke_scene_state_json"
        if scene_state_json.exists():
            patch_scene_state_artifact_ids(
                scene_state_json,
                viewer_scene_artifact_id=viewer_scene_artifact_id,
                viewer_state_artifact_id=viewer_state_artifact_id,
            )
            state.viewer_scene = ViewerSceneState(**json.loads(scene_state_json.read_text(encoding="utf-8")))
        if viewer_glb.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    viewer_glb,
                    ArtifactType.VIEWER_SCENE_GLB,
                    artifact_id=viewer_scene_artifact_id,
                    semantic_role="viewer_scene",
                )
            )
        if scene_state_json.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    scene_state_json,
                    ArtifactType.VIEWER_SCENE_STATE_JSON,
                    artifact_id=viewer_state_artifact_id,
                    semantic_role="viewer_scene_state",
                )
            )

    summary = {
        "ok": record.status == ToolCallStatus.SUCCEEDED,
        "dry_run": dry_run,
        "input_blend": str(blend_path),
        "output_dir": str(output_path),
        "viewer_glb_exists": viewer_glb.exists(),
        "scene_state_json_exists": scene_state_json.exists(),
        "viewer_scene_object_count": len(state.viewer_scene.objects) if state.viewer_scene is not None else None,
        "tool_call_status": record.status.value,
        "tool_call_id": record.tool_call_id,
        "artifact_ids": sorted(state.artifact_ids()),
    }
    write_json(output_path / "state.json", model_to_dict(state))
    write_json(output_path / "tool_call_log.json", {"tool_call_log": [model_to_dict(item) for item in state.tool_call_log]})
    write_json(output_path / "summary.json", summary)
    return summary


def run_local_e2e_smoke(
    *,
    root: str | Path,
    scene_glb: str | Path,
    asset_glb: str | Path,
    output_dir: str | Path,
    blender_path: str | Path | None = None,
    viewer_base_url: str = "http://127.0.0.1:8092",
    compose_timeout_seconds: float = 300,
    export_timeout_seconds: float = 180,
    viewer_timeout_seconds: float = 10,
    dry_run: bool = False,
    reset_metadata: bool = True,
) -> dict:
    root_path = Path(root).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        for relative in ["summary.json"]:
            target = output_path / relative
            if target.exists():
                target.unlink()

    compose_dir = output_path / "compose"
    viewer_dir = output_path / "viewer_export"
    compose_summary = run_compose_existing_scene_smoke(
        root=root_path,
        scene_glb=scene_glb,
        asset_glb=asset_glb,
        output_dir=compose_dir,
        blender_path=blender_path,
        timeout_seconds=compose_timeout_seconds,
        dry_run=dry_run,
        reset_metadata=reset_metadata,
    )

    export_summary = None
    viewer_check = None
    if compose_summary["ok"] and not dry_run:
        export_summary = run_export_viewer_scene_smoke(
            root=root_path,
            input_blend=compose_dir / "composed_scene.blend",
            output_dir=viewer_dir,
            blender_path=blender_path,
            timeout_seconds=export_timeout_seconds,
            dry_run=False,
            reset_metadata=reset_metadata,
        )
        if export_summary["ok"] and export_summary["viewer_glb_exists"]:
            viewer_check = check_viewer_model(
                viewer_dir / "viewer_scene.glb",
                base_url=viewer_base_url,
                timeout=viewer_timeout_seconds,
            )

    ok = compose_summary["ok"]
    if dry_run:
        ok = ok and export_summary is None
    else:
        ok = ok and bool(export_summary and export_summary["ok"]) and bool(viewer_check and viewer_check["ok"])

    summary = {
        "ok": ok,
        "dry_run": dry_run,
        "root": str(root_path),
        "scene_glb": str(Path(scene_glb).expanduser().resolve()),
        "asset_glb": str(Path(asset_glb).expanduser().resolve()),
        "output_dir": str(output_path),
        "compose_dir": str(compose_dir),
        "viewer_export_dir": str(viewer_dir),
        "compose": compose_summary,
        "export_viewer": export_summary,
        "viewer_check": viewer_check,
    }
    write_json(output_path / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    render = subparsers.add_parser("render")
    render.add_argument("--root", default="/home/team/zouzhiyuan/image23D_Agent")
    render.add_argument("--input-glb", required=True)
    render.add_argument("--output-dir", required=True)
    render.add_argument("--blender-path")
    render.add_argument("--timeout", type=float, default=300)
    render.add_argument("--dry-run", action="store_true")
    render.add_argument("--no-reset-metadata", action="store_true")

    compose = subparsers.add_parser("compose")
    compose.add_argument("--root", default="/home/team/zouzhiyuan/image23D_Agent")
    compose.add_argument("--scene-glb", required=True)
    compose.add_argument("--asset-glb", required=True)
    compose.add_argument("--output-dir", required=True)
    compose.add_argument("--blender-path")
    compose.add_argument("--timeout", type=float, default=300)
    compose.add_argument("--dry-run", action="store_true")
    compose.add_argument("--no-reset-metadata", action="store_true")

    export_viewer = subparsers.add_parser("export-viewer")
    export_viewer.add_argument("--root", default="/home/team/zouzhiyuan/image23D_Agent")
    export_viewer.add_argument("--input-blend", required=True)
    export_viewer.add_argument("--output-dir", required=True)
    export_viewer.add_argument("--blender-path")
    export_viewer.add_argument("--timeout", type=float, default=300)
    export_viewer.add_argument("--dry-run", action="store_true")
    export_viewer.add_argument("--no-reset-metadata", action="store_true")

    e2e = subparsers.add_parser("e2e")
    e2e.add_argument("--root", default="/home/team/zouzhiyuan/image23D_Agent")
    e2e.add_argument("--scene-glb", required=True)
    e2e.add_argument("--asset-glb", required=True)
    e2e.add_argument("--output-dir", required=True)
    e2e.add_argument("--blender-path")
    e2e.add_argument("--viewer-base-url", default="http://127.0.0.1:8092")
    e2e.add_argument("--compose-timeout", type=float, default=300)
    e2e.add_argument("--export-timeout", type=float, default=180)
    e2e.add_argument("--viewer-timeout", type=float, default=10)
    e2e.add_argument("--dry-run", action="store_true")
    e2e.add_argument("--no-reset-metadata", action="store_true")

    # Backward-compatible legacy invocation for the first render smoke.
    parser.add_argument("--root", default="/home/team/zouzhiyuan/image23D_Agent")
    parser.add_argument("--input-glb")
    parser.add_argument("--output-dir")
    parser.add_argument("--blender-path")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-reset-metadata", action="store_true")
    args = parser.parse_args()

    if args.command == "compose":
        summary = run_compose_existing_scene_smoke(
            root=args.root,
            scene_glb=args.scene_glb,
            asset_glb=args.asset_glb,
            output_dir=args.output_dir,
            blender_path=args.blender_path,
            timeout_seconds=args.timeout,
            dry_run=args.dry_run,
            reset_metadata=not args.no_reset_metadata,
        )
    elif args.command == "export-viewer":
        summary = run_export_viewer_scene_smoke(
            root=args.root,
            input_blend=args.input_blend,
            output_dir=args.output_dir,
            blender_path=args.blender_path,
            timeout_seconds=args.timeout,
            dry_run=args.dry_run,
            reset_metadata=not args.no_reset_metadata,
        )
    elif args.command == "e2e":
        summary = run_local_e2e_smoke(
            root=args.root,
            scene_glb=args.scene_glb,
            asset_glb=args.asset_glb,
            output_dir=args.output_dir,
            blender_path=args.blender_path,
            viewer_base_url=args.viewer_base_url,
            compose_timeout_seconds=args.compose_timeout,
            export_timeout_seconds=args.export_timeout,
            viewer_timeout_seconds=args.viewer_timeout,
            dry_run=args.dry_run,
            reset_metadata=not args.no_reset_metadata,
        )
    else:
        if not args.input_glb or not args.output_dir:
            parser.error("render smoke requires --input-glb and --output-dir")
        summary = run_render_existing_glb_smoke(
            root=args.root,
            input_glb=args.input_glb,
            output_dir=args.output_dir,
            blender_path=args.blender_path,
            timeout_seconds=args.timeout,
            dry_run=args.dry_run,
            reset_metadata=not args.no_reset_metadata,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
