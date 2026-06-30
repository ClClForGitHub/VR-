import json
from pathlib import Path

from agent_runtime.domain_dispatcher import DomainToolDispatchResult
from agent_runtime.runtime_audit import audit_runtime_run
from agent_runtime.runtime_console import append_console_message, create_runtime_console_run
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.runtime_loop import read_runtime_loop_summary, run_bounded_runtime_loop
from agent_runtime.runtime_runs import build_runtime_run_bundle
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    BlenderObjectRecord,
    BlenderSceneState,
    ReviewPatch,
    SceneSpec,
    ToolCallRecord,
    ToolCallStatus,
    UserTurn,
    ViewerSceneState,
    WorkflowPhase,
)


def test_runtime_loop_applies_supported_candidates_and_stops_at_delegated_domain_job(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(
        created.run_dir,
        role="user",
        text="Create a compact friendly robot in a clean studio display scene.",
    )

    result = run_bounded_runtime_loop(
        created.run_dir,
        max_steps=8,
        dry_run=True,
        response_text_by_node=_fixture_responses(),
    )

    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    scene_spec_output = _latest_output_for_node(Path(created.run_dir), "SceneSpecCompiler")
    loop_summary = read_runtime_loop_summary(created.run_dir)
    bundle = build_runtime_run_bundle(created.run_dir)
    audit = audit_runtime_run(created.run_dir)

    assert result.ok is True
    assert result.stop_reason == "delegated"
    assert [row.execution_status for row in result.iterations] == [
        "completed",
        "completed",
        "completed",
        "completed",
        "delegated",
    ]
    assert state["phase"] == "CONCEPT_GENERATION"
    assert state["scene_spec"]["scene_id"] == "scene_001"
    assert state["concept_bundle"]["prompt_pack"]["final_preview_prompt"].startswith("A compact friendly robot")
    assert scene_spec_output["context_json"]["interpretation"]["user_goal"] == "Create a compact friendly robot display."
    assert scene_spec_output["llm_result"]["parsed_output"]["subjects"][0]["subject_id"] == "subject_robot"
    assert loop_summary is not None
    assert loop_summary["stop_reason"] == "delegated"
    assert bundle.runtime_loop_summary is not None
    assert bundle.runtime_loop_summary["latest_record"]["domain_tool_name"] == "generate_concept_images"
    assert bundle.file_manifest is not None
    assert {"runtime_loop", "runtime_loop_summary"} <= {item.label for item in bundle.file_manifest.files if item.exists}
    assert audit.ok is True


def test_runtime_loop_stops_on_dry_run_without_fixture(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="Make a robot display scene.")

    result = run_bounded_runtime_loop(created.run_dir, max_steps=3, dry_run=True)

    assert result.ok is True
    assert result.stop_reason == "dry_run_needs_live_or_fixture"
    assert len(result.iterations) == 1
    assert result.iterations[0].node_name == "ReferenceBindingValidator"
    assert result.iterations[0].execution_status == "dry_run"


def test_runtime_loop_executes_delivery_job_and_stops_when_complete(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_delivery_loop"
    run_dir.mkdir(parents=True)
    state = _delivery_state(tmp_path)
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps({"ok": True, "workflow": "runtime-console", "requested_stages": [], "executed_stages": []}),
        encoding="utf-8",
    )

    result = run_bounded_runtime_loop(run_dir, max_steps=3, dry_run=False)
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    bundle = build_runtime_run_bundle(run_dir)

    assert result.ok is True
    assert result.stop_reason == "completed_no_jobs"
    assert [row.execution_status for row in result.iterations] == ["completed", None]
    assert result.iterations[0].job_kind == "delivery"
    assert result.iterations[0].apply_status == "no_unapplied_runtime_candidate"
    assert state_payload["artifacts"][-1]["artifact_type"] == "EXPORT_PACKAGE"
    assert bundle.file_manifest is not None
    ready_labels = {item.label for item in bundle.file_manifest.files if item.exists}
    assert "delivery_package" in ready_labels


def test_runtime_loop_live_blender_edit_refreshes_viewer_and_stops_at_preview_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = _blender_edit_refresh_run_dir(tmp_path)
    script_calls = _patch_fake_script_dispatcher(monkeypatch)
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        if tool_name == "execute_blender_code":
            return {"status": "ok", "result": {"ok": True, "object": "Hero", "location": [1, 2, 3]}}
        if tool_name == "get_objects_summary":
            return _objects_summary(object_name="Hero")
        raise AssertionError(tool_name)

    initial_plan = build_and_save_runtime_dispatch_plan(run_dir)
    assert [job.domain_tool_name for job in initial_plan.runtime_plan.jobs] == [
        "move_subject",
        "export_viewer_scene",
        "render_preview",
    ]

    result = run_bounded_runtime_loop(
        run_dir,
        max_steps=5,
        dry_run=False,
        blender_raw_tool_caller=raw_tool_caller,
    )

    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))
    runtime_plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    delivery_handoff = json.loads((run_dir / "delivery_handoff.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.stop_reason == "waiting_user"
    assert [row.execution_status for row in result.iterations] == [
        "completed",
        "completed",
        "completed",
        "waiting_user",
    ]
    assert [row.domain_tool_name for row in result.iterations[:3]] == [
        "move_subject",
        "export_viewer_scene",
        "render_preview",
    ]
    assert [call[0] for call in raw_calls] == [
        "execute_blender_code",
        "get_objects_summary",
        "execute_blender_code",
    ]
    assert "save_as_mainfile" in raw_calls[2][1]["code"]
    assert [call[0] for call in script_calls] == ["export_viewer_scene", "render_preview"]
    assert state_payload["phase"] == "BLENDER_PREVIEW"
    assert state_payload["viewer_scene"]["viewer_scene_artifact_id"].startswith("runtime_")
    assert state_payload["viewer_scene"]["viewer_scene_path"].endswith("viewer_export/viewer_scene.glb")
    assert state_payload["blender_scene"]["preview_image_id"].startswith("runtime_")
    assert summary["latest_blender_edit_execution"]["domain_tool_name"] == "move_subject"
    assert summary["latest_runtime_script_execution"]["domain_tool_name"] == "render_preview"
    assert frontend_status["phase"] == "BLENDER_PREVIEW"
    assert delivery_handoff["ready"] is False
    assert delivery_handoff["issues"] == ["missing_subject_assets", "missing_scene_assets"]
    assert runtime_plan["runtime_plan"]["requires_user"] is True
    assert runtime_plan["runtime_plan"]["jobs"][0]["kind"] == "user_gate"
    assert result.summary.latest_record is not None
    assert result.summary.latest_record.stop_reason == "waiting_user"


def test_runtime_loop_routes_blender_feedback_into_edit_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = _blender_edit_router_run_dir(tmp_path)
    script_calls = _patch_fake_script_dispatcher(monkeypatch)
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        if tool_name == "execute_blender_code":
            return {"status": "ok", "result": {"ok": True, "object": "Hero", "location": [1, 2, 3]}}
        if tool_name == "get_objects_summary":
            return _objects_summary(object_name="Hero")
        raise AssertionError(tool_name)

    initial_plan = build_and_save_runtime_dispatch_plan(run_dir)
    assert [job.node_name or job.domain_tool_name for job in initial_plan.runtime_plan.jobs] == [
        "BlenderEditRouter",
        "export_viewer_scene",
        "render_preview",
    ]

    result = run_bounded_runtime_loop(
        run_dir,
        max_steps=6,
        dry_run=False,
        response_text_by_node={"BlenderEditRouter": _blender_edit_router_response()},
        blender_raw_tool_caller=raw_tool_caller,
        provider_configs=[],
        env={},
    )

    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    router_output = _latest_output_for_node(run_dir, "BlenderEditRouter")
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))
    runtime_plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.stop_reason == "waiting_user"
    assert [row.node_name or row.domain_tool_name or row.job_kind for row in result.iterations] == [
        "BlenderEditRouter",
        "move_subject",
        "export_viewer_scene",
        "render_preview",
        "user_gate",
    ]
    assert [row.execution_status for row in result.iterations] == [
        "completed",
        "completed",
        "completed",
        "completed",
        "waiting_user",
    ]
    assert router_output["context_json"]["user_edit_text"] == "把机器人挪到画面中心，镜头保持不变。"
    assert router_output["llm_result"]["parsed_output"]["domain_tool_calls"][0]["domain_tool_name"] == "move_subject"
    edit_plan = state_payload["review_patches"][0]["structured_delta"]["blender_edit_plan"]
    assert edit_plan["route"] == "pure_blender_edit"
    assert edit_plan["domain_tool_calls"][0]["arguments"] == {"blender_object_id": "hero", "location": [1, 2, 3]}
    assert [call[0] for call in raw_calls] == [
        "execute_blender_code",
        "get_objects_summary",
        "execute_blender_code",
    ]
    assert [call[0] for call in script_calls] == ["export_viewer_scene", "render_preview"]
    assert state_payload["phase"] == "BLENDER_PREVIEW"
    assert frontend_status["phase"] == "BLENDER_PREVIEW"
    assert runtime_plan["runtime_plan"]["requires_user"] is True
    assert runtime_plan["runtime_plan"]["jobs"][0]["kind"] == "user_gate"


