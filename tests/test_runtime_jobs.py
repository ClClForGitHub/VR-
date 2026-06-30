from agent_runtime.runtime_jobs import build_agent_runtime_plan, build_runtime_web_surface
from agent_runtime.runtime_profiles import RuntimeServiceConfig
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    BlenderSceneState,
    CameraSpec,
    ConceptBundle,
    EnvironmentSpec,
    LightingSpec,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    ViewerSceneState,
    WorkflowPhase,
)


def _scene_spec() -> SceneSpec:
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
    )


def test_runtime_plan_marks_hunyuan3d_subject_generation_as_sub_agent_long_job() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(concept_version=1, final_preview_image_id="concept_001", approved=True),
    )

    plan = build_agent_runtime_plan(state)

    subject_job = next(job for job in plan.jobs if job.domain_tool_name == "build_subject_asset")
    assert subject_job.executor == "sub_agent"
    assert subject_job.long_running is True
    assert subject_job.blocks_runtime is True
    assert subject_job.profile_id == "hq_textured_1m_768"
    assert subject_job.tool_arguments["texture"] is True
    assert subject_job.tool_arguments["octree_resolution"] == 768
    assert subject_job.tool_arguments["face_count"] == 1000000
    assert subject_job.job_id in plan.sub_agent_job_ids
    assert subject_job.job_id in plan.long_running_job_ids


def test_runtime_plan_can_use_fast_hunyuan3d_profile_for_smoke_jobs() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(concept_version=1, final_preview_image_id="concept_001", approved=True),
    )

    plan = build_agent_runtime_plan(state, hunyuan3d_profile_id="fast_shape_50k_768")

    subject_job = next(job for job in plan.jobs if job.domain_tool_name == "build_subject_asset")
    assert subject_job.profile_id == "fast_shape_50k_768"
    assert subject_job.tool_arguments["texture"] is False
    assert subject_job.tool_arguments["face_count"] == 50000
    assert subject_job.tool_arguments["num_inference_steps"] == 30


def test_runtime_plan_turns_user_gate_into_waiting_user_job() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        viewer_scene=ViewerSceneState(viewer_scene_id="viewer_scene_001"),
    )

    plan = build_agent_runtime_plan(state)

    assert plan.requires_user is True
    assert plan.blocked is True
    assert plan.jobs[0].kind == "user_gate"
    assert plan.jobs[0].executor == "user"
    assert plan.jobs[0].status == "waiting_user"


def test_runtime_web_surface_reuses_existing_glb_viewer_and_blender_web_urls() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene_001",
            blend_file_artifact_id="blend_artifact_001",
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene_001",
            viewer_scene_path="/tmp/viewer_scene.glb",
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="blend_artifact_001",
                artifact_type=ArtifactType.BLENDER_FILE,
                uri="/tmp/scene.blend",
                mime_type="application/x-blender",
            )
        ],
    )
    config = RuntimeServiceConfig(
        glb_viewer_base_url="http://viewer.local:8092",
        blender_web_http_url="http://blender.local:8300",
        blender_web_https_url="https://blender.local:8301",
    )

    surface = build_runtime_web_surface(
        state,
        service_config=config,
        frontend_status_path="/tmp/frontend_status.json",
        delivery_handoff_path="/tmp/delivery_handoff.json",
    )

    assert surface.glb_viewer_index_url == "http://viewer.local:8092/"
    assert surface.viewer_scene_url == "http://viewer.local:8092/viewer?path=/tmp/viewer_scene.glb"
    assert surface.viewer_asset_url == "http://viewer.local:8092/asset?path=/tmp/viewer_scene.glb"
    assert surface.blender_web_http_url == "http://blender.local:8300"
    assert surface.blender_scene_path == "/tmp/scene.blend"
    assert surface.frontend_status_path == "/tmp/frontend_status.json"
