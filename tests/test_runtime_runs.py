import json
from pathlib import Path

from agent_runtime.runtime_runs import (
    PublicUrlConfig,
    build_runtime_run_bundle,
    decode_runtime_run_key,
    discover_runtime_runs,
    encode_runtime_run_key,
    resolve_runtime_run_dir,
    rewrite_runtime_urls,
)
from agent_runtime.state import AgentProjectState, ViewerSceneState, WorkflowPhase


def test_discover_runtime_runs_reports_existing_output_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    (run_dir / "viewer_export").mkdir(parents=True)
    (run_dir / "state.json").write_text(
        AgentProjectState(project_id="p", thread_id="t", phase=WorkflowPhase.INTAKE).model_dump_json(),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "frontend_status.json").write_text("{}", encoding="utf-8")
    (run_dir / "viewer_export" / "scene_state.json").write_text("{}", encoding="utf-8")

    items = discover_runtime_runs(root=tmp_path)

    assert len(items) == 1
    assert items[0].run_id == "run_001"
    assert items[0].run_key == encode_runtime_run_key("run_001")
    assert items[0].has_state is True
    assert items[0].has_scene_state is True
    assert items[0].has_delivery_handoff is False


def test_runtime_run_bundle_reads_existing_files_and_rewrites_public_urls(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_001"
    (run_dir / "viewer_export").mkdir(parents=True)
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_path="/tmp/viewer_scene.glb",
        ),
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (run_dir / "frontend_status.json").write_text(json.dumps({"viewer": "http://127.0.0.1:8092/viewer?path=/tmp/a.glb"}), encoding="utf-8")
    (run_dir / "delivery_handoff.json").write_text(json.dumps({"viewer_url": "http://127.0.0.1:8092/viewer?path=/tmp/a.glb"}), encoding="utf-8")
    (run_dir / "runtime_execution.jsonl").write_text('{"status":"dry_run"}\n', encoding="utf-8")
    (run_dir / "runtime_execution_summary.json").write_text(json.dumps({"total_records": 1}), encoding="utf-8")
    (run_dir / "viewer_export" / "scene_state.json").write_text(json.dumps({"objects": []}), encoding="utf-8")

    bundle = build_runtime_run_bundle(
        run_dir,
        public_urls=PublicUrlConfig(public_glb_viewer_base_url="http://public.example:8092"),
    )

    assert bundle.frontend_status == {"viewer": "http://public.example:8092/viewer?path=/tmp/a.glb"}
    assert bundle.delivery_handoff == {"viewer_url": "http://public.example:8092/viewer?path=/tmp/a.glb"}
    assert bundle.runtime_execution_summary == {"total_records": 1}
    assert bundle.web_surface is not None
    assert bundle.web_surface.viewer_scene_url == "http://public.example:8092/viewer?path=/tmp/viewer_scene.glb"
    assert bundle.file_manifest is not None
    assert {item.label for item in bundle.file_manifest.files if item.exists} >= {"runtime_execution", "runtime_execution_summary"}
    assert bundle.file_manifest.missing_required == ["viewer_scene"]
    assert bundle.missing_files == []