def _fixture_responses() -> dict[str, str]:
    return {
        "ReferenceBindingValidator": json.dumps(
            {
                "valid_bindings": [],
                "requires_clarification": False,
                "open_questions": [],
                "issues": [],
            }
        ),
        "SceneInterpreter": json.dumps(
            {
                "user_goal": "Create a compact friendly robot display.",
                "subject_summaries": ["A compact friendly robot with rounded panels."],
                "environment_summary": "A clean small studio display area.",
                "style_summary": "bright, polished, toy-like, readable silhouette",
                "open_questions": [],
            }
        ),
        "SceneSpecCompiler": json.dumps(
            {
                "scene_id": "scene_001",
                "title": "Compact Robot Display",
                "user_goal": "Create a compact friendly robot in a clean studio display scene.",
                "style": {
                    "style_keywords": ["clean", "friendly", "polished"],
                    "rendering_style": "stylized",
                },
                "environment": {
                    "environment_type": "studio",
                    "description": "A small clean studio display area with a simple pedestal.",
                },
                "lighting": {"description": "Soft studio lighting with a gentle key light."},
                "camera": {
                    "shot_type": "three quarter",
                    "framing": "full subject centered with some floor visible",
                    "target_subject_ids": ["subject_robot"],
                },
                "subjects": [
                    {
                        "subject_id": "subject_robot",
                        "display_name": "Friendly Robot",
                        "category": "character",
                        "role_in_scene": "hero subject",
                        "description": "A compact friendly robot with rounded white panels and blue accent lights.",
                        "appearance": "rounded body, small antenna, expressive screen face, clean toy-like finish",
                        "pose_or_state": "standing upright on a small pedestal",
                        "reference_image_ids": [],
                        "priority": "hero",
                        "needs_2d_concept": True,
                        "needs_3d_asset": True,
                        "asset_strategy": "hunyuan3d_img2asset",
                        "preferred_subject_image_view": "three_quarter",
                    }
                ],
                "spatial_relations": [],
                "constraints": ["single clear hero subject", "avoid cluttered background"],
                "open_questions": [],
                "version": 1,
            }
        ),
        "ConceptPromptPlanner": json.dumps(
            {
                "final_preview_prompt": "A compact friendly robot on a small pedestal in a clean studio display scene.",
                "subject_prompts": {
                    "subject_robot": "Compact friendly robot, rounded white panels, blue accent lights, expressive face screen, three-quarter view."
                },
                "scene_prompts": [
                    "Clean studio display area, small pedestal, soft shadows, uncluttered floor."
                ],
                "negative_prompt": "blurry, cropped, extra limbs, messy background",
            }
        ),
    }


