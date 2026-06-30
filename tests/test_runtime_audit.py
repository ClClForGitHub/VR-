import json
from pathlib import Path

from agent_runtime.runtime_audit import audit_runtime_run
from agent_runtime.runtime_console import append_console_message, create_runtime_console_run, save_console_upload
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.runtime_execution import execute_next_runtime_job
from agent_runtime.state import (
    AgentProjectState,
    BlenderObjectRecord,
    BlenderSceneState,
    ReviewPatch,
    ViewerSceneState,
    WorkflowPhase,
)


def test_runtime_audit_passes_text_intake_execution_chain(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="Create one clean robot.")
    build_and_save_runtime_dispatch_plan(created.run_dir)
    execute_next_runtime_job(created.run_dir, env={})

    result = audit_runtime_run(created.run_dir)

    assert result.ok is True
    assert result.error_count == 0
    check_ids = {check.check_id for check in result.checks}
    assert "chat_user_turns_mirrored_to_state" in check_ids
    assert any(check.check_id.startswith("reference_binding_context_uses_latest_user_turn") for check in result.checks)


def test_runtime_audit_passes_uploaded_unbound_reference_gate(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    save_console_upload(
        created.run_dir,
        filename="reference.png",
        content=b"fake-image",
        mime_type="image/png",
    )
    build_and_save_runtime_dispatch_plan(created.run_dir)
    execute_next_runtime_job(created.run_dir)

    result = audit_runtime_run(created.run_dir)

    assert result.ok is True
    assert result.error_count == 0
    assert any(check.check_id == "user_gate_matches_unbound_images" and check.ok for check in result.checks)


def test_runtime_audit_accepts_blender_domain_tool_dry_run_output(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    state = AgentProjectState(
        project_id="project_blender_edit",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_EDIT,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            objects=[
                BlenderObjectRecord(
                    object_id="hero",
                    blender_name="Hero",
                    subject_id="subject_robot",
                    object_type="subject_asset",
                )
            ],
        ),
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_scene_001"),
        review_patches=[
            ReviewPatch(
                patch_id="patch_move_hero",
                source_turn_id="turn_001",
                phase_created=WorkflowPhase.BLENDER_PREVIEW,
                target_type="blender_object",
                target_id="hero",
                patch_type="move_object",
                instruction="把主体移动到画面中心。",
                structured_delta={
                    "blender_edit_plan": {
                        "route": "pure_blender_edit",
                        "reason": "minor placement edit",
                        "domain_tool_calls": [
                            {
                                "domain_tool_name": "move_subject",
                                "arguments": {"object_id": "hero", "subject_id": "subject_robot", "location": [1, 2, 3]},
                                "reason": "center_hero",
                            }
                        ],
                    }
                },
            )
        ],
    )
    run_dir = Path(created.run_dir)
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir)
    execute_next_runtime_job(run_dir, dry_run=True)

    result = audit_runtime_run(run_dir)

    assert result.ok is True
    assert result.error_count == 0
    assert any(check.check_id.startswith("dry_run_domain_tool_has_operation_plan") and check.ok for check in result.checks)
    assert not any(check.check_id.startswith("dry_run_llm_has_no_state_candidate") for check in result.checks)


