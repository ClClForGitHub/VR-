import json
from pathlib import Path

from agent_runtime.llm_providers import LLMChatResult, LLMProviderConfig, build_provider_configs
from agent_runtime.visual_qa import (
    SubjectAssetVisualQARequest,
    image_data_url,
    run_subject_asset_visual_qa,
)


class FakeChatClient:
    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def chat(self, **kwargs):
        return LLMChatResult(
            ok=True,
            provider=self.config.provider,
            model=kwargs["model"],
            content=json.dumps(
                {
                    "status": "pass",
                    "score": 0.91,
                    "issues": [],
                    "suggested_action": "accept",
                    "reasoning": "matches the source image well enough",
                }
            ),
            request_summary={"model": kwargs["model"]},
        )


def _image(path: Path) -> Path:
    path.write_bytes(b"fake-image")
    return path


def test_image_data_url_uses_mime_type_and_base64(tmp_path: Path) -> None:
    url = image_data_url(_image(tmp_path / "source.png"))

    assert url.startswith("data:image/png;base64,")
    assert "fake-image" not in url


def test_visual_qa_dry_run_uses_first_vision_provider(tmp_path: Path) -> None:
    configs = build_provider_configs(env={"QWEN_API_KEY": "fake-qwen", "DEEPSEEK_API_KEY": "fake-deepseek"})

    result = run_subject_asset_visual_qa(
        request=SubjectAssetVisualQARequest(
            subject_id="subject_001",
            asset_id="asset_001",
            source_image_path=str(_image(tmp_path / "source.png")),
            preview_image_path=str(_image(tmp_path / "preview.png")),
        ),
        provider_configs=configs,
        env={"QWEN_API_KEY": "fake-qwen", "DEEPSEEK_API_KEY": "fake-deepseek"},
        dry_run=True,
    )

    assert result.ok is True
    assert result.provider == "qwen"
    assert result.model == "qwen3.7-plus"
    assert result.status == "uncertain"
    assert result.issues == ["visual_qa_dry_run"]
    assert result.request_summary["key_suffix"] == "qwen"


def test_visual_qa_parses_provider_json_response(tmp_path: Path) -> None:
    configs = build_provider_configs(env={"QWEN_API_KEY": "fake-qwen"})

    result = run_subject_asset_visual_qa(
        request=SubjectAssetVisualQARequest(
            subject_id="subject_001",
            asset_id="asset_001",
            source_image_path=str(_image(tmp_path / "source.png")),
            preview_image_path=str(_image(tmp_path / "preview.png")),
        ),
        provider_configs=configs,
        env={"QWEN_API_KEY": "fake-qwen"},
        client_factory=lambda config, api_key: FakeChatClient(config, api_key),
    )

    assert result.ok is True
    assert result.provider == "qwen"
    assert result.status == "pass"
    assert result.score == 0.91
    assert result.suggested_action == "accept"


def test_visual_qa_reports_missing_vision_provider(tmp_path: Path) -> None:
    result = run_subject_asset_visual_qa(
        request=SubjectAssetVisualQARequest(
            subject_id="subject_001",
            asset_id="asset_001",
            source_image_path=str(_image(tmp_path / "source.png")),
            preview_image_path=str(_image(tmp_path / "preview.png")),
        ),
        provider_configs=[
            LLMProviderConfig(
                provider="deepseek",
                base_url="https://api.deepseek.com",
                api_key_env="DEEPSEEK_API_KEY",
                model="deepseek-v4-flash",
                supports_vision=False,
            )
        ],
        env={"DEEPSEEK_API_KEY": "fake-deepseek"},
    )

    assert result.ok is False
    assert result.status == "uncertain"
    assert result.issues == ["no_vision_provider_configured"]
