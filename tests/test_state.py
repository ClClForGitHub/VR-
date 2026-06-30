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
    LightingSpec,
    PendingAction,
    ReferenceBinding,
    RenderSettings,
    ScaleEstimate,
    Scene3DRecord,
    SceneSpec,
    SpatialRelation,
    StyleSpec,
    SubjectSpec,
    TransformSpec,
    ViewerCameraState,
    ViewerSceneObjectRecord,
    ViewerSceneState,
    VisualQAResult,
    WorkflowPhase,
)


def _dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def test_reference_binding_requires_confidence_between_zero_and_one() -> None:
    with pytest.raises(ValueError):
        ReferenceBinding(
            binding_id="binding_001",
            image_id="image_001",
            target_type="subject",
            usage="subject_reference",
            confidence=1.5,
        )


def test_state_rejects_implicit_reference_bindings_for_v1() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.INTAKE,
        reference_bindings=[
            ReferenceBinding(
                binding_id="binding_001",
                image_id="image_001",
                target_type="subject",
                usage="subject_reference",
                explicit_in_user_text=False,
            )
        ],
    )

    with pytest.raises(ValueError, match="implicit reference bindings"):
        state.assert_reference_bindings_are_explicit()


def test_doc004_core_sources_are_available_on_agent_project_state() -> None:
    scene_spec = SceneSpec(
        scene_id="scene_001",
        title="Workshop Demo",
        user_goal="Create a compact workshop scene with one hero robot and one workbench.",
        style=StyleSpec(style_keywords=["clean", "stylized"], realism_level="stylized"),
        environment=EnvironmentSpec(
            environment_type="indoor workshop",
            description="A small fabrication room with shelves and a workbench.",
        ),
        lighting=LightingSpec(description="Soft overhead light."),
        camera=CameraSpec(shot_type="medium wide shot", angle="eye level"),
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="hero robot",
                category="character",
                description="A small friendly robot with a square body.",
                priority="hero",
            ),
            SubjectSpec(
                subject_id="subject_bench",
                display_name="workbench",
                category="furniture",
                description="A sturdy bench with tools arranged on top.",
                asset_strategy="blender_primitive",
            ),
        ],
        spatial_relations=[
            SpatialRelation(
                relation_id="rel_001",
                source_subject_id="subject_robot",
                relation="near",
                target_subject_id="subject_bench",
            )
        ],
    )
    concept_bundle = ConceptBundle(
        concept_version=1,
        final_preview_image_id="artifact_preview",
        prompt_pack=ConceptPromptPack(
            final_preview_prompt="stylized workshop with hero robot",
            subject_prompts={"subject_robot": "front view robot concept"},
        ),
        visual_qa=VisualQAResult(ok=True, score=0.92),
        approved=True,
    )
    subject_asset = Asset3DRecord(
        asset_id="asset_robot",
        subject_id="subject_robot",
        source_image_id="artifact_robot_concept",
        glb_uri="/tmp/robot.glb",
        status="succeeded",
        quality_score=0.88,
    )
    scene_asset = Scene3DRecord(
        scene_asset_id="scene_asset_001",
        service="hy_world",
        raw_output_type="mesh",
        adapted_artifact_ids=["artifact_scene_glb"],
        blender_import_mode="mesh_import",
        status="adapted",
    )
    blender_scene = BlenderSceneState(
        blender_scene_id="blend_scene_001",
        blend_file_artifact_id="artifact_blend",
        preview_image_id="artifact_preview_png",
        objects=[
            BlenderObjectRecord(
                object_id="object_robot",
                blender_name="Robot",
                subject_id="subject_robot",
                asset_id="asset_robot",
                object_type="subject_asset",
                transform=TransformSpec(location=(1.0, 2.0, 0.0)),
            )
        ],
        render_settings=RenderSettings(engine="cycles", resolution_x=1024, resolution_y=768),
    )
    viewer_scene = ViewerSceneState(
        viewer_scene_id="viewer_scene_001",
        source_blend_version_id="blend_scene_001",
        viewer_scene_artifact_id="artifact_viewer_glb",
        viewer_state_artifact_id="artifact_scene_state",
        objects=[
            ViewerSceneObjectRecord(
                viewer_object_id="Robot",
                blender_object_id="object_robot",
                asset_id="asset_robot",
                display_name="Robot",
                transform=TransformSpec(location=(1.0, 2.0, 0.0)),
            )
        ],
    )

    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        scene_spec=scene_spec,
        concept_bundle=concept_bundle,
        subject_assets=[subject_asset],
        scene_asset=scene_asset,
        blender_scene=blender_scene,
        viewer_scene=viewer_scene,
        pending_action=PendingAction(
            action_id="action_001",
            phase=WorkflowPhase.BLENDER_PREVIEW,
            action_type="blender_preview_review",
            payload={"viewer_scene_id": "viewer_scene_001"},
        ),
    )

    payload = _dump(state)
    assert payload["scene_spec"]["subjects"][0]["subject_id"] == "subject_robot"
    assert payload["concept_bundle"]["visual_qa"]["score"] == 0.92
    assert payload["subject_assets"][0]["glb_uri"] == "/tmp/robot.glb"
    assert payload["scene_asset"]["blender_import_mode"] == "mesh_import"
    assert payload["viewer_scene"]["viewer_scene_artifact_id"] == "artifact_viewer_glb"
    assert payload["pending_action"]["action_type"] == "blender_preview_review"


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: VisualQAResult(ok=False, score=1.2),
            "score must be between 0 and 1",
        ),
        (
            lambda: Asset3DRecord(
                asset_id="asset_001",
                subject_id="subject_001",
                source_image_id="image_001",
                quality_score=-0.1,
            ),
            "quality_score must be between 0 and 1",
        ),
        (
            lambda: ScaleEstimate(
                subject_id="subject_001",
                relative_scale_description="small foreground prop",
                confidence=2.0,
            ),
            "confidence must be between 0 and 1",
        ),
        (
            lambda: SceneSpec(
                scene_id="scene_001",
                title="Invalid version",
                user_goal="demo",
                style=StyleSpec(),
                environment=EnvironmentSpec(environment_type="studio", description="demo"),
                lighting=LightingSpec(),
                camera=CameraSpec(),
                version=0,
            ),
            "version must be positive",
        ),
    ],
)
def test_doc004_state_validators_reject_out_of_range_values(factory, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_viewer_scene_state_accepts_existing_exporter_snapshot_shape() -> None:
    viewer_scene = ViewerSceneState(
        viewer_scene_id="viewer_scene",
        source_blend_version_id="composed_scene",
        viewer_scene_artifact_id="smoke_viewer_scene_glb",
        viewer_state_artifact_id="smoke_scene_state_json",
        objects=[
            {
                "viewer_object_id": "Robot",
                "subject_id": None,
                "blender_object_id": "Robot",
                "asset_id": None,
                "display_name": "Robot",
                "selectable": True,
                "highlighted": False,
                "object_type": "MESH",
                "transform": {
                    "location": [1.0, 2.0, 0.0],
                    "rotation_euler": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
                "bounds": {
                    "min": [0.5, 1.5, -0.2],
                    "max": [1.5, 2.5, 1.8],
                },
            }
        ],
        camera={
            "name": "Preview_Camera",
            "type": "PERSP",
            "transform": {
                "location": [3.0, -5.0, 3.0],
                "rotation_euler": [1.0, 0.0, 0.5],
                "scale": [1.0, 1.0, 1.0],
            },
            "focal_length": 35.0,
            "ortho_scale": 6.0,
            "clip_start": 0.1,
            "clip_end": 1000.0,
        },
        active_object_id="Robot",
        source_blend_path="/tmp/composed_scene.blend",
        viewer_scene_path="/tmp/viewer_scene.glb",
    )

    assert viewer_scene.objects[0].transform.location == (1.0, 2.0, 0.0)
    assert viewer_scene.objects[0].bounds is not None
    assert viewer_scene.objects[0].bounds.min == (0.5, 1.5, -0.2)
    assert isinstance(viewer_scene.camera, ViewerCameraState)
    assert viewer_scene.camera.transform is not None
    assert viewer_scene.camera.transform.location == (3.0, -5.0, 3.0)
