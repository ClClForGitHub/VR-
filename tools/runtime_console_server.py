#!/usr/bin/env python3
"""Serve the image23D runtime console.

This server is intentionally thin: it reads/writes run-directory files through
`agent_runtime.runtime_console` and `agent_runtime.runtime_runs`, and embeds the
existing GLB viewer for 3D preview.
"""

from __future__ import annotations

import argparse
import base64
import json
import posixpath
import time
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from agent_runtime.runtime_console import (
    append_console_message,
    create_runtime_console_run,
    read_console_messages,
    read_console_uploads,
    save_console_upload,
)
from agent_runtime.runtime_delegation import plan_next_delegated_handoff, read_runtime_handoff_summary
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan, read_runtime_dispatch_plan
from agent_runtime.runtime_execution import execute_next_runtime_job, read_runtime_execution_summary
from agent_runtime.runtime_asset_actions import apply_runtime_asset_action, read_runtime_asset_action_summary
from agent_runtime.runtime_handoff_apply import (
    apply_blender_assembly_result,
    apply_concept_handoff_result,
    apply_scene_asset_handoff_result,
    apply_subject_asset_handoff_result,
    read_runtime_handoff_apply_summary,
)
from agent_runtime.runtime_loop import read_runtime_loop_summary, run_bounded_runtime_loop
from agent_runtime.runtime_state_apply import apply_next_runtime_candidate, read_runtime_apply_summary
from agent_runtime.runtime_user_actions import (
    approve_blender_preview,
    approve_concept_review,
    approve_model_assets,
    read_runtime_user_action_summary,
    request_blender_changes,
    request_concept_changes,
    request_model_changes,
)
from agent_runtime.runtime_worker import execute_next_runtime_worker, read_runtime_worker_summary
from agent_runtime.runtime_runs import (
    PublicUrlConfig,
    build_runtime_run_bundle,
    discover_runtime_runs,
    resolve_runtime_run_dir,
)


STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

RUN_EVENT_WATCH_FILES = [
    "state.json",
    "frontend_status.json",
    "summary.json",
    "runtime_plan.json",
    "runtime_execution.jsonl",
    "runtime_apply.jsonl",
    "runtime_loop.jsonl",
    "runtime_handoff.jsonl",
    "runtime_worker.jsonl",
    "runtime_user_action.jsonl",
    "runtime_asset_action.jsonl",
    "runtime_asset_action_summary.json",
    "runtime_handoff_apply.jsonl",
    "delivery_handoff.json",
    "chat.jsonl",
    "uploads.json",
]

RUN_EVENT_WATCH_GLOBS = [
    "viewer_export/*",
    "preview_render/*",
    "delivery_package/**/*.zip",
]


