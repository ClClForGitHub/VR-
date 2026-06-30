import base64
from pathlib import Path

import pytest

from agent_runtime import service_adapters as service_adapter_module
from agent_runtime.service_adapters import (
    Hunyuan3DServiceAdapter,
    JsonHttpResult,
    WorldMirrorGenerationRequest,
    WorldMirrorSSEEvent,
    WorldMirrorServiceAdapter,
    encode_file_base64,
    extract_worldmirror_upload_target_dir,
)
from agent_runtime.viewer import ViewerHeadResult


def test_encode_file_base64_reads_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "image.png"
    source.write_bytes(b"demo-bytes")

    assert encode_file_base64(source) == base64.b64encode(b"demo-bytes").decode("ascii")

    with pytest.raises(FileNotFoundError):
        encode_file_base64(tmp_path / "missing.png")


def test_hunyuan3d_build_payload_uses_current_api_model_fields(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"image")

    payload = Hunyuan3DServiceAdapter().build_payload(
        image_path=image,
        texture=False,
        randomize_seed=False,
        seed=42,
        num_inference_steps=5,
    )
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()

    assert data["image"] == base64.b64encode(b"image").decode("ascii")
    assert data["texture"] is False
    assert data["randomize_seed"] is False
    assert data["seed"] == 42
    assert data["num_inference_steps"] == 5
    assert "type" not in data


@pytest.mark.parametrize(
    "kwargs",
    [
        {"image_base64": ""},
        {"image_base64": "abc", "seed": -1},
        {"image_base64": "abc", "octree_resolution": 32},
        {"image_base64": "abc", "num_chunks": 10},
    ],
)
def test_hunyuan3d_build_payload_validates_current_api_bounds(kwargs) -> None:
    with pytest.raises(ValueError):
        Hunyuan3DServiceAdapter().build_payload(**kwargs)


def test_hunyuan3d_health_checks_health_and_openapi(monkeypatch) -> None:
    def fake_get_json(url: str, *, timeout: float):
        assert timeout == 3
        return JsonHttpResult(url=url, ok=True, status=200, data={"status": "healthy", "worker_id": "abc"})

    def fake_head_url(url: str, timeout: float):
        assert timeout == 3
        return ViewerHeadResult(url=url, ok=True, status=200, content_type="application/json")

    monkeypatch.setattr("agent_runtime.service_adapters._get_json", fake_get_json)
    monkeypatch.setattr("agent_runtime.service_adapters.head_url", fake_head_url)

    health = Hunyuan3DServiceAdapter(base_url="http://hunyuan.local/", timeout=3).health()

    assert health["ok"] is True
    assert health["base_url"] == "http://hunyuan.local"
    assert health["health"]["data"]["worker_id"] == "abc"
    assert health["openapi"]["content_type"] == "application/json"


def test_hunyuan3d_submit_async_and_status(monkeypatch) -> None:
    def fake_post_json(url: str, payload: dict, *, timeout: float):
        assert url == "http://hunyuan.local/send"
        assert payload["image"] == "abc"
        return JsonHttpResult(url=url, ok=True, status=200, data={"uid": "task_001"})

    def fake_get_json(url: str, *, timeout: float):
        assert url == "http://hunyuan.local/status/task_001"
        return JsonHttpResult(url=url, ok=True, status=200, data={"status": "completed", "model_base64": "Z2xi"})

    monkeypatch.setattr("agent_runtime.service_adapters._post_json", fake_post_json)
    monkeypatch.setattr("agent_runtime.service_adapters._get_json", fake_get_json)
    adapter = Hunyuan3DServiceAdapter(base_url="http://hunyuan.local")
    payload = adapter.build_payload(image_base64="abc")

    response = adapter.submit_async(payload)
    status = adapter.task_status("task_001")

    assert response["ok"] is True
    assert response["uid"] == "task_001"
    assert status["ok"] is True
    assert status["status"] == "completed"
    assert status["has_model_base64"] is True


