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
    assert plan.target_height_ratio == 0.50
    assert plan.camera_distance_multiplier < 2.8
    assert plan.camera_ortho_scale_factor < 1.55
    assert plan.camera_direction[2] > 1.0
    assert "grass" in (plan.notes or "")


def test_build_compose_scene_plan_fallback_without_scene_spec() -> None:
    state = AgentProjectState(project_id="project", thread_id="thread", phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION)

    plan = build_compose_scene_plan(state)

    assert plan.subject_id is None
    assert plan.target_region == "front_left"
    assert plan.target_region_normalized == (-0.18, 0.18)
    assert plan.target_height_ratio == 0.42
    assert plan.camera_ortho_scale_factor == 1.55
