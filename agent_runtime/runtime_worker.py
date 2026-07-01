"""Execute planned delegated handoffs through bounded worker adapters.

This module sits between ``runtime_delegation`` and ``runtime_handoff_apply``.
It does not create another state store: worker attempts are logged, and any
state mutation still flows through the existing handoff-apply functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.codex_self_mcp import CodexSelfMCPAdapter, extract_last_image_from_codex_mcp_log
from agent_runtime.concept_image_execution import (
    CodexSelfMCPConceptImageBackend,
    ConceptImageBackend,
    execute_concept_image_handoff,
)
from agent_runtime.runtime_delegation import RuntimeDelegatedHandoffRecord, read_runtime_handoff_records
from agent_runtime.runtime_handoff_apply import (
    RuntimeHandoffApplyResult,
    apply_blender_assembly_result,
    apply_concept_handoff_result,
    apply_scene_asset_handoff_result,
    apply_subject_asset_handoff_result,
)


RuntimeWorkerBackend = Literal["fixture", "codex_self_mcp", "codex_self_log", "live_image"]
RuntimeWorkerStatus = Literal["dry_run", "applied", "completed", "skipped", "failed"]


class RuntimeWorkerExecutionRecord(BaseModel):
    worker_id: str
    handoff_id: str | None = None
    execution_id: str | None = None
    job_id: str | None = None
    domain_tool_name: str | None = None
    backend: RuntimeWorkerBackend
    status: RuntimeWorkerStatus
    ok: bool
    created_at: str
    dry_run: bool = True
    worker_json: str | None = None
    apply_id: str | None = None
    apply_status: str | None = None
    applied_artifact_ids: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)


class RuntimeWorkerSummary(BaseModel):
    run_dir: str
    generated_at: str
    worker_log_jsonl: str
    total_records: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    latest_record: RuntimeWorkerExecutionRecord | None = None
    handled_handoff_ids: list[str] = Field(default_factory=list)


class RuntimeWorkerExecutionResult(BaseModel):
    ok: bool
    run_dir: str
    worker_log_jsonl: str
    worker_summary_json: str
    selected_handoff_id: str | None = None
    record: RuntimeWorkerExecutionRecord | None = None
    summary: RuntimeWorkerSummary
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


HANDLED_WORKER_STATUSES = {"applied", "completed"}
CONCEPT_TOOLS = {"generate_concept_images", "regenerate_concept_images"}


def execute_next_runtime_worker(
    run_dir: str | Path,
    *,
    backend: RuntimeWorkerBackend = "fixture",
    dry_run: bool = True,
    fixture_payload: dict[str, Any] | None = None,
    handoff_id: str | None = None,
    rebuild_plan: bool = True,
    codex_adapter: CodexSelfMCPAdapter | None = None,
    concept_image_backend: ConceptImageBackend | None = None,
    confirm_execute: bool = False,
    timeout_seconds: float = 300,
) -> RuntimeWorkerExecutionResult:
    """Execute or dry-run the next planned delegated handoff.

    ``fixture`` backend is the deterministic local adapter used by tests and by
    manual result registration. ``codex_self_mcp`` plans or executes the local
    codex-self channel, but non-dry-run execution still requires
    ``confirm_execute=True``. ``codex_self_log`` ingests a completed codex-self
    MCP JSONL log and extracts its final generated image through the existing
    log decoder.
    """

    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for runtime worker: {state_path}")

    records = read_runtime_worker_records(path)
    selected = _select_handoff(
        read_runtime_handoff_records(path),
        handled=_handled_handoff_ids(records),
        handoff_id=handoff_id,
    )
    if selected is None:
        summary = _write_worker_summary(path, records)
        return RuntimeWorkerExecutionResult(
            ok=True,
            run_dir=str(path),
            worker_log_jsonl=str(_worker_log_path(path)),
            worker_summary_json=str(_worker_summary_path(path)),
            summary=summary,
            message="no_planned_handoff_for_worker",
        )

    if backend == "fixture":
        record = _execute_fixture_worker(
            path,
            handoff=selected,
            dry_run=dry_run,
            fixture_payload=fixture_payload or {},
            rebuild_plan=rebuild_plan,
        )
    elif backend == "codex_self_mcp":
        record = _execute_codex_self_worker(
            path,
            handoff=selected,
            dry_run=dry_run,
            adapter=codex_adapter or CodexSelfMCPAdapter(),
            confirm_execute=confirm_execute,
            timeout_seconds=timeout_seconds,
            rebuild_plan=rebuild_plan,
        )
    elif backend == "live_image":
        record = _execute_live_image_worker(
            path,
            handoff=selected,
            dry_run=dry_run,
            concept_backend=concept_image_backend
            or CodexSelfMCPConceptImageBackend(timeout_seconds=timeout_seconds),
            confirm_execute=confirm_execute,
            rebuild_plan=rebuild_plan,
        )
    elif backend == "codex_self_log":
        record = _execute_codex_self_log_worker(
            path,
            handoff=selected,
            dry_run=dry_run,
            payload=fixture_payload or {},
            rebuild_plan=rebuild_plan,
        )
    else:  # pragma: no cover - Literal keeps ordinary callers out.
        raise ValueError(f"unsupported runtime worker backend: {backend}")

    _append_jsonl(_worker_log_path(path), _model_to_dict(record))
    records.append(record)
    summary = _write_worker_summary(path, records)
    return RuntimeWorkerExecutionResult(
        ok=record.ok,
        run_dir=str(path),
        worker_log_jsonl=str(_worker_log_path(path)),
        worker_summary_json=str(_worker_summary_path(path)),
        selected_handoff_id=selected.handoff_id,
        record=record,
        summary=summary,
        message=record.status,
        issues=list(record.issues),
    )


def read_runtime_worker_records(run_dir: str | Path, *, limit: int | None = None) -> list[RuntimeWorkerExecutionRecord]:
    path = _worker_log_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return []
    records = [
        RuntimeWorkerExecutionRecord(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:] if limit is not None else records


def read_runtime_worker_summary(run_dir: str | Path) -> dict[str, Any] | None:
    path = _worker_summary_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _execute_fixture_worker(
    run_dir: Path,
    *,
    handoff: RuntimeDelegatedHandoffRecord,
    dry_run: bool,
    fixture_payload: dict[str, Any],
    rebuild_plan: bool,
) -> RuntimeWorkerExecutionRecord:
    worker_id = f"worker_{uuid4().hex[:12]}"
    worker_payload = _worker_payload(
        run_dir,
        worker_id=worker_id,
        backend="fixture",
        handoff=handoff,
        request_payload=fixture_payload,
    )
    if dry_run:
        worker_payload["dry_run"] = True
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="fixture",
            dry_run=True,
            status="dry_run",
            ok=True,
            worker_json=worker_json,
            issues=["fixture_worker_dry_run_no_state_mutation"],
            result_summary={"accepted_payload_keys": sorted(fixture_payload.keys())},
        )

    apply_payload, issues = _apply_payload_for_handoff(handoff, fixture_payload)
    if issues:
        worker_payload["issues"] = issues
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="fixture",
            dry_run=False,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=issues,
        )

    apply_result = _apply_worker_payload(run_dir, handoff=handoff, payload=apply_payload, rebuild_plan=rebuild_plan)
    worker_payload["apply_payload"] = apply_payload
    worker_payload["apply_result"] = _model_to_dict(apply_result)
    worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
    return _record_from_apply(
        worker_id=worker_id,
        handoff=handoff,
        backend="fixture",
        worker_json=worker_json,
        apply_result=apply_result,
    )


def _execute_live_image_worker(
    run_dir: Path,
    *,
    handoff: RuntimeDelegatedHandoffRecord,
    dry_run: bool,
    concept_backend: ConceptImageBackend,
    confirm_execute: bool,
    rebuild_plan: bool,
) -> RuntimeWorkerExecutionRecord:
    worker_id = f"worker_{uuid4().hex[:12]}"
    handoff_payload = _read_handoff_json(handoff)
    worker_payload = _worker_payload(
        run_dir,
        worker_id=worker_id,
        backend="live_image",
        handoff=handoff,
        request_payload={
            "backend": getattr(concept_backend, "backend_name", "concept_image_backend"),
            "confirm_execute": confirm_execute,
        },
    )

    if handoff.domain_tool_name not in CONCEPT_TOOLS:
        issue = f"live_image_worker_unsupported_domain_tool:{handoff.domain_tool_name}"
        worker_payload["issues"] = [issue]
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="live_image",
            dry_run=dry_run,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=[issue],
        )

    if dry_run or not confirm_execute:
        execution_result = execute_concept_image_handoff(
            run_dir=run_dir,
            handoff_payload=handoff_payload,
            backend=concept_backend,
            handoff_id=handoff.handoff_id,
            dry_run=True,
        )
        issues = ["live_image_worker_dry_run_no_state_mutation"] if dry_run else ["live_image_worker_requires_confirm_execute"]
        worker_payload["dry_run"] = True
        worker_payload["issues"] = issues
        worker_payload["execution_result"] = _model_to_dict(execution_result)
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="live_image",
            dry_run=True,
            status="dry_run",
            ok=True,
            worker_json=worker_json,
            issues=issues,
            result_summary={
                "live_generation_calls_jsonl": execution_result.live_generation_calls_jsonl,
                "call_count": len(execution_result.call_records),
                "successful_call_count": sum(1 for record in execution_result.call_records if record.ok),
                "backend": execution_result.backend,
            },
        )

    execution_result = execute_concept_image_handoff(
        run_dir=run_dir,
        handoff_payload=handoff_payload,
        backend=concept_backend,
        handoff_id=handoff.handoff_id,
        dry_run=False,
    )
    worker_payload["execution_result"] = _model_to_dict(execution_result)
    if not execution_result.ok or not execution_result.image_results:
        issues = list(execution_result.issues) or ["live_image_worker_no_generated_images"]
        worker_payload["issues"] = issues
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="live_image",
            dry_run=False,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=issues,
            result_summary={
                "live_generation_calls_jsonl": execution_result.live_generation_calls_jsonl,
                "call_count": len(execution_result.call_records),
                "successful_call_count": sum(1 for record in execution_result.call_records if record.ok),
                "backend": execution_result.backend,
                "status": execution_result.status,
                "capability": execution_result.capability,
            },
        )

    apply_payload = {"image_results": execution_result.image_results}
    apply_result = _apply_worker_payload(run_dir, handoff=handoff, payload=apply_payload, rebuild_plan=rebuild_plan)
    worker_payload["apply_payload"] = apply_payload
    worker_payload["apply_result"] = _model_to_dict(apply_result)
    worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
    record = _record_from_apply(
        worker_id=worker_id,
        handoff=handoff,
        backend="live_image",
        worker_json=worker_json,
        apply_result=apply_result,
    )
    record.result_summary.update(
        {
            "live_generation_calls_jsonl": execution_result.live_generation_calls_jsonl,
            "call_count": len(execution_result.call_records),
            "successful_call_count": sum(1 for item in execution_result.call_records if item.ok),
            "backend": execution_result.backend,
            "status": execution_result.status,
        }
    )
    return record


def _execute_codex_self_worker(
    run_dir: Path,
    *,
    handoff: RuntimeDelegatedHandoffRecord,
    dry_run: bool,
    adapter: CodexSelfMCPAdapter,
    confirm_execute: bool,
    timeout_seconds: float,
    rebuild_plan: bool,
) -> RuntimeWorkerExecutionRecord:
    worker_id = f"worker_{uuid4().hex[:12]}"
    handoff_payload = _read_handoff_json(handoff)
    task_prompt = str(handoff_payload.get("task_prompt") or "")
    worker_dir = run_dir / "runtime_worker"
    worker_dir.mkdir(parents=True, exist_ok=True)
    log_path = worker_dir / f"{worker_id}_codex_self.jsonl"
    image_path = worker_dir / f"{worker_id}_concept.png" if handoff.domain_tool_name in CONCEPT_TOOLS else None
    sandbox = "read-only" if handoff.domain_tool_name in CONCEPT_TOOLS else "workspace-write"
    plan = adapter.build_call_plan(
        prompt=task_prompt,
        cwd=run_dir,
        sandbox=sandbox,
        approval_policy="never",
        timeout_seconds=timeout_seconds,
        log_path=log_path,
        extract_last_image_to=image_path,
    )
    worker_payload = _worker_payload(
        run_dir,
        worker_id=worker_id,
        backend="codex_self_mcp",
        handoff=handoff,
        request_payload={"call_plan": _model_to_dict(plan)},
    )
    if dry_run or not confirm_execute:
        issues = ["codex_self_worker_dry_run_no_state_mutation"] if dry_run else ["codex_self_worker_requires_confirm_execute"]
        worker_payload["dry_run"] = dry_run
        worker_payload["issues"] = issues
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_mcp",
            dry_run=dry_run,
            status="dry_run",
            ok=True,
            worker_json=worker_json,
            issues=issues,
            result_summary={"call_plan": _model_to_dict(plan)},
        )

    execution_issues = _codex_self_concept_execution_issues(handoff_payload)
    if execution_issues:
        worker_payload["issues"] = execution_issues
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_mcp",
            dry_run=False,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=execution_issues,
            result_summary={
                "call_plan": _model_to_dict(plan),
                "reason": "codex_self_mcp_not_sufficient_for_structured_concept_handoff",
            },
        )

    run_result = adapter.run_call_plan(plan)
    worker_payload["run_result"] = _model_to_dict(run_result)
    if not run_result.ok:
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_mcp",
            dry_run=False,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=list(run_result.issues),
            result_summary={"returncode": run_result.returncode},
        )

    if handoff.domain_tool_name in CONCEPT_TOOLS and image_path is not None and image_path.exists():
        apply_payload = {
            "image_results": [
                    {
                        "image_path": str(image_path),
                        "subject_id": _first_subject_id(handoff_payload),
                        "artifact_id": f"{handoff.job_id or 'concept'}_{worker_id}",
                        "output_type": "subject_concept",
                        "final_preview": True,
                    }
                ]
        }
        apply_result = _apply_worker_payload(run_dir, handoff=handoff, payload=apply_payload, rebuild_plan=rebuild_plan)
        worker_payload["apply_payload"] = apply_payload
        worker_payload["apply_result"] = _model_to_dict(apply_result)
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_from_apply(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_mcp",
            worker_json=worker_json,
            apply_result=apply_result,
        )

    if handoff.domain_tool_name in CONCEPT_TOOLS:
        worker_payload["issues"] = ["codex_self_worker_missing_extracted_image"]
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_mcp",
            dry_run=False,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=["codex_self_worker_missing_extracted_image"],
            result_summary={"returncode": run_result.returncode, "image_extracted": False},
        )

    worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
    return _record_common(
        worker_id=worker_id,
        handoff=handoff,
        backend="codex_self_mcp",
        dry_run=False,
        status="completed",
        ok=True,
        worker_json=worker_json,
        result_summary={"returncode": run_result.returncode, "image_extracted": False},
    )


def _codex_self_concept_execution_issues(handoff_payload: dict[str, Any]) -> list[str]:
    execution = handoff_payload.get("execution") if isinstance(handoff_payload, dict) else {}
    domain_tool_name = execution.get("domain_tool_name") if isinstance(execution, dict) else None
    if domain_tool_name not in CONCEPT_TOOLS:
        return []
    concept_generation = handoff_payload.get("concept_generation")
    if not isinstance(concept_generation, dict):
        return []
    requirements = concept_generation.get("requirements") or []
    if not isinstance(requirements, list):
        return ["codex_self_worker_invalid_concept_generation_requirements"]

    issues = []
    if len(requirements) != 1:
        issues.append("codex_self_worker_cannot_execute_multi_requirement_concept_handoff")
    for requirement in requirements:
        if not isinstance(requirement, dict):
            issues.append("codex_self_worker_invalid_concept_requirement")
            continue
        requirement_id = requirement.get("requirement_id") or "unknown_requirement"
        if requirement.get("must_use_image_inputs") or requirement.get("input_reference_image_ids"):
            issues.append(f"codex_self_worker_cannot_attach_required_input_images:{requirement_id}")
        if requirement.get("source_requirement_ids"):
            issues.append(f"codex_self_worker_cannot_resolve_source_requirement_images:{requirement_id}")
    return issues


def _execute_codex_self_log_worker(
    run_dir: Path,
    *,
    handoff: RuntimeDelegatedHandoffRecord,
    dry_run: bool,
    payload: dict[str, Any],
    rebuild_plan: bool,
) -> RuntimeWorkerExecutionRecord:
    worker_id = f"worker_{uuid4().hex[:12]}"
    handoff_payload = _read_handoff_json(handoff)
    log_path = Path(str(payload.get("log_path") or "")).expanduser() if payload.get("log_path") else None
    default_image_path = run_dir / "runtime_worker" / f"{worker_id}_concept.png"
    image_path = Path(str(payload.get("extract_last_image_to") or default_image_path)).expanduser()
    worker_payload = _worker_payload(
        run_dir,
        worker_id=worker_id,
        backend="codex_self_log",
        handoff=handoff,
        request_payload={
            "log_path": str(log_path) if log_path is not None else None,
            "extract_last_image_to": str(image_path),
            "subject_id": payload.get("subject_id") or _first_subject_id(handoff_payload),
            "output_type": payload.get("output_type", "subject_concept"),
            "requirement_id": payload.get("requirement_id"),
            "target_id": payload.get("target_id"),
            "artifact_id": payload.get("artifact_id"),
            "final_preview": payload.get("final_preview", True),
        },
    )

    if dry_run:
        worker_payload["dry_run"] = True
        worker_payload["issues"] = ["codex_self_log_worker_dry_run_no_state_mutation"]
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_log",
            dry_run=True,
            status="dry_run",
            ok=True,
            worker_json=worker_json,
            issues=["codex_self_log_worker_dry_run_no_state_mutation"],
            result_summary={
                "log_path": str(log_path) if log_path is not None else None,
                "extract_last_image_to": str(image_path),
            },
        )

    if handoff.domain_tool_name not in CONCEPT_TOOLS:
        issue = f"codex_self_log_worker_unsupported_domain_tool:{handoff.domain_tool_name}"
        worker_payload["issues"] = [issue]
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_log",
            dry_run=False,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=[issue],
        )

    if log_path is None or not log_path.exists():
        worker_payload["issues"] = ["codex_self_log_worker_missing_log_path"]
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_log",
            dry_run=False,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=["codex_self_log_worker_missing_log_path"],
            result_summary={"log_path": str(log_path) if log_path is not None else None},
        )

    extract_result = extract_last_image_from_codex_mcp_log(log_path, image_path)
    worker_payload["extract_result"] = _model_to_dict(extract_result)
    if not extract_result.ok:
        worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
        return _record_common(
            worker_id=worker_id,
            handoff=handoff,
            backend="codex_self_log",
            dry_run=False,
            status="failed",
            ok=False,
            worker_json=worker_json,
            issues=list(extract_result.issues) or ["codex_self_log_worker_extract_failed"],
            error=extract_result.error,
            result_summary={"log_path": str(log_path), "image_extracted": False},
        )

    apply_payload = {
        "image_results": [
            {
                "image_path": extract_result.output_path,
                "subject_id": payload.get("subject_id") or _first_subject_id(handoff_payload),
                "artifact_id": payload.get("artifact_id") or f"{handoff.job_id or 'concept'}_{worker_id}",
                "output_type": payload.get("output_type", "subject_concept"),
                "requirement_id": payload.get("requirement_id"),
                "target_id": payload.get("target_id"),
                "final_preview": bool(payload.get("final_preview", True)),
            }
        ]
    }
    apply_result = _apply_worker_payload(run_dir, handoff=handoff, payload=apply_payload, rebuild_plan=rebuild_plan)
    worker_payload["apply_payload"] = apply_payload
    worker_payload["apply_result"] = _model_to_dict(apply_result)
    worker_json = _write_worker_json(run_dir, worker_id, worker_payload)
    return _record_from_apply(
        worker_id=worker_id,
        handoff=handoff,
        backend="codex_self_log",
        worker_json=worker_json,
        apply_result=apply_result,
    )


def _apply_payload_for_handoff(
    handoff: RuntimeDelegatedHandoffRecord,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    tool = handoff.domain_tool_name
    if tool in CONCEPT_TOOLS:
        if not payload.get("image_results"):
            return {}, ["fixture_worker_missing_image_results"]
        return {"image_results": payload.get("image_results") or []}, []
    if tool == "build_subject_asset":
        if not payload.get("asset_results"):
            return {}, ["fixture_worker_missing_asset_results"]
        return {"asset_results": payload.get("asset_results") or []}, []
    if tool == "build_scene_asset":
        if not payload.get("scene_asset_results"):
            return {}, ["fixture_worker_missing_scene_asset_results"]
        return {"scene_asset_results": payload.get("scene_asset_results") or []}, []
    if payload.get("blender_results"):
        return {"blender_results": payload.get("blender_results") or []}, []
    return {}, [f"unsupported_fixture_worker_domain_tool:{tool}"]


def _apply_worker_payload(
    run_dir: Path,
    *,
    handoff: RuntimeDelegatedHandoffRecord,
    payload: dict[str, Any],
    rebuild_plan: bool,
) -> RuntimeHandoffApplyResult:
    if payload.get("blender_results"):
        return apply_blender_assembly_result(
            run_dir,
            handoff_id=handoff.handoff_id,
            blender_results=payload.get("blender_results") or [],
            rebuild_plan=rebuild_plan,
        )
    if payload.get("scene_asset_results"):
        return apply_scene_asset_handoff_result(
            run_dir,
            handoff_id=handoff.handoff_id,
            scene_asset_results=payload.get("scene_asset_results") or [],
            rebuild_plan=rebuild_plan,
        )
    if payload.get("asset_results"):
        return apply_subject_asset_handoff_result(
            run_dir,
            handoff_id=handoff.handoff_id,
            asset_results=payload.get("asset_results") or [],
            rebuild_plan=rebuild_plan,
        )
    return apply_concept_handoff_result(
        run_dir,
        handoff_id=handoff.handoff_id,
        image_results=payload.get("image_results") or [],
        rebuild_plan=rebuild_plan,
    )


def _record_from_apply(
    *,
    worker_id: str,
    handoff: RuntimeDelegatedHandoffRecord,
    backend: RuntimeWorkerBackend,
    worker_json: Path,
    apply_result: RuntimeHandoffApplyResult,
) -> RuntimeWorkerExecutionRecord:
    apply_record = apply_result.record
    issues = list(apply_result.issues)
    status: RuntimeWorkerStatus = "applied" if apply_result.ok and apply_record is not None and apply_record.status == "applied" else "failed"
    return _record_common(
        worker_id=worker_id,
        handoff=handoff,
        backend=backend,
        dry_run=False,
        status=status,
        ok=apply_result.ok,
        worker_json=worker_json,
        apply_id=apply_record.apply_id if apply_record is not None else None,
        apply_status=apply_record.status if apply_record is not None else None,
        applied_artifact_ids=list(apply_record.artifact_ids) if apply_record is not None else [],
        issues=issues,
        result_summary={
            "apply_message": apply_result.message,
            "checkpoint_id": apply_record.checkpoint_id if apply_record is not None else None,
        },
    )


def _record_common(
    *,
    worker_id: str,
    handoff: RuntimeDelegatedHandoffRecord,
    backend: RuntimeWorkerBackend,
    dry_run: bool,
    status: RuntimeWorkerStatus,
    ok: bool,
    worker_json: str | Path | None,
    apply_id: str | None = None,
    apply_status: str | None = None,
    applied_artifact_ids: list[str] | None = None,
    issues: list[str] | None = None,
    error: str | None = None,
    result_summary: dict[str, Any] | None = None,
) -> RuntimeWorkerExecutionRecord:
    return RuntimeWorkerExecutionRecord(
        worker_id=worker_id,
        handoff_id=handoff.handoff_id,
        execution_id=handoff.execution_id,
        job_id=handoff.job_id,
        domain_tool_name=handoff.domain_tool_name,
        backend=backend,
        status=status,
        ok=ok,
        created_at=utc_now_iso(),
        dry_run=dry_run,
        worker_json=str(worker_json) if worker_json is not None else None,
        apply_id=apply_id,
        apply_status=apply_status,
        applied_artifact_ids=applied_artifact_ids or [],
        issues=issues or [],
        error=error,
        result_summary=result_summary or {},
    )


def _select_handoff(
    records: list[RuntimeDelegatedHandoffRecord],
    *,
    handled: set[str],
    handoff_id: str | None,
) -> RuntimeDelegatedHandoffRecord | None:
    for record in records:
        if record.status != "planned" or not record.ok:
            continue
        if record.handoff_id in handled:
            continue
        if handoff_id is None or record.handoff_id == handoff_id:
            return record
    return None


def _handled_handoff_ids(records: list[RuntimeWorkerExecutionRecord]) -> set[str]:
    return {record.handoff_id for record in records if record.handoff_id and record.status in HANDLED_WORKER_STATUSES}


def _write_worker_summary(run_dir: Path, records: list[RuntimeWorkerExecutionRecord]) -> RuntimeWorkerSummary:
    counts: dict[str, int] = {}
    handled = []
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        if record.status in HANDLED_WORKER_STATUSES and record.handoff_id:
            handled.append(record.handoff_id)
    summary = RuntimeWorkerSummary(
        run_dir=str(run_dir),
        generated_at=utc_now_iso(),
        worker_log_jsonl=str(_worker_log_path(run_dir)),
        total_records=len(records),
        status_counts=counts,
        latest_record=records[-1] if records else None,
        handled_handoff_ids=handled,
    )
    _write_json(_worker_summary_path(run_dir), _model_to_dict(summary))
    return summary


def _worker_payload(
    run_dir: Path,
    *,
    worker_id: str,
    backend: RuntimeWorkerBackend,
    handoff: RuntimeDelegatedHandoffRecord,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "worker_id": worker_id,
        "created_at": utc_now_iso(),
        "run_dir": str(run_dir),
        "backend": backend,
        "handoff": _model_to_dict(handoff),
        "handoff_json": _read_handoff_json(handoff),
        "request_payload": request_payload,
    }


def _read_handoff_json(handoff: RuntimeDelegatedHandoffRecord) -> dict[str, Any]:
    if not handoff.handoff_json:
        return {}
    path = Path(handoff.handoff_json).expanduser()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _first_subject_id(handoff_payload: dict[str, Any]) -> str:
    subject_ids = handoff_payload.get("state_summary", {}).get("subject_ids") or []
    return subject_ids[0] if subject_ids else "subject_001"


def _write_worker_json(run_dir: Path, worker_id: str, payload: dict[str, Any]) -> Path:
    path = run_dir / "runtime_worker" / f"{worker_id}.json"
    _write_json(path, payload)
    return path


def _worker_log_path(run_dir: Path) -> Path:
    return run_dir / "runtime_worker.jsonl"


def _worker_summary_path(run_dir: Path) -> Path:
    return run_dir / "runtime_worker_summary.json"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
