import json
from pathlib import Path

from agent_runtime.runtime_console import append_console_message, create_runtime_console_run, save_console_upload
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.runtime_execution import RuntimeJobExecutionRecord
from agent_runtime.runtime_loop import run_bounded_runtime_loop
from agent_runtime.runtime_runs import build_runtime_run_bundle
from agent_runtime.runtime_state_apply import apply_next_runtime_candidate, read_runtime_apply_records
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    BlenderObjectRecord,
    BlenderSceneState,
    ConceptBundle,
    ConceptPromptPack,
    ReviewPatch,
    SceneSpec,
    UserTurn,
    ViewerSceneObjectRecord,
    ViewerSceneState,
    WorkflowPhase,
)


def test_runtime_state_apply_reference_binding_candidate_updates_state_and_plan(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    upload = save_console_upload(
        created.run_dir,
        filename="reference.png",
        content=b"fake-image",
        mime_type="image/png",
    )
    append_console_message(
        created.run_dir,
        role="user",
        text=f"Use {upload.image_id} as the subject reference for subject_robot.",
        attachment_ids=[upload.image_id or ""],
    )
    build_and_save_runtime_dispatch_plan(created.run_dir)
    _write_completed_execution(
        Path(created.run_dir),
        execution_id="exec_ref",
        job_id="job_01_intake_ReferenceBindingValidator",
        node_name="ReferenceBindingValidator",
        parsed_output={
            "valid_bindings": [
                {
                    "image_id": upload.image_id,
                    "target_type": "subject",
                    "target_id": "subject_robot",
                    "usage": "subject_reference",
                    "explicit_in_user_text": True,
                    "confidence": 0.96,
                }
            ],
            "requires_clarification": False,
            "open_questions": [],
            "issues": [],
        },
    )

    result = apply_next_runtime_candidate(created.run_dir)
    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((Path(created.run_dir) / "runtime_plan.json").read_text(encoding="utf-8"))
    records = read_runtime_apply_records(created.run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert result.record.applied_fields == ["reference_bindings"]
    assert result.record.checkpoint_id is not None
    assert state["reference_bindings"][0]["image_id"] == upload.image_id
    assert state["reference_bindings"][0]["target_id"] == "subject_robot"
    assert plan["ok"] is True
    assert plan["runtime_plan"]["jobs"][0]["kind"] == "llm_node"
    assert records[0].execution_id == "exec_ref"


def test_runtime_state_apply_scene_spec_candidate_advances_phase_and_checkpoint(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    run_dir.mkdir(parents=True)
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.SCENE_SPEC_DRAFT,
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    _write_completed_execution(
        run_dir,
        execution_id="exec_scene",
        job_id="job_01_scenespec_SceneSpecCompiler",
        node_name="SceneSpecCompiler",
        parsed_output=_scene_spec_payload(),
    )

    result = apply_next_runtime_candidate(run_dir, rebuild_plan=True)
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record is not None
    assert result.record.applied_fields == ["scene_spec", "phase"]
    assert state_payload["phase"] == "SCENE_SPEC_READY"
    assert state_payload["scene_spec"]["scene_id"] == "scene_001"
    assert summary["executed_stages"] == ["runtime_state_apply"]
    assert summary["stage_checkpoints"][0]["node_name"] == "SceneSpecCompiler"
    assert frontend_status["phase"] == "SCENE_SPEC_READY"
    assert (run_dir / "checkpoints" / "checkpoints.jsonl").exists()


def test_runtime_run_bundle_exposes_runtime_apply_files(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    _write_completed_execution(
        Path(created.run_dir),
        execution_id="exec_scene",
        job_id="job_01_scenespec_SceneSpecCompiler",
        node_name="SceneSpecCompiler",
        parsed_output=_scene_spec_payload(),
    )
    apply_next_runtime_candidate(created.run_dir)

    bundle = build_runtime_run_bundle(created.run_dir)
    assert bundle.runtime_apply_summary is not None
    assert bundle.runtime_apply_summary["latest_record"]["status"] == "applied"
    assert bundle.file_manifest is not None
    existing = {record.label for record in bundle.file_manifest.files if record.exists}
    assert {"runtime_apply", "runtime_apply_summary"} <= existing


def test_runtime_state_apply_feedback_patch_parser_appends_review_patch_and_rebuilds_plan(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_feedback"
    run_dir.mkdir(parents=True)
    state = _concept_review_state()
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    _write_completed_execution(
        run_dir,
        execution_id="exec_feedback",
        job_id="job_01_concept_review_FeedbackPatchParser",
        node_name="FeedbackPatchParser",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        parsed_output={
            "patches": [_review_patch_payload("patch_from_llm")],
            "requires_clarification": False,
            "clarification_question": None,
        },
    )

    result = apply_next_runtime_candidate(run_dir, rebuild_plan=True)
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record is not None
    assert result.record.applied_fields == ["review_patches", "phase"]
    assert state_payload["phase"] == "CONCEPT_REVIEW"
    assert state_payload["review_patches"][0]["patch_id"] == "patch_from_llm"
    assert [job.get("node_name") or job.get("domain_tool_name") for job in plan["runtime_plan"]["jobs"]] == [
        "RegenerationRouter",
        "ConceptPromptPlanner",
        "regenerate_concept_images",
    ]


def test_runtime_loop_routes_pending_review_patch_to_regeneration_delegation(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_regen"
    run_dir.mkdir(parents=True)
    state = _concept_review_state(
        review_patches=[
            ReviewPatch(
                patch_id="patch_pending",
                source_turn_id="turn_feedback",
                phase_created=WorkflowPhase.CONCEPT_REVIEW,
                target_type="subject",
                target_id="subject_robot",
                patch_type="appearance_change",
                instruction="让主体更像棉花娃娃",
                affected_artifact_ids=["concept_old"],
            )
        ]
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir)

    result = run_bounded_runtime_loop(
        run_dir,
        max_steps=5,
        dry_run=True,
        response_text_by_node={
            "RegenerationRouter": json.dumps(
                {
                    "route": "regenerate_concept",
                    "affected_artifact_ids": ["concept_old"],
                    "next_phase": "CONCEPT_GENERATION",
                    "reason": "用户要求调整概念外观，需要重生成概念图。",
                },
                ensure_ascii=False,
            ),
            "ConceptPromptPlanner": json.dumps(
                {
                    "final_preview_prompt": "A soft plush-like robot in a clean warm flower field.",
                    "subject_prompts": {"subject_robot": "soft plush robot, chibi proportions"},
                    "scene_prompts": ["clean warm flower field"],
                    "negative_prompt": "clutter, blurry",
                },
                ensure_ascii=False,
            ),
        },
    )
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.stop_reason == "delegated"
    assert [item.node_name or item.domain_tool_name for item in result.iterations] == [
        "RegenerationRouter",
        "ConceptPromptPlanner",
        "regenerate_concept_images",
    ]
    assert state_payload["phase"] == "CONCEPT_GENERATION"
    assert state_payload["concept_bundle"]["final_preview_image_id"] is None
    assert state_payload["concept_bundle"]["subject_concept_images"] == {}
    assert state_payload["concept_bundle"]["prompt_pack"]["subject_prompts"]["subject_robot"].startswith("soft plush")


def test_runtime_state_apply_blender_edit_router_records_patch_without_repeating_router(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_blender_edit"
    run_dir.mkdir(parents=True)
    state = _blender_edit_state()
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    _write_completed_execution(
        run_dir,
        execution_id="exec_blender_router",
        job_id="job_01_blender_edit_BlenderEditRouter",
        node_name="BlenderEditRouter",
        phase=WorkflowPhase.BLENDER_EDIT,
        parsed_output={
            "route": "pure_blender_edit",
            "patches": [
                {
                    **_review_patch_payload("patch_camera"),
                    "phase_created": "BLENDER_PREVIEW",
                    "target_type": "camera",
                    "target_id": None,
                    "patch_type": "camera_change",
                    "instruction": "镜头低一点，主体更居中。",
                }
            ],
            "allowed_domain_tool_names": ["update_camera", "export_viewer_scene", "render_preview"],
            "domain_tool_calls": [
                {
                    "domain_tool_name": "update_camera",
                    "arguments": {"camera_name": "Camera", "location": [0, -5, 2.2], "focal_length": 45},
                    "reason": "lower_camera_and_center_subject",
                    "patch_id": "patch_camera",
                }
            ],
            "reason": "用户请求属于相机和构图调整。",
        },
    )

    result = apply_next_runtime_candidate(run_dir)
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    records = read_runtime_apply_records(run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.applied_fields == ["review_patches"]
    assert result.record.result_summary["route"] == "pure_blender_edit"
    assert state_payload["phase"] == "BLENDER_EDIT"
    assert state_payload["review_patches"][0]["patch_id"] == "patch_camera"
    edit_plan = state_payload["review_patches"][0]["structured_delta"]["blender_edit_plan"]
    assert edit_plan["domain_tool_calls"][0]["domain_tool_name"] == "update_camera"
    assert edit_plan["domain_tool_calls"][0]["arguments"]["focal_length"] == 45
    assert result.record.result_summary["domain_tool_calls"][0]["domain_tool_name"] == "update_camera"
    assert records[0].node_name == "BlenderEditRouter"


def test_runtime_state_apply_blender_edit_router_synthesizes_patch_from_tool_calls(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_blender_edit_tool_only"
    run_dir.mkdir(parents=True)
    state = _blender_edit_state()
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    _write_completed_execution(
        run_dir,
        execution_id="exec_blender_router_tool_only",
        job_id="job_01_blender_edit_BlenderEditRouter",
        node_name="BlenderEditRouter",
        phase=WorkflowPhase.BLENDER_EDIT,
        parsed_output={
            "route": "pure_blender_edit",
            "patches": [],
            "allowed_domain_tool_names": ["move_subject", "export_viewer_scene", "render_preview"],
            "domain_tool_calls": [
                {
                    "domain_tool_name": "move_subject",
                    "arguments": {"subject_id": "subject_robot", "location": [1, 2, 3]},
                    "reason": "Move Hero to new coordinates.",
                    "patch_id": None,
                }
            ],
            "reason": "User request maps directly to a Blender transform.",
        },
    )

    result = apply_next_runtime_candidate(run_dir, rebuild_plan=True)
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record is not None
    assert result.record.applied_fields == ["review_patches"]
    assert result.record.result_summary["patch_ids"][0].startswith("patch_blender_edit_")
    patch = state_payload["review_patches"][0]
    assert patch["patch_type"] == "move_object"
    assert patch["target_type"] == "blender_object"
    assert patch["target_id"] == "subject_robot"
    edit_plan = patch["structured_delta"]["blender_edit_plan"]
    assert edit_plan["domain_tool_calls"][0]["arguments"] == {"subject_id": "subject_robot", "location": [1, 2, 3]}
    plan_result = build_and_save_runtime_dispatch_plan(run_dir)
    plan_payload = json.loads(Path(plan_result.runtime_plan_json).read_text(encoding="utf-8"))
    jobs = plan_payload["runtime_plan"]["jobs"]
    assert jobs[0]["domain_tool_name"] == "move_subject"
    assert jobs[0]["tool_arguments"] == {"subject_id": "subject_robot", "location": [1, 2, 3]}


def test_runtime_state_apply_hydrates_blender_objects_from_viewer_for_full_asset_edit(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_full_asset_edit"
    run_dir.mkdir(parents=True)
    subject_glb = tmp_path / "subject.glb"
    scene_glb = tmp_path / "scene.glb"
    subject_glb.write_bytes(b"subject")
    scene_glb.write_bytes(b"scene")
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.BLENDER_EDIT,
        scene_spec=SceneSpec(**_scene_spec_payload(subject_id="subject_plush")),
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            blend_file_artifact_id="blend_file_001",
            preview_image_id="preview_001",
            objects=[],
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene_001",
            viewer_scene_artifact_id="viewer_glb_001",
            objects=[
                ViewerSceneObjectRecord(
                    viewer_object_id="geometry_0",
                    blender_object_id="geometry_0",
                    display_name="geometry_0",
                    object_type="MESH",
                ),
                ViewerSceneObjectRecord(
                    viewer_object_id="Hunyuan3D_geometry_0.001",
                    blender_object_id="Hunyuan3D_geometry_0.001",
                    display_name="Hunyuan3D_geometry_0.001",
                    object_type="MESH",
                ),
            ],
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="workflow_subject_glb",
                artifact_type=ArtifactType.SUBJECT_3D_ASSET,
                uri=str(subject_glb),
                mime_type="model/gltf-binary",
            ),
            ArtifactRecord(
                artifact_id="workflow_scene_glb",
                artifact_type=ArtifactType.SCENE_3D_ASSET,
                uri=str(scene_glb),
                mime_type="model/gltf-binary",
            ),
        ],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    _write_completed_execution(
        run_dir,
        execution_id="exec_blender_router_full_asset",
        job_id="job_01_blender_edit_BlenderEditRouter",
        node_name="BlenderEditRouter",
        phase=WorkflowPhase.BLENDER_EDIT,
        parsed_output={
            "route": "pure_blender_edit",
            "patches": [],
            "allowed_domain_tool_names": ["move_subject", "export_viewer_scene", "render_preview"],
            "domain_tool_calls": [
                {
                    "domain_tool_name": "move_subject",
                    "arguments": {"subject_id": "subject_plush", "location": [0.5, 1.0, 1.5]},
                    "reason": "Move the hero subject while preserving generated assets.",
                    "patch_id": None,
                }
            ],
            "reason": "User requested a placement adjustment.",
        },
    )

    result = apply_next_runtime_candidate(run_dir, rebuild_plan=True)
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    plan_payload = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record is not None
    assert result.record.applied_fields == ["blender_scene", "review_patches"]
    assert result.record.result_summary["hydrated_blender_scene"]["subject_ids"] == ["subject_plush"]
    hydrated_subject = next(
        item for item in state_payload["blender_scene"]["objects"] if item["subject_id"] == "subject_plush"
    )
    assert state_payload["blender_scene"]["scene_asset_id"] == "workflow_scene_glb"
    assert hydrated_subject["blender_name"] == "Hunyuan3D_geometry_0.001"
    assert hydrated_subject["asset_id"] == "workflow_subject_glb"
    assert hydrated_subject["object_type"] == "subject_asset"
    scene_layers = [item for item in state_payload["blender_scene"]["objects"] if item["object_type"] == "scene_layer"]
    assert scene_layers[0]["scene_asset_id"] == "workflow_scene_glb"
    jobs = plan_payload["runtime_plan"]["jobs"]
    assert jobs[0]["domain_tool_name"] == "move_subject"
    assert jobs[0]["tool_arguments"] == {"subject_id": "subject_plush", "location": [0.5, 1.0, 1.5]}


def _write_completed_execution(
    run_dir: Path,
    *,
    execution_id: str,
    job_id: str,
    node_name: str,
    parsed_output: dict,
    phase: WorkflowPhase | None = None,
) -> None:
    output_path = run_dir / "runtime_execution" / f"{execution_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "execution_id": execution_id,
                "job": {"job_id": job_id, "node_name": node_name},
                "context_json": {},
                "llm_result": {
                    "ok": True,
                    "node_name": node_name,
                    "dry_run": False,
                    "parsed_output": parsed_output,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record = RuntimeJobExecutionRecord(
        execution_id=execution_id,
        job_id=job_id,
        job_kind="llm_node",
        phase=phase or (WorkflowPhase.INTAKE if node_name == "ReferenceBindingValidator" else WorkflowPhase.SCENE_SPEC_DRAFT),
        executor="main_runtime",
        status="completed",
        ok=True,
        created_at="2026-06-28T00:00:00+00:00",
        dry_run=False,
        node_name=node_name,
        output_json=str(output_path),
    )
    with (run_dir / "runtime_execution.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json() + "\n")


def _scene_spec_payload(*, subject_id: str = "subject_robot") -> dict:
    return {
        "scene_id": "scene_001",
        "title": "Robot Display",
        "user_goal": "Create a clean robot display scene.",
        "style": {"style_keywords": ["clean"], "rendering_style": "stylized"},
        "environment": {
            "environment_type": "studio",
            "description": "A compact display studio.",
        },
        "lighting": {"description": "Soft studio light."},
        "camera": {"shot_type": "three quarter"},
        "subjects": [
            {
                "subject_id": subject_id,
                "display_name": "Robot",
                "category": "character",
                "description": "A compact friendly robot.",
            }
        ],
        "spatial_relations": [],
        "constraints": [],
        "open_questions": [],
        "version": 1,
    }


def _concept_review_state(*, review_patches: list[ReviewPatch] | None = None) -> AgentProjectState:
    return AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        user_turns=[
            UserTurn(
                turn_id="turn_feedback",
                text="让主体更像棉花娃娃",
                phase_at_turn=WorkflowPhase.CONCEPT_REVIEW,
                created_at="2026-06-28T00:00:00+00:00",
            )
        ],
        scene_spec=SceneSpec(**_scene_spec_payload()),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="concept_old",
            subject_concept_images={"subject_robot": ["concept_old"]},
            prompt_pack=ConceptPromptPack(final_preview_prompt="old prompt"),
            approved=False,
        ),
        review_patches=review_patches or [],
    )


def _blender_edit_state() -> AgentProjectState:
    return AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.BLENDER_EDIT,
        user_turns=[
            UserTurn(
                turn_id="turn_blender_feedback",
                text="镜头低一点，主体更居中",
                phase_at_turn=WorkflowPhase.BLENDER_EDIT,
                created_at="2026-06-28T00:00:00+00:00",
            )
        ],
        scene_spec=SceneSpec(**_scene_spec_payload()),
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            blend_file_artifact_id="blend_file_001",
            preview_image_id="preview_001",
            objects=[
                BlenderObjectRecord(
                    object_id="hero",
                    blender_name="Hero",
                    subject_id="subject_robot",
                    object_type="subject_asset",
                )
            ],
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene_001",
            viewer_scene_artifact_id="viewer_glb_001",
        ),
    )


def _review_patch_payload(patch_id: str) -> dict:
    return {
        "patch_id": patch_id,
        "source_turn_id": "turn_feedback",
        "phase_created": "CONCEPT_REVIEW",
        "target_type": "subject",
        "target_id": "subject_robot",
        "patch_type": "appearance_change",
        "instruction": "让主体更像棉花娃娃",
        "structured_delta": {"feedback_text": "让主体更像棉花娃娃"},
        "affected_artifact_ids": ["concept_old"],
        "status": "pending",
    }
