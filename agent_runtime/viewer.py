"""Helpers for checking the existing GLB viewer runtime."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel


class ViewerUrls(BaseModel):
    asset_url: str
    viewer_url: str


class ViewerHeadResult(BaseModel):
    url: str
    ok: bool
    status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    error: str | None = None


def build_viewer_urls(model_path: str | Path, base_url: str = "http://127.0.0.1:8092") -> ViewerUrls:
    base = base_url.rstrip("/")
    resolved = str(Path(model_path).expanduser().resolve())
    encoded = quote(resolved)
    return ViewerUrls(
        asset_url=f"{base}/asset?path={encoded}",
        viewer_url=f"{base}/viewer?path={encoded}",
    )


def head_url(url: str, timeout: float = 10) -> ViewerHeadResult:
    try:
        request = Request(url, method="HEAD")
        with urlopen(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            return ViewerHeadResult(
                url=url,
                ok=200 <= response.status < 300,
                status=response.status,
                content_type=response.headers.get("Content-Type"),
                content_length=int(length) if length is not None else None,
            )
    except Exception as exc:  # pragma: no cover - exact urllib errors vary by platform
        return ViewerHeadResult(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")


def check_viewer_model(
    model_path: str | Path,
    *,
    base_url: str = "http://127.0.0.1:8092",
    timeout: float = 10,
) -> dict:
    urls = build_viewer_urls(model_path, base_url=base_url)
    asset = head_url(urls.asset_url, timeout=timeout)
    viewer = head_url(urls.viewer_url, timeout=timeout)
    return {
        "ok": asset.ok and viewer.ok,
        "asset": _model_to_dict(asset),
        "viewer": _model_to_dict(viewer),
        "urls": _model_to_dict(urls),
    }


def _model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
