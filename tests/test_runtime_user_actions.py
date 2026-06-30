import json
from pathlib import Path

from agent_runtime.runtime_console import create_runtime_console_run
from agent_runtime.runtime_runs import build_runtime_run_bundle
from agent_runtime.runtime_user_actions import (
    approve_blender_preview,
    approve_concept_review,
    read_runtime_user_action_summary,
    request_blender_changes,
    request_concept_changes,
)
from agent_runtime.state import (
    AgentProjectState,
    BlenderSceneState,
    CameraSpec,
    ConceptBundle,
    ConceptPromptPack,
    EnvironmentSpec,
    LightingSpec,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    UserTurn,
    ViewerSceneState,
    WorkflowPhase,
)


def test_approve_concept_review_advances_to_subject_asset_plan(tmp_path: Path) -> None:
    run_dir = _concept_review_run(tmp_path)

    result = approve_concept_review(run_dir, note="looks good")
    state = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((Path(run_dir) / "runtime_plan.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((Path(run_dir) / "frontend_status.json").read_text(encoding="utf-8"))
    summary = read_runtime_user_action_summary(run_dir)
    bundle = build_runtime_run_bundle(run_dir)

    assert result.ok is True
    assert result.record.status == "applied"
    assert result.record.applied_fields == ["concept_bundle", "phase"]
    assert state["phase"] == "CONCEPT_APPROVED"
    assert state["concept_bundle"]["approved"] is True
    assert state["concept_bundle"]["approved_at"]
    assert plan["runtime_plan"]["jobs"][0]["domain_tool_name"] == "build_subject_asset"
    assert frontend_status["phase"] == "CONCEPT_APPROVED"
    assert summary is not None
    assert summary["latest_record"]["action_type"] == "approve_concept"
    assert bundle.runtime_user_action_summary is not None
    assert {"runtime_user_action", "runtime_user_action_summary"} <= {
        item.label for item in bundle.file_manifest.files if item.exists
    }


def test_request_concept_changes_creates_pending_review_patch_and_regen_plan(tmp_path: Path) -> None:
    run_dir = _concept_review_run(tmp_path)

    result = request_concept_changes(
        run_dir,
        feedback_text="把机器人改成黄色，眼睛更大一些",
        source_turn_id="turn_feedback_001",
    )
    state = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((Path(run_dir) / "runtime_plan.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record.status == "applied"
    assert result.record.applied_fields == ["review_patches", "phase"]
    assert state["phase"] == "CONCEPT_REVIEW"
    assert state["concept_bundle"]["approved"] is False
    assert state["review_patches"][0]["status"] == "pending"
    assert state["review_patches"][0]["source_turn_id"] == "turn_feedback_001"
    assert state["review_patches"][0]["instruction"] == "把机器人改成黄色，眼睛更大一些"
    assert state["review_patches"][0]["affected_artifact_ids"] == ["concept_robot_001"]
    assert [job.get("node_name") or job.get("domain_tool_name") for job in plan["runtime_plan"]["jobs"]] == [
        "RegenerationRouter",
        "ConceptPromptPlanner",
        "regenerate_concept_images",
    ]


def test_approve_concept_review_fails_without_state_mutation_outside_gate(tmp_path: Path) -> None:
    run_dir = _concept_review_run(tmp_path, phase=WorkflowPhase.CONCEPT_GENERATION)
    before = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))

    result = approve_concept_review(run_dir)
    after = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))
    summary = read_runtime_user_action_summary(run_dir)

    assert result.ok is False
    assert result.record.status == "failed"
    assert "runtime_user_action_failed" in result.record.issues
    assert before == after
    assert summary is not None
    assert summary["status_counts"] == {"failed": 1}


