"""Deterministic delivery package builder for V1 scene outputs."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.artifacts import FileArtifactStore, sha256_file, utc_now_iso
from agent_runtime.delivery_handoff import build_delivery_handoff
from agent_runtime.state import AgentProjectState, ArtifactRecord, ArtifactType, WorkflowPhase


VIEWER_MODEL_TYPES = {ArtifactType.VIEWER_SCENE_GLB, ArtifactType.VIEWER_SCENE_GLTF}


class DeliveryPackageItem(BaseModel):
    artifact_id: str
    artifact_type: str
    semantic_role: str | None = None
    source_uri: str
    package_path: str
    size_bytes: int
    sha256: str
    version: int


class DeliveryPackageResult(BaseModel):
    ok: bool
    package_id: str
    package_dir: str
    package_zip: str
    package_artifact_id: str | None = None
    metadata_json: str
    version_manifest_json: str
    issues: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    items: list[DeliveryPackageItem] = Field(default_factory=list)


def build_delivery_package(
    *,
    state: AgentProjectState,
    output_dir: str | Path,
    artifact_store: FileArtifactStore | None = None,
    package_id: str | None = None,
) -> tuple[DeliveryPackageResult, AgentProjectState]:
    package_id = package_id or f"delivery_{state.project_id}_{uuid4().hex[:8]}"
    output_path = Path(output_dir).expanduser().resolve()
    package_dir = output_path / package_id
    files_dir = package_dir / "files"
    package_zip = output_path / f"{package_id}.zip"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    if package_zip.exists():
        package_zip.unlink()
    files_dir.mkdir(parents=True, exist_ok=True)

    selected = _select_delivery_artifacts(state)
    issues = list(selected["issues"])
    items: list[DeliveryPackageItem] = []
    copied_ids: set[str] = set()
    for role, artifacts in selected["groups"].items():
        for artifact in artifacts:
            if artifact.artifact_id in copied_ids:
                continue
            copied_ids.add(artifact.artifact_id)
            item = _copy_artifact_to_package(artifact, files_dir / role)
            items.append(item)

    handoff = build_delivery_handoff(state)
    checks = {
        "has_blend_file": bool(selected["groups"]["blender"]),
        "has_preview_render": bool(selected["groups"]["preview"]),
        "has_viewer_scene": bool(selected["groups"]["viewer_scene"]),
        "has_viewer_state": bool(selected["groups"]["viewer_state"]),
        "subject_asset_count": len(selected["groups"]["subject_assets"]),
        "scene_asset_count": len(selected["groups"]["scene_assets"]),
        "has_metadata_json": True,
        "has_version_manifest_json": True,
        "delivery_handoff_ready": handoff.ready,
        "delivery_handoff_verified": handoff.verified,
        "texture_policy": "embedded_in_glb_or_sidecar_artifact",
    }
    metadata_path = package_dir / "metadata.json"
    manifest_path = package_dir / "version_manifest.json"
    metadata = {
        "package_id": package_id,
        "project_id": state.project_id,
        "thread_id": state.thread_id,
        "phase_at_packaging": state.phase.value,
        "created_at": utc_now_iso(),
        "delivery_handoff": _model_to_dict(handoff),
        "checks": checks,
        "issues": issues,
        "artifact_count": len(items),
    }
    manifest = {
        "package_id": package_id,
        "created_at": metadata["created_at"],
        "source_state": {
            "project_id": state.project_id,
            "thread_id": state.thread_id,
            "version": state.version,
            "artifact_ids": sorted(state.artifact_ids()),
        },
        "items": [_model_to_dict(item) for item in items],
    }
    _write_json(metadata_path, metadata)
    _write_json(manifest_path, manifest)
    _zip_directory(package_dir, package_zip)

    ok = not issues and package_zip.is_file()
    package_artifact_id = None
    if artifact_store is not None:
        package_artifact_id = package_id
        package_artifact = artifact_store.register_file(
            package_zip,
            ArtifactType.EXPORT_PACKAGE,
            artifact_id=package_artifact_id,
            semantic_role="delivery_package",
            metadata={
                "stage": "delivery",
                "package_id": package_id,
                "ok": ok,
                "issue_count": len(issues),
                "item_count": len(items),
            },
        )
        state.artifacts.append(package_artifact)
        state.phase = WorkflowPhase.DELIVERY

    result = DeliveryPackageResult(
        ok=ok,
        package_id=package_id,
        package_dir=str(package_dir),
        package_zip=str(package_zip),
        package_artifact_id=package_artifact_id,
        metadata_json=str(metadata_path),
        version_manifest_json=str(manifest_path),
        issues=issues,
        checks=checks,
        items=items,
    )
    return result, state


def _select_delivery_artifacts(state: AgentProjectState) -> dict[str, Any]:
    issues: list[str] = []
    blend = _artifact_by_id(state.artifacts, state.blender_scene.blend_file_artifact_id) if state.blender_scene and state.blender_scene.blend_file_artifact_id else None
    if blend is None:
        blend = _first_artifact_of_type(state.artifacts, ArtifactType.BLENDER_FILE)
    preview = _artifact_by_id(state.artifacts, state.blender_scene.preview_image_id) if state.blender_scene and state.blender_scene.preview_image_id else None
    if preview is None:
        preview = _first_artifact_of_type(state.artifacts, ArtifactType.BLENDER_PREVIEW_RENDER)
    viewer_scene = (
        _artifact_by_id(state.artifacts, state.viewer_scene.viewer_scene_artifact_id)
        if state.viewer_scene and state.viewer_scene.viewer_scene_artifact_id
        else None
    )
    if viewer_scene is None:
        viewer_scene = _first_viewer_model_artifact(state.artifacts)
    viewer_state = (
        _artifact_by_id(state.artifacts, state.viewer_scene.viewer_state_artifact_id)
        if state.viewer_scene and state.viewer_scene.viewer_state_artifact_id
        else None
    )
    if viewer_state is None:
        viewer_state = _first_artifact_of_type(state.artifacts, ArtifactType.VIEWER_SCENE_STATE_JSON)
    subject_assets = [artifact for artifact in state.artifacts if artifact.artifact_type == ArtifactType.SUBJECT_3D_ASSET]
    scene_assets = [artifact for artifact in state.artifacts if artifact.artifact_type == ArtifactType.SCENE_3D_ASSET]

    if blend is None:
        issues.append("missing_blend_file")
    if preview is None:
        issues.append("missing_preview_render")
    if viewer_scene is None:
        issues.append("missing_viewer_scene")
    if viewer_state is None:
        issues.append("missing_viewer_state")
    if not subject_assets:
        issues.append("missing_subject_assets")
    if not scene_assets:
        issues.append("missing_scene_assets")

    groups = {
        "blender": [blend] if blend is not None else [],
        "preview": [preview] if preview is not None else [],
        "viewer_scene": [viewer_scene] if viewer_scene is not None else [],
        "viewer_state": [viewer_state] if viewer_state is not None else [],
        "subject_assets": subject_assets,
        "scene_assets": scene_assets,
    }
    missing_files = [
        artifact.artifact_id
        for artifacts in groups.values()
        for artifact in artifacts
        if not Path(artifact.uri).expanduser().is_file()
    ]
    issues.extend(f"missing_artifact_file:{artifact_id}" for artifact_id in missing_files)
    return {"issues": issues, "groups": groups}


def _copy_artifact_to_package(artifact: ArtifactRecord, target_dir: Path) -> DeliveryPackageItem:
    source = Path(artifact.uri).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{artifact.artifact_id}{source.suffix}"
    shutil.copy2(source, target)
    return DeliveryPackageItem(
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type.value,
        semantic_role=artifact.semantic_role,
        source_uri=str(source),
        package_path=str(target.relative_to(target_dir.parent.parent)),
        size_bytes=target.stat().st_size,
        sha256=sha256_file(target),
        version=artifact.version,
    )


def _artifact_by_id(artifacts: list[ArtifactRecord], artifact_id: str | None) -> ArtifactRecord | None:
    if not artifact_id:
        return None
    for artifact in artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    return None


def _first_artifact_of_type(artifacts: list[ArtifactRecord], artifact_type: ArtifactType) -> ArtifactRecord | None:
    for artifact in artifacts:
        if artifact.artifact_type == artifact_type:
            return artifact
    return None


def _first_viewer_model_artifact(artifacts: list[ArtifactRecord]) -> ArtifactRecord | None:
    for artifact in artifacts:
        if artifact.artifact_type in VIEWER_MODEL_TYPES:
            return artifact
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _zip_directory(source_dir: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))


def _model_to_dict(model) -> dict:
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
