"""Runtime execution step logging for planned V1 jobs.

The runtime dispatch layer writes what should happen next. This module takes
one safe step from that plan and records what actually happened without
pretending long-running services, sub-agents, or user gates finished.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.agent_prompts import OUTPUT_MODELS_BY_NODE
from agent_runtime.artifacts import FileArtifactStore, utc_now_iso
from agent_runtime.blender_mcp import build_safe_blender_mcp_operation_plan
from agent_runtime.blender_mcp import BlenderLabSocketRawToolCaller
from agent_runtime.domain_tools import allowed_tool_names
from agent_runtime.domain_dispatcher import (
    BlenderMCPDomainToolDispatcher,
    RawBlenderMCPToolCaller,
    ScriptDomainToolDispatcher,
)
from agent_runtime.delivery_handoff import build_delivery_handoff
from agent_runtime.delivery_package import build_delivery_package
from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.llm_nodes import LLMNodeExecutionResult, run_llm_node
from agent_runtime.llm_providers import LLMProviderConfig, build_provider_configs, load_agent_llm_env
from agent_runtime.persistence import FileStateCheckpointStore, StateCheckpointRecord
from agent_runtime.runtime_profiles import RuntimeServiceConfig
from agent_runtime.runtime_dispatch import (
    RuntimeDispatchPlanResult,
    build_and_save_runtime_dispatch_plan,
    read_runtime_dispatch_plan,
)
from agent_runtime.runtime_jobs import RuntimeJobSpec
from agent_runtime.state import AgentProjectState, ArtifactType, ViewerSceneState, WorkflowPhase
from agent_runtime.state_views import (
    MissingStateContextError,
    apply_state_updates,
    build_blender_assembly_planner_context,
    build_blender_edit_router_context,
    build_concept_prompt_planner_context,
    build_scene_interpreter_context,
    summarize_concept_bundle,
)
from agent_runtime.viewer_runtime import ViewerRuntimeAdapter
from agent_runtime.tool_executor import CommandExecutionOptions


RuntimeExecutionStatus = Literal[
    "dry_run",
    "completed",
    "waiting_user",
    "delegated",
    "blocked",
    "failed",
]


class RuntimeJobExecutionRecord(BaseModel):
    execution_id: str
    job_id: str
    job_kind: str
    phase: WorkflowPhase
    executor: str
    status: RuntimeExecutionStatus
    ok: bool
    created_at: str
    dry_run: bool = True
    node_name: str | None = None
    domain_tool_name: str | None = None
    output_json: str | None = None
    required_outputs: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeExecutionSummary(BaseModel):
    run_dir: str
    generated_at: str
    execution_log_jsonl: str
    total_records: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    latest_record: RuntimeJobExecutionRecord | None = None
    handled_job_ids: list[str] = Field(default_factory=list)
    pending_job_ids: list[str] = Field(default_factory=list)


class RuntimeExecutionStepResult(BaseModel):
    ok: bool
    run_dir: str
    state_json: str
    runtime_plan_json: str
    execution_log_jsonl: str
    execution_summary_json: str
    generated_plan: bool = False
    selected_job_id: str | None = None
    record: RuntimeJobExecutionRecord | None = None
    summary: RuntimeExecutionSummary
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


HANDLED_STATUSES = {"completed"}
RUNTIME_SCRIPT_DOMAIN_TOOLS = {"export_viewer_scene", "render_preview"}


def execute_next_runtime_job(
    run_dir: str | Path,
    *,
    dry_run: bool = True,
    provider_configs: list[LLMProviderConfig] | None = None,
    env: dict[str, str] | None = None,
    response_text_by_node: dict[str, str] | None = None,
    blender_raw_tool_caller: RawBlenderMCPToolCaller | None = None,
    blender_raw_caller_source: str | None = None,
) -> RuntimeExecutionStepResult:
    """Execute or safely account for the next unhandled runtime job.

    Dry-run is the default because the current V1 console is still wiring the
    runtime boundary. Live provider calls can be enabled by passing
    ``dry_run=False`` once the operator explicitly wants close-out testing.
    """

    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for runtime execution: {state_path}")

    generated_plan = False
    plan_payload = read_runtime_dispatch_plan(path)
    if plan_payload is None:
        plan_result = build_and_save_runtime_dispatch_plan(path)
        plan_payload = _model_to_dict(plan_result)
        generated_plan = True
    plan_result = RuntimeDispatchPlanResult(**plan_payload)
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))

    records = read_runtime_execution_records(path)
    handled_ids = _handled_job_ids(records)
    selected = _select_next_job(plan_result.runtime_plan.jobs, handled_ids)
    if selected is None:
        summary = _write_execution_summary(
            path,
            records=records,
            jobs=plan_result.runtime_plan.jobs,
        )
        return RuntimeExecutionStepResult(
            ok=True,
            run_dir=str(path),
            state_json=str(state_path),
            runtime_plan_json=str(path / "runtime_plan.json"),
            execution_log_jsonl=str(_execution_log_path(path)),
            execution_summary_json=str(_execution_summary_path(path)),
            generated_plan=generated_plan,
            summary=summary,
            message="no_unhandled_runtime_jobs",
        )

    record = _execute_job(
        run_dir=path,
        state=state,
        job=selected,
        dry_run=dry_run,
        provider_configs=provider_configs,
        env=env,
        response_text_by_node=response_text_by_node,
        blender_raw_tool_caller=blender_raw_tool_caller,
        blender_raw_caller_source=blender_raw_caller_source,
    )
    _append_jsonl(_execution_log_path(path), _model_to_dict(record))
    records.append(record)
    summary = _write_execution_summary(path, records=records, jobs=plan_result.runtime_plan.jobs)
    return RuntimeExecutionStepResult(
        ok=record.ok,
        run_dir=str(path),
        state_json=str(state_path),
        runtime_plan_json=str(path / "runtime_plan.json"),
        execution_log_jsonl=str(_execution_log_path(path)),
        execution_summary_json=str(_execution_summary_path(path)),
        generated_plan=generated_plan,
        selected_job_id=selected.job_id,
        record=record,
        summary=summary,
        issues=list(record.issues),
        message=record.status,
    )


def read_runtime_execution_records(run_dir: str | Path, *, limit: int | None = None) -> list[RuntimeJobExecutionRecord]:
    path = _execution_log_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return []
    records = [
        RuntimeJobExecutionRecord(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:] if limit is not None else records


def read_runtime_execution_summary(run_dir: str | Path) -> dict[str, Any] | None:
    path = _execution_summary_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _execute_job(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
    dry_run: bool,
    provider_configs: list[LLMProviderConfig] | None,
    env: dict[str, str] | None,
    response_text_by_node: dict[str, str] | None,
    blender_raw_tool_caller: RawBlenderMCPToolCaller | None,
    blender_raw_caller_source: str | None,
) -> RuntimeJobExecutionRecord:
    execution_id = f"exec_{uuid4().hex[:12]}"
    common = _record_common(execution_id=execution_id, job=job, dry_run=dry_run)

    if job.kind == "user_gate" or job.executor == "user" or job.status == "waiting_user":
        return RuntimeJobExecutionRecord(
            **common,
            status="waiting_user",
            ok=True,
            issues=["runtime_waiting_for_user_input"],
            result_summary={"reason": job.reason, "payload": job.metadata.get("payload")},
        )

    if job.kind == "delivery":
        return _execute_delivery_job(run_dir=run_dir, state=state, job=job, common=common, dry_run=dry_run)

    if job.kind == "domain_tool" and _is_runtime_script_domain_tool(job):
        return _execute_runtime_script_domain_tool_job(
            run_dir=run_dir,
            state=state,
            job=job,
            common=common,
            dry_run=dry_run,
            execution_id=execution_id,
        )

    if job.kind == "domain_tool" and _is_blender_edit_domain_tool(job):
        return _execute_blender_edit_domain_tool_job(
            run_dir=run_dir,
            state=state,
            job=job,
            common=common,
            dry_run=dry_run,
            execution_id=execution_id,
            raw_tool_caller=blender_raw_tool_caller,
            raw_caller_source=blender_raw_caller_source,
        )

    if job.long_running or job.executor in {"sub_agent", "background_worker"}:
        return RuntimeJobExecutionRecord(
            **common,
            status="delegated",
            ok=True,
            issues=["job_requires_external_worker_or_sub_agent"],
            result_summary={
                "reason": job.reason,
                "command_hint": job.command_hint,
                "profile_id": job.profile_id,
                "timeout_seconds": job.timeout_seconds,
            },
        )

    if job.kind != "llm_node":
        return RuntimeJobExecutionRecord(
            **common,
            status="blocked",
            ok=False,
            issues=["unsupported_main_runtime_job_kind"],
            error=f"main runtime step does not execute job kind: {job.kind}",
        )

    if not job.node_name or job.node_name not in OUTPUT_MODELS_BY_NODE:
        return RuntimeJobExecutionRecord(
            **common,
            status="blocked",
            ok=False,
            issues=["unsupported_llm_node"],
            error=f"unsupported llm node: {job.node_name}",
        )

    node_context = build_llm_node_context(state, job, run_dir=run_dir)
    values = env if env is not None else load_agent_llm_env()
    configs = provider_configs if provider_configs is not None else build_provider_configs(env=values)
    response_text = response_text_by_node.get(job.node_name) if response_text_by_node and job.node_name else None
    result = run_llm_node(
        node_name=job.node_name,
        context_json=node_context,
        provider_configs=configs,
        env=values,
        dry_run=dry_run,
        response_text=response_text,
    )
    output_path = _write_execution_output(
        run_dir,
        execution_id=execution_id,
        payload={
            "execution_id": execution_id,
            "job": _model_to_dict(job),
            "context_json": node_context,
            "llm_result": _model_to_dict(result),
        },
    )
    status: RuntimeExecutionStatus = "dry_run" if result.ok and result.dry_run else "completed" if result.ok else "failed"
    return RuntimeJobExecutionRecord(
        **common,
        status=status,
        ok=result.ok,
        output_json=str(output_path),
        issues=list(result.issues),
        error=result.error,
        result_summary=_llm_result_summary(result),
    )


def _is_blender_edit_domain_tool(job: RuntimeJobSpec) -> bool:
    return (
        job.phase == WorkflowPhase.BLENDER_EDIT
        and not _is_runtime_script_domain_tool(job)
        and job.domain_tool_name in set(allowed_tool_names(WorkflowPhase.BLENDER_EDIT))
    )


def _is_runtime_script_domain_tool(job: RuntimeJobSpec) -> bool:
    return job.domain_tool_name in RUNTIME_SCRIPT_DOMAIN_TOOLS


def _execute_runtime_script_domain_tool_job(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
    common: dict[str, Any],
    dry_run: bool,
    execution_id: str,
) -> RuntimeJobExecutionRecord:
    assert job.domain_tool_name is not None
    try:
        arguments, blender_path = _runtime_script_tool_arguments(run_dir=run_dir, state=state, job=job)
        dispatcher = ScriptDomainToolDispatcher(
            state=state,
            root=_project_root(),
            blender_path=blender_path,
        )
        result = dispatcher.dispatch(
            job.domain_tool_name,
            arguments,
            options=CommandExecutionOptions(timeout_seconds=job.timeout_seconds or 300, dry_run=dry_run),
        )
        updated = dispatcher.state
        checkpoint = None
        if result.ok and not dry_run:
            updated, checkpoint = _persist_runtime_script_domain_tool_outputs(
                run_dir=run_dir,
                state=updated,
                job=job,
                dispatch_result=result,
                execution_id=execution_id,
                arguments=arguments,
            )
        output_path = _write_execution_output(
            run_dir,
            execution_id=execution_id,
            payload={
                "execution_id": execution_id,
                "job": _model_to_dict(job),
                "script_tool_result": _model_to_dict(result),
                "checkpoint": _model_to_dict(checkpoint) if checkpoint is not None else None,
            },
        )
    except Exception as exc:
        return RuntimeJobExecutionRecord(
            **common,
            status="failed",
            ok=False,
            issues=["runtime_script_domain_tool_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )
    status: RuntimeExecutionStatus = "dry_run" if dry_run and result.ok else "completed" if result.ok else "failed"
    return RuntimeJobExecutionRecord(
        **common,
        status=status,
        ok=result.ok,
        output_json=str(output_path),
        issues=["runtime_script_domain_tool_dry_run"] if dry_run and result.ok else [] if result.ok else ["runtime_script_domain_tool_failed"],
        result_summary={
            "domain_tool_name": result.domain_tool_name,
            "tool_call_id": result.tool_call_id,
            "tool_call_status": result.tool_call_status,
            "outputs": dict(result.outputs),
            "checkpoint_id": checkpoint.checkpoint_id if checkpoint is not None else None,
        },
    )


def _execute_blender_edit_domain_tool_job(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
    common: dict[str, Any],
    dry_run: bool,
    execution_id: str,
    raw_tool_caller: RawBlenderMCPToolCaller | None,
    raw_caller_source: str | None,
) -> RuntimeJobExecutionRecord:
    if state.blender_scene is None:
        return RuntimeJobExecutionRecord(
            **common,
            status="blocked",
            ok=False,
            issues=["blender_edit_requires_blender_scene"],
            error="state.blender_scene is required for Blender edit domain tools",
        )
    assert job.domain_tool_name is not None
    try:
        plan = build_safe_blender_mcp_operation_plan(
            phase=WorkflowPhase.BLENDER_EDIT,
            domain_tool_name=job.domain_tool_name,
            arguments=job.tool_arguments,
            blender_scene=state.blender_scene,
        )
    except Exception as exc:
        return RuntimeJobExecutionRecord(
            **common,
            status="failed",
            ok=False,
            issues=["blender_edit_plan_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )
    output_path = _write_execution_output(
        run_dir,
        execution_id=execution_id,
        payload={
            "execution_id": execution_id,
            "job": _model_to_dict(job),
            "domain_tool_result": {
                "dry_run": dry_run,
                "operation_plan": _model_to_dict(plan),
            },
        },
    )
    if not plan.ok:
        return RuntimeJobExecutionRecord(
            **common,
            status="blocked",
            ok=False,
            output_json=str(output_path),
            issues=["blender_edit_plan_rejected", *list(plan.issues)],
            result_summary={"operation_plan": _model_to_dict(plan)},
        )
    if not dry_run:
        return _execute_live_blender_edit_domain_tool_job(
            run_dir=run_dir,
            state=state,
            job=job,
            common=common,
            execution_id=execution_id,
            operation_plan=_model_to_dict(plan),
            raw_tool_caller=raw_tool_caller,
            raw_caller_source=raw_caller_source,
        )
    return RuntimeJobExecutionRecord(
        **common,
        status="dry_run",
        ok=True,
        output_json=str(output_path),
        issues=["blender_edit_domain_tool_dry_run"],
        result_summary={"operation_plan": _model_to_dict(plan)},
    )


def _execute_live_blender_edit_domain_tool_job(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
    common: dict[str, Any],
    execution_id: str,
    operation_plan: dict[str, Any],
    raw_tool_caller: RawBlenderMCPToolCaller | None,
    raw_caller_source: str | None,
) -> RuntimeJobExecutionRecord:
    if raw_tool_caller is not None and raw_caller_source is not None:
        return RuntimeJobExecutionRecord(
            **common,
            status="blocked",
            ok=False,
            issues=["blender_edit_raw_caller_ambiguous"],
            error="Use either blender_raw_tool_caller or blender_raw_caller_source, not both.",
            result_summary={"operation_plan": operation_plan},
        )
    if raw_tool_caller is None:
        if raw_caller_source is None:
            return RuntimeJobExecutionRecord(
                **common,
                status="blocked",
                ok=False,
                issues=["blender_edit_requires_explicit_raw_caller"],
                error=(
                    "Non-dry-run Blender edit execution requires an explicit raw caller. "
                    "Pass blender_raw_caller_source='blender-lab-socket' or inject blender_raw_tool_caller."
                ),
                result_summary={"operation_plan": operation_plan},
            )
        if raw_caller_source != "blender-lab-socket":
            return RuntimeJobExecutionRecord(
                **common,
                status="blocked",
                ok=False,
                issues=["unsupported_blender_edit_raw_caller_source"],
                error=f"unsupported blender_raw_caller_source: {raw_caller_source}",
                result_summary={"operation_plan": operation_plan},
            )
        raw_tool_caller = BlenderLabSocketRawToolCaller()
    assert job.domain_tool_name is not None
    try:
        dispatcher = BlenderMCPDomainToolDispatcher(
            state=state,
            raw_tool_caller=raw_tool_caller,
            ensure_blend_loaded=raw_caller_source == "blender-lab-socket",
        )
        result = dispatcher.dispatch(
            job.domain_tool_name,
            job.tool_arguments,
            options=CommandExecutionOptions(dry_run=False),
        )
        updated = dispatcher.state
        updated.updated_at = utc_now_iso()
        checkpoint = _persist_blender_edit_outputs(
            run_dir=run_dir,
            state=updated,
            job=job,
            dispatch_result=result,
            execution_id=execution_id,
            raw_caller_source=raw_caller_source or "injected",
        )
        output_path = _write_execution_output(
            run_dir,
            execution_id=execution_id,
            payload={
                "execution_id": execution_id,
                "job": _model_to_dict(job),
                "domain_tool_result": _model_to_dict(result),
                "operation_plan": operation_plan,
                "checkpoint": _model_to_dict(checkpoint),
            },
        )
    except Exception as exc:
        return RuntimeJobExecutionRecord(
            **common,
            status="failed",
            ok=False,
            issues=["blender_edit_domain_tool_execution_failed"],
            error=f"{type(exc).__name__}: {exc}",
            result_summary={"operation_plan": operation_plan},
        )
    return RuntimeJobExecutionRecord(
        **common,
        status="completed" if result.ok else "failed",
        ok=result.ok,
        output_json=str(output_path),
        issues=[] if result.ok else ["blender_edit_domain_tool_failed"],
        result_summary={
            "domain_tool_name": result.domain_tool_name,
            "tool_call_id": result.tool_call_id,
            "tool_call_status": result.tool_call_status,
            "outputs": dict(result.outputs),
            "checkpoint_id": checkpoint.checkpoint_id,
            "operation_plan": operation_plan,
        },
    )


def _execute_delivery_job(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
    common: dict[str, Any],
    dry_run: bool,
) -> RuntimeJobExecutionRecord:
    if state.phase != WorkflowPhase.DELIVERY:
        return RuntimeJobExecutionRecord(
            **common,
            status="blocked",
            ok=False,
            issues=["delivery_job_requires_delivery_phase"],
            error=f"delivery job requires DELIVERY phase, got {state.phase.value}",
        )

    handoff = build_delivery_handoff(state)
    if dry_run:
        return RuntimeJobExecutionRecord(
            **common,
            status="dry_run",
            ok=handoff.ready,
            issues=[] if handoff.ready else ["delivery_handoff_not_ready", *handoff.issues],
            result_summary={
                "dry_run": True,
                "delivery_handoff_ready": handoff.ready,
                "delivery_handoff_verified": handoff.verified,
                "delivery_handoff_issues": list(handoff.issues),
                "package_output_dir": str(run_dir / "delivery_package" / "package"),
            },
        )

    try:
        package_id = _delivery_package_id(state, job)
        result, updated = build_delivery_package(
            state=state,
            output_dir=run_dir / "delivery_package" / "package",
            artifact_store=FileArtifactStore(run_dir / "artifacts"),
            package_id=package_id,
        )
        updated.updated_at = utc_now_iso()
        checkpoint = _persist_delivery_outputs(
            run_dir=run_dir,
            state=updated,
            job=job,
            package_result=result,
            execution_id=common["execution_id"],
        )
        output_path = _write_execution_output(
            run_dir,
            execution_id=common["execution_id"],
            payload={
                "execution_id": common["execution_id"],
                "job": _model_to_dict(job),
                "delivery_result": _model_to_dict(result),
                "checkpoint": _model_to_dict(checkpoint),
            },
        )
    except Exception as exc:
        return RuntimeJobExecutionRecord(
            **common,
            status="failed",
            ok=False,
            issues=["delivery_job_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    return RuntimeJobExecutionRecord(
        **common,
        status="completed" if result.ok else "failed",
        ok=result.ok,
        output_json=str(output_path),
        issues=list(result.issues),
        result_summary={
            "package_id": result.package_id,
            "package_artifact_id": result.package_artifact_id,
            "package_zip": result.package_zip,
            "metadata_json": result.metadata_json,
            "version_manifest_json": result.version_manifest_json,
            "item_count": len(result.items),
            "checks": dict(result.checks),
        },
    )


def _persist_delivery_outputs(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
    package_result,
    execution_id: str,
) -> StateCheckpointRecord:
    _write_json(run_dir / "state.json", _model_to_dict(state))
    handoff = build_delivery_handoff(state)
    _write_json(run_dir / "delivery_handoff.json", _model_to_dict(handoff))
    checkpoint = _save_delivery_checkpoint(
        run_dir,
        state,
        job=job,
        package_result=package_result,
        execution_id=execution_id,
    )
    summary_payload = _read_json(run_dir / "summary.json") or {}
    _append_delivery_to_summary(
        summary_payload,
        checkpoint=checkpoint,
        job=job,
        package_result=package_result,
        execution_id=execution_id,
    )
    _write_json(run_dir / "summary.json", summary_payload)
    _write_json(run_dir / "frontend_status.json", _model_to_dict(build_frontend_status(state=state, summary=summary_payload)))
    build_and_save_runtime_dispatch_plan(run_dir)
    return checkpoint


def _persist_blender_edit_outputs(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
    dispatch_result,
    execution_id: str,
    raw_caller_source: str,
) -> StateCheckpointRecord:
    _write_json(run_dir / "state.json", _model_to_dict(state))
    checkpoint = _save_blender_edit_checkpoint(
        run_dir,
        state,
        job=job,
        dispatch_result=dispatch_result,
        execution_id=execution_id,
        raw_caller_source=raw_caller_source,
    )
    summary_payload = _read_json(run_dir / "summary.json") or {}
    _append_blender_edit_to_summary(
        summary_payload,
        checkpoint=checkpoint,
        job=job,
        dispatch_result=dispatch_result,
        execution_id=execution_id,
        raw_caller_source=raw_caller_source,
    )
    _write_json(run_dir / "summary.json", summary_payload)
    _write_json(run_dir / "frontend_status.json", _model_to_dict(build_frontend_status(state=state, summary=summary_payload)))
    return checkpoint


def _runtime_script_tool_arguments(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
) -> tuple[dict[str, Any], str | Path | None]:
    arguments = dict(job.tool_arguments)
    blender_path = arguments.pop("blender_path", None)
    if job.domain_tool_name == "export_viewer_scene":
        input_blend = arguments.get("input_blend") or _resolve_blend_file_path(state)
        if input_blend is None:
            raise ValueError("export_viewer_scene requires input_blend or state.blender_scene.blend_file_artifact_id")
        viewer_dir = run_dir / "viewer_export"
        viewer_dir.mkdir(parents=True, exist_ok=True)
        arguments.setdefault("input_blend", str(input_blend))
        arguments.setdefault("viewer_glb", str(viewer_dir / "viewer_scene.glb"))
        arguments.setdefault("scene_state_json", str(viewer_dir / "scene_state.json"))
        return arguments, blender_path
    if job.domain_tool_name == "render_preview":
        input_glb = arguments.get("input_glb") or _resolve_viewer_glb_path(state)
        if input_glb is None:
            raise ValueError("render_preview requires input_glb or state.viewer_scene.viewer_scene_path")
        preview_dir = run_dir / "preview_render"
        preview_dir.mkdir(parents=True, exist_ok=True)
        arguments.setdefault("input_glb", str(input_glb))
        arguments.setdefault("preview_png", str(preview_dir / "preview.png"))
        arguments.setdefault("preview_blend", str(preview_dir / "preview.blend"))
        return arguments, blender_path
    raise ValueError(f"unsupported runtime script domain tool: {job.domain_tool_name}")


def _persist_runtime_script_domain_tool_outputs(
    *,
    run_dir: Path,
    state: AgentProjectState,
    job: RuntimeJobSpec,
    dispatch_result,
    execution_id: str,
    arguments: dict[str, Any],
) -> tuple[AgentProjectState, StateCheckpointRecord]:
    updated = state
    artifact_store = FileArtifactStore(run_dir / "artifacts")
    if job.domain_tool_name == "export_viewer_scene":
        updated = _apply_export_viewer_outputs(
            state=updated,
            artifact_store=artifact_store,
            arguments=arguments,
            execution_id=execution_id,
        )
    elif job.domain_tool_name == "render_preview":
        updated = _apply_render_preview_outputs(
            state=updated,
            artifact_store=artifact_store,
            arguments=arguments,
            execution_id=execution_id,
        )
    updated.updated_at = utc_now_iso()
    _write_json(run_dir / "state.json", _model_to_dict(updated))
    checkpoint = _save_runtime_script_domain_tool_checkpoint(
        run_dir,
        updated,
        job=job,
        dispatch_result=dispatch_result,
        execution_id=execution_id,
    )
    summary_payload = _read_json(run_dir / "summary.json") or {}
    _append_runtime_script_domain_tool_to_summary(
        summary_payload,
        checkpoint=checkpoint,
        job=job,
        dispatch_result=dispatch_result,
        execution_id=execution_id,
        arguments=arguments,
    )
    _write_json(run_dir / "summary.json", summary_payload)
    _write_json(run_dir / "frontend_status.json", _model_to_dict(build_frontend_status(state=updated, summary=summary_payload)))
    _write_json(run_dir / "delivery_handoff.json", _model_to_dict(build_delivery_handoff(updated)))
    if job.domain_tool_name == "render_preview":
        build_and_save_runtime_dispatch_plan(run_dir)
    return updated, checkpoint


def _apply_export_viewer_outputs(
    *,
    state: AgentProjectState,
    artifact_store: FileArtifactStore,
    arguments: dict[str, Any],
    execution_id: str,
) -> AgentProjectState:
    viewer_glb = Path(arguments["viewer_glb"]).expanduser().resolve()
    scene_state_json = Path(arguments["scene_state_json"]).expanduser().resolve()
    if not viewer_glb.is_file():
        raise FileNotFoundError(f"viewer GLB was not produced: {viewer_glb}")
    if not scene_state_json.is_file():
        raise FileNotFoundError(f"scene_state.json was not produced: {scene_state_json}")
    viewer_scene_artifact_id = f"runtime_{execution_id}_viewer_scene_glb"
    viewer_state_artifact_id = f"runtime_{execution_id}_scene_state_json"
    payload = json.loads(scene_state_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scene_state.json root must be an object")
    payload.setdefault("viewer_scene_id", f"viewer_scene_{execution_id}")
    payload["viewer_scene_artifact_id"] = viewer_scene_artifact_id
    payload["viewer_state_artifact_id"] = viewer_state_artifact_id
    payload["viewer_scene_path"] = str(viewer_glb)
    payload["source_blend_path"] = str(Path(arguments["input_blend"]).expanduser().resolve())
    payload.setdefault("last_exported_at", utc_now_iso())
    viewer_scene = ViewerSceneState(**payload)
    viewer_scene = _merge_blender_object_metadata_into_viewer_scene(viewer_scene, state)
    _write_json(scene_state_json, _model_to_dict(viewer_scene))
    viewer_glb_artifact = artifact_store.register_file(
        viewer_glb,
        ArtifactType.VIEWER_SCENE_GLB,
        artifact_id=viewer_scene_artifact_id,
        semantic_role="viewer_scene",
        metadata={
            "stage": "runtime_export_viewer",
            "execution_id": execution_id,
            "viewer": _viewer_metadata(viewer_glb),
        },
    )
    viewer_state_artifact = artifact_store.register_file(
        scene_state_json,
        ArtifactType.VIEWER_SCENE_STATE_JSON,
        artifact_id=viewer_state_artifact_id,
        semantic_role="viewer_scene_state",
        metadata={"stage": "runtime_export_viewer", "execution_id": execution_id},
    )
    state.artifacts = [*state.artifacts, viewer_glb_artifact, viewer_state_artifact]
    return apply_state_updates(
        state,
        node_name="ScenePreviewExporter",
        updates={"viewer_scene": viewer_scene},
    )


def _merge_blender_object_metadata_into_viewer_scene(
    viewer_scene: ViewerSceneState,
    state: AgentProjectState,
) -> ViewerSceneState:
    blender_scene = state.blender_scene
    if blender_scene is None:
        return viewer_scene
    metadata_by_name = {
        item.blender_name: item
        for item in blender_scene.objects
    }
    updated_objects = []
    changed = False
    for item in viewer_scene.objects:
        source = metadata_by_name.get(item.blender_object_id) or metadata_by_name.get(item.display_name)
        if source is None:
            updated_objects.append(item)
            continue
        updates: dict[str, Any] = {}
        for field_name in ("subject_id", "asset_id"):
            if getattr(item, field_name) is None and getattr(source, field_name) is not None:
                updates[field_name] = getattr(source, field_name)
        if updates:
            updated_objects.append(item.model_copy(update=updates))
            changed = True
        else:
            updated_objects.append(item)
    if not changed:
        return viewer_scene
    return viewer_scene.model_copy(update={"objects": updated_objects})


def _apply_render_preview_outputs(
    *,
    state: AgentProjectState,
    artifact_store: FileArtifactStore,
    arguments: dict[str, Any],
    execution_id: str,
) -> AgentProjectState:
    preview_png = Path(arguments["preview_png"]).expanduser().resolve()
    preview_blend = Path(arguments["preview_blend"]).expanduser().resolve()
    if not preview_png.is_file():
        raise FileNotFoundError(f"preview PNG was not produced: {preview_png}")
    preview_artifact = artifact_store.register_file(
        preview_png,
        ArtifactType.BLENDER_PREVIEW_RENDER,
        artifact_id=f"runtime_{execution_id}_preview_png",
        semantic_role="blender_preview_render",
        metadata={"stage": "runtime_render_preview", "execution_id": execution_id},
    )
    new_artifacts = [*state.artifacts, preview_artifact]
    if preview_blend.is_file():
        new_artifacts.append(
            artifact_store.register_file(
                preview_blend,
                ArtifactType.BLENDER_FILE,
                artifact_id=f"runtime_{execution_id}_preview_blend",
                semantic_role="render_preview_blend",
                metadata={"stage": "runtime_render_preview", "execution_id": execution_id},
            )
        )
    state.artifacts = new_artifacts
    if state.blender_scene is None:
        raise ValueError("render_preview requires state.blender_scene to update preview_image_id")
    blender_scene = state.blender_scene.model_copy(
        update={
            "preview_image_id": preview_artifact.artifact_id,
            "last_synced_at": utc_now_iso(),
        }
    )
    return apply_state_updates(
        state,
        node_name="BlenderPreviewRenderer",
        updates={
            "blender_scene": blender_scene,
            "phase": WorkflowPhase.BLENDER_PREVIEW,
        },
    )


def _save_runtime_script_domain_tool_checkpoint(
    run_dir: Path,
    state: AgentProjectState,
    *,
    job: RuntimeJobSpec,
    dispatch_result,
    execution_id: str,
) -> StateCheckpointRecord:
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    stage = "runtime_export_viewer" if job.domain_tool_name == "export_viewer_scene" else "runtime_render_preview"
    return store.save_checkpoint(
        state,
        reason=f"{stage}_completed" if dispatch_result.ok else f"{stage}_failed",
        node_name="ScenePreviewExporter" if job.domain_tool_name == "export_viewer_scene" else "BlenderPreviewRenderer",
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={
            "stage": stage,
            "execution_id": execution_id,
            "job_id": job.job_id,
            "domain_tool_name": job.domain_tool_name,
            "tool_call_id": dispatch_result.tool_call_id,
            "tool_call_status": dispatch_result.tool_call_status,
            "ok": dispatch_result.ok,
        },
    )


def _append_runtime_script_domain_tool_to_summary(
    summary: dict[str, Any],
    *,
    checkpoint: StateCheckpointRecord,
    job: RuntimeJobSpec,
    dispatch_result,
    execution_id: str,
    arguments: dict[str, Any],
) -> None:
    stage = "export_viewer" if job.domain_tool_name == "export_viewer_scene" else "render_preview"
    summary.setdefault("ok", True)
    summary.setdefault("workflow", "runtime-console")
    requested = summary.setdefault("requested_stages", [])
    if stage not in requested:
        requested.append(stage)
    executed = summary.setdefault("executed_stages", [])
    if stage not in executed:
        executed.append(stage)
    summary["latest_runtime_script_execution"] = {
        "execution_id": execution_id,
        "job_id": job.job_id,
        "domain_tool_name": job.domain_tool_name,
        "tool_call_id": dispatch_result.tool_call_id,
        "tool_call_status": dispatch_result.tool_call_status,
        "outputs": dict(dispatch_result.outputs),
    }
    if job.domain_tool_name == "export_viewer_scene":
        summary["latest_viewer_scene_path"] = str(Path(arguments["viewer_glb"]).expanduser().resolve())
    if job.domain_tool_name == "render_preview":
        summary["phase"] = WorkflowPhase.BLENDER_PREVIEW.value
        summary["latest_preview_image_path"] = str(Path(arguments["preview_png"]).expanduser().resolve())
    checkpoints = summary.setdefault("stage_checkpoints", [])
    checkpoints.append(
        {
            "checkpoint_id": checkpoint.checkpoint_id,
            "reason": checkpoint.reason,
            "metadata": checkpoint.metadata,
        }
    )
    summary["checkpoint"] = _model_to_dict(checkpoint)
    if not dispatch_result.ok:
        summary["ok"] = False


def _resolve_blend_file_path(state: AgentProjectState) -> Path | None:
    if state.blender_scene is None or not state.blender_scene.blend_file_artifact_id:
        return None
    artifact_id = state.blender_scene.blend_file_artifact_id
    for artifact in state.artifacts:
        if artifact.artifact_id == artifact_id:
            return Path(artifact.uri).expanduser().resolve()
    return None


def _resolve_viewer_glb_path(state: AgentProjectState) -> Path | None:
    if state.viewer_scene is not None and state.viewer_scene.viewer_scene_path:
        return Path(state.viewer_scene.viewer_scene_path).expanduser().resolve()
    artifact_id = state.viewer_scene.viewer_scene_artifact_id if state.viewer_scene is not None else None
    if artifact_id:
        for artifact in state.artifacts:
            if artifact.artifact_id == artifact_id:
                return Path(artifact.uri).expanduser().resolve()
    return None


def _viewer_metadata(viewer_glb: Path) -> dict[str, Any]:
    config = RuntimeServiceConfig()
    adapter = ViewerRuntimeAdapter(base_url=config.glb_viewer_base_url)
    runtime_status = adapter.runtime_status()
    model_check = adapter.check_model(viewer_glb)
    if isinstance(model_check, dict):
        model_check["runtime"] = runtime_status
        runtime_ok = runtime_status.get("ok") if isinstance(runtime_status, dict) else False
        model_check["ok"] = bool(model_check.get("ok") and runtime_ok)
    return adapter.artifact_metadata(
        viewer_glb,
        runtime_status=runtime_status,
        model_check=model_check,
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_llm_node_context(
    state: AgentProjectState,
    job: RuntimeJobSpec,
    *,
    run_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a small context view for a runtime LLM node."""

    node_name = job.node_name or ""
    latest_turn = state.user_turns[-1] if state.user_turns else None
    if node_name == "UserIntentRouter":
        return {
            "phase": state.phase.value,
            "latest_user_turn": _model_to_dict(latest_turn) if latest_turn is not None else None,
            "pending_action": _model_to_dict(state.pending_action) if state.pending_action is not None else None,
        }
    if node_name == "ReferenceBindingValidator":
        return {
            "user_text": latest_turn.text if latest_turn is not None else "",
            "input_images": [_model_to_dict(item) for item in state.input_images],
            "declared_bindings": [
                _model_to_dict(item)
                for item in state.reference_bindings
                if item.explicit_in_user_text
            ],
        }
    if node_name == "SceneInterpreter":
        return _context_or_issue(
            lambda: build_scene_interpreter_context(state),
            fallback={
                "user_text": latest_turn.text if latest_turn is not None else "",
                "input_images": [_model_to_dict(item) for item in state.input_images],
                "declared_bindings": [_model_to_dict(item) for item in state.reference_bindings],
            },
        )
    if node_name == "SceneSpecCompiler":
        interpretation = _latest_parsed_output_for_node(run_dir, "SceneInterpreter")
        return {
            "interpretation": interpretation,
            "reference_bindings": [_model_to_dict(item) for item in state.reference_bindings],
            "previous_scene_spec": _model_to_dict(state.scene_spec) if state.scene_spec is not None else None,
            "latest_user_turn": _model_to_dict(latest_turn) if latest_turn is not None else None,
            "context_issue": None if interpretation is not None else "SceneInterpreter candidate output is not persisted yet.",
        }
    if node_name == "ConceptPromptPlanner":
        return _context_or_issue(
            lambda: build_concept_prompt_planner_context(state),
            fallback={"scene_spec": _model_to_dict(state.scene_spec) if state.scene_spec is not None else None},
        )
    if node_name == "ConceptVisualQA":
        return {
            "scene_spec": _model_to_dict(state.scene_spec) if state.scene_spec is not None else None,
            "concept_bundle": _model_to_dict(state.concept_bundle) if state.concept_bundle is not None else None,
            "reference_bindings": [_model_to_dict(item) for item in state.reference_bindings],
        }
    if node_name == "FeedbackPatchParser":
        return {
            "user_feedback": latest_turn.text if latest_turn is not None else "",
            "phase": state.phase.value,
            "scene_spec": _model_to_dict(state.scene_spec) if state.scene_spec is not None else None,
            "concept_bundle": _model_to_dict(state.concept_bundle) if state.concept_bundle is not None else None,
        }
    if node_name == "RegenerationRouter":
        return {
            "review_patches": [_model_to_dict(item) for item in state.review_patches],
            "current_phase": state.phase.value,
            "artifact_summary": _artifact_summary(state),
        }
    if node_name == "SceneAssetAdapterPlanner":
        return {
            "scene_spec": _model_to_dict(state.scene_spec) if state.scene_spec is not None else None,
            "scene_generation_output_summary": _model_to_dict(state.scene_asset) if state.scene_asset is not None else None,
        }
    if node_name == "BlenderAssemblyPlanner":
        return _context_or_issue(
            lambda: build_blender_assembly_planner_context(state),
            fallback={
                "scene_spec": _model_to_dict(state.scene_spec) if state.scene_spec is not None else None,
                "subject_assets": [_model_to_dict(item) for item in state.subject_assets],
                "scene_asset": _model_to_dict(state.scene_asset) if state.scene_asset is not None else None,
                "concept_bundle_summary": summarize_concept_bundle(state.concept_bundle),
            },
        )
    if node_name == "BlenderPreviewReviewGate":
        return {
            "user_feedback": latest_turn.text if latest_turn is not None else "",
            "viewer_scene": _model_to_dict(state.viewer_scene) if state.viewer_scene is not None else None,
            "blender_preview": _model_to_dict(state.blender_scene) if state.blender_scene is not None else None,
            "scene_spec": _model_to_dict(state.scene_spec) if state.scene_spec is not None else None,
        }
    if node_name == "BlenderEditRouter":
        return _context_or_issue(
            lambda: build_blender_edit_router_context(state),
            fallback={
                "user_edit_text": latest_turn.text if latest_turn is not None else "",
                "blender_scene": _model_to_dict(state.blender_scene) if state.blender_scene is not None else None,
                "scene_spec": _model_to_dict(state.scene_spec) if state.scene_spec is not None else None,
            },
        )
    return {
        "phase": state.phase.value,
        "latest_user_turn": _model_to_dict(latest_turn) if latest_turn is not None else None,
    }


