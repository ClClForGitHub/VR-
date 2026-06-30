"""Delivery/front-end handoff summaries derived from AgentProjectState.

This module consumes existing viewer scene state and viewer artifact metadata.
It does not start a viewer service or invent another scene format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent_runtime.viewer import build_viewer_urls
from agent_runtime.state import AgentProjectState, ArtifactRecord, ArtifactType


VIEWER_MODEL_TYPES = {ArtifactType.VIEWER_SCENE_GLB, ArtifactType.VIEWER_SCENE_GLTF}


class DeliveryHandoff(BaseModel):
    project_id: str
    phase: str
    ready: bool
    verified: bool
    issues: list[str] = Field(default_factory=list)
    viewer_scene_id: str | None = None
    viewer_scene_object_count: int | None = None
    viewer_scene_artifact_id: str | None = None
    viewer_state_artifact_id: str | None = None
    viewer_scene_path: str | None = None
    viewer_state_path: str | None = None
    viewer_base_url: str | None = None
    asset_url: str | None = None
    viewer_url: str | None = None
    viewer_runtime_ok: bool | None = None
    viewer_model_ok: bool | None = None
    blend_file_artifact_id: str | None = None
    preview_image_id: str | None = None
    subject_asset_count: int = 0
    scene_asset_count: int = 0
    artifact_ids: list[str] = Field(default_factory=list)


def build_delivery_handoff(state: AgentProjectState) -> DeliveryHandoff:
    issues: list[str] = []
    viewer_scene = state.viewer_scene
    blender_scene = state.blender_scene
    artifact_ids = sorted(state.artifact_ids())
    blend_artifact = (
        _artifact_by_id(state.artifacts, blender_scene.blend_file_artifact_id)
        if blender_scene is not None and blender_scene.blend_file_artifact_id
        else None
    )
    if blend_artifact is None:
        blend_artifact = _first_artifact_of_type(state.artifacts, ArtifactType.BLENDER_FILE)
    preview_artifact = (
        _artifact_by_id(state.artifacts, blender_scene.preview_image_id)
        if blender_scene is not None and blender_scene.preview_image_id
        else None
    )
    if preview_artifact is None:
        preview_artifact = _first_artifact_of_type(state.artifacts, ArtifactType.BLENDER_PREVIEW_RENDER)
    viewer_model_artifact = (
        _artifact_by_id(state.artifacts, viewer_scene.viewer_scene_artifact_id)
        if viewer_scene is not None and viewer_scene.viewer_scene_artifact_id
        else None
    )
    if viewer_model_artifact is None:
        viewer_model_artifact = _first_viewer_model_artifact(state.artifacts)
    viewer_state_artifact = (
        _artifact_by_id(state.artifacts, viewer_scene.viewer_state_artifact_id)
        if viewer_scene is not None and viewer_scene.viewer_state_artifact_id
        else None
    )
    if viewer_state_artifact is None:
        viewer_state_artifact = _first_artifact_of_type(state.artifacts, ArtifactType.VIEWER_SCENE_STATE_JSON)
    subject_assets = [artifact for artifact in state.artifacts if artifact.artifact_type == ArtifactType.SUBJECT_3D_ASSET]
    scene_assets = [artifact for artifact in state.artifacts if artifact.artifact_type == ArtifactType.SCENE_3D_ASSET]

    if viewer_scene is None:
        issues.append("missing_viewer_scene")
    else:
        if viewer_scene.viewer_scene_artifact_id and _artifact_by_id(state.artifacts, viewer_scene.viewer_scene_artifact_id) is None:
            issues.append("missing_viewer_scene_artifact")
        if viewer_scene.viewer_state_artifact_id and _artifact_by_id(state.artifacts, viewer_scene.viewer_state_artifact_id) is None:
            issues.append("missing_viewer_state_artifact")

    if blend_artifact is None:
        issues.append("missing_blend_file")
    if preview_artifact is None:
        issues.append("missing_preview_render")
    if viewer_model_artifact is None and "missing_viewer_scene" not in issues:
        issues.append("missing_viewer_scene")
    if viewer_state_artifact is None:
        issues.append("missing_viewer_state")
    if not subject_assets:
        issues.append("missing_subject_assets")
    if not scene_assets:
        issues.append("missing_scene_assets")

    viewer_metadata = _viewer_metadata(viewer_model_artifact)
    if viewer_model_artifact is not None and not viewer_metadata:
        issues.append("missing_viewer_metadata")

    asset_url = _metadata_value(viewer_metadata, "asset_url")
    viewer_url = _metadata_value(viewer_metadata, "viewer_url")
    if viewer_model_artifact is not None and not asset_url:
        issues.append("missing_asset_url")
    if viewer_model_artifact is not None and not viewer_url:
        issues.append("missing_viewer_url")

    runtime_status = viewer_metadata.get("runtime_status") if isinstance(viewer_metadata, dict) else None
    model_check = viewer_metadata.get("model_check") if isinstance(viewer_metadata, dict) else None
    viewer_runtime_ok = _dict_bool(runtime_status, "ok")
    viewer_model_ok = _dict_bool(model_check, "ok")

    required_artifacts = [
        artifact
        for artifact in [blend_artifact, preview_artifact, viewer_model_artifact, viewer_state_artifact, *subject_assets, *scene_assets]
        if artifact is not None
    ]
    for artifact in required_artifacts:
        if not Path(artifact.uri).expanduser().is_file():
            issues.append(f"missing_artifact_file:{artifact.artifact_id}")

    issues = list(dict.fromkeys(issues))
    ready = not issues
    verified = ready and viewer_runtime_ok is True and viewer_model_ok is True

    return DeliveryHandoff(
        project_id=state.project_id,
        phase=state.phase.value,
        ready=ready,
        verified=verified,
        issues=issues,
        viewer_scene_id=viewer_scene.viewer_scene_id if viewer_scene is not None else None,
        viewer_scene_object_count=len(viewer_scene.objects) if viewer_scene is not None else None,
        viewer_scene_artifact_id=viewer_model_artifact.artifact_id if viewer_model_artifact is not None else None,
        viewer_state_artifact_id=viewer_state_artifact.artifact_id if viewer_state_artifact is not None else None,
        viewer_scene_path=viewer_model_artifact.uri if viewer_model_artifact is not None else None,
        viewer_state_path=viewer_state_artifact.uri if viewer_state_artifact is not None else None,
        viewer_base_url=_metadata_value(viewer_metadata, "base_url"),
        asset_url=asset_url,
        viewer_url=viewer_url,
        viewer_runtime_ok=viewer_runtime_ok,
        viewer_model_ok=viewer_model_ok,
        blend_file_artifact_id=blend_artifact.artifact_id if blend_artifact is not None else None,
        preview_image_id=preview_artifact.artifact_id if preview_artifact is not None else None,
        subject_asset_count=len(subject_assets),
        scene_asset_count=len(scene_assets),
        artifact_ids=artifact_ids,
    )


def _artifact_by_id(artifacts: list[ArtifactRecord], artifact_id: str) -> ArtifactRecord | None:
    for artifact in artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    return None


def _first_viewer_model_artifact(artifacts: list[ArtifactRecord]) -> ArtifactRecord | None:
    for artifact in artifacts:
        if artifact.artifact_type in VIEWER_MODEL_TYPES:
            return artifact
    return None


def _first_artifact_of_type(artifacts: list[ArtifactRecord], artifact_type: ArtifactType) -> ArtifactRecord | None:
    for artifact in artifacts:
        if artifact.artifact_type == artifact_type:
            return artifact
    return None


def _viewer_metadata(artifact: ArtifactRecord | None) -> dict[str, Any]:
    if artifact is None:
        return {}
    viewer = artifact.metadata.get("viewer")
    if isinstance(viewer, dict):
        return viewer
    metadata = artifact.metadata or {}
    base_url = metadata.get("viewer_base_url") or metadata.get("base_url")
    asset_url = metadata.get("asset_url")
    viewer_url = metadata.get("viewer_url")
    output: dict[str, Any] = {}
    if isinstance(base_url, str) and base_url:
        output["base_url"] = base_url
        urls = build_viewer_urls(artifact.uri, base_url=base_url)
        output.setdefault("asset_url", urls.asset_url)
        output.setdefault("viewer_url", urls.viewer_url)
    if isinstance(asset_url, str) and asset_url:
        output["asset_url"] = asset_url
    if isinstance(viewer_url, str) and viewer_url:
        output["viewer_url"] = viewer_url
    for key in ("runtime_status", "model_check"):
        if isinstance(metadata.get(key), dict):
            output[key] = metadata[key]
    return output


def _metadata_value(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _dict_bool(value: Any, key: str) -> bool | None:
    if isinstance(value, dict) and isinstance(value.get(key), bool):
        return value[key]
    return None
