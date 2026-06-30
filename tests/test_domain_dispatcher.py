from pathlib import Path

import pytest

from agent_runtime.artifacts import FileArtifactStore
from agent_runtime.domain_dispatcher import (
    BlenderMCPDomainToolDispatcher,
    Hunyuan3DDomainToolDispatcher,
    ScriptDomainToolDispatcher,
    WorldMirrorDomainToolDispatcher,
)
from agent_runtime.service_adapters import (
    Hunyuan3DGenerationPayload,
    JsonHttpResult,
    WorldMirrorGenerationCallPlan,
    WorldMirrorGenerationContract,
    WorldMirrorGenerationSubmission,
    WorldMirrorQueuedPollResult,
    WorldMirrorQueuedSubmission,
    WorldMirrorSSEEvent,
    WorldMirrorUploadPollResult,
    WorldMirrorUploadSubmission,
)
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    BlenderObjectRecord,
    BlenderSceneState,
    WorkflowPhase,
)
from agent_runtime.tool_executor import CommandExecutionOptions


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"placeholder")


def _make_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _touch(root / "tools/render_glb_preview.py")
    _touch(root / "tools/compose_blender_scene.py")
    _touch(root / "tools/export_viewer_scene.py")
    return root


def _state(phase: WorkflowPhase = WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION) -> AgentProjectState:
    return AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=phase,
    )


def _blender_edit_state() -> AgentProjectState:
    state = _state(WorkflowPhase.BLENDER_EDIT)
    state.blender_scene = BlenderSceneState(
        blender_scene_id="Scene",
        objects=[
            BlenderObjectRecord(
                object_id="hero",
                blender_name="Hero",
                subject_id="subject_robot",
                object_type="subject_asset",
            )
        ],
    )
    return state


def _objects_summary(*, object_name: str = "Hero") -> dict:
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
                            "parent": None,
                            "data_name": object_name,
                            "selected": True,
                            "visible": True,
                            "hide_viewport": False,
                        }
                    ],
                    "children": [],
                }
            ],
        },
    }


class FakeHunyuan3DService:
    base_url = "http://fake-hunyuan"

    def __init__(self) -> None:
        self.submitted_payloads = []
        self.status_by_uid = {}
        self.saved_requests = []

    def build_payload(self, **kwargs):
        image = kwargs.get("image_base64")
        if image is None:
            image_path = kwargs.get("image_path")
            image = Path(image_path).read_bytes().hex() if image_path else "fake_image"
        return Hunyuan3DGenerationPayload(
            image=image,
            texture=kwargs.get("texture", True),
            seed=kwargs.get("seed", 1234),
            randomize_seed=kwargs.get("randomize_seed", True),
            num_inference_steps=kwargs.get("num_inference_steps", 50),
        )

    def submit_async(self, payload):
        self.submitted_payloads.append(payload)
        return {"ok": True, "uid": "uid_001", "raw": {"data": {"uid": "uid_001"}}}

    def task_status(self, uid: str):
        return self.status_by_uid.get(
            uid,
            {"ok": True, "status": "completed", "has_model_base64": True, "raw": {"data": {"status": "completed"}}},
        )

    def save_status_model(self, status_payload, output_path):
        self.saved_requests.append((status_payload, output_path))
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-glb")
        return output


