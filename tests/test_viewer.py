from pathlib import Path

from agent_runtime.viewer import build_viewer_urls, check_viewer_model


def test_build_viewer_urls_quotes_absolute_model_path(tmp_path: Path) -> None:
    model = tmp_path / "space model.glb"
    urls = build_viewer_urls(model, base_url="http://viewer.local/")

    assert urls.asset_url.startswith("http://viewer.local/asset?path=")
    assert urls.viewer_url.startswith("http://viewer.local/viewer?path=")
    assert "space%20model.glb" in urls.asset_url


def test_check_viewer_model_reports_connection_failure(tmp_path: Path) -> None:
    result = check_viewer_model(
        tmp_path / "missing.glb",
        base_url="http://127.0.0.1:9",
        timeout=0.2,
    )

    assert result["ok"] is False
    assert result["asset"]["ok"] is False
    assert result["viewer"]["ok"] is False
