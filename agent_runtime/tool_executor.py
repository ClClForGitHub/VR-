"""Deterministic tool execution and ToolCallRecord logging."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent_runtime.domain_tools import assert_tool_allowed
from agent_runtime.script_adapters import ScriptCommand
from agent_runtime.state import (
    AgentProjectState,
    ToolCallRecord,
    ToolCallStatus,
    WorkflowError,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class CommandExecutionOptions:
    timeout_seconds: float = 300.0
    max_output_chars: int = 20000
    dry_run: bool = False


class ToolExecutor:
    """Run domain tool command plans under phase guards.

    The executor mutates `AgentProjectState.tool_call_log` intentionally: the
    graph state is the project fact source, and every tool call should leave a
    structured trace there.
    """

    def __init__(self, state: AgentProjectState) -> None:
        self.state = state

    def record_dry_run(
        self,
        domain_tool_name: str,
        command: ScriptCommand,
        *,
        arguments: dict | None = None,
    ) -> ToolCallRecord:
        return self.run_command(
            domain_tool_name,
            command,
            arguments=arguments,
            options=CommandExecutionOptions(dry_run=True),
        )

    def run_command(
        self,
        domain_tool_name: str,
        command: ScriptCommand,
        *,
        arguments: dict | None = None,
        options: CommandExecutionOptions | None = None,
    ) -> ToolCallRecord:
        assert_tool_allowed(self.state.phase, domain_tool_name)
        options = options or CommandExecutionOptions()
        started_at = utc_now_iso()
        record = ToolCallRecord(
            tool_call_id=f"tool_call_{uuid4().hex[:12]}",
            project_id=self.state.project_id,
            phase=self.state.phase,
            domain_tool_name=domain_tool_name,
            tool_name=domain_tool_name,
            raw_tool_calls=[
                {
                    "kind": "subprocess",
                    "argv": command.argv,
                    "cwd": command.cwd,
                    "description": command.description,
                }
            ],
            arguments=arguments or {},
            arguments_summary=arguments or {},
            status=ToolCallStatus.STARTED,
            started_at=started_at,
        )

        if options.dry_run:
            record.status = ToolCallStatus.SUCCEEDED
            record.result_summary = {
                "dry_run": True,
                "argv": command.argv,
                "cwd": command.cwd,
                "description": command.description,
            }
            record.ended_at = utc_now_iso()
            record.finished_at = record.ended_at
            self.state.tool_call_log.append(record)
            return record

        try:
            completed = subprocess.run(
                command.argv,
                cwd=command.cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=options.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            record.status = ToolCallStatus.FAILED
            record.error = {
                "code": "TIMEOUT",
                "message": f"command timed out after {options.timeout_seconds} seconds",
                "stdout": _trim(exc.stdout or "", options.max_output_chars),
                "stderr": _trim(exc.stderr or "", options.max_output_chars),
            }
            record.error_message = record.error["message"]
            record.ended_at = utc_now_iso()
            record.finished_at = record.ended_at
            self._set_last_error(record, "TIMEOUT", record.error["message"], retriable=True)
            self.state.tool_call_log.append(record)
            return record

        stdout = _trim(completed.stdout, options.max_output_chars)
        stderr = _trim(completed.stderr, options.max_output_chars)
        record.result_summary = {
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
        record.ended_at = utc_now_iso()
        record.finished_at = record.ended_at
        if completed.returncode == 0:
            record.status = ToolCallStatus.SUCCEEDED
            self.state.last_error = None
        else:
            record.status = ToolCallStatus.FAILED
            record.error = {
                "code": "NONZERO_EXIT",
                "message": f"command exited with {completed.returncode}",
                "returncode": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
            record.error_message = record.error["message"]
            self._set_last_error(record, "NONZERO_EXIT", record.error["message"], retriable=False)
        self.state.tool_call_log.append(record)
        return record

    def _set_last_error(
        self,
        record: ToolCallRecord,
        code: str,
        message: str,
        *,
        retriable: bool,
    ) -> None:
        self.state.last_error = WorkflowError(
            error_id=f"error_{uuid4().hex[:12]}",
            phase=self.state.phase,
            code=code,
            message=message,
            retriable=retriable,
            details={
                "tool_call_id": record.tool_call_id,
                "domain_tool_name": record.domain_tool_name,
            },
            created_at=utc_now_iso(),
        )


def _trim(value: str | bytes, max_chars: int) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if len(value) <= max_chars:
        return value
    half = max_chars // 2
    return value[:half] + "\n...[truncated]...\n" + value[-half:]


def build_python_command(root: str | Path, code: str, *, description: str) -> ScriptCommand:
    """Small test/support helper for non-Blender command execution."""

    root_path = Path(root).expanduser().resolve()
    return ScriptCommand(
        argv=["python", "-c", code],
        cwd=str(root_path),
        description=description,
    )