class FakeWorldMirrorService:
    base_url = "http://fake-worldmirror"

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.status_calls = 0
        self.uploaded_requests = []
        self.upload_polled_requests = []
        self.submitted_requests = []
        self.polled_requests = []

    def runtime_status(self):
        self.status_calls += 1
        return {
            "ok": self.ok,
            "base_url": self.base_url,
            "index": {"ok": True},
            "config": {"ok": self.ok},
        }

    def build_generation_call_plan(self, request):
        return WorldMirrorGenerationCallPlan(
            ok=self.ok,
            base_url=self.base_url,
            api_prefix="/gradio_api",
            upload_url=f"{self.base_url}/gradio_api/call/_on_upload",
            reconstruct_url=f"{self.base_url}/gradio_api/call/gradio_demo",
            upload_payload={"data": [[], request.time_interval]} if request.input_files else None,
            reconstruct_payload={
                "data": [
                    request.workspace_dir or "<from _on_upload output[0]>",
                    request.frame_selector,
                    request.show_camera,
                    request.filter_sky_bg,
                    request.show_mesh,
                    request.filter_ambiguous,
                ]
            },
            workspace_dir=request.workspace_dir,
            workspace_source="provided_workspace_dir" if request.workspace_dir else "upload_output_target_dir",
            request=request,
            contract=WorldMirrorGenerationContract(ok=self.ok, base_url=self.base_url),
            issues=[] if self.ok else ["fake_failure"],
        )

    def submit_upload(self, request):
        self.uploaded_requests.append(request)
        plan = self.build_generation_call_plan(request)
        return WorldMirrorUploadSubmission(
            ok=self.ok,
            call_plan=plan,
            upload_submission=WorldMirrorQueuedSubmission(
                ok=self.ok,
                base_url=self.base_url,
                api_prefix="/gradio_api",
                api_name="_on_upload",
                submit_url=f"{self.base_url}/gradio_api/call/_on_upload",
                event_id="upload_evt_fake_001" if self.ok else None,
                raw=JsonHttpResult(
                    url=f"{self.base_url}/gradio_api/call/_on_upload",
                    ok=self.ok,
                    status=200 if self.ok else 500,
                    data={"event_id": "upload_evt_fake_001"} if self.ok else {},
                ),
                submits_long_running_job=False,
                issues=[] if self.ok else ["fake_upload_failure"],
            ),
            issues=[] if self.ok else ["fake_upload_failure"],
        )

    def poll_upload(self, *, event_id: str, api_prefix: str = "/gradio_api"):
        self.upload_polled_requests.append((event_id, api_prefix))
        poll_result = WorldMirrorQueuedPollResult(
            ok=self.ok,
            base_url=self.base_url,
            api_prefix=api_prefix,
            api_name="_on_upload",
            event_id=event_id,
            stream_url=f"{self.base_url}{api_prefix}/call/_on_upload/{event_id}",
            complete=self.ok,
            output_data=["gradio_demo_output/input_images_uploaded"] if self.ok else None,
            events=(
                [WorldMirrorSSEEvent(event="complete", data=["gradio_demo_output/input_images_uploaded"])]
                if self.ok
                else []
            ),
            issues=[] if self.ok else ["fake_upload_poll_failure"],
        )
        return WorldMirrorUploadPollResult(
            ok=self.ok,
            poll_result=poll_result,
            target_dir="gradio_demo_output/input_images_uploaded" if self.ok else None,
            issues=[] if self.ok else ["fake_upload_poll_failure"],
        )

    def submit_generation(self, request):
        self.submitted_requests.append(request)
        plan = self.build_generation_call_plan(request)
        return WorldMirrorGenerationSubmission(
            ok=self.ok,
            call_plan=plan,
            reconstruct_submission=WorldMirrorQueuedSubmission(
                ok=self.ok,
                base_url=self.base_url,
                api_prefix="/gradio_api",
                api_name="gradio_demo",
                submit_url=f"{self.base_url}/gradio_api/call/gradio_demo",
                event_id="evt_fake_001" if self.ok else None,
                raw=JsonHttpResult(
                    url=f"{self.base_url}/gradio_api/call/gradio_demo",
                    ok=self.ok,
                    status=200 if self.ok else 500,
                    data={"event_id": "evt_fake_001"} if self.ok else {},
                ),
                submits_long_running_job=True,
                issues=[] if self.ok else ["fake_submit_failure"],
            ),
            issues=[] if self.ok else ["fake_submit_failure"],
        )

    def poll_queued_call(self, *, api_name: str, event_id: str, api_prefix: str = "/gradio_api"):
        self.polled_requests.append((api_name, event_id, api_prefix))
        return WorldMirrorQueuedPollResult(
            ok=self.ok,
            base_url=self.base_url,
            api_prefix=api_prefix,
            api_name=api_name,
            event_id=event_id,
            stream_url=f"{self.base_url}{api_prefix}/call/{api_name}/{event_id}",
            complete=self.ok,
            output_data=[{"path": "scene.glb"}] if self.ok else None,
            events=[WorldMirrorSSEEvent(event="complete", data=[{"path": "scene.glb"}])] if self.ok else [],
            issues=[] if self.ok else ["fake_poll_failure"],
        )


def _worldmirror_output(root: Path) -> Path:
    output = root / "worldmirror_output"
    output.mkdir()
    (output / "scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb").write_bytes(b"glb")
    (output / "camera_params.json").write_text("{}", encoding="utf-8")
    (output / "gaussians.ply").write_text("ply", encoding="utf-8")
    return output