def test_hunyuan3d_save_status_model_writes_base64_model(tmp_path: Path) -> None:
    output = Hunyuan3DServiceAdapter().save_status_model(
        {"raw": {"data": {"model_base64": base64.b64encode(b"glb-data").decode("ascii")}}},
        tmp_path / "asset.glb",
    )

    assert output.read_bytes() == b"glb-data"

    with pytest.raises(ValueError, match="does not contain model_base64"):
        Hunyuan3DServiceAdapter().save_status_model({"raw": {"data": {}}}, tmp_path / "missing.glb")


def test_worldmirror_runtime_status_checks_gradio_index_and_config(monkeypatch) -> None:
    calls = []

    def fake_probe(url: str, *, timeout: float):
        calls.append((url, timeout))
        return ViewerHeadResult(url=url, ok=True, status=200, content_type="text/html")

    monkeypatch.setattr("agent_runtime.service_adapters._head_or_get_url", fake_probe)

    status = WorldMirrorServiceAdapter(base_url="http://world.local/", timeout=4).runtime_status()

    assert status["ok"] is True
    assert status["base_url"] == "http://world.local"
    assert calls == [
        ("http://world.local/", 4),
        ("http://world.local/config", 4),
    ]


def test_worldmirror_runtime_status_reports_config_failure(monkeypatch) -> None:
    def fake_probe(url: str, *, timeout: float):
        return ViewerHeadResult(url=url, ok=not url.endswith("/config"), status=200)

    monkeypatch.setattr("agent_runtime.service_adapters._head_or_get_url", fake_probe)

    status = WorldMirrorServiceAdapter(base_url="http://world.local").runtime_status()

    assert status["ok"] is False
    assert status["index"]["ok"] is True
    assert status["config"]["ok"] is False


def _worldmirror_config() -> dict:
    return {
        "api_prefix": "/gradio_api",
        "version": "5.33.0",
        "protocol": "sse_v3",
        "components": [
            {"id": 7, "type": "file", "props": {"label": "Upload Video or Images"}, "api_info": {"type": "array"}},
            {"id": 8, "type": "slider", "props": {"label": "Video Sample Interval (s)", "value": 1.0}, "api_info": {"type": "number"}},
            {"id": 4, "type": "textbox", "props": {"value": "None"}, "api_info": {"type": "string"}},
            {"id": 40, "type": "dropdown", "props": {"label": "Show Points of a Specific Frame", "value": "All"}, "api_info": {"type": "string"}},
            {"id": 44, "type": "checkbox", "props": {"label": "Show Camera", "value": True}, "api_info": {"type": "boolean"}},
            {"id": 47, "type": "checkbox", "props": {"label": "Filter Sky Background", "value": False}, "api_info": {"type": "boolean"}},
            {"id": 45, "type": "checkbox", "props": {"label": "Show Mesh", "value": True}, "api_info": {"type": "boolean"}},
            {"id": 46, "type": "checkbox", "props": {"label": "Filter low confidence & edges", "value": True}, "api_info": {"type": "boolean"}},
            {"id": 18, "type": "model3d", "props": {"label": "3D Pointmap / Mesh"}, "api_info": {"type": "object"}},
        ],
        "dependencies": [
            {"api_name": "_on_upload", "queue": True, "connection": "sse", "inputs": [7, 8], "outputs": [4]},
            {"api_name": "gradio_demo", "queue": True, "connection": "sse", "inputs": [4, 40, 44, 47, 45, 46], "outputs": [18]},
        ],
    }


def test_worldmirror_generation_contract_extracts_upload_and_reconstruct_endpoints() -> None:
    contract = WorldMirrorServiceAdapter(base_url="http://world.local").generation_contract(
        config_payload=_worldmirror_config()
    )

    assert contract.ok is True
    assert contract.api_prefix == "/gradio_api"
    assert contract.gradio_version == "5.33.0"
    assert contract.upload_endpoint.api_name == "_on_upload"
    assert [item.component_id for item in contract.upload_endpoint.inputs] == [7, 8]
    assert contract.reconstruct_endpoint.api_name == "gradio_demo"
    assert [item.component_id for item in contract.reconstruct_endpoint.inputs] == [4, 40, 44, 47, 45, 46]


