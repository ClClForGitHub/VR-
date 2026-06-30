"""Bounded runtime loop for the V1 console.

The loop is intentionally conservative: it executes one planned job at a time,
applies supported completed candidates, rebuilds the plan after state mutation,
and stops at user gates, delegated work, failures, or a caller-provided step
budget.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.domain_dispatcher import RawBlenderMCPToolCaller
from agent_runtime.llm_providers import LLMProviderConfig
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan, read_runtime_dispatch_plan
from agent_runtime.runtime_execution import RuntimeExecutionStepResult, execute_next_runtime_job
from agent_runtime.runtime_state_apply import RuntimeStateApplyResult, apply_next_runtime_candidate


RuntimeLoopStopReason = Literal[
    "completed_no_jobs",
    "waiting_user",
    "delegated",
    "blocked",
    "failed",
    "dry_run_needs_live_or_fixture",
    "max_steps",
]


class RuntimeLoopIterationRecord(BaseModel):
    loop_id: str
    iteration: int
    created_at: str
    run_dir: str
    stop_reason: RuntimeLoopStopReason | None = None
    execution_id: str | None = None
    job_id: str | None = None
    job_kind: str | None = None
    node_name: str | None = None
    domain_tool_name: str | None = None
    execution_status: str | None = None
    execution_ok: bool | None = None
    apply_id: str | None = None
    apply_status: str | None = None
    apply_ok: bool | None = None
    applied_fields: list[str] = Field(default_factory=list)
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


class RuntimeLoopSummary(BaseModel):
    run_dir: str
    generated_at: str
    loop_log_jsonl: str
    total_records: int = 0
    stop_reason: RuntimeLoopStopReason | None = None
    latest_record: RuntimeLoopIterationRecord | None = None
    completed_iterations: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)


class RuntimeLoopResult(BaseModel):
    ok: bool
    run_dir: str
    runtime_plan_json: str
    loop_log_jsonl: str
    loop_summary_json: str
    stop_reason: RuntimeLoopStopReason
    iterations: list[RuntimeLoopIterationRecord] = Field(default_factory=list)
    summary: RuntimeLoopSummary
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


TERMINAL_EXECUTION_STATUS_TO_REASON: dict[str, RuntimeLoopStopReason] = {
    "waiting_user": "waiting_user",
    "delegated": "delegated",
    "blocked": "blocked",
    "failed": "failed",
    "dry_run": "dry_run_needs_live_or_fixture",
}


def run_bounded_runtime_loop(
    run_dir: str | Path,
    *,
    max_steps: int = 8,
    dry_run: bool = True,
    provider_configs: list[LLMProviderConfig] | None = None,
    env: dict[str, str] | None = None,
    response_text_by_node: dict[str, str] | None = None,
    blender_raw_tool_caller: RawBlenderMCPToolCaller | None = None,
    blender_raw_caller_source: str | None = None,
) -> RuntimeLoopResult:
    """Run bounded ``execute -> apply -> rebuild plan`` iterations.

    ``response_text_by_node`` is the dev/test seam for real parser semantics:
    supplied node JSON is parsed and validated by ``run_llm_node`` exactly like
    provider output, but no network call is made for those nodes.
    """

    path = Path(run_dir).expanduser().resolve()
    if max_steps < 1:
        raise ValueError("max_steps must be >= 1")
    if not (path / "state.json").exists():
        raise FileNotFoundError(f"state.json not found for runtime loop: {path / 'state.json'}")

    if read_runtime_dispatch_plan(path) is None:
        build_and_save_runtime_dispatch_plan(path)

    loop_records: list[RuntimeLoopIterationRecord] = []
    stop_reason: RuntimeLoopStopReason | None = None
    issues: list[str] = []
    message: str | None = None

    for iteration in range(1, max_steps + 1):
        step = execute_next_runtime_job(
            path,
            dry_run=dry_run,
            provider_configs=provider_configs,
            env=env,
            response_text_by_node=response_text_by_node,
            blender_raw_tool_caller=blender_raw_tool_caller,
            blender_raw_caller_source=blender_raw_caller_source,
        )
        record = _record_from_step(path, iteration=iteration, step=step)

        if step.record is None:
            stop_reason = "completed_no_jobs"
            record.stop_reason = stop_reason
            record.message = step.message
            _append_loop_record(path, record)
            loop_records.append(record)
            message = step.message
            break

        if step.record.status == "completed":
            apply_result = apply_next_runtime_candidate(path, rebuild_plan=True)
            _merge_apply_result(record, apply_result)
            _append_loop_record(path, record)
            loop_records.append(record)
            if apply_result.record is not None and not apply_result.ok:
                stop_reason = "failed"
                record.stop_reason = stop_reason
                issues.extend(apply_result.issues)
                message = apply_result.message
                break
            continue

        stop_reason = TERMINAL_EXECUTION_STATUS_TO_REASON.get(step.record.status, "failed")
        record.stop_reason = stop_reason
        _append_loop_record(path, record)
        loop_records.append(record)
        issues.extend(step.issues)
        message = step.message
        break

    if stop_reason is None:
        stop_reason = "max_steps"
        message = f"stopped after max_steps={max_steps}"
        if loop_records:
            loop_records[-1].stop_reason = stop_reason
            _rewrite_loop_records(path, read_runtime_loop_records(path)[:-1] + [loop_records[-1]])

    all_records = read_runtime_loop_records(path)
    summary = _write_loop_summary(path, all_records, stop_reason=stop_reason)
    return RuntimeLoopResult(
        ok=stop_reason not in {"blocked", "failed"},
        run_dir=str(path),
        runtime_plan_json=str(path / "runtime_plan.json"),
        loop_log_jsonl=str(_loop_log_path(path)),
        loop_summary_json=str(_loop_summary_path(path)),
        stop_reason=stop_reason,
        iterations=loop_records,
        summary=summary,
        message=message,
        issues=issues,
    )


def read_runtime_loop_records(run_dir: str | Path, *, limit: int | None = None) -> list[RuntimeLoopIterationRecord]:
    path = _loop_log_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return []
    records = [
        RuntimeLoopIterationRecord(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:] if limit is not None else records


def read_runtime_loop_summary(run_dir: str | Path) -> dict[str, Any] | None:
    path = _loop_summary_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _record_from_step(
    run_dir: Path,
    *,
    iteration: int,
    step: RuntimeExecutionStepResult,
) -> RuntimeLoopIterationRecord:
    execution = step.record
    return RuntimeLoopIterationRecord(
        loop_id=f"loop_{uuid4().hex[:12]}",
        iteration=iteration,
        created_at=utc_now_iso(),
        run_dir=str(run_dir),
        execution_id=execution.execution_id if execution is not None else None,
        job_id=execution.job_id if execution is not None else step.selected_job_id,
        job_kind=execution.job_kind if execution is not None else None,
        node_name=execution.node_name if execution is not None else None,
        domain_tool_name=execution.domain_tool_name if execution is not None else None,
        execution_status=execution.status if execution is not None else None,
        execution_ok=execution.ok if execution is not None else step.ok,
        message=step.message,
        issues=list(step.issues),
    )


def _merge_apply_result(record: RuntimeLoopIterationRecord, apply_result: RuntimeStateApplyResult) -> None:
    apply_record = apply_result.record
    record.apply_id = apply_record.apply_id if apply_record is not None else None
    record.apply_status = apply_record.status if apply_record is not None else apply_result.message
    record.apply_ok = apply_record.ok if apply_record is not None else apply_result.ok
    record.applied_fields = list(apply_record.applied_fields) if apply_record is not None else []
    if apply_result.issues:
        record.issues.extend(apply_result.issues)


def _write_loop_summary(
    run_dir: Path,
    records: list[RuntimeLoopIterationRecord],
    *,
    stop_reason: RuntimeLoopStopReason | None,
) -> RuntimeLoopSummary:
    counts: dict[str, int] = {}
    for record in records:
        key = record.stop_reason or record.execution_status or "continued"
        counts[key] = counts.get(key, 0) + 1
    summary = RuntimeLoopSummary(
        run_dir=str(run_dir),
        generated_at=utc_now_iso(),
        loop_log_jsonl=str(_loop_log_path(run_dir)),
        total_records=len(records),
        stop_reason=stop_reason,
        latest_record=records[-1] if records else None,
        completed_iterations=len([record for record in records if record.execution_status == "completed"]),
        status_counts=counts,
    )
    _write_json(_loop_summary_path(run_dir), _model_to_dict(summary))
    return summary


def _append_loop_record(run_dir: Path, record: RuntimeLoopIterationRecord) -> None:
    path = _loop_log_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_model_to_dict(record), ensure_ascii=False, sort_keys=True) + "\n")


def _rewrite_loop_records(run_dir: Path, records: list[RuntimeLoopIterationRecord]) -> None:
    path = _loop_log_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_model_to_dict(record), ensure_ascii=False, sort_keys=True) + "\n")


def _loop_log_path(run_dir: Path) -> Path:
    return run_dir / "runtime_loop.jsonl"


def _loop_summary_path(run_dir: Path) -> Path:
    return run_dir / "runtime_loop_summary.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