def test_runtime_run_bundle_uses_visual_child_stage_for_group_run(tmp_path: Path) -> None:
    group_dir = tmp_path / "outputs" / "runs" / "demo_run"
    stage_dir = group_dir / "blender_viewer"
    (stage_dir / "viewer_export").mkdir(parents=True)
    viewer_path = stage_dir / "viewer_export" / "viewer_scene.glb"
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_path=str(viewer_path),
        ),
    )
    (stage_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (stage_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (stage_dir / "frontend_status.json").write_text(json.dumps({"phase": "BLENDER_PREVIEW"}), encoding="utf-8")
    (stage_dir / "delivery_handoff.json").write_text(json.dumps({"ready": True}), encoding="utf-8")
    (stage_dir / "viewer_export" / "scene_state.json").write_text(json.dumps({"objects": []}), encoding="utf-8")
    viewer_path.write_bytes(b"glTF")

    items = discover_runtime_runs(root=tmp_path)
    by_id = {item.run_id: item for item in items}
    assert by_id["demo_run"].has_viewer_scene is True
    assert by_id["demo_run/blender_viewer"].is_stage is True

    bundle = build_runtime_run_bundle(group_dir)

    assert bundle.run_id == "demo_run"
    assert bundle.effective_run_dir == str(stage_dir.resolve())
    assert bundle.web_surface is not None
    assert bundle.web_surface.viewer_scene_path == str(viewer_path)
    assert bundle.file_manifest is not None
    assert bundle.file_manifest.missing_required == []


def test_runtime_run_bundle_keeps_parent_control_state_with_visual_child_stage(tmp_path: Path) -> None:
    group_dir = tmp_path / "outputs" / "runs" / "demo_run"
    stage_dir = group_dir / "blender_viewer"
    (stage_dir / "viewer_export").mkdir(parents=True)
    viewer_path = stage_dir / "viewer_export" / "viewer_scene.glb"
    parent_state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_path=str(viewer_path),
        ),
    )
    child_state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.DELIVERY,
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_path=str(viewer_path),
        ),
    )
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "state.json").write_text(parent_state.model_dump_json(), encoding="utf-8")
    (group_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    (group_dir / "frontend_status.json").write_text(
        json.dumps({"phase": "BLENDER_PREVIEW", "current_stage": "blender_preview_approval"}),
        encoding="utf-8",
    )
    (group_dir / "runtime_plan.json").write_text(json.dumps({"runtime_plan": {"requires_user": True}}), encoding="utf-8")
    (stage_dir / "state.json").write_text(child_state.model_dump_json(), encoding="utf-8")
    (stage_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (stage_dir / "frontend_status.json").write_text(json.dumps({"phase": "DELIVERY"}), encoding="utf-8")
    (stage_dir / "delivery_handoff.json").write_text(json.dumps({"ready": True}), encoding="utf-8")
    (stage_dir / "viewer_export" / "scene_state.json").write_text(json.dumps({"objects": []}), encoding="utf-8")
    viewer_path.write_bytes(b"glTF")

    bundle = build_runtime_run_bundle(group_dir)

    assert bundle.run_id == "demo_run"
    assert bundle.effective_run_dir == str(stage_dir.resolve())
    assert bundle.state["phase"] == "BLENDER_PREVIEW"
    assert bundle.frontend_status["phase"] == "BLENDER_PREVIEW"
    assert bundle.runtime_plan == {"runtime_plan": {"requires_user": True}}
    assert bundle.delivery_handoff == {"ready": True}
    assert bundle.scene_state == {"objects": []}
    assert bundle.web_surface is not None
    assert bundle.web_surface.viewer_scene_url is not None
    assert bundle.file_manifest is not None
    assert bundle.file_manifest.missing_required == []


def test_runtime_run_bundle_includes_formal_delivery_package_zip(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "demo_run"
    (run_dir / "viewer_export").mkdir(parents=True)
    (run_dir / "delivery_package" / "package").mkdir(parents=True)
    viewer_path = run_dir / "viewer_export" / "viewer_scene.glb"
    viewer_path.write_bytes(b"glTF")
    (run_dir / "viewer_export" / "scene_state.json").write_text(json.dumps({"objects": []}), encoding="utf-8")
    delivery_zip = run_dir / "delivery_package" / "package" / "delivery_demo.zip"
    delivery_zip.write_bytes(b"zip")
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.DELIVERY,
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_path=str(viewer_path),
        ),
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "delivery_package_zip": str(delivery_zip)}), encoding="utf-8")
    (run_dir / "frontend_status.json").write_text(json.dumps({"phase": "DELIVERY"}), encoding="utf-8")
    (run_dir / "delivery_handoff.json").write_text(json.dumps({"ready": True}), encoding="utf-8")

    bundle = build_runtime_run_bundle(run_dir)

    assert bundle.file_manifest is not None
    delivery_records = [item for item in bundle.file_manifest.files if item.label == "delivery_package"]
    assert len(delivery_records) == 1
    assert delivery_records[0].exists is True
    assert delivery_records[0].path == str(delivery_zip)
    assert delivery_records[0].url is not None


