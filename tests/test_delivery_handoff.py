from pathlib import Path

from agent_runtime.delivery_handoff import build_delivery_handoff
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    BlenderSceneState,
    ViewerSceneObjectRecord,
    ViewerSceneState,
    WorkflowPhase,
)


def test_delivery_handoff_uses_viewer_artifact_metadata(tmp_path: Path) -> None:
    viewer_glb = tmp_path / "viewer_scene.glb"
    viewer_state = tmp_path / "scene_state.json"
    viewer_glb.write_bytes(b"placeholder")
    viewer_state.write_text("{}", encoding="utf-8")
    artifacts = _required_delivery_artifacts(tmp_path)
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_001",
            blend_file_artifact_id="blend_file",
            preview_image_id="preview_png",
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_artifact_id="viewer_glb",
            viewer_state_artifact_id="viewer_state",
            objects=[ViewerSceneObjectRecord(viewer_object_id="object_001")],
        ),
        artifacts=[
            *artifacts,
            ArtifactRecord(
                artifact_id="viewer_glb",
                artifact_type=ArtifactType.VIEWER_SCENE_GLB,
                uri=str(viewer_glb),
                mime_type="model/gltf-binary",
                metadata={
                    "viewer": {
                        "base_url": "http://viewer.local",
                        "asset_url": "http://viewer.local/asset?path=viewer_scene.glb",
                        "viewer_url": "http://viewer.local/viewer?path=viewer_scene.glb",
                        "runtime_status": {"ok": True},
                        "model_check": {"ok": True},
                    }
                },
            ),
            ArtifactRecord(
                artifact_id="viewer_state",
                artifact_type=ArtifactType.VIEWER_SCENE_STATE_JSON,
                uri=str(viewer_state),
                mime_type="application/json",
            ),
        ],
    )

    handoff = build_delivery_handoff(state)

    assert handoff.ready is True
    assert handoff.verified is True
    assert handoff.issues == []
    assert handoff.viewer_scene_id == "viewer_scene"
    assert handoff.viewer_scene_object_count == 1
    assert handoff.viewer_scene_artifact_id == "viewer_glb"
    assert handoff.viewer_state_artifact_id == "viewer_state"
    assert handoff.viewer_base_url == "http://viewer.local"
    assert handoff.asset_url.startswith("http://viewer.local/asset")
    assert handoff.viewer_url.startswith("http://viewer.local/viewer")
    assert handoff.blend_file_artifact_id == "blend_file"
    assert handoff.preview_image_id == "preview_png"
    assert handoff.subject_asset_count == 1
    assert handoff.scene_asset_count == 1


def test_delivery_handoff_reports_missing_viewer_scene() -> None:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
    )

    handoff = build_delivery_handoff(state)

    assert handoff.ready is False
    assert handoff.verified is False
    assert handoff.issues == [
        "missing_viewer_scene",
        "missing_blend_file",
        "missing_preview_render",
        "missing_viewer_state",
        "missing_subject_assets",
        "missing_scene_assets",
    ]


def test_delivery_handoff_builds_urls_from_flat_viewer_base_metadata(tmp_path: Path) -> None:
    viewer_glb = tmp_path / "viewer_scene.glb"
    viewer_state = tmp_path / "scene_state.json"
    viewer_glb.write_bytes(b"placeholder")
    viewer_state.write_text("{}", encoding="utf-8")
    artifacts = _required_delivery_artifacts(tmp_path)
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_001",
            blend_file_artifact_id="blend_file",
            preview_image_id="preview_png",
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_artifact_id="viewer_glb",
            viewer_state_artifact_id="viewer_state",
            objects=[ViewerSceneObjectRecord(viewer_object_id="object_001")],
        ),
        artifacts=[
            *artifacts,
            ArtifactRecord(
                artifact_id="viewer_glb",
                artifact_type=ArtifactType.VIEWER_SCENE_GLB,
                uri=str(viewer_glb),
                mime_type="model/gltf-binary",
                metadata={"viewer_base_url": "http://viewer.local"},
            ),
            ArtifactRecord(
                artifact_id="viewer_state",
                artifact_type=ArtifactType.VIEWER_SCENE_STATE_JSON,
                uri=str(viewer_state),
                mime_type="application/json",
            ),
        ],
    )

    handoff = build_delivery_handoff(state)

    assert handoff.ready is True
    assert handoff.verified is False
    assert handoff.issues == []
    assert handoff.viewer_base_url == "http://viewer.local"
    assert handoff.asset_url.startswith("http://viewer.local/asset")
    assert handoff.viewer_url.startswith("http://viewer.local/viewer")


