from pathlib import Path

from agent_runtime.script_adapters import ScriptCommand
from agent_runtime.state import AgentProjectState, ToolCallStatus, WorkflowPhase
from agent_runtime.tool_executor import (
    CommandExecutionOptions,
    ToolExecutor,
    build_python_command,
)


def _state(phase: WorkflowPhase = WorkflowPhase.BLENDER_EDIT) -> AgentProjectState:
    return AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=phase,
    )


def test_tool_executor_records_dry_run_without_running_command(tmp_path: Path) -> None:
    state = _state()
    executor = ToolExecutor(state)
    command = ScriptCommand(
        argv=["python", "-c", "raise SystemExit(99)"],
        cwd=str(tmp_path),
        description="not executed",
    )

    record = executor.record_dry_run("render_preview", command, arguments={"asset": "demo.glb"})

    assert record.status == ToolCallStatus.SUCCEEDED
    assert record.tool_name == "render_preview"
    assert record.arguments_summary == {"asset": "demo.glb"}
    assert record.result_summary["dry_run"] is True
    assert record.finished_at == record.ended_at
    assert state.tool_call_log == [record]


def test_tool_executor_runs_allowed_command_success(tmp_path: Path) -> None:
    state = _state()
    executor = ToolExecutor(state)
    command = build_python_command(tmp_path, "print('ok')", description="unit command")

    record = executor.run_command("render_preview", command, options=CommandExecutionOptions(timeout_seconds=5))

    assert record.status == ToolCallStatus.SUCCEEDED
    assert record.result_summary["returncode"] == 0
    assert record.result_summary["stdout"].strip() == "ok"
    assert record.finished_at == record.ended_at
    assert state.last_error is None


def test_tool_executor_records_nonzero_failure(tmp_path: Path) -> None:
    state = _state()
    executor = ToolExecutor(state)
    command = build_python_command(
        tmp_path,
        "import sys; print('bad'); sys.exit(7)",
        description="failing unit command",
    )

    record = executor.run_command("render_preview", command, options=CommandExecutionOptions(timeout_seconds=5))

    assert record.status == ToolCallStatus.FAILED
    assert record.error["code"] == "NONZERO_EXIT"
    assert record.error_message == "command exited with 7"
    assert record.result_summary["returncode"] == 7
    assert state.last_error is not None
    assert state.last_error.details["tool_call_id"] == record.tool_call_id
    assert state.last_error.message == "command exited with 7"


def test_tool_executor_rejects_phase_inappropriate_tool(tmp_path: Path) -> None:
    state = _state(WorkflowPhase.CONCEPT_GENERATION)
    executor = ToolExecutor(state)
    command = build_python_command(tmp_path, "print('nope')", description="guarded")

    try:
        executor.run_command("delete_subject", command, options=CommandExecutionOptions(timeout_seconds=5))
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("phase guard did not reject delete_subject")

    assert state.tool_call_log == []
