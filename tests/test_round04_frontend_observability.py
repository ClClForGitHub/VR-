from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.state import (
    AgentProjectState,
    Asset3DRecord,
    AssetLibraryItem,
    EnvironmentSpec,
    LightingSpec,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_frontend_status_exposes_model_review_user_actions() -> None:
    state = AgentProjectState(
        project_id="project_round04_frontend",
        thread_id="thread_round04",
        phase=WorkflowPhase.SUBJECT_ASSET_QA,
        scene_spec=SceneSpec(
            scene_id="scene_model_review",
            title="Model Review",
            user_goal="Review generated model assets.",
            style=StyleSpec(style_keywords=["clean"]),
            environment=EnvironmentSpec(environment_type="studio", description="studio"),
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
                library_item_id="library_subject_model_robot_001",
                artifact_id="subject_model_robot_001",
                asset_kind="subject_model",
                subject_id="subject_robot",
                source_artifact_ids=["concept_robot_001"],
                created_at="2026-07-01T00:00:00+00:00",
                updated_at="2026-07-01T00:00:00+00:00",
            )
        ],
    )

    status = build_frontend_status(state=state, summary={"ok": True, "dry_run": False})
    payloads = {item.action_type: item.payload for item in status.available_user_action_payloads}

    assert status.status == "needs_user_action"
    assert status.current_stage == "model_asset_approval"
    assert status.current_node == "ModelAssetReviewGate"
    assert status.progress_label == "Waiting for approve_model_assets"
    assert status.available_user_actions == ["approve_model_assets", "request_model_changes"]
    assert payloads["approve_model_assets"]["action_type"] == "approve_model_assets"
    assert payloads["request_model_changes"]["feedback_text"]