def test_worldmirror_generation_call_plan_uses_config_contract_and_local_files(tmp_path: Path) -> None:
    image = tmp_path / "view.png"
    image.write_bytes(b"png")
    adapter = WorldMirrorServiceAdapter(base_url="http://world.local")

    plan = adapter.build_generation_call_plan(
        WorldMirrorGenerationRequest(input_files=[str(image)], show_camera=False),
        config_payload=_worldmirror_config(),
    )

    assert plan.ok is True
    assert plan.submits_long_running_job is False
    assert plan.upload_url == "http://world.local/gradio_api/call/_on_upload"
    assert plan.reconstruct_url == "http://world.local/gradio_api/call/gradio_demo"
    assert plan.upload_payload["data"][0][0]["path"] == str(image.resolve())
    assert plan.upload_payload["data"][0][0]["meta"] == {"_type": "gradio.FileData"}
    assert plan.reconstruct_payload["data"] == [
        "<from _on_upload output[0]>",
        "All",
        False,
        False,
        True,
        True,
    ]


def test_worldmirror_generation_call_plan_accepts_existing_workspace_without_upload() -> None:
    adapter = WorldMirrorServiceAdapter(base_url="http://world.local")

    plan = adapter.build_generation_call_plan(
        WorldMirrorGenerationRequest(workspace_dir="gradio_demo_output/input_images_existing"),
        config_payload=_worldmirror_config(),
    )

    assert plan.ok is True
    assert plan.upload_payload is None
    assert plan.workspace_source == "provided_workspace_dir"
    assert plan.reconstruct_payload["data"][0] == "gradio_demo_output/input_images_existing"


def test_worldmirror_submit_generation_posts_reconstruct_call(monkeypatch) -> None:
    calls = []

    def fake_post_json(url: str, payload: dict, *, timeout: float):
        calls.append((url, payload, timeout))
        return JsonHttpResult(url=url, ok=True, status=200, data={"event_id": "evt_001"})

    monkeypatch.setattr(service_adapter_module, "_post_json", fake_post_json)
    adapter = WorldMirrorServiceAdapter(base_url="http://world.local", timeout=7)

    submission = adapter.submit_generation(
        WorldMirrorGenerationRequest(workspace_dir="gradio_demo_output/input_images_existing"),
        config_payload=_worldmirror_config(),
    )

    assert submission.ok is True
    assert submission.submits_long_running_job is True
    assert submission.reconstruct_submission.event_id == "evt_001"
    assert submission.reconstruct_submission.submits_long_running_job is True
    assert calls == [
        (
            "http://world.local/gradio_api/call/gradio_demo",
            {
                "data": [
                    "gradio_demo_output/input_images_existing",
                    "All",
                    True,
                    False,
                    True,
                    True,
                ]
            },
            7,
        )
    ]


