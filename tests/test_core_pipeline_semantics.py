import json
from pathlib import Path

from agent_runtime.agent_prompts import ConceptPromptPlannerOutput, concept_prompt_pack_from_planner_output
from agent_runtime.reference_intake import build_reference_intake_result
from agent_runtime.state import EnvironmentSpec, LightingSpec, SceneSpec, StyleSpec, SubjectSpec


def test_round03_core_pipeline_fixture_cases_are_present() -> None:
    fixture_path = Path(__file__).parent / "fixtures/user_journeys/core_pipeline_semantic_cases.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert {case["case_id"] for case in payload["cases"]} == {
        "case_text_only_robot_display",
        "case_reference_bound_subject_and_scene",
        "case_reject_then_reselect_old_concept",
        "case_multi_subject_selection_payload",
        "case_ip_identity_research_placeholder",
    }


def test_reference_bound_subject_and_scene_require_explicit_bindings() -> None:
    result = build_reference_intake_result(
        user_text=(
            "Use image_subject_ref only for the hero robot and image_scene_ref "
            "only for the tabletop scene."
        ),
        input_images=[
            {"image_id": "image_subject_ref", "artifact_id": "artifact_subject_ref", "uri": "/tmp/subject.png"},
            {"image_id": "image_scene_ref", "artifact_id": "artifact_scene_ref", "uri": "/tmp/scene.png"},
        ],
        declared_bindings=[
            {
                "image_id": "image_subject_ref",
                "target_type": "subject",
                "target_id": "subject_robot",
                "usage": "subject_reference",
            },
            {
                "image_id": "image_scene_ref",
                "target_type": "scene",
                "target_id": "scene_robot_tabletop",
                "usage": "scene_reference",
            },
        ],
    )

    assert result.ok is True
    assert [(binding.image_id, binding.target_type, binding.usage) for binding in result.reference_bindings] == [
        ("image_subject_ref", "subject", "subject_reference"),
        ("image_scene_ref", "scene", "scene_reference"),
    ]


def test_scene_spec_to_concept_prompt_pack_keeps_core_requirement_semantics() -> None:
    scene_spec = _reference_bound_scene_spec()
    prompt_pack = concept_prompt_pack_from_planner_output(
        ConceptPromptPlannerOutput(
            final_preview_prompt="A polished target render using the subject concept and scene concept.",
            subject_prompts={"subject_robot": "Subject-only robot concept using image_subject_ref."},
            scene_prompts=["Scene-only tabletop studio using image_scene_ref, no robot."],
        ),
        scene_spec=scene_spec,
    )

    subject_requirement, scene_requirement, target_requirement = prompt_pack.image_requirements

    assert subject_requirement.output_type == "subject_concept"
    assert subject_requirement.target_id == "subject_robot"
    assert subject_requirement.generation_mode == "image_guided"
    assert subject_requirement.input_reference_image_ids == ["image_subject_ref"]

    assert scene_requirement.output_type == "scene_concept"
    assert scene_requirement.target_id == "scene_robot_tabletop"
    assert scene_requirement.generation_mode == "image_guided"
    assert scene_requirement.input_reference_image_ids == ["image_scene_ref"]

    assert target_requirement.output_type == "target_render"
    assert target_requirement.generation_mode == "multi_image_composite"
    assert target_requirement.source_requirement_ids == [
        "subject_concept:subject_robot",
        "scene_concept:1",
    ]


def _reference_bound_scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_robot_tabletop",
        title="Robot Tabletop",
        user_goal="Create a robot on a clean tabletop scene.",
        style=StyleSpec(style_keywords=["clean"]),
        environment=EnvironmentSpec(
            environment_type="tabletop_studio",
            description="Clean tabletop with soft props.",
            scene_reference_image_ids=["image_scene_ref"],
        ),
        lighting=LightingSpec(description="Soft studio light."),
        camera={},
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Hero Robot",
                category="character",
                description="A compact friendly robot.",
                reference_image_ids=["image_subject_ref"],
                needs_2d_concept=True,
                needs_3d_asset=True,
            )
        ],
    )
