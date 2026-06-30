import json
import zipfile
from pathlib import Path

from agent_runtime.artifacts import FileArtifactStore
from agent_runtime.delivery_package import build_delivery_package
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    BlenderSceneState,
    ViewerSceneState,
    WorkflowPhase,
)


def _artifact(tmp_path: Path, artifact_id: str, artifact_type: ArtifactType, suffix: str, payload: bytes) -> ArtifactRecord:
    path = tmp_path / f"{artifact_id}{suffix}"
    path.write_bytes(payload)
    return ArtifactRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        uri=str(path),
        mime_type="application/octet-stream",
        semantic_role=artifact_id,
        size_bytes=len(payload),
    )


def _complete_state(tmp_path: Path) -> AgentProjectState:
    blend = _artifact(tmp_path, "blend_file", ArtifactType.BLENDER_FILE, ".blend", b"blend")
    preview = _artifact(tmp_path, "preview_png", ArtifactType.BLENDER_PREVIEW_RENDER, ".png", b"png")
    viewer_glb = _artifact(tmp_path, "viewer_glb", ArtifactType.VIEWER_SCENE_GLB, ".glb", b"viewer")
    viewer_state = _artifact(tmp_path, "viewer_state", ArtifactType.VIEWER_SCENE_STATE_JSON, ".json", b"{}")
    subject = _artifact(tmp_path, "subject_glb", ArtifactType.SUBJECT_3D_ASSET, ".glb", b"subject")
    scene = _artifact(tmp_path, "scene_glb", ArtifactType.SCENE_3D_ASSET, ".glb", b"scene")
    viewer_glb.metadata["viewer"] = {
        "base_url": "http://viewer.local",
        "asset_url": "http://viewer.local/asset?path=viewer.glb",
        "viewer_url": "http://viewer.local/viewer?path=viewer.glb",
        "runtime_status": {"ok": True},
        "model_check": {"ok": True},
    }
    return AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_scene",
            blend_file_artifact_id="blend_file",
            preview_image_id="preview_png",
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_artifact_id="viewer_glb",
            viewer_state_artifact_id="viewer_state",
        ),
        artifacts=[blend, preview, viewer_glb, viewer_state, subject, scene],
    )


def test_build_delivery_package_writes_manifest_zip_and_registers_artifact(tmp_path: Path) -> None:
    state = _complete_state(tmp_path)
    store = FileArtifactStore(tmp_path / "artifact_store")

    result, updated_state = build_delivery_package(
        state=state,
        output_dir=tmp_path / "delivery",
        artifact_store=store,
        package_id="delivery_project_001",
    )

    assert result.ok is True
    assert result.issues == []
    assert result.package_artifact_id == "delivery_project_001"
    assert Path(result.package_zip).is_file()
    assert Path(result.metadata_json).is_file()
    assert Path(result.version_manifest_json).is_file()
    assert len(result.items) == 6
    assert updated_state.phase == WorkflowPhase.DELIVERY
    assert updated_state.artifacts[-1].artifact_type == ArtifactType.EXPORT_PACKAGE
    assert len(store.load_records()) == 1

    metadata = json.loads(Path(result.metadata_json).read_text(encoding="utf-8"))
    manifest = json.loads(Path(result.version_manifest_json).read_text(encoding="utf-8"))
    assert metadata["checks"]["has_blend_file"] is True
    assert metadata["delivery_handoff"]["ready"] is True
    assert manifest["source_state"]["project_id"] == "project_001"
    assert {item["artifact_id"] for item in manifest["items"]} == {
        "blend_file",
        "preview_png",
        "viewer_glb",
        "viewer_state",
        "subject_glb",
        "scene_glb",
    }
    with zipfile.ZipFile(result.package_zip) as archive:
        names = set(archive.namelist())
    assert "metadata.json" in names
    assert "version_manifest.json" in names
    assert "files/viewer_scene/viewer_glb.glb" in names
    assert "files/viewer_state/viewer_state.json" in names


def test_build_delivery_package_reports_missing_required_artifacts(tmp_path: Path) -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
    )

    result, updated_state = build_delivery_package(
        state=state,
        output_dir=tmp_path / "delivery",
        package_id="delivery_incomplete",
    )

    assert result.ok is False
    assert result.package_artifact_id is None
    assert set(result.issues) == {
        "missing_blend_file",
        "missing_preview_render",
        "missing_viewer_scene",
        "missing_viewer_state",
        "missing_subject_assets",
        "missing_scene_assets",
    }
    assert Path(result.package_zip).is_file()
    assert updated_state.phase == WorkflowPhase.BLENDER_PREVIEW