def test_worldmirror_submit_generation_requires_workspace_before_reconstruct(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "view.png"
    image.write_bytes(b"png")

    def fail_post_json(url: str, payload: dict, *, timeout: float):  # pragma: no cover - should not run
        raise AssertionError("submit_generation must not post without a workspace_dir")

    monkeypatch.setattr(service_adapter_module, "_post_json", fail_post_json)
    adapter = WorldMirrorServiceAdapter(base_url="http://world.local")

    submission = adapter.submit_generation(
        WorldMirrorGenerationRequest(input_files=[str(image)]),
        config_payload=_worldmirror_config(),
    )

    assert submission.ok is False
    assert "workspace_dir_required_for_reconstruct_submit" in submission.issues
    assert submission.reconstruct_submission is None


def test_worldmirror_submit_upload_posts_upload_call(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "view.png"
    image.write_bytes(b"png")
    calls = []
    upload_calls = []

    def fake_upload_files(self, input_files: list[str], *, api_prefix: str = "/gradio_api"):
        upload_calls.append((input_files, api_prefix))
        return JsonHttpResult(
            url="http://world.local/gradio_api/upload",
            ok=True,
            status=200,
            data=["/tmp/gradio/uploaded/view.png"],
        )

    def fake_post_json(url: str, payload: dict, *, timeout: float):
        calls.append((url, payload, timeout))
        return JsonHttpResult(url=url, ok=True, status=200, data={"event_id": "upload_evt_001"})

    monkeypatch.setattr(WorldMirrorServiceAdapter, "upload_files", fake_upload_files)
    monkeypatch.setattr(service_adapter_module, "_post_json", fake_post_json)
    adapter = WorldMirrorServiceAdapter(base_url="http://world.local", timeout=6)

    submission = adapter.submit_upload(
        WorldMirrorGenerationRequest(input_files=[str(image)]),
        config_payload=_worldmirror_config(),
    )

    assert submission.ok is True
    assert submission.submits_long_running_job is False
    assert submission.upload_submission.event_id == "upload_evt_001"
    assert upload_calls == [([str(image)], "/gradio_api")]
    assert calls[0][0] == "http://world.local/gradio_api/call/_on_upload"
    assert calls[0][1]["data"][0][0]["path"] == "/tmp/gradio/uploaded/view.png"
    assert calls[0][1]["data"][0][0]["orig_name"] == "view.png"
    assert calls[0][1]["data"][1] == 1.0
    assert calls[0][2] == 6


def test_worldmirror_submit_upload_requires_input_files(monkeypatch) -> None:
    def fail_post_json(url: str, payload: dict, *, timeout: float):  # pragma: no cover - should not run
        raise AssertionError("submit_upload must not post without input_files")

    monkeypatch.setattr(service_adapter_module, "_post_json", fail_post_json)
    adapter = WorldMirrorServiceAdapter(base_url="http://world.local")

    submission = adapter.submit_upload(
        WorldMirrorGenerationRequest(workspace_dir="gradio_demo_output/input_images_existing"),
        config_payload=_worldmirror_config(),
    )

    assert submission.ok is False
    assert "input_files_required_for_upload" in submission.issues
    assert submission.upload_submission is None


def test_worldmirror_poll_queued_call_parses_complete_event(monkeypatch) -> None:
    def fake_get_sse_events(url: str, *, timeout: float):
        assert url == "http://world.local/gradio_api/call/gradio_demo/evt_001"
        assert timeout == 9
        return (
            [
                WorldMirrorSSEEvent(event="generating", data={"msg": "running"}),
                WorldMirrorSSEEvent(event="complete", data=[{"path": "scene.glb"}]),
            ],
            None,
        )

    monkeypatch.setattr(service_adapter_module, "_get_sse_events", fake_get_sse_events)
    adapter = WorldMirrorServiceAdapter(base_url="http://world.local", timeout=9)

    result = adapter.poll_queued_call(api_name="gradio_demo", event_id="evt_001")

    assert result.ok is True
    assert result.complete is True
    assert result.output_data == [{"path": "scene.glb"}]
    assert [event.event for event in result.events] == ["generating", "complete"]


def test_worldmirror_poll_upload_extracts_target_dir(monkeypatch) -> None:
    def fake_get_sse_events(url: str, *, timeout: float):
        assert url == "http://world.local/gradio_api/call/_on_upload/upload_evt_001"
        return (
            [
                WorldMirrorSSEEvent(event="complete", data=["gradio_demo_output/input_images_uploaded", [], "ok", ""]),
            ],
            None,
        )

    monkeypatch.setattr(service_adapter_module, "_get_sse_events", fake_get_sse_events)
    adapter = WorldMirrorServiceAdapter(base_url="http://world.local")

    result = adapter.poll_upload(event_id="upload_evt_001")

    assert result.ok is True
    assert result.target_dir == "gradio_demo_output/input_images_uploaded"
    assert result.poll_result.complete is True


def test_extract_worldmirror_upload_target_dir_supports_gradio_shapes() -> None:
    assert extract_worldmirror_upload_target_dir(["target", [], "ok"]) == "target"
    assert extract_worldmirror_upload_target_dir({"data": ["target", []]}) == "target"
    assert extract_worldmirror_upload_target_dir({"target_dir": "target"}) == "target"
    assert extract_worldmirror_upload_target_dir([]) is None


def test_worldmirror_sse_parser_handles_json_and_plain_text_events() -> None:
    events = service_adapter_module._parse_sse_events(
        "event: generating\n"
        "data: {\"msg\": \"running\"}\n\n"
        "event: complete\n"
        "data: plain text\n\n"
    )

    assert events[0].event == "generating"
    assert events[0].data == {"msg": "running"}
    assert events[1].event == "complete"
    assert events[1].data == "plain text"
