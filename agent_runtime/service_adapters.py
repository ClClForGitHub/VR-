"""Adapters for existing local model services.

These adapters describe and check the local services started by
`scripts/start_a40_services.sh`. They do not start new services and do not hide
long-running generation behind tests or status checks.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, field_validator

from agent_runtime.viewer import ViewerHeadResult, head_url


class JsonHttpResult(BaseModel):
    url: str
    ok: bool
    status: int | None = None
    content_type: str | None = None
    data: dict[str, Any] | list[Any] | None = None
    error: str | None = None


class Hunyuan3DGenerationPayload(BaseModel):
    """Current local `Hunyuan3D-2.1/api_models.py` GenerationRequest shape."""

    image: str
    remove_background: bool = True
    texture: bool = True
    seed: int = Field(default=1234, ge=0, le=2**32 - 1)
    randomize_seed: bool = True
    octree_resolution: int = Field(default=768, ge=64, le=1024)
    num_inference_steps: int = Field(default=50, ge=1, le=100)
    guidance_scale: float = Field(default=5.0, ge=0.1, le=20.0)
    num_chunks: int = Field(default=200000, ge=1000, le=5000000)
    face_count: int = Field(default=1000000, ge=1000, le=1000000)

    @field_validator("image")
    def image_is_not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("image base64 must not be empty")
        return value


class Hunyuan3DHealth(BaseModel):
    ok: bool
    base_url: str
    health: JsonHttpResult
    openapi: ViewerHeadResult


class Hunyuan3DTaskResponse(BaseModel):
    ok: bool
    uid: str | None = None
    raw: JsonHttpResult


class Hunyuan3DTaskStatus(BaseModel):
    ok: bool
    status: str | None = None
    has_model_base64: bool = False
    message: str | None = None
    raw: JsonHttpResult


class WorldMirrorRuntimeStatus(BaseModel):
    ok: bool
    base_url: str
    index: ViewerHeadResult
    config: ViewerHeadResult


class WorldMirrorEndpointIO(BaseModel):
    component_id: int
    component_type: str | None = None
    label: str | None = None
    value: Any = None
    api_info: dict[str, Any] | list[Any] | str | None = None


class WorldMirrorEndpointContract(BaseModel):
    api_name: str
    queue: bool = True
    connection: str | None = None
    input_ids: list[int] = Field(default_factory=list)
    output_ids: list[int] = Field(default_factory=list)
    inputs: list[WorldMirrorEndpointIO] = Field(default_factory=list)
    outputs: list[WorldMirrorEndpointIO] = Field(default_factory=list)


class WorldMirrorGenerationContract(BaseModel):
    ok: bool
    base_url: str
    api_prefix: str = "/gradio_api"
    gradio_version: str | None = None
    protocol: str | None = None
    upload_endpoint: WorldMirrorEndpointContract | None = None
    reconstruct_endpoint: WorldMirrorEndpointContract | None = None
    issues: list[str] = Field(default_factory=list)


class WorldMirrorGenerationRequest(BaseModel):
    input_files: list[str] = Field(default_factory=list)
    workspace_dir: str | None = None
    time_interval: float = Field(default=1.0, ge=0.1, le=10.0)
    frame_selector: str = "All"
    show_camera: bool = True
    filter_sky_bg: bool = False
    show_mesh: bool = True
    filter_ambiguous: bool = True

    @field_validator("input_files")
    def input_files_are_not_empty_strings(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item:
                raise ValueError("input_files must not contain empty paths")
        return value


class WorldMirrorGenerationCallPlan(BaseModel):
    ok: bool
    base_url: str
    api_prefix: str
    upload_url: str
    reconstruct_url: str
    upload_api_name: str = "_on_upload"
    reconstruct_api_name: str = "gradio_demo"
    upload_payload: dict[str, Any] | None = None
    reconstruct_payload: dict[str, Any]
    workspace_dir: str | None = None
    workspace_source: str
    request: WorldMirrorGenerationRequest
    contract: WorldMirrorGenerationContract
    submits_long_running_job: bool = False
    issues: list[str] = Field(default_factory=list)


class WorldMirrorQueuedSubmission(BaseModel):
    ok: bool
    base_url: str
    api_prefix: str
    api_name: str
    submit_url: str
    event_id: str | None = None
    raw: JsonHttpResult
    submits_long_running_job: bool = False
    issues: list[str] = Field(default_factory=list)


class WorldMirrorSSEEvent(BaseModel):
    event: str | None = None
    data: Any = None


class WorldMirrorQueuedPollResult(BaseModel):
    ok: bool
    base_url: str
    api_prefix: str
    api_name: str
    event_id: str
    stream_url: str
    complete: bool = False
    output_data: Any = None
    events: list[WorldMirrorSSEEvent] = Field(default_factory=list)
    error: str | None = None
    issues: list[str] = Field(default_factory=list)


class WorldMirrorGenerationSubmission(BaseModel):
    ok: bool
    call_plan: WorldMirrorGenerationCallPlan
    reconstruct_submission: WorldMirrorQueuedSubmission | None = None
    submits_long_running_job: bool = True
    issues: list[str] = Field(default_factory=list)


class WorldMirrorUploadSubmission(BaseModel):
    ok: bool
    call_plan: WorldMirrorGenerationCallPlan
    upload_submission: WorldMirrorQueuedSubmission | None = None
    submits_long_running_job: bool = False
    issues: list[str] = Field(default_factory=list)


class WorldMirrorUploadPollResult(BaseModel):
    ok: bool
    poll_result: WorldMirrorQueuedPollResult
    target_dir: str | None = None
    issues: list[str] = Field(default_factory=list)


class Hunyuan3DServiceAdapter:
    """Client for the existing Hunyuan3D-2.1 FastAPI service."""

    def __init__(self, *, base_url: str = "http://127.0.0.1:8091", timeout: float = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict:
        health = _get_json(f"{self.base_url}/health", timeout=self.timeout)
        openapi = head_url(f"{self.base_url}/openapi.json", timeout=self.timeout)
        return _model_to_dict(
            Hunyuan3DHealth(
                ok=health.ok and openapi.ok,
                base_url=self.base_url,
                health=health,
                openapi=openapi,
            )
        )

    def build_payload(
        self,
        *,
        image_base64: str | None = None,
        image_path: str | Path | None = None,
        remove_background: bool = True,
        texture: bool = True,
        seed: int = 1234,
        randomize_seed: bool = True,
        octree_resolution: int = 768,
        num_inference_steps: int = 50,
        guidance_scale: float = 5.0,
        num_chunks: int = 200000,
        face_count: int = 1000000,
    ) -> Hunyuan3DGenerationPayload:
        if image_base64 is None:
            if image_path is None:
                raise ValueError("image_base64 or image_path is required")
            image_base64 = encode_file_base64(image_path)
        return Hunyuan3DGenerationPayload(
            image=image_base64,
            remove_background=remove_background,
            texture=texture,
            seed=seed,
            randomize_seed=randomize_seed,
            octree_resolution=octree_resolution,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            num_chunks=num_chunks,
            face_count=face_count,
        )

    def submit_async(self, payload: Hunyuan3DGenerationPayload | dict[str, Any]) -> dict:
        result = _post_json(f"{self.base_url}/send", _model_to_dict(payload), timeout=self.timeout)
        uid = result.data.get("uid") if isinstance(result.data, dict) else None
        return _model_to_dict(Hunyuan3DTaskResponse(ok=result.ok and bool(uid), uid=uid, raw=result))

    def task_status(self, uid: str) -> dict:
        result = _get_json(f"{self.base_url}/status/{uid}", timeout=self.timeout)
        status = result.data.get("status") if isinstance(result.data, dict) else None
        model_base64 = result.data.get("model_base64") if isinstance(result.data, dict) else None
        message = result.data.get("message") if isinstance(result.data, dict) else None
        return _model_to_dict(
            Hunyuan3DTaskStatus(
                ok=result.ok and bool(status),
                status=status,
                has_model_base64=bool(model_base64),
                message=message,
                raw=result,
            )
        )

    def save_status_model(self, status_payload: dict[str, Any], output_path: str | Path) -> Path:
        raw = status_payload.get("raw", {})
        data = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(data, dict) or not data.get("model_base64"):
            raise ValueError("status payload does not contain model_base64")
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(base64.b64decode(data["model_base64"]))
        return output


class WorldMirrorServiceAdapter:
    """Status adapter for the existing HY-World WorldMirror Gradio service."""

    def __init__(self, *, base_url: str = "http://127.0.0.1:8081", timeout: float = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def runtime_status(self) -> dict:
        index = _head_or_get_url(f"{self.base_url}/", timeout=self.timeout)
        config = _head_or_get_url(f"{self.base_url}/config", timeout=self.timeout)
        return _model_to_dict(
            WorldMirrorRuntimeStatus(
                ok=index.ok and config.ok,
                base_url=self.base_url,
                index=index,
                config=config,
            )
        )

    def config(self) -> JsonHttpResult:
        return _get_json(f"{self.base_url}/config", timeout=self.timeout)

    def generation_contract(self, config_payload: dict[str, Any] | None = None) -> WorldMirrorGenerationContract:
        payload = config_payload
        issues = []
        if payload is None:
            config_result = self.config()
            if not config_result.ok or not isinstance(config_result.data, dict):
                return WorldMirrorGenerationContract(
                    ok=False,
                    base_url=self.base_url,
                    issues=[config_result.error or "worldmirror_config_unavailable"],
                )
            payload = config_result.data
        components = {item.get("id"): item for item in payload.get("components", []) if isinstance(item, dict)}
        upload_dep = _find_gradio_dependency(payload, "_on_upload")
        reconstruct_dep = _find_gradio_dependency(payload, "gradio_demo")
        if upload_dep is None:
            issues.append("missing__on_upload_endpoint")
        if reconstruct_dep is None:
            issues.append("missing_gradio_demo_endpoint")
        api_prefix = payload.get("api_prefix") or "/gradio_api"
        return WorldMirrorGenerationContract(
            ok=not issues,
            base_url=self.base_url,
            api_prefix=api_prefix,
            gradio_version=payload.get("version"),
            protocol=payload.get("protocol"),
            upload_endpoint=_endpoint_contract(upload_dep, components) if upload_dep is not None else None,
            reconstruct_endpoint=_endpoint_contract(reconstruct_dep, components) if reconstruct_dep is not None else None,
            issues=issues,
        )

    def build_generation_call_plan(
        self,
        request: WorldMirrorGenerationRequest,
        *,
        config_payload: dict[str, Any] | None = None,
    ) -> WorldMirrorGenerationCallPlan:
        contract = self.generation_contract(config_payload=config_payload)
        issues = list(contract.issues)
        file_payloads = [_gradio_file_payload(path) for path in request.input_files]
        workspace_dir = request.workspace_dir
        workspace_source = "provided_workspace_dir" if workspace_dir else "upload_output_target_dir"
        upload_payload = None
        if file_payloads:
            upload_payload = {"data": [file_payloads, request.time_interval]}
        elif workspace_dir is None:
            issues.append("input_files_or_workspace_dir_required")
        reconstruct_workspace = workspace_dir or "<from _on_upload output[0]>"
        reconstruct_payload = {
            "data": [
                reconstruct_workspace,
                request.frame_selector,
                request.show_camera,
                request.filter_sky_bg,
                request.show_mesh,
                request.filter_ambiguous,
            ]
        }
        return WorldMirrorGenerationCallPlan(
            ok=contract.ok and not issues,
            base_url=self.base_url,
            api_prefix=contract.api_prefix,
            upload_url=f"{self.base_url}{contract.api_prefix}/call/_on_upload",
            reconstruct_url=f"{self.base_url}{contract.api_prefix}/call/gradio_demo",
            upload_payload=upload_payload,
            reconstruct_payload=reconstruct_payload,
            workspace_dir=workspace_dir,
            workspace_source=workspace_source,
            request=request,
            contract=contract,
            issues=issues,
        )

    def submit_queued_call(
        self,
        *,
        api_name: str,
        payload: dict[str, Any],
        api_prefix: str = "/gradio_api",
        submits_long_running_job: bool = False,
    ) -> WorldMirrorQueuedSubmission:
        submit_url = f"{self.base_url}{api_prefix}/call/{api_name}"
        result = _post_json(submit_url, payload, timeout=self.timeout)
        event_id = None
        if isinstance(result.data, dict):
            event_id = result.data.get("event_id") or result.data.get("id")
        issues: list[str] = []
        if not result.ok:
            issues.append(result.error or "queued_call_submit_failed")
        if result.ok and not event_id:
            issues.append("missing_event_id")
        return WorldMirrorQueuedSubmission(
            ok=result.ok and bool(event_id) and not issues,
            base_url=self.base_url,
            api_prefix=api_prefix,
            api_name=api_name,
            submit_url=submit_url,
            event_id=event_id,
            raw=result,
            submits_long_running_job=submits_long_running_job,
            issues=issues,
        )

    def submit_generation(
        self,
        request: WorldMirrorGenerationRequest,
        *,
        config_payload: dict[str, Any] | None = None,
    ) -> WorldMirrorGenerationSubmission:
        plan = self.build_generation_call_plan(request, config_payload=config_payload)
        issues = list(plan.issues)
        if not request.workspace_dir:
            issues.append("workspace_dir_required_for_reconstruct_submit")
        if issues or not plan.ok:
            return WorldMirrorGenerationSubmission(ok=False, call_plan=plan, issues=issues)
        submission = self.submit_queued_call(
            api_name=plan.reconstruct_api_name,
            payload=plan.reconstruct_payload,
            api_prefix=plan.api_prefix,
            submits_long_running_job=True,
        )
        return WorldMirrorGenerationSubmission(
            ok=submission.ok,
            call_plan=plan,
            reconstruct_submission=submission,
            issues=list(submission.issues),
        )

    def submit_upload(
        self,
        request: WorldMirrorGenerationRequest,
        *,
        config_payload: dict[str, Any] | None = None,
    ) -> WorldMirrorUploadSubmission:
        plan = self.build_generation_call_plan(request, config_payload=config_payload)
        issues = list(plan.issues)
        if plan.upload_payload is None:
            issues.append("input_files_required_for_upload")
        if issues or not plan.ok:
            return WorldMirrorUploadSubmission(ok=False, call_plan=plan, issues=issues)
        upload_result = self.upload_files(request.input_files, api_prefix=plan.api_prefix)
        if not upload_result.ok or not isinstance(upload_result.data, list):
            issues.append(upload_result.error or "worldmirror_file_upload_failed")
            return WorldMirrorUploadSubmission(ok=False, call_plan=plan, issues=issues)
        uploaded_payload = {
            "data": [
                [
                    _gradio_uploaded_file_payload(
                        uploaded_path,
                        original_path=original_path,
                    )
                    for uploaded_path, original_path in zip(upload_result.data, request.input_files, strict=False)
                ],
                request.time_interval,
            ]
        }
        plan = _copy_model_update(plan, {"upload_payload": uploaded_payload})
        submission = self.submit_queued_call(
            api_name=plan.upload_api_name,
            payload=plan.upload_payload,
            api_prefix=plan.api_prefix,
            submits_long_running_job=False,
        )
        return WorldMirrorUploadSubmission(
            ok=submission.ok,
            call_plan=plan,
            upload_submission=submission,
            issues=list(submission.issues),
        )

    def upload_files(self, input_files: list[str], *, api_prefix: str = "/gradio_api") -> JsonHttpResult:
        upload_url = f"{self.base_url}{api_prefix}/upload"
        return _post_multipart_files(upload_url, [Path(path).expanduser().resolve() for path in input_files], timeout=self.timeout)

    def poll_queued_call(
        self,
        *,
        api_name: str,
        event_id: str,
        api_prefix: str = "/gradio_api",
    ) -> WorldMirrorQueuedPollResult:
        stream_url = f"{self.base_url}{api_prefix}/call/{api_name}/{event_id}"
        if not event_id:
            return WorldMirrorQueuedPollResult(
                ok=False,
                base_url=self.base_url,
                api_prefix=api_prefix,
                api_name=api_name,
                event_id=event_id,
                stream_url=stream_url,
                issues=["event_id_required"],
            )
        events, error = _get_sse_events(stream_url, timeout=self.timeout)
        complete = any(event.event == "complete" for event in events)
        error_event = next((event for event in events if event.event == "error"), None)
        issues: list[str] = []
        if error:
            issues.append(error)
        if error_event is not None:
            issues.append("worldmirror_queue_error_event")
        if not complete and not issues:
            issues.append("worldmirror_queue_not_complete")
        return WorldMirrorQueuedPollResult(
            ok=complete and error_event is None and not error,
            base_url=self.base_url,
            api_prefix=api_prefix,
            api_name=api_name,
            event_id=event_id,
            stream_url=stream_url,
            complete=complete,
            output_data=_last_complete_event_data(events),
            events=events,
            error=error,
            issues=issues,
        )

    def poll_upload(
        self,
        *,
        event_id: str,
        api_prefix: str = "/gradio_api",
    ) -> WorldMirrorUploadPollResult:
        poll_result = self.poll_queued_call(api_name="_on_upload", event_id=event_id, api_prefix=api_prefix)
        target_dir = extract_worldmirror_upload_target_dir(poll_result.output_data)
        issues = list(poll_result.issues)
        if poll_result.ok and not target_dir:
            issues.append("upload_target_dir_not_found")
        return WorldMirrorUploadPollResult(
            ok=poll_result.ok and bool(target_dir),
            poll_result=poll_result,
            target_dir=target_dir,
            issues=issues,
        )


def encode_file_base64(path: str | Path) -> str:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    return base64.b64encode(source.read_bytes()).decode("ascii")


def _get_json(url: str, *, timeout: float) -> JsonHttpResult:
    return _request_json("GET", url, None, timeout=timeout)


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> JsonHttpResult:
    return _request_json("POST", url, payload, timeout=timeout)


def _post_multipart_files(url: str, files: list[Path], *, timeout: float) -> JsonHttpResult:
    boundary = "----image23d-agent-gradio-upload-boundary"
    chunks: list[bytes] = []
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="files"; filename="{path.name}"\r\n'
                    f"Content-Type: {mime_type}\r\n\r\n"
                ).encode("utf-8"),
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    request = Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read()
            content_type = response.headers.get("Content-Type")
            parsed = json.loads(raw_body.decode("utf-8")) if raw_body else None
            return JsonHttpResult(
                url=url,
                ok=200 <= response.status < 300,
                status=response.status,
                content_type=content_type,
                data=parsed,
            )
    except HTTPError as exc:
        return JsonHttpResult(
            url=url,
            ok=False,
            status=exc.code,
            content_type=exc.headers.get("Content-Type") if exc.headers else None,
            error=f"HTTPError: {exc}",
        )
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return JsonHttpResult(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    *,
    timeout: float,
) -> JsonHttpResult:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read()
            content_type = response.headers.get("Content-Type")
            parsed = json.loads(raw_body.decode("utf-8")) if raw_body else None
            return JsonHttpResult(
                url=url,
                ok=200 <= response.status < 300,
                status=response.status,
                content_type=content_type,
                data=parsed,
            )
    except HTTPError as exc:
        return JsonHttpResult(
            url=url,
            ok=False,
            status=exc.code,
            content_type=exc.headers.get("Content-Type") if exc.headers else None,
            error=f"HTTPError: {exc}",
        )
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return JsonHttpResult(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")


def _head_or_get_url(url: str, *, timeout: float) -> ViewerHeadResult:
    head = head_url(url, timeout=timeout)
    if head.ok:
        return head
    if head.error and "HTTP Error 405" in head.error:
        try:
            request = Request(url, method="GET")
            with urlopen(request, timeout=timeout) as response:
                length = response.headers.get("Content-Length")
                return ViewerHeadResult(
                    url=url,
                    ok=200 <= response.status < 300,
                    status=response.status,
                    content_type=response.headers.get("Content-Type"),
                    content_length=int(length) if length is not None else None,
                )
        except Exception as exc:  # pragma: no cover - exact urllib errors vary by platform
            return ViewerHeadResult(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")
    return head


def _get_sse_events(url: str, *, timeout: float) -> tuple[list[WorldMirrorSSEEvent], str | None]:
    request = Request(url, headers={"Accept": "text/event-stream"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read()
            text = raw_body.decode("utf-8", errors="replace")
            return _parse_sse_events(text), None
    except HTTPError as exc:
        return [], f"HTTPError: {exc}"
    except (URLError, TimeoutError) as exc:
        return [], f"{type(exc).__name__}: {exc}"


def _parse_sse_events(text: str) -> list[WorldMirrorSSEEvent]:
    events: list[WorldMirrorSSEEvent] = []
    current_event: str | None = None
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal current_event, data_lines
        if current_event is None and not data_lines:
            return
        raw_data = "\n".join(data_lines)
        parsed_data: Any = None
        if raw_data:
            try:
                parsed_data = json.loads(raw_data)
            except json.JSONDecodeError:
                parsed_data = raw_data
        events.append(WorldMirrorSSEEvent(event=current_event, data=parsed_data))
        current_event = None
        data_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    flush()
    return events


def _last_complete_event_data(events: list[WorldMirrorSSEEvent]) -> Any:
    for event in reversed(events):
        if event.event == "complete":
            return event.data
    return events[-1].data if events else None


def extract_worldmirror_upload_target_dir(output_data: Any) -> str | None:
    if isinstance(output_data, str):
        return output_data
    if isinstance(output_data, dict):
        direct = output_data.get("target_dir")
        if isinstance(direct, str) and direct:
            return direct
        data = output_data.get("data")
        if data is not None:
            return extract_worldmirror_upload_target_dir(data)
    if isinstance(output_data, list) and output_data:
        first = output_data[0]
        if isinstance(first, str) and first:
            return first
        if isinstance(first, dict):
            return extract_worldmirror_upload_target_dir(first)
    return None


def _model_to_dict(model) -> dict:
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _find_gradio_dependency(config_payload: dict[str, Any], api_name: str) -> dict[str, Any] | None:
    for dependency in config_payload.get("dependencies", []) or []:
        if isinstance(dependency, dict) and dependency.get("api_name") == api_name:
            return dependency
    return None


def _endpoint_contract(
    dependency: dict[str, Any],
    components: dict[int, dict[str, Any]],
) -> WorldMirrorEndpointContract:
    input_ids = list(dependency.get("inputs", []) or [])
    output_ids = list(dependency.get("outputs", []) or [])
    return WorldMirrorEndpointContract(
        api_name=dependency.get("api_name") or "",
        queue=bool(dependency.get("queue", True)),
        connection=dependency.get("connection"),
        input_ids=input_ids,
        output_ids=output_ids,
        inputs=[_component_io(component_id, components.get(component_id, {})) for component_id in input_ids],
        outputs=[_component_io(component_id, components.get(component_id, {})) for component_id in output_ids],
    )


def _component_io(component_id: int, component: dict[str, Any]) -> WorldMirrorEndpointIO:
    props = component.get("props") if isinstance(component.get("props"), dict) else {}
    return WorldMirrorEndpointIO(
        component_id=component_id,
        component_type=component.get("type"),
        label=props.get("label"),
        value=props.get("value"),
        api_info=component.get("api_info"),
    )


def _gradio_file_payload(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    return {
        "path": str(file_path),
        "orig_name": file_path.name,
        "size": file_path.stat().st_size,
        "meta": {"_type": "gradio.FileData"},
    }


def _gradio_uploaded_file_payload(uploaded_path: Any, *, original_path: str | Path) -> dict[str, Any]:
    source = Path(original_path).expanduser().resolve()
    return {
        "path": str(uploaded_path),
        "orig_name": source.name,
        "meta": {"_type": "gradio.FileData"},
    }


def _copy_model_update(model: Any, update: dict[str, Any]) -> Any:
    if hasattr(model, "model_copy"):
        return model.model_copy(update=update)
    return model.copy(update=update)