def test_delivery_handoff_reports_missing_subject_and_scene_assets(tmp_path: Path) -> None:
    viewer_glb = tmp_path / "viewer_scene.glb"
    viewer_state = tmp_path / "scene_state.json"
    blend = tmp_path / "scene.blend"
    preview = tmp_path / "preview.png"
    viewer_glb.write_bytes(b"placeholder")
    viewer_state.write_text("{}", encoding="utf-8")
    blend.write_bytes(b"blend")
    preview.write_bytes(b"png")
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_PREVIEW,
        blender_scene=BlenderSceneState(
            blender_scene_id="blend_001",
            blend_file_artifact_id="blend_file",
            preview_image_id="preview_png",
        ),
        viewer_scene=ViewerSceneState(
            viewer_scene_id="viewer_scene",
            viewer_scene_artifact_id="viewer_glb",
            viewer_state_artifact_id="viewer_state",
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="blend_file",
                artifact_type=ArtifactType.BLENDER_FILE,
                uri=str(blend),
                mime_type="application/x-blender",
            ),
            ArtifactRecord(
                artifact_id="preview_png",
                artifact_type=ArtifactType.BLENDER_PREVIEW_RENDER,
                uri=str(preview),
                mime_type="image/png",
            ),
            ArtifactRecord(
                artifact_id="viewer_glb",
                artifact_type=ArtifactType.VIEWER_SCENE_GLB,
                uri=str(viewer_glb),
                mime_type="model/gltf-binary",
                metadata={
                    "viewer": {
                        "base_url": "http://viewer.local",
                        "asset_url": "http://viewer.local/asset?path=viewer_scene.glb",
                        "viewer_url": "http://viewer.local/viewer?path=viewer_scene.glb",
                        "runtime_status": {"ok": True},
                        "model_check": {"ok": True},
                    }
                },
            ),
            ArtifactRecord(
                artifact_id="viewer_state",
                artifact_type=ArtifactType.VIEWER_SCENE_STATE_JSON,
                uri=str(viewer_state),
                mime_type="application/json",
            ),
        ],
    )

    handoff = build_delivery_handoff(state)

    assert handoff.ready is False
    assert handoff.verified is False
    assert handoff.issues == ["missing_subject_assets", "missing_scene_assets"]


def _required_delivery_artifacts(tmp_path: Path) -> list[ArtifactRecord]:
    blend = tmp_path / "scene.blend"
    preview = tmp_path / "preview.png"
    subject = tmp_path / "subject.glb"
    scene = tmp_path / "scene_asset.glb"
    blend.write_bytes(b"blend")
    preview.write_bytes(b"png")
    subject.write_bytes(b"subject")
    scene.write_bytes(b"scene")
    return [
        ArtifactRecord(
            artifact_id="blend_file",
            artifact_type=ArtifactType.BLENDER_FILE,
            uri=str(blend),
            mime_type="application/x-blender",
        ),
        ArtifactRecord(
            artifact_id="preview_png",
            artifact_type=ArtifactType.BLENDER_PREVIEW_RENDER,
            uri=str(preview),
            mime_type="image/png",
        ),
        ArtifactRecord(
            artifact_id="subject_asset",
            artifact_type=ArtifactType.SUBJECT_3D_ASSET,
            uri=str(subject),
            mime_type="model/gltf-binary",
        ),
        ArtifactRecord(
            artifact_id="scene_asset",
            artifact_type=ArtifactType.SCENE_3D_ASSET,
            uri=str(scene),
            mime_type="model/gltf-binary",
        ),
    ]