def test_dispatcher_import_scene_asset_wraps_existing_compose_script(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    scene = tmp_path / "scene.glb"
    asset = tmp_path / "asset.glb"
    _touch(blender)
    _touch(scene)
    _touch(asset)
    state = _state()

    result = ScriptDomainToolDispatcher(
        state=state,
        root=root,
        blender_path=blender,
    ).dispatch(
        "import_scene_asset",
        {
            "scene_glb": scene,
            "asset_glb": asset,
            "preview_png": tmp_path / "composed.png",
            "output_blend": tmp_path / "composed.blend",
        },
        options=CommandExecutionOptions(dry_run=True),
    )

    assert result.ok is True
    assert result.dry_run is True
    assert result.domain_tool_name == "import_scene_asset"
    assert result.outputs["output_blend"] == str((tmp_path / "composed.blend").resolve())
    assert len(state.tool_call_log) == 1
    assert state.tool_call_log[0].domain_tool_name == "import_scene_asset"
    assert state.tool_call_log[0].raw_tool_calls[0]["argv"][3] == str(
        (root / "tools/compose_blender_scene.py").resolve()
    )


def test_dispatcher_export_viewer_scene_wraps_existing_export_script(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    blend = tmp_path / "scene.blend"
    _touch(blender)
    _touch(blend)
    state = _state()

    result = ScriptDomainToolDispatcher(
        state=state,
        root=root,
        blender_path=blender,
    ).dispatch(
        "export_viewer_scene",
        {
            "input_blend": blend,
            "viewer_glb": tmp_path / "viewer_scene.glb",
            "scene_state_json": tmp_path / "scene_state.json",
        },
        options=CommandExecutionOptions(dry_run=True),
    )

    assert result.ok is True
    assert result.outputs["viewer_glb"] == str((tmp_path / "viewer_scene.glb").resolve())
    assert state.tool_call_log[0].domain_tool_name == "export_viewer_scene"
    assert state.tool_call_log[0].raw_tool_calls[0]["argv"][3] == str(
        (root / "tools/export_viewer_scene.py").resolve()
    )


def test_dispatcher_render_preview_wraps_existing_preview_script(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    glb = tmp_path / "asset.glb"
    _touch(blender)
    _touch(glb)
    state = _state(WorkflowPhase.BLENDER_EDIT)

    result = ScriptDomainToolDispatcher(
        state=state,
        root=root,
        blender_path=blender,
    ).dispatch(
        "render_preview",
        {
            "input_glb": glb,
            "preview_png": tmp_path / "preview.png",
            "preview_blend": tmp_path / "preview.blend",
        },
        options=CommandExecutionOptions(dry_run=True),
    )

    assert result.ok is True
    assert result.outputs["preview_blend"] == str((tmp_path / "preview.blend").resolve())
    assert state.tool_call_log[0].domain_tool_name == "render_preview"
    assert state.tool_call_log[0].raw_tool_calls[0]["argv"][3] == str(
        (root / "tools/render_glb_preview.py").resolve()
    )


def test_dispatcher_rejects_missing_required_arguments(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    state = _state()

    with pytest.raises(ValueError, match="missing required domain tool arguments"):
        ScriptDomainToolDispatcher(state=state, root=root).dispatch(
            "import_scene_asset",
            {"scene_glb": tmp_path / "scene.glb"},
            options=CommandExecutionOptions(dry_run=True),
        )

    assert state.tool_call_log == []


def test_dispatcher_keeps_phase_guard_from_tool_executor(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    blender = tmp_path / "blender"
    scene = tmp_path / "scene.glb"
    asset = tmp_path / "asset.glb"
    _touch(blender)
    _touch(scene)
    _touch(asset)
    state = _state(WorkflowPhase.CONCEPT_GENERATION)

    with pytest.raises(ValueError, match="not allowed"):
        ScriptDomainToolDispatcher(
            state=state,
            root=root,
            blender_path=blender,
        ).dispatch(
            "import_scene_asset",
            {
                "scene_glb": scene,
                "asset_glb": asset,
                "preview_png": tmp_path / "composed.png",
                "output_blend": tmp_path / "composed.blend",
            },
            options=CommandExecutionOptions(dry_run=True),
        )

    assert state.tool_call_log == []


def test_dispatcher_rejects_unimplemented_domain_tool(tmp_path: Path) -> None:
    root = _make_root(tmp_path)

    with pytest.raises(NotImplementedError, match="not script-backed"):
        ScriptDomainToolDispatcher(state=_state(), root=root).dispatch(
            "build_subject_asset",
            {},
            options=CommandExecutionOptions(dry_run=True),
        )


def test_blender_mcp_dispatcher_dry_run_records_safe_plan_without_raw_call() -> None:
    state = _blender_edit_state()
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        return {"status": "ok", "result": {"ok": True}}

    result = BlenderMCPDomainToolDispatcher(state=state, raw_tool_caller=raw_tool_caller).dispatch(
        "move_subject",
        {"blender_object_id": "hero", "location": [1, 2, 3]},
        options=CommandExecutionOptions(dry_run=True),
    )

    assert result.ok is True
    assert result.dry_run is True
    assert raw_calls == []
    assert result.outputs["planned"] is True
    assert result.outputs["raw_tool_name"] == "execute_blender_code"
    assert result.outputs["arguments_summary"] == {"blender_name": "Hero", "location": [1.0, 2.0, 3.0]}
    assert len(state.tool_call_log) == 1
    record = state.tool_call_log[0]
    assert record.domain_tool_name == "move_subject"
    assert record.tool_name == "execute_blender_code"
    assert record.status.value == "succeeded"
    assert record.raw_tool_calls[0]["planned_only"] is True


def test_blender_mcp_dispatcher_dry_run_accepts_live_llm_object_aliases() -> None:
    state = _blender_edit_state()
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        return {"status": "ok", "result": {"ok": True}}

    result = BlenderMCPDomainToolDispatcher(state=state, raw_tool_caller=raw_tool_caller).dispatch(
        "move_subject",
        {"object_id": "hero", "subject_id": "subject_robot", "location": [1, 2, 3]},
        options=CommandExecutionOptions(dry_run=True),
    )

    assert result.ok is True
    assert result.dry_run is True
    assert raw_calls == []
    assert result.outputs["arguments_summary"] == {"blender_name": "Hero", "location": [1.0, 2.0, 3.0]}
    record = state.tool_call_log[0]
    assert record.domain_tool_name == "move_subject"
    assert record.status.value == "succeeded"


def test_blender_mcp_dispatcher_executes_raw_tool_and_resynchronizes_scene() -> None:
    state = _blender_edit_state()
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        if tool_name == "execute_blender_code":
            return {"status": "ok", "result": {"ok": True, "object": "Hero", "location": [1, 2, 3]}}
        if tool_name == "get_objects_summary":
            return _objects_summary(object_name="Hero")
        raise AssertionError(tool_name)

    dispatcher = BlenderMCPDomainToolDispatcher(state=state, raw_tool_caller=raw_tool_caller)
    result = dispatcher.dispatch(
        "move_subject",
        {"blender_object_id": "hero", "location": [1, 2, 3]},
    )

    assert result.ok is True
    assert result.outputs["blender_scene_object_count"] == 1
    assert [call[0] for call in raw_calls] == ["execute_blender_code", "get_objects_summary"]
    assert dispatcher.state.blender_scene.objects[0].blender_name == "Hero"
    assert dispatcher.state.last_error is None
    record = dispatcher.state.tool_call_log[0]
    assert record.status.value == "succeeded"
    assert len(record.raw_tool_calls) == 2
    assert record.raw_tool_calls[0]["tool_name"] == "execute_blender_code"
    assert record.raw_tool_calls[1]["tool_name"] == "get_objects_summary"


def test_blender_mcp_dispatcher_loads_run_local_blend_before_live_edit(tmp_path: Path) -> None:
    state = _blender_edit_state()
    blend = tmp_path / "scene.blend"
    _touch(blend)
    state.blender_scene = state.blender_scene.model_copy(
        update={
            "blend_file_artifact_id": "blend_file",
            "scene_asset_id": "scene_asset_001",
        }
    )
    state.artifacts.append(
        ArtifactRecord(
            artifact_id="blend_file",
            artifact_type=ArtifactType.BLENDER_FILE,
            uri=str(blend),
            mime_type="application/x-blender",
        )
    )
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        if tool_name == "execute_blender_code":
            code = arguments["code"]
            if "open_mainfile" in code:
                return {"status": "ok", "result": {"ok": True, "loaded_blend": str(blend)}}
            if "save_as_mainfile" in code:
                return {"status": "ok", "result": {"ok": True, "saved_to": str(blend)}}
            return {"status": "ok", "result": {"ok": True, "object": "Hero", "location": [1, 2, 3]}}
        if tool_name == "get_objects_summary":
            return _objects_summary(object_name="Hero")
        raise AssertionError(tool_name)

    dispatcher = BlenderMCPDomainToolDispatcher(
        state=state,
        raw_tool_caller=raw_tool_caller,
        ensure_blend_loaded=True,
    )
    result = dispatcher.dispatch(
        "move_subject",
        {"blender_object_id": "hero", "location": [1, 2, 3]},
    )

    assert result.ok is True
    assert [call[0] for call in raw_calls] == [
        "execute_blender_code",
        "execute_blender_code",
        "get_objects_summary",
        "execute_blender_code",
    ]
    assert "open_mainfile" in raw_calls[0][1]["code"]
    assert str(blend) in raw_calls[0][1]["code"]
    assert result.outputs["blend_load_raw_result"]["status"] == "ok"
    assert dispatcher.state.blender_scene.scene_asset_id == "scene_asset_001"
    record = dispatcher.state.tool_call_log[0]
    assert record.raw_tool_calls[0]["purpose"] == "load_blend_before_edit"
    assert record.raw_tool_calls[1]["tool_name"] == "execute_blender_code"


def test_blender_mcp_dispatcher_read_only_summary_updates_blender_scene() -> None:
    state = _blender_edit_state()

    def raw_tool_caller(tool_name, arguments):
        assert tool_name == "get_objects_summary"
        assert arguments == {}
        return _objects_summary(object_name="Hero")

    dispatcher = BlenderMCPDomainToolDispatcher(state=state, raw_tool_caller=raw_tool_caller)
    result = dispatcher.dispatch("get_blender_scene_summary", {})

    assert result.ok is True
    assert result.outputs["blender_scene_object_count"] == 1
    assert dispatcher.state.blender_scene.blender_scene_id == "Scene"
    assert dispatcher.state.tool_call_log[0].domain_tool_name == "get_blender_scene_summary"


def test_blender_mcp_dispatcher_records_plan_rejection_and_last_error() -> None:
    state = _blender_edit_state()

    dispatcher = BlenderMCPDomainToolDispatcher(
        state=state,
        raw_tool_caller=lambda tool_name, arguments: {"status": "ok"},
    )
    result = dispatcher.dispatch(
        "delete_subject",
        {"blender_object_id": "hero"},
    )

    assert result.ok is False
    assert result.outputs["requires_confirmation"] is True
    assert state.tool_call_log[0].status.value == "failed"
    assert state.last_error.code == "BLENDER_MCP_PLAN_REJECTED"
    assert state.last_error.retriable is False


def test_blender_mcp_dispatcher_records_sync_failure_after_raw_success() -> None:
    state = _blender_edit_state()

    def raw_tool_caller(tool_name, arguments):
        if tool_name == "execute_blender_code":
            return {"status": "ok", "result": {"ok": True}}
        if tool_name == "get_objects_summary":
            return {"status": "ok", "result": {"status": "error", "message": "scene unavailable"}}
        raise AssertionError(tool_name)

    dispatcher = BlenderMCPDomainToolDispatcher(state=state, raw_tool_caller=raw_tool_caller)
    result = dispatcher.dispatch(
        "move_subject",
        {"blender_object_id": "hero", "location": [1, 2, 3]},
    )

    assert result.ok is False
    assert dispatcher.state.last_error.code == "BLENDER_MCP_SYNC_FAILED"
    assert dispatcher.state.last_error.retriable is True
    assert dispatcher.state.tool_call_log[0].error_message == "scene unavailable"


def test_blender_mcp_dispatcher_keeps_phase_guard() -> None:
    state = _state(WorkflowPhase.CONCEPT_GENERATION)

    with pytest.raises(ValueError, match="not allowed"):
        BlenderMCPDomainToolDispatcher(
            state=state,
            raw_tool_caller=lambda tool_name, arguments: {"status": "ok"},
        ).dispatch(
            "move_subject",
            {"blender_name": "Hero", "location": [1, 2, 3]},
        )

    assert state.tool_call_log == []


def test_hunyuan3d_dispatcher_submit_dry_run_does_not_call_service() -> None:
    service = FakeHunyuan3DService()
    state = _state(WorkflowPhase.SUBJECT_ASSET_GENERATION)

    result = Hunyuan3DDomainToolDispatcher(
        state=state,
        service_adapter=service,
    ).dispatch(
        "build_subject_asset",
        {
            "operation": "submit_async",
            "subject_id": "subject_001",
            "source_image_id": "image_001",
            "image_base64": "abc",
        },
        options=CommandExecutionOptions(dry_run=True),
    )

    assert result.ok is True
    assert result.dry_run is True
    assert result.outputs["submitted"] is False
    assert service.submitted_payloads == []
    assert state.subject_assets == []
    assert len(state.tool_call_log) == 1
    assert state.tool_call_log[0].arguments["image_base64"] == "<base64:3 chars>"


def test_hunyuan3d_dispatcher_submit_updates_running_subject_asset() -> None:
    service = FakeHunyuan3DService()
    state = _state(WorkflowPhase.SUBJECT_ASSET_GENERATION)
    dispatcher = Hunyuan3DDomainToolDispatcher(state=state, service_adapter=service)

    result = dispatcher.dispatch(
        "build_subject_asset",
        {
            "operation": "submit_async",
            "asset_id": "asset_001",
            "subject_id": "subject_001",
            "source_image_id": "image_001",
            "image_base64": "abc",
            "texture": False,
            "randomize_seed": False,
            "seed": 7,
        },
    )

    assert result.ok is True
    assert result.outputs["uid"] == "uid_001"
    assert service.submitted_payloads
    assert dispatcher.state.subject_assets[0].asset_id == "asset_001"
    assert dispatcher.state.subject_assets[0].job_id == "uid_001"
    assert dispatcher.state.subject_assets[0].status == "running"
    assert dispatcher.state.subject_assets[0].generation_params["image"] == "<base64:3 chars>"


def test_hunyuan3d_dispatcher_check_status_records_service_status() -> None:
    service = FakeHunyuan3DService()
    service.status_by_uid["uid_001"] = {
        "ok": True,
        "status": "completed",
        "has_model_base64": True,
        "raw": {"data": {"status": "completed", "model_base64": "Z2xi"}},
    }
    state = _state(WorkflowPhase.SUBJECT_ASSET_GENERATION)

    result = Hunyuan3DDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_subject_asset",
        {"operation": "check_status", "uid": "uid_001"},
    )

    assert result.ok is True
    assert result.outputs["status"]["status"] == "completed"
    assert result.outputs["status"]["raw"]["data"]["model_base64"] == "<base64:4 chars>"
    assert state.tool_call_log[0].result_summary["status"]["raw"]["data"]["model_base64"] == "<base64:4 chars>"


def test_hunyuan3d_dispatcher_save_completed_registers_artifact_and_asset(tmp_path: Path) -> None:
    service = FakeHunyuan3DService()
    state = _state(WorkflowPhase.SUBJECT_ASSET_GENERATION)
    store = FileArtifactStore(tmp_path / "artifacts")
    dispatcher = Hunyuan3DDomainToolDispatcher(
        state=state,
        service_adapter=service,
        artifact_store=store,
    )

    result = dispatcher.dispatch(
        "build_subject_asset",
        {
            "operation": "save_completed",
            "asset_id": "asset_001",
            "uid": "uid_001",
            "subject_id": "subject_001",
            "source_image_id": "image_001",
            "status_payload": {"raw": {"data": {"model_base64": "Z2xi"}}},
            "output_glb": tmp_path / "subject.glb",
        },
    )

    assert result.ok is True
    assert result.outputs["artifact_id"] == "asset_001"
    assert (tmp_path / "subject.glb").read_bytes() == b"fake-glb"
    assert dispatcher.state.artifacts[0].artifact_id == "asset_001"
    assert dispatcher.state.artifacts[0].artifact_type.value == "SUBJECT_3D_ASSET"
    assert dispatcher.state.subject_assets[0].status == "succeeded"
    assert dispatcher.state.subject_assets[0].glb_uri == str((tmp_path / "subject.glb").resolve())
    assert len(store.load_records()) == 1


def test_hunyuan3d_dispatcher_save_completed_requires_artifact_store(tmp_path: Path) -> None:
    state = _state(WorkflowPhase.SUBJECT_ASSET_GENERATION)

    with pytest.raises(ValueError, match="artifact_store is required"):
        Hunyuan3DDomainToolDispatcher(state=state, service_adapter=FakeHunyuan3DService()).dispatch(
            "build_subject_asset",
            {
                "operation": "save_completed",
                "subject_id": "subject_001",
                "source_image_id": "image_001",
                "status_payload": {"raw": {"data": {"model_base64": "Z2xi"}}},
                "output_glb": tmp_path / "subject.glb",
            },
        )


def test_hunyuan3d_dispatcher_keeps_phase_guard() -> None:
    state = _state(WorkflowPhase.BLENDER_EDIT)

    with pytest.raises(ValueError, match="not allowed"):
        Hunyuan3DDomainToolDispatcher(state=state, service_adapter=FakeHunyuan3DService()).dispatch(
            "build_subject_asset",
            {
                "operation": "submit_async",
                "subject_id": "subject_001",
                "source_image_id": "image_001",
                "image_base64": "abc",
            },
            options=CommandExecutionOptions(dry_run=True),
        )


def test_worldmirror_dispatcher_runtime_status_dry_run_does_not_call_service() -> None:
    service = FakeWorldMirrorService()
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {"operation": "runtime_status"},
        options=CommandExecutionOptions(dry_run=True),
    )

    assert result.ok is True
    assert result.dry_run is True
    assert result.outputs["checked"] is False
    assert service.status_calls == 0
    assert state.tool_call_log[0].domain_tool_name == "build_scene_asset"
    assert state.tool_call_log[0].raw_tool_calls[0]["service"] == "hy_world"


def test_worldmirror_dispatcher_runtime_status_records_service_status() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {"operation": "runtime_status"},
    )

    assert result.ok is True
    assert result.outputs["checked"] is True
    assert result.outputs["status"]["ok"] is True
    assert service.status_calls == 1
    assert state.tool_call_log[0].result_summary["status"]["base_url"] == "http://fake-worldmirror"


def test_worldmirror_dispatcher_prepare_generation_records_call_plan() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {
            "operation": "prepare_generation",
            "workspace_dir": "gradio_demo_output/input_images_existing",
            "show_camera": False,
        },
    )

    assert result.ok is True
    assert result.outputs["operation"] == "prepare_generation"
    assert result.outputs["prepared"] is True
    assert result.outputs["submits_long_running_job"] is False
    assert result.outputs["call_plan"]["reconstruct_url"] == "http://fake-worldmirror/gradio_api/call/gradio_demo"
    assert result.outputs["call_plan"]["reconstruct_payload"]["data"][0] == "gradio_demo_output/input_images_existing"
    assert result.outputs["call_plan"]["reconstruct_payload"]["data"][2] is False
    assert state.scene_asset is None
    assert state.tool_call_log[0].raw_tool_calls[0]["operation"] == "prepare_generation"


def test_worldmirror_dispatcher_upload_inputs_requires_confirmation() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {
            "operation": "upload_inputs",
            "input_files": ["view.png"],
        },
    )

    assert result.ok is False
    assert result.outputs["submitted"] is False
    assert result.outputs["submits_long_running_job"] is False
    assert result.outputs["issues"] == ["worldmirror_upload_requires_explicit_confirmation"]
    assert service.uploaded_requests == []


