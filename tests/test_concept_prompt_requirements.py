from agent_runtime.concept_planning import apply_concept_prompt_planner_output
from agent_runtime.state import AgentProjectState, EnvironmentSpec, LightingSpec, SceneSpec, StyleSpec, SubjectSpec, WorkflowPhase


def test_text_only_robot_display_creates_subject_scene_and_target_requirements() -> None:
    result, updated = apply_concept_prompt_planner_output(
        state=AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.SCENE_SPEC_READY,
            scene_spec=_robot_scene_spec(),
        ),
        planner_output={
            "final_preview_prompt": "Final render of the robot on the clean display.",
            "subject_prompts": {"subject_robot": "Subject-only full-body robot on neutral background."},
            "scene_prompts": ["Scene-only clean studio display, no robot."],
        },
    )

    assert result.ok is True
    requirements = updated.concept_bundle.prompt_pack.image_requirements
    assert [item.output_type for item in requirements] == ["subject_concept", "scene_concept", "target_render"]
    assert requirements[-1].generation_mode == "multi_image_composite"
    assert requirements[-1].source_requirement_ids == ["subject_concept:subject_robot", "scene_concept:1"]


def test_reference_bound_subject_and_scene_requirements_do_not_cross_contaminate() -> None:
    result, updated = apply_concept_prompt_planner_output(
        state=AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.SCENE_SPEC_READY,
            scene_spec=_robot_scene_spec(subject_ref=True, scene_ref=True),
        ),
        planner_output={
            "final_preview_prompt": "Final render using both generated concepts.",
            "subject_prompts": {"subject_robot": "Use image_subject_ref for robot identity only."},
            "scene_prompts": ["Use image_scene_ref for the tabletop scene only, no robot."],
        },
    )

    assert result.ok is True
    requirements = updated.concept_bundle.prompt_pack.image_requirements
    subject_requirement = requirements[0]
    scene_requirement = requirements[1]
    assert subject_requirement.generation_mode == "image_guided"
    assert subject_requirement.input_reference_image_ids == ["image_subject_ref"]
    assert "image_scene_ref" not in subject_requirement.input_reference_image_ids
    assert scene_requirement.generation_mode == "image_guided"
    assert scene_requirement.input_reference_image_ids == ["image_scene_ref"]
    assert "image_subject_ref" not in scene_requirement.input_reference_image_ids


def test_scene_reference_requirement_is_validated_even_when_planner_supplies_requirements() -> None:
    state = AgentProjectState(
        project_id="project_round03",
        thread_id="thread_round03",
        phase=WorkflowPhase.SCENE_SPEC_READY,
        scene_spec=_robot_scene_spec(scene_ref=True),
    )

    result, _updated = apply_concept_prompt_planner_output(
        state=state,
        planner_output={
            "final_preview_prompt": "Final render.",
            "subject_prompts": {"subject_robot": "Robot."},
            "scene_prompts": ["Scene."],
            "image_requirements": [
                {
                    "requirement_id": "subject_concept:subject_robot",
                    "output_type": "subject_concept",
                    "target_id": "subject_robot",
                    "prompt_key": "subject_prompts.subject_robot",
                    "user_review_label": "Robot",
                    "purpose": "subject review",
                },
                {
                    "requirement_id": "scene_concept:1",
                    "output_type": "scene_concept",
                    "target_id": "scene_robot_display",
                    "prompt_key": "scene_prompts.0",
                    "user_review_label": "Scene",
                    "purpose": "scene review",
                    "generation_mode": "text_to_image",
                },
                {
                    "requirement_id": "target_render:final_preview",
                    "output_type": "target_render",
                    "target_id": "scene_robot_display",
                    "prompt_key": "final_preview_prompt",
                    "user_review_label": "Target",
                    "purpose": "composition review",
                },
            ],
        },
    )

    assert result.ok is True


def test_procedural_props_are_not_treated_as_model_subjects() -> None:
    result, _updated = apply_concept_prompt_planner_output(
        state=AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.SCENE_SPEC_READY,
            scene_spec=_robot_scene_spec(with_procedural_prop=True),
        ),
        planner_output={
            "final_preview_prompt": "Robot surrounded by procedural props.",
            "subject_prompts": {
                "subject_robot": "Robot only.",
                "subject_display_blocks": "Display blocks prop concept.",
            },
            "scene_prompts": ["Scene with display blocks as procedural props."],
        },
    )

    assert result.ok is False
    assert result.issues == ["unexpected_subject_concept_prompt:subject_display_blocks"]


