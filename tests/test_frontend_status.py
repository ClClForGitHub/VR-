from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    BlenderSceneState,
    ConceptBundle,
    PendingAction,
    ViewerSceneState,
    WorkflowPhase,
)


def test_frontend_status_summarizes_pending_action_and_stage_progress() -> None:
    state = AgentProjectState(
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
                "source_image_id": "image_001",
                "repair_decision": {"user_visible": True},
            },
        ),
    )
    summary = {
        "ok": True,
        "dry_run": False,
        "requested_stages": ["quality_check", "repair_decision", "repair_execute"],
        "executed_stages": ["quality_check", "repair_decision", "repair_execute"],
        "stage_checkpoints": [
            {
                "node_name": "workflow_runner.subject_asset.quality_check",
                "reason": "subject_asset_quality_checked",
                "metadata": {"stage": "quality_check", "workflow": "subject-asset", "ok": True},
            },
            {
                "node_name": "workflow_runner.subject_asset.repair_execute",
                "reason": "subject_asset_repair_execution_handled",
                "metadata": {"stage": "repair_execute", "workflow": "subject-asset", "ok": True},
            },
        ],
        "skipped_stages": {},
    }

    status = build_frontend_status(state=state, summary=summary)

    assert status.status == "needs_user_action"
    assert status.workflow == "subject-asset"
    assert status.current_stage == "repair_execute"
    assert status.current_node == "workflow_runner.subject_asset.repair_execute"
    assert status.progress_label == "Waiting for ask_user_clarification"
    assert status.pending_action is not None
    assert status.pending_action.asset_id == "asset_001"
    assert status.pending_action.payload_kind == "subject_asset_repair"
    assert [item.stage for item in status.stage_progress] == [
        "quality_check",
        "repair_decision",
        "repair_execute",
    ]
    assert status.stage_progress[-1].status == "completed"


def test_frontend_status_marks_failed_checkpoint_as_attention_required() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SUBJECT_ASSET_QA,
    )
    summary = {
        "ok": False,
        "dry_run": True,
        "requested_stages": ["quality_check"],
        "executed_stages": ["quality_check"],
        "stage_checkpoints": [
            {
                "node_name": "workflow_runner.subject_asset.quality_check",
                "reason": "quality_check_failed",
                "metadata": {"stage": "quality_check", "workflow": "subject-asset", "ok": False},
            }
        ],
        "skipped_stages": {},
    }

    status = build_frontend_status(state=state, summary=summary)

    assert status.status == "attention_required"
    assert status.current_stage == "quality_check"
    assert status.stage_progress[0].status == "failed"
    assert status.stage_progress[0].reason == "quality_check_failed"


def test_frontend_status_prefers_blender_preview_gate_over_stale_summary_stage() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        blender_scene=BlenderSceneState(blender_scene_id="blend_001"),
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_001"),
    )
    summary = {
        "ok": True,
        "dry_run": False,
        "requested_stages": ["runtime_state_apply", "concept_approval"],
        "executed_stages": ["runtime_state_apply", "concept_approval"],
        "stage_checkpoints": [
            {
                "node_name": "ConceptReviewGate",
                "reason": "concept_approved",
                "metadata": {"stage": "concept_approval", "workflow": "runtime-console", "ok": True},
            }
        ],
        "skipped_stages": {},
    }

    status = build_frontend_status(state=state, summary=summary)

    assert status.status == "needs_user_action"
    assert status.current_stage == "blender_preview_approval"
    assert status.current_node == "BlenderPreviewReviewGate"
    assert status.progress_label == "Waiting for approve_blender_preview"


def test_frontend_status_marks_concept_review_outputs_as_user_gate() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        concept_bundle=ConceptBundle(
            concept_version=1,
            subject_concept_images={"subject_001": ["concept_001"]},
            approved=False,
        ),
    )

    status = build_frontend_status(state=state, summary={"ok": True, "dry_run": False})

    assert status.status == "needs_user_action"
    assert status.current_stage == "concept_approval"
    assert status.current_node == "ConceptReviewGate"
    assert status.progress_label == "Waiting for approve_concept"


def test_frontend_status_falls_back_to_asset_artifacts_for_legacy_full_asset_runs() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_EDIT,
        artifacts=[
            ArtifactRecord(
                artifact_id="workflow_subject_glb",
                artifact_type=ArtifactType.SUBJECT_3D_ASSET,
                uri="/tmp/subject.glb",
                mime_type="model/gltf-binary",
            ),
            ArtifactRecord(
                artifact_id="workflow_scene_glb",
                artifact_type=ArtifactType.SCENE_3D_ASSET,
                uri="/tmp/scene.glb",
                mime_type="model/gltf-binary",
            ),
        ],
    )

    status = build_frontend_status(state=state, summary={"ok": True, "dry_run": False})

    assert status.subject_asset_ids == ["workflow_subject_glb"]
    assert status.scene_asset_id == "workflow_scene_glb"
