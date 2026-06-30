"""Runtime console persistence helpers.

The console is a thin input/control surface over the authoritative runtime
files. It records chat turns and uploaded references inside a run directory and
updates `AgentProjectState` for user turns and input images.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    InputImage,
    UserTurn,
    WorkflowPhase,
)


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class RuntimeConsoleRunResult(BaseModel):
    ok: bool
    run_id: str
    run_dir: str
    state_json: str
    summary_json: str
    frontend_status_json: str


class RuntimeConsoleMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant", "system"]
    text: str
    created_at: str
    attachment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeConsoleUploadResult(BaseModel):
    ok: bool
    upload_id: str
    artifact_id: str | None = None
    image_id: str | None = None
    filename: str
    uri: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: str


def create_runtime_console_run(
    *,
    root: str | Path = "/home/team/zouzhiyuan/image23D_Agent",
    run_id: str | None = None,
    project_id: str | None = None,
    thread_id: str | None = None,
) -> RuntimeConsoleRunResult:
    resolved_run_id = run_id or f"runtime_console_{utc_now_iso().replace(':', '').replace('-', '').replace('+', 'Z')}"
    run_dir = resolve_runtime_console_run_dir(root=root, run_id=resolved_run_id, must_exist=False)
    run_dir.mkdir(parents=True, exist_ok=False)
    now = utc_now_iso()
    state = AgentProjectState(
        project_id=project_id or resolved_run_id,
        thread_id=thread_id or "runtime_console",
        phase=WorkflowPhase.INTAKE,
        created_at=now,
        updated_at=now,
    )
    summary = {
        "ok": True,
        "workflow": "runtime-console",
        "dry_run": False,
        "requested_stages": [],
        "executed_stages": [],
        "skipped_stages": {},
    }
    _write_state(run_dir, state)
    _write_json(run_dir / "summary.json", summary)
    _write_json(run_dir / "frontend_status.json", _model_to_dict(build_frontend_status(state=state, summary=summary)))
    (run_dir / "runtime_console").mkdir(exist_ok=True)
    return RuntimeConsoleRunResult(
        ok=True,
        run_id=resolved_run_id,
        run_dir=str(run_dir),
        state_json=str(run_dir / "state.json"),
        summary_json=str(run_dir / "summary.json"),
        frontend_status_json=str(run_dir / "frontend_status.json"),
    )


def resolve_runtime_console_run_dir(
    *,
    root: str | Path = "/home/team/zouzhiyuan/image23D_Agent",
    run_id: str,
    must_exist: bool = True,
) -> Path:
    if not SAFE_ID_RE.match(run_id) or run_id in {".", ".."}:
        raise ValueError(f"unsafe run_id: {run_id}")
    runs_root = Path(root).expanduser().resolve() / "outputs" / "runs"
    run_dir = (runs_root / run_id).resolve()
    try:
        run_dir.relative_to(runs_root)
    except ValueError as exc:
        raise ValueError(f"run_id escapes runs root: {run_id}") from exc
    if must_exist and not run_dir.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    return run_dir


def append_console_message(
    run_dir: str | Path,
    *,
    role: Literal["user", "assistant", "system"],
    text: str,
    attachment_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeConsoleMessage:
    if not text.strip():
        raise ValueError("message text must not be empty")
    path = Path(run_dir).expanduser().resolve()
    console_dir = path / "runtime_console"
    console_dir.mkdir(parents=True, exist_ok=True)
    message = RuntimeConsoleMessage(
        message_id=f"msg_{uuid4().hex[:12]}",
        role=role,
        text=text,
        created_at=utc_now_iso(),
        attachment_ids=attachment_ids or [],
        metadata=metadata or {},
    )
    _append_jsonl(console_dir / "chat.jsonl", _model_to_dict(message))

    if role == "user" and (path / "state.json").exists():
        state = _read_state(path)
        state.user_turns.append(
            UserTurn(
                turn_id=message.message_id,
                text=text,
                image_ids=list(message.attachment_ids),
                phase_at_turn=state.phase,
                created_at=message.created_at,
            )
        )
        state.updated_at = utc_now_iso()
        _write_state(path, state)
    return message


def read_console_messages(run_dir: str | Path, *, limit: int = 200) -> list[RuntimeConsoleMessage]:
    chat_path = Path(run_dir).expanduser().resolve() / "runtime_console" / "chat.jsonl"
    if not chat_path.exists():
        return []
    rows = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(RuntimeConsoleMessage(**json.loads(line)))
    return rows[-limit:]


def save_console_upload(
    run_dir: str | Path,
    *,
    filename: str,
    content: bytes,
    mime_type: str | None = None,
) -> RuntimeConsoleUploadResult:
    if not content:
        raise ValueError("upload content must not be empty")
    path = Path(run_dir).expanduser().resolve()
    console_dir = path / "runtime_console"
    upload_dir = console_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(filename)
    upload_id = f"upload_{uuid4().hex[:12]}"
    target = upload_dir / f"{upload_id}_{safe_name}"
    target.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    guessed_mime = mime_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    now = utc_now_iso()
    artifact_id = None
    image_id = None

    if (path / "state.json").exists() and guessed_mime.startswith("image/"):
        state = _read_state(path)
        artifact_id = f"artifact_{upload_id}"
        image_id = f"image_{upload_id}"
        state.artifacts.append(
            ArtifactRecord(
                artifact_id=artifact_id,
                artifact_type=ArtifactType.INPUT_IMAGE,
                uri=str(target),
                mime_type=guessed_mime,
                semantic_role="runtime_console_upload",
                size_bytes=len(content),
                sha256=digest,
                created_at=now,
                metadata={"upload_id": upload_id, "original_filename": filename},
            )
        )
        state.input_images.append(
            InputImage(
                image_id=image_id,
                artifact_id=artifact_id,
                uri=str(target),
                mime_type=guessed_mime,
                notes="Uploaded through runtime console.",
            )
        )
        state.updated_at = now
        _write_state(path, state)

    result = RuntimeConsoleUploadResult(
        ok=True,
        upload_id=upload_id,
        artifact_id=artifact_id,
        image_id=image_id,
        filename=safe_name,
        uri=str(target),
        mime_type=guessed_mime,
        size_bytes=len(content),
        sha256=digest,
        created_at=now,
    )
    _append_jsonl(console_dir / "uploads.jsonl", _model_to_dict(result))
    return result


def read_console_uploads(run_dir: str | Path, *, limit: int = 200) -> list[RuntimeConsoleUploadResult]:
    upload_log = Path(run_dir).expanduser().resolve() / "runtime_console" / "uploads.jsonl"
    if not upload_log.exists():
        return []
    rows = []
    for line in upload_log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(RuntimeConsoleUploadResult(**json.loads(line)))
    return rows[-limit:]


def _safe_filename(filename: str) -> str:
    name = Path(filename or "upload.bin").name
    name = SAFE_FILENAME_RE.sub("_", name).strip("._")
    return name or "upload.bin"


def _read_state(run_dir: Path) -> AgentProjectState:
    return AgentProjectState(**json.loads((run_dir / "state.json").read_text(encoding="utf-8")))


def _write_state(run_dir: Path, state: AgentProjectState) -> None:
    _write_json(run_dir / "state.json", _model_to_dict(state))


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

