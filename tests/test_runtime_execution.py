import json
from pathlib import Path

from agent_runtime.runtime_console import (
    append_console_message,
    create_runtime_console_run,
    save_console_upload,
)
from agent_runtime.domain_dispatcher import DomainToolDispatchResult
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.runtime_execution import (
    build_llm_node_context,
    execute_next_runtime_job,
    read_runtime_execution_records,
    read_runtime_execution_summary,
)
from agent_runtime.runtime_user_actions import approve_blender_preview
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    Asset3DRecord,
    BlenderAssemblyPlan,
    BlenderObjectRecord,
    BlenderSceneState,
    CameraSpec,
    ConceptBundle,
    EnvironmentSpec,
    LightingSpec,
    ReviewPatch,
    Scene3DRecord,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    ToolCallRecord,
    ToolCallStatus,
    ViewerSceneState,
    WorkflowPhase,
)


def test_runtime_execution_records_user_gate_without_state_mutation(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    upload = save_console_upload(
        created.run_dir,
        filename="reference.png",
        content=b"fake-image",
        mime_type="image/png",
    )
    before_state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    build_and_save_runtime_dispatch_plan(created.run_dir)

    result = execute_next_runtime_job(created.run_dir)
    records = read_runtime_execution_records(created.run_dir)
    after_state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "waiting_user"
    assert result.record.issues == ["runtime_waiting_for_user_input"]
    assert f"image_{upload.upload_id}" in str(result.record.result_summary)
    assert records[0].job_kind == "user_gate"
    assert after_state == before_state


def test_runtime_execution_repeats_user_gate_until_state_changes(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    save_console_upload(
        created.run_dir,
        filename="reference.png",
        content=b"fake-image",
        mime_type="image/png",
    )
    build_and_save_runtime_dispatch_plan(created.run_dir)

    first = execute_next_runtime_job(created.run_dir)
    second = execute_next_runtime_job(created.run_dir)

    assert first.record is not None
    assert second.record is not None
    assert first.record.status == "waiting_user"
    assert second.record.status == "waiting_user"
    assert second.record.job_id == first.record.job_id


def test_runtime_execution_dry_runs_first_llm_node_and_writes_outputs(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="Make a clean robot display scene.")
    build_and_save_runtime_dispatch_plan(created.run_dir)

    result = execute_next_runtime_job(created.run_dir, env={})
    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "dry_run"
    assert result.record.node_name == "ReferenceBindingValidator"
    assert result.record.output_json is not None

    output = json.loads(Path(result.record.output_json).read_text(encoding="utf-8"))
    assert output["llm_result"]["dry_run"] is True
    assert output["context_json"]["user_text"] == "Make a clean robot display scene."
    assert "fake" not in str(output["llm_result"]).lower()

    summary = read_runtime_execution_summary(created.run_dir)
    assert summary is not None
    assert summary["latest_record"]["job_id"] == result.record.job_id
    assert summary["status_counts"] == {"dry_run": 1}


def test_runtime_execution_dry_run_does_not_hide_fixture_rerun(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="Make a clean robot display scene.")
    build_and_save_runtime_dispatch_plan(created.run_dir)

    dry = execute_next_runtime_job(created.run_dir, env={})
    live = execute_next_runtime_job(
        created.run_dir,
        response_text_by_node={
            "ReferenceBindingValidator": json.dumps(
                {
                    "valid_bindings": [],
                    "requires_clarification": False,
                    "open_questions": [],
                    "issues": [],
                }
            )
        },
    )

    assert dry.record is not None
    assert live.record is not None
    assert dry.record.status == "dry_run"
    assert live.record.status == "completed"
    assert live.record.job_id == dry.record.job_id
    assert live.record.node_name == "ReferenceBindingValidator"


def test_runtime_execution_delegates_long_sub_agent_domain_job(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    run_dir.mkdir(parents=True)
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(concept_version=1, approved=True),
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")

    build_and_save_runtime_dispatch_plan(run_dir)
    result = execute_next_runtime_job(run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "delegated"
    assert result.record.domain_tool_name == "build_subject_asset"
    assert result.record.result_summary["command_hint"].startswith("workflow_runner subject-asset")
    assert "job_requires_external_worker_or_sub_agent" in result.record.issues


def test_runtime_execution_dry_runs_planned_blender_edit_domain_tool(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_blender_edit_tool"
    run_dir.mkdir(parents=True)
    state = AgentProjectState(
        project_id="project_blender_edit",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_EDIT,
        scene_spec=_scene_spec(),
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
                                "arguments": {"blender_object_id": "hero", "location": [1, 2, 3]},
                                "reason": "center_hero",
                            }
                        ],
                    }
                },
            )
        ],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    plan = build_and_save_runtime_dispatch_plan(run_dir)
    assert plan.runtime_plan.jobs[0].domain_tool_name == "move_subject"

    result = execute_next_runtime_job(run_dir, dry_run=True)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "dry_run"
    assert result.record.domain_tool_name == "move_subject"
    assert result.record.output_json is not None
    payload = json.loads(Path(result.record.output_json).read_text(encoding="utf-8"))
    operation_plan = payload["domain_tool_result"]["operation_plan"]
    assert operation_plan["domain_tool_name"] == "move_subject"
    assert operation_plan["raw_tool_name"] == "execute_blender_code"
    assert operation_plan["arguments_summary"] == {"blender_name": "Hero", "location": [1.0, 2.0, 3.0]}
    assert "obj.location = (1.0, 2.0, 3.0)" in operation_plan["raw_tool_arguments"]["code"]
    assert "blender_edit_domain_tool_dry_run" in result.record.issues