def test_worldmirror_dispatcher_upload_inputs_records_event_id_when_confirmed() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {
            "operation": "upload_inputs",
            "input_files": ["view.png"],
            "confirm_upload": True,
        },
    )

    assert result.ok is True
    assert result.outputs["submitted"] is True
    assert result.outputs["submits_long_running_job"] is False
    assert result.outputs["submission"]["upload_submission"]["event_id"] == "upload_evt_fake_001"
    assert len(service.uploaded_requests) == 1
    assert state.tool_call_log[0].raw_tool_calls[0]["operation"] == "upload_inputs"


def test_worldmirror_dispatcher_poll_upload_extracts_target_dir_when_confirmed() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {
            "operation": "poll_upload",
            "event_id": "upload_evt_fake_001",
            "confirm_poll": True,
        },
    )

    assert result.ok is True
    assert result.outputs["polled"] is True
    assert result.outputs["target_dir"] == "gradio_demo_output/input_images_uploaded"
    assert result.outputs["upload_result"]["target_dir"] == "gradio_demo_output/input_images_uploaded"
    assert service.upload_polled_requests == [("upload_evt_fake_001", "/gradio_api")]


def test_worldmirror_dispatcher_submit_generation_requires_confirmation() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {
            "operation": "submit_generation",
            "workspace_dir": "gradio_demo_output/input_images_existing",
        },
    )

    assert result.ok is False
    assert result.outputs["submitted"] is False
    assert result.outputs["submits_long_running_job"] is False
    assert result.outputs["issues"] == ["worldmirror_submit_requires_explicit_confirmation"]
    assert service.submitted_requests == []
    assert state.tool_call_log[0].status.value == "failed"


