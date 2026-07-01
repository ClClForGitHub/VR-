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
    ConceptImageRequirement,
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


def test_user_requested_samples_cover_accept_and_reject_review_branches(tmp_path: Path) -> None:
    beach_accept = _concept_review_run(
        tmp_path / "beach_accept",
        run_id="sample_beach_accept",
        user_text="我想看到一个鸣潮的Q版角色菲比和弗糯糯在海滩上，旁边是沙滩椅和沙子城堡。",
        scene_spec=_sample_scene_spec(
            scene_id="scene_chibi_beach_duo",
            title="Chibi Beach Duo",
            user_goal="Create chibi Phoebe and Fronono-inspired characters on a beach with chair and sand castle.",
            subject_id="subject_phoebe_chibi",
            display_name="Chibi Phoebe",
            category="character",
        ),
        subject_id="subject_phoebe_chibi",
        concept_id="concept_beach_duo_001",
        prompt="菲比和弗糯糯 Q 版角色在海滩上，旁边有沙滩椅和沙子城堡。",
        include_full_concept_set=True,
    )
    beach_accept_result = approve_concept_review(beach_accept, note="同意角色与海滩道具设定")
    beach_accept_state = json.loads((Path(beach_accept) / "state.json").read_text(encoding="utf-8"))

    gwen_reject = _concept_review_run(
        tmp_path / "gwen_reject",
        run_id="sample_gwen_reject",
        user_text="我想看到英雄联盟的Q版角色小小格温图片1在棋盘上，旁边是很多国际象棋棋子。",
        scene_spec=_sample_scene_spec(
            scene_id="scene_little_gwen_chessboard",
            title="Little Gwen Chessboard",
            user_goal="Create chibi Little Gwen from image 1 on a chessboard with chess pieces.",
            subject_id="subject_little_gwen",
            display_name="Chibi Little Gwen",
            category="character",
        ),
        subject_id="subject_little_gwen",
        concept_id="concept_little_gwen_001",
        prompt="图片1小小格温站在棋盘上，周围是很多国际象棋棋子。",
        include_full_concept_set=True,
    )
    gwen_reject_result = request_concept_changes(
        gwen_reject,
        feedback_text="不同意图片1参考匹配：小小格温的蓝色头发和剪刀魔法元素要更明显，棋子不要挡住脸。",
        source_turn_id="turn_gwen_review_reject",
    )
    gwen_reject_state = json.loads((Path(gwen_reject) / "state.json").read_text(encoding="utf-8"))

    rover_preview_accept = _blender_preview_run(
        tmp_path / "rover_preview_accept",
        run_id="sample_rover_preview_accept",
        user_text="我想看到一个探索者机器人车在月亮上，旁边是坑坑洼洼的月壤。",
        scene_spec=_sample_scene_spec(
            scene_id="scene_explorer_rover_moon",
            title="Explorer Rover On Moon",
            user_goal="Create an explorer robot rover on pitted lunar regolith.",
            subject_id="subject_explorer_rover",
            display_name="Explorer Robot Rover",
            category="vehicle",
        ),
    )
    rover_accept_result = approve_blender_preview(rover_preview_accept, note="同意月壤坑洼和车的位置，可以进入交付")
    rover_accept_state = json.loads((Path(rover_preview_accept) / "state.json").read_text(encoding="utf-8"))

    beach_preview_reject = _blender_preview_run(
        tmp_path / "beach_preview_reject",
        run_id="sample_beach_preview_reject",
        user_text="我想看到一个鸣潮的Q版角色菲比和弗糯糯在海滩上，旁边是沙滩椅和沙子城堡。",
        scene_spec=_sample_scene_spec(
            scene_id="scene_chibi_beach_duo",
            title="Chibi Beach Duo",
            user_goal="Create chibi beach duo with chair and sand castle.",
            subject_id="subject_phoebe_chibi",
            display_name="Chibi Phoebe",
            category="character",
        ),
    )
    beach_preview_reject_result = request_blender_changes(
        beach_preview_reject,
        feedback_text="不同意预览：沙滩椅太靠后，沙子城堡需要放到两个Q版角色前方并且相机稍微拉近。",
        source_turn_id="turn_beach_preview_reject",
    )
    beach_preview_reject_state = json.loads((Path(beach_preview_reject) / "state.json").read_text(encoding="utf-8"))

    assert beach_accept_result.ok is True
    assert beach_accept_state["phase"] == "CONCEPT_APPROVED"
    assert beach_accept_state["concept_bundle"]["approved"] is True
    assert gwen_reject_result.ok is True
    assert gwen_reject_state["phase"] == "CONCEPT_REVIEW"
    assert gwen_reject_state["review_patches"][0]["instruction"].startswith("不同意图片1参考匹配")
    assert gwen_reject_state["concept_bundle"]["prompt_pack"]["image_requirements"]
    assert [item["output_type"] for item in gwen_reject_state["concept_bundle"]["prompt_pack"]["image_requirements"]] == [
        "subject_concept",
        "scene_concept",
        "target_render",
    ]
    assert gwen_reject_state["review_patches"][0]["affected_artifact_ids"] == [
        "concept_little_gwen_001",
        "concept_little_gwen_001_render",
        "concept_little_gwen_001_scene",
    ]
    assert rover_accept_result.ok is True
    assert rover_accept_state["phase"] == "DELIVERY"
    assert beach_preview_reject_result.ok is True
    assert beach_preview_reject_state["phase"] == "BLENDER_EDIT"
    assert beach_preview_reject_state["review_patches"][0]["instruction"].startswith("不同意预览")


