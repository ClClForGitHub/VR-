import json
from pathlib import Path

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.concept_planning import apply_concept_prompt_planner_output
from agent_runtime.runtime_user_actions import request_concept_changes
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    AssetLibraryItem,
    ConceptBundle,
    ConceptPromptPack,
    EnvironmentSpec,
    LightingSpec,
    ReviewPatch,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_concept_rework_request_creates_review_patch_and_regeneration_plan(tmp_path: Path) -> None:
    run_dir = _write_rework_run(tmp_path)

    result = request_concept_changes(
        run_dir,
        feedback_text="Make the robot softer and more toy-like.",
        source_turn_id="turn_feedback_001",
    )
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    runtime_plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record.applied_fields == ["review_patches", "phase"]
    assert state_payload["phase"] == "CONCEPT_REVIEW"
    assert state_payload["review_patches"][0]["source_turn_id"] == "turn_feedback_001"
    assert state_payload["review_patches"][0]["structured_delta"]["kind"] == "concept_feedback"
    assert state_payload["asset_library"][0]["review_status"] == "rejected"
    assert [action["node_name"] for action in runtime_plan["controller"]["actions"] if action.get("node_name")] == [
        "RegenerationRouter",
        "ConceptPromptPlanner",
    ]
    assert runtime_plan["controller"]["actions"][-1]["domain_tool_name"] == "regenerate_concept_images"


def test_pending_rework_planner_application_clears_old_concept_outputs_only() -> None:
    state = AgentProjectState(
        project_id="project_round03",
        thread_id="thread_round03",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=2,
            final_preview_image_id="target_old",
            subject_concept_images={"subject_robot": ["concept_old"]},
            scene_concept_image_ids=["scene_old"],
            prompt_pack=ConceptPromptPack(final_preview_prompt="old target"),
            approved=True,
            approved_at="2026-07-01T00:00:00+00:00",
        ),
        review_patches=[
            ReviewPatch(
                patch_id="patch_001",
                source_turn_id="turn_feedback_001",
                phase_created=WorkflowPhase.CONCEPT_REVIEW,
                target_type="global",
                patch_type="style_change",
                instruction="Make it cuter.",
            )
        ],
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output={
            "final_preview_prompt": "New target render after feedback.",
            "subject_prompts": {"subject_robot": "New softer robot concept."},
            "scene_prompts": ["Same scene, softer light."],
        },
    )

    assert result.ok is True
    assert updated.phase == WorkflowPhase.CONCEPT_GENERATION
    assert updated.concept_bundle.concept_version == 3
    assert updated.concept_bundle.final_preview_image_id is None
    assert updated.concept_bundle.subject_concept_images == {}
    assert updated.concept_bundle.scene_concept_image_ids == []
    assert updated.review_patches[0].status == "pending"


def _write_rework_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "outputs/runs/rework"
    run_dir.mkdir(parents=True)
    now = utc_now_iso()
    state = AgentProjectState(
        project_id="project_round03",
        thread_id="thread_round03",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="target_old",
            subject_concept_images={"subject_robot": ["concept_old"]},
            scene_concept_image_ids=["scene_old"],
            prompt_pack=ConceptPromptPack(final_preview_prompt="old target"),
            approved=False,
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="concept_old",
                artifact_type=ArtifactType.SUBJECT_CONCEPT_IMAGE,
                uri=str(tmp_path / "concept_old.png"),
                mime_type="image/png",
                semantic_role="subject_concept_image",
                linked_subject_id="subject_robot",
            )
        ],
        asset_library=[
            AssetLibraryItem(
                library_item_id="library_concept_old",
                artifact_id="concept_old",
                asset_kind="subject_concept",
                subject_id="subject_robot",
                review_status="rejected",
                selection_status="available",
                created_at=now,
                updated_at=now,
            )
        ],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    return run_dir


def _scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_robot_display",
        title="Robot Display",
        user_goal="Create a robot display.",
        style=StyleSpec(style_keywords=["clean"]),
        environment=EnvironmentSpec(environment_type="studio", description="Clean display."),
        lighting=LightingSpec(description="Soft light."),
        camera={},
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Hero Robot",
                category="character",
                description="A compact robot.",
            )
        ],
    )
