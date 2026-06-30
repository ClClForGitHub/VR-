import json
from pathlib import Path

import pytest

from agent_runtime.codex_self_mcp import CodexSelfMCPCallPlan, CodexSelfMCPRunResult, CodexSelfMCPStatus
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
    CameraSpec,
    ConceptBundle,
    EnvironmentSpec,
    LightingSpec,
    ReviewPatch,
    SceneSpec,
    SpatialRelation,
    StyleSpec,
    SubjectSpec,
    ViewerSceneState,
    WorkflowPhase,
)
from agent_runtime.workflow_runner import (
    run_blender_edit_workflow,
    run_codex_self_mcp_workflow,
    run_concept_seed_workflow,
    run_concept_regeneration_workflow,
    run_delivery_package_workflow,
    run_local_e2e_workflow,
    run_review_patch_workflow,
    run_scene_asset_workflow,
    run_subject_asset_workflow,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"placeholder")


def _minimal_glb() -> bytes:
    return b"glTF" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little")


def _scene_spec_for_compose() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_plush_flowers",
        title="Plush In Flowers",
        user_goal="Place a yellow plush toy on the right side of a flower field.",
        style=StyleSpec(visual_style="soft realistic"),
        environment=EnvironmentSpec(
            environment_type="flower field",
            description="A bright flower field with grass ground.",
            ground_surface="grass",
        ),
        lighting=LightingSpec(description="soft daylight"),
        camera=CameraSpec(shot_type="close-up", angle="high angle"),
        subjects=[
            SubjectSpec(
                subject_id="subject_plush",
                display_name="Yellow Plush",
                category="character",
                priority="hero",
                description="A yellow cotton plush toy.",
                scale_hint="large hero subject",
                placement_hint="right side foreground",
            )
        ],
        spatial_relations=[
            SpatialRelation(
                relation_id="rel_right",
                source_subject_id="subject_plush",
                relation="right_of",
                target_region="foreground",
            )
        ],
    )


class FakeHunyuan3DService:
    base_url = "http://fake-hunyuan"

    def __init__(self) -> None:
        self.submitted_payloads = []
        self.status_requests = []
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
        self.status_requests.append(uid)
        return {
            "ok": True,
            "status": "completed",
            "has_model_base64": True,
            "raw": {"data": {"status": "completed", "model_base64": "Z2xi"}},
        }

    def save_status_model(self, status_payload, output_path):
        self.saved_requests.append((status_payload, output_path))
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_minimal_glb())
        return output


class FakeWorldMirrorService:
    base_url = "http://fake-worldmirror"

    def __init__(self) -> None:
        self.status_calls = 0
        self.uploaded_requests = []
        self.upload_polled_requests = []
        self.submitted_requests = []
        self.polled_requests = []

    def runtime_status(self):
        self.status_calls += 1
        return {
            "ok": True,
            "base_url": self.base_url,
            "index": {"ok": True},
            "config": {"ok": True},
        }

    def build_generation_call_plan(self, request):
        return WorldMirrorGenerationCallPlan(
            ok=True,
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
            contract=WorldMirrorGenerationContract(ok=True, base_url=self.base_url),
        )

    def submit_upload(self, request):
        self.uploaded_requests.append(request)
        plan = self.build_generation_call_plan(request)
        return WorldMirrorUploadSubmission(
            ok=True,
            call_plan=plan,
            upload_submission=WorldMirrorQueuedSubmission(
                ok=True,
                base_url=self.base_url,
                api_prefix="/gradio_api",
                api_name="_on_upload",
                submit_url=f"{self.base_url}/gradio_api/call/_on_upload",
                event_id="upload_evt_fake_001",
                raw=JsonHttpResult(
                    url=f"{self.base_url}/gradio_api/call/_on_upload",
                    ok=True,
                    status=200,
                    data={"event_id": "upload_evt_fake_001"},
                ),
                submits_long_running_job=False,
            ),
        )

    def poll_upload(self, *, event_id: str, api_prefix: str = "/gradio_api"):
        self.upload_polled_requests.append((event_id, api_prefix))
        poll_result = WorldMirrorQueuedPollResult(
            ok=True,
            base_url=self.base_url,
            api_prefix=api_prefix,
            api_name="_on_upload",
            event_id=event_id,
            stream_url=f"{self.base_url}{api_prefix}/call/_on_upload/{event_id}",
            complete=True,
            output_data=["gradio_demo_output/input_images_uploaded"],
            events=[WorldMirrorSSEEvent(event="complete", data=["gradio_demo_output/input_images_uploaded"])],
        )
        return WorldMirrorUploadPollResult(
            ok=True,
            poll_result=poll_result,
            target_dir="gradio_demo_output/input_images_uploaded",
        )

    def submit_generation(self, request):
        self.submitted_requests.append(request)
        plan = self.build_generation_call_plan(request)
        return WorldMirrorGenerationSubmission(
            ok=True,
            call_plan=plan,
            reconstruct_submission=WorldMirrorQueuedSubmission(
                ok=True,
                base_url=self.base_url,
                api_prefix="/gradio_api",
                api_name="gradio_demo",
                submit_url=f"{self.base_url}/gradio_api/call/gradio_demo",
                event_id="evt_fake_001",
                raw=JsonHttpResult(
                    url=f"{self.base_url}/gradio_api/call/gradio_demo",
                    ok=True,
                    status=200,
                    data={"event_id": "evt_fake_001"},
                ),
                submits_long_running_job=True,
            ),
        )

    def poll_queued_call(self, *, api_name: str, event_id: str, api_prefix: str = "/gradio_api"):
        self.polled_requests.append((api_name, event_id, api_prefix))
        return WorldMirrorQueuedPollResult(
            ok=True,
            base_url=self.base_url,
            api_prefix=api_prefix,
            api_name=api_name,
            event_id=event_id,
            stream_url=f"{self.base_url}{api_prefix}/call/{api_name}/{event_id}",
            complete=True,
            output_data=[{"path": "scene.glb"}],
            events=[WorldMirrorSSEEvent(event="complete", data=[{"path": "scene.glb"}])],
        )


class FakeCodexSelfMCPAdapter:
    def __init__(self) -> None:
        self.repo_path = Path("/fake/codex-self-mcp")
        self.codex_command = "fake-codex"
        self.status_calls = 0
        self.plan_calls = []
        self.run_calls = []

    def status(self, *, run_smoke: bool = False, timeout_seconds: float = 30):
        self.status_calls += 1
        return CodexSelfMCPStatus(
            ok=True,
            repo_path=str(self.repo_path),
            client_script_path=str(self.repo_path / "scripts/call_codex_mcp.py"),
            client_script_exists=True,
            codex_command=self.codex_command,
            codex_cli_path="/usr/bin/fake-codex",
            codex_cli_found=True,
            login_status_ok=True,
            mcp_server_supported=True,
            configured_in_codex_mcp_list=False,
            mcp_list_servers=["blender_lab"],
            issues=[],
        )

    def build_call_plan(self, **kwargs):
        self.plan_calls.append(kwargs)
        cwd = Path(kwargs["cwd"]).expanduser().resolve()
        log_path = Path(kwargs["log_path"]).expanduser()
        prompt = kwargs.get("prompt")
        prompt_file = kwargs.get("prompt_file")
        command = [
            "python",
            str(self.repo_path / "scripts/call_codex_mcp.py"),
            "--cwd",
            str(cwd),
            "--sandbox",
            kwargs.get("sandbox", "workspace-write"),
            "--approval-policy",
            kwargs.get("approval_policy", "never"),
            "--timeout",
            str(kwargs.get("timeout_seconds", 300)),
            "--log",
            str(log_path),
        ]
        if prompt is not None:
            command.extend(["--prompt", prompt])
        else:
            command.extend(["--prompt-file", str(Path(prompt_file).expanduser().resolve())])
        return CodexSelfMCPCallPlan(
            command=command,
            cwd=str(cwd),
            sandbox=kwargs.get("sandbox", "workspace-write"),
            approval_policy=kwargs.get("approval_policy", "never"),
            timeout_seconds=kwargs.get("timeout_seconds", 300),
            log_path=str(log_path),
            prompt_source="inline" if prompt is not None else "file",
            prompt_preview=prompt if prompt is not None else None,
            prompt_file=str(Path(prompt_file).expanduser().resolve()) if prompt_file is not None else None,
            extract_last_image_to=(
                str(Path(kwargs["extract_last_image_to"]).expanduser())
                if kwargs.get("extract_last_image_to") is not None
                else None
            ),
        )

    def run_call_plan(self, plan):
        self.run_calls.append(plan)
        return CodexSelfMCPRunResult(
            ok=True,
            returncode=0,
            stdout_tail="handoff done",
            stderr_tail="",
            plan=plan,
        )