def test_runtime_execution_live_blender_edit_requires_explicit_raw_caller(tmp_path: Path) -> None:
    run_dir = _blender_edit_run_dir(tmp_path)
    build_and_save_runtime_dispatch_plan(run_dir)

    result = execute_next_runtime_job(run_dir, dry_run=False)

    assert result.ok is False
    assert result.record is not None
    assert result.record.status == "blocked"
    assert result.record.issues == ["blender_edit_requires_explicit_raw_caller"]
    assert result.record.domain_tool_name == "move_subject"


def test_runtime_execution_live_blender_edit_with_injected_raw_caller_updates_state(tmp_path: Path) -> None:
    run_dir = _blender_edit_run_dir(tmp_path)
    plan = build_and_save_runtime_dispatch_plan(run_dir)
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        if tool_name == "execute_blender_code":
            return {"status": "ok", "result": {"ok": True, "object": "Hero", "location": [1, 2, 3]}}
        if tool_name == "get_objects_summary":
            return _objects_summary(object_name="Hero")
        raise AssertionError(tool_name)

    result = execute_next_runtime_job(
        run_dir,
        dry_run=False,
        blender_raw_tool_caller=raw_tool_caller,
    )

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "completed"
    assert result.record.domain_tool_name == "move_subject"
    assert [call[0] for call in raw_calls] == ["execute_blender_code", "get_objects_summary"]
    assert result.summary.handled_job_ids == [plan.runtime_plan.jobs[0].job_id]
    assert result.summary.pending_job_ids[:2] == [
        plan.runtime_plan.jobs[1].job_id,
        plan.runtime_plan.jobs[2].job_id,
    ]

    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))
    output = json.loads(Path(result.record.output_json).read_text(encoding="utf-8"))

    assert state_payload["phase"] == "BLENDER_EDIT"
    assert state_payload["blender_scene"]["objects"][0]["blender_name"] == "Hero"
    assert state_payload["blender_scene"]["objects"][0]["subject_id"] == "subject_robot"
    assert state_payload["blender_scene"]["objects"][0]["object_type"] == "subject_asset"
    assert state_payload["blender_scene"]["objects"][0]["transform"]["location"] == [1.0, 2.0, 3.0]
    assert state_payload["tool_call_log"][0]["domain_tool_name"] == "move_subject"
    assert len(state_payload["tool_call_log"][0]["raw_tool_calls"]) == 2
    assert summary["latest_blender_edit_execution"]["domain_tool_name"] == "move_subject"
    assert summary["latest_blender_edit_execution"]["raw_caller_source"] == "injected"
    assert summary["stage_checkpoints"][-1]["reason"] == "blender_edit_domain_tool_executed"
    assert frontend_status["phase"] == "BLENDER_EDIT"
    assert output["domain_tool_result"]["ok"] is True
    assert output["domain_tool_result"]["outputs"]["raw_tool_name"] == "execute_blender_code"


