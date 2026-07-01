from agent_runtime.controller import build_controller_plan
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    Asset3DRecord,
    BlenderAssemblyPlan,
    BlenderObjectRecord,
    BlenderSceneState,
    CameraSpec,
    ConceptBundle,
    EnvironmentSpec,
    InputImage,
    LightingSpec,
    ReferenceBinding,
    ReviewPatch,
    Scene3DRecord,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    ViewerSceneState,
    WorkflowPhase,
)


def _scene_spec(open_questions=None) -> SceneSpec:
    return SceneSpec(
        scene_id="scene_001",
        title="Robot Workshop",
        user_goal="Create a small robot in a workshop.",
        style=StyleSpec(style_keywords=["stylized"]),
        environment=EnvironmentSpec(environment_type="workshop", description="A compact workshop."),
        lighting=LightingSpec(description="Soft studio light."),
        camera=CameraSpec(shot_type="medium wide"),
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="hero robot",
                category="character",
                description="Small friendly robot.",
            )
        ],
        open_questions=open_questions or [],
    )


def _scene_spec_with_procedural_prop() -> SceneSpec:
    spec = _scene_spec()
    spec.subjects.append(
        SubjectSpec(
            subject_id="subject_chess_pieces",
            display_name="Chess Pieces",
            category="prop",
            description="Many procedural chess pieces around the hero.",
            needs_2d_concept=False,
            needs_3d_asset=False,
            asset_strategy="procedural_blender",
        )
    )
    return spec


def test_controller_blocks_intake_when_reference_image_is_unbound() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.INTAKE,
        input_images=[
            InputImage(
                image_id="image_001",
                artifact_id="artifact_image_001",
                uri="/tmp/image.png",
                mime_type="image/png",
            )
        ],
    )

    plan = build_controller_plan(state)

    assert plan.blocked is True
    assert plan.requires_user is True
    assert plan.actions[0].action_type == "ask_user"
    assert "image_missing_binding:image_001" in plan.issues


def test_controller_runs_scene_understanding_after_explicit_binding() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.INTAKE,
        input_images=[
            InputImage(
                image_id="image_001",
                artifact_id="artifact_image_001",
                uri="/tmp/image.png",
                mime_type="image/png",
            )
        ],
        reference_bindings=[
            ReferenceBinding(
                binding_id="binding_001",
                image_id="image_001",
                target_type="subject",
                target_id="subject_robot",
                usage="subject_reference",
            )
        ],
    )

    plan = build_controller_plan(state)

    assert plan.blocked is False
    assert [action.node_name for action in plan.actions] == [
        "ReferenceBindingValidator",
        "SceneInterpreter",
        "SceneSpecCompiler",
    ]


def test_controller_routes_scene_spec_to_concept_generation() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SCENE_SPEC_READY,
        scene_spec=_scene_spec(),
    )

    plan = build_controller_plan(state)

    assert plan.next_phase == WorkflowPhase.CONCEPT_GENERATION
    assert plan.actions[0].node_name == "ConceptPromptPlanner"
    assert plan.actions[1].domain_tool_name == "generate_concept_images"


def test_controller_waits_for_concept_approval_before_subject_generation() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_REVIEW,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="artifact_preview_001",
            approved=False,
        ),
    )

    plan = build_controller_plan(state)

    assert plan.blocked is True
    assert plan.requires_user is True
    assert plan.actions[0].action_type == "await_user_approval"
    assert all(action.domain_tool_name != "build_subject_asset" for action in plan.actions)


def test_controller_runs_subject_generation_after_concept_approval() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="artifact_preview_001",
            approved=True,
        ),
    )

    plan = build_controller_plan(state)

    assert plan.next_phase == WorkflowPhase.SUBJECT_ASSET_GENERATION
    assert [action.domain_tool_name for action in plan.actions] == [
        "build_subject_asset",
        "check_subject_asset_quality",
    ]


def test_controller_subject_generation_ignores_procedural_scene_props() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec_with_procedural_prop(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="artifact_preview_001",
            approved=True,
        ),
    )

    plan = build_controller_plan(state)

    assert plan.next_phase == WorkflowPhase.SUBJECT_ASSET_GENERATION
    assert plan.actions[0].payload["subject_ids"] == ["subject_robot"]