def _worldmirror_output(root: Path) -> Path:
    output = root / "worldmirror_output"
    output.mkdir()
    (output / "scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb").write_bytes(_minimal_glb())
    (output / "camera_params.json").write_text("{}", encoding="utf-8")
    (output / "gaussians.ply").write_text("ply", encoding="utf-8")
    return output


def _delivery_state(tmp_path: Path) -> AgentProjectState:
    files = {}
    for name, suffix, payload in [
        ("blend_file", ".blend", b"blend"),
        ("preview_png", ".png", b"png"),
        ("viewer_glb", ".glb", b"viewer"),
        ("viewer_state", ".json", b"{}"),
        ("subject_glb", ".glb", b"subject"),
        ("scene_glb", ".glb", b"scene"),
    ]:
        path = tmp_path / f"{name}{suffix}"
        path.write_bytes(payload)
        files[name] = path
    artifacts = [
        ArtifactRecord(
            artifact_id="blend_file",
            artifact_type=ArtifactType.BLENDER_FILE,
            uri=str(files["blend_file"]),
            mime_type="application/x-blender",
        ),
        ArtifactRecord(
            artifact_id="preview_png",
            artifact_type=ArtifactType.BLENDER_PREVIEW_RENDER,
            uri=str(files["preview_png"]),
            mime_type="image/png",
        ),
        ArtifactRecord(
            artifact_id="viewer_glb",
            artifact_type=ArtifactType.VIEWER_SCENE_GLB,
            uri=str(files["viewer_glb"]),
            mime_type="model/gltf-binary",
            metadata={
                "viewer": {
                    "asset_url": "http://viewer.local/asset?path=viewer.glb",
                    "viewer_url": "http://viewer.local/viewer?path=viewer.glb",
                    "runtime_status": {"ok": True},
                    "model_check": {"ok": True},
                }
            },
        ),
        ArtifactRecord(
            artifact_id="viewer_state",
            artifact_type=ArtifactType.VIEWER_SCENE_STATE_JSON,
            uri=str(files["viewer_state"]),
            mime_type="application/json",
        ),
        ArtifactRecord(
            artifact_id="subject_glb",
            artifact_type=ArtifactType.SUBJECT_3D_ASSET,
            uri=str(files["subject_glb"]),
            mime_type="model/gltf-binary",
        ),
        ArtifactRecord(
            artifact_id="scene_glb",
            artifact_type=ArtifactType.SCENE_3D_ASSET,
            uri=str(files["scene_glb"]),
            mime_type="model/gltf-binary",
        ),
    ]
    return AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
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
        artifacts=artifacts,
    )


def _blender_edit_state(tmp_path: Path) -> AgentProjectState:
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"blend")
    return AgentProjectState(
        project_id="project_edit",
        thread_id="thread_edit",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        blender_scene=BlenderSceneState(
            blender_scene_id="Scene",
            blend_file_artifact_id="blend_file",
            objects=[
                BlenderObjectRecord(
                    object_id="hero",
                    blender_name="Hero",
                    object_type="subject_asset",
                )
            ],
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="blend_file",
                artifact_type=ArtifactType.BLENDER_FILE,
                uri=str(blend),
                mime_type="application/x-blender",
            )
        ],
    )


def _mcp_objects_summary(*, object_name: str = "Hero") -> dict:
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


