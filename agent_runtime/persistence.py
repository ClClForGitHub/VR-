"""File-backed project-state checkpoints for the V1 agent runtime."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - compatibility for Pydantic v1 environments
    from pydantic import BaseModel, Field

from agent_runtime.artifacts import sha256_file, utc_now_iso
from agent_runtime.state import AgentProjectState, WorkflowPhase


class StateCheckpointRecord(BaseModel):
    """Metadata for one persisted AgentProjectState snapshot."""

    checkpoint_id: str
    project_id: str
    thread_id: str
    phase: WorkflowPhase
    state_version: int
    parent_checkpoint_id: str | None = None
    reason: str
    node_name: str | None = None
    created_at: str
    state_snapshot_uri: str
    state_snapshot_sha256: str
    artifact_ids: list[str] = Field(default_factory=list)
    important_artifacts: list[str] = Field(default_factory=list)
    tool_call_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateEventRecord(BaseModel):
    """Append-only lifecycle event for checkpoints and recovery actions."""

    event_id: str
    event_type: str
    project_id: str
    thread_id: str
    phase: WorkflowPhase
    checkpoint_id: str | None = None
    source_checkpoint_id: str | None = None
    target_checkpoint_id: str | None = None
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)


class FileStateCheckpointStore:
    """Append-only checkpoint index plus immutable JSON state snapshots.

    This is intentionally small and file-based: it gives the local workflows a
    concrete recovery artifact now, while keeping the record shape close enough
    to wrap with a LangGraph checkpointer later.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        index_filename: str = "checkpoints.jsonl",
        events_filename: str = "events.jsonl",
        snapshots_dirname: str = "snapshots",
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.index_path = self.root / index_filename
        self.events_path = self.root / events_filename
        self.snapshots_path = self.root / snapshots_dirname

    def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshots_path.mkdir(parents=True, exist_ok=True)
        self.index_path.touch(exist_ok=True)
        self.events_path.touch(exist_ok=True)

    def save_checkpoint(
        self,
        state: AgentProjectState,
        *,
        reason: str,
        node_name: str | None = None,
        parent_checkpoint_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StateCheckpointRecord:
        self.ensure_ready()
        checkpoint_id = _checkpoint_id(state)
        snapshot_path = self.snapshots_path / f"{checkpoint_id}.json"
        _write_json(snapshot_path, _model_to_dict(state))
        artifact_ids = sorted(state.artifact_ids())
        record = StateCheckpointRecord(
            checkpoint_id=checkpoint_id,
            project_id=state.project_id,
            thread_id=state.thread_id,
            phase=state.phase,
            state_version=state.version,
            parent_checkpoint_id=parent_checkpoint_id,
            reason=reason,
            node_name=node_name,
            created_at=utc_now_iso(),
            state_snapshot_uri=str(snapshot_path),
            state_snapshot_sha256=sha256_file(snapshot_path),
            artifact_ids=artifact_ids,
            important_artifacts=artifact_ids,
            tool_call_count=len(state.tool_call_log),
            metadata=metadata or {},
        )
        _append_json_line(self.index_path, record)
        self.append_event(
            "checkpoint_created",
            state=state,
            checkpoint_id=checkpoint_id,
            payload={
                "reason": reason,
                "node_name": node_name,
                "state_snapshot_uri": str(snapshot_path),
            },
        )
        return record

    def list_checkpoints(
        self,
        *,
        project_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[StateCheckpointRecord]:
        records = []
        if not self.index_path.exists():
            return records
        with self.index_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = StateCheckpointRecord(**json.loads(line))
                if project_id is not None and record.project_id != project_id:
                    continue
                if thread_id is not None and record.thread_id != thread_id:
                    continue
                records.append(record)
        return records

    def latest_checkpoint(
        self,
        *,
        project_id: str | None = None,
        thread_id: str | None = None,
    ) -> StateCheckpointRecord | None:
        records = self.list_checkpoints(project_id=project_id, thread_id=thread_id)
        return records[-1] if records else None

    def load_checkpoint(self, checkpoint_id: str) -> AgentProjectState:
        record = self.get_checkpoint(checkpoint_id)
        payload = json.loads(Path(record.state_snapshot_uri).read_text(encoding="utf-8"))
        return AgentProjectState(**payload)

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        *,
        reason: str | None = None,
    ) -> AgentProjectState:
        state = self.load_checkpoint(checkpoint_id)
        self.append_event(
            "checkpoint_restored",
            state=state,
            checkpoint_id=checkpoint_id,
            source_checkpoint_id=checkpoint_id,
            target_checkpoint_id=checkpoint_id,
            payload={"reason": reason or "restore_checkpoint"},
        )
        return state

    def get_checkpoint(self, checkpoint_id: str) -> StateCheckpointRecord:
        for record in self.list_checkpoints():
            if record.checkpoint_id == checkpoint_id:
                return record
        raise KeyError(f"checkpoint not found: {checkpoint_id}")

    def list_events(self) -> list[StateEventRecord]:
        events = []
        if not self.events_path.exists():
            return events
        with self.events_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(StateEventRecord(**json.loads(line)))
        return events

    def append_event(
        self,
        event_type: str,
        *,
        state: AgentProjectState | None = None,
        checkpoint_id: str | None = None,
        source_checkpoint_id: str | None = None,
        target_checkpoint_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> StateEventRecord:
        self.ensure_ready()
        event_state = state
        if event_state is None:
            lookup_id = checkpoint_id or source_checkpoint_id or target_checkpoint_id
            if lookup_id is None:
                raise ValueError("state or checkpoint id is required for state events")
            event_state = self.load_checkpoint(lookup_id)
        event = StateEventRecord(
            event_id=f"event_{_timestamp_for_id()}_{uuid4().hex[:10]}",
            event_type=event_type,
            project_id=event_state.project_id,
            thread_id=event_state.thread_id,
            phase=event_state.phase,
            checkpoint_id=checkpoint_id,
            source_checkpoint_id=source_checkpoint_id,
            target_checkpoint_id=target_checkpoint_id,
            created_at=utc_now_iso(),
            payload=payload or {},
        )
        _append_json_line(self.events_path, event)
        return event


def langgraph_thread_config(state: AgentProjectState) -> dict[str, dict[str, str]]:
    """Return the canonical LangGraph thread config for this project state."""

    return {"configurable": {"thread_id": state.thread_id}}


def _checkpoint_id(state: AgentProjectState) -> str:
    return "ckpt_{project}_{thread}_{timestamp}_{suffix}".format(
        project=_safe_token(state.project_id),
        thread=_safe_token(state.thread_id),
        timestamp=_timestamp_for_id(),
        suffix=uuid4().hex[:10],
    )


def _timestamp_for_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    return token or "state"


def _model_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _append_json_line(path: Path, record: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _model_to_dict(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)
