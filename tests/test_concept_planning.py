import json

from agent_runtime.concept_planning import apply_concept_prompt_planner_output
from agent_runtime.llm_nodes import run_llm_node
from agent_runtime.state import AgentProjectState, ConceptBundle, ConceptPromptPack, ReviewPatch, WorkflowPhase


def _planner_payload():
    return {
        "final_preview_prompt": "A friendly robot in a warm workshop.",
        "subject_prompts": {"subject_robot": "friendly robot concept"},
        "scene_prompts": ["warm compact workshop"],
        "negative_prompt": "blurry",
    }


def test_apply_concept_prompt_planner_output_creates_concept_bundle() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SCENE_SPEC_READY,
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output=_planner_payload(),
    )

    assert result.ok is True
    assert result.concept_version == 1
    assert updated.phase == WorkflowPhase.CONCEPT_GENERATION
    assert updated.concept_bundle is not None
    assert updated.concept_bundle.prompt_pack is not None
    assert updated.concept_bundle.prompt_pack.subject_prompts["subject_robot"] == "friendly robot concept"
    assert updated.concept_bundle.approved is False


def test_apply_concept_prompt_planner_output_from_llm_result_resets_approval() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        concept_bundle=ConceptBundle(
            concept_version=2,
            final_preview_image_id="preview_old",
            subject_concept_images={"subject_robot": ["concept_old"]},
            prompt_pack=ConceptPromptPack(final_preview_prompt="old prompt"),
            approved=True,
            approved_at="2026-06-28T00:00:00+00:00",
        ),
    )
    llm_result = run_llm_node(
        node_name="ConceptPromptPlanner",
        context_json={},
        provider_configs=[],
        response_text=json.dumps(_planner_payload()),
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output=llm_result,
    )

    assert result.ok is True
    assert updated.concept_bundle is not None
    assert updated.concept_bundle.concept_version == 3
    assert updated.concept_bundle.final_preview_image_id == "preview_old"
    assert updated.concept_bundle.subject_concept_images == {"subject_robot": ["concept_old"]}
    assert updated.concept_bundle.approved is False
    assert updated.concept_bundle.approved_at is None
    assert updated.concept_bundle.visual_qa is None


def test_apply_concept_prompt_planner_output_blocks_invalid_llm_result() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SCENE_SPEC_READY,
    )
    llm_result = run_llm_node(
        node_name="ConceptPromptPlanner",
        context_json={},
        provider_configs=[],
        response_text=json.dumps({"subject_prompts": {}}),
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output=llm_result,
    )

    assert result.ok is False
    assert result.issues == ["missing_valid_concept_prompt_planner_output"]
    assert updated == state


def test_apply_concept_prompt_planner_output_clears_old_images_for_pending_review_patch() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        concept_bundle=ConceptBundle(
            concept_version=2,
            final_preview_image_id="preview_old",
            subject_concept_images={"subject_robot": ["concept_old"]},
            scene_concept_image_ids=["scene_old"],
            prompt_pack=ConceptPromptPack(final_preview_prompt="old prompt"),
            approved=True,
            approved_at="2026-06-28T00:00:00+00:00",
        ),
        review_patches=[
            ReviewPatch(
                patch_id="patch_001",
                source_turn_id="turn_001",
                phase_created=WorkflowPhase.CONCEPT_REVIEW,
                target_type="subject",
                target_id="subject_robot",
                patch_type="appearance_change",
                instruction="make the subject softer",
            )
        ],
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output=_planner_payload(),
    )

    assert result.ok is True
    assert updated.phase == WorkflowPhase.CONCEPT_GENERATION
    assert updated.concept_bundle is not None
    assert updated.concept_bundle.concept_version == 3
    assert updated.concept_bundle.final_preview_image_id is None
    assert updated.concept_bundle.subject_concept_images == {}
    assert updated.concept_bundle.scene_concept_image_ids == []
    assert updated.concept_bundle.approved is False
