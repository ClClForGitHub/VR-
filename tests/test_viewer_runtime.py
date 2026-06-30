from pathlib import Path

import pytest

from agent_runtime.state import ArtifactRecord, ArtifactType
from agent_runtime.viewer import ViewerHeadResult
from agent_runtime.viewer_runtime import (
    ViewerRuntimeAdapter,
    annotate_state_artifact_with_viewer,
)


def test_viewer_runtime_status_checks_index_and_api_list(monkeypatch) -> None:
    calls = []

    def fake_head_url(url: str, timeout: float):
        calls.append((url, timeout))
        return ViewerHeadResult(
            url=url,
            ok=True,
            status=200,
            content_type="application/json" if "api/list" in url else "text/html",
        )

    monkeypatch.setattr("agent_runtime.viewer_runtime.head_url", fake_head_url)

    status = ViewerRuntimeAdapter(base_url="http://viewer.local/", timeout=3).runtime_status()

    assert status["ok"] is True
    assert status["base_url"] == "http://viewer.local"
    assert calls == [
        ("http://viewer.local/", 3),
        ("http://viewer.local/api/list?limit=1", 3),
    ]
    assert status["index"]["content_type"] == "text/html"
    assert status["api_list"]["content_type"] == "application/json"


def test_viewer_runtime_status_reports_failure(monkeypatch) -> None:
    def fake_head_url(url: str, timeout: float):
        return ViewerHeadResult(url=url, ok="api/list" not in url, status=200)

    monkeypatch.setattr("agent_runtime.viewer_runtime.head_url", fake_head_url)

    status = ViewerRuntimeAdapter(base_url="http://viewer.local").runtime_status()

    assert status["ok"] is False
    assert status["index"]["ok"] is True
    assert status["api_list"]["ok"] is False


def test_viewer_artifact_metadata_contains_asset_and_viewer_urls(tmp_path: Path) -> None:
    model = tmp_path / "viewer scene.glb"
    model.write_bytes(b"placeholder")

    metadata = ViewerRuntimeAdapter(base_url="http://viewer.local").artifact_metadata(model)

    assert metadata["base_url"] == "http://viewer.local"
    assert metadata["model_path"] == str(model.resolve())
    assert metadata["asset_url"].startswith("http://viewer.local/asset?path=")
    assert metadata["viewer_url"].startswith("http://viewer.local/viewer?path=")
    assert "%20" in metadata["asset_url"]


def test_annotate_artifact_adds_viewer_metadata(tmp_path: Path) -> None:
    model = tmp_path / "scene.glb"
    model.write_bytes(b"placeholder")
    artifact = ArtifactRecord(
        artifact_id="viewer_glb",
        artifact_type=ArtifactType.VIEWER_SCENE_GLB,
        uri=str(model),
        mime_type="model/gltf-binary",
        metadata={"stage": "viewer_export"},
    )
    adapter = ViewerRuntimeAdapter(base_url="http://viewer.local")

    annotated = adapter.annotate_artifact(
        artifact,
        runtime_status={"ok": True},
        model_check={"ok": True},
    )

    assert artifact.metadata == {"stage": "viewer_export"}
    assert annotated.metadata["stage"] == "viewer_export"
    assert annotated.metadata["viewer"]["runtime_status"] == {"ok": True}
    assert annotated.metadata["viewer"]["model_check"] == {"ok": True}
    assert annotated.metadata["viewer"]["viewer_url"].startswith("http://viewer.local/viewer")


def test_annotate_artifact_rejects_non_viewer_artifact(tmp_path: Path) -> None:
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"placeholder")
    artifact = ArtifactRecord(
        artifact_id="blend",
        artifact_type=ArtifactType.BLENDER_FILE,
        uri=str(blend),
        mime_type="application/x-blender",
    )

    with pytest.raises(ValueError, match="not a viewer model artifact"):
        ViewerRuntimeAdapter().annotate_artifact(artifact)


def test_annotate_state_artifact_with_viewer_updates_matching_record(tmp_path: Path) -> None:
    model = tmp_path / "scene.glb"
    model.write_bytes(b"placeholder")
    artifacts = [
        ArtifactRecord(
            artifact_id="input",
            artifact_type=ArtifactType.SCENE_3D_ASSET,
            uri="/tmp/input.glb",
            mime_type="model/gltf-binary",
        ),
        ArtifactRecord(
            artifact_id="viewer_glb",
            artifact_type=ArtifactType.VIEWER_SCENE_GLB,
            uri=str(model),
            mime_type="model/gltf-binary",
        ),
    ]

    updated = annotate_state_artifact_with_viewer(
        artifacts,
        artifact_id="viewer_glb",
        adapter=ViewerRuntimeAdapter(base_url="http://viewer.local"),
    )

    assert updated[0] is artifacts[0]
    assert updated[1].metadata["viewer"]["asset_url"].startswith("http://viewer.local/asset")

    with pytest.raises(KeyError, match="artifact not found"):
        annotate_state_artifact_with_viewer(
            artifacts,
            artifact_id="missing",
            adapter=ViewerRuntimeAdapter(),
        )
