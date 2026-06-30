from pathlib import Path

from agent_runtime.artifacts import FileArtifactStore
from agent_runtime.concept_regeneration import apply_review_patch_concept_regeneration
from agent_runtime.state import AgentProjectState, ConceptBundle, ReviewPatch, WorkflowPhase


def _state_with_pending_subject_patch() -> AgentProjectState:
    return AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        concept_bundle=ConceptBundle(
            concept_version=2,
            final_preview_image_id="preview_old",
            subject_concept_images={"subject_001": ["source_old"]},
            approved=True,
            approved_at="2026-06-28T00:00:00+00:00",
        ),
        review_patches=[
            ReviewPatch(
                patch_id="patch_001",
                source_turn_id="turn_001",
                phase_created=WorkflowPhase.CONCEPT_REVIEW,
                target_type="subject",
                target_id="subject_001",
                patch_type="redo_subject",
                instruction="重画主体概念图，让轮廓更接近参考图。",
                structured_delta={"asset_id": "asset_bad"},
                affected_artifact_ids=["asset_bad", "source_old"],
            )
        ],
    )


def test_apply_review_patch_concept_regeneration_dry_run_keeps_patch_pending() -> None:
    state = _state_with_pending_subject_patch()

    result, updated = apply_review_patch_concept_regeneration(
        state=state,
        dry_run=True,
    )

    assert result.ok is True
    assert result.status == "planned"
    assert result.patch_id == "patch_001"
    assert result.target_subject_id == "subject_001"
    assert result.previous_image_ids == ["source_old"]
    assert result.invalidated_asset_ids == ["asset_bad"]
    assert result.plan["domain_tool_name"] == "regenerate_concept_images"
    assert updated.phase == WorkflowPhase.CONCEPT_GENERATION
    assert updated.review_patches[0].status == "pending"
    assert updated.concept_bundle == state.concept_bundle
    assert updated.artifacts == []


def test_apply_review_patch_concept_regeneration_registers_generated_subject_image(tmp_path: Path) -> None:
    state = _state_with_pending_subject_patch()
    image = tmp_path / "generated.png"
    image.write_bytes(b"generated concept image")
    artifact_store = FileArtifactStore(tmp_path / "artifacts")

    result, updated = apply_review_patch_concept_regeneration(
        state=state,
        artifact_store=artifact_store,
        generated_image_path=image,
        generated_image_artifact_id="source_new",
        dry_run=False,
    )

    assert result.ok is True
    assert result.status == "applied"
    assert result.generated_image_artifact_id == "source_new"
    assert result.marked_patch_applied is True
    assert updated.phase == WorkflowPhase.SUBJECT_ASSET_GENERATION
    assert updated.review_patches[0].status == "applied"
    assert updated.concept_bundle is not None
    assert updated.concept_bundle.concept_version == 3
    assert updated.concept_bundle.final_preview_image_id is None
    assert updated.concept_bundle.approved is False
    assert updated.concept_bundle.subject_concept_images["subject_001"] == ["source_old", "source_new"]
    assert updated.artifacts[0].artifact_id == "source_new"
    assert updated.artifacts[0].artifact_type.value == "SUBJECT_CONCEPT_IMAGE"
    assert Path(updated.artifacts[0].uri).is_file()


def test_apply_review_patch_concept_regeneration_blocks_without_pending_patch() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_REVIEW,
    )

    result, updated = apply_review_patch_concept_regeneration(
        state=state,
        dry_run=True,
    )

    assert result.ok is False
    assert result.status == "blocked"
    assert result.issues == ["missing_review_patch"]
    assert updated == state