def test_runtime_audit_accepts_blender_domain_tool_live_output(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    state = AgentProjectState(
        project_id="project_blender_edit",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_EDIT,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            objects=[
                BlenderObjectRecord(
                    object_id="hero",
                    blender_name="Hero",
                    subject_id="subject_robot",
                    object_type="subject_asset",
                )
            ],
        ),
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_scene_001"),
        review_patches=[
            ReviewPatch(
                patch_id="patch_move_hero",
                source_turn_id="turn_001",
                phase_created=WorkflowPhase.BLENDER_PREVIEW,
                target_type="blender_object",
                target_id="hero",
                patch_type="move_object",
                instruction="把主体移动到画面中心。",
                structured_delta={
                    "blender_edit_plan": {
                        "route": "pure_blender_edit",
                        "reason": "minor placement edit",
                        "domain_tool_calls": [
                            {
                                "domain_tool_name": "move_subject",
                                "arguments": {"object_id": "hero", "subject_id": "subject_robot", "location": [1, 2, 3]},
                                "reason": "center_hero",
                            }
                        ],
                    }
                },
            )
        ],
    )
    run_dir = Path(created.run_dir)
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir)

    def raw_tool_caller(tool_name, arguments):
        if tool_name == "execute_blender_code":
            return {"status": "ok", "result": {"ok": True, "object": "Hero", "location": [1, 2, 3]}}
        if tool_name == "get_objects_summary":
            return {
                "status": "ok",
                "result": {
                    "status": "ok",
                    "scene_name": "Scene",
                    "active_object": "Hero",
                    "object_mode": "OBJECT",
                    "camera_object": "Camera",
                    "collections": [
                        {
                            "name": "Scene Collection",
                            "objects": [
                                {
                                    "name": "Hero",
                                    "type": "MESH",
                                    "visible": True,
                                    "hide_viewport": False,
                                }
                            ],
                        }
                    ],
                },
            }
        raise AssertionError(tool_name)

    step = execute_next_runtime_job(run_dir, dry_run=False, blender_raw_tool_caller=raw_tool_caller)
    assert step.ok is True
    assert step.record is not None
    payload = json.loads(Path(step.record.output_json).read_text(encoding="utf-8"))
    assert payload["domain_tool_result"]["domain_tool_name"] == "move_subject"
    assert payload["operation_plan"]["domain_tool_name"] == "move_subject"

    result = audit_runtime_run(run_dir)

    assert result.ok is True
    assert result.error_count == 0
    assert any(
        check.check_id.startswith(f"execution_output_matches_record:{step.record.execution_id}") and check.ok
        for check in result.checks
    )


def test_runtime_audit_accepts_recovered_failed_prior_phase_job(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    state = AgentProjectState(
        project_id="project_blender_edit",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_EDIT,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            objects=[
                BlenderObjectRecord(
                    object_id="hero",
                    blender_name="Hero",
                    subject_id="subject_robot",
                    object_type="subject_asset",
                )
            ],
        ),
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_scene_001"),
        review_patches=[
            ReviewPatch(
                patch_id="patch_move_hero",
                source_turn_id="turn_001",
                phase_created=WorkflowPhase.BLENDER_PREVIEW,
                target_type="blender_object",
                target_id="hero",
                patch_type="move_object",
                instruction="把主体移动到画面中心。",
                structured_delta={
                    "blender_edit_plan": {
                        "route": "pure_blender_edit",
                        "reason": "minor placement edit",
                        "domain_tool_calls": [
                            {
                                "domain_tool_name": "move_subject",
                                "arguments": {"object_id": "hero", "subject_id": "subject_robot", "location": [1, 2, 3]},
                                "reason": "center_hero",
                            }
                        ],
                    }
                },
            )
        ],
    )
    run_dir = Path(created.run_dir)
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir)

    failed = execute_next_runtime_job(
        run_dir,
        dry_run=False,
        blender_raw_tool_caller=lambda _tool_name, _arguments: {"status": "error", "message": "object not found"},
    )
    assert failed.ok is False

    def raw_tool_caller(tool_name, arguments):
        if tool_name == "execute_blender_code":
            return {"status": "ok", "result": {"ok": True, "object": "Hero", "location": [1, 2, 3]}}
        if tool_name == "get_objects_summary":
            return {
                "status": "ok",
                "result": {
                    "status": "ok",
                    "scene_name": "Scene",
                    "active_object": "Hero",
                    "object_mode": "OBJECT",
                    "camera_object": "Camera",
                    "collections": [{"name": "Scene Collection", "objects": [{"name": "Hero", "type": "MESH"}]}],
                },
            }
        raise AssertionError(tool_name)

    recovered = execute_next_runtime_job(run_dir, dry_run=False, blender_raw_tool_caller=raw_tool_caller)
    assert recovered.ok is True

    preview_state = AgentProjectState(**json.loads((run_dir / "state.json").read_text(encoding="utf-8")))
    preview_state.phase = WorkflowPhase.BLENDER_PREVIEW
    preview_state.viewer_scene = ViewerSceneState(viewer_scene_id="viewer_scene_001")
    (run_dir / "state.json").write_text(preview_state.model_dump_json(), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir)

    result = audit_runtime_run(run_dir)

    assert result.ok is True
    assert result.error_count == 0
