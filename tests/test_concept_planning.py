import json

from agent_runtime.concept_planning import apply_concept_prompt_planner_output
from agent_runtime.llm_nodes import run_llm_node
from agent_runtime.state import (
    AgentProjectState,
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
    assert [item.output_type for item in updated.concept_bundle.prompt_pack.image_requirements] == [
        "subject_concept",
        "scene_concept",
        "target_render",
    ]
    assert updated.concept_bundle.approved is False


def test_apply_concept_prompt_planner_output_enforces_scene_spec_subject_boundaries() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SCENE_SPEC_READY,
        scene_spec=_scene_spec_with_procedural_prop(),
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output={
            "final_preview_prompt": "A hero robot on a chessboard with procedural props.",
            "subject_prompts": {
                "subject_robot": "Hero robot concept.",
                "subject_chess_pieces": "Chess piece prop concept.",
            },
            "scene_prompts": ["Chessboard stage with surrounding procedural pieces."],
        },
    )

    assert result.ok is False
    assert result.issues == ["unexpected_subject_concept_prompt:subject_chess_pieces"]
    assert updated == state


def test_apply_concept_prompt_planner_output_records_review_requirements_from_scene_spec() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SCENE_SPEC_READY,
        scene_spec=_scene_spec_with_procedural_prop(),
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output={
            "final_preview_prompt": "A hero robot on a chessboard with procedural props.",
            "subject_prompts": {"subject_robot": "Hero robot concept."},
            "scene_prompts": ["Chessboard stage with surrounding procedural pieces."],
        },
    )

    assert result.ok is True
    assert updated.concept_bundle is not None
    requirements = updated.concept_bundle.prompt_pack.image_requirements
    assert [item.output_type for item in requirements] == ["subject_concept", "scene_concept", "target_render"]
    assert [item.target_id for item in requirements] == ["subject_robot", "scene_robot_board", "scene_robot_board"]
    assert requirements[-1].generation_mode == "multi_image_composite"
    assert requirements[-1].source_requirement_ids == ["subject_concept:subject_robot", "scene_concept:1"]


def test_apply_concept_prompt_planner_output_tracks_subject_reference_inputs() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SCENE_SPEC_READY,
        scene_spec=_scene_spec_with_subject_reference(),
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output={
            "final_preview_prompt": "A high quality image-guided hero robot target render in a studio.",
            "subject_prompts": {
                "subject_robot": "Use input reference image image_robot_ref as the required identity reference for the hero robot."
            },
            "scene_prompts": ["Scene-only clean studio pedestal, no character."],
        },
    )

    assert result.ok is True
    requirements = updated.concept_bundle.prompt_pack.image_requirements
    subject_requirement = requirements[0]
    assert subject_requirement.requirement_id == "subject_concept:subject_robot"
    assert subject_requirement.generation_mode == "image_guided"
    assert subject_requirement.input_reference_image_ids == ["image_robot_ref"]
    assert subject_requirement.must_use_image_inputs is True
    assert requirements[-1].generation_mode == "multi_image_composite"
    assert requirements[-1].source_requirement_ids == ["subject_concept:subject_robot", "scene_concept:1"]


def test_apply_concept_prompt_planner_output_blocks_clarification_output() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SCENE_SPEC_READY,
        scene_spec=_scene_spec_with_subject_reference(),
    )

    result, updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output={
            "final_preview_prompt": "A target render.",
            "subject_prompts": {"subject_robot": "robot"},
            "scene_prompts": ["studio"],
            "requires_clarification": True,
            "open_questions": ["Which character identity should be used?"],
        },
    )

    assert result.ok is False
    assert result.issues == ["planner_requires_clarification:Which character identity should be used?"]
    assert updated == state


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


def _scene_spec_with_procedural_prop() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_robot_board",
        title="Robot Board Scene",
        user_goal="Place one robot on a chessboard with procedural chess pieces.",
        style=StyleSpec(style_keywords=["stylized"]),
        environment=EnvironmentSpec(
            environment_type="chessboard_stage",
            description="A large chessboard surface.",
            background_elements=["many chess pieces"],
        ),
        lighting=LightingSpec(description="Soft studio light."),
        camera={},
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Hero Robot",
                category="character",
                description="A compact hero robot.",
                needs_2d_concept=True,
                needs_3d_asset=True,
                asset_strategy="hunyuan3d_img2asset",
            ),
            SubjectSpec(
                subject_id="subject_chess_pieces",
                display_name="Chess Pieces",
                category="prop",
                description="Many procedural chess pieces surrounding the hero.",
                needs_2d_concept=False,
                needs_3d_asset=False,
                asset_strategy="procedural_blender",
            ),
        ],
    )


def _scene_spec_with_subject_reference() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_robot_ref",
        title="Robot Reference Scene",
        user_goal="Place the referenced robot in a studio.",
        style=StyleSpec(style_keywords=["stylized"]),
        environment=EnvironmentSpec(
            environment_type="studio",
            description="A clean studio pedestal.",
        ),
        lighting=LightingSpec(description="Soft studio light."),
        camera={},
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Hero Robot",
                category="character",
                description="A compact hero robot based on the uploaded reference.",
                reference_image_ids=["image_robot_ref"],
                needs_2d_concept=True,
                needs_3d_asset=True,
                asset_strategy="hunyuan3d_img2asset",
            )
        ],
    )
