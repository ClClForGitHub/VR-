"""Read-only runtime run discovery and front-end handoff helpers."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, Field

from agent_runtime.runtime_jobs import RuntimeWebSurface, build_runtime_web_surface
from agent_runtime.runtime_profiles import RuntimeServiceConfig
from agent_runtime.state import AgentProjectState
from agent_runtime.runtime_dispatch import read_runtime_dispatch_plan
from agent_runtime.runtime_delegation import read_runtime_handoff_summary
from agent_runtime.runtime_execution import read_runtime_execution_summary
from agent_runtime.runtime_handoff_apply import read_runtime_handoff_apply_summary
from agent_runtime.runtime_loop import read_runtime_loop_summary
from agent_runtime.runtime_asset_actions import read_runtime_asset_action_summary
from agent_runtime.runtime_state_apply import read_runtime_apply_summary
from agent_runtime.runtime_user_actions import read_runtime_user_action_summary
from agent_runtime.runtime_worker import read_runtime_worker_summary


class PublicUrlConfig(BaseModel):
    """Browser-facing URL bases for locally hosted runtime services."""

    local_glb_viewer_base_url: str = "http://127.0.0.1:8092"
    public_glb_viewer_base_url: str = "http://10.2.16.106:8092"
    local_blender_web_http_url: str = "http://127.0.0.1:8300"
    public_blender_web_http_url: str = "http://10.2.16.106:8300"
    local_blender_web_https_url: str = "https://127.0.0.1:8301"
    public_blender_web_https_url: str = "https://10.2.16.106:8301"


class RuntimeRunIndexItem(BaseModel):
    run_key: str
    run_id: str
    display_name: str
    relative_path: str
    run_dir: str
    effective_run_dir: str
    parent_run_id: str | None = None
    stage_id: str | None = None
    is_stage: bool = False
    modified_at: float
    has_state: bool
    has_summary: bool
    has_frontend_status: bool
    has_delivery_handoff: bool
    has_scene_state: bool
    has_viewer_scene: bool = False
    frontend_phase: str | None = None
    frontend_status_value: str | None = None


class RuntimeRunFileRecord(BaseModel):
    label: str
    kind: str
    path: str
    relative_path: str
    exists: bool
    size_bytes: int | None = None
    modified_at: float | None = None
    url: str | None = None


class RuntimeRunFileManifest(BaseModel):
    run_dir: str
    effective_run_dir: str
    files: list[RuntimeRunFileRecord] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)


class RuntimeRunBundle(BaseModel):
    run_key: str
    run_id: str
    display_name: str
    relative_path: str
    run_dir: str
    effective_run_dir: str
    state: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    frontend_status: dict[str, Any] | None = None
    delivery_handoff: dict[str, Any] | None = None
    scene_state: dict[str, Any] | None = None
    runtime_plan: dict[str, Any] | None = None
    runtime_execution_summary: dict[str, Any] | None = None
    runtime_apply_summary: dict[str, Any] | None = None
    runtime_loop_summary: dict[str, Any] | None = None
    runtime_handoff_summary: dict[str, Any] | None = None
    runtime_handoff_apply_summary: dict[str, Any] | None = None
    runtime_worker_summary: dict[str, Any] | None = None
    runtime_user_action_summary: dict[str, Any] | None = None
    runtime_asset_action_summary: dict[str, Any] | None = None
    web_surface: RuntimeWebSurface | None = None
    file_manifest: RuntimeRunFileManifest | None = None
    missing_files: list[str] = Field(default_factory=list)


def discover_runtime_runs(
    *,
    root: str | Path = "/home/team/zouzhiyuan/image23D_Agent",
    limit: int = 50,
) -> list[RuntimeRunIndexItem]:
    runs_root = Path(root).expanduser().resolve() / "outputs" / "runs"
    if not runs_root.exists():
        return []
    items = []
    for run_dir in _candidate_run_dirs(runs_root):
        items.append(_index_item(runs_root, run_dir))
    items.sort(key=lambda item: (item.has_viewer_scene, item.has_scene_state, item.modified_at), reverse=True)
    return items[:limit]


def build_runtime_run_bundle(
    run_dir: str | Path,
    *,
    service_config: RuntimeServiceConfig | None = None,
    public_urls: PublicUrlConfig | None = None,
) -> RuntimeRunBundle:
    path = Path(run_dir).expanduser().resolve()
    runs_root = _runs_root_from_run_dir(path)
    effective_path = _best_runtime_dir(path)
    control_path = _control_runtime_dir(path, effective_path)
    config = service_config or RuntimeServiceConfig()
    url_config = public_urls or PublicUrlConfig()
    missing = []

    state_payload = _read_optional_json(control_path / "state.json", missing, "state.json")
    summary = _read_optional_json(control_path / "summary.json", missing, "summary.json")
    frontend_status = _read_optional_json(control_path / "frontend_status.json", missing, "frontend_status.json")
    delivery_handoff = _read_optional_json(
        _preferred_existing_path(control_path / "delivery_handoff.json", effective_path / "delivery_handoff.json"),
        missing,
        "delivery_handoff.json",
    )
    scene_state = _find_scene_state(effective_path, missing)
    runtime_plan = read_runtime_dispatch_plan(control_path)
    runtime_execution_summary = read_runtime_execution_summary(control_path)
    runtime_apply_summary = read_runtime_apply_summary(control_path)
    runtime_loop_summary = read_runtime_loop_summary(control_path)
    runtime_handoff_summary = read_runtime_handoff_summary(control_path)
    runtime_handoff_apply_summary = read_runtime_handoff_apply_summary(control_path)
    runtime_worker_summary = read_runtime_worker_summary(control_path)
    runtime_user_action_summary = read_runtime_user_action_summary(control_path)
    runtime_asset_action_summary = read_runtime_asset_action_summary(control_path)
    manifest = _build_file_manifest(
        run_dir=path,
        control_run_dir=control_path,
        visual_run_dir=effective_path,
        runs_root=runs_root,
        public_urls=url_config,
    )

    web_surface = None
    if state_payload is not None:
        state = AgentProjectState(**state_payload)
        web_surface = build_runtime_web_surface(
            state,
            service_config=_public_service_config(config, url_config),
            frontend_status_path=str(control_path / "frontend_status.json") if (control_path / "frontend_status.json").exists() else None,
            delivery_handoff_path=str(_preferred_existing_path(control_path / "delivery_handoff.json", effective_path / "delivery_handoff.json"))
            if _preferred_existing_path(control_path / "delivery_handoff.json", effective_path / "delivery_handoff.json").exists()
            else None,
        )

    relative_path = _relative_run_path(runs_root, path)
    return RuntimeRunBundle(
        run_key=encode_runtime_run_key(relative_path),
        run_id=relative_path,
        display_name=_display_name(relative_path),
        relative_path=relative_path,
        run_dir=str(path),
        effective_run_dir=str(effective_path),
        state=_rewrite_urls(state_payload, url_config),
        summary=_rewrite_urls(summary, url_config),
        frontend_status=_rewrite_urls(frontend_status, url_config),
        delivery_handoff=_rewrite_urls(delivery_handoff, url_config),
        scene_state=_rewrite_urls(scene_state, url_config),
        runtime_plan=_rewrite_urls(runtime_plan, url_config),
        runtime_execution_summary=_rewrite_urls(runtime_execution_summary, url_config),
        runtime_apply_summary=_rewrite_urls(runtime_apply_summary, url_config),
        runtime_loop_summary=_rewrite_urls(runtime_loop_summary, url_config),
        runtime_handoff_summary=_rewrite_urls(runtime_handoff_summary, url_config),
        runtime_handoff_apply_summary=_rewrite_urls(runtime_handoff_apply_summary, url_config),
        runtime_worker_summary=_rewrite_urls(runtime_worker_summary, url_config),
        runtime_user_action_summary=_rewrite_urls(runtime_user_action_summary, url_config),
        runtime_asset_action_summary=_rewrite_urls(runtime_asset_action_summary, url_config),
        web_surface=web_surface,
        file_manifest=manifest,
        missing_files=missing,
    )


def rewrite_runtime_urls(payload: Any, public_urls: PublicUrlConfig | None = None) -> Any:
    return _rewrite_urls(payload, public_urls or PublicUrlConfig())


def encode_runtime_run_key(relative_path: str) -> str:
    payload = base64.urlsafe_b64encode(relative_path.encode("utf-8")).decode("ascii").rstrip("=")
    return f"r_{payload}"


def decode_runtime_run_key(run_key: str) -> str:
    if not run_key.startswith("r_"):
        return run_key
    payload = run_key[2:]
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii")).decode("utf-8")


def resolve_runtime_run_dir(
    *,
    root: str | Path = "/home/team/zouzhiyuan/image23D_Agent",
    run_key: str,
    must_exist: bool = True,
) -> Path:
    runs_root = Path(root).expanduser().resolve() / "outputs" / "runs"
    relative = decode_runtime_run_key(run_key)
    if not relative or relative in {".", ".."}:
        raise ValueError(f"unsafe run key: {run_key}")
    rel_path = Path(relative)
    if rel_path.is_absolute() or any(part in {"", ".", ".."} for part in rel_path.parts):
        raise ValueError(f"unsafe run key: {run_key}")
    run_dir = (runs_root / rel_path).resolve()
    try:
        run_dir.relative_to(runs_root)
    except ValueError as exc:
        raise ValueError(f"run key escapes runs root: {run_key}") from exc
    if must_exist and not run_dir.exists():
        raise FileNotFoundError(f"run not found: {run_key}")
    return run_dir


def _index_item(runs_root: Path, run_dir: Path) -> RuntimeRunIndexItem:
    effective = _best_runtime_dir(run_dir)
    relative_path = _relative_run_path(runs_root, run_dir)
    parts = Path(relative_path).parts
    parent_run_id = parts[0] if len(parts) > 1 else None
    stage_id = "/".join(parts[1:]) if len(parts) > 1 else None
    modified_at = max(run_dir.stat().st_mtime, effective.stat().st_mtime)
    frontend_status = _read_json_if_exists(effective / "frontend_status.json") or {}
    return RuntimeRunIndexItem(
        run_key=encode_runtime_run_key(relative_path),
        run_id=relative_path,
        display_name=_display_name(relative_path),
        relative_path=relative_path,
        run_dir=str(run_dir),
        effective_run_dir=str(effective),
        parent_run_id=parent_run_id,
        stage_id=stage_id,
        is_stage=len(parts) > 1,
        modified_at=modified_at,
        has_state=(effective / "state.json").exists(),
        has_summary=(effective / "summary.json").exists(),
        has_frontend_status=(effective / "frontend_status.json").exists(),
        has_delivery_handoff=(effective / "delivery_handoff.json").exists(),
        has_scene_state=_scene_state_path(effective) is not None,
        has_viewer_scene=_viewer_scene_path(effective) is not None,
        frontend_phase=frontend_status.get("phase") if isinstance(frontend_status.get("phase"), str) else None,
        frontend_status_value=frontend_status.get("status") if isinstance(frontend_status.get("status"), str) else None,
    )


def _candidate_run_dirs(runs_root: Path) -> list[Path]:
    candidates = []
    for run_dir in sorted(runs_root.iterdir()):
        if not run_dir.is_dir():
            continue
        candidates.append(run_dir)
        for child in sorted(run_dir.rglob("*")):
            if not child.is_dir() or _skip_discovery_dir(child):
                continue
            if _has_visual_runtime_files(child):
                candidates.append(child)
    return candidates


def _skip_discovery_dir(path: Path) -> bool:
    skip_names = {
        "artifacts",
        "checkpoints",
        "package",
        "runtime_console",
        "subject_assets",
        "uploads",
        "viewer_export",
    }
    return any(part in skip_names for part in path.parts)


def _has_runtime_files(path: Path) -> bool:
    return any(
        (
            (path / "state.json").exists(),
            (path / "summary.json").exists(),
            (path / "frontend_status.json").exists(),
            (path / "delivery_handoff.json").exists(),
            _scene_state_path(path) is not None,
            _viewer_scene_path(path) is not None,
        )
    )


def _best_runtime_dir(run_dir: Path) -> Path:
    candidates = [run_dir]
    for child in run_dir.rglob("*"):
        if not child.is_dir() or _skip_discovery_dir(child):
            continue
        if _has_visual_runtime_files(child):
            candidates.append(child)
    candidates.sort(key=_runtime_dir_score, reverse=True)
    return candidates[0]


def _control_runtime_dir(run_dir: Path, effective_run_dir: Path) -> Path:
    if _has_control_runtime_files(run_dir):
        return run_dir
    return effective_run_dir


def _has_control_runtime_files(path: Path) -> bool:
    return any(
        (
            (path / "state.json").exists(),
            (path / "summary.json").exists(),
            (path / "frontend_status.json").exists(),
            (path / "runtime_plan.json").exists(),
        )
    )


def _preferred_existing_path(primary: Path, fallback: Path) -> Path:
    return primary if primary.exists() else fallback


def _has_visual_runtime_files(path: Path) -> bool:
    return any(
        (
            (path / "delivery_handoff.json").exists(),
            _scene_state_path(path) is not None,
            _viewer_scene_path(path) is not None,
        )
    )


def _runtime_dir_score(path: Path) -> tuple[int, float]:
    score = 0
    if _viewer_scene_path(path) is not None:
        score += 100
    if _scene_state_path(path) is not None:
        score += 60
    if (path / "delivery_handoff.json").exists():
        score += 30
    if (path / "state.json").exists():
        score += 20
    if (path / "frontend_status.json").exists():
        score += 10
    if (path / "summary.json").exists():
        score += 5
    return score, path.stat().st_mtime


def _viewer_scene_path(run_dir: Path) -> Path | None:
    direct = run_dir / "viewer_scene.glb"
    if direct.exists():
        return direct
    nested = run_dir / "viewer_export" / "viewer_scene.glb"
    if nested.exists():
        return nested
    candidates = sorted(run_dir.glob("**/viewer_scene.glb"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _scene_state_path(run_dir: Path) -> Path | None:
    direct = run_dir / "scene_state.json"
    if direct.exists():
        return direct
    nested = run_dir / "viewer_export" / "scene_state.json"
    if nested.exists():
        return nested
    candidates = sorted(run_dir.glob("**/scene_state.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _delivery_package_zip_path(run_dir: Path) -> Path | None:
    package_root = run_dir / "delivery_package" / "package"
    if not package_root.exists():
        return None
    candidates = sorted(package_root.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _find_scene_state(run_dir: Path, missing: list[str]) -> dict[str, Any] | None:
    path = _scene_state_path(run_dir)
    if path is None:
        missing.append("scene_state.json")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _build_file_manifest(
    *,
    run_dir: Path,
    control_run_dir: Path,
    visual_run_dir: Path,
    runs_root: Path,
    public_urls: PublicUrlConfig,
) -> RuntimeRunFileManifest:
    delivery_handoff_path = _preferred_existing_path(control_run_dir / "delivery_handoff.json", visual_run_dir / "delivery_handoff.json")
    required = [
        ("state", "json", control_run_dir / "state.json"),
        ("summary", "json", control_run_dir / "summary.json"),
        ("frontend_status", "json", control_run_dir / "frontend_status.json"),
        ("delivery_handoff", "json", delivery_handoff_path),
        ("scene_state", "json", _scene_state_path(visual_run_dir) or (visual_run_dir / "viewer_export" / "scene_state.json")),
        ("viewer_scene", "model", _viewer_scene_path(visual_run_dir) or (visual_run_dir / "viewer_export" / "viewer_scene.glb")),
    ]
    optional = [
        ("runtime_plan", "json", control_run_dir / "runtime_plan.json"),
        ("runtime_execution", "jsonl", control_run_dir / "runtime_execution.jsonl"),
        ("runtime_execution_summary", "json", control_run_dir / "runtime_execution_summary.json"),
        ("runtime_apply", "jsonl", control_run_dir / "runtime_apply.jsonl"),
        ("runtime_apply_summary", "json", control_run_dir / "runtime_apply_summary.json"),
        ("runtime_loop", "jsonl", control_run_dir / "runtime_loop.jsonl"),
        ("runtime_loop_summary", "json", control_run_dir / "runtime_loop_summary.json"),
        ("runtime_handoff", "jsonl", control_run_dir / "runtime_handoff.jsonl"),
        ("runtime_handoff_summary", "json", control_run_dir / "runtime_handoff_summary.json"),
        ("runtime_worker", "jsonl", control_run_dir / "runtime_worker.jsonl"),
        ("runtime_worker_summary", "json", control_run_dir / "runtime_worker_summary.json"),
        ("runtime_user_action", "jsonl", control_run_dir / "runtime_user_action.jsonl"),
        ("runtime_user_action_summary", "json", control_run_dir / "runtime_user_action_summary.json"),
        ("runtime_asset_action", "jsonl", control_run_dir / "runtime_asset_action.jsonl"),
        ("runtime_asset_action_summary", "json", control_run_dir / "runtime_asset_action_summary.json"),
        ("runtime_handoff_apply", "jsonl", control_run_dir / "runtime_handoff_apply.jsonl"),
        ("runtime_handoff_apply_summary", "json", control_run_dir / "runtime_handoff_apply_summary.json"),
        ("chat", "jsonl", control_run_dir / "runtime_console" / "chat.jsonl"),
        ("uploads", "jsonl", control_run_dir / "runtime_console" / "uploads.jsonl"),
        ("delivery_package", "model", _delivery_package_zip_path(control_run_dir) or (control_run_dir / "delivery_package" / "package" / "delivery_package.zip")),
    ]
    files = [
        _file_record(
            label,
            kind,
            path,
            run_dir=_manifest_file_root(path, control_run_dir=control_run_dir, visual_run_dir=visual_run_dir),
            public_urls=public_urls,
        )
        for label, kind, path in required + optional
    ]
    missing_required = [record.label for record in files[: len(required)] if not record.exists]
    return RuntimeRunFileManifest(
        run_dir=str(run_dir),
        effective_run_dir=str(visual_run_dir),
        files=files,
        missing_required=missing_required,
    )


def _manifest_file_root(path: Path, *, control_run_dir: Path, visual_run_dir: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(control_run_dir.resolve())
        return control_run_dir
    except ValueError:
        pass
    try:
        resolved.relative_to(visual_run_dir.resolve())
        return visual_run_dir
    except ValueError:
        return control_run_dir


def _file_record(label: str, kind: str, path: Path, *, run_dir: Path, public_urls: PublicUrlConfig) -> RuntimeRunFileRecord:
    exists = path.exists()
    relative_path = _relative_to(path, run_dir) if exists else _relative_to(path, run_dir)
    url = None
    if exists:
        if path.suffix.lower() in {".glb", ".gltf"}:
            url = f"{public_urls.public_glb_viewer_base_url.rstrip('/')}/viewer?path={quote(str(path))}"
        else:
            url = f"/api/runs/{encode_runtime_run_key(_relative_to(run_dir, _runs_root_from_run_dir(run_dir)))}/file?path={quote(relative_path)}"
    return RuntimeRunFileRecord(
        label=label,
        kind=kind,
        path=str(path),
        relative_path=relative_path,
        exists=exists,
        size_bytes=path.stat().st_size if exists else None,
        modified_at=path.stat().st_mtime if exists else None,
        url=url,
    )


def _read_optional_json(path: Path, missing: list[str], label: str) -> dict[str, Any] | None:
    if not path.exists():
        missing.append(label)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _runs_root_from_run_dir(run_dir: Path) -> Path:
    resolved = run_dir.resolve()
    parts = resolved.parts
    for index in range(len(parts) - 2, -1, -1):
        if parts[index : index + 2] == ("outputs", "runs"):
            return Path(*parts[: index + 2])
    return resolved.parent


def _relative_run_path(runs_root: Path, run_dir: Path) -> str:
    return run_dir.resolve().relative_to(runs_root.resolve()).as_posix()


def _relative_to(path: Path, parent: Path) -> str:
    try:
        return path.resolve().relative_to(parent.resolve()).as_posix()
    except ValueError:
        return path.name


def _display_name(relative_path: str) -> str:
    parts = Path(relative_path).parts
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} / {'/'.join(parts[1:])}"


def _public_service_config(config: RuntimeServiceConfig, public_urls: PublicUrlConfig) -> RuntimeServiceConfig:
    data = config.model_dump(mode="json") if hasattr(config, "model_dump") else config.dict()
    data["glb_viewer_base_url"] = public_urls.public_glb_viewer_base_url
    data["blender_web_http_url"] = public_urls.public_blender_web_http_url
    data["blender_web_https_url"] = public_urls.public_blender_web_https_url
    return RuntimeServiceConfig(**data)


def _rewrite_urls(payload: Any, public_urls: PublicUrlConfig) -> Any:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return {key: _rewrite_urls(value, public_urls) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_rewrite_urls(value, public_urls) for value in payload]
    if isinstance(payload, str):
        replacements = (
            (public_urls.local_glb_viewer_base_url, public_urls.public_glb_viewer_base_url),
            (public_urls.local_blender_web_http_url, public_urls.public_blender_web_http_url),
            (public_urls.local_blender_web_https_url, public_urls.public_blender_web_https_url),
        )
        for local, public in replacements:
            if payload.startswith(local):
                return public + payload[len(local) :]
    return payload