class RuntimeConsoleHandler(BaseHTTPRequestHandler):
    server_version = "RuntimeConsole/0.1"

    @property
    def root(self) -> Path:
        return self.server.root

    @property
    def static_root(self) -> Path:
        return self.server.static_root

    @property
    def public_urls(self) -> PublicUrlConfig:
        return self.server.public_urls

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self):
        parsed = urlparse(self.path)
        route = posixpath.normpath(parsed.path)
        try:
            if route in {"/", "/index.html"}:
                return self._send_static("index.html")
            if route in {"/app.js", "/styles.css", "/polish.css", "/ui18_final.css", "/ui19_public.css", "/ui25_creator.css"}:
                return self._send_static(route.lstrip("/"))
            if route == "/api/runs":
                query = parse_qs(parsed.query)
                collection = _query_string(query, "collection")
                limit = _safe_int(_query_string(query, "limit"), default=50, minimum=1, maximum=500)
                return self._send_json([
                    _model_to_dict(item)
                    for item in discover_runtime_runs(root=self.root, limit=limit, collection=collection)
                ])
            if route.startswith("/api/runs/"):
                return self._handle_run_get(route, parse_qs(parsed.query))
            self._send_error(HTTPStatus.NOT_FOUND, f"not found: {route}")
        except Exception as exc:  # pragma: no cover - exercised through manual use
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self):
        parsed = urlparse(self.path)
        route = posixpath.normpath(parsed.path)
        try:
            if route == "/api/runs":
                payload = self._read_json_body(default={})
                result = create_runtime_console_run(
                    root=self.root,
                    run_id=payload.get("run_id"),
                    project_id=payload.get("project_id"),
                    thread_id=payload.get("thread_id"),
                )
                return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
            if route.startswith("/api/runs/"):
                return self._handle_run_post(route)
            self._send_error(HTTPStatus.NOT_FOUND, f"not found: {route}")
        except Exception as exc:  # pragma: no cover - exercised through manual use
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def _handle_run_get(self, route: str, query: dict):
        parts = [unquote(part) for part in route.split("/") if part]
        if len(parts) < 3:
            return self._send_error(HTTPStatus.NOT_FOUND, "missing run id")
        run_key = parts[2]
        run_dir = resolve_runtime_run_dir(root=self.root, run_key=run_key)
        effective_dir = self._effective_run_dir(run_dir)
        if len(parts) == 3:
            bundle = build_runtime_run_bundle(run_dir, public_urls=self.public_urls)
            return self._send_json(_model_to_dict(bundle))
        leaf = parts[3]
        if leaf == "chat":
            return self._send_json([_model_to_dict(item) for item in read_console_messages(effective_dir)])
        if leaf == "uploads":
            return self._send_json([_model_to_dict(item) for item in read_console_uploads(effective_dir)])
        if leaf == "bundle":
            bundle = build_runtime_run_bundle(run_dir, public_urls=self.public_urls)
            return self._send_json(_model_to_dict(bundle))
        if leaf == "runtime-plan":
            plan = read_runtime_dispatch_plan(effective_dir)
            return self._send_json(plan or {})
        if leaf == "runtime-execution":
            summary = read_runtime_execution_summary(effective_dir)
            return self._send_json(summary or {})
        if leaf == "runtime-apply":
            summary = read_runtime_apply_summary(effective_dir)
            return self._send_json(summary or {})
        if leaf == "runtime-loop":
            summary = read_runtime_loop_summary(effective_dir)
            return self._send_json(summary or {})
        if leaf == "runtime-handoff":
            summary = read_runtime_handoff_summary(effective_dir)
            return self._send_json(summary or {})
        if leaf == "runtime-worker":
            summary = read_runtime_worker_summary(effective_dir)
            return self._send_json(summary or {})
        if leaf == "runtime-user-action":
            summary = read_runtime_user_action_summary(effective_dir)
            return self._send_json(summary or {})
        if leaf == "runtime-asset-action":
            summary = read_runtime_asset_action_summary(effective_dir)
            return self._send_json(summary or {})
        if leaf == "runtime-handoff-apply":
            summary = read_runtime_handoff_apply_summary(effective_dir)
            return self._send_json(summary or {})
        if leaf == "events":
            return self._send_run_events(run_dir, effective_dir, query)
        if leaf == "file":
            return self._send_run_file(run_dir, query)
        return self._send_error(HTTPStatus.NOT_FOUND, f"unknown run endpoint: {leaf}")

    def _handle_run_post(self, route: str):
        parts = [unquote(part) for part in route.split("/") if part]
        if len(parts) != 4:
            return self._send_error(HTTPStatus.NOT_FOUND, "expected /api/runs/<run_id>/<action>")
        run_key, action = parts[2], parts[3]
        run_dir = resolve_runtime_run_dir(root=self.root, run_key=run_key)
        effective_dir = self._effective_run_dir(run_dir)
        if action == "chat":
            payload = self._read_json_body()
            message = append_console_message(
                effective_dir,
                role=payload.get("role", "user"),
                text=payload.get("text", ""),
                attachment_ids=payload.get("attachment_ids") or [],
                metadata=payload.get("metadata") or {},
            )
            return self._send_json(_model_to_dict(message), status=HTTPStatus.CREATED)
        if action == "upload":
            upload = self._read_upload_body()
            result = save_console_upload(effective_dir, **upload)
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "plan":
            payload = self._read_json_body(default={})
            result = build_and_save_runtime_dispatch_plan(
                effective_dir,
                hunyuan3d_profile_id=payload.get("hunyuan3d_profile_id"),
                prefer_sub_agents_for_long_jobs=bool(payload.get("prefer_sub_agents_for_long_jobs", True)),
            )
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "step":
            payload = self._read_json_body(default={})
            result = execute_next_runtime_job(
                effective_dir,
                dry_run=bool(payload.get("dry_run", True)),
                response_text_by_node=payload.get("response_text_by_node") or None,
                blender_raw_caller_source=payload.get("blender_raw_caller_source") or None,
            )
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "apply":
            payload = self._read_json_body(default={})
            result = apply_next_runtime_candidate(
                effective_dir,
                rebuild_plan=bool(payload.get("rebuild_plan", True)),
            )
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "loop":
            payload = self._read_json_body(default={})
            result = run_bounded_runtime_loop(
                effective_dir,
                max_steps=int(payload.get("max_steps", 8)),
                dry_run=bool(payload.get("dry_run", True)),
                response_text_by_node=payload.get("response_text_by_node") or None,
                blender_raw_caller_source=payload.get("blender_raw_caller_source") or None,
            )
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "handoff":
            result = plan_next_delegated_handoff(effective_dir)
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "worker":
            payload = self._read_json_body(default={})
            result = execute_next_runtime_worker(
                effective_dir,
                backend=payload.get("backend", "fixture"),
                dry_run=bool(payload.get("dry_run", True)),
                fixture_payload=payload.get("fixture_payload") or {},
                handoff_id=payload.get("handoff_id"),
                rebuild_plan=bool(payload.get("rebuild_plan", True)),
                confirm_execute=bool(payload.get("confirm_execute", False)),
                timeout_seconds=float(payload.get("timeout_seconds", 300)),
            )
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "user-action":
            payload = self._read_json_body(default={})
            action_type = payload.get("action_type")
            if action_type == "approve_concept":
                result = approve_concept_review(
                    effective_dir,
                    note=payload.get("note"),
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            elif action_type == "approve_model_assets":
                result = approve_model_assets(
                    effective_dir,
                    note=payload.get("note"),
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            elif action_type == "approve_blender_preview":
                result = approve_blender_preview(
                    effective_dir,
                    note=payload.get("note"),
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            elif action_type == "request_concept_changes":
                result = request_concept_changes(
                    effective_dir,
                    feedback_text=payload.get("feedback_text", ""),
                    source_turn_id=payload.get("source_turn_id"),
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            elif action_type == "request_model_changes":
                result = request_model_changes(
                    effective_dir,
                    feedback_text=payload.get("feedback_text", ""),
                    source_turn_id=payload.get("source_turn_id"),
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            elif action_type == "request_blender_changes":
                result = request_blender_changes(
                    effective_dir,
                    feedback_text=payload.get("feedback_text", ""),
                    source_turn_id=payload.get("source_turn_id"),
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            else:
                return self._send_error(HTTPStatus.BAD_REQUEST, f"unknown user action: {action_type}")
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "asset-action":
            payload = self._read_json_body(default={})
            result = apply_runtime_asset_action(
                effective_dir,
                payload=payload,
                rebuild_plan=bool(payload.get("rebuild_plan", True)),
            )
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        if action == "handoff-apply":
            payload = self._read_json_body(default={})
            if payload.get("blender_results"):
                result = apply_blender_assembly_result(
                    effective_dir,
                    handoff_id=payload.get("handoff_id"),
                    blender_results=payload.get("blender_results") or [],
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            elif payload.get("scene_asset_results"):
                result = apply_scene_asset_handoff_result(
                    effective_dir,
                    handoff_id=payload.get("handoff_id"),
                    scene_asset_results=payload.get("scene_asset_results") or [],
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            elif payload.get("asset_results"):
                result = apply_subject_asset_handoff_result(
                    effective_dir,
                    handoff_id=payload.get("handoff_id"),
                    asset_results=payload.get("asset_results") or [],
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            else:
                result = apply_concept_handoff_result(
                    effective_dir,
                    handoff_id=payload.get("handoff_id"),
                    image_results=payload.get("image_results") or [],
                    rebuild_plan=bool(payload.get("rebuild_plan", True)),
                )
            return self._send_json(_model_to_dict(result), status=HTTPStatus.CREATED)
        return self._send_error(HTTPStatus.NOT_FOUND, f"unknown run action: {action}")

    def _effective_run_dir(self, run_dir: Path) -> Path:
        bundle = build_runtime_run_bundle(run_dir, public_urls=self.public_urls)
        return Path(bundle.effective_run_dir)

    def _send_run_file(self, run_dir: Path, query: dict):
        rel_values = query.get("path") or []
        if not rel_values:
            return self._send_error(HTTPStatus.BAD_REQUEST, "missing file path")
        rel_path = Path(rel_values[0])
        if rel_path.is_absolute() or any(part in {"", ".", ".."} for part in rel_path.parts):
            return self._send_error(HTTPStatus.BAD_REQUEST, "invalid file path")
        path = (run_dir / rel_path).resolve()
        try:
            path.relative_to(run_dir.resolve())
        except ValueError:
            return self._send_error(HTTPStatus.BAD_REQUEST, "file path escapes run")
        if not path.exists() or not path.is_file():
            return self._send_error(HTTPStatus.NOT_FOUND, f"missing file: {rel_values[0]}")
        content_type = STATIC_TYPES.get(path.suffix, "application/octet-stream")
        self._send_bytes(path.read_bytes(), content_type)

    def _send_static(self, filename: str):
        path = (self.static_root / filename).resolve()
        try:
            path.relative_to(self.static_root)
        except ValueError:
            return self._send_error(HTTPStatus.BAD_REQUEST, "invalid static path")
        if not path.exists():
            return self._send_error(HTTPStatus.NOT_FOUND, f"missing static file: {filename}")
        content_type = STATIC_TYPES.get(path.suffix, "application/octet-stream")
        self._send_bytes(path.read_bytes(), content_type)

    def _send_run_events(self, run_dir: Path, effective_dir: Path, query: dict):
        interval = _safe_float(query.get("interval", ["2"])[0], default=2.0, minimum=0.2, maximum=30.0)
        max_seconds = _safe_float(query.get("max_seconds", ["180"])[0], default=180.0, minimum=0.2, maximum=900.0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        last_signature = _runtime_event_signature(run_dir, effective_dir)
        started = time.monotonic()
        event_id = 0

        def write_event(event_name: str, payload: dict) -> bool:
            nonlocal event_id
            event_id += 1
            body = (
                f"id: {event_id}\n"
                f"event: {event_name}\n"
                f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            ).encode("utf-8")
            try:
                self.wfile.write(body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return False
            return True

        if not write_event("ready", {"ok": True, "signature": last_signature["fingerprint"]}):
            return
        next_heartbeat = time.monotonic() + 15.0
        while time.monotonic() - started < max_seconds:
            time.sleep(interval)
            signature = _runtime_event_signature(run_dir, effective_dir)
            if signature["fingerprint"] != last_signature["fingerprint"]:
                last_signature = signature
                if not write_event("refresh", signature):
                    return
            elif time.monotonic() >= next_heartbeat:
                if not write_event("heartbeat", {"ok": True, "signature": signature["fingerprint"]}):
                    return
                next_heartbeat = time.monotonic() + 15.0

    def _read_json_body(self, *, default=None):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0 and default is not None:
            return default
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def _read_upload_body(self) -> dict:
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if content_type.startswith("application/json"):
            payload = json.loads(body.decode("utf-8") or "{}")
            return {
                "filename": payload["filename"],
                "content": base64.b64decode(payload["content_base64"]),
                "mime_type": payload.get("mime_type"),
                "metadata": payload.get("metadata") or {},
            }
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("upload requires multipart/form-data or application/json")
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
        )
        fields = {}
        file_payload = None
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name != "file":
                if name:
                    fields[name] = part.get_content()
                continue
            filename = part.get_filename() or "upload.bin"
            file_payload = {
                "filename": filename,
                "content": part.get_payload(decode=True) or b"",
                "mime_type": part.get_content_type(),
            }
        if file_payload is not None:
            file_payload["metadata"] = {
                key: value
                for key, value in fields.items()
                if key in {"binding_role", "slot_id", "entity_id", "mention", "display_label"}
            }
            return file_payload
        raise ValueError("multipart upload did not include a file field")

    def _send_json(self, payload, *, status: HTTPStatus = HTTPStatus.OK):
        self._send_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8", status=status)

    def _send_error(self, status: HTTPStatus, message: str):
        self._send_json({"ok": False, "error": message}, status=status)

    def _send_bytes(self, body: bytes, content_type: str, *, status: HTTPStatus = HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _safe_float(value, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _safe_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _query_string(query: dict, key: str) -> str | None:
    values = query.get(key) or []
    if not values:
        return None
    value = str(values[0]).strip()
    return value or None


def _runtime_event_signature(run_dir: Path, effective_dir: Path) -> dict:
    roots = []
    for root in [run_dir, effective_dir]:
        resolved = root.resolve()
        if resolved not in roots:
            roots.append(resolved)
    records = []
    for root in roots:
        for rel in RUN_EVENT_WATCH_FILES:
            path = root / rel
            _append_signature_record(records, root, path)
        for pattern in RUN_EVENT_WATCH_GLOBS:
            for path in sorted(root.glob(pattern))[:200]:
                if path.is_file():
                    _append_signature_record(records, root, path)
    fingerprint = "|".join(records)
    return {
        "ok": True,
        "fingerprint": fingerprint,
        "file_count": len(records),
        "generated_at": time.time(),
    }


def _append_signature_record(records: list[str], root: Path, path: Path) -> None:
    try:
        rel = path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return
    try:
        stat = path.stat()
    except OSError:
        records.append(f"{root.name}:{rel}:missing")
        return
    if not path.is_file():
        return
    records.append(f"{root.name}:{rel}:{stat.st_mtime_ns}:{stat.st_size}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the image23D runtime console.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument("--root", default="/home/team/zouzhiyuan/image23D_Agent")
    parser.add_argument("--public-glb-viewer-base-url", default="http://10.2.16.106:8092")
    parser.add_argument("--public-blender-web-http-url", default="http://10.2.16.106:8300")
    parser.add_argument("--public-blender-web-https-url", default="https://10.2.16.106:8301")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    static_root = root / "web" / "runtime_console"
    public_urls = PublicUrlConfig(
        public_glb_viewer_base_url=args.public_glb_viewer_base_url.rstrip("/"),
        public_blender_web_http_url=args.public_blender_web_http_url.rstrip("/"),
        public_blender_web_https_url=args.public_blender_web_https_url.rstrip("/"),
    )
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((args.host, args.port), RuntimeConsoleHandler)
    server.root = root
    server.static_root = static_root
    server.public_urls = public_urls
    print(f"Serving runtime console on http://{args.host}:{args.port}/", flush=True)
    print(f"Workspace root: {root}", flush=True)
    print(f"Static root: {static_root}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