def test_named_identity_requires_evidence_or_clarification() -> None:
    result, _updated = apply_concept_prompt_planner_output(
        state=AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.SCENE_SPEC_READY,
            scene_spec=_identity_scene_spec(),
        ),
        planner_output={
            "final_preview_prompt": "Named character in a clean display scene.",
            "subject_prompts": {"subject_named_character": "A chibi named character."},
            "scene_prompts": ["Clean themed scene."],
        },
    )

    assert result.ok is False
    assert "missing_identity_research_evidence:subject_named_character" in result.issues


def test_named_identity_rejects_notes_without_search_evidence() -> None:
    result, _updated = apply_concept_prompt_planner_output(
        state=AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.SCENE_SPEC_READY,
            scene_spec=_identity_scene_spec(),
        ),
        planner_output={
            "final_preview_prompt": "Named character in a clean display scene.",
            "subject_prompts": {"subject_named_character": "A chibi named character with verified outfit."},
            "scene_prompts": ["Clean themed scene."],
            "identity_notes": ["Verified subject_named_character as Example Game Character from official source."],
        },
    )

    assert result.ok is False
    assert "missing_identity_research_evidence:subject_named_character" in result.issues


def test_named_identity_accepts_structured_search_evidence() -> None:
    result, _updated = apply_concept_prompt_planner_output(
        state=AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.SCENE_SPEC_READY,
            scene_spec=_identity_scene_spec(),
        ),
        planner_output={
            "final_preview_prompt": "Named character in a clean display scene.",
            "subject_prompts": {"subject_named_character": "A chibi named character with verified green hair, red coat, and gold hair ornament."},
            "scene_prompts": ["Clean themed scene."],
            "identity_notes": ["subject_named_character verified from official and wiki sources."],
            "identity_search_evidence": [
                {
                    "subject_id": "subject_named_character",
                    "requested_name": "Example Game Character",
                    "resolved_identity": "Example Game Character",
                    "source_urls": ["https://example.com/official-character"],
                    "search_queries": ["Example Game Character official appearance"],
                    "visual_traits": [
                        "green hair with long side locks",
                        "red coat with gold trim",
                        "black gloves and boots",
                    ],
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert result.ok is True


def _robot_scene_spec(*, subject_ref: bool = False, scene_ref: bool = False, with_procedural_prop: bool = False) -> SceneSpec:
    subjects = [
        SubjectSpec(
            subject_id="subject_robot",
            display_name="Hero Robot",
            category="character",
            description="A compact friendly robot.",
            reference_image_ids=["image_subject_ref"] if subject_ref else [],
            needs_2d_concept=True,
            needs_3d_asset=True,
        )
    ]
    if with_procedural_prop:
        subjects.append(
            SubjectSpec(
                subject_id="subject_display_blocks",
                display_name="Display Blocks",
                category="prop",
                description="Procedural blocks around the robot.",
                needs_2d_concept=False,
                needs_3d_asset=False,
                asset_strategy="procedural_blender",
            )
        )
    return SceneSpec(
        scene_id="scene_robot_display",
        title="Robot Display",
        user_goal="Create a robot display.",
        style=StyleSpec(style_keywords=["clean"]),
        environment=EnvironmentSpec(
            environment_type="studio",
            description="Clean display studio.",
            scene_reference_image_ids=["image_scene_ref"] if scene_ref else [],
        ),
        lighting=LightingSpec(description="Soft light."),
        camera={},
        subjects=subjects,
    )


def _identity_scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_identity",
        title="Named Character Display",
        user_goal="Create a chibi named game character in a themed scene.",
        style=StyleSpec(style_keywords=["chibi"]),
        environment=EnvironmentSpec(environment_type="themed_studio", description="Clean themed scene."),
        lighting=LightingSpec(description="Soft light."),
        camera={},
        subjects=[
            SubjectSpec(
                subject_id="subject_named_character",
                display_name="Example Game Character",
                canonical_identity="Example Game Character",
                identity_aliases=["EGC"],
                identity_confidence=0.8,
                category="character",
                description="A named IP/game character placeholder.",
            )
        ],
    )
