"""LangGraph dependency and checkpoint wiring diagnostics.

This module deliberately avoids pretending that the local workflow runner is a
LangGraph graph. It records whether the real dependency is available and how
the existing file-backed checkpoint store should be wrapped once LangGraph is
installed for this project environment.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - compatibility for Pydantic v1 environments
    from pydantic import BaseModel, Field

from agent_runtime.persistence import FileStateCheckpointStore, langgraph_thread_config
from agent_runtime.state import AgentProjectState


ModuleFinder = Callable[[str], Any]
VersionGetter = Callable[[str], str]


class LangGraphRuntimeStatus(BaseModel):
    installed: bool
    ready: bool
    package_name: str = "langgraph"
    version: str | None = None
    modules: dict[str, bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


class LangGraphCheckpointWiringPlan(BaseModel):
    ready_to_run_graph: bool
    dependency_status: LangGraphRuntimeStatus
    thread_config: dict[str, Any]
    checkpoint_store_root: str
    checkpoint_index_path: str
    checkpoint_events_path: str
    checkpoint_snapshots_path: str
    intended_state_type: str = "AgentProjectState"
    intended_checkpointer: str = "FileStateCheckpointStore-backed LangGraph checkpointer adapter"
    pending_steps: list[str] = Field(default_factory=list)


def check_langgraph_runtime(
    *,
    package_name: str = "langgraph",
    required_modules: list[str] | None = None,
    module_finder: ModuleFinder | None = None,
    version_getter: VersionGetter | None = None,
) -> LangGraphRuntimeStatus:
    modules_to_check = required_modules or [
        "langgraph",
        "langgraph.graph",
        "langgraph.checkpoint",
    ]
    finder = module_finder or importlib.util.find_spec
    get_version = version_getter or importlib.metadata.version

    modules = {name: _module_exists(finder, name) for name in modules_to_check}
    installed = modules.get(package_name, False)
    version = None
    issues = []
    if installed:
        try:
            version = get_version(package_name)
        except importlib.metadata.PackageNotFoundError:
            issues.append("langgraph_version_not_found")
        except Exception as exc:  # pragma: no cover - defensive metadata boundary
            issues.append(f"langgraph_version_error:{exc}")
    else:
        issues.append("langgraph_not_installed")

    missing_modules = [name for name, present in modules.items() if not present]
    for name in missing_modules:
        if name != package_name:
            issues.append(f"missing_module:{name}")

    ready = installed and not missing_modules
    return LangGraphRuntimeStatus(
        installed=installed,
        ready=ready,
        package_name=package_name,
        version=version,
        modules=modules,
        issues=issues,
    )


def build_langgraph_checkpoint_wiring_plan(
    *,
    state: AgentProjectState,
    checkpoint_store: FileStateCheckpointStore,
    dependency_status: LangGraphRuntimeStatus | None = None,
) -> LangGraphCheckpointWiringPlan:
    status = dependency_status or check_langgraph_runtime()
    pending_steps = [
        "Install or enable the real langgraph package in the project runtime environment.",
        "Implement a LangGraph checkpointer adapter that delegates state snapshots to FileStateCheckpointStore.",
        "Wire DOC-003 node boundaries to save checkpoints through the adapter.",
        "Run a real graph smoke before marking LangGraph integration complete.",
    ]
    if status.ready:
        pending_steps = pending_steps[1:]
    return LangGraphCheckpointWiringPlan(
        ready_to_run_graph=status.ready and not pending_steps,
        dependency_status=status,
        thread_config=langgraph_thread_config(state),
        checkpoint_store_root=str(checkpoint_store.root),
        checkpoint_index_path=str(checkpoint_store.index_path),
        checkpoint_events_path=str(checkpoint_store.events_path),
        checkpoint_snapshots_path=str(checkpoint_store.snapshots_path),
        pending_steps=pending_steps,
    )


def _module_exists(finder: ModuleFinder, module_name: str) -> bool:
    try:
        return finder(module_name) is not None
    except ModuleNotFoundError:
        return False