def test_runtime_execution_socket_blender_edit_loads_run_local_blend(tmp_path: Path, monkeypatch) -> None:
    run_dir = _blender_edit_run_dir(tmp_path)
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    blend = _artifact(tmp_path, "blend_file", ArtifactType.BLENDER_FILE, ".blend", b"blend")
    state_payload["artifacts"].append(blend.model_dump(mode="json"))
    state_payload["blender_scene"]["blend_file_artifact_id"] = blend.artifact_id
    (run_dir / "state.json").write_text(json.dumps(state_payload, ensure_ascii=False), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir)
    raw_calls = []

    class FakeSocketRawCaller:
        def __init__(self):
            pass

        def __call__(self, tool_name, arguments):
            raw_calls.append((tool_name, arguments))
            if tool_name == "execute_blender_code":
                code = arguments["code"]
                if "open_mainfile" in code:
                    return {"status": "ok", "result": {"ok": True, "loaded_blend": blend.uri}}
                if "save_as_mainfile" in code:
                    return {"status": "ok", "result": {"ok": True, "saved_to": blend.uri}}
                return {"status": "ok", "result": {"ok": True, "object": "Hero", "location": [1, 2, 3]}}
            if tool_name == "get_objects_summary":
                return _objects_summary(object_name="Hero")
            raise AssertionError(tool_name)

    monkeypatch.setattr("agent_runtime.runtime_execution.BlenderLabSocketRawToolCaller", FakeSocketRawCaller)

    result = execute_next_runtime_job(
        run_dir,
        dry_run=False,
        blender_raw_caller_source="blender-lab-socket",
    )

    assert result.ok is True
    assert result.record is not None
    assert result.record.domain_tool_name == "move_subject"
    assert result.record.result_summary["outputs"]["blend_load_raw_result"]["status"] == "ok"
    assert [call[0] for call in raw_calls] == [
        "execute_blender_code",
        "execute_blender_code",
        "get_objects_summary",
        "execute_blender_code",
    ]
    assert "open_mainfile" in raw_calls[0][1]["code"]
    output = json.loads(Path(result.record.output_json).read_text(encoding="utf-8"))
    assert output["domain_tool_result"]["tool_call_record"]["raw_tool_calls"][0]["purpose"] == "load_blend_before_edit"


def test_runtime_execution_dry_runs_viewer_refresh_script_job(tmp_path: Path, monkeypatch) -> None:
    run_dir = _viewer_refresh_run_dir(tmp_path)
    calls = _patch_fake_script_dispatcher(monkeypatch)
    plan = build_and_save_runtime_dispatch_plan(run_dir)
    assert plan.runtime_plan.jobs[0].domain_tool_name == "export_viewer_scene"

    result = execute_next_runtime_job(run_dir, dry_run=True)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "dry_run"
    assert result.record.domain_tool_name == "export_viewer_scene"
    assert result.record.issues == ["runtime_script_domain_tool_dry_run"]
    assert calls[0][0] == "export_viewer_scene"
    assert calls[0][2] is True
    assert calls[0][1]["input_blend"].endswith("blend_file.blend")
    assert calls[0][1]["viewer_glb"].endswith("viewer_export/viewer_scene.glb")
    assert json.loads((run_dir / "state.json").read_text(encoding="utf-8"))["viewer_scene"] is None


def test_runtime_execution_dry_runs_import_scene_asset_from_assembly_plan(tmp_path: Path, monkeypatch) -> None:
    run_dir = _assembly_import_run_dir(tmp_path)
    calls = _patch_fake_script_dispatcher(monkeypatch)
    plan = build_and_save_runtime_dispatch_plan(run_dir)
    assert plan.runtime_plan.jobs[0].domain_tool_name == "import_scene_asset"

    result = execute_next_runtime_job(run_dir, dry_run=True)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "dry_run"
    assert result.record.domain_tool_name == "import_scene_asset"
    assert calls[0][0] == "import_scene_asset"
    assert calls[0][2] is True
    assert calls[0][1]["scene_glb"].endswith("scene_glb.glb")
    assert calls[0][1]["asset_glb"].endswith("subject_glb.glb")
    assert calls[0][1]["preview_png"].endswith("compose/composed_preview.png")
    assembly_plan = json.loads(Path(calls[0][1]["assembly_plan_json"]).read_text(encoding="utf-8"))
    assert assembly_plan["planner"] == "llm_bridge_v1"
    assert assembly_plan["plan_id"] == "assembly_plan_runtime_001"
    assert assembly_plan["target_region"] == "front_right"
    assert assembly_plan["target_height_ratio"] == 0.5
    assert assembly_plan["subject_yaw_degrees"] == 35.0