def test_worldmirror_dispatcher_submit_generation_records_event_id_when_confirmed() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {
            "operation": "submit_generation",
            "workspace_dir": "gradio_demo_output/input_images_existing",
            "confirm_submit": True,
        },
    )

    assert result.ok is True
    assert result.outputs["submitted"] is True
    assert result.outputs["submits_long_running_job"] is True
    assert result.outputs["submission"]["reconstruct_submission"]["event_id"] == "evt_fake_001"
    assert len(service.submitted_requests) == 1
    assert state.tool_call_log[0].raw_tool_calls[0]["operation"] == "submit_generation"


def test_worldmirror_dispatcher_poll_generation_requires_confirmation() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {
            "operation": "poll_generation",
            "event_id": "evt_fake_001",
        },
    )

    assert result.ok is False
    assert result.outputs["polled"] is False
    assert result.outputs["submits_long_running_job"] is False
    assert result.outputs["issues"] == ["worldmirror_poll_requires_explicit_confirmation"]
    assert service.polled_requests == []


def test_worldmirror_dispatcher_poll_generation_records_complete_result_when_confirmed() -> None:
    service = FakeWorldMirrorService(ok=True)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(state=state, service_adapter=service).dispatch(
        "build_scene_asset",
        {
            "operation": "poll_generation",
            "event_id": "evt_fake_001",
            "api_name": "gradio_demo",
            "confirm_poll": True,
        },
    )

    assert result.ok is True
    assert result.outputs["polled"] is True
    assert result.outputs["submits_long_running_job"] is True
    assert result.outputs["poll_result"]["complete"] is True
    assert result.outputs["poll_result"]["output_data"] == [{"path": "scene.glb"}]
    assert service.polled_requests == [("gradio_demo", "evt_fake_001", "/gradio_api")]


