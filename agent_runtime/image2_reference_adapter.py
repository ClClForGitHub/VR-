"""Reference-image generation helpers for codex-self image2 calls."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import selectors
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent_runtime.codex_self_mcp import (
    CodexSelfMCPAdapter,
    CodexSelfMCPRunResult,
)


class Image2ReferenceAttachment(BaseModel):
    label: str
    path: str
    view_path: str | None = None
    mime_type: str | None = None
    view_mime_type: str | None = None
    sha256: str
    view_sha256: str | None = None
    role: str
    image_id: str | None = None
    source_requirement_id: str | None = None


class CodexSelfMCPImage2LogEvidence(BaseModel):
    log_path: str
    viewed_image_paths: list[str] = Field(default_factory=list)
    view_image_payload_paths: list[str] = Field(default_factory=list)
    image_generation_count: int = 0
    image_generation_call_ids: list[str] = Field(default_factory=list)
    revised_prompts: list[str] = Field(default_factory=list)
    final_content: str | None = None
    issues: list[str] = Field(default_factory=list)


class CodexSelfMCPImage2CallResult(BaseModel):
    ok: bool
    output_path: str | None = None
    log_path: str
    viewed_image_paths: list[str] = Field(default_factory=list)
    view_image_payload_paths: list[str] = Field(default_factory=list)
    image_generation_count: int = 0
    issues: list[str] = Field(default_factory=list)
    run_result: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)


class CodexSelfMCPImage2Adapter:
    """Use a fresh Codex sub-agent to view local references then generate."""

    def __init__(
        self,
        adapter: CodexSelfMCPAdapter | None = None,
        *,
        timeout_seconds: float = 900,
    ) -> None:
        self.adapter = adapter or CodexSelfMCPAdapter()
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        prompt: str,
        attachments: list[Image2ReferenceAttachment],
        output_path: str | Path,
        requirement_id: str,
        output_type: str,
        generation_mode: str,
        negative_prompt: str | None = None,
    ) -> CodexSelfMCPImage2CallResult:
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        prompt_path = output.with_suffix(".codex_self_image2_prompt.md")
        log_path = output.with_suffix(".codex_self_image2.jsonl")
        viewable_attachments, conversion_issues = prepare_viewable_attachment_manifest(
            attachments,
            view_dir=output.parent / "reference_views" / _safe_name(requirement_id),
        )
        prompt_path.write_text(
            build_codex_self_image2_prompt(
                prompt=prompt,
                attachments=viewable_attachments,
                requirement_id=requirement_id,
                output_type=output_type,
                generation_mode=generation_mode,
                negative_prompt=negative_prompt,
            ),
            encoding="utf-8",
        )
        if hasattr(self.adapter, "codex_command"):
            run_summary = _run_codex_mcp_until_image_result(
                codex_command=getattr(self.adapter, "codex_command"),
                prompt=prompt_path.read_text(encoding="utf-8"),
                cwd=output.parent,
                log_path=log_path,
                output_path=output,
                timeout_seconds=self.timeout_seconds,
            )
            run_ok = bool(run_summary.get("ok"))
            run_issues = list(run_summary.get("issues") or [])
            run_result_payload = run_summary
        else:
            plan = self.adapter.build_call_plan(
                prompt_file=prompt_path,
                cwd=output.parent,
                sandbox="read-only",
                approval_policy="never",
                timeout_seconds=self.timeout_seconds,
                log_path=log_path,
                extract_last_image_to=output,
            )
            run_result = self.adapter.run_call_plan(plan)
            run_ok = run_result.ok
            run_issues = list(run_result.issues)
            run_result_payload = _model_to_dict(run_result)
        evidence = inspect_codex_self_image2_log(log_path)
        expected_paths = [str(Path(_view_path(item)).expanduser().resolve()) for item in viewable_attachments]
        viewed_paths = {str(Path(path).expanduser().resolve()) for path in evidence.viewed_image_paths}
        payload_paths = {str(Path(path).expanduser().resolve()) for path in evidence.view_image_payload_paths}
        issues = list(conversion_issues)
        issues.extend(run_issues)
        issues.extend(evidence.issues)
        for expected_path in expected_paths:
            if expected_path not in viewed_paths:
                issues.append(f"codex_self_image2_missing_view_image_call:{expected_path}")
            if expected_path not in payload_paths:
                issues.append(f"codex_self_image2_missing_view_image_payload:{expected_path}")
        if evidence.image_generation_count < 1:
            issues.append("codex_self_image2_missing_image_generation")
        if not output.exists() or output.stat().st_size <= 0:
            issues.append("codex_self_image2_missing_output_image")
        return CodexSelfMCPImage2CallResult(
            ok=run_ok and not issues,
            output_path=str(output) if output.exists() else None,
            log_path=str(log_path),
            viewed_image_paths=evidence.viewed_image_paths,
            view_image_payload_paths=evidence.view_image_payload_paths,
            image_generation_count=evidence.image_generation_count,
            issues=_unique(issues),
            run_result=run_result_payload,
            evidence=_model_to_dict(evidence),
        )

    def run_view_image_canary(
        self,
        *,
        probe_dir: str | Path,
        timeout_seconds: float = 180,
    ) -> dict[str, Any]:
        probe_path = Path(probe_dir).expanduser().resolve()
        probe_path.mkdir(parents=True, exist_ok=True)
        image_path = probe_path / "codex_self_view_image_canary.png"
        _write_visual_canary_png(image_path)
        log_path = probe_path / "codex_self_view_image_canary.jsonl"
        prompt_path = probe_path / "codex_self_view_image_canary_prompt.md"
        prompt_path.write_text(
            "\n".join(
                [
                    "You are a visual canary.",
                    f"Use the image viewing tool to inspect this exact local file: {image_path}",
                    "Do not use shell commands, Python, OCR, file names, file size, or binary reads.",
                    'Return only JSON: {"used_visual_tool": true/false, "description": "...", "issues": []}.',
                ]
            ),
            encoding="utf-8",
        )
        plan = self.adapter.build_call_plan(
            prompt_file=prompt_path,
            cwd=probe_path,
            sandbox="read-only",
            approval_policy="never",
            timeout_seconds=timeout_seconds,
            log_path=log_path,
        )
        run_result = self.adapter.run_call_plan(plan)
        evidence = inspect_codex_self_image2_log(log_path)
        viewed = str(image_path.resolve()) in {str(Path(path).expanduser().resolve()) for path in evidence.viewed_image_paths}
        has_payload = str(image_path.resolve()) in {
            str(Path(path).expanduser().resolve()) for path in evidence.view_image_payload_paths
        }
        issues = list(run_result.issues)
        issues.extend(evidence.issues)
        if not viewed:
            issues.append("view_image_canary_missing_view_image_tool_call")
        if not has_payload:
            issues.append("view_image_canary_missing_input_image_payload")
        return {
            "ok": run_result.ok and viewed and has_payload and not issues,
            "image_path": str(image_path),
            "log_path": str(log_path),
            "viewed_image_paths": evidence.viewed_image_paths,
            "view_image_payload_paths": evidence.view_image_payload_paths,
            "issues": _unique(issues),
            "run_result": _model_to_dict(run_result),
            "evidence": _model_to_dict(evidence),
        }


def build_attachment_manifest(
    *,
    input_reference_image_ids: list[str],
    input_image_paths: list[str],
    source_requirement_ids: list[str],
    source_image_paths: list[str],
    output_type: str,
) -> list[Image2ReferenceAttachment]:
    attachments = []
    label_index = 1
    for image_id, path in zip(input_reference_image_ids, input_image_paths):
        role = "subject_reference" if output_type == "subject_concept" else "scene_reference"
        attachments.append(_attachment(label_index, path, role=role, image_id=image_id))
        label_index += 1
    for source_id, path in zip(source_requirement_ids, source_image_paths):
        attachments.append(_attachment(label_index, path, role="generated_concept_reference", source_requirement_id=source_id))
        label_index += 1
    return attachments


def prepare_viewable_attachment_manifest(
    attachments: list[Image2ReferenceAttachment],
    *,
    view_dir: str | Path,
) -> tuple[list[Image2ReferenceAttachment], list[str]]:
    """Create view_image-compatible copies while preserving original paths."""

    prepared: list[Image2ReferenceAttachment] = []
    issues: list[str] = []
    view_root = Path(view_dir).expanduser().resolve()
    for item in attachments:
        original_path = Path(item.path).expanduser().resolve()
        view_path = Path(item.view_path).expanduser().resolve() if item.view_path else original_path
        if item.view_path or _is_natively_viewable_image(original_path):
            prepared.append(
                _copy_attachment(
                    item,
                    view_path=str(view_path),
                    view_mime_type=_guess_mime_type(view_path, default=item.mime_type),
                    view_sha256=_sha256(view_path) if view_path.exists() else None,
                )
            )
            continue

        converted_path = view_root / f"{_safe_name(item.label)}_{original_path.stem}_{item.sha256[:12]}.png"
        try:
            _convert_image_to_png(original_path, converted_path)
        except Exception as exc:  # pragma: no cover - exercised by live AVIF/image codecs.
            issues.append(f"attachment_view_conversion_failed:{original_path}:{type(exc).__name__}:{exc}")
            prepared.append(
                _copy_attachment(
                    item,
                    view_path=str(view_path),
                    view_mime_type=_guess_mime_type(view_path, default=item.mime_type),
                    view_sha256=_sha256(view_path) if view_path.exists() else None,
                )
            )
            continue

        prepared.append(
            _copy_attachment(
                item,
                view_path=str(converted_path),
                view_mime_type="image/png",
                view_sha256=_sha256(converted_path),
            )
        )
    return prepared, issues


def build_codex_self_image2_prompt(
    *,
    prompt: str,
    attachments: list[Image2ReferenceAttachment],
    requirement_id: str,
    output_type: str,
    generation_mode: str,
    negative_prompt: str | None,
) -> str:
    attachment_lines = [
        (
            f"- {item.label}: view_path={_view_path(item)} | original_path={item.path} | "
            f"role={item.role} | sha256={item.sha256} | view_sha256={item.view_sha256 or item.sha256}"
        )
        for item in attachments
    ]
    if not attachment_lines:
        attachment_lines = ["- No visual attachments for this requirement."]
    mode_rules = _mode_rules(output_type, generation_mode, len(attachments))
    payload = {
        "requirement_id": requirement_id,
        "output_type": output_type,
        "generation_mode": generation_mode,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "attachments": [_model_to_dict(item) for item in attachments],
    }
    return (
        "You are a bounded image2 concept worker for image23D_Agent.\n"
        "This is one isolated requirement. Do not rely on previous chat context.\n"
        "Do not run shell commands to inspect images. Do not use file names, metadata, OCR, Python, PIL, ImageMagick, or binary reads as a substitute for vision.\n"
        "Before image generation, call the image viewing tool once for each listed attachment view_path.\n"
        "If the prompt names a specific IP/game/anime character and no subject reference image is attached, use available web/search capability to verify the character's visual identity before generation. If web/search is unavailable, rely only on explicit visual traits and source URLs already written in the prompt; do not invent identity details from memory.\n"
        "Then generate exactly one new bitmap image. Do not paste or collage the input image; use it as a visual reference.\n\n"
        "Attachment manifest:\n"
        + "\n".join(attachment_lines)
        + "\n\n"
        "Mode rules:\n"
        + mode_rules
        + "\n\n"
        "Structured request JSON:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n\n"
        "Final response after generation: compact JSON with keys ok, viewed_image_paths, generated, issues.\n"
    )


def inspect_codex_self_image2_log(log_path: str | Path) -> CodexSelfMCPImage2LogEvidence:
    log = Path(log_path).expanduser().resolve()
    viewed_paths = []
    payload_paths = []
    view_call_paths: dict[str, str] = {}
    call_ids = []
    revised_prompts = []
    final_content = None
    issues = []
    if not log.exists():
        return CodexSelfMCPImage2LogEvidence(log_path=str(log), issues=["missing_codex_self_image2_log"])
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("method") != "codex/event":
            continue
        msg = obj.get("params", {}).get("msg", {})
        msg_type = msg.get("type")
        if msg_type == "view_image_tool_call" and msg.get("path"):
            path = str(Path(str(msg["path"])).expanduser().resolve())
            viewed_paths.append(path)
            if msg.get("call_id"):
                view_call_paths[str(msg["call_id"])] = path
        elif msg_type == "image_generation_end":
            if msg.get("call_id"):
                call_ids.append(str(msg["call_id"]))
            if msg.get("revised_prompt"):
                revised_prompts.append(str(msg["revised_prompt"]))
        elif msg_type == "agent_message" and msg.get("phase") == "final_answer":
            final_content = str(msg.get("message") or "")
        if msg_type == "raw_response_item":
            item = msg.get("item") or {}
            if item.get("type") == "function_call" and item.get("name") == "view_image":
                call_id = str(item.get("call_id") or "")
                path = _view_image_path_from_arguments(item.get("arguments"))
                if call_id and path:
                    resolved = str(Path(path).expanduser().resolve())
                    view_call_paths[call_id] = resolved
                    viewed_paths.append(resolved)
            elif item.get("type") == "function_call_output":
                call_id = str(item.get("call_id") or "")
                path = view_call_paths.get(call_id)
                if not path:
                    continue
                output = item.get("output")
                if _has_input_image_payload(output):
                    payload_paths.append(path)
                elif _contains_unprocessed_image_message(output):
                    issues.append(f"view_image_payload_unprocessed:{path}")
    return CodexSelfMCPImage2LogEvidence(
        log_path=str(log),
        viewed_image_paths=_unique(viewed_paths),
        view_image_payload_paths=_unique(payload_paths),
        image_generation_count=len(call_ids),
        image_generation_call_ids=call_ids,
        revised_prompts=revised_prompts,
        final_content=final_content,
        issues=issues,
    )


def _run_codex_mcp_until_image_result(
    *,
    codex_command: str,
    prompt: str,
    cwd: Path,
    log_path: Path,
    output_path: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    proc = subprocess.Popen(
        [codex_command, "mcp-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=cwd,
        env=os.environ.copy(),
    )
    selector = selectors.DefaultSelector()
    assert proc.stdout is not None
    assert proc.stderr is not None
    assert proc.stdin is not None
    selector.register(proc.stdout, selectors.EVENT_READ, data="stdout")
    selector.register(proc.stderr, selectors.EVENT_READ, data="stderr")
    stderr_tail: list[str] = []
    stdout_tail: list[str] = []
    issues: list[str] = []
    last_result: str | None = None
    rpc_completed = False
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def send(payload: dict[str, Any]) -> None:
        proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def read_event_until(predicate, timeout: float):
        end = time.monotonic() + timeout
        with log_path.open("a", encoding="utf-8") as log_handle:
            while time.monotonic() < end:
                wait = max(0.05, min(1.0, end - time.monotonic()))
                for key, _ in selector.select(wait):
                    line = key.fileobj.readline()
                    if not line:
                        continue
                    if key.data == "stderr":
                        stderr_tail.append(line.rstrip())
                        del stderr_tail[:-20]
                        continue
                    stdout_tail.append(line.rstrip())
                    del stdout_tail[:-20]
                    log_handle.write(line)
                    log_handle.flush()
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if predicate(obj):
                        return obj
        return None

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "image23d-codex-self-image2",
                        "title": "image23D codex-self image2",
                        "version": "0.1.0",
                    },
                },
            }
        )
        init = read_event_until(lambda obj: obj.get("id") == 1, 30)
        if init is None:
            issues.append("codex_self_image2_initialize_timeout")
            return _stream_result(False, None, stdout_tail, stderr_tail, issues)
        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "codex",
                    "arguments": {
                        "prompt": prompt,
                        "cwd": str(cwd),
                        "sandbox": "read-only",
                        "approval-policy": "never",
                    },
                },
            }
        )

        end = time.monotonic() + timeout_seconds
        with log_path.open("a", encoding="utf-8") as log_handle:
            while time.monotonic() < end:
                wait = max(0.05, min(1.0, end - time.monotonic()))
                for key, _ in selector.select(wait):
                    line = key.fileobj.readline()
                    if not line:
                        continue
                    if key.data == "stderr":
                        stderr_tail.append(line.rstrip())
                        del stderr_tail[:-20]
                        continue
                    stdout_tail.append(line.rstrip())
                    del stdout_tail[:-20]
                    log_handle.write(line)
                    log_handle.flush()
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("id") == 2:
                        rpc_completed = True
                    msg = obj.get("params", {}).get("msg", {}) if obj.get("method") == "codex/event" else {}
                    if msg.get("type") == "image_generation_end" and msg.get("result"):
                        last_result = str(msg["result"])
                        raw = base64.b64decode(last_result)
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_bytes(raw)
                        return _stream_result(True, proc.returncode, stdout_tail, stderr_tail, issues, rpc_completed=rpc_completed)
                    if rpc_completed:
                        break
                if rpc_completed:
                    break
        if not last_result:
            issues.append("codex_self_image2_stream_missing_image_generation_result")
        return _stream_result(False, proc.returncode, stdout_tail, stderr_tail, issues, rpc_completed=rpc_completed)
    except Exception as exc:
        issues.append("codex_self_image2_stream_failed")
        return _stream_result(
            False,
            proc.returncode,
            stdout_tail,
            stderr_tail,
            issues,
            error=f"{type(exc).__name__}: {exc}",
            rpc_completed=rpc_completed,
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _stream_result(
    ok: bool,
    returncode: int | None,
    stdout_tail: list[str],
    stderr_tail: list[str],
    issues: list[str],
    *,
    error: str | None = None,
    rpc_completed: bool = False,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "returncode": returncode,
        "stdout_tail": "\n".join(stdout_tail[-20:]),
        "stderr_tail": "\n".join(stderr_tail[-20:]),
        "issues": _unique(issues),
        "error": error,
        "rpc_completed": rpc_completed,
        "stopped_after_image_generation_result": ok and not rpc_completed,
    }


def _view_path(item: Image2ReferenceAttachment) -> str:
    return item.view_path or item.path


def _copy_attachment(item: Image2ReferenceAttachment, **updates: Any) -> Image2ReferenceAttachment:
    if hasattr(item, "model_copy"):
        return item.model_copy(update=updates)
    return item.copy(update=updates)


def _is_natively_viewable_image(path: Path) -> bool:
    expected_by_suffix = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
    }
    expected = expected_by_suffix.get(path.suffix.lower())
    if expected is None:
        return False
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.format == expected
    except Exception:
        return False


def _convert_image_to_png(source: Path, target: Path) -> None:
    from PIL import Image, ImageOps

    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.save(target, format="PNG")


def _write_visual_canary_png(target: Path) -> None:
    from PIL import Image, ImageDraw

    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (128, 96), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 18, 54, 62), fill=(230, 32, 32))
    draw.ellipse((70, 22, 112, 64), fill=(30, 90, 230))
    draw.line((8, 82, 120, 82), fill=(20, 20, 20), width=3)
    image.save(target, format="PNG")


def _view_image_path_from_arguments(arguments: Any) -> str | None:
    if not arguments:
        return None
    if isinstance(arguments, str):
        try:
            payload = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    elif isinstance(arguments, dict):
        payload = arguments
    else:
        return None
    path = payload.get("path")
    return str(path) if path else None


def _has_input_image_payload(output: Any) -> bool:
    if isinstance(output, list):
        return any(isinstance(item, dict) and item.get("type") == "input_image" for item in output)
    if isinstance(output, dict):
        return output.get("type") == "input_image" or _has_input_image_payload(output.get("content"))
    return False


def _contains_unprocessed_image_message(output: Any) -> bool:
    if isinstance(output, str):
        lowered = output.lower()
        return "could not be processed" in lowered or "image content omitted" in lowered
    if isinstance(output, list):
        return any(_contains_unprocessed_image_message(item) for item in output)
    if isinstance(output, dict):
        return any(_contains_unprocessed_image_message(value) for value in output.values())
    return False


def _attachment(
    label_index: int,
    path: str,
    *,
    role: str,
    image_id: str | None = None,
    source_requirement_id: str | None = None,
) -> Image2ReferenceAttachment:
    resolved = Path(path).expanduser().resolve()
    return Image2ReferenceAttachment(
        label=f"Image {label_index}",
        path=str(resolved),
        mime_type=_guess_mime_type(resolved),
        sha256=_sha256(resolved),
        role=role,
        image_id=image_id,
        source_requirement_id=source_requirement_id,
    )


def _mode_rules(output_type: str, generation_mode: str, attachment_count: int) -> str:
    if output_type == "subject_concept":
        if attachment_count <= 0:
            return (
                "Generate one clean subject-only concept suitable as a Hunyuan3D source image, with neutral/simple background and the full object visible. "
                "Use only the prompt's explicit verified identity traits and source-backed visual details for named characters."
            )
        return (
            "Image 1 is the user-provided subject reference. Preserve identity, silhouette, proportions, major colors, materials, and defining details. "
            "Generate one clean subject-only concept suitable as a Hunyuan3D source image, with neutral/simple background and the full object visible."
        )
    if output_type == "scene_concept":
        if attachment_count:
            return (
                "Image 1 is the scene/layout/style reference. Generate a scene-only concept with clear environment layout, ground plane, lighting direction, and props. "
                "Do not include hero subjects unless explicitly requested."
            )
        return "Generate a scene-only concept with clear environment layout, ground plane, lighting direction, and props. Do not include hero subjects."
    if output_type == "target_render":
        return (
            "Images 1..N are generated subject and scene concept references from this same run. Use them as visual references, not pasted collage pieces. "
            "Generate one new coherent target render showing the intended final composition, preserving subject identities and scene layout."
        )
    return f"Generate one concept image for generation_mode={generation_mode}."


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _guess_mime_type(path: Path, *, default: str | None = "application/octet-stream") -> str | None:
    by_suffix = {
        ".avif": "image/avif",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }
    return by_suffix.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or default


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned[:96] or "attachment"


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if isinstance(model, BaseModel):
        return model.dict()
    return dict(model)
