"""Scene asset adaptation helpers for existing WorldMirror/HY-World outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.artifacts import FileArtifactStore
from agent_runtime.state import AgentProjectState, ArtifactType, Scene3DRecord
from agent_runtime.state_views import apply_state_updates


SceneAdapterStatus = Literal["adapted", "accepted_with_warning", "failed"]


class WorldMirrorOutputSummary(BaseModel):
    output_dir: str
    status: SceneAdapterStatus
    primary_scene_glb: str | None = None
    scene_glb_candidates: list[str] = Field(default_factory=list)
    camera_params_json: str | None = None
    gaussian_ply: str | None = None
    gaussian_kiri_ply: str | None = None
    predictions_npz: str | None = None
    image_count: int = 0
    raw_output_type: str
    blender_import_mode: str
    issues: list[str] = Field(default_factory=list)


def inspect_worldmirror_output(output_dir: str | Path) -> WorldMirrorOutputSummary:
    output_path = Path(output_dir).expanduser().resolve()
    issues: list[str] = []
    if not output_path.exists():
        return WorldMirrorOutputSummary(
            output_dir=str(output_path),
            status="failed",
            raw_output_type="unknown",
            blender_import_mode="visual_reference_only",
            issues=["missing_output_dir"],
        )
    if not output_path.is_dir():
        return WorldMirrorOutputSummary(
            output_dir=str(output_path),
            status="failed",
            raw_output_type="unknown",
            blender_import_mode="visual_reference_only",
            issues=["output_path_not_directory"],
        )

    scene_glbs = sorted(output_path.glob("*.glb"))
    primary_scene_glb = _select_primary_scene_glb(scene_glbs)
    camera_params = _optional_file(output_path / "camera_params.json")
    gaussian_ply = _optional_file(output_path / "gaussians.ply")
    gaussian_kiri_ply = _optional_file(output_path / "gaussians_kiri.ply")
    predictions_npz = _optional_file(output_path / "predictions.npz")
    image_count = _count_input_images(output_path / "images")

    raw_output_type = "unknown"
    blender_import_mode = "visual_reference_only"
    status: SceneAdapterStatus = "failed"
    if primary_scene_glb is not None:
        raw_output_type = "mesh"
        blender_import_mode = "mesh_import"
        status = "adapted"
    elif gaussian_ply is not None or gaussian_kiri_ply is not None:
        raw_output_type = "3dgs"
        blender_import_mode = "3dgs_layer"
        status = "accepted_with_warning"
        issues.append("no_scene_glb_using_gaussian_reference")
    elif camera_params is not None or predictions_npz is not None or image_count:
        raw_output_type = "depth_camera_normals"
        blender_import_mode = "depth_camera_scaffold"
        status = "accepted_with_warning"
        issues.append("no_scene_glb_using_depth_camera_reference")
    else:
        issues.append("no_supported_worldmirror_outputs")

    return WorldMirrorOutputSummary(
        output_dir=str(output_path),
        status=status,
        primary_scene_glb=str(primary_scene_glb) if primary_scene_glb is not None else None,
        scene_glb_candidates=[str(path) for path in scene_glbs],
        camera_params_json=str(camera_params) if camera_params is not None else None,
        gaussian_ply=str(gaussian_ply) if gaussian_ply is not None else None,
        gaussian_kiri_ply=str(gaussian_kiri_ply) if gaussian_kiri_ply is not None else None,
        predictions_npz=str(predictions_npz) if predictions_npz is not None else None,
        image_count=image_count,
        raw_output_type=raw_output_type,
        blender_import_mode=blender_import_mode,
        issues=issues,
    )


def register_worldmirror_output(
    *,
    state: AgentProjectState,
    artifact_store: FileArtifactStore,
    output_dir: str | Path,
    scene_asset_id: str,
    source_scene_concept_image_ids: list[str] | None = None,
    source_prompt: str | None = None,
) -> tuple[WorldMirrorOutputSummary, AgentProjectState]:
    summary = inspect_worldmirror_output(output_dir)
    artifact_ids: list[str] = []
    adapted_artifact_ids: list[str] = []

    for role, path_value in _artifact_paths(summary).items():
        if path_value is None:
            continue
        artifact_id = f"{scene_asset_id}_{role}"
        artifact = artifact_store.register_file(
            path_value,
            ArtifactType.SCENE_3D_ASSET,
            artifact_id=artifact_id,
            semantic_role=f"worldmirror_{role}",
            metadata={
                "stage": "scene_asset_adaptation",
                "scene_asset_id": scene_asset_id,
                "service": "hy_world",
                "output_dir": summary.output_dir,
                "raw_output_type": summary.raw_output_type,
                "blender_import_mode": summary.blender_import_mode,
            },
        )
        state.artifacts.append(artifact)
        artifact_ids.append(artifact.artifact_id)
        if role == "scene_glb":
            adapted_artifact_ids.append(artifact.artifact_id)

    scene_asset = Scene3DRecord(
        scene_asset_id=scene_asset_id,
        source_scene_concept_image_ids=source_scene_concept_image_ids or [],
        source_prompt=source_prompt,
        service="hy_world",
        raw_output_type=summary.raw_output_type,
        raw_artifact_ids=artifact_ids,
        adapted_artifact_ids=adapted_artifact_ids,
        blender_import_mode=summary.blender_import_mode,
        status=summary.status,
        adapter_notes="; ".join(summary.issues) if summary.issues else "worldmirror output adapted",
        generation_params={
            "output_dir": summary.output_dir,
            "image_count": summary.image_count,
            "scene_glb_candidate_count": len(summary.scene_glb_candidates),
            "primary_scene_glb": summary.primary_scene_glb,
        },
    )
    state = apply_state_updates(
        state,
        node_name="SceneAssetAdapter",
        updates={"scene_asset": scene_asset},
    )
    return summary, state


def _select_primary_scene_glb(scene_glbs: list[Path]) -> Path | None:
    for path in scene_glbs:
        if path.name.startswith("scene_All"):
            return path
    return scene_glbs[0] if scene_glbs else None


def _optional_file(path: Path) -> Path | None:
    return path if path.is_file() else None


def _count_input_images(images_dir: Path) -> int:
    if not images_dir.is_dir():
        return 0
    return sum(1 for path in images_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})


def _artifact_paths(summary: WorldMirrorOutputSummary) -> dict[str, str | None]:
    return {
        "scene_glb": summary.primary_scene_glb,
        "camera_params_json": summary.camera_params_json,
        "gaussian_ply": summary.gaussian_ply,
        "gaussian_kiri_ply": summary.gaussian_kiri_ply,
        "predictions_npz": summary.predictions_npz,
    }