def test_runtime_execution_live_import_scene_asset_registers_blender_scene(tmp_path: Path, monkeypatch) -> None:
    run_dir = _assembly_import_run_dir(tmp_path)
    calls = _patch_fake_script_dispatcher(monkeypatch)
    build_and_save_runtime_dispatch_plan(run_dir)

    result = execute_next_runtime_job(run_dir, dry_run=False)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "completed"
    assert result.record.domain_tool_name == "import_scene_asset"
    assert calls[0][0] == "import_scene_asset"
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["blender_scene"]["blend_file_artifact_id"].startswith("runtime_")
    assert state["blender_scene"]["preview_image_id"].startswith("runtime_")
    assert {artifact["artifact_type"] for artifact in state["artifacts"]} >= {
        "BLENDER_FILE",
        "BLENDER_PREVIEW_RENDER",
    }
    runtime_plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    assert runtime_plan["runtime_plan"]["jobs"][0]["domain_tool_name"] == "export_viewer_scene"


def test_runtime_execution_live_viewer_refresh_and_preview_rebuilds_plan(tmp_path: Path, monkeypatch) -> None:
    run_dir = _viewer_refresh_run_dir(tmp_path)
    calls = _patch_fake_script_dispatcher(monkeypatch)
    viewer_checks = _patch_fake_viewer_runtime_adapter(monkeypatch)
    plan = build_and_save_runtime_dispatch_plan(run_dir)
    assert [job.domain_tool_name for job in plan.runtime_plan.jobs] == ["export_viewer_scene", "render_preview"]

    export_step = execute_next_runtime_job(run_dir, dry_run=False)
    render_step = execute_next_runtime_job(run_dir, dry_run=False)

    assert export_step.ok is True
    assert render_step.ok is True
    assert export_step.record is not None
    assert render_step.record is not None
    assert export_step.record.status == "completed"
    assert render_step.record.status == "completed"
    assert [call[0] for call in calls] == ["export_viewer_scene", "render_preview"]
    assert calls[1][1]["input_glb"].endswith("viewer_export/viewer_scene.glb")

    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))
    runtime_plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    delivery_handoff = json.loads((run_dir / "delivery_handoff.json").read_text(encoding="utf-8"))

    artifact_types = [item["artifact_type"] for item in state_payload["artifacts"]]
    assert state_payload["phase"] == "BLENDER_PREVIEW"
    assert state_payload["viewer_scene"]["viewer_scene_artifact_id"].startswith("runtime_")
    assert state_payload["viewer_scene"]["viewer_scene_path"].endswith("viewer_export/viewer_scene.glb")
    assert state_payload["viewer_scene"]["objects"][0]["subject_id"] == "subject_robot"
    scene_state_payload = json.loads((run_dir / "viewer_export/scene_state.json").read_text(encoding="utf-8"))
    assert scene_state_payload["objects"][0]["subject_id"] == "subject_robot"
    assert scene_state_payload["objects"][0]["asset_id"] is None
    assert state_payload["blender_scene"]["preview_image_id"].startswith("runtime_")
    assert artifact_types.count("VIEWER_SCENE_GLB") == 1
    assert artifact_types.count("VIEWER_SCENE_STATE_JSON") == 1
    assert artifact_types.count("BLENDER_PREVIEW_RENDER") == 1
    viewer_artifact = next(item for item in state_payload["artifacts"] if item["artifact_type"] == "VIEWER_SCENE_GLB")
    viewer_metadata = viewer_artifact["metadata"]["viewer"]
    assert viewer_metadata["runtime_status"]["ok"] is True
    assert viewer_metadata["model_check"]["ok"] is True
    assert viewer_metadata["model_check"]["runtime"]["ok"] is True
    assert viewer_checks == [
        ("runtime_status", "http://viewer.local"),
        ("check_model", str((run_dir / "viewer_export" / "viewer_scene.glb").resolve())),
        ("artifact_metadata", str((run_dir / "viewer_export" / "viewer_scene.glb").resolve())),
    ]
    assert summary["latest_runtime_script_execution"]["domain_tool_name"] == "render_preview"
    assert summary["phase"] == "BLENDER_PREVIEW"
    assert frontend_status["phase"] == "BLENDER_PREVIEW"
    assert delivery_handoff["ready"] is False
    assert delivery_handoff["verified"] is False
    assert delivery_handoff["issues"] == ["missing_subject_assets", "missing_scene_assets"]
    assert delivery_handoff["viewer_runtime_ok"] is True
    assert delivery_handoff["viewer_model_ok"] is True
    assert runtime_plan["runtime_plan"]["requires_user"] is True
    assert runtime_plan["runtime_plan"]["jobs"][0]["kind"] == "user_gate"