def test_approve_blender_preview_fails_without_state_mutation_outside_gate(tmp_path: Path) -> None:
    run_dir = _blender_preview_run(tmp_path, phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION)
    before = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))

    result = approve_blender_preview(run_dir)
    after = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))

    assert result.ok is False
    assert result.record.status == "failed"
    assert "runtime_user_action_failed" in result.record.issues
    assert before == after


def _concept_review_run(
    tmp_path: Path,
    *,
    phase: WorkflowPhase = WorkflowPhase.CONCEPT_REVIEW,
    run_id: str = "run_001",
    user_text: str = "Create a compact robot display.",
    scene_spec: SceneSpec | None = None,
    subject_id: str = "subject_robot",
    concept_id: str = "concept_robot_001",
    prompt: str = "A compact friendly robot on a pedestal.",
    include_full_concept_set: bool = False,
) -> Path:
    created = create_runtime_console_run(root=tmp_path, run_id=run_id)
    run_dir = Path(created.run_dir)
    final_preview_image_id = f"{concept_id}_render" if include_full_concept_set else concept_id
    scene_concept_image_ids = [f"{concept_id}_scene"] if include_full_concept_set else []
    prompt_pack = ConceptPromptPack(final_preview_prompt=prompt)
    if include_full_concept_set:
        prompt_pack = ConceptPromptPack(
            final_preview_prompt=prompt,
            subject_prompts={subject_id: f"Subject-only concept for {subject_id}."},
            scene_prompts=[f"Scene concept for {scene_spec.scene_id if scene_spec is not None else 'scene'}."],
            image_requirements=[
                ConceptImageRequirement(
                    requirement_id=f"subject_concept:{subject_id}",
                    output_type="subject_concept",
                    target_id=subject_id,
                    prompt_key=f"subject_prompts.{subject_id}",
                    user_review_label=f"主体概念图：{subject_id}",
                    purpose="review subject identity",
                ),
                ConceptImageRequirement(
                    requirement_id="scene_concept:1",
                    output_type="scene_concept",
                    target_id=(scene_spec.scene_id if scene_spec is not None else "scene_001"),
                    prompt_key="scene_prompts.0",
                    user_review_label="场景概念图",
                    purpose="review scene and props",
                ),
                ConceptImageRequirement(
                    requirement_id="target_render:final_preview",
                    output_type="target_render",
                    target_id=(scene_spec.scene_id if scene_spec is not None else "scene_001"),
                    prompt_key="final_preview_prompt",
                    user_review_label="最终渲染构图图",
                    purpose="review final composition",
                ),
            ],
        )
    state = AgentProjectState(
        project_id=run_id,
        thread_id="runtime_console",
        phase=phase,
        user_turns=[
            UserTurn(
                turn_id="turn_001",
                text=user_text,
                phase_at_turn=WorkflowPhase.INTAKE,
                created_at="2026-06-29T00:00:00+00:00",
            )
        ],
        scene_spec=scene_spec or _scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id=final_preview_image_id,
            subject_concept_images={subject_id: [concept_id]},
            scene_concept_image_ids=scene_concept_image_ids,
            prompt_pack=prompt_pack,
            approved=False,
        ),
    )
    _write_json(run_dir / "state.json", _model_to_dict(state))
    _write_json(run_dir / "summary.json", {"ok": True, "workflow": "runtime-console", "requested_stages": [], "executed_stages": []})
    return run_dir


def _blender_preview_run(
    tmp_path: Path,
    *,
    phase: WorkflowPhase = WorkflowPhase.BLENDER_PREVIEW,
    run_id: str = "run_blender_preview",
    user_text: str = "Create a compact robot display.",
    scene_spec: SceneSpec | None = None,
) -> Path:
    created = create_runtime_console_run(root=tmp_path, run_id=run_id)
    run_dir = Path(created.run_dir)
    state = AgentProjectState(
        project_id=run_id,
        thread_id="runtime_console",
        phase=phase,
        user_turns=[
            UserTurn(
                turn_id="turn_001",
                text=user_text,
                phase_at_turn=WorkflowPhase.INTAKE,
                created_at="2026-06-29T00:00:00+00:00",
            )
        ],
        scene_spec=scene_spec or _scene_spec(),
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


def _sample_scene_spec(
    *,
    scene_id: str,
    title: str,
    user_goal: str,
    subject_id: str,
    display_name: str,
    category: str,
) -> SceneSpec:
    return SceneSpec(
        scene_id=scene_id,
        title=title,
        user_goal=user_goal,
        style=StyleSpec(style_keywords=["user sample"], rendering_style="stylized"),
        environment=EnvironmentSpec(environment_type="sample_scene", description=user_goal),
        lighting=LightingSpec(description="Review lighting."),
        camera=CameraSpec(shot_type="three quarter", target_subject_ids=[subject_id]),
        subjects=[
            SubjectSpec(
                subject_id=subject_id,
                display_name=display_name,
                category=category,
                description=display_name,
            )
        ],
    )


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