def test_local_e2e_workflow_dry_run_uses_single_project_state(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    scene_glb = tmp_path / "scene.glb"
    asset_glb = tmp_path / "asset.glb"
    blender = tmp_path / "blender"
    output_dir = tmp_path / "workflow"
    _touch(root / "tools/compose_blender_scene.py")
    _touch(scene_glb)
    _touch(asset_glb)
    _touch(blender)

    summary = run_local_e2e_workflow(
        root=root,
        scene_glb=scene_glb,
        asset_glb=asset_glb,
        output_dir=output_dir,
        blender_path=blender,
        dry_run=True,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert summary["single_project_state"] is True
    assert summary["requested_stages"] == ["compose", "export_viewer", "viewer_check"]
    assert summary["executed_stages"] == ["compose"]
    assert summary["skipped_stages"] == {
        "export_viewer": "dry_run",
        "viewer_check": "export_viewer_skipped",
    }
    assert summary["tool_call_count"] == 1
    assert summary["compose"]["tool_call_status"] == "succeeded"
    assert summary["compose"]["output_blend_exists"] is False
    assert Path(summary["compose"]["assembly_plan_json"]).is_file()
    assert summary["compose"]["assembly_plan"]["target_region"] == "front_left"
    assert summary["compose"]["assembly_plan"]["camera_ortho_scale_factor"] == 1.55
    assert summary["context_views"]["compose"]["view"] == "BlenderAssemblyPlannerContext"
    assert summary["context_views"]["compose"]["available"] is False
    assert "state.scene_spec" in summary["context_views"]["compose"]["missing"]
    assert "import_scene_asset" in summary["context_views"]["compose"]["allowed_domain_tools"]
    assert summary["compose"]["context_view_input"] == summary["context_views"]["compose"]
    assert summary["export_viewer"] is None
    assert summary["viewer_check"] is None
    assert summary["delivery_handoff"]["ready"] is False
    assert summary["delivery_handoff"]["issues"] == [
        "missing_viewer_scene",
        "missing_blend_file",
        "missing_preview_render",
        "missing_viewer_state",
    ]
    assert (output_dir / "delivery_handoff.json").exists()
    assert summary["artifact_ids"] == ["workflow_scene_glb", "workflow_subject_glb"]
    assert summary["checkpoint"]["project_id"] == "v1_local_e2e_workflow"
    assert summary["checkpoint"]["thread_id"] == "local_workflow"
    assert summary["checkpoint"]["phase"] == "BLENDER_ASSEMBLY_EXECUTION"
    assert summary["checkpoint"]["reason"] == "workflow_output"
    assert summary["checkpoint"]["node_name"] == "workflow_runner"
    assert summary["checkpoint"]["parent_checkpoint_id"] == summary["stage_checkpoints"][-1]["checkpoint_id"]
    assert summary["checkpoint"]["artifact_ids"] == ["workflow_scene_glb", "workflow_subject_glb"]
    assert summary["checkpoint"]["tool_call_count"] == 1
    assert [record["metadata"]["stage"] for record in summary["stage_checkpoints"]] == ["compose"]
    assert summary["stage_checkpoints"][0]["reason"] == "blender_assembly_execution_completed"
    assert summary["stage_checkpoints"][0]["node_name"] == "workflow_runner.compose"
    assert summary["stage_checkpoints"][0]["parent_checkpoint_id"] is None
    assert summary["stage_checkpoints"][0]["metadata"]["checkpoint_kind"] == "stage"
    assert summary["stage_checkpoints"][0]["metadata"]["workflow"] == "local-e2e"
    assert summary["stage_checkpoints"][0]["metadata"]["ok"] is True
    assert summary["stage_checkpoints"][0]["metadata"]["assembly_plan_id"] == summary["compose"]["assembly_plan"]["plan_id"]
    assert summary["stage_checkpoints"][0]["metadata"]["assembly_plan_json"] == summary["compose"]["assembly_plan_json"]
    assert summary["checkpoint_index_jsonl"] == str((output_dir / "checkpoints/checkpoints.jsonl").resolve())
    assert summary["checkpoint_events_jsonl"] == str((output_dir / "checkpoints/events.jsonl").resolve())
    assert Path(summary["checkpoint"]["state_snapshot_uri"]).is_file()
    checkpoint_state = json.loads(Path(summary["checkpoint"]["state_snapshot_uri"]).read_text(encoding="utf-8"))
    assert checkpoint_state["project_id"] == "v1_local_e2e_workflow"
    assert checkpoint_state["phase"] == "BLENDER_ASSEMBLY_EXECUTION"
    assert checkpoint_state["artifacts"][0]["artifact_id"] == "workflow_scene_glb"

    state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
    assert state["project_id"] == "v1_local_e2e_workflow"
    assert state["phase"] == "BLENDER_ASSEMBLY_EXECUTION"
    assert state["blender_scene"] is None
    assert state["viewer_scene"] is None
    assert [artifact["artifact_id"] for artifact in state["artifacts"]] == [
        "workflow_scene_glb",
        "workflow_subject_glb",
    ]
    assert [asset["asset_id"] for asset in state["subject_assets"]] == ["workflow_subject_glb"]
    assert state["subject_assets"][0]["subject_id"] == "subject_001"
    assert state["scene_asset"]["scene_asset_id"] == "workflow_scene_glb"
    assert state["scene_asset"]["adapted_artifact_ids"] == ["workflow_scene_glb"]
    assert len(state["tool_call_log"]) == 1
    assert state["tool_call_log"][0]["domain_tool_name"] == "import_scene_asset"
    assert state["tool_call_log"][0]["arguments"]["assembly_plan_json"] == summary["compose"]["assembly_plan_json"]

    tool_log = json.loads((output_dir / "tool_call_log.json").read_text(encoding="utf-8"))
    assert len(tool_log["tool_call_log"]) == 1
    assert tool_log["tool_call_log"][0]["result_summary"]["dry_run"] is True
    assert tool_log["tool_call_log"][0]["arguments"]["assembly_plan_json"] == summary["compose"]["assembly_plan_json"]


def test_local_e2e_workflow_uses_scene_spec_for_compose_plan(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    scene_glb = tmp_path / "scene.glb"
    asset_glb = tmp_path / "asset.glb"
    blender = tmp_path / "blender"
    output_dir = tmp_path / "workflow"
    scene_spec_json = tmp_path / "scene_spec.json"
    _touch(root / "tools/compose_blender_scene.py")
    _touch(scene_glb)
    _touch(asset_glb)
    _touch(blender)
    scene_spec = _scene_spec_for_compose()
    scene_spec_json.write_text(json.dumps(scene_spec.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    summary = run_local_e2e_workflow(
        root=root,
        scene_glb=scene_glb,
        asset_glb=asset_glb,
        output_dir=output_dir,
        blender_path=blender,
        dry_run=True,
        scene_spec_json=scene_spec_json,
    )

    assert summary["scene_spec_json"] == str(scene_spec_json.resolve())
    assert summary["scene_spec_id"] == "scene_plush_flowers"
    assert summary["context_views"]["compose"]["available"] is True
    assert summary["context_views"]["compose"]["summary"]["scene_id"] == "scene_plush_flowers"
    assert summary["compose"]["assembly_plan"]["subject_id"] == "subject_plush"
    assert summary["compose"]["assembly_plan"]["target_region"] == "front_right"
    assert summary["compose"]["assembly_plan"]["target_region_normalized"][1] < 0
    assert summary["compose"]["assembly_plan"]["target_height_ratio"] == 0.50
    assert summary["compose"]["assembly_plan"]["camera_target_normalized"][0] > 0
    assert summary["compose"]["assembly_plan"]["camera_target_normalized"][1] < 0
    assert summary["compose"]["assembly_plan"]["camera_ortho_scale_factor"] < 1.55
    state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
    assert state["scene_spec"]["scene_id"] == "scene_plush_flowers"
    assert state["subject_assets"][0]["subject_id"] == "subject_plush"
    assert state["scene_asset"]["scene_asset_id"] == "workflow_scene_glb"


def test_local_e2e_workflow_dry_run_resets_artifact_metadata(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    scene_glb = tmp_path / "scene.glb"
    asset_glb = tmp_path / "asset.glb"
    blender = tmp_path / "blender"
    output_dir = tmp_path / "workflow"
    _touch(root / "tools/compose_blender_scene.py")
    _touch(scene_glb)
    _touch(asset_glb)
    _touch(blender)

    for _ in range(2):
        summary = run_local_e2e_workflow(
            root=root,
            scene_glb=scene_glb,
            asset_glb=asset_glb,
            output_dir=output_dir,
            blender_path=blender,
            dry_run=True,
        )
        assert summary["ok"] is True

    metadata_lines = [
        line
        for line in (output_dir / "artifacts/artifacts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(metadata_lines) == 2
    checkpoint_lines = [
        line
        for line in (output_dir / "checkpoints/checkpoints.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_lines = [
        line
        for line in (output_dir / "checkpoints/events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(checkpoint_lines) == 2
    assert len(event_lines) == 2


def test_local_e2e_workflow_supports_compose_only_stage_selection(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    scene_glb = tmp_path / "scene.glb"
    asset_glb = tmp_path / "asset.glb"
    blender = tmp_path / "blender"
    output_dir = tmp_path / "workflow"
    _touch(root / "tools/compose_blender_scene.py")
    _touch(scene_glb)
    _touch(asset_glb)
    _touch(blender)

    summary = run_local_e2e_workflow(
        root=root,
        scene_glb=scene_glb,
        asset_glb=asset_glb,
        output_dir=output_dir,
        blender_path=blender,
        dry_run=True,
        stages=["compose"],
    )

    assert summary["ok"] is True
    assert summary["requested_stages"] == ["compose"]
    assert summary["executed_stages"] == ["compose"]
    assert summary["skipped_stages"] == {
        "export_viewer": "not_requested",
        "viewer_check": "not_requested",
    }
    assert summary["export_viewer"] is None
    assert summary["viewer_check"] is None


@pytest.mark.parametrize(
    "stages",
    [
        ["viewer_check"],
        ["compose", "viewer_check"],
        ["compose", "bad_stage"],
        "",
    ],
)
def test_local_e2e_workflow_rejects_invalid_stage_selection(tmp_path: Path, stages) -> None:
    root = tmp_path / "repo"
    scene_glb = tmp_path / "scene.glb"
    asset_glb = tmp_path / "asset.glb"
    blender = tmp_path / "blender"
    _touch(root / "tools/compose_blender_scene.py")
    _touch(scene_glb)
    _touch(asset_glb)
    _touch(blender)

    with pytest.raises(ValueError):
        run_local_e2e_workflow(
            root=root,
            scene_glb=scene_glb,
            asset_glb=asset_glb,
            output_dir=tmp_path / "workflow",
            blender_path=blender,
            dry_run=True,
            stages=stages,
        )


def test_subject_asset_workflow_dry_run_submit_records_input_without_service_call(tmp_path: Path) -> None:
    image = tmp_path / "subject.png"
    _touch(image)
    output_dir = tmp_path / "subject_workflow"
    service = FakeHunyuan3DService()

    summary = run_subject_asset_workflow(
        output_dir=output_dir,
        subject_id="subject_001",
        source_image_id="subject_image_001",
        image_path=image,
        asset_id="asset_001",
        service_adapter=service,
        dry_run=True,
        stages=["submit"],
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert summary["requested_stages"] == ["submit"]
    assert summary["executed_stages"] == ["submit"]
    assert summary["skipped_stages"] == {
        "check_status": "not_requested",
        "save_completed": "not_requested",
        "quality_check": "not_requested",
        "repair_decision": "not_requested",
        "repair_execute": "not_requested",
    }
    assert service.submitted_payloads == []
    assert summary["artifact_ids"] == ["subject_image_001"]
    assert summary["subject_asset_count"] == 0
    assert summary["tool_call_count"] == 1
    assert summary["submit"]["outputs"]["submitted"] is False
    assert summary["context_views"]["submit"]["view"] == "SubjectAssetGenerationStateInput"
    assert summary["context_views"]["submit"]["available"] is True
    assert "build_subject_asset" in summary["context_views"]["submit"]["allowed_domain_tools"]
    assert summary["context_views"]["submit"]["summary"]["source_image_artifact_id"] == "subject_image_001"
    assert [record["metadata"]["stage"] for record in summary["stage_checkpoints"]] == ["submit"]
    assert summary["stage_checkpoints"][0]["reason"] == "subject_asset_generation_submitted"
    assert summary["checkpoint"]["parent_checkpoint_id"] == summary["stage_checkpoints"][0]["checkpoint_id"]

    state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "SUBJECT_ASSET_GENERATION"
    assert state["artifacts"][0]["artifact_type"] == "SUBJECT_CONCEPT_IMAGE"
    assert state["tool_call_log"][0]["domain_tool_name"] == "build_subject_asset"
    serialized_state = json.dumps(state, ensure_ascii=False)
    assert "placeholder" not in serialized_state


def test_subject_asset_workflow_submit_check_save_registers_subject_asset(tmp_path: Path) -> None:
    image = tmp_path / "subject.png"
    _touch(image)
    output_dir = tmp_path / "subject_workflow"
    service = FakeHunyuan3DService()

    summary = run_subject_asset_workflow(
        output_dir=output_dir,
        subject_id="subject_001",
        source_image_id="subject_image_001",
        image_path=image,
        asset_id="asset_001",
        service_adapter=service,
        stages=["submit", "check_status", "save_completed"],
    )

    assert summary["ok"] is True
    assert summary["job_id"] == "uid_001"
    assert summary["executed_stages"] == ["submit", "check_status", "save_completed"]
    assert summary["skipped_stages"] == {
        "quality_check": "not_requested",
        "repair_decision": "not_requested",
        "repair_execute": "not_requested",
    }
    assert summary["artifact_ids"] == ["asset_001", "subject_image_001"]
    assert summary["subject_asset_count"] == 1
    assert summary["tool_call_count"] == 3
    assert service.submitted_payloads
    assert service.status_requests == ["uid_001", "uid_001"]
    assert (output_dir / "subject_assets/asset_001.glb").read_bytes() == _minimal_glb()
    assert [record["metadata"]["stage"] for record in summary["stage_checkpoints"]] == [
        "submit",
        "check_status",
        "save_completed",
    ]
    assert [record["reason"] for record in summary["stage_checkpoints"]] == [
        "subject_asset_generation_submitted",
        "subject_asset_status_checked",
        "subject_asset_generation_completed",
    ]
    assert summary["stage_checkpoints"][1]["parent_checkpoint_id"] == summary["stage_checkpoints"][0]["checkpoint_id"]
    assert summary["stage_checkpoints"][2]["parent_checkpoint_id"] == summary["stage_checkpoints"][1]["checkpoint_id"]
    assert summary["checkpoint"]["parent_checkpoint_id"] == summary["stage_checkpoints"][2]["checkpoint_id"]

    state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
    assert state["subject_assets"][0]["asset_id"] == "asset_001"
    assert state["subject_assets"][0]["status"] == "succeeded"
    assert state["subject_assets"][0]["job_id"] == "uid_001"
    assert state["subject_assets"][0]["glb_uri"] == str((output_dir / "subject_assets/asset_001.glb").resolve())
    assert state["artifacts"][1]["artifact_id"] == "asset_001"
    assert state["artifacts"][1]["metadata"]["source_image_id"] == "subject_image_001"
    assert state["tool_call_log"][1]["result_summary"]["status"]["raw"]["data"]["model_base64"] == "<base64:4 chars>"
    assert state["tool_call_log"][2]["arguments"]["status_payload"]["raw"]["data"]["model_base64"] == (
        "<base64:4 chars>"
    )
    serialized_summary = json.dumps(summary, ensure_ascii=False)
    assert "Z2xi" not in serialized_summary


def test_subject_asset_workflow_save_completed_requires_job_id(tmp_path: Path) -> None:
    summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        service_adapter=FakeHunyuan3DService(),
        stages=["save_completed"],
    )

    assert summary["ok"] is False
    assert summary["executed_stages"] == []
    assert summary["skipped_stages"] == {
        "submit": "not_requested",
        "check_status": "not_requested",
        "save_completed": "missing_job_id",
        "quality_check": "not_requested",
        "repair_decision": "not_requested",
        "repair_execute": "not_requested",
    }
    assert summary["tool_call_count"] == 0


def test_subject_asset_workflow_quality_check_updates_subject_asset(tmp_path: Path) -> None:
    image = tmp_path / "subject.png"
    _touch(image)
    output_dir = tmp_path / "subject_workflow"

    summary = run_subject_asset_workflow(
        output_dir=output_dir,
        subject_id="subject_001",
        source_image_id="subject_image_001",
        image_path=image,
        asset_id="asset_001",
        service_adapter=FakeHunyuan3DService(),
        stages=["submit", "check_status", "save_completed", "quality_check"],
    )

    assert summary["ok"] is True
    assert summary["executed_stages"] == ["submit", "check_status", "save_completed", "quality_check"]
    assert summary["quality_check"]["status"] == "pass"
    assert summary["quality_check"]["score"] == 1.0
    assert summary["quality_check"]["issues"] == []
    assert summary["quality_check"]["suggested_action"] == "accept"
    assert summary["tool_call_count"] == 3
    assert [record["metadata"]["stage"] for record in summary["stage_checkpoints"]] == [
        "submit",
        "check_status",
        "save_completed",
        "quality_check",
    ]
    assert summary["stage_checkpoints"][-1]["reason"] == "subject_asset_quality_checked"
    assert summary["stage_checkpoints"][-1]["phase"] == "SUBJECT_ASSET_QA"

    state = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "SUBJECT_ASSET_QA"
    asset = state["subject_assets"][0]
    assert asset["status"] == "succeeded"
    assert asset["quality_score"] == 1.0
    assert asset["quality_notes"] == "subject asset quality checks passed"
    assert asset["generation_params"]["quality"]["status"] == "pass"


def test_subject_asset_workflow_quality_check_existing_glb(tmp_path: Path) -> None:
    glb = tmp_path / "existing.glb"
    glb.write_bytes(_minimal_glb())

    summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        asset_id="asset_existing",
        output_glb=glb,
        service_adapter=FakeHunyuan3DService(),
        stages=["quality_check"],
    )

    assert summary["ok"] is True
    assert summary["requested_stages"] == ["quality_check"]
    assert summary["executed_stages"] == ["quality_check"]
    assert summary["skipped_stages"] == {
        "submit": "not_requested",
        "check_status": "not_requested",
        "save_completed": "not_requested",
        "repair_decision": "not_requested",
        "repair_execute": "not_requested",
    }
    assert summary["subject_asset_count"] == 1
    assert summary["artifact_ids"] == ["asset_existing"]
    assert summary["quality_check"]["status"] == "pass"
    assert summary["context_views"]["quality_check"]["view"] == "SubjectAssetQualityStateInput"
    assert summary["context_views"]["quality_check"]["available"] is True
    assert "check_subject_asset_quality" in summary["context_views"]["quality_check"]["allowed_domain_tools"]
    assert summary["context_views"]["quality_check"]["summary"]["subject_asset_ids"] == ["asset_existing"]

    state = json.loads((tmp_path / "subject_workflow/state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "SUBJECT_ASSET_QA"
    assert state["artifacts"][0]["artifact_type"] == "SUBJECT_3D_ASSET"
    assert state["subject_assets"][0]["service"] == "existing_asset"
    assert state["subject_assets"][0]["generation_params"]["quality_source"] == "existing_output_glb"


def test_subject_asset_workflow_repair_decision_records_retry_plan_for_failed_quality(tmp_path: Path) -> None:
    glb = tmp_path / "bad.glb"
    glb.write_bytes(b"BAD!" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little"))

    summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        asset_id="asset_bad",
        output_glb=glb,
        service_adapter=FakeHunyuan3DService(),
        stages=["quality_check", "repair_decision"],
    )

    assert summary["ok"] is False
    assert summary["executed_stages"] == ["quality_check", "repair_decision"]
    assert summary["quality_check"]["status"] == "fail"
    assert summary["repair_decision"]["action"] == "retry_hunyuan3d"
    assert summary["repair_decision"]["user_visible"] is False
    assert summary["repair_decision"]["next_stage"] == "SUBJECT_ASSET_GENERATION"
    assert [record["reason"] for record in summary["stage_checkpoints"]] == [
        "quality_check_failed",
        "subject_asset_repair_decision_planned",
    ]

    state = json.loads((tmp_path / "subject_workflow/state.json").read_text(encoding="utf-8"))
    asset = state["subject_assets"][0]
    assert asset["status"] == "needs_regen"
    assert asset["generation_params"]["repair_decision"]["action"] == "retry_hunyuan3d"


def test_subject_asset_workflow_repair_decision_accepts_passed_quality(tmp_path: Path) -> None:
    glb = tmp_path / "good.glb"
    glb.write_bytes(_minimal_glb())

    summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        asset_id="asset_good",
        output_glb=glb,
        service_adapter=FakeHunyuan3DService(),
        stages=["quality_check", "repair_decision"],
    )

    assert summary["ok"] is True
    assert summary["repair_decision"]["action"] == "accept"
    assert summary["repair_decision"]["user_visible"] is False
    assert summary["repair_decision"]["next_stage"] == "BLENDER_ASSEMBLY_PLANNING"


def test_subject_asset_workflow_repair_execute_accepts_passed_asset(tmp_path: Path) -> None:
    glb = tmp_path / "good.glb"
    glb.write_bytes(_minimal_glb())

    summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        asset_id="asset_good",
        output_glb=glb,
        service_adapter=FakeHunyuan3DService(),
        stages=["quality_check", "repair_decision", "repair_execute"],
    )

    assert summary["ok"] is True
    assert summary["executed_stages"] == ["quality_check", "repair_decision", "repair_execute"]
    assert summary["repair_execute"]["action"] == "accept"
    assert summary["repair_execute"]["status"] == "accepted"
    assert summary["repair_execute"]["executed"] is False
    assert [record["reason"] for record in summary["stage_checkpoints"]] == [
        "subject_asset_quality_checked",
        "subject_asset_repair_decision_planned",
        "subject_asset_repair_execution_handled",
    ]

    state = json.loads((tmp_path / "subject_workflow/state.json").read_text(encoding="utf-8"))
    asset = state["subject_assets"][0]
    assert asset["status"] == "succeeded"
    assert asset["generation_params"]["repair_execution"]["status"] == "accepted"


def test_subject_asset_workflow_repair_execute_plans_retry_in_dry_run(tmp_path: Path) -> None:
    image = tmp_path / "subject.png"
    _touch(image)
    glb = tmp_path / "bad.glb"
    glb.write_bytes(b"BAD!" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little"))
    service = FakeHunyuan3DService()

    summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        image_path=image,
        asset_id="asset_bad",
        output_glb=glb,
        service_adapter=service,
        dry_run=True,
        stages=["quality_check", "repair_decision", "repair_execute"],
    )

    assert summary["ok"] is False
    assert summary["repair_decision"]["action"] == "retry_hunyuan3d"
    assert summary["repair_execute"]["action"] == "retry_hunyuan3d"
    assert summary["repair_execute"]["status"] == "planned"
    assert summary["repair_execute"]["dry_run"] is True
    assert summary["repair_execute"]["executed"] is False
    assert summary["repair_execute"]["outputs"]["outputs"]["submitted"] is False
    assert service.submitted_payloads == []
    assert summary["tool_call_count"] == 1
    assert summary["context_views"]["repair_execute"]["phase"] == "SUBJECT_ASSET_GENERATION"
    assert "build_subject_asset" in summary["context_views"]["repair_execute"]["allowed_domain_tools"]
    assert [record["reason"] for record in summary["stage_checkpoints"]] == [
        "quality_check_failed",
        "subject_asset_repair_decision_planned",
        "subject_asset_repair_execution_handled",
    ]

    state = json.loads((tmp_path / "subject_workflow/state.json").read_text(encoding="utf-8"))
    asset = state["subject_assets"][0]
    assert state["phase"] == "SUBJECT_ASSET_GENERATION"
    assert asset["status"] == "needs_regen"
    assert asset["generation_params"]["repair_execution"]["status"] == "planned"
    assert state["tool_call_log"][0]["result_summary"]["submitted"] is False


def test_subject_asset_workflow_repair_execute_blocks_unconfirmed_live_retry(tmp_path: Path) -> None:
    image = tmp_path / "subject.png"
    _touch(image)
    glb = tmp_path / "bad.glb"
    glb.write_bytes(b"BAD!" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little"))
    service = FakeHunyuan3DService()

    summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        image_path=image,
        asset_id="asset_bad",
        output_glb=glb,
        service_adapter=service,
        stages=["quality_check", "repair_decision", "repair_execute"],
    )

    assert summary["ok"] is False
    assert summary["repair_execute"]["status"] == "blocked"
    assert summary["repair_execute"]["reason"] == "repair_execution_requires_explicit_confirmation"
    assert summary["repair_execute"]["requires_confirmation"] is True
    assert summary["repair_execute"]["tool_call_id"] is None
    assert service.submitted_payloads == []

    state = json.loads((tmp_path / "subject_workflow/state.json").read_text(encoding="utf-8"))
    asset = state["subject_assets"][0]
    assert asset["generation_params"]["repair_execution"]["status"] == "blocked"
    assert state["tool_call_log"] == []


def test_subject_asset_workflow_repair_execute_creates_user_pending_action(tmp_path: Path) -> None:
    glb = tmp_path / "good.glb"
    glb.write_bytes(_minimal_glb())

    summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        asset_id="asset_good",
        output_glb=glb,
        service_adapter=FakeHunyuan3DService(),
        qa_user_requested_review=True,
        stages=["quality_check", "repair_decision", "repair_execute"],
    )

    assert summary["ok"] is True
    assert summary["repair_decision"]["action"] == "ask_user"
    assert summary["repair_execute"]["status"] == "pending_action"
    assert summary["repair_execute"]["pending_action_id"].startswith("pending_")
    assert summary["repair_execute"]["user_visible"] is True

    state = json.loads((tmp_path / "subject_workflow/state.json").read_text(encoding="utf-8"))
    assert state["pending_action"]["action_type"] == "ask_user_clarification"
    assert state["pending_action"]["payload"]["repair_decision"]["action"] == "ask_user"
    assert state["subject_assets"][0]["status"] == "uncertain"
    frontend_status = json.loads((tmp_path / "subject_workflow/frontend_status.json").read_text(encoding="utf-8"))
    assert summary["frontend_status_json"] == str((tmp_path / "subject_workflow/frontend_status.json").resolve())
    assert frontend_status["status"] == "needs_user_action"
    assert frontend_status["current_stage"] == "repair_execute"
    assert frontend_status["pending_action"]["action_type"] == "ask_user_clarification"
    assert frontend_status["pending_action"]["asset_id"] == "asset_good"


def test_review_patch_workflow_records_user_feedback_from_pending_action(tmp_path: Path) -> None:
    glb = tmp_path / "good.glb"
    glb.write_bytes(_minimal_glb())
    source_summary = run_subject_asset_workflow(
        output_dir=tmp_path / "subject_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        asset_id="asset_good",
        output_glb=glb,
        service_adapter=FakeHunyuan3DService(),
        qa_user_requested_review=True,
        stages=["quality_check", "repair_decision", "repair_execute"],
    )

    summary = run_review_patch_workflow(
        state_json=source_summary["state_json"],
        output_dir=tmp_path / "review_patch_workflow",
        user_feedback="重画主体概念图，让外形更接近参考图。",
        source_turn_id="turn_feedback_001",
        patch_id="patch_feedback_001",
    )

    assert summary["ok"] is True
    assert summary["review_patch"]["patch"]["patch_id"] == "patch_feedback_001"
    assert summary["review_patch"]["patch"]["target_type"] == "subject"
    assert summary["review_patch"]["patch"]["target_id"] == "subject_001"
    assert summary["review_patch"]["patch"]["patch_type"] == "redo_subject"
    assert summary["review_patch"]["cleared_pending_action"] is True
    assert summary["pending_action_cleared"] is True
    assert summary["phase"] == "CONCEPT_REVIEW"
    assert [record["reason"] for record in summary["stage_checkpoints"]] == ["review_patch_created"]

    state = json.loads((tmp_path / "review_patch_workflow/state.json").read_text(encoding="utf-8"))
    assert state["pending_action"] is None
    assert state["phase"] == "CONCEPT_REVIEW"
    assert state["review_patches"][0]["patch_id"] == "patch_feedback_001"
    assert state["review_patches"][0]["structured_delta"]["pending_action_id"].startswith("pending_")
    frontend_status = json.loads((tmp_path / "review_patch_workflow/frontend_status.json").read_text(encoding="utf-8"))
    assert frontend_status["status"] == "completed"
    assert frontend_status["current_stage"] == "review_patch"
    assert frontend_status["review_patch_ids"] == ["patch_feedback_001"]


def test_concept_seed_workflow_registers_initial_subject_concept(tmp_path: Path) -> None:
    image = tmp_path / "subject_concept.png"
    image.write_bytes(b"subject concept image")

    summary = run_concept_seed_workflow(
        image_path=image,
        output_dir=tmp_path / "concept_seed_workflow",
        subject_id="subject_001",
        source_image_id="subject_image_001",
        project_id="project_demo",
        thread_id="thread_demo",
        prompt="single friendly robot on white background",
    )

    assert summary["ok"] is True
    assert summary["phase"] == "SUBJECT_ASSET_GENERATION"
    assert summary["concept_seed"]["artifact_id"] == "subject_image_001"
    assert [record["reason"] for record in summary["stage_checkpoints"]] == ["concept_seed_registered"]

    output_state = json.loads((tmp_path / "concept_seed_workflow/state.json").read_text(encoding="utf-8"))
    assert output_state["project_id"] == "project_demo"
    assert output_state["concept_bundle"]["approved"] is True
    assert output_state["concept_bundle"]["subject_concept_images"] == {
        "subject_001": ["subject_image_001"]
    }
    assert output_state["artifacts"][0]["artifact_type"] == "SUBJECT_CONCEPT_IMAGE"

    frontend_status = json.loads((tmp_path / "concept_seed_workflow/frontend_status.json").read_text(encoding="utf-8"))
    assert frontend_status["status"] == "completed"
    assert frontend_status["current_stage"] == "seed_concept"
    assert frontend_status["artifact_ids"] == ["subject_image_001"]


def test_concept_regeneration_workflow_applies_pending_review_patch(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="preview_old",
            subject_concept_images={"subject_001": ["subject_image_old"]},
            approved=True,
        ),
        review_patches=[
            ReviewPatch(
                patch_id="patch_feedback_001",
                source_turn_id="turn_feedback_001",
                phase_created=WorkflowPhase.CONCEPT_REVIEW,
                target_type="subject",
                target_id="subject_001",
                patch_type="redo_subject",
                instruction="重画主体概念图，让外形更接近参考图。",
                structured_delta={"asset_id": "asset_bad"},
                affected_artifact_ids=["asset_bad", "subject_image_old"],
            )
        ],
    )
    state_path.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    generated_image = tmp_path / "generated_subject.png"
    generated_image.write_bytes(b"generated subject concept")

    summary = run_concept_regeneration_workflow(
        state_json=state_path,
        output_dir=tmp_path / "concept_regeneration_workflow",
        patch_id="patch_feedback_001",
        generated_image_path=generated_image,
        generated_image_artifact_id="subject_image_new",
        dry_run=False,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is False
    assert summary["phase"] == "SUBJECT_ASSET_GENERATION"
    assert summary["concept_regeneration"]["status"] == "applied"
    assert summary["concept_regeneration"]["generated_image_artifact_id"] == "subject_image_new"
    assert [record["reason"] for record in summary["stage_checkpoints"]] == [
        "review_patch_concept_regeneration_handled"
    ]

    output_state = json.loads((tmp_path / "concept_regeneration_workflow/state.json").read_text(encoding="utf-8"))
    assert output_state["review_patches"][0]["status"] == "applied"
    assert output_state["concept_bundle"]["concept_version"] == 2
    assert output_state["concept_bundle"]["final_preview_image_id"] is None
    assert output_state["concept_bundle"]["approved"] is False
    assert output_state["concept_bundle"]["subject_concept_images"]["subject_001"] == [
        "subject_image_old",
        "subject_image_new",
    ]
    assert output_state["artifacts"][0]["artifact_id"] == "subject_image_new"

    frontend_status = json.loads(
        (tmp_path / "concept_regeneration_workflow/frontend_status.json").read_text(encoding="utf-8")
    )
    assert frontend_status["status"] == "completed"
    assert frontend_status["current_stage"] == "apply_review_patch"
    assert frontend_status["review_patch_ids"] == ["patch_feedback_001"]


@pytest.mark.parametrize(
    "stages",
    [
        ["save_completed", "check_status"],
        ["submit", "submit"],
        ["bad_stage"],
        "",
    ],
)
def test_subject_asset_workflow_rejects_invalid_stage_selection(tmp_path: Path, stages) -> None:
    with pytest.raises(ValueError):
        run_subject_asset_workflow(
            output_dir=tmp_path / "subject_workflow",
            subject_id="subject_001",
            source_image_id="subject_image_001",
            service_adapter=FakeHunyuan3DService(),
            stages=stages,
        )


def test_scene_asset_workflow_runtime_status_dry_run_records_context(tmp_path: Path) -> None:
    service = FakeWorldMirrorService()

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        service_adapter=service,
        dry_run=True,
        stages=["runtime_status"],
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert summary["executed_stages"] == ["runtime_status"]
    assert summary["skipped_stages"] == {
        "prepare_generation": "not_requested",
        "upload_inputs": "not_requested",
        "poll_upload": "not_requested",
        "submit_generation": "not_requested",
        "poll_generation": "not_requested",
        "inspect_output": "not_requested",
        "save_generation": "not_requested",
        "register_existing_output": "not_requested",
    }
    assert service.status_calls == 0
    assert summary["runtime_status"]["outputs"]["checked"] is False
    assert summary["has_scene_asset"] is False
    assert summary["context_views"]["runtime_status"]["view"] == "SceneAssetRuntimeStatusStateInput"
    assert "build_scene_asset" in summary["context_views"]["runtime_status"]["allowed_domain_tools"]
    assert (tmp_path / "scene_workflow/state.json").exists()


def test_scene_asset_workflow_prepare_generation_records_call_plan_and_checkpoint(tmp_path: Path) -> None:
    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_workspace_dir="gradio_demo_output/input_images_existing",
        service_adapter=FakeWorldMirrorService(),
        stages=["prepare_generation"],
        show_camera=False,
    )

    assert summary["ok"] is True
    assert summary["executed_stages"] == ["prepare_generation"]
    assert summary["skipped_stages"] == {
        "runtime_status": "not_requested",
        "upload_inputs": "not_requested",
        "poll_upload": "not_requested",
        "submit_generation": "not_requested",
        "poll_generation": "not_requested",
        "inspect_output": "not_requested",
        "save_generation": "not_requested",
        "register_existing_output": "not_requested",
    }
    assert summary["prepare_generation"]["outputs"]["prepared"] is True
    assert summary["prepare_generation"]["outputs"]["submits_long_running_job"] is False
    assert summary["worldmirror_workspace_dir"] == "gradio_demo_output/input_images_existing"
    assert (
        summary["prepare_generation"]["outputs"]["call_plan"]["reconstruct_payload"]["data"][0]
        == "gradio_demo_output/input_images_existing"
    )
    assert summary["context_views"]["prepare_generation"]["view"] == "SceneAssetGenerationCallPlanStateInput"
    assert summary["stage_checkpoints"][0]["reason"] == "scene_generation_call_prepared"


def test_scene_asset_workflow_upload_inputs_requires_confirmation(tmp_path: Path) -> None:
    service = FakeWorldMirrorService()
    image = tmp_path / "view.png"
    image.write_bytes(b"png")

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_input_files=[image],
        service_adapter=service,
        stages=["upload_inputs"],
    )

    assert summary["ok"] is False
    assert summary["executed_stages"] == ["upload_inputs"]
    assert summary["upload_inputs"]["outputs"]["submitted"] is False
    assert summary["upload_inputs"]["outputs"]["issues"] == ["worldmirror_upload_requires_explicit_confirmation"]
    assert service.uploaded_requests == []
    assert summary["stage_checkpoints"][0]["reason"] == "upload_inputs_failed"


def test_scene_asset_workflow_upload_inputs_records_event_id_when_confirmed(tmp_path: Path) -> None:
    service = FakeWorldMirrorService()
    image = tmp_path / "view.png"
    image.write_bytes(b"png")

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_input_files=[image],
        service_adapter=service,
        stages=["upload_inputs"],
        confirm_worldmirror_upload=True,
    )

    assert summary["ok"] is True
    assert summary["upload_inputs"]["outputs"]["submitted"] is True
    assert summary["upload_inputs"]["outputs"]["submits_long_running_job"] is False
    assert summary["upload_inputs"]["outputs"]["submission"]["upload_submission"]["event_id"] == "upload_evt_fake_001"
    assert len(service.uploaded_requests) == 1
    assert summary["context_views"]["upload_inputs"]["view"] == "SceneAssetUploadInputsStateInput"
    assert summary["stage_checkpoints"][0]["reason"] == "scene_generation_inputs_upload_stage_completed"


def test_scene_asset_workflow_poll_upload_feeds_submit_generation_workspace(tmp_path: Path) -> None:
    service = FakeWorldMirrorService()

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_upload_event_id="upload_evt_fake_001",
        service_adapter=service,
        stages=["poll_upload", "submit_generation"],
        confirm_worldmirror_upload_poll=True,
        confirm_worldmirror_submit=True,
    )

    assert summary["ok"] is True
    assert summary["executed_stages"] == ["poll_upload", "submit_generation"]
    assert summary["poll_upload"]["outputs"]["target_dir"] == "gradio_demo_output/input_images_uploaded"
    assert summary["worldmirror_effective_workspace_dir"] == "gradio_demo_output/input_images_uploaded"
    assert summary["submit_generation"]["outputs"]["submitted"] is True
    assert service.upload_polled_requests == [("upload_evt_fake_001", "/gradio_api")]
    assert service.submitted_requests[0].workspace_dir == "gradio_demo_output/input_images_uploaded"
    assert [record["reason"] for record in summary["stage_checkpoints"]] == [
        "scene_generation_upload_poll_stage_completed",
        "scene_generation_submit_stage_completed",
    ]


def test_scene_asset_workflow_submit_generation_requires_confirmation(tmp_path: Path) -> None:
    service = FakeWorldMirrorService()

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_workspace_dir="gradio_demo_output/input_images_existing",
        service_adapter=service,
        stages=["submit_generation"],
    )

    assert summary["ok"] is False
    assert summary["executed_stages"] == ["submit_generation"]
    assert summary["submit_generation"]["outputs"]["submitted"] is False
    assert summary["submit_generation"]["outputs"]["issues"] == ["worldmirror_submit_requires_explicit_confirmation"]
    assert service.submitted_requests == []
    assert summary["stage_checkpoints"][0]["reason"] == "submit_generation_failed"


def test_scene_asset_workflow_submit_generation_records_event_id_when_confirmed(tmp_path: Path) -> None:
    service = FakeWorldMirrorService()

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_workspace_dir="gradio_demo_output/input_images_existing",
        service_adapter=service,
        stages=["submit_generation"],
        confirm_worldmirror_submit=True,
    )

    assert summary["ok"] is True
    assert summary["submit_generation"]["outputs"]["submitted"] is True
    assert summary["submit_generation"]["outputs"]["submits_long_running_job"] is True
    assert summary["submit_generation"]["outputs"]["submission"]["reconstruct_submission"]["event_id"] == "evt_fake_001"
    assert len(service.submitted_requests) == 1
    assert service.submitted_requests[0].workspace_dir == "gradio_demo_output/input_images_existing"
    assert summary["worldmirror_workspace_dir"] == "gradio_demo_output/input_images_existing"
    assert summary["context_views"]["submit_generation"]["view"] == "SceneAssetGenerationSubmitStateInput"
    assert summary["stage_checkpoints"][0]["reason"] == "scene_generation_submit_stage_completed"


def test_scene_asset_workflow_poll_generation_records_complete_result_when_confirmed(tmp_path: Path) -> None:
    service = FakeWorldMirrorService()

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_event_id="evt_fake_001",
        service_adapter=service,
        stages=["poll_generation"],
        confirm_worldmirror_poll=True,
    )

    assert summary["ok"] is True
    assert summary["poll_generation"]["outputs"]["polled"] is True
    assert summary["poll_generation"]["outputs"]["poll_result"]["complete"] is True
    assert service.polled_requests == [("gradio_demo", "evt_fake_001", "/gradio_api")]
    assert summary["context_views"]["poll_generation"]["view"] == "SceneAssetGenerationPollStateInput"
    assert summary["stage_checkpoints"][0]["reason"] == "scene_generation_poll_stage_completed"


def test_scene_asset_workflow_save_generation_registers_output(tmp_path: Path) -> None:
    world_output = _worldmirror_output(tmp_path)

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_output_dir=world_output,
        service_adapter=FakeWorldMirrorService(),
        stages=["save_generation"],
    )

    assert summary["ok"] is True
    assert summary["executed_stages"] == ["save_generation"]
    assert summary["save_generation"]["outputs"]["registered"] is True
    assert summary["has_scene_asset"] is True
    assert summary["context_views"]["save_generation"]["view"] == "SceneAssetGenerationSaveStateInput"
    assert summary["stage_checkpoints"][0]["reason"] == "scene_generation_saved"


def test_scene_asset_workflow_register_existing_worldmirror_output(tmp_path: Path) -> None:
    world_output = _worldmirror_output(tmp_path)

    summary = run_scene_asset_workflow(
        output_dir=tmp_path / "scene_workflow",
        scene_asset_id="scene_asset_001",
        worldmirror_output_dir=world_output,
        source_scene_concept_image_ids=["scene_concept_001"],
        service_adapter=FakeWorldMirrorService(),
        stages=["inspect_output", "register_existing_output"],
    )

    assert summary["ok"] is True
    assert summary["executed_stages"] == ["inspect_output", "register_existing_output"]
    assert summary["skipped_stages"] == {
        "runtime_status": "not_requested",
        "prepare_generation": "not_requested",
        "upload_inputs": "not_requested",
        "poll_upload": "not_requested",
        "submit_generation": "not_requested",
        "poll_generation": "not_requested",
        "save_generation": "not_requested",
    }
    assert summary["has_scene_asset"] is True
    assert summary["scene_asset"]["status"] == "adapted"
    assert summary["scene_asset"]["adapted_artifact_ids"] == ["scene_asset_001_scene_glb"]
    assert summary["artifact_ids"] == [
        "scene_asset_001_camera_params_json",
        "scene_asset_001_gaussian_ply",
        "scene_asset_001_scene_glb",
    ]
    assert summary["register_existing_output"]["outputs"]["registered"] is True
    assert [record["metadata"]["stage"] for record in summary["stage_checkpoints"]] == [
        "inspect_output",
        "register_existing_output",
    ]
    assert [record["reason"] for record in summary["stage_checkpoints"]] == [
        "scene_asset_output_inspected",
        "scene_asset_adapted",
    ]
    assert summary["checkpoint"]["parent_checkpoint_id"] == summary["stage_checkpoints"][-1]["checkpoint_id"]

    state = json.loads((tmp_path / "scene_workflow/state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "SCENE_ASSET_GENERATION"
    assert state["scene_asset"]["scene_asset_id"] == "scene_asset_001"
    assert state["scene_asset"]["source_scene_concept_image_ids"] == ["scene_concept_001"]
    assert len(state["artifacts"]) == 3


@pytest.mark.parametrize(
    "stages",
    [
        ["register_existing_output", "inspect_output"],
        ["runtime_status", "runtime_status"],
        ["bad_stage"],
        "",
    ],
)
def test_scene_asset_workflow_rejects_invalid_stage_selection(tmp_path: Path, stages) -> None:
    with pytest.raises(ValueError):
        run_scene_asset_workflow(
            output_dir=tmp_path / "scene_workflow",
            scene_asset_id="scene_asset_001",
            service_adapter=FakeWorldMirrorService(),
            stages=stages,
        )


def test_codex_self_mcp_workflow_status_and_plan_handoff(tmp_path: Path) -> None:
    adapter = FakeCodexSelfMCPAdapter()

    summary = run_codex_self_mcp_workflow(
        output_dir=tmp_path / "codex_self",
        cwd=tmp_path,
        prompt="check the current V1 handoff state",
        sandbox="read-only",
        service_adapter=adapter,
        stages=["status", "plan_handoff"],
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert summary["executed_stages"] == ["status", "plan_handoff"]
    assert summary["skipped_stages"] == {"execute_handoff": "not_requested"}
    assert summary["status"]["outputs"]["ok"] is True
    assert summary["plan_handoff"]["outputs"]["planned"] is True
    assert summary["plan_handoff"]["outputs"]["call_plan"]["sandbox"] == "read-only"
    assert summary["context_views"]["plan_handoff"]["view"] == "CodexSelfMCPHandoffPlanStateInput"
    assert [record["reason"] for record in summary["stage_checkpoints"]] == [
        "codex_self_mcp_status_checked",
        "codex_self_mcp_handoff_planned",
    ]
    assert adapter.status_calls == 1
    assert len(adapter.plan_calls) == 1
    assert adapter.run_calls == []
    assert (tmp_path / "codex_self/summary.json").exists()
    assert (tmp_path / "codex_self/state.json").exists()


def test_codex_self_mcp_workflow_execute_dry_run_does_not_run(tmp_path: Path) -> None:
    adapter = FakeCodexSelfMCPAdapter()

    summary = run_codex_self_mcp_workflow(
        output_dir=tmp_path / "codex_self",
        cwd=tmp_path,
        prompt="do not run",
        service_adapter=adapter,
        stages=["execute_handoff"],
        dry_run=True,
    )

    assert summary["ok"] is True
    assert summary["executed_stages"] == ["execute_handoff"]
    assert summary["execute_handoff"]["outputs"]["executed"] is False
    assert summary["execute_handoff"]["outputs"]["requires_confirmation"] is True
    assert adapter.run_calls == []
    assert summary["stage_checkpoints"][0]["reason"] == "codex_self_mcp_execute_stage_completed"


def test_codex_self_mcp_workflow_execute_requires_confirmation(tmp_path: Path) -> None:
    adapter = FakeCodexSelfMCPAdapter()

    summary = run_codex_self_mcp_workflow(
        output_dir=tmp_path / "codex_self",
        cwd=tmp_path,
        prompt="requires confirmation",
        service_adapter=adapter,
        stages=["execute_handoff"],
        dry_run=False,
    )

    assert summary["ok"] is False
    assert summary["execute_handoff"]["outputs"]["executed"] is False
    assert summary["execute_handoff"]["outputs"]["issues"] == [
        "codex_self_mcp_execute_requires_explicit_confirmation"
    ]
    assert adapter.run_calls == []
    assert summary["stage_checkpoints"][0]["reason"] == "execute_handoff_failed"


def test_codex_self_mcp_workflow_execute_runs_when_confirmed(tmp_path: Path) -> None:
    adapter = FakeCodexSelfMCPAdapter()

    summary = run_codex_self_mcp_workflow(
        output_dir=tmp_path / "codex_self",
        cwd=tmp_path,
        prompt="confirmed handoff",
        service_adapter=adapter,
        stages=["execute_handoff"],
        dry_run=False,
        confirm_execute=True,
    )

    assert summary["ok"] is True
    assert summary["execute_handoff"]["outputs"]["executed"] is True
    assert summary["execute_handoff"]["outputs"]["result"]["stdout_tail"] == "handoff done"
    assert len(adapter.run_calls) == 1
    assert summary["stage_checkpoints"][0]["reason"] == "codex_self_mcp_execute_stage_completed"


def test_blender_edit_workflow_dry_run_records_plan_and_checkpoint(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = _blender_edit_state(tmp_path)
    state_path.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    summary = run_blender_edit_workflow(
        state_json=state_path,
        output_dir=tmp_path / "blender_edit_workflow",
        domain_tool_name="move_subject",
        arguments={"blender_object_id": "hero", "location": [1, 2, 3]},
        dry_run=True,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert summary["phase"] == "BLENDER_EDIT"
    assert summary["executed_stages"] == ["blender_edit"]
    assert summary["skipped_stages"] == {"export_viewer": "not_requested", "viewer_check": "not_requested"}
    assert summary["blender_edit"]["outputs"]["raw_tool_name"] == "execute_blender_code"
    assert summary["blender_edit"]["outputs"]["arguments_summary"] == {
        "blender_name": "Hero",
        "location": [1.0, 2.0, 3.0],
    }
    assert [record["metadata"]["stage"] for record in summary["stage_checkpoints"]] == ["blender_edit"]
    assert summary["stage_checkpoints"][0]["reason"] == "blender_edit_applied"
    assert summary["checkpoint"]["parent_checkpoint_id"] == summary["stage_checkpoints"][0]["checkpoint_id"]

    output_state = json.loads((tmp_path / "blender_edit_workflow/state.json").read_text(encoding="utf-8"))
    assert output_state["phase"] == "BLENDER_EDIT"
    assert output_state["tool_call_log"][0]["domain_tool_name"] == "move_subject"
    assert output_state["tool_call_log"][0]["result_summary"]["dry_run"] is True


def test_blender_edit_workflow_executes_injected_raw_caller_and_syncs_scene(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = _blender_edit_state(tmp_path)
    state_path.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        if tool_name == "execute_blender_code":
            return {"status": "ok", "result": {"ok": True, "object": "Hero"}}
        if tool_name == "get_objects_summary":
            return _mcp_objects_summary(object_name="Hero")
        raise AssertionError(tool_name)

    summary = run_blender_edit_workflow(
        state_json=state_path,
        output_dir=tmp_path / "blender_edit_workflow",
        domain_tool_name="move_subject",
        arguments={"blender_object_id": "hero", "location": [1, 2, 3]},
        raw_tool_caller=raw_tool_caller,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is False
    assert [call[0] for call in raw_calls] == [
        "execute_blender_code",
        "get_objects_summary",
        "execute_blender_code",
    ]
    assert "save_as_mainfile" in raw_calls[2][1]["code"]
    assert summary["blender_edit"]["outputs"]["blender_scene_object_count"] == 1
    assert summary["blender_edit"]["outputs"]["saved_blend_path"].endswith("scene.blend")

    output_state = json.loads((tmp_path / "blender_edit_workflow/state.json").read_text(encoding="utf-8"))
    assert output_state["blender_scene"]["objects"][0]["blender_name"] == "Hero"
    assert output_state["last_error"] is None


def test_blender_edit_workflow_executes_socket_raw_caller_source(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "state.json"
    state = _blender_edit_state(tmp_path)
    state_path.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    raw_calls = []

    class FakeSocketRawCaller:
        def __init__(self, *, root):
            self.root = root

        def __call__(self, tool_name, arguments):
            raw_calls.append((tool_name, arguments))
            if tool_name == "get_objects_summary":
                return _mcp_objects_summary(object_name="Hero")
            if tool_name == "execute_blender_code":
                return {"status": "ok", "result": {"ok": True, "saved_to": "scene.blend"}}
            raise AssertionError(tool_name)

    monkeypatch.setattr("agent_runtime.workflow_runner.BlenderLabSocketRawToolCaller", FakeSocketRawCaller)

    summary = run_blender_edit_workflow(
        state_json=state_path,
        output_dir=tmp_path / "blender_edit_workflow",
        domain_tool_name="get_blender_scene_summary",
        raw_caller_source="blender-lab-socket",
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is False
    assert summary["raw_caller_source"] == "blender-lab-socket"
    assert [call[0] for call in raw_calls] == ["get_objects_summary", "execute_blender_code"]
    assert "save_as_mainfile" in raw_calls[1][1]["code"]
    assert summary["blender_edit"]["outputs"]["blender_scene_object_count"] == 1
    assert summary["blender_edit"]["outputs"]["saved_blend_path"].endswith("scene.blend")

    output_state = json.loads((tmp_path / "blender_edit_workflow/state.json").read_text(encoding="utf-8"))
    assert output_state["tool_call_log"][0]["raw_tool_calls"][0]["server"] == "blender_lab"
    assert output_state["blender_scene"]["objects"][0]["blender_name"] == "Hero"


def test_blender_edit_workflow_records_rejected_operation(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = _blender_edit_state(tmp_path)
    state_path.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    summary = run_blender_edit_workflow(
        state_json=state_path,
        output_dir=tmp_path / "blender_edit_workflow",
        domain_tool_name="delete_subject",
        arguments={"blender_object_id": "hero"},
        dry_run=True,
    )

    assert summary["ok"] is False
    assert summary["stage_checkpoints"][0]["reason"] == "blender_edit_failed"
    assert summary["blender_edit"]["outputs"]["requires_confirmation"] is True

    output_state = json.loads((tmp_path / "blender_edit_workflow/state.json").read_text(encoding="utf-8"))
    assert output_state["last_error"]["code"] == "BLENDER_MCP_PLAN_REJECTED"
    assert output_state["tool_call_log"][0]["status"] == "failed"


def test_blender_edit_workflow_requires_raw_caller_for_non_dry_run(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = _blender_edit_state(tmp_path)
    state_path.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="raw_tool_caller or raw_caller_source is required"):
        run_blender_edit_workflow(
            state_json=state_path,
            output_dir=tmp_path / "blender_edit_workflow",
            domain_tool_name="move_subject",
            arguments={"blender_object_id": "hero", "location": [1, 2, 3]},
        )


def test_delivery_package_workflow_builds_package_from_saved_state(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = _delivery_state(tmp_path)
    state_path.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    summary = run_delivery_package_workflow(
        state_json=state_path,
        output_dir=tmp_path / "delivery_workflow",
        package_id="delivery_project_001",
    )

    assert summary["ok"] is True
    assert summary["phase"] == "DELIVERY"
    assert summary["package"]["ok"] is True
    assert summary["package"]["package_artifact_id"] == "delivery_project_001"
    assert Path(summary["package"]["package_zip"]).is_file()
    assert "delivery_project_001" in summary["artifact_ids"]
    assert [record["metadata"]["stage"] for record in summary["stage_checkpoints"]] == ["delivery_package"]
    assert summary["stage_checkpoints"][0]["reason"] == "delivery_package_created"
    assert summary["checkpoint"]["parent_checkpoint_id"] == summary["stage_checkpoints"][0]["checkpoint_id"]

    output_state = json.loads((tmp_path / "delivery_workflow/state.json").read_text(encoding="utf-8"))
    assert output_state["phase"] == "DELIVERY"
    assert output_state["artifacts"][-1]["artifact_type"] == "EXPORT_PACKAGE"