def test_runtime_execution_delivery_job_builds_package_and_rebuilds_plan(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_delivery"
    run_dir.mkdir(parents=True)
    state = _delivery_state(tmp_path)
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps({"ok": True, "workflow": "runtime-console", "requested_stages": [], "executed_stages": []}),
        encoding="utf-8",
    )
    initial_plan = build_and_save_runtime_dispatch_plan(run_dir)
    assert initial_plan.runtime_plan.jobs[0].kind == "delivery"

    result = execute_next_runtime_job(run_dir, dry_run=False)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "completed"
    assert result.record.job_kind == "delivery"
    assert result.record.output_json is not None
    assert Path(result.record.result_summary["package_zip"]).is_file()

    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))
    runtime_plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))

    assert state_payload["phase"] == "DELIVERY"
    assert state_payload["artifacts"][-1]["artifact_type"] == "EXPORT_PACKAGE"
    assert summary["delivery_package_ok"] is True
    assert Path(summary["delivery_package_zip"]).is_file()
    assert summary["executed_stages"] == ["delivery_package"]
    assert frontend_status["phase"] == "DELIVERY"
    assert (run_dir / "delivery_handoff.json").is_file()
    assert runtime_plan["runtime_plan"]["jobs"] == []
    assert result.summary.pending_job_ids == []


def test_preview_approval_then_delivery_step_builds_formal_package(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_preview_to_delivery"
    run_dir.mkdir(parents=True)
    state = _delivery_state(tmp_path)
    state.phase = WorkflowPhase.BLENDER_PREVIEW
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps({"ok": True, "workflow": "runtime-console", "requested_stages": [], "executed_stages": []}),
        encoding="utf-8",
    )

    approval = approve_blender_preview(run_dir, note="accepted")
    step = execute_next_runtime_job(run_dir, dry_run=False)

    assert approval.ok is True
    assert approval.record.action_type == "approve_blender_preview"
    assert step.ok is True
    assert step.record is not None
    assert step.record.job_kind == "delivery"
    assert Path(step.record.result_summary["package_zip"]).is_file()

    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    runtime_plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    assert state_payload["phase"] == "DELIVERY"
    assert state_payload["artifacts"][-1]["artifact_type"] == "EXPORT_PACKAGE"
    assert runtime_plan["runtime_plan"]["jobs"] == []


def test_build_llm_node_context_keeps_scene_spec_compiler_candidate_boundary() -> None:
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.INTAKE,
    )
    plan = build_and_save_runtime_dispatch_plan_for_state(state)
    job = plan.runtime_plan.jobs[2]

    context = build_llm_node_context(state, job)

    assert context["interpretation"] is None
    assert context["context_issue"] == "SceneInterpreter candidate output is not persisted yet."


