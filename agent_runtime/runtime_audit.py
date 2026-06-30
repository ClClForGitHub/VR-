"""Semantic audit for runtime run directories.

This module checks the files produced by the runtime console as an input ->
plan -> execution evidence chain. It is intentionally file-oriented: the audit
reads the run directory outputs instead of calling the runtime execution code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.runtime_dispatch import RuntimeDispatchPlanResult
from agent_runtime.runtime_delegation import RuntimeDelegatedHandoffRecord, RuntimeDelegatedHandoffSummary
from agent_runtime.runtime_execution import RuntimeExecutionSummary, RuntimeJobExecutionRecord
from agent_runtime.runtime_handoff_apply import RuntimeHandoffApplyRecord, RuntimeHandoffApplySummary
from agent_runtime.runtime_loop import RuntimeLoopIterationRecord, RuntimeLoopSummary
from agent_runtime.runtime_state_apply import RuntimeStateApplyRecord, RuntimeStateApplySummary
from agent_runtime.state import AgentProjectState


AuditSeverity = Literal["error", "warning", "info"]


class RuntimeAuditCheck(BaseModel):
    check_id: str
    ok: bool
    severity: AuditSeverity = "error"
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class RuntimeRunAuditResult(BaseModel):
    ok: bool
    run_dir: str
    audited_at: str
    checks: list[RuntimeAuditCheck] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0


def audit_runtime_run(run_dir: str | Path) -> RuntimeRunAuditResult:
    path = Path(run_dir).expanduser().resolve()
    checks: list[RuntimeAuditCheck] = []

    state = _read_model(path / "state.json", AgentProjectState, checks, "state_json_valid")
    plan = _read_model(path / "runtime_plan.json", RuntimeDispatchPlanResult, checks, "runtime_plan_valid")
    records = _read_execution_records(path, checks)
    execution_summary = _read_optional_model(
        path / "runtime_execution_summary.json",
        RuntimeExecutionSummary,
        checks,
        "runtime_execution_summary_valid",
    )
    apply_records = _read_apply_records(path, checks)
    apply_summary = _read_optional_model(
        path / "runtime_apply_summary.json",
        RuntimeStateApplySummary,
        checks,
        "runtime_apply_summary_valid",
    )
    loop_records = _read_loop_records(path, checks)
    loop_summary = _read_optional_model(
        path / "runtime_loop_summary.json",
        RuntimeLoopSummary,
        checks,
        "runtime_loop_summary_valid",
    )
    handoff_records = _read_handoff_records(path, checks)
    handoff_summary = _read_optional_model(
        path / "runtime_handoff_summary.json",
        RuntimeDelegatedHandoffSummary,
        checks,
        "runtime_handoff_summary_valid",
    )
    handoff_apply_records = _read_handoff_apply_records(path, checks)
    handoff_apply_summary = _read_optional_model(
        path / "runtime_handoff_apply_summary.json",
        RuntimeHandoffApplySummary,
        checks,
        "runtime_handoff_apply_summary_valid",
    )
    chat_rows = _read_optional_jsonl(path / "runtime_console" / "chat.jsonl", checks, "chat_jsonl_valid")

    if state is not None:
        _check_local_artifact_paths(path, state, checks)
        if chat_rows:
            _check_chat_mirrored_to_state(state, chat_rows, checks)
    if state is not None and plan is not None:
        _check_plan_matches_state(state, plan, checks)
        _check_user_gate_semantics(state, plan, checks)
    if plan is not None:
        _check_execution_records_against_plan(path, plan, records, apply_records, checks)
    if execution_summary is not None:
        _check_execution_summary(execution_summary, records, plan, checks)
    if apply_summary is not None:
        _check_apply_summary(path, apply_summary, apply_records, checks)
    if loop_summary is not None:
        _check_loop_summary(loop_summary, loop_records, checks)
    if handoff_summary is not None:
        _check_handoff_summary(path, handoff_summary, handoff_records, checks)
    if handoff_apply_summary is not None:
        _check_handoff_apply_summary(path, handoff_apply_summary, handoff_apply_records, checks)
    if state is not None and records:
        _check_execution_outputs(path, state, records, checks)

    error_count = sum(1 for check in checks if not check.ok and check.severity == "error")
    warning_count = sum(1 for check in checks if not check.ok and check.severity == "warning")
    return RuntimeRunAuditResult(
        ok=error_count == 0,
        run_dir=str(path),
        audited_at=utc_now_iso(),
        checks=checks,
        error_count=error_count,
        warning_count=warning_count,
    )


def _check_plan_matches_state(
    state: AgentProjectState,
    plan: RuntimeDispatchPlanResult,
    checks: list[RuntimeAuditCheck],
) -> None:
    runtime_plan = plan.runtime_plan
    checks.append(
        RuntimeAuditCheck(
            check_id="plan_project_matches_state",
            ok=runtime_plan.project_id == state.project_id and runtime_plan.thread_id == state.thread_id,
            message="runtime plan project/thread ids match state",
            evidence={
                "state_project_id": state.project_id,
                "plan_project_id": runtime_plan.project_id,
                "state_thread_id": state.thread_id,
                "plan_thread_id": runtime_plan.thread_id,
            },
        )
    )
    checks.append(
        RuntimeAuditCheck(
            check_id="plan_phase_matches_state",
            ok=runtime_plan.phase == state.phase and runtime_plan.controller.phase == state.phase,
            message="runtime plan phase and controller phase match state phase",
            evidence={
                "state_phase": state.phase.value,
                "runtime_plan_phase": runtime_plan.phase.value,
                "controller_phase": runtime_plan.controller.phase.value,
            },
        )
    )
    checks.append(
        RuntimeAuditCheck(
            check_id="plan_has_jobs_for_actions",
            ok=len(runtime_plan.jobs) == len(runtime_plan.controller.actions),
            message="runtime plan has one job for each controller action",
            evidence={
                "job_count": len(runtime_plan.jobs),
                "action_count": len(runtime_plan.controller.actions),
            },
        )
    )


def _check_user_gate_semantics(
    state: AgentProjectState,
    plan: RuntimeDispatchPlanResult,
    checks: list[RuntimeAuditCheck],
) -> None:
    unbound = _unbound_image_ids(state)
    user_gates = [job for job in plan.runtime_plan.jobs if job.kind == "user_gate"]
    if not user_gates:
        checks.append(
            RuntimeAuditCheck(
                check_id="user_gate_not_required_or_absent",
                ok=not unbound,
                severity="warning",
                message="no user gate is present when reference bindings are complete",
                evidence={"unbound_image_ids": unbound},
            )
        )
        return

    payload = user_gates[0].metadata.get("payload") if user_gates[0].metadata else {}
    payload_image_ids = sorted(payload.get("image_ids", [])) if isinstance(payload, dict) else []
    checks.append(
        RuntimeAuditCheck(
            check_id="user_gate_matches_unbound_images",
            ok=payload_image_ids == unbound,
            message="user gate image payload matches unbound input images",
            evidence={"payload_image_ids": payload_image_ids, "unbound_image_ids": unbound},
        )
    )


def _check_chat_mirrored_to_state(
    state: AgentProjectState,
    chat_rows: list[dict[str, Any]],
    checks: list[RuntimeAuditCheck],
) -> None:
    user_rows = [row for row in chat_rows if row.get("role") == "user"]
    turns_by_id = {turn.turn_id: turn for turn in state.user_turns}
    missing = []
    mismatched = []
    for row in user_rows:
        turn = turns_by_id.get(row.get("message_id"))
        if turn is None:
            missing.append(row.get("message_id"))
            continue
        if turn.text != row.get("text") or turn.image_ids != (row.get("attachment_ids") or []):
            mismatched.append(row.get("message_id"))
    checks.append(
        RuntimeAuditCheck(
            check_id="chat_user_turns_mirrored_to_state",
            ok=not missing and not mismatched,
            message="user chat rows are mirrored into AgentProjectState.user_turns",
            evidence={
                "user_chat_count": len(user_rows),
                "state_user_turn_count": len(state.user_turns),
                "missing_message_ids": missing,
                "mismatched_message_ids": mismatched,
            },
        )
    )


def _check_execution_records_against_plan(
    run_dir: Path,
    plan: RuntimeDispatchPlanResult,
    records: list[RuntimeJobExecutionRecord],
    apply_records: list[RuntimeStateApplyRecord],
    checks: list[RuntimeAuditCheck],
) -> None:
    if not (run_dir / "runtime_execution.jsonl").exists():
        checks.append(
            RuntimeAuditCheck(
                check_id="runtime_execution_log_present",
                ok=False,
                severity="warning",
                message="runtime execution log is not present yet",
            )
        )
        return
    job_ids = {job.job_id for job in plan.runtime_plan.jobs}
    applied_execution_ids = {
        record.execution_id for record in apply_records if record.status == "applied" and record.execution_id
    }
    recovered_job_ids = {
        record.job_id
        for record in records
        if record.status in {"completed", "dry_run", "waiting_user", "delegated", "blocked"}
    }
    unknown = [
        record.job_id
        for record in records
        if record.job_id not in job_ids
        and record.execution_id not in applied_execution_ids
        and record.job_id not in recovered_job_ids
        and record.status not in {"completed", "dry_run", "waiting_user", "delegated", "blocked"}
    ]
    checks.append(
        RuntimeAuditCheck(
            check_id="execution_job_ids_exist_in_plan",
            ok=not unknown,
            message="execution records reference current runtime jobs or already-applied prior jobs",
            evidence={
                "record_count": len(records),
                "plan_job_count": len(job_ids),
                "applied_execution_ids": sorted(applied_execution_ids),
                "recovered_job_ids": sorted(recovered_job_ids),
                "unknown_job_ids": unknown,
            },
        )
    )


def _check_execution_summary(
    summary: RuntimeExecutionSummary,
    records: list[RuntimeJobExecutionRecord],
    plan: RuntimeDispatchPlanResult | None,
    checks: list[RuntimeAuditCheck],
) -> None:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    latest_ok = (summary.latest_record is None and not records) or (
        summary.latest_record is not None
        and records
        and summary.latest_record.execution_id == records[-1].execution_id
    )
    checks.append(
        RuntimeAuditCheck(
            check_id="execution_summary_matches_log",
            ok=summary.total_records == len(records) and summary.status_counts == counts and latest_ok,
            message="runtime_execution_summary.json matches runtime_execution.jsonl",
            evidence={
                "summary_total_records": summary.total_records,
                "log_record_count": len(records),
                "summary_status_counts": summary.status_counts,
                "log_status_counts": counts,
                "latest_ok": latest_ok,
            },
        )
    )
    if plan is None:
        return
    plan_job_ids = {job.job_id for job in plan.runtime_plan.jobs}
    log_job_ids = {record.job_id for record in records}
    handled_valid = set(summary.handled_job_ids).issubset(plan_job_ids | log_job_ids)
    summary_phase_stale = bool(summary.latest_record is not None and summary.latest_record.phase != plan.runtime_plan.phase)
    plan_newer_than_summary = bool(plan and plan.generated_at > summary.generated_at)
    pending_valid = (
        plan_newer_than_summary
        or summary_phase_stale
        or set(summary.pending_job_ids).issubset(plan_job_ids | log_job_ids)
    )
    checks.append(
        RuntimeAuditCheck(
            check_id="execution_summary_job_ids_match_plan",
            ok=handled_valid and pending_valid,
            message="execution summary handled/pending ids are from current plan or execution history",
            evidence={
                "handled_job_ids": summary.handled_job_ids,
                "pending_job_ids": summary.pending_job_ids,
                "plan_newer_than_summary": plan_newer_than_summary,
                "summary_phase_stale": summary_phase_stale,
            },
        )
    )


def _check_loop_summary(
    summary: RuntimeLoopSummary,
    records: list[RuntimeLoopIterationRecord],
    checks: list[RuntimeAuditCheck],
) -> None:
    counts: dict[str, int] = {}
    for record in records:
        key = record.stop_reason or record.execution_status or "continued"
        counts[key] = counts.get(key, 0) + 1
    latest_ok = (summary.latest_record is None and not records) or (
        summary.latest_record is not None
        and records
        and summary.latest_record.loop_id == records[-1].loop_id
    )


def _check_handoff_summary(
    run_dir: Path,
    summary: RuntimeDelegatedHandoffSummary,
    records: list[RuntimeDelegatedHandoffRecord],
    checks: list[RuntimeAuditCheck],
) -> None:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    latest_ok = (summary.latest_record is None and not records) or (
        summary.latest_record is not None
        and records
        and summary.latest_record.handoff_id == records[-1].handoff_id
    )


def _check_handoff_apply_summary(
    run_dir: Path,
    summary: RuntimeHandoffApplySummary,
    records: list[RuntimeHandoffApplyRecord],
    checks: list[RuntimeAuditCheck],
) -> None:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    latest_ok = (summary.latest_record is None and not records) or (
        summary.latest_record is not None
        and records
        and summary.latest_record.apply_id == records[-1].apply_id
    )
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_handoff_apply_summary_matches_log",
            ok=summary.total_records == len(records) and summary.status_counts == counts and latest_ok,
            message="runtime_handoff_apply_summary.json matches runtime_handoff_apply.jsonl",
            evidence={
                "summary_total_records": summary.total_records,
                "log_record_count": len(records),
                "summary_status_counts": summary.status_counts,
                "log_status_counts": counts,
                "latest_ok": latest_ok,
            },
        )
    )
    missing_checkpoints = [
        record.checkpoint_id
        for record in records
        if record.status == "applied"
        and record.checkpoint_id
        and not _checkpoint_id_exists(run_dir, record.checkpoint_id)
    ]
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_handoff_apply_checkpoints_exist",
            ok=not missing_checkpoints,
            message="applied handoff results have checkpoint records",
            evidence={"missing_checkpoint_ids": missing_checkpoints},
        )
    )
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_handoff_summary_matches_log",
            ok=summary.total_records == len(records) and summary.status_counts == counts and latest_ok,
            message="runtime_handoff_summary.json matches runtime_handoff.jsonl",
            evidence={
                "summary_total_records": summary.total_records,
                "log_record_count": len(records),
                "summary_status_counts": summary.status_counts,
                "log_status_counts": counts,
                "latest_ok": latest_ok,
            },
        )
    )
    missing = [
        record.handoff_json
        for record in records
        if record.status == "planned" and record.handoff_json and not Path(record.handoff_json).exists()
    ]
    escaped = [
        record.handoff_json
        for record in records
        if record.status == "planned"
        and record.handoff_json
        and not _is_relative_to(Path(record.handoff_json), run_dir)
    ]
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_handoff_files_exist",
            ok=not missing and not escaped,
            message="planned delegated handoff JSON files exist inside the run directory",
            evidence={"missing": missing, "escaped": escaped},
        )
    )
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_loop_summary_matches_log",
            ok=summary.total_records == len(records) and summary.status_counts == counts and latest_ok,
            message="runtime_loop_summary.json matches runtime_loop.jsonl",
            evidence={
                "summary_total_records": summary.total_records,
                "log_record_count": len(records),
                "summary_status_counts": summary.status_counts,
                "log_status_counts": counts,
                "latest_ok": latest_ok,
            },
        )
    )


def _check_execution_outputs(
    run_dir: Path,
    state: AgentProjectState,
    records: list[RuntimeJobExecutionRecord],
    checks: list[RuntimeAuditCheck],
) -> None:
    latest_user_text = state.user_turns[-1].text if state.user_turns else ""
    for record in records:
        if not record.output_json:
            continue
        output_path = Path(record.output_json).expanduser().resolve()
        exists = output_path.exists()
        inside_run = _is_relative_to(output_path, run_dir)
        checks.append(
            RuntimeAuditCheck(
                check_id=f"execution_output_exists:{record.execution_id}",
                ok=exists and inside_run,
                message="execution output JSON exists inside the run directory",
                evidence={"output_json": str(output_path), "inside_run_dir": inside_run},
            )
        )
        if not exists:
            continue
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        _check_execution_output_payload(record, payload, latest_user_text, checks)


def _check_apply_summary(
    run_dir: Path,
    summary: RuntimeStateApplySummary,
    records: list[RuntimeStateApplyRecord],
    checks: list[RuntimeAuditCheck],
) -> None:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    latest_ok = (summary.latest_record is None and not records) or (
        summary.latest_record is not None
        and records
        and summary.latest_record.apply_id == records[-1].apply_id
    )
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_apply_summary_matches_log",
            ok=summary.total_records == len(records) and summary.status_counts == counts and latest_ok,
            message="runtime_apply_summary.json matches runtime_apply.jsonl",
            evidence={
                "summary_total_records": summary.total_records,
                "log_record_count": len(records),
                "summary_status_counts": summary.status_counts,
                "log_status_counts": counts,
                "latest_ok": latest_ok,
            },
        )
    )
    missing_checkpoints = [
        record.checkpoint_uri
        for record in records
        if record.status == "applied" and record.checkpoint_uri and not Path(record.checkpoint_uri).exists()
    ]
    escaped_checkpoints = [
        record.checkpoint_uri
        for record in records
        if record.status == "applied"
        and record.checkpoint_uri
        and not _is_relative_to(Path(record.checkpoint_uri), run_dir)
    ]
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_apply_checkpoints_exist",
            ok=not missing_checkpoints and not escaped_checkpoints,
            message="applied runtime state updates have run-local checkpoint snapshots",
            evidence={
                "missing_checkpoints": missing_checkpoints,
                "escaped_checkpoints": escaped_checkpoints,
            },
        )
    )


def _check_execution_output_payload(
    record: RuntimeJobExecutionRecord,
    payload: dict[str, Any],
    latest_user_text: str,
    checks: list[RuntimeAuditCheck],
) -> None:
    job = payload.get("job") or {}
    if "llm_result" in payload:
        _check_llm_output_payload(record, payload, job, latest_user_text, checks)
        return
    if "domain_tool_result" in payload:
        _check_domain_tool_output_payload(record, payload, job, checks)
        return
    checks.append(
        RuntimeAuditCheck(
            check_id=f"execution_output_matches_record:{record.execution_id}",
            ok=payload.get("execution_id") == record.execution_id and job.get("job_id") == record.job_id,
            message="execution output JSON matches execution record and planned job",
            evidence={
                "record_execution_id": record.execution_id,
                "payload_execution_id": payload.get("execution_id"),
                "record_job_id": record.job_id,
                "payload_job_id": job.get("job_id"),
                "payload_keys": sorted(payload.keys()),
            },
        )
    )


def _check_llm_output_payload(
    record: RuntimeJobExecutionRecord,
    payload: dict[str, Any],
    job: dict[str, Any],
    latest_user_text: str,
    checks: list[RuntimeAuditCheck],
) -> None:
    llm_result = payload.get("llm_result") or {}
    context = payload.get("context_json") or {}
    checks.append(
        RuntimeAuditCheck(
            check_id=f"execution_output_matches_record:{record.execution_id}",
            ok=(
                payload.get("execution_id") == record.execution_id
                and job.get("job_id") == record.job_id
                and llm_result.get("node_name") == record.node_name
            ),
            message="execution output JSON matches execution record and planned job",
            evidence={
                "record_execution_id": record.execution_id,
                "payload_execution_id": payload.get("execution_id"),
                "record_job_id": record.job_id,
                "payload_job_id": job.get("job_id"),
                "record_node_name": record.node_name,
                "payload_node_name": llm_result.get("node_name"),
            },
        )
    )
    if record.status == "dry_run":
        checks.append(
            RuntimeAuditCheck(
                check_id=f"dry_run_llm_has_no_state_candidate:{record.execution_id}",
                ok=llm_result.get("dry_run") is True and llm_result.get("parsed_output") is None,
                message="dry-run LLM execution produced prompt evidence but no parsed state candidate",
                evidence={
                    "dry_run": llm_result.get("dry_run"),
                    "has_parsed_output": llm_result.get("parsed_output") is not None,
                    "issues": llm_result.get("issues"),
                },
            )
        )
    if record.node_name == "ReferenceBindingValidator":
        checks.append(
            RuntimeAuditCheck(
                check_id=f"reference_binding_context_uses_latest_user_turn:{record.execution_id}",
                ok=context.get("user_text") == latest_user_text,
                message="ReferenceBindingValidator context user_text comes from latest state user turn",
                evidence={
                    "context_user_text": context.get("user_text"),
                    "latest_state_user_text": latest_user_text,
                },
            )
        )


def _check_domain_tool_output_payload(
    record: RuntimeJobExecutionRecord,
    payload: dict[str, Any],
    job: dict[str, Any],
    checks: list[RuntimeAuditCheck],
) -> None:
    domain_result = payload.get("domain_tool_result") or {}
    operation_plan = domain_result.get("operation_plan") or payload.get("operation_plan") or {}
    payload_domain_tool_name = domain_result.get("domain_tool_name") or operation_plan.get("domain_tool_name")
    checks.append(
        RuntimeAuditCheck(
            check_id=f"execution_output_matches_record:{record.execution_id}",
            ok=(
                payload.get("execution_id") == record.execution_id
                and job.get("job_id") == record.job_id
                and payload_domain_tool_name == record.domain_tool_name
            ),
            message="domain-tool execution output JSON matches execution record and planned job",
            evidence={
                "record_execution_id": record.execution_id,
                "payload_execution_id": payload.get("execution_id"),
                "record_job_id": record.job_id,
                "payload_job_id": job.get("job_id"),
                "record_domain_tool_name": record.domain_tool_name,
                "payload_domain_tool_name": payload_domain_tool_name,
            },
        )
    )
    if record.status == "dry_run":
        checks.append(
            RuntimeAuditCheck(
                check_id=f"dry_run_domain_tool_has_operation_plan:{record.execution_id}",
                ok=(
                    domain_result.get("dry_run") is True
                    and operation_plan.get("ok") is True
                    and bool(operation_plan.get("raw_tool_name"))
                ),
                message="dry-run domain-tool execution produced a safe operation plan",
                evidence={
                    "dry_run": domain_result.get("dry_run"),
                    "operation_plan_ok": operation_plan.get("ok"),
                    "raw_tool_name": operation_plan.get("raw_tool_name"),
                    "issues": operation_plan.get("issues"),
                },
            )
        )


def _check_local_artifact_paths(
    run_dir: Path,
    state: AgentProjectState,
    checks: list[RuntimeAuditCheck],
) -> None:
    missing = []
    escaped = []
    for artifact in state.artifacts:
        uri = artifact.uri
        if not uri or uri.startswith(("http://", "https://")):
            continue
        path = Path(uri).expanduser().resolve()
        if not path.exists():
            missing.append(uri)
        if _looks_run_local(uri) and not _is_relative_to(path, run_dir):
            escaped.append(uri)
    checks.append(
        RuntimeAuditCheck(
            check_id="state_local_artifact_paths_exist",
            ok=not missing and not escaped,
            severity="warning",
            message="local artifact URIs referenced by state exist and run-local artifacts stay inside the run directory",
            evidence={"missing": missing, "escaped_run_local": escaped},
        )
    )


def _read_model(
    path: Path,
    model_type: type[BaseModel],
    checks: list[RuntimeAuditCheck],
    check_id: str,
) -> Any | None:
    if not path.exists():
        checks.append(RuntimeAuditCheck(check_id=check_id, ok=False, message=f"missing required file: {path.name}"))
        return None
    try:
        model = model_type(**json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        checks.append(
            RuntimeAuditCheck(
                check_id=check_id,
                ok=False,
                message=f"{path.name} failed validation",
                evidence={"error": f"{type(exc).__name__}: {exc}"},
            )
        )
        return None
    checks.append(RuntimeAuditCheck(check_id=check_id, ok=True, message=f"{path.name} is valid JSON/schema"))
    return model


def _read_optional_model(
    path: Path,
    model_type: type[BaseModel],
    checks: list[RuntimeAuditCheck],
    check_id: str,
) -> Any | None:
    if not path.exists():
        checks.append(
            RuntimeAuditCheck(
                check_id=check_id,
                ok=True,
                severity="info",
                message=f"optional file is not present yet: {path.name}",
            )
        )
        return None
    return _read_model(path, model_type, checks, check_id)


def _read_execution_records(
    run_dir: Path,
    checks: list[RuntimeAuditCheck],
) -> list[RuntimeJobExecutionRecord]:
    path = run_dir / "runtime_execution.jsonl"
    if not path.exists():
        checks.append(
            RuntimeAuditCheck(
                check_id="runtime_execution_jsonl_valid",
                ok=False,
                severity="warning",
                message="runtime_execution.jsonl is not present yet",
            )
        )
        return []
    records: list[RuntimeJobExecutionRecord] = []
    errors = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(RuntimeJobExecutionRecord(**json.loads(line)))
        except Exception as exc:
            errors.append({"line": index, "error": f"{type(exc).__name__}: {exc}"})
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_execution_jsonl_valid",
            ok=not errors,
            message="runtime_execution.jsonl rows are valid execution records",
            evidence={"record_count": len(records), "errors": errors},
        )
    )
    return records


def _read_apply_records(
    run_dir: Path,
    checks: list[RuntimeAuditCheck],
) -> list[RuntimeStateApplyRecord]:
    path = run_dir / "runtime_apply.jsonl"
    if not path.exists():
        checks.append(
            RuntimeAuditCheck(
                check_id="runtime_apply_jsonl_valid",
                ok=True,
                severity="info",
                message="runtime_apply.jsonl is not present yet",
            )
        )
        return []
    records: list[RuntimeStateApplyRecord] = []
    errors = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(RuntimeStateApplyRecord(**json.loads(line)))
        except Exception as exc:
            errors.append({"line": index, "error": f"{type(exc).__name__}: {exc}"})
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_apply_jsonl_valid",
            ok=not errors,
            message="runtime_apply.jsonl rows are valid apply records",
            evidence={"record_count": len(records), "errors": errors},
        )
    )
    return records


def _read_loop_records(
    run_dir: Path,
    checks: list[RuntimeAuditCheck],
) -> list[RuntimeLoopIterationRecord]:
    path = run_dir / "runtime_loop.jsonl"
    if not path.exists():
        checks.append(
            RuntimeAuditCheck(
                check_id="runtime_loop_jsonl_valid",
                ok=True,
                severity="info",
                message="runtime_loop.jsonl is not present yet",
            )
        )
        return []
    records: list[RuntimeLoopIterationRecord] = []
    errors = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(RuntimeLoopIterationRecord(**json.loads(line)))
        except Exception as exc:
            errors.append({"line": index, "error": f"{type(exc).__name__}: {exc}"})
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_loop_jsonl_valid",
            ok=not errors,
            message="runtime_loop.jsonl rows are valid loop records",
            evidence={"record_count": len(records), "errors": errors},
        )
    )
    return records


def _read_handoff_records(
    run_dir: Path,
    checks: list[RuntimeAuditCheck],
) -> list[RuntimeDelegatedHandoffRecord]:
    path = run_dir / "runtime_handoff.jsonl"
    if not path.exists():
        checks.append(
            RuntimeAuditCheck(
                check_id="runtime_handoff_jsonl_valid",
                ok=True,
                severity="info",
                message="runtime_handoff.jsonl is not present yet",
            )
        )
        return []
    records: list[RuntimeDelegatedHandoffRecord] = []
    errors = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(RuntimeDelegatedHandoffRecord(**json.loads(line)))
        except Exception as exc:
            errors.append({"line": index, "error": f"{type(exc).__name__}: {exc}"})
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_handoff_jsonl_valid",
            ok=not errors,
            message="runtime_handoff.jsonl rows are valid delegated handoff records",
            evidence={"record_count": len(records), "errors": errors},
        )
    )
    return records


def _read_handoff_apply_records(
    run_dir: Path,
    checks: list[RuntimeAuditCheck],
) -> list[RuntimeHandoffApplyRecord]:
    path = run_dir / "runtime_handoff_apply.jsonl"
    if not path.exists():
        checks.append(
            RuntimeAuditCheck(
                check_id="runtime_handoff_apply_jsonl_valid",
                ok=True,
                severity="info",
                message="runtime_handoff_apply.jsonl is not present yet",
            )
        )
        return []
    records: list[RuntimeHandoffApplyRecord] = []
    errors = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(RuntimeHandoffApplyRecord(**json.loads(line)))
        except Exception as exc:
            errors.append({"line": index, "error": f"{type(exc).__name__}: {exc}"})
    checks.append(
        RuntimeAuditCheck(
            check_id="runtime_handoff_apply_jsonl_valid",
            ok=not errors,
            message="runtime_handoff_apply.jsonl rows are valid handoff apply records",
            evidence={"record_count": len(records), "errors": errors},
        )
    )
    return records


def _read_optional_jsonl(
    path: Path,
    checks: list[RuntimeAuditCheck],
    check_id: str,
) -> list[dict[str, Any]]:
    if not path.exists():
        checks.append(
            RuntimeAuditCheck(
                check_id=check_id,
                ok=True,
                severity="info",
                message=f"optional jsonl file is not present: {path.name}",
            )
        )
        return []
    rows = []
    errors = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                rows.append(parsed)
            else:
                errors.append({"line": index, "error": "JSONL row root is not an object"})
        except Exception as exc:
            errors.append({"line": index, "error": f"{type(exc).__name__}: {exc}"})
    checks.append(
        RuntimeAuditCheck(
            check_id=check_id,
            ok=not errors,
            message=f"{path.name} rows are valid JSON objects",
            evidence={"row_count": len(rows), "errors": errors},
        )
    )
    return rows


def _unbound_image_ids(state: AgentProjectState) -> list[str]:
    image_ids = {image.image_id for image in state.input_images}
    bound = {binding.image_id for binding in state.reference_bindings if binding.explicit_in_user_text}
    return sorted(image_ids - bound)


def _looks_run_local(uri: str) -> bool:
    return "runtime_console/" in uri or "artifacts/" in uri or "runtime_execution/" in uri


def _checkpoint_id_exists(run_dir: Path, checkpoint_id: str) -> bool:
    path = run_dir / "checkpoints" / "checkpoints.jsonl"
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            if json.loads(line).get("checkpoint_id") == checkpoint_id:
                return True
        except Exception:
            continue
    return False


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a runtime run directory by reading its JSON/file outputs.")
    parser.add_argument("run_dir", help="Path to outputs/runs/<run_id> or a stage directory.")
    parser.add_argument("--json", action="store_true", help="Print full JSON audit result.")
    args = parser.parse_args()

    result = audit_runtime_run(args.run_dir)
    if args.json:
        print(json.dumps(_model_to_dict(result), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"ok={result.ok} errors={result.error_count} warnings={result.warning_count} run_dir={result.run_dir}")
        for check in result.checks:
            status = "ok" if check.ok else check.severity
            print(f"{status}\t{check.check_id}\t{check.message}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