def test_worldmirror_dispatcher_register_existing_output_updates_scene_asset(tmp_path: Path) -> None:
    output = _worldmirror_output(tmp_path)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)
    store = FileArtifactStore(tmp_path / "artifacts")
    dispatcher = WorldMirrorDomainToolDispatcher(
        state=state,
        service_adapter=FakeWorldMirrorService(),
        artifact_store=store,
    )

    result = dispatcher.dispatch(
        "adapt_scene_asset",
        {
            "operation": "register_existing_output",
            "scene_asset_id": "scene_asset_001",
            "output_dir": output,
            "source_scene_concept_image_ids": ["scene_concept_001"],
        },
    )

    assert result.ok is True
    assert result.outputs["registered"] is True
    assert result.outputs["scene_asset_id"] == "scene_asset_001"
    assert dispatcher.state.scene_asset is not None
    assert dispatcher.state.scene_asset.status == "adapted"
    assert dispatcher.state.scene_asset.adapted_artifact_ids == ["scene_asset_001_scene_glb"]
    assert [artifact.artifact_id for artifact in dispatcher.state.artifacts] == [
        "scene_asset_001_scene_glb",
        "scene_asset_001_camera_params_json",
        "scene_asset_001_gaussian_ply",
    ]
    assert len(store.load_records()) == 3


def test_worldmirror_dispatcher_register_existing_output_dry_run_does_not_register(tmp_path: Path) -> None:
    output = _worldmirror_output(tmp_path)
    state = _state(WorkflowPhase.SCENE_ASSET_GENERATION)

    result = WorldMirrorDomainToolDispatcher(
        state=state,
        service_adapter=FakeWorldMirrorService(),
    ).dispatch(
        "adapt_scene_asset",
        {
            "operation": "register_existing_output",
            "scene_asset_id": "scene_asset_001",
            "output_dir": output,
        },
        options=CommandExecutionOptions(dry_run=True),
    )

    assert result.ok is True
    assert result.dry_run is True
    assert result.outputs["registered"] is False
    assert state.scene_asset is None
    assert state.artifacts == []


def test_worldmirror_dispatcher_keeps_phase_guard(tmp_path: Path) -> None:
    state = _state(WorkflowPhase.BLENDER_EDIT)

    with pytest.raises(ValueError, match="not allowed"):
        WorldMirrorDomainToolDispatcher(state=state, service_adapter=FakeWorldMirrorService()).dispatch(
            "build_scene_asset",
            {"operation": "runtime_status"},
            options=CommandExecutionOptions(dry_run=True),
        )

    assert state.tool_call_log == []
