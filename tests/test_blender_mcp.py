import subprocess
import os
from pathlib import Path

import pytest

from agent_runtime.blender_mcp import (
    BlenderLabSocketRawToolCaller,
    BlenderMCPAdapter,
    build_safe_blender_mcp_operation_plan,
    sync_blender_scene_state_from_objects_summary,
)
from agent_runtime.state import BlenderObjectRecord, BlenderSceneState, WorkflowPhase


def _make_status_script(tmp_path: Path) -> Path:
    script = tmp_path / "status_blender51_lab_mcp_bridge.sh"
    script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def _make_codex(tmp_path: Path) -> Path:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\n", encoding="utf-8")
    codex.chmod(0o755)
    return codex


def test_blender_mcp_adapter_status_uses_existing_script_and_codex_mcp_list(tmp_path: Path) -> None:
    script = _make_status_script(tmp_path)
    codex = _make_codex(tmp_path)

    def fake_run(args, timeout):
        if args == ["bash", str(script)]:
            return subprocess.CompletedProcess(
                args,
                0,
                "Blender 5.1.2\n"
                "Blender 5.1 Lab MCP bridge running: pid=123\n"
                "Blender Lab MCP bridge socket: open on 127.0.0.1:9876\n",
                "",
            )
        if args == [str(codex), "mcp", "list"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "Name         Command  Args  Env  Cwd  Status   Auth\n"
                "blender_lab  blender  -     -    -    enabled  Unsupported\n",
                "",
            )
        raise AssertionError(args)

    adapter = BlenderMCPAdapter(
        status_script=script,
        codex_command=str(codex),
        run_command=fake_run,
    )
    status = adapter.status()

    assert status.ok is True
    assert status.blender_version == "Blender 5.1.2"
    assert status.bridge_running is True
    assert status.socket_open is True
    assert status.codex_cli_found is True
    assert status.configured_in_codex_mcp_list is True
    assert status.mcp_list_servers == ["blender_lab"]
    assert status.issues == []


def test_blender_mcp_adapter_status_reports_missing_script_or_cli(tmp_path: Path) -> None:
    adapter = BlenderMCPAdapter(
        status_script=tmp_path / "missing.sh",
        codex_command=str(tmp_path / "missing-codex"),
    )

    status = adapter.status()

    assert status.ok is False
    assert status.status_script_exists is False
    assert status.codex_cli_found is False
    assert "missing_status_script" in status.issues
    assert "missing_codex_cli" in status.issues


def test_blender_lab_socket_raw_tool_caller_reuses_toolcode_and_socket_env(tmp_path: Path) -> None:
    tool_dir = tmp_path / "third_party/blender_lab_mcp/mcp/blmcp/tools"
    tool_dir.mkdir(parents=True)
    (tool_dir / "get_objects_summary.py").write_text("# fake tool", encoding="utf-8")
    calls = []

    def fake_send_code(code, strict_json):
        calls.append((code, strict_json, os.environ["BLENDER_MCP_HOST"], os.environ["BLENDER_MCP_PORT"]))
        return {"status": "ok", "result": {"status": "ok", "scene_name": "Scene", "collections": []}}

    caller = BlenderLabSocketRawToolCaller(
        root=tmp_path,
        bridge_host="10.0.0.1",
        bridge_port=1234,
        send_code_func=fake_send_code,
        toolcode_load_from_filepath=lambda path: "TOOLCODE:" + Path(path).name,
        toolcode_wrap_with_calling_convention=lambda code: "WRAPPED:" + code,
        toolcode_format_call=lambda code, params: f"CALL:{code}:{params!r}",
    )

    result = caller("get_objects_summary", {})

    assert result["result"]["scene_name"] == "Scene"
    assert calls == [
        (
            "CALL:WRAPPED:TOOLCODE:get_objects_summary.py:None",
            True,
            "10.0.0.1",
            "1234",
        )
    ]


def test_blender_lab_socket_raw_tool_caller_validates_execute_code_args() -> None:
    calls = []
    caller = BlenderLabSocketRawToolCaller(
        send_code_func=lambda code, strict_json: calls.append((code, strict_json)) or {"status": "ok", "result": {}}
    )

    assert caller("execute_blender_code", {"code": "result = {'ok': True}"}) == {"status": "ok", "result": {}}
    assert calls == [("result = {'ok': True}", False)]

    with pytest.raises(ValueError, match="non-empty string code"):
        caller("execute_blender_code", {"code": ""})
    with pytest.raises(ValueError, match="unsupported"):
        caller("delete_everything", {})


