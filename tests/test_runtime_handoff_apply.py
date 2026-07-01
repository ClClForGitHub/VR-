import json
from pathlib import Path

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.runtime_handoff_apply import apply_blender_assembly_result
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    AssemblySelection,
    AssetLibraryItem,
    CameraSpec,
    EnvironmentSpec,
    LightingSpec,
    Scene3DRecord,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_blender_handoff_apply_records_selected_sources_in_asset_library(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_blender_asset_library"
    run_dir.mkdir(parents=True)
    blend = tmp_path / "scene.blend"
    viewer_glb = tmp_path / "viewer_scene.glb"
    scene_state = tmp_path / "scene_state.json"
    preview = tmp_path / "preview.png"
    blend.write_bytes(b"blend")
    viewer_glb.write_bytes(b"viewer")
    scene_state.write_text(json.dumps({"viewer_scene_id": "viewer_001", "objects": []}), encoding="utf-8")
    preview.write_bytes(b"preview")
    now = utc_now_iso()
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=_scene_spec(),
        scene_asset=Scene3DRecord(
            scene_asset_id="scene_record_001",
            service="hy_world",
            raw_output_type="mesh",
            adapted_artifact_ids=["scene_asset_v1"],
            blender_import_mode="mesh_import",
            status="adapted",
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="subject_model_v2",
                artifact_type=ArtifactType.SUBJECT_3D_ASSET,
                uri=str(tmp_path / "subject.glb"),
                mime_type="model/gltf-binary",
                linked_subject_id="subject_robot",
            ),
            ArtifactRecord(
                artifact_id="scene_asset_v1",
                artifact_type=ArtifactType.SCENE_3D_ASSET,
                uri=str(tmp_path / "scene.glb"),
                mime_type="model/gltf-binary",
                linked_scene_id="scene_001",
            ),
        ],
        asset_library=[
            _library_item("subject_model_v2", "subject_model", now, subject_id="subject_robot"),
            _library_item("scene_asset_v1", "scene_asset", now, scene_id="scene_001"),
        ],
        active_assembly_selection=AssemblySelection(
            selection_id="assembly_selection_test",
            selected_subject_assets={"subject_robot": "subject_model_v2"},
            selected_scene_asset_id="scene_asset_v1",
            updated_at=now,
        ),
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")

    result = apply_blender_assembly_result(
        run_dir,
        blender_results=[
            {
                "blend_path": str(blend),
                "viewer_scene_path": str(viewer_glb),
                "scene_state_json_path": str(scene_state),
                "preview_image_path": str(preview),
                "blender_scene_id": "blender_001",
                "viewer_scene_id": "viewer_001",
            }
        ],
    )
    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    new_items = [
        item
        for item in payload["asset_library"]
        if item["asset_kind"] in {"blender_scene", "viewer_scene", "target_render"}
    ]

    assert result.ok is True
    assert set(result.record.applied_fields) == {"artifacts", "blender_scene", "viewer_scene", "asset_library", "phase"}
    assert {item["asset_kind"] for item in new_items} == {"blender_scene", "viewer_scene", "target_render"}
    assert all(
        item["source_artifact_ids"] == ["subject_model_v2", "scene_asset_v1"]
        for item in new_items
    )


def _library_item(
    artifact_id: str,
    asset_kind: str,
    now: str,
    *,
    subject_id: str | None = None,
    scene_id: str | None = None,
) -> AssetLibraryItem:
    return AssetLibraryItem(
        library_item_id=f"library_{artifact_id}",
        artifact_id=artifact_id,
        asset_kind=asset_kind,
        subject_id=subject_id,
        scene_id=scene_id,
        created_at=now,
        updated_at=now,
    )


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
