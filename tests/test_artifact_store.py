from pathlib import Path

from agent_runtime.artifacts import FileArtifactStore, sha256_file
from agent_runtime.state import AgentProjectState, ArtifactType, WorkflowPhase


def test_register_file_keeps_state_to_metadata_reference(tmp_path: Path) -> None:
    source = tmp_path / "asset.glb"
    source.write_bytes(b"glb payload")

    store = FileArtifactStore(tmp_path / "store")
    record = store.register_file(
        source,
        ArtifactType.SUBJECT_3D_ASSET,
        semantic_role="subject_asset",
        artifact_id="subject_asset_v001",
    )

    assert record.uri == str(source.resolve())
    assert record.size_bytes == len(b"glb payload")
    assert record.sha256 == sha256_file(source)
    assert record.mime_type == "model/gltf-binary"

    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SUBJECT_ASSET_GENERATION,
        artifacts=[record],
    )
    serialized = state.model_dump_json() if hasattr(state, "model_dump_json") else state.json()
    assert "glb payload" not in serialized
    assert "subject_asset_v001" in state.artifact_ids()

    loaded = store.load_records()
    assert loaded == [record]


def test_register_file_can_copy_into_store(tmp_path: Path) -> None:
    source = tmp_path / "preview.png"
    source.write_bytes(b"png payload")

    store = FileArtifactStore(tmp_path / "store")
    record = store.register_file(
        source,
        ArtifactType.BLENDER_PREVIEW_RENDER,
        artifact_id="preview_v001",
        copy_into_store=True,
    )

    copied = Path(record.uri)
    assert copied.exists()
    assert copied != source.resolve()
    assert copied.read_bytes() == b"png payload"
