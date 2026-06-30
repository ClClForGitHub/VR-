from agent_runtime.blender_assembly_planner import build_compose_scene_plan
from agent_runtime.state import (
    AgentProjectState,
    CameraSpec,
    EnvironmentSpec,
    LightingSpec,
    SceneSpec,
    SpatialRelation,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_build_compose_scene_plan_uses_scene_spec_hints() -> None:
    state = AgentProjectState(
        project_id="project",
        thread_id="thread",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=SceneSpec(
            scene_id="scene_001",
            title="Toy in flower field",
            user_goal="Place the toy on the right in a close high-angle shot.",
            style=StyleSpec(visual_style="realistic"),
            environment=EnvironmentSpec(
                environment_type="garden",
                description="flower field",
                ground_surface="grass",
            ),
            lighting=LightingSpec(description="soft daylight"),
            camera=CameraSpec(shot_type="close-up", angle="high angle"),
            subjects=[
                SubjectSpec(
                    subject_id="toy_001",
                    display_name="yellow toy",
                    category="character",
                    priority="hero",
                    description="yellow plush toy",
                    scale_hint="large enough to be the hero",
                    placement_hint="right side foreground",
                )
            ],
            spatial_relations=[
                SpatialRelation(
                    relation_id="rel_001",
                    source_subject_id="toy_001",
                    relation="right_of",
                    target_region="foreground",
                )
            ],
        ),
    )

    plan = build_compose_scene_plan(state, scene_asset_id="scene_glb", subject_asset_id="toy_glb")

    assert plan.subject_id == "toy_001"
    assert plan.scene_asset_id == "scene_glb"
    assert plan.subject_asset_id == "toy_glb"
    assert plan.target_region == "front_right"
    assert plan.target_region_normalized[0] > 0
    assert plan.target_region_normalized[1] < 0
    assert plan.target_height_ratio == 0.50
    assert plan.camera_target_normalized[0] > 0
    assert plan.camera_target_normalized[1] < 0
    assert plan.camera_distance_multiplier < 2.8
    assert plan.camera_ortho_scale_factor < 1.55
    assert plan.camera_direction[2] > 1.0
    assert "grass" in (plan.notes or "")


def test_build_compose_scene_plan_combines_back_left_and_wide_camera_hints() -> None:
    state = AgentProjectState(
        project_id="project",
        thread_id="thread",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=SceneSpec(
            scene_id="scene_002",
            title="Garden prop panorama",
            user_goal="Put the sign on the left background in a wide 16:9 landscape view.",
            style=StyleSpec(visual_style="realistic"),
            environment=EnvironmentSpec(environment_type="garden", description="wide garden"),
            lighting=LightingSpec(description="morning light"),
            camera=CameraSpec(shot_type="wide", framing="16:9 landscape full scene"),
            subjects=[
                SubjectSpec(
                    subject_id="sign_001",
                    display_name="wood sign",
                    category="prop",
                    priority="important",
                    description="a small wooden sign",
                    placement_hint="left background",
                )
            ],
            spatial_relations=[
                SpatialRelation(
                    relation_id="rel_001",
                    source_subject_id="sign_001",
                    relation="behind",
                    target_region="left background",
                )
            ],
        ),
    )

    plan = build_compose_scene_plan(state)

    assert plan.target_region == "back_left"
    assert plan.target_region_normalized[0] < 0
    assert plan.target_region_normalized[1] > 0
    assert plan.camera_target_normalized[0] < 0
    assert plan.camera_target_normalized[1] > 0
    assert abs(plan.camera_target_normalized[0]) < abs(plan.target_region_normalized[0])
    assert plan.camera_ortho_scale_factor > 1.55
    assert plan.render_resolution == (1600, 900)


def test_build_compose_scene_plan_uses_portrait_resolution_for_vertical_request() -> None:
    state = AgentProjectState(
        project_id="project",
        thread_id="thread",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=SceneSpec(
            scene_id="scene_003",
            title="Portrait toy preview",
            user_goal="Create a vertical portrait preview for phone review.",
            style=StyleSpec(visual_style="soft"),
            environment=EnvironmentSpec(environment_type="studio", description="simple studio"),
            lighting=LightingSpec(description="softbox"),
            camera=CameraSpec(shot_type="portrait close-up", framing="vertical 9:16"),
            subjects=[
                SubjectSpec(
                    subject_id="toy_001",
                    display_name="toy",
                    category="character",
                    priority="hero",
                    description="a toy",
                    placement_hint="center foreground",
                )
            ],
        ),
    )

    plan = build_compose_scene_plan(state)

    assert plan.target_region == "center"
    assert plan.camera_target_normalized == (0.0, 0.0)
    assert plan.render_resolution == (1080, 1440)


def test_build_compose_scene_plan_fallback_without_scene_spec() -> None:
    state = AgentProjectState(project_id="project", thread_id="thread", phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION)

    plan = build_compose_scene_plan(state)

    assert plan.subject_id is None
    assert plan.target_region == "front_left"
    assert plan.target_region_normalized == (-0.18, 0.18)
    assert plan.target_height_ratio == 0.42
    assert plan.camera_target_normalized == (0.0, 0.0)
    assert plan.camera_ortho_scale_factor == 1.55
    assert plan.render_resolution == (1400, 900)
