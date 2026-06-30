from pathlib import Path

from agent_runtime.artifacts import FileArtifactStore
from agent_runtime.scene_assets import inspect_worldmirror_output, register_worldmirror_output
from agent_runtime.state import AgentProjectState, WorkflowPhase


def _worldmirror_output(root: Path) -> Path:
    output = root / "input_images_001"
    (output / "images").mkdir(parents=True)
    (output / "scene_0_image_camTrue_meshTrue_edgesTrue_skyFalse.glb").write_bytes(b"secondary")
    (output / "scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb").write_bytes(b"primary")
    (output / "camera_params.json").write_text("{}", encoding="utf-8")
    (output / "gaussians.ply").write_text("ply", encoding="utf-8")
    (output / "predictions.npz").write_bytes(b"npz")
    (output / "images/image_0001.jpg").write_bytes(b"jpg")
    return output


def test_inspect_worldmirror_output_prefers_scene_all_glb(tmp_path: Path) -> None:
    output = _worldmirror_output(tmp_path)

    summary = inspect_worldmirror_output(output)

    assert summary.status == "adapted"
    assert summary.raw_output_type == "mesh"
    assert summary.blender_import_mode == "mesh_import"
    assert summary.primary_scene_glb == str((output / "scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb").resolve())
    assert len(summary.scene_glb_candidates) == 2
    assert summary.image_count == 1
    assert summary.issues == []


def test_inspect_worldmirror_output_accepts_gaussian_only_with_warning(tmp_path: Path) -> None:
    output = tmp_path / "world"
    output.mkdir()
    (output / "gaussians.ply").write_text("ply", encoding="utf-8")

    summary = inspect_worldmirror_output(output)

    assert summary.status == "accepted_with_warning"
    assert summary.raw_output_type == "3dgs"
    assert summary.blender_import_mode == "3dgs_layer"
    assert summary.issues == ["no_scene_glb_using_gaussian_reference"]


def test_register_worldmirror_output_updates_scene_asset_and_artifacts(tmp_path: Path) -> None:
    output = _worldmirror_output(tmp_path)
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SCENE_ASSET_GENERATION,
    )
    store = FileArtifactStore(tmp_path / "artifacts")

    summary, state = register_worldmirror_output(
        state=state,
        artifact_store=store,
        output_dir=output,
        scene_asset_id="scene_asset_001",
        source_scene_concept_image_ids=["scene_concept_001"],
        source_prompt="small room",
    )

    assert summary.status == "adapted"
    assert state.scene_asset is not None
    assert state.scene_asset.scene_asset_id == "scene_asset_001"
    assert state.scene_asset.raw_output_type == "mesh"
    assert state.scene_asset.blender_import_mode == "mesh_import"
    assert state.scene_asset.status == "adapted"
    assert state.scene_asset.adapted_artifact_ids == ["scene_asset_001_scene_glb"]
    assert "scene_asset_001_camera_params_json" in state.scene_asset.raw_artifact_ids
    assert len(state.artifacts) == 4
    assert state.artifacts[0].artifact_type.value == "SCENE_3D_ASSET"
    assert state.artifacts[0].metadata["output_dir"] == str(output.resolve())
    assert len(store.load_records()) == 4
