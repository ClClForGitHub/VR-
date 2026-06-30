"""Runtime console dispatch planning.

This module turns the current run state into controller/runtime job JSON. It
does not execute long-running jobs; execution will be wired as the next layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.controller import ControllerPlan, build_controller_plan
from agent_runtime.runtime_jobs import AgentRuntimePlan, build_agent_runtime_plan
from agent_runtime.runtime_profiles import RuntimeServiceConfig
from agent_runtime.state import AgentProjectState


class RuntimeDispatchPlanResult(BaseModel):
    ok: bool
    run_dir: str
    state_json: str
    runtime_plan_json: str
    generated_at: str
    controller: ControllerPlan
    runtime_plan: AgentRuntimePlan


def build_and_save_runtime_dispatch_plan(
    run_dir: str | Path,
    *,
    service_config: RuntimeServiceConfig | None = None,
    hunyuan3d_profile_id: str | None = None,
    prefer_sub_agents_for_long_jobs: bool = True,
) -> RuntimeDispatchPlanResult:
    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for runtime dispatch: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    controller = build_controller_plan(state)
    runtime_plan = build_agent_runtime_plan(
        state,
        controller=controller,
        service_config=service_config,
        hunyuan3d_profile_id=hunyuan3d_profile_id,
        prefer_sub_agents_for_long_jobs=prefer_sub_agents_for_long_jobs,
        frontend_status_path=str(path / "frontend_status.json") if (path / "frontend_status.json").exists() else None,
        delivery_handoff_path=str(path / "delivery_handoff.json") if (path / "delivery_handoff.json").exists() else None,
    )
    result = RuntimeDispatchPlanResult(
        ok=not runtime_plan.blocked,
        run_dir=str(path),
        state_json=str(state_path),
        runtime_plan_json=str(path / "runtime_plan.json"),
        generated_at=utc_now_iso(),
        controller=controller,
        runtime_plan=runtime_plan,
    )
    _write_json(path / "runtime_plan.json", _model_to_dict(result))
    return result


def read_runtime_dispatch_plan(run_dir: str | Path) -> dict[str, Any] | None:
    path = Path(run_dir).expanduser().resolve() / "runtime_plan.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