def test_scene_spec_compiler_context_ignores_stale_scene_interpreter_turn(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="OLD user request")
    build_and_save_runtime_dispatch_plan(created.run_dir)
    execute_next_runtime_job(
        created.run_dir,
        response_text_by_node={
            "ReferenceBindingValidator": json.dumps(
                {
                    "valid_bindings": [],
                    "requires_clarification": False,
                    "open_questions": [],
                    "issues": [],
                }
            )
        },
    )
    execute_next_runtime_job(
        created.run_dir,
        response_text_by_node={
            "SceneInterpreter": json.dumps(
                {
                    "user_goal": "OLD interpreted goal",
                    "subject_summaries": [],
                    "environment_summary": None,
                    "style_summary": None,
                    "open_questions": [],
                }
            )
        },
    )
    append_console_message(created.run_dir, role="user", text="NEW user request")
    state = AgentProjectState(**json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8")))
    job = [item for item in build_and_save_runtime_dispatch_plan_for_state(state).runtime_plan.jobs if item.node_name == "SceneSpecCompiler"][0]

    context = build_llm_node_context(state, job, run_dir=created.run_dir)

    assert context["latest_user_turn"]["text"] == "NEW user request"
    assert context["interpretation"] is None
    assert context["context_issue"] == "SceneInterpreter candidate output is not persisted yet."


def test_concept_prompt_planner_context_includes_search_contract_and_identity_research(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_identity_context"
    run_dir.mkdir(parents=True)
    identity_row = {
        "ok": True,
        "requested_name": "Q版弗洛洛",
        "resolved_identity": "Phrolova / 弗洛洛",
        "source_urls": ["https://wutheringwaves.kurogames.com/en/main/news/detail/2907"],
        "visual_traits": ["violet visual identity", "dark outfit", "theatrical musician motif"],
        "subject_id_hint": "subject_phrolova_chibi",
    }
    (run_dir / "identity_research.jsonl").write_text(json.dumps(identity_row, ensure_ascii=False) + "\n", encoding="utf-8")
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.SCENE_SPEC_READY,
        scene_spec=SceneSpec(
            scene_id="scene_001",
            title="demo",
            user_goal="demo",
            style=StyleSpec(rendering_style="chibi"),
            environment=EnvironmentSpec(environment_type="studio", description="simple studio"),
            lighting=LightingSpec(description="soft light"),
            camera=CameraSpec(shot_type="full body"),
            subjects=[
                SubjectSpec(
                    subject_id="subject_phrolova_chibi",
                    display_name="Q版弗洛洛",
                    category="character",
                    description="Wuthering Waves Phrolova in chibi style.",
                    needs_2d_concept=True,
                )
            ],
        ),
    )
    job = [item for item in build_and_save_runtime_dispatch_plan_for_state(state).runtime_plan.jobs if item.node_name == "ConceptPromptPlanner"][0]

    context = build_llm_node_context(state, job, run_dir=run_dir)

    assert context["identity_research"] == [identity_row]
    assert context["provider_web_search"]["provider"] == "qwen"
    assert context["provider_web_search"]["expected_enabled"] is True
    assert context["provider_web_search"]["request_body_contract"]["enable_search"] is True


def build_and_save_runtime_dispatch_plan_for_state(state: AgentProjectState):
    from agent_runtime.runtime_jobs import build_agent_runtime_plan
    from agent_runtime.controller import build_controller_plan

    controller = build_controller_plan(state)
    return type(
        "PlanHolder",
        (),
        {"runtime_plan": build_agent_runtime_plan(state, controller=controller)},
    )()


def _scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_001",
        title="Robot Display",
        user_goal="Create one robot model in a simple display scene.",
        style=StyleSpec(style_keywords=["clean"], rendering_style="stylized"),
        environment=EnvironmentSpec(environment_type="studio", description="Small display studio."),
        lighting=LightingSpec(description="Soft studio lighting."),
        camera=CameraSpec(shot_type="three quarter"),
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Robot",
                category="character",
                description="A friendly robot.",
            )
        ],
    )


def _delivery_state(tmp_path: Path) -> AgentProjectState:
    blend = _artifact(tmp_path, "blend_file", ArtifactType.BLENDER_FILE, ".blend", b"blend")
    preview = _artifact(tmp_path, "preview_png", ArtifactType.BLENDER_PREVIEW_RENDER, ".png", b"png")
    viewer_glb = _artifact(tmp_path, "viewer_glb", ArtifactType.VIEWER_SCENE_GLB, ".glb", b"viewer")
    viewer_state = _artifact(tmp_path, "viewer_state", ArtifactType.VIEWER_SCENE_STATE_JSON, ".json", b"{}")
    subject = _artifact(tmp_path, "subject_glb", ArtifactType.SUBJECT_3D_ASSET, ".glb", b"subject")
    scene = _artifact(tmp_path, "scene_glb", ArtifactType.SCENE_3D_ASSET, ".glb", b"scene")
    viewer_glb.metadata["viewer"] = {
        "base_url": "http://viewer.local",
        "asset_url": "http://viewer.local/asset?path=viewer.glb",
        "viewer_url": "http://viewer.local/viewer?path=viewer.glb",
        "runtime_status": {"ok": True},
        "model_check": {"ok": True},
    }
    return AgentProjectState(
        project_id="project_delivery",
        thread_id="runtime_console",
        phase=WorkflowPhase.DELIVERY,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene",
            blend_file_artifact_id="blend_file",
            preview_image_id="preview_png",
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_artifact_id="viewer_glb",
            viewer_state_artifact_id="viewer_state",
        ),
        artifacts=[blend, preview, viewer_glb, viewer_state, subject, scene],
    )