def test_sync_blender_scene_state_from_objects_summary_maps_current_mcp_shape() -> None:
    summary = {
        "status": "ok",
        "result": {
            "status": "ok",
            "scene_name": "Scene",
            "active_workspace": "Layout",
            "active_object": "Camera",
            "object_mode": "OBJECT",
            "camera_object": "Camera",
            "collections": [
                {
                    "name": "Scene Collection",
                    "objects": [
                        {
                            "name": "asset.glb",
                            "type": "MESH",
                            "parent": "world",
                            "data_name": "asset.glb",
                            "selected": False,
                            "visible": True,
                            "hide_viewport": False,
                        },
                        {
                            "name": "Camera",
                            "type": "CAMERA",
                            "parent": None,
                            "data_name": "Camera",
                            "selected": True,
                            "visible": True,
                            "hide_viewport": False,
                        },
                        {
                            "name": "world",
                            "type": "EMPTY",
                            "parent": None,
                            "data_name": None,
                            "selected": False,
                            "visible": True,
                            "hide_viewport": False,
                        },
                    ],
                    "children": [],
                }
            ],
        },
    }

    result = sync_blender_scene_state_from_objects_summary(
        summary,
        blend_file_artifact_id="blend_artifact",
        preview_image_id="preview_artifact",
        scene_asset_id="scene_asset_001",
    )

    assert result.ok is True
    assert result.scene_name == "Scene"
    assert result.active_object == "Camera"
    assert result.object_mode == "OBJECT"
    assert result.camera_object == "Camera"
    assert result.object_count == 3
    assert result.blender_scene.blender_scene_id == "Scene"
    assert result.blender_scene.blend_file_artifact_id == "blend_artifact"
    assert result.blender_scene.preview_image_id == "preview_artifact"
    assert result.blender_scene.scene_asset_id == "scene_asset_001"
    assert [item.blender_name for item in result.blender_scene.objects] == ["asset.glb", "Camera", "world"]
    assert [item.object_type for item in result.blender_scene.objects] == ["unknown", "camera", "helper"]
    assert result.blender_scene.objects[0].notes == "parent=world; data_name=asset.glb"
    assert result.blender_scene.objects[1].semantic_role == "camera"
    assert result.blender_scene.objects[1].notes == "data_name=Camera; selected=true"


def test_sync_blender_scene_state_from_objects_summary_preserves_error_boundary() -> None:
    result = sync_blender_scene_state_from_objects_summary(
        {"status": "ok", "result": {"status": "error", "message": "background window unavailable"}}
    )

    assert result.ok is False
    assert result.blender_scene is None
    assert result.issues == ["background window unavailable"]


def _scene_state() -> BlenderSceneState:
    return BlenderSceneState(
        blender_scene_id="Scene",
        objects=[
            BlenderObjectRecord(
                object_id="hero",
                blender_name="Hero",
                subject_id="subject_robot",
                object_type="subject_asset",
            ),
            BlenderObjectRecord(
                object_id="camera",
                blender_name="Camera",
                object_type="camera",
            ),
        ],
    )


def test_build_safe_blender_mcp_operation_plan_maps_read_only_scene_summary() -> None:
    plan = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="get_blender_scene_summary",
    )

    assert plan.ok is True
    assert plan.raw_tool_name == "get_objects_summary"
    assert plan.raw_tool_arguments == {}
    assert plan.safety_notes == ["read_only_scene_summary"]


def test_build_safe_blender_mcp_operation_plan_generates_fixed_move_template() -> None:
    plan = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="move_subject",
        arguments={"blender_object_id": "hero", "location": [1, 2, 3]},
        blender_scene=_scene_state(),
    )

    assert plan.ok is True
    assert plan.raw_tool_name == "execute_blender_code"
    assert plan.arguments_summary == {"blender_name": "Hero", "location": [1.0, 2.0, 3.0]}
    assert "bpy.data.objects.get('Hero')" in plan.raw_tool_arguments["code"]
    assert "obj.location = (1.0, 2.0, 3.0)" in plan.raw_tool_arguments["code"]
    assert "fixed_python_template" in plan.safety_notes


