from agent_runtime.review_patches import create_review_patch_from_pending_action
from agent_runtime.state import AgentProjectState, PendingAction, WorkflowPhase


def _state_with_subject_repair_pending_action() -> AgentProjectState:
    return AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SUBJECT_ASSET_QA,
        pending_action=PendingAction(
            action_id="pending_001",
            phase=WorkflowPhase.SUBJECT_ASSET_QA,
            action_type="ask_user_clarification",
            payload={
                "kind": "subject_asset_repair",
                "asset_id": "asset_001",
                "subject_id": "subject_001",
                "source_image_id": "source_001",
                "repair_decision": {
                    "action": "ask_user",
                    "reason": "quality_uncertain_requires_review",
                    "user_visible": True,
                },
            },
        ),
    )


def test_create_review_patch_from_pending_subject_asset_action() -> None:
    state = _state_with_subject_repair_pending_action()

    result, updated = create_review_patch_from_pending_action(
        state=state,
        user_feedback="重画这个主体概念图，轮廓要更像原图。",
        source_turn_id="turn_001",
        patch_id="patch_001",
    )

    assert result.ok is True
    assert result.patch is not None
    assert result.patch.patch_id == "patch_001"
    assert result.patch.source_turn_id == "turn_001"
    assert result.patch.phase_created == WorkflowPhase.SUBJECT_ASSET_QA
    assert result.patch.target_type == "subject"
    assert result.patch.target_id == "subject_001"
    assert result.patch.patch_type == "redo_subject"
    assert result.patch.affected_artifact_ids == ["asset_001", "source_001"]
    assert result.patch.structured_delta["pending_action_id"] == "pending_001"
    assert result.patch.structured_delta["repair_decision"]["action"] == "ask_user"
    assert updated.pending_action is None
    assert updated.phase == WorkflowPhase.CONCEPT_REVIEW
    assert [patch.patch_id for patch in updated.review_patches] == ["patch_001"]


def test_create_review_patch_reports_missing_pending_action() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SUBJECT_ASSET_QA,
    )

    result, updated = create_review_patch_from_pending_action(
        state=state,
        user_feedback="redo subject",
    )

    assert result.ok is False
    assert result.issues == ["missing_pending_action"]
    assert updated.review_patches == []