def _blender_edit_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "outputs" / "runs" / "run_blender_edit_tool"
    run_dir.mkdir(parents=True)
    state = AgentProjectState(
        project_id="project_blender_edit",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_EDIT,
        scene_spec=_scene_spec(),
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
                                "arguments": {"blender_object_id": "hero", "location": [1, 2, 3]},
                                "reason": "center_hero",
                            }
                        ],
                    }
                },
            )
        ],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    return run_dir


def _viewer_refresh_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "outputs" / "runs" / "run_viewer_refresh"
    run_dir.mkdir(parents=True)
    blend = _artifact(tmp_path, "blend_file", ArtifactType.BLENDER_FILE, ".blend", b"blend")
    state = AgentProjectState(
        project_id="project_viewer_refresh",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            blend_file_artifact_id=blend.artifact_id,
            objects=[
                BlenderObjectRecord(
                    object_id="hero",
                    blender_name="Hero",
                    subject_id="subject_robot",
                    object_type="subject_asset",
                )
            ],
        ),
        artifacts=[blend],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    return run_dir


def _assembly_import_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "outputs" / "runs" / "run_assembly_import"
    run_dir.mkdir(parents=True)
    scene_glb = _artifact(tmp_path, "scene_glb", ArtifactType.SCENE_3D_ASSET, ".glb", b"scene")
    subject_glb = _artifact(tmp_path, "subject_glb", ArtifactType.SUBJECT_3D_ASSET, ".glb", b"subject")
    state = AgentProjectState(
        project_id="project_assembly_import",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=_scene_spec(),
        blender_assembly_plan=BlenderAssemblyPlan(
            plan_id="assembly_plan_runtime_001",
            placement_plans=[
                {
                    "subject_id": "subject_robot",
                    "target_region": "front_right",
                    "composition_notes": "Place the hero in the foreground right third.",
                    "transform_hint": {"rotation_euler": (0.0, 0.0, 35.0)},
                }
            ],
            scale_estimates=[
                {
                    "subject_id": "subject_robot",
                    "relative_scale_description": "large hero subject",
                    "scale_factor_hint": 0.5,
                }
            ],
            camera_plan=CameraSpec(shot_type="close-up", angle="high angle"),
        ),
        subject_assets=[
            Asset3DRecord(
                asset_id=subject_glb.artifact_id,
                subject_id="subject_robot",
                source_image_id="concept_robot",
                glb_uri=subject_glb.uri,
                status="succeeded",
            )
        ],
        scene_asset=Scene3DRecord(
            scene_asset_id="scene_asset_001",
            service="hy_world",
            raw_output_type="mesh",
            adapted_artifact_ids=[scene_glb.artifact_id],
            blender_import_mode="mesh_import",
            status="adapted",
        ),
        artifacts=[scene_glb, subject_glb],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    return run_dir


def _patch_fake_script_dispatcher(monkeypatch):
    calls = []

    class FakeScriptDomainToolDispatcher:
        def __init__(self, *, state, root, blender_path=None):
            self.state = state
            self.root = root
            self.blender_path = blender_path

        def dispatch(self, domain_tool_name, arguments, *, options=None):
            dry_run = bool(options and options.dry_run)
            args = {key: str(value) for key, value in arguments.items()}
            calls.append((domain_tool_name, args, dry_run))
            if not dry_run and domain_tool_name == "export_viewer_scene":
                Path(args["viewer_glb"]).parent.mkdir(parents=True, exist_ok=True)
                Path(args["viewer_glb"]).write_bytes(b"glb")
                Path(args["scene_state_json"]).write_text(
                    json.dumps(
                        {
                            "viewer_scene_id": "viewer_scene_refreshed",
                            "objects": [{"viewer_object_id": "hero_viewer", "display_name": "Hero"}],
                        }
                    ),
                    encoding="utf-8",
                )
            if not dry_run and domain_tool_name == "import_scene_asset":
                Path(args["output_blend"]).parent.mkdir(parents=True, exist_ok=True)
                Path(args["output_blend"]).write_bytes(b"blend")
                Path(args["preview_png"]).write_bytes(b"png")
            if not dry_run and domain_tool_name == "render_preview":
                Path(args["preview_png"]).parent.mkdir(parents=True, exist_ok=True)
                Path(args["preview_png"]).write_bytes(b"png")
                Path(args["preview_blend"]).write_bytes(b"blend")
            record = ToolCallRecord(
                tool_call_id=f"tool_call_{len(calls):03d}",
                project_id=self.state.project_id,
                phase=self.state.phase,
                domain_tool_name=domain_tool_name,
                tool_name=domain_tool_name,
                raw_tool_calls=[{"kind": "fake_script", "arguments": args}],
                arguments=args,
                arguments_summary=args,
                result_summary={"dry_run": dry_run},
                status=ToolCallStatus.SUCCEEDED,
                started_at="2026-06-30T00:00:00+00:00",
                ended_at="2026-06-30T00:00:01+00:00",
                finished_at="2026-06-30T00:00:01+00:00",
            )
            self.state.tool_call_log.append(record)
            return DomainToolDispatchResult(
                domain_tool_name=domain_tool_name,
                ok=True,
                dry_run=dry_run,
                tool_call_id=record.tool_call_id,
                tool_call_status=record.status.value,
                arguments=args,
                outputs={
                    key: args[key]
                    for key in ("viewer_glb", "scene_state_json", "output_blend", "preview_png", "preview_blend")
                    if key in args
                },
                tool_call_record=record,
            )

    monkeypatch.setattr(
        "agent_runtime.runtime_execution.ScriptDomainToolDispatcher",
        FakeScriptDomainToolDispatcher,
    )
    return calls


def _patch_fake_viewer_runtime_adapter(monkeypatch):
    checks = []

    class FakeViewerRuntimeAdapter:
        def __init__(self, *, base_url="http://viewer.local", timeout=10):
            self.base_url = base_url.rstrip("/")
            self.timeout = timeout

        def runtime_status(self):
            checks.append(("runtime_status", self.base_url))
            return {"base_url": self.base_url, "ok": True}

        def check_model(self, model_path):
            path = str(Path(model_path).expanduser().resolve())
            checks.append(("check_model", path))
            return {"ok": True, "asset": {"ok": True}, "viewer": {"ok": True}}

        def artifact_metadata(self, model_path, *, runtime_status=None, model_check=None):
            path = str(Path(model_path).expanduser().resolve())
            checks.append(("artifact_metadata", path))
            return {
                "base_url": self.base_url,
                "model_path": path,
                "asset_url": f"{self.base_url}/asset?path={path}",
                "viewer_url": f"{self.base_url}/viewer?path={path}",
                "runtime_status": runtime_status,
                "model_check": model_check,
            }

    class FakeRuntimeServiceConfig:
        glb_viewer_base_url = "http://viewer.local"

    monkeypatch.setattr("agent_runtime.runtime_execution.ViewerRuntimeAdapter", FakeViewerRuntimeAdapter)
    monkeypatch.setattr("agent_runtime.runtime_execution.RuntimeServiceConfig", FakeRuntimeServiceConfig)
    return checks


def _objects_summary(*, object_name: str) -> dict:
    return {
        "status": "ok",
        "result": {
            "status": "ok",
            "scene_name": "Scene",
            "active_object": object_name,
            "object_mode": "OBJECT",
            "camera_object": "Camera",
            "collections": [
                {
                    "name": "Scene Collection",
                    "objects": [
                        {
                            "name": object_name,
                            "type": "MESH",
                            "visible": True,
                            "hide_viewport": False,
                        }
                    ],
                }
            ],
        },
    }


def _artifact(tmp_path: Path, artifact_id: str, artifact_type: ArtifactType, suffix: str, payload: bytes) -> ArtifactRecord:
    path = tmp_path / f"{artifact_id}{suffix}"
    path.write_bytes(payload)
    return ArtifactRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        uri=str(path),
        mime_type="application/octet-stream",
        semantic_role=artifact_id,
        size_bytes=len(payload),
    )