def test_build_safe_blender_mcp_operation_plan_accepts_live_llm_object_aliases() -> None:
    object_alias_plan = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="move_subject",
        arguments={"object_id": "hero", "subject_id": "subject_robot", "location": [1, 2, 3]},
        blender_scene=_scene_state(),
    )

    assert object_alias_plan.ok is True
    assert object_alias_plan.arguments_summary == {"blender_name": "Hero", "location": [1.0, 2.0, 3.0]}
    assert "bpy.data.objects.get('Hero')" in object_alias_plan.raw_tool_arguments["code"]

    subject_fallback_plan = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="move_subject",
        arguments={"subject_id": "subject_robot", "location": [4, 5, 6]},
        blender_scene=_scene_state(),
    )

    assert subject_fallback_plan.ok is True
    assert subject_fallback_plan.arguments_summary == {"blender_name": "Hero", "location": [4.0, 5.0, 6.0]}
    assert "obj.location = (4.0, 5.0, 6.0)" in subject_fallback_plan.raw_tool_arguments["code"]


def test_build_safe_blender_mcp_operation_plan_rejects_conflicting_object_and_subject() -> None:
    plan = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="move_subject",
        arguments={"object_id": "camera", "subject_id": "subject_robot", "location": [1, 2, 3]},
        blender_scene=_scene_state(),
    )

    assert plan.ok is False
    assert plan.raw_tool_name is None
    assert plan.issues == [
        "object_id/blender_name and subject_id resolve to different Blender objects: camera != hero"
    ]


def test_build_safe_blender_mcp_operation_plan_rejects_wrong_phase_and_missing_object() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        build_safe_blender_mcp_operation_plan(
            phase=WorkflowPhase.CONCEPT_GENERATION,
            domain_tool_name="move_subject",
            arguments={"blender_object_id": "hero", "location": [1, 2, 3]},
            blender_scene=_scene_state(),
        )

    plan = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="move_subject",
        arguments={"blender_object_id": "missing", "location": [1, 2, 3]},
        blender_scene=_scene_state(),
    )

    assert plan.ok is False
    assert plan.raw_tool_name is None
    assert plan.issues == ["object_id not found in BlenderSceneState: missing"]


def test_build_safe_blender_mcp_operation_plan_requires_delete_confirmation() -> None:
    unconfirmed = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="delete_subject",
        arguments={"blender_object_id": "hero"},
        blender_scene=_scene_state(),
    )

    assert unconfirmed.ok is False
    assert unconfirmed.requires_confirmation is True
    assert unconfirmed.issues == ["delete_subject requires confirm_delete=true"]

    confirmed = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="delete_subject",
        arguments={"blender_object_id": "hero", "confirm_delete": True},
        blender_scene=_scene_state(),
    )

    assert confirmed.ok is True
    assert confirmed.requires_confirmation is True
    assert "bpy.data.objects.remove(obj, do_unlink=True)" in confirmed.raw_tool_arguments["code"]
    assert "destructive_operation_confirmed" in confirmed.safety_notes


def test_build_safe_blender_mcp_operation_plan_validates_camera_light_and_material_args() -> None:
    camera_plan = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="update_camera",
        arguments={"camera_name": "Camera", "location": [0, -6, 2.2], "focal_length": 45},
        blender_scene=_scene_state(),
    )
    assert camera_plan.ok is True
    assert "bpy.data.cameras.new('Camera')" in camera_plan.raw_tool_arguments["code"]

    bad_light = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="update_lighting",
        arguments={"energy": -1},
        blender_scene=_scene_state(),
    )
    assert bad_light.ok is False
    assert bad_light.issues == ["energy must be a non-negative number"]

    material_plan = build_safe_blender_mcp_operation_plan(
        phase=WorkflowPhase.BLENDER_EDIT,
        domain_tool_name="set_simple_material",
        arguments={"blender_name": "Hero", "base_color": [1, 0.5, 0.25, 1]},
        blender_scene=_scene_state(),
    )
    assert material_plan.ok is True
    assert material_plan.arguments_summary["material_name"] == "Hero_simple_material"
    assert "Base Color" in material_plan.raw_tool_arguments["code"]
