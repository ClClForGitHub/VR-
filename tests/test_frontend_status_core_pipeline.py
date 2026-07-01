from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.state import (
    AgentProjectState,
    AssemblySelection,
    AssetLibraryItem,
    ConceptBundle,
    ConceptImageRequirement,
    ConceptPromptPack,
    EnvironmentSpec,
    LightingSpec,
    Scene3DRecord,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_frontend_status_exposes_core_pipeline_requirements_library_selection_and_payloads() -> None:
    state = AgentProjectState(
        project_id="project_round03",
        thread_id="thread_round03",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=2,
            final_preview_image_id="target_render_selected",
            subject_concept_images={"subject_robot": ["concept_selected"]},
            scene_concept_image_ids=["scene_concept_selected"],
            prompt_pack=ConceptPromptPack(
                final_preview_prompt="Target render using subject and scene concepts.",
                subject_prompts={"subject_robot": "Subject-only robot."},
                scene_prompts=["Scene-only display."],
                image_requirements=[
                    ConceptImageRequirement(
                        requirement_id="subject_concept:subject_robot",
                        output_type="subject_concept",
                        target_id="subject_robot",
                        prompt_key="subject_prompts.subject_robot",
                        user_review_label="Subject concept",
                        purpose="subject review",
                    ),
                    ConceptImageRequirement(
                        requirement_id="scene_concept:1",
                        output_type="scene_concept",
                        target_id="scene_robot_display",
                        prompt_key="scene_prompts.0",
                        user_review_label="Scene concept",
                        purpose="scene review",
                    ),
                    ConceptImageRequirement(
                        requirement_id="target_render:final_preview",
                        output_type="target_render",
                        target_id="scene_robot_display",
                        prompt_key="final_preview_prompt",
                        user_review_label="Target render",
                        purpose="composition review",
                        generation_mode="multi_image_composite",
                        source_requirement_ids=["subject_concept:subject_robot", "scene_concept:1"],
                        must_use_image_inputs=True,
                    ),
                ],
            ),
            approved=True,
        ),
        scene_asset=Scene3DRecord(
            scene_asset_id="scene_asset_selected",
            service="hy_world",
            raw_output_type="mesh",
            adapted_artifact_ids=["scene_asset_selected"],
            blender_import_mode="mesh_import",
            status="adapted",
        ),
        asset_library=[
            AssetLibraryItem(
                library_item_id="library_concept_selected",
                artifact_id="concept_selected",
                asset_kind="subject_concept",
                subject_id="subject_robot",
                review_status="rejected",
                selection_status="selected_for_model_generation",
                created_at="2026-07-01T00:00:00+00:00",
                updated_at="2026-07-01T00:00:00+00:00",
            ),
            AssetLibraryItem(
                library_item_id="library_subject_model_selected",
                artifact_id="subject_model_selected",
                asset_kind="subject_model",
                subject_id="subject_robot",
                source_artifact_ids=["concept_selected"],
                selection_status="selected_for_assembly",
                created_at="2026-07-01T00:00:00+00:00",
                updated_at="2026-07-01T00:00:00+00:00",
            ),
            AssetLibraryItem(
                library_item_id="library_scene_concept_selected",
                artifact_id="scene_concept_selected",
                asset_kind="scene_concept",
                scene_id="scene_robot_display",
                selection_status="selected_for_assembly",
                created_at="2026-07-01T00:00:00+00:00",
                updated_at="2026-07-01T00:00:00+00:00",
            ),
            AssetLibraryItem(
                library_item_id="library_target_render_selected",
                artifact_id="target_render_selected",
                asset_kind="target_render",
                scene_id="scene_robot_display",
                selection_status="selected_for_assembly",
                created_at="2026-07-01T00:00:00+00:00",
                updated_at="2026-07-01T00:00:00+00:00",
            ),
        ],
        active_assembly_selection=AssemblySelection(
            selection_id="assembly_selection_round03",
            selected_subject_assets={"subject_robot": "subject_model_selected"},
            selected_scene_asset_id="scene_asset_selected",
            selected_scene_concept_image_id="scene_concept_selected",
            selected_target_render_image_id="target_render_selected",
            updated_at="2026-07-01T00:00:00+00:00",
        ),
    )

    status = build_frontend_status(state=state, summary={"ok": True, "dry_run": False})
    payloads = {item.action_type: item.payload for item in status.available_asset_action_payloads}

    assert status.phase == "BLENDER_ASSEMBLY_EXECUTION"
    assert [item.output_type for item in status.concept_requirements] == [
        "subject_concept",
        "scene_concept",
        "target_render",
    ]
    assert [item.ready_artifact_ids for item in status.concept_requirements] == [
        ["concept_selected"],
        ["scene_concept_selected"],
        ["target_render_selected"],
    ]
    assert status.asset_library[0].review_status == "rejected"
    assert status.asset_library[1].source_artifact_ids == ["concept_selected"]
    assert status.active_assembly_selection.selected_subject_assets == {"subject_robot": "subject_model_selected"}
    assert status.active_assembly_selection.selected_target_render_image_id == "target_render_selected"
    assert set(status.available_asset_actions) == {
        "set_asset_review_status",
        "select_concept_for_subject_generation",
        "select_asset_for_assembly",
    }
    assert payloads["set_asset_review_status"]["artifact_id"] == "concept_selected"
    assert payloads["select_concept_for_subject_generation"]["concept_artifact_id"] == "concept_selected"
    assert payloads["select_asset_for_assembly"]["subject_asset_ids_by_subject"] == {
        "subject_robot": "subject_model_selected"
    }
    assert payloads["select_asset_for_assembly"]["scene_asset_id"] == "scene_asset_selected"
    assert payloads["select_asset_for_assembly"]["target_render_image_id"] == "target_render_selected"


def _scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_robot_display",
        title="Robot Display",
        user_goal="Create a robot display.",
        style=StyleSpec(style_keywords=["clean"]),
        environment=EnvironmentSpec(environment_type="studio", description="Clean display."),
        lighting=LightingSpec(description="Soft light."),
        camera={},
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Hero Robot",
                category="character",
                description="A compact robot.",
            )
        ],
    )