def test_approve_blender_preview_advances_to_delivery_plan(tmp_path: Path) -> None:
    run_dir = _blender_preview_run(tmp_path)

    result = approve_blender_preview(run_dir, note="preview accepted")
    state = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((Path(run_dir) / "runtime_plan.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((Path(run_dir) / "frontend_status.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record.status == "applied"
    assert result.record.action_type == "approve_blender_preview"
    assert result.record.applied_fields == ["phase"]
    assert state["phase"] == "DELIVERY"
    assert plan["runtime_plan"]["jobs"][0]["kind"] == "delivery"
    assert frontend_status["phase"] == "DELIVERY"


def test_request_blender_changes_routes_to_blender_edit_plan(tmp_path: Path) -> None:
    run_dir = _blender_preview_run(tmp_path)

    result = request_blender_changes(
        run_dir,
        feedback_text="把相机拉近一点，机器人放画面中间",
        source_turn_id="turn_preview_feedback_001",
    )
    state = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((Path(run_dir) / "runtime_plan.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record.status == "applied"
    assert result.record.action_type == "request_blender_changes"
    assert result.record.applied_fields == ["review_patches", "phase"]
    assert state["phase"] == "BLENDER_EDIT"
    assert state["review_patches"][0]["phase_created"] == "BLENDER_PREVIEW"
    assert state["review_patches"][0]["patch_type"] == "layout_change"
    assert state["review_patches"][0]["instruction"] == "把相机拉近一点，机器人放画面中间"
    assert state["review_patches"][0]["affected_artifact_ids"] == [
        "blend_file_001",
        "preview_render_001",
        "viewer_glb_001",
        "viewer_state_001",
    ]
    assert [job.get("node_name") or job.get("domain_tool_name") for job in plan["runtime_plan"]["jobs"]] == [
        "BlenderEditRouter",
        "export_viewer_scene",
        "render_preview",
    ]


def test_approve_blender_preview_fails_without_state_mutation_outside_gate(tmp_path: Path) -> None:
    run_dir = _blender_preview_run(tmp_path, phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION)
    before = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))

    result = approve_blender_preview(run_dir)
    after = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))

    assert result.ok is False
    assert result.record.status == "failed"
    assert "runtime_user_action_failed" in result.record.issues
    assert before == after


def _concept_review_run(tmp_path: Path, *, phase: WorkflowPhase = WorkflowPhase.CONCEPT_REVIEW) -> Path:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    run_dir = Path(created.run_dir)
    state = AgentProjectState(
        project_id="run_001",
        thread_id="runtime_console",
        phase=phase,
        user_turns=[
            UserTurn(
                turn_id="turn_001",
                text="Create a compact robot display.",
                phase_at_turn=WorkflowPhase.INTAKE,
                created_at="2026-06-29T00:00:00+00:00",
            )
        ],
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="concept_robot_001",
            subject_concept_images={"subject_robot": ["concept_robot_001"]},
            prompt_pack=ConceptPromptPack(final_preview_prompt="A compact friendly robot on a pedestal."),
            approved=False,
        ),
    )
    _write_json(run_dir / "state.json", _model_to_dict(state))
    _write_json(run_dir / "summary.json", {"ok": True, "workflow": "runtime-console", "requested_stages": [], "executed_stages": []})
    return run_dir


def _blender_preview_run(tmp_path: Path, *, phase: WorkflowPhase = WorkflowPhase.BLENDER_PREVIEW) -> Path:
    created = create_runtime_console_run(root=tmp_path, run_id="run_blender_preview")
    run_dir = Path(created.run_dir)
    state = AgentProjectState(
        project_id="run_blender_preview",
        thread_id="runtime_console",
        phase=phase,
        user_turns=[
            UserTurn(
                turn_id="turn_001",
                text="Create a compact robot display.",
                phase_at_turn=WorkflowPhase.INTAKE,
                created_at="2026-06-29T00:00:00+00:00",
            )
        ],
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="concept_robot_001",
            approved=True,
        ),
        blender_scene=BlenderSceneState(
            blender_scene_id="blender_scene_001",
            blend_file_artifact_id="blend_file_001",
            preview_image_id="preview_render_001",
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene_001",
            viewer_scene_artifact_id="viewer_glb_001",
            viewer_state_artifact_id="viewer_state_001",
            viewer_scene_path=str(run_dir / "viewer_export" / "viewer_scene.glb"),
        ),
    )
    _write_json(run_dir / "state.json", _model_to_dict(state))
    _write_json(run_dir / "summary.json", {"ok": True, "workflow": "runtime-console", "requested_stages": [], "executed_stages": []})
    return run_dir


def _scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_001",
        title="Robot Display",
        user_goal="Create a compact robot display.",
        style=StyleSpec(style_keywords=["clean"], rendering_style="stylized"),
        environment=EnvironmentSpec(environment_type="studio", description="Clean display area."),
        lighting=LightingSpec(description="Soft light."),
        camera=CameraSpec(shot_type="three quarter", target_subject_ids=["subject_robot"]),
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Robot",
                category="character",
                description="A compact friendly robot.",
            )
        ],
    )


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