def _latest_output_for_node(run_dir: Path, node_name: str) -> dict:
    records = [
        json.loads(line)
        for line in (run_dir / "runtime_execution.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in reversed(records):
        if record.get("node_name") == node_name:
            return json.loads(Path(record["output_json"]).read_text(encoding="utf-8"))
    raise AssertionError(f"missing node output: {node_name}")


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


def _blender_edit_refresh_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "outputs" / "runs" / "run_blender_edit_refresh_loop"
    run_dir.mkdir(parents=True)
    blend = _artifact(tmp_path, "blend_file", ArtifactType.BLENDER_FILE, ".blend", b"blend")
    state = AgentProjectState(
        project_id="project_blender_edit_refresh",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_EDIT,
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
        artifacts=[blend],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    return run_dir


def _blender_edit_router_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "outputs" / "runs" / "run_blender_edit_router_loop"
    run_dir.mkdir(parents=True)
    blend = _artifact(tmp_path, "blend_file", ArtifactType.BLENDER_FILE, ".blend", b"blend")
    state = AgentProjectState(
        project_id="project_blender_edit_router",
        thread_id="runtime_console",
        phase=WorkflowPhase.BLENDER_EDIT,
        user_turns=[
            UserTurn(
                turn_id="turn_blender_feedback_001",
                text="把机器人挪到画面中心，镜头保持不变。",
                phase_at_turn=WorkflowPhase.BLENDER_EDIT,
                created_at="2026-06-30T00:00:00+00:00",
            )
        ],
        scene_spec=SceneSpec(**_fixture_scene_spec_payload()),
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
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_scene_001"),
        artifacts=[blend],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    return run_dir


def _fixture_scene_spec_payload() -> dict:
    return {
        "scene_id": "scene_001",
        "title": "Compact Robot Display",
        "user_goal": "Create a compact friendly robot in a clean studio display scene.",
        "style": {
            "style_keywords": ["clean", "friendly", "polished"],
            "rendering_style": "stylized",
        },
        "environment": {
            "environment_type": "studio",
            "description": "A small clean studio display area with a simple pedestal.",
        },
        "lighting": {"description": "Soft studio lighting with a gentle key light."},
        "camera": {
            "shot_type": "three quarter",
            "framing": "full subject centered with some floor visible",
            "target_subject_ids": ["subject_robot"],
        },
        "subjects": [
            {
                "subject_id": "subject_robot",
                "display_name": "Friendly Robot",
                "category": "character",
                "role_in_scene": "hero subject",
                "description": "A compact friendly robot with rounded white panels and blue accent lights.",
                "appearance": "rounded body, small antenna, expressive screen face, clean toy-like finish",
                "pose_or_state": "standing upright on a small pedestal",
                "reference_image_ids": [],
                "priority": "hero",
                "needs_2d_concept": True,
                "needs_3d_asset": True,
                "asset_strategy": "hunyuan3d_img2asset",
                "preferred_subject_image_view": "three_quarter",
            }
        ],
        "spatial_relations": [],
        "constraints": ["single clear hero subject", "avoid cluttered background"],
        "open_questions": [],
        "version": 1,
    }


def _blender_edit_router_response() -> str:
    return json.dumps(
        {
            "route": "pure_blender_edit",
            "patches": [
                {
                    "patch_id": "patch_move_hero_from_router",
                    "source_turn_id": "turn_blender_feedback_001",
                    "phase_created": "BLENDER_EDIT",
                    "target_type": "blender_object",
                    "target_id": "hero",
                    "patch_type": "move_object",
                    "instruction": "把机器人挪到画面中心，镜头保持不变。",
                    "structured_delta": {},
                    "affected_artifact_ids": ["blend_file"],
                    "status": "pending",
                }
            ],
            "allowed_domain_tool_names": ["move_subject", "export_viewer_scene", "render_preview"],
            "domain_tool_calls": [
                {
                    "domain_tool_name": "move_subject",
                    "arguments": {"blender_object_id": "hero", "location": [1, 2, 3]},
                    "reason": "center_hero_without_camera_change",
                    "patch_id": "patch_move_hero_from_router",
                }
            ],
            "reason": "用户要求的是已有 Blender 场景内的主体位置微调。",
        }
    )


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
                    for key in ("viewer_glb", "scene_state_json", "preview_png", "preview_blend")
                    if key in args
                },
                tool_call_record=record,
            )

    monkeypatch.setattr(
        "agent_runtime.runtime_execution.ScriptDomainToolDispatcher",
        FakeScriptDomainToolDispatcher,
    )
    return calls


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
