import json
from pathlib import Path

from agent_runtime.runtime_console import create_runtime_console_run
from agent_runtime.runtime_user_actions import approve_model_assets, request_model_changes
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    Asset3DRecord,
    AssetLibraryItem,
    ConceptBundle,
    ConceptImageRequirement,
    ConceptPromptPack,
    EnvironmentSpec,
    LightingSpec,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_approve_model_assets_advances_to_scene_generation(tmp_path: Path) -> None:
    run_dir = _model_review_run(tmp_path)

    result = approve_model_assets(run_dir, note="模型可以")
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record.action_type == "approve_model_assets"
    assert result.record.applied_fields == ["asset_library", "phase"]
    assert state["phase"] == "SCENE_ASSET_GENERATION"
    assert state["asset_library"][1]["review_status"] == "liked"
    assert frontend_status["phase"] == "SCENE_ASSET_GENERATION"


def test_request_model_changes_creates_review_patch_and_returns_to_concept_regen(tmp_path: Path) -> None:
    run_dir = _model_review_run(tmp_path)

    result = request_model_changes(
        run_dir,
        feedback_text="不同意，模型失真严重，需要重新生成概念图。",
        source_turn_id="turn_model_feedback_001",
    )
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record.action_type == "request_model_changes"
    assert state["phase"] == "CONCEPT_REVIEW"
    assert state["concept_bundle"]["approved"] is False
    assert state["review_patches"][0]["phase_created"] == "SUBJECT_ASSET_QA"
    assert state["review_patches"][0]["patch_type"] == "redo_subject"
    assert state["review_patches"][0]["structured_delta"]["return_to"] == "concept_regeneration"
    assert state["asset_library"][1]["review_status"] == "rejected"
    assert [job.get("node_name") or job.get("domain_tool_name") for job in plan["runtime_plan"]["jobs"]] == [
        "RegenerationRouter",
        "ConceptPromptPlanner",
        "regenerate_concept_images",
    ]


def _model_review_run(tmp_path: Path) -> Path:
    created = create_runtime_console_run(root=tmp_path, run_id="round04_model_review")
    run_dir = Path(created.run_dir)
    state = AgentProjectState(
        project_id="project_round04_model_review",
        thread_id="thread_round04",
        phase=WorkflowPhase.SUBJECT_ASSET_QA,
        scene_spec=SceneSpec(
            scene_id="scene_robot_lab",
            title="Robot Lab",
            user_goal="Create a robot in a lab.",
            style=StyleSpec(style_keywords=["clean"]),
            environment=EnvironmentSpec(environment_type="lab", description="A clean lab."),
            lighting=LightingSpec(description="soft"),
            camera={},
            subjects=[
                SubjectSpec(
                    subject_id="subject_robot",
                    display_name="Robot",
                    category="character",
                    description="A compact robot.",
                )
            ],
        ),
        concept_bundle=ConceptBundle(
            concept_version=1,
            approved=True,
            approved_at="2026-07-01T00:00:00+00:00",
            subject_concept_images={"subject_robot": ["concept_robot_001"]},
            scene_concept_image_ids=["scene_concept_001"],
            final_preview_image_id="target_render_001",
            prompt_pack=ConceptPromptPack(
                final_preview_prompt="Robot in a lab.",
                subject_prompts={"subject_robot": "Robot only."},
                scene_prompts=["Lab only."],
                image_requirements=[
                    ConceptImageRequirement(
                        requirement_id="subject_concept:subject_robot",
                        output_type="subject_concept",
                        target_id="subject_robot",
                        prompt_key="subject_prompts.subject_robot",
                        user_review_label="Robot concept",
                        purpose="subject model source",
                    )
                ],
            ),
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="concept_robot_001",
                artifact_type=ArtifactType.SUBJECT_CONCEPT_IMAGE,
                uri="/tmp/concept_robot_001.png",
                mime_type="image/png",
                linked_subject_id="subject_robot",
            ),
            ArtifactRecord(
                artifact_id="subject_model_robot_001",
                artifact_type=ArtifactType.SUBJECT_3D_ASSET,
                uri="/tmp/subject_model_robot_001.glb",
                mime_type="model/gltf-binary",
                linked_subject_id="subject_robot",
            ),
        ],
        subject_assets=[
            Asset3DRecord(
                asset_id="subject_model_robot_001",
                subject_id="subject_robot",
                source_image_id="concept_robot_001",
                glb_uri="/tmp/subject_model_robot_001.glb",
                status="succeeded",
            )
        ],
        asset_library=[
            AssetLibraryItem(
                library_item_id="library_concept_robot_001",
                artifact_id="concept_robot_001",
                asset_kind="subject_concept",
                subject_id="subject_robot",
                selection_status="selected_for_model_generation",
                created_at="2026-07-01T00:00:00+00:00",
                updated_at="2026-07-01T00:00:00+00:00",
            ),
            AssetLibraryItem(
                library_item_id="library_subject_model_robot_001",
                artifact_id="subject_model_robot_001",
                asset_kind="subject_model",
                subject_id="subject_robot",
                source_artifact_ids=["concept_robot_001"],
                created_at="2026-07-01T00:00:00+00:00",
                updated_at="2026-07-01T00:00:00+00:00",
            ),
        ],
    )
    (run_dir / "state.json").write_text(json.dumps(state.model_dump(mode="json"), indent=2), encoding="utf-8")
    return run_dir
