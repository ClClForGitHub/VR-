import importlib.metadata
from pathlib import Path

from agent_runtime.langgraph_adapter import (
    LangGraphRuntimeStatus,
    build_langgraph_checkpoint_wiring_plan,
    check_langgraph_runtime,
)
from agent_runtime.persistence import FileStateCheckpointStore
from agent_runtime.state import AgentProjectState, WorkflowPhase


def test_check_langgraph_runtime_reports_missing_dependency_without_importing_graph() -> None:
    def missing_finder(name):
        if name != "langgraph":
            raise ModuleNotFoundError(name)
        return None

    def missing_version(name):
        raise importlib.metadata.PackageNotFoundError(name)

    status = check_langgraph_runtime(
        module_finder=missing_finder,
        version_getter=missing_version,
    )

    assert status.installed is False
    assert status.ready is False
    assert status.version is None
    assert status.modules == {
        "langgraph": False,
        "langgraph.graph": False,
        "langgraph.checkpoint": False,
    }
    assert "langgraph_not_installed" in status.issues
    assert "missing_module:langgraph.graph" in status.issues
    assert "missing_module:langgraph.checkpoint" in status.issues


def test_check_langgraph_runtime_reports_ready_when_required_modules_exist() -> None:
    status = check_langgraph_runtime(
        module_finder=lambda name: object(),
        version_getter=lambda name: "1.2.3",
    )

    assert status.installed is True
    assert status.ready is True
    assert status.version == "1.2.3"
    assert status.issues == []


def test_build_langgraph_checkpoint_wiring_plan_uses_file_checkpoint_store(tmp_path: Path) -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.INTAKE,
    )
    store = FileStateCheckpointStore(tmp_path / "checkpoints")
    status = LangGraphRuntimeStatus(
        installed=False,
        ready=False,
        modules={"langgraph": False},
        issues=["langgraph_not_installed"],
    )

    plan = build_langgraph_checkpoint_wiring_plan(
        state=state,
        checkpoint_store=store,
        dependency_status=status,
    )

    assert plan.ready_to_run_graph is False
    assert plan.thread_config == {"configurable": {"thread_id": "thread_001"}}
    assert plan.checkpoint_store_root == str((tmp_path / "checkpoints").resolve())
    assert plan.checkpoint_index_path.endswith("checkpoints.jsonl")
    assert plan.checkpoint_events_path.endswith("events.jsonl")
    assert plan.checkpoint_snapshots_path.endswith("snapshots")
    assert plan.pending_steps[0].startswith("Install or enable the real langgraph package")
