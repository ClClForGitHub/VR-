import importlib.util
import json
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.runtime_console import create_runtime_console_run
from agent_runtime.runtime_runs import PublicUrlConfig
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    AssetLibraryItem,
    CameraSpec,
    ConceptBundle,
    EnvironmentSpec,
    LightingSpec,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "runtime_console_server.py"
SPEC = importlib.util.spec_from_file_location("runtime_console_server_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime_console_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_console_server)

RuntimeConsoleHandler = runtime_console_server.RuntimeConsoleHandler
_runtime_event_signature = runtime_console_server._runtime_event_signature


def test_runtime_event_signature_tracks_core_file_changes(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_events"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text('{"phase":"INTAKE"}', encoding="utf-8")
    before = _runtime_event_signature(run_dir, run_dir)

    (run_dir / "frontend_status.json").write_text('{"phase":"BLENDER_PREVIEW"}', encoding="utf-8")
    after = _runtime_event_signature(run_dir, run_dir)

    assert before["fingerprint"] != after["fingerprint"]
    assert after["file_count"] >= before["file_count"]


def test_runtime_console_events_endpoint_streams_ready_event(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_events")
    server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeConsoleHandler)
    server.root = tmp_path
    server.static_root = tmp_path
    server.public_urls = PublicUrlConfig()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run_key = urllib.parse.quote(created.run_id, safe="")
        url = f"http://127.0.0.1:{server.server_port}/api/runs/{run_key}/events?max_seconds=0.2&interval=0.2"
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "text/event-stream" in content_type
    assert "event: ready" in body
    assert '"ok": true' in body


def test_runtime_console_asset_action_endpoint_applies_frontend_selection(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_asset_action")
    run_dir = Path(created.run_dir)
    concept_path = tmp_path / "concept_a.png"
    concept_path.write_bytes(b"concept")
    now = utc_now_iso()
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            subject_concept_images={"subject_robot": ["concept_a"]},
            approved=True,
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="concept_a",
                artifact_type=ArtifactType.SUBJECT_CONCEPT_IMAGE,
                uri=str(concept_path),
                mime_type="image/png",
                semantic_role="subject_concept_image",
                linked_subject_id="subject_robot",
            )
        ],
        asset_library=[
            AssetLibraryItem(
                library_item_id="library_concept_a",
                artifact_id="concept_a",
                asset_kind="subject_concept",
                subject_id="subject_robot",
                review_status="rejected",
                created_at=now,
                updated_at=now,
            )
        ],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeConsoleHandler)
    server.root = tmp_path
    server.static_root = tmp_path
    server.public_urls = PublicUrlConfig()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run_key = urllib.parse.quote(created.run_id, safe="")
        url = f"http://127.0.0.1:{server.server_port}/api/runs/{run_key}/asset-action"
        body = json.dumps(
            {
                "action_type": "select_concept_for_subject_generation",
                "subject_id": "subject_robot",
                "concept_artifact_id": "concept_a",
                "note": "front-end selection",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    action_summary = json.loads((run_dir / "runtime_asset_action_summary.json").read_text(encoding="utf-8"))

    assert payload["ok"] is True
    assert state_payload["asset_library"][0]["selection_status"] == "selected_for_model_generation"
    assert state_payload["asset_library"][0]["review_status"] == "rejected"
    assert action_summary["latest_record"]["action_type"] == "select_concept_for_subject_generation"


def _scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_001",
        title="Robot Display",
        user_goal="Create a robot display.",
        style=StyleSpec(style_keywords=["clean"]),
        environment=EnvironmentSpec(environment_type="studio", description="Small studio."),
        lighting=LightingSpec(description="Soft light."),
        camera=CameraSpec(shot_type="three quarter"),
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Robot",
                category="character",
                description="A compact robot.",
            )
        ],
    )
