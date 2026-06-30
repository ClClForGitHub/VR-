import pytest

from agent_runtime.state import (
    AgentProjectState,
    Asset3DRecord,
    BlenderObjectRecord,
    BlenderSceneState,
    CameraSpec,
    ConceptBundle,
    ConceptPromptPack,
    EnvironmentSpec,
    InputImage,
    LightingSpec,
    ReferenceBinding,
    ReviewPatch,
    Scene3DRecord,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    TransformSpec,
    UserTurn,
    ViewerSceneState,
    VisualQAResult,
    WorkflowPhase,
)
from agent_runtime.state_views import (
    MissingStateContextError,
    StateMutationError,
    allowed_state_fields_for_node,
    apply_state_updates,
    assert_state_update_allowed,
    build_blender_assembly_planner_context,
    build_blender_edit_router_context,
    build_concept_prompt_planner_context,
    build_scene_interpreter_context,
    controlled_state_fields,
)


def _scene_spec(scene_id: str = "scene_001") -> SceneSpec:
    return SceneSpec(
        scene_id=scene_id,
        title="Workshop Demo",
        user_goal="Create a workshop scene with one robot.",
        style=StyleSpec(style_keywords=["clean", "stylized"]),
        environment=EnvironmentSpec(
            environment_type="indoor workshop",
            description="A small room with a workbench.",
        ),
        lighting=LightingSpec(description="soft overhead light"),
        camera=CameraSpec(shot_type="medium wide shot"),
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="hero robot",
                category="character",
                description="A small friendly robot.",
            )
        ],
    )


def _base_state() -> AgentProjectState:
    return AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_EDIT,
        user_turns=[
            UserTurn(
                turn_id="turn_001",
                text="use the first image as the robot",
                image_ids=["image_001"],
                phase_at_turn=WorkflowPhase.INTAKE,
                created_at="2026-06-27T00:00:00+00:00",
            ),
            UserTurn(
                turn_id="turn_002",
                text="move the robot closer to the bench",
                image_ids=[],
                phase_at_turn=WorkflowPhase.BLENDER_EDIT,
                created_at="2026-06-27T00:05:00+00:00",
            ),
        ],
        input_images=[
            InputImage(
                image_id="image_001",
                artifact_id="artifact_image_001",
                uri="/tmp/image_001.png",
                mime_type="image/png",
            ),
            InputImage(
                image_id="image_002",
                artifact_id="artifact_image_002",
                uri="/tmp/image_002.png",
                mime_type="image/png",
            ),
        ],
        reference_bindings=[
            ReferenceBinding(
                binding_id="binding_001",
                image_id="image_001",
                target_type="subject",
                target_id="subject_robot",
                usage="subject_reference",
            ),
            ReferenceBinding(
                binding_id="binding_002",
                image_id="image_002",
                target_type="style",
                usage="style_reference",
            ),
        ],
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=2,
            final_preview_image_id="artifact_preview_concept",
            subject_concept_images={"subject_robot": ["artifact_robot_concept"]},
            scene_concept_image_ids=["artifact_scene_concept"],
            prompt_pack=ConceptPromptPack(
                final_preview_prompt="stylized workshop with a hero robot",
                subject_prompts={"subject_robot": "front view of robot"},
                scene_prompts=["small workshop background"],
                negative_prompt="low quality",
            ),
            visual_qa=VisualQAResult(ok=True, score=0.91),
            approved=True,
        ),
        review_patches=[
            ReviewPatch(
                patch_id="patch_pending",
                source_turn_id="turn_002",
                phase_created=WorkflowPhase.CONCEPT_REVIEW,
                target_type="subject",
                target_id="subject_robot",
                patch_type="appearance_change",
                instruction="make the robot more compact",
            ),
            ReviewPatch(
                patch_id="patch_applied",
                source_turn_id="turn_001",
                phase_created=WorkflowPhase.CONCEPT_REVIEW,
                target_type="camera",
                patch_type="camera_change",
                instruction="use a wider shot",
                status="applied",
            ),
        ],
        subject_assets=[
            Asset3DRecord(
                asset_id="asset_robot",
                subject_id="subject_robot",
                source_image_id="artifact_robot_concept",
                glb_uri="/tmp/robot.glb",
                status="succeeded",
            )
        ],
        scene_asset=Scene3DRecord(
            scene_asset_id="scene_asset_001",
            service="hy_world",
            raw_output_type="mesh",
            blender_import_mode="mesh_import",
            status="adapted",
        ),
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            preview_image_id="artifact_blender_preview",
            objects=[
                BlenderObjectRecord(
                    object_id="object_robot",
                    blender_name="Robot",
                    subject_id="subject_robot",
                    transform=TransformSpec(location=(1.0, 0.0, 0.0)),
                )
            ],
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene_001",
            source_blend_version_id="blend_scene_001",
        ),
    )


