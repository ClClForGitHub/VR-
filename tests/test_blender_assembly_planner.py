from agent_runtime.blender_assembly_planner import build_compose_scene_plan, build_compose_scene_plan_from_blender_assembly_plan
from agent_runtime.state import (
    AgentProjectState,
    BlenderAssemblyPlan,
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
    assert plan.subject_yaw_degrees == 0.0
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


def test_build_compose_scene_plan_infers_subject_orientation_toward_center() -> None:
    state = AgentProjectState(
        project_id="project",
        thread_id="thread",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=SceneSpec(
            scene_id="scene_004",
            title="Robot display",
            user_goal="把机器人放到右前方，并让它朝向中心。",
            style=StyleSpec(visual_style="stylized"),
            environment=EnvironmentSpec(environment_type="studio", description="display room"),
            lighting=LightingSpec(description="soft studio light"),
            camera=CameraSpec(shot_type="medium"),
            subjects=[
                SubjectSpec(
                    subject_id="robot_001",
                    display_name="robot",
                    category="character",
                    priority="hero",
                    description="a small robot",
                    pose_or_state="朝向中心",
                    placement_hint="right foreground",
                )
            ],
        ),
    )

    plan = build_compose_scene_plan(state)

    assert plan.target_region == "front_right"
    assert plan.subject_yaw_degrees == 90.0
    assert "scene center" in plan.orientation_reason


def test_build_compose_scene_plan_keeps_placement_when_orientation_mentions_center() -> None:
    state = AgentProjectState(
        project_id="project",
        thread_id="thread",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=SceneSpec(
            scene_id="scene_004b",
            title="Right foreground orientation",
            user_goal="Place the plush on the right foreground and make it face the scene center.",
            style=StyleSpec(visual_style="realistic"),
            environment=EnvironmentSpec(environment_type="garden", description="flower field", ground_surface="grass"),
            lighting=LightingSpec(description="soft daylight"),
            camera=CameraSpec(shot_type="close-up", angle="high angle"),
            subjects=[
                SubjectSpec(
                    subject_id="plush_001",
                    display_name="plush",
                    category="character",
                    priority="hero",
                    description="a plush character",
                    pose_or_state="facing the scene center",
                    placement_hint="right side foreground on the grass, facing center",
                    scale_hint="large hero",
                )
            ],
            spatial_relations=[
                SpatialRelation(
                    relation_id="rel_001",
                    source_subject_id="plush_001",
                    relation="right_of",
                    target_region="foreground grass area",
                    notes="Use right foreground composition and orient the subject toward the scene center.",
                )
            ],
        ),
    )

    plan = build_compose_scene_plan(state)

    assert plan.target_region == "front_right"
    assert plan.target_region_normalized == (0.24, -0.24)
    assert plan.subject_yaw_degrees == 90.0


def test_blender_assembly_plan_bridge_prefers_transform_hint_yaw() -> None:
    state = AgentProjectState(
        project_id="project",
        thread_id="thread",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=SceneSpec(
            scene_id="scene_005",
            title="Robot bridge",
            user_goal="Put the robot on the left.",
            style=StyleSpec(visual_style="stylized"),
            environment=EnvironmentSpec(environment_type="studio", description="display room"),
            lighting=LightingSpec(description="soft studio light"),
            camera=CameraSpec(shot_type="medium"),
            subjects=[
                SubjectSpec(
                    subject_id="robot_001",
                    display_name="robot",
                    category="character",
                    priority="hero",
                    description="a robot",
                    placement_hint="left foreground",
                )
            ],
        ),
    )
    assembly_plan = BlenderAssemblyPlan(
        plan_id="assembly_plan_001",
        placement_plans=[
            {
                "subject_id": "robot_001",
                "target_region": "front_left",
                "composition_notes": "Even if the text says facing right, use the explicit transform.",
                "transform_hint": {"rotation_euler": (0.0, 0.0, -35.0)},
            }
        ],
    )

    plan = build_compose_scene_plan_from_blender_assembly_plan(state, assembly_plan)

    assert plan.planner == "llm_bridge_v1"
    assert plan.subject_yaw_degrees == -35.0
    assert "transform_hint.rotation_euler.z" in plan.orientation_reason


def test_build_compose_scene_plan_fallback_without_scene_spec() -> None:
    state = AgentProjectState(project_id="project", thread_id="thread", phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION)

    plan = build_compose_scene_plan(state)

    assert plan.subject_id is None
    assert plan.target_region == "front_left"
    assert plan.target_region_normalized == (-0.18, 0.18)
    assert plan.target_height_ratio == 0.42
    assert plan.subject_yaw_degrees == 0.0
    assert plan.camera_target_normalized == (0.0, 0.0)
    assert plan.camera_ortho_scale_factor == 1.55
    assert plan.render_resolution == (1400, 900)
