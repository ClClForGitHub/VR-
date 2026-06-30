import importlib.util
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent_runtime.runtime_console import create_runtime_console_run
from agent_runtime.runtime_runs import PublicUrlConfig


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
