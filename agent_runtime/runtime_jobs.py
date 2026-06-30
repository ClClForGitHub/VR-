"""Agent runtime planning contracts.

This module converts the deterministic controller plan into runtime job specs
that can be executed by the main runtime, a background worker, a sub-agent, or a
user gate. It deliberately does not execute the jobs.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.controller import ControllerAction, ControllerPlan, build_controller_plan
from agent_runtime.runtime_profiles import (
    RuntimeExecutor,
    RuntimeServiceConfig,
    get_hunyuan3d_profile,
)
from agent_runtime.state import AgentProjectState, ArtifactType, WorkflowPhase
from agent_runtime.viewer import build_viewer_urls


RuntimeJobStatus = Literal["planned", "ready", "waiting_user", "blocked"]
RuntimeJobKind = Literal["llm_node", "domain_tool", "user_gate", "delivery", "stop"]


class RuntimeWebSurface(BaseModel):
    """Existing web surfaces the UI/runtime can point at."""

    glb_viewer_base_url: str
    glb_viewer_index_url: str
    viewer_scene_path: str | None = None
    viewer_scene_url: str | None = None
    viewer_asset_url: str | None = None
    blender_web_http_url: str
    blender_web_https_url: str
    blender_scene_path: str | None = None
    blend_file_artifact_id: str | None = None
    frontend_status_path: str | None = None
    delivery_handoff_path: str | None = None


class RuntimeJobSpec(BaseModel):
    job_id: str
    kind: RuntimeJobKind
    phase: WorkflowPhase
    reason: str
    executor: RuntimeExecutor
    status: RuntimeJobStatus = "planned"
    node_name: str | None = None
    domain_tool_name: str | None = None
    long_running: bool = False
    blocks_runtime: bool = False
    user_visible: bool = False
    profile_id: str | None = None
    timeout_seconds: float | None = None
    dependencies: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    command_hint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimePlan(BaseModel):
    project_id: str
    thread_id: str
    phase: WorkflowPhase
    controller: ControllerPlan
    jobs: list[RuntimeJobSpec] = Field(default_factory=list)
    web_surface: RuntimeWebSurface
    requires_user: bool = False
    blocked: bool = False
    long_running_job_ids: list[str] = Field(default_factory=list)
    sub_agent_job_ids: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


def build_agent_runtime_plan(
    state: AgentProjectState,
    *,
    controller: ControllerPlan | None = None,
    service_config: RuntimeServiceConfig | None = None,
    hunyuan3d_profile_id: str | None = None,
    prefer_sub_agents_for_long_jobs: bool = True,
    frontend_status_path: str | None = None,
    delivery_handoff_path: str | None = None,
) -> AgentRuntimePlan:
    """Build a non-executing runtime plan from the current project state."""

    config = service_config or RuntimeServiceConfig()
    controller_plan = controller or build_controller_plan(state)
    jobs = [
        _job_from_action(
            index=index,
            action=action,
            hunyuan3d_profile_id=hunyuan3d_profile_id or config.default_hunyuan3d_profile_id,
            prefer_sub_agents_for_long_jobs=prefer_sub_agents_for_long_jobs,
        )
        for index, action in enumerate(controller_plan.actions)
    ]
    long_running = [job.job_id for job in jobs if job.long_running]
    sub_agent = [job.job_id for job in jobs if job.executor == "sub_agent"]
    return AgentRuntimePlan(
        project_id=state.project_id,
        thread_id=state.thread_id,
        phase=state.phase,
        controller=controller_plan,
        jobs=jobs,
        web_surface=build_runtime_web_surface(
            state,
            service_config=config,
            frontend_status_path=frontend_status_path,
            delivery_handoff_path=delivery_handoff_path,
        ),
        requires_user=controller_plan.requires_user,
        blocked=controller_plan.blocked,
        long_running_job_ids=long_running,
        sub_agent_job_ids=sub_agent,
        issues=list(controller_plan.issues),
    )


def build_runtime_web_surface(
    state: AgentProjectState,
    *,
    service_config: RuntimeServiceConfig | None = None,
    frontend_status_path: str | None = None,
    delivery_handoff_path: str | None = None,
) -> RuntimeWebSurface:
    config = service_config or RuntimeServiceConfig()
    viewer_scene_path = state.viewer_scene.viewer_scene_path if state.viewer_scene is not None else None
    viewer_scene_url = None
    viewer_asset_url = None
    if viewer_scene_path:
        urls = build_viewer_urls(viewer_scene_path, base_url=config.glb_viewer_base_url)
        viewer_scene_url = urls.viewer_url
        viewer_asset_url = urls.asset_url
    blend_artifact_id = state.blender_scene.blend_file_artifact_id if state.blender_scene is not None else None
    return RuntimeWebSurface(
        glb_viewer_base_url=config.glb_viewer_base_url,
        glb_viewer_index_url=f"{config.glb_viewer_base_url.rstrip('/')}/",
        viewer_scene_path=viewer_scene_path,
        viewer_scene_url=viewer_scene_url,
        viewer_asset_url=viewer_asset_url,
        blender_web_http_url=config.blender_web_http_url,
        blender_web_https_url=config.blender_web_https_url,
        blender_scene_path=_blend_file_path(state, blend_artifact_id),
        blend_file_artifact_id=blend_artifact_id,
        frontend_status_path=frontend_status_path,
        delivery_handoff_path=delivery_handoff_path,
    )


def _job_from_action(
    *,
    index: int,
    action: ControllerAction,
    hunyuan3d_profile_id: str,
    prefer_sub_agents_for_long_jobs: bool,
) -> RuntimeJobSpec:
    if action.action_type in {"ask_user", "await_user_approval"}:
        return RuntimeJobSpec(
            job_id=_job_id(index, action, "user_gate"),
            kind="user_gate",
            phase=action.phase,
            reason=action.reason,
            executor="user",
            status="waiting_user",
            blocks_runtime=True,
            user_visible=True,
            required_outputs=list(action.required_outputs),
            metadata={"payload": action.payload},
        )
    if action.action_type == "run_node":
        return RuntimeJobSpec(
            job_id=_job_id(index, action, action.node_name or "node"),
            kind="llm_node",
            phase=action.phase,
            reason=action.reason,
            executor="main_runtime",
            status="ready",
            node_name=action.node_name,
            required_outputs=list(action.required_outputs),
            metadata={"allowed_domain_tools": action.allowed_domain_tools, "payload": action.payload},
        )
    if action.action_type == "run_domain_tool":
        return _domain_tool_job(
            index=index,
            action=action,
            hunyuan3d_profile_id=hunyuan3d_profile_id,
            prefer_sub_agents_for_long_jobs=prefer_sub_agents_for_long_jobs,
        )
    if action.action_type == "deliver":
        return RuntimeJobSpec(
            job_id=_job_id(index, action, "delivery"),
            kind="delivery",
            phase=action.phase,
            reason=action.reason,
            executor="main_runtime",
            status="ready",
            required_outputs=list(action.required_outputs),
            metadata={"payload": action.payload},
        )
    return RuntimeJobSpec(
        job_id=_job_id(index, action, "stop"),
        kind="stop",
        phase=action.phase,
        reason=action.reason,
        executor="main_runtime",
        status="blocked",
        blocks_runtime=True,
        metadata={"payload": action.payload},
    )


def _domain_tool_job(
    *,
    index: int,
    action: ControllerAction,
    hunyuan3d_profile_id: str,
    prefer_sub_agents_for_long_jobs: bool,
) -> RuntimeJobSpec:
    tool = action.domain_tool_name or "domain_tool"
    long_running_tools = {"build_subject_asset", "build_scene_asset", "generate_concept_images", "regenerate_concept_images"}
    executor: RuntimeExecutor = "background_worker"
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = {"payload": action.payload}
    tool_arguments = dict(action.payload)
    profile_id = None

    if tool == "build_subject_asset":
        profile = get_hunyuan3d_profile(hunyuan3d_profile_id)
        profile_id = profile.profile_id
        tool_arguments = {**profile.payload_kwargs(), **tool_arguments}
        metadata["hunyuan3d_profile"] = _model_to_dict(profile)
        timeout_seconds = 600 if profile.duration_class == "long" else 300
        executor = profile.suggested_executor
        if prefer_sub_agents_for_long_jobs and profile.duration_class in {"medium", "long"}:
            executor = "sub_agent"
    elif tool == "build_scene_asset":
        executor = "sub_agent" if prefer_sub_agents_for_long_jobs else "background_worker"
        timeout_seconds = 1200
    elif tool in {"generate_concept_images", "regenerate_concept_images"}:
        executor = "sub_agent" if prefer_sub_agents_for_long_jobs else "background_worker"
        timeout_seconds = 600
    elif tool in {"check_subject_asset_quality", "approve_concept", "parse_review_patch"}:
        executor = "main_runtime"
        timeout_seconds = 120
    elif tool in {
        "get_blender_scene_summary",
        "move_subject",
        "rotate_subject",
        "scale_subject",
        "delete_subject",
        "replace_subject_asset",
        "update_camera",
        "update_lighting",
        "set_simple_material",
    }:
        executor = "main_runtime"
        timeout_seconds = 120
    elif tool in {"export_viewer_scene", "render_preview", "import_subject_asset", "import_scene_asset"}:
        executor = "background_worker"
        timeout_seconds = 300

    long_running = tool in long_running_tools
    return RuntimeJobSpec(
        job_id=_job_id(index, action, tool),
        kind="domain_tool",
        phase=action.phase,
        reason=action.reason,
        executor=executor,
        status="ready",
        domain_tool_name=tool,
        long_running=long_running,
        blocks_runtime=long_running,
        user_visible=tool in {"generate_concept_images", "regenerate_concept_images", "build_subject_asset", "build_scene_asset"},
        profile_id=profile_id,
        timeout_seconds=timeout_seconds,
        required_outputs=list(action.required_outputs),
        tool_arguments=tool_arguments,
        command_hint=_command_hint(tool, profile_id=profile_id),
        metadata=metadata,
    )


def _blend_file_path(state: AgentProjectState, blend_artifact_id: str | None) -> str | None:
    if not blend_artifact_id:
        return None
    for artifact in state.artifacts:
        if artifact.artifact_id == blend_artifact_id and artifact.artifact_type == ArtifactType.BLENDER_FILE:
            return artifact.uri
    return None


def _job_id(index: int, action: ControllerAction, name: str) -> str:
    phase = action.phase.value.lower()
    safe_name = name.replace(" ", "_").replace(".", "_")
    return f"job_{index + 1:02d}_{phase}_{safe_name}"


def _command_hint(tool: str, *, profile_id: str | None) -> str | None:
    if tool == "build_subject_asset":
        suffix = f" --hunyuan-profile {profile_id}" if profile_id else ""
        return f"workflow_runner subject-asset{suffix}"
    if tool == "build_scene_asset":
        return "workflow_runner scene-asset"
    if tool in {"generate_concept_images", "regenerate_concept_images"}:
        return "workflow_runner codex-self or provider-backed image generation"
    if tool == "import_scene_asset":
        return "domain_dispatcher import_scene_asset"
    if tool in {"export_viewer_scene", "render_preview"}:
        return f"domain_dispatcher {tool}"
    if tool in {
        "get_blender_scene_summary",
        "move_subject",
        "rotate_subject",
        "scale_subject",
        "delete_subject",
        "replace_subject_asset",
        "update_camera",
        "update_lighting",
        "set_simple_material",
    }:
        return f"workflow_runner blender-edit --tool {tool}"
    return None


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