def test_scene_interpreter_context_uses_selected_turn_images_and_bindings() -> None:
    state = _base_state()

    context = build_scene_interpreter_context(state, turn_id="turn_001")

    assert context.user_text == "use the first image as the robot"
    assert [image.image_id for image in context.input_images] == ["image_001"]
    assert [binding.binding_id for binding in context.declared_bindings] == ["binding_001"]


def test_scene_interpreter_context_accepts_direct_user_text() -> None:
    state = _base_state()

    context = build_scene_interpreter_context(state, user_text="make a tiny robot")

    assert context.user_text == "make a tiny robot"
    assert [image.image_id for image in context.input_images] == ["image_001", "image_002"]
    assert [binding.binding_id for binding in context.declared_bindings] == [
        "binding_001",
        "binding_002",
    ]


def test_concept_prompt_planner_context_keeps_pending_patches_only() -> None:
    context = build_concept_prompt_planner_context(_base_state())

    assert context.scene_spec.scene_id == "scene_001"
    assert [patch.patch_id for patch in context.active_review_patches] == ["patch_pending"]
    assert context.prior_prompt_pack_summary is not None
    assert "subject_prompt_count=1" in context.prior_prompt_pack_summary


def test_blender_assembly_context_exposes_execution_tools_and_latest_ids() -> None:
    context = build_blender_assembly_planner_context(_base_state())

    assert context.subject_assets[0].asset_id == "asset_robot"
    assert context.scene_asset is not None
    assert context.latest_preview_image_id == "artifact_blender_preview"
    assert context.latest_viewer_scene_id == "viewer_scene_001"
    assert "import_scene_asset" in context.allowed_domain_tools
    assert "export_viewer_scene" in context.allowed_domain_tools
    assert context.concept_bundle_summary is not None
    assert "visual_qa_ok=True" in context.concept_bundle_summary


def test_blender_edit_router_context_requires_scene_and_blender_state() -> None:
    state = _base_state()

    context = build_blender_edit_router_context(state, turn_id="turn_002")

    assert context.user_edit_text == "move the robot closer to the bench"
    assert context.blender_scene.blender_scene_id == "blend_scene_001"
    assert context.latest_preview_image_id == "artifact_blender_preview"
    assert "move_subject" in context.allowed_edit_tools

    missing_blender = apply_state_updates(
        state,
        node_name="BlenderCommandExecutor",
        updates={"blender_scene": None},
    )
    with pytest.raises(MissingStateContextError, match="state.blender_scene"):
        build_blender_edit_router_context(missing_blender, user_edit_text="move it")


def test_state_mutation_guard_allows_only_doc004_field_owners() -> None:
    assert "scene_spec" in controlled_state_fields()
    assert "scene_spec" in allowed_state_fields_for_node("SceneSpecCompiler")

    assert_state_update_allowed("SceneSpecCompiler", "scene_spec")
    with pytest.raises(StateMutationError, match="ConceptPromptPlanner is not allowed"):
        assert_state_update_allowed("ConceptPromptPlanner", "scene_spec")

    with pytest.raises(KeyError, match="unknown AgentProjectState field"):
        assert_state_update_allowed("SceneSpecCompiler", "not_a_state_field")


def test_apply_state_updates_returns_validated_copy_after_guard() -> None:
    state = _base_state()
    next_scene = _scene_spec(scene_id="scene_002")

    updated = apply_state_updates(
        state,
        node_name="SceneSpecCompiler",
        updates={"scene_spec": next_scene},
    )

    assert updated.scene_spec is not None
    assert updated.scene_spec.scene_id == "scene_002"
    assert state.scene_spec is not None
    assert state.scene_spec.scene_id == "scene_001"

    with pytest.raises(StateMutationError):
        apply_state_updates(
            state,
            node_name="ScenePreviewExporter",
            updates={"scene_spec": next_scene},
        )