def test_runtime_run_key_resolves_nested_stage(tmp_path: Path) -> None:
    stage_dir = tmp_path / "outputs" / "runs" / "demo_run" / "blender_viewer"
    stage_dir.mkdir(parents=True)
    key = encode_runtime_run_key("demo_run/blender_viewer")

    assert decode_runtime_run_key(key) == "demo_run/blender_viewer"
    assert resolve_runtime_run_dir(root=tmp_path, run_key=key) == stage_dir.resolve()


def test_nonvisual_workflow_child_does_not_override_parent_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "demo_run"
    child_dir = run_dir / "subject_asset_handoff_001"
    child_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        AgentProjectState(project_id="p", thread_id="t", phase=WorkflowPhase.CONCEPT_APPROVED).model_dump_json(),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (run_dir / "frontend_status.json").write_text(json.dumps({"phase": "CONCEPT_APPROVED"}), encoding="utf-8")
    (child_dir / "state.json").write_text(
        AgentProjectState(project_id="p", thread_id="t", phase=WorkflowPhase.SUBJECT_ASSET_GENERATION).model_dump_json(),
        encoding="utf-8",
    )
    (child_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (child_dir / "frontend_status.json").write_text(json.dumps({"phase": "SUBJECT_ASSET_GENERATION"}), encoding="utf-8")

    items = discover_runtime_runs(root=tmp_path)
    bundle = build_runtime_run_bundle(run_dir)

    assert [item.run_id for item in items] == ["demo_run"]
    assert bundle.effective_run_dir == str(run_dir.resolve())
    assert bundle.state["phase"] == "CONCEPT_APPROVED"


def test_discover_runtime_runs_prefers_visual_runs_over_newer_intake_runs(tmp_path: Path) -> None:
    visual_dir = tmp_path / "outputs" / "runs" / "visual_run" / "blender_viewer"
    smoke_dir = tmp_path / "outputs" / "runs" / "newer_smoke"
    (visual_dir / "viewer_export").mkdir(parents=True)
    smoke_dir.mkdir(parents=True)
    (visual_dir / "viewer_export" / "viewer_scene.glb").write_bytes(b"glTF")
    (visual_dir / "viewer_export" / "scene_state.json").write_text("{}", encoding="utf-8")
    (smoke_dir / "state.json").write_text(
        AgentProjectState(project_id="p", thread_id="t", phase=WorkflowPhase.INTAKE).model_dump_json(),
        encoding="utf-8",
    )
    (smoke_dir / "summary.json").write_text("{}", encoding="utf-8")

    items = discover_runtime_runs(root=tmp_path)

    assert items[0].run_id == "visual_run"
    assert items[0].has_viewer_scene is True
    assert items[-1].run_id == "newer_smoke"


def test_rewrite_runtime_urls_is_recursive() -> None:
    payload = {
        "items": [
            "http://127.0.0.1:8092/asset?path=/tmp/a.glb",
            {"blend": "http://127.0.0.1:8300/"},
        ]
    }

    rewritten = rewrite_runtime_urls(
        payload,
        PublicUrlConfig(
            public_glb_viewer_base_url="http://host:8092",
            public_blender_web_http_url="http://host:8300",
        ),
    )

    assert rewritten["items"][0] == "http://host:8092/asset?path=/tmp/a.glb"
    assert rewritten["items"][1]["blend"] == "http://host:8300/"
