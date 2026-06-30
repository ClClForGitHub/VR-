"""Runtime adapter for the existing local GLB viewer.

This module wraps `tools/glb_viewer_server.py` through HTTP checks and URL
construction helpers. It does not start or replace the viewer service.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

from pydantic import BaseModel, Field

from agent_runtime.state import ArtifactRecord, ArtifactType
from agent_runtime.viewer import ViewerHeadResult, build_viewer_urls, check_viewer_model, head_url


VIEWER_ARTIFACT_TYPES = {ArtifactType.VIEWER_SCENE_GLB, ArtifactType.VIEWER_SCENE_GLTF}


class ViewerRuntimeStatus(BaseModel):
    base_url: str
    ok: bool
    index: ViewerHeadResult
    api_list: ViewerHeadResult


class ViewerArtifactMetadata(BaseModel):
    base_url: str
    model_path: str
    asset_url: str
    viewer_url: str
    runtime_status: dict | None = None
    model_check: dict | None = None


class ViewerRuntimeAdapter:
    """Thin status/link adapter for the existing GLB viewer HTTP service."""

    def __init__(self, *, base_url: str = "http://127.0.0.1:8092", timeout: float = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def runtime_status(self) -> dict:
        index = head_url(self.base_url + "/", timeout=self.timeout)
        api_list = head_url(urljoin(self.base_url + "/", "api/list?limit=1"), timeout=self.timeout)
        status = ViewerRuntimeStatus(
            base_url=self.base_url,
            ok=index.ok and api_list.ok,
            index=index,
            api_list=api_list,
        )
        return _model_to_dict(status)

    def model_urls(self, model_path: str | Path) -> dict:
        return _model_to_dict(build_viewer_urls(model_path, base_url=self.base_url))

    def check_model(self, model_path: str | Path) -> dict:
        return check_viewer_model(model_path, base_url=self.base_url, timeout=self.timeout)

    def artifact_metadata(
        self,
        model_path: str | Path,
        *,
        runtime_status: dict | None = None,
        model_check: dict | None = None,
    ) -> dict:
        urls = build_viewer_urls(model_path, base_url=self.base_url)
        metadata = ViewerArtifactMetadata(
            base_url=self.base_url,
            model_path=str(Path(model_path).expanduser().resolve()),
            asset_url=urls.asset_url,
            viewer_url=urls.viewer_url,
            runtime_status=runtime_status,
            model_check=model_check,
        )
        return _model_to_dict(metadata)

    def annotate_artifact(
        self,
        artifact: ArtifactRecord,
        *,
        runtime_status: dict | None = None,
        model_check: dict | None = None,
    ) -> ArtifactRecord:
        if artifact.artifact_type not in VIEWER_ARTIFACT_TYPES:
            raise ValueError(f"artifact is not a viewer model artifact: {artifact.artifact_type.value}")
        payload = _model_to_dict(artifact)
        payload["metadata"] = dict(payload.get("metadata") or {})
        payload["metadata"]["viewer"] = self.artifact_metadata(
            artifact.uri,
            runtime_status=runtime_status,
            model_check=model_check,
        )
        return ArtifactRecord(**payload)


def annotate_state_artifact_with_viewer(
    artifacts: list[ArtifactRecord],
    *,
    artifact_id: str,
    adapter: ViewerRuntimeAdapter,
    runtime_status: dict | None = None,
    model_check: dict | None = None,
) -> list[ArtifactRecord]:
    updated = []
    found = False
    for artifact in artifacts:
        if artifact.artifact_id == artifact_id:
            updated.append(
                adapter.annotate_artifact(
                    artifact,
                    runtime_status=runtime_status,
                    model_check=model_check,
                )
            )
            found = True
        else:
            updated.append(artifact)
    if not found:
        raise KeyError(f"artifact not found: {artifact_id}")
    return updated


def _model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