def test_controller_waits_for_blender_preview_approval() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(concept_version=1, approved=True),
        subject_assets=[
            Asset3DRecord(
                asset_id="asset_robot",
                subject_id="subject_robot",
                source_image_id="artifact_preview_001",
                glb_uri="/tmp/robot.glb",
                status="succeeded",
            )
        ],
        blender_scene=BlenderSceneState(blender_scene_id="blend_scene_001"),
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_scene_001"),
    )

    plan = build_controller_plan(state)

    assert plan.blocked is True
    assert plan.requires_user is True
    assert plan.actions[0].action_type == "await_user_approval"
    assert plan.actions[0].payload["viewer_scene_id"] == "viewer_scene_001"


def test_controller_executes_existing_blender_assembly_plan_with_import_scene_asset() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=_scene_spec(),
        blender_assembly_plan=BlenderAssemblyPlan(
            plan_id="assembly_plan_001",
            placement_plans=[{"subject_id": "subject_robot", "target_region": "front_right"}],
        ),
        subject_assets=[
            Asset3DRecord(
                asset_id="asset_robot",
                subject_id="subject_robot",
                source_image_id="artifact_preview_001",
                glb_uri="/tmp/robot.glb",
                status="succeeded",
            )
        ],
        scene_asset=Scene3DRecord(
            scene_asset_id="scene_asset_001",
            service="hy_world",
            raw_output_type="mesh",
            adapted_artifact_ids=["scene_glb_001"],
            blender_import_mode="mesh_import",
            status="adapted",
        ),
    )

    plan = build_controller_plan(state)

    assert plan.next_phase == WorkflowPhase.BLENDER_PREVIEW
    assert [action.node_name for action in plan.actions if action.node_name] == []
    assert plan.actions[0].domain_tool_name == "import_scene_asset"
    assert plan.actions[0].payload == {
        "assembly_plan_id": "assembly_plan_001",
        "scene_asset_id": "scene_asset_001",
        "subject_id": "subject_robot",
        "subject_asset_id": "asset_robot",
    }


def test_controller_schedules_planned_blender_edit_before_preview_refresh() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_EDIT,
        scene_spec=_scene_spec(),
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            objects=[
                BlenderObjectRecord(
                    object_id="hero",
                    blender_name="Hero",
                    subject_id="subject_robot",
                    object_type="subject_asset",
                )
            ],
        ),
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_scene_001"),
        review_patches=[
            ReviewPatch(
                patch_id="patch_move_hero",
                source_turn_id="turn_001",
                phase_created=WorkflowPhase.BLENDER_PREVIEW,
                target_type="blender_object",
                target_id="hero",
                patch_type="move_object",
                instruction="把主体向左移动一点。",
                structured_delta={
                    "blender_edit_plan": {
                        "route": "pure_blender_edit",
                        "reason": "minor placement edit",
                        "domain_tool_calls": [
                            {
                                "domain_tool_name": "move_subject",
                                "arguments": {"blender_object_id": "hero", "location": [-0.4, 0, 0]},
                                "reason": "move_hero_left",
                            }
                        ],
                    }
                },
            )
        ],
    )

    plan = build_controller_plan(state)

    assert plan.next_phase == WorkflowPhase.BLENDER_PREVIEW
    assert [action.domain_tool_name for action in plan.actions] == [
        "move_subject",
        "export_viewer_scene",
        "render_preview",
    ]
    assert all(action.node_name != "BlenderEditRouter" for action in plan.actions)
    assert plan.actions[0].payload == {"blender_object_id": "hero", "location": [-0.4, 0, 0]}


def test_controller_stops_delivery_after_package_artifact_exists(tmp_path) -> None:
    package_zip = tmp_path / "delivery.zip"
    package_zip.write_bytes(b"zip")
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.DELIVERY,
        blender_scene=BlenderSceneState(blender_scene_id="blend_scene_001"),
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_scene_001"),
        artifacts=[
            ArtifactRecord(
                artifact_id="delivery_project_001",
                artifact_type=ArtifactType.EXPORT_PACKAGE,
                uri=str(package_zip),
                mime_type="application/zip",
                metadata={"ok": True},
            )
        ],
    )

    plan = build_controller_plan(state)

    assert plan.blocked is False
    assert plan.requires_user is False
    assert plan.actions == []