def _context_or_issue(builder, *, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        context = builder()
        return _model_to_dict(context)
    except (MissingStateContextError, ValueError) as exc:
        return {**fallback, "context_issue": str(exc)}


def _latest_parsed_output_for_node(run_dir: str | Path | None, node_name: str) -> dict[str, Any] | None:
    if run_dir is None:
        return None
    try:
        records = read_runtime_execution_records(run_dir)
    except Exception:
        return None
    for record in reversed(records):
        if record.node_name != node_name or record.status != "completed" or not record.ok or not record.output_json:
            continue
        output_path = Path(record.output_json).expanduser().resolve()
        if not output_path.exists():
            continue
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        llm_result = payload.get("llm_result") if isinstance(payload, dict) else None
        context = payload.get("context_json") if isinstance(payload, dict) else None
        if not _candidate_context_matches_current_turn(context, node_name=node_name, latest_turn_text=_latest_user_text_from_run(run_dir)):
            continue
        parsed = llm_result.get("parsed_output") if isinstance(llm_result, dict) else None
        if isinstance(parsed, dict):
            return parsed
    return None


def _candidate_context_matches_current_turn(
    context: Any,
    *,
    node_name: str,
    latest_turn_text: str | None,
) -> bool:
    if not isinstance(context, dict) or latest_turn_text is None:
        return False
    if node_name == "SceneInterpreter":
        return context.get("user_text") == latest_turn_text
    return True


def _latest_user_text_from_run(run_dir: str | Path | None) -> str | None:
    if run_dir is None:
        return None
    state_path = Path(run_dir).expanduser().resolve() / "state.json"
    if not state_path.exists():
        return None
    try:
        state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    except Exception:
        return None
    return state.user_turns[-1].text if state.user_turns else ""


def _delivery_package_id(state: AgentProjectState, job: RuntimeJobSpec) -> str | None:
    payload = job.metadata.get("payload") if isinstance(job.metadata, dict) else None
    if isinstance(payload, dict) and isinstance(payload.get("package_id"), str):
        return payload["package_id"]
    return None


def _save_delivery_checkpoint(
    run_dir: Path,
    state: AgentProjectState,
    *,
    job: RuntimeJobSpec,
    package_result,
    execution_id: str,
) -> StateCheckpointRecord:
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    return store.save_checkpoint(
        state,
        reason="delivery_package_created" if package_result.ok else "delivery_package_failed",
        node_name="DeliveryPackager",
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={
            "stage": "delivery_package",
            "execution_id": execution_id,
            "job_id": job.job_id,
            "package_id": package_result.package_id,
            "package_artifact_id": package_result.package_artifact_id,
            "package_zip": package_result.package_zip,
            "ok": package_result.ok,
            "issues": list(package_result.issues),
        },
    )


def _save_blender_edit_checkpoint(
    run_dir: Path,
    state: AgentProjectState,
    *,
    job: RuntimeJobSpec,
    dispatch_result,
    execution_id: str,
    raw_caller_source: str,
) -> StateCheckpointRecord:
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    return store.save_checkpoint(
        state,
        reason="blender_edit_domain_tool_executed" if dispatch_result.ok else "blender_edit_domain_tool_failed",
        node_name="BlenderCommandExecutor",
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={
            "stage": "blender_edit",
            "execution_id": execution_id,
            "job_id": job.job_id,
            "domain_tool_name": job.domain_tool_name,
            "tool_call_id": dispatch_result.tool_call_id,
            "tool_call_status": dispatch_result.tool_call_status,
            "raw_caller_source": raw_caller_source,
            "ok": dispatch_result.ok,
            "dry_run": dispatch_result.dry_run,
        },
    )


def _append_delivery_to_summary(
    summary: dict[str, Any],
    *,
    checkpoint: StateCheckpointRecord,
    job: RuntimeJobSpec,
    package_result,
    execution_id: str,
) -> None:
    summary.setdefault("ok", True)
    summary.setdefault("workflow", "runtime-console")
    requested = summary.setdefault("requested_stages", [])
    if "delivery_package" not in requested:
        requested.append("delivery_package")
    executed = summary.setdefault("executed_stages", [])
    if "delivery_package" not in executed:
        executed.append("delivery_package")
    summary["phase"] = WorkflowPhase.DELIVERY.value
    summary["delivery_package_zip"] = package_result.package_zip
    summary["delivery_package_artifact_id"] = package_result.package_artifact_id
    summary["delivery_package_ok"] = package_result.ok
    summary["delivery_package_issues"] = list(package_result.issues)
    checkpoints = summary.setdefault("stage_checkpoints", [])
    checkpoints.append(
        {
            "checkpoint_id": checkpoint.checkpoint_id,
            "reason": checkpoint.reason,
            "metadata": checkpoint.metadata,
        }
    )
    summary["checkpoint"] = _model_to_dict(checkpoint)
    summary["latest_delivery_execution"] = {
        "execution_id": execution_id,
        "job_id": job.job_id,
        "package_id": package_result.package_id,
        "package_zip": package_result.package_zip,
    }
    if not package_result.ok:
        summary["ok"] = False


def _append_blender_edit_to_summary(
    summary: dict[str, Any],
    *,
    checkpoint: StateCheckpointRecord,
    job: RuntimeJobSpec,
    dispatch_result,
    execution_id: str,
    raw_caller_source: str,
) -> None:
    summary.setdefault("ok", True)
    summary.setdefault("workflow", "runtime-console")
    requested = summary.setdefault("requested_stages", [])
    if "blender_edit" not in requested:
        requested.append("blender_edit")
    executed = summary.setdefault("executed_stages", [])
    if "blender_edit" not in executed:
        executed.append("blender_edit")
    summary["phase"] = WorkflowPhase.BLENDER_EDIT.value
    summary["latest_blender_edit_execution"] = {
        "execution_id": execution_id,
        "job_id": job.job_id,
        "domain_tool_name": job.domain_tool_name,
        "tool_call_id": dispatch_result.tool_call_id,
        "tool_call_status": dispatch_result.tool_call_status,
        "raw_caller_source": raw_caller_source,
        "ok": dispatch_result.ok,
    }
    checkpoints = summary.setdefault("stage_checkpoints", [])
    checkpoints.append(
        {
            "checkpoint_id": checkpoint.checkpoint_id,
            "reason": checkpoint.reason,
            "metadata": checkpoint.metadata,
        }
    )
    summary["checkpoint"] = _model_to_dict(checkpoint)
    if not dispatch_result.ok:
        summary["ok"] = False


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _record_common(*, execution_id: str, job: RuntimeJobSpec, dry_run: bool) -> dict[str, Any]:
    return {
        "execution_id": execution_id,
        "job_id": job.job_id,
        "job_kind": job.kind,
        "phase": job.phase,
        "executor": job.executor,
        "created_at": utc_now_iso(),
        "dry_run": dry_run,
        "node_name": job.node_name,
        "domain_tool_name": job.domain_tool_name,
        "required_outputs": list(job.required_outputs),
        "metadata": {"job_reason": job.reason},
    }


def _select_next_job(jobs: list[RuntimeJobSpec], handled_ids: set[str]) -> RuntimeJobSpec | None:
    for job in jobs:
        if job.job_id not in handled_ids:
            return job
    return None


def _handled_job_ids(records: list[RuntimeJobExecutionRecord]) -> set[str]:
    return {record.job_id for record in records if record.status in HANDLED_STATUSES}


def _write_execution_output(run_dir: Path, *, execution_id: str, payload: dict[str, Any]) -> Path:
    path = run_dir / "runtime_execution" / f"{execution_id}.json"
    _write_json(path, payload)
    return path


def _write_execution_summary(
    run_dir: Path,
    *,
    records: list[RuntimeJobExecutionRecord],
    jobs: list[RuntimeJobSpec],
) -> RuntimeExecutionSummary:
    handled_ids = sorted(_handled_job_ids(records))
    pending = [job.job_id for job in jobs if job.job_id not in handled_ids]
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    summary = RuntimeExecutionSummary(
        run_dir=str(run_dir),
        generated_at=utc_now_iso(),
        execution_log_jsonl=str(_execution_log_path(run_dir)),
        total_records=len(records),
        status_counts=counts,
        latest_record=records[-1] if records else None,
        handled_job_ids=handled_ids,
        pending_job_ids=pending,
    )
    _write_json(_execution_summary_path(run_dir), _model_to_dict(summary))
    return summary


def _llm_result_summary(result: LLMNodeExecutionResult) -> dict[str, Any]:
    return {
        "node_name": result.node_name,
        "provider": result.provider,
        "model": result.model,
        "dry_run": result.dry_run,
        "output_model_name": result.output_model_name,
        "request_summary": result.request_summary,
        "has_parsed_output": result.parsed_output is not None,
    }


def _artifact_summary(state: AgentProjectState) -> list[dict[str, Any]]:
    return [
        {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type.value,
            "semantic_role": artifact.semantic_role,
            "linked_subject_id": artifact.linked_subject_id,
            "linked_scene_id": artifact.linked_scene_id,
            "uri": artifact.uri,
        }
        for artifact in state.artifacts
    ]


def _execution_log_path(run_dir: Path) -> Path:
    return run_dir / "runtime_execution.jsonl"


def _execution_summary_path(run_dir: Path) -> Path:
    return run_dir / "runtime_execution_summary.json"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model: Any) -> dict[str, Any] | None:
    if model is None:
        return None
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
