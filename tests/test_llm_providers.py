from pathlib import Path

from agent_runtime.llm_providers import build_provider_configs, load_agent_llm_env, provider_public_summary


def test_load_agent_llm_env_parses_local_file_without_logging_plaintext(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.agent_llm.local"
    env_file.write_text(
        "\n".join(
            [
                "AGENT_LLM_PROVIDER_PRIORITY=qwen,deepseek",
                "QWEN_API_KEY=fake-qwen-secret",
                'QWEN_MODEL_ALIAS="QWEN 3.7max"',
                "DEEPSEEK_API_KEY=fake-deepseek-secret",
            ]
        ),
        encoding="utf-8",
    )

    values = load_agent_llm_env(env_file)
    configs = build_provider_configs(env=values)
    summary = provider_public_summary(configs)

    assert values["QWEN_MODEL_ALIAS"] == "QWEN 3.7max"
    assert [item.provider for item in configs] == ["qwen", "deepseek"]
    assert summary[0]["api_key_suffix"] == "cret"
    assert str(summary).find("fake-qwen-secret") == -1


def test_provider_configs_use_current_defaults_and_vision_boundary() -> None:
    configs = build_provider_configs(
        env={
            "AGENT_LLM_PROVIDER_PRIORITY": "qwen,deepseek",
            "QWEN_API_KEY": "fake-0000qwen",
            "DEEPSEEK_API_KEY": "fake-1111deepseek",
        }
    )
    qwen = configs[0]
    deepseek = configs[1]

    assert qwen.model == "qwen3.7-max"
    assert qwen.vision_model == "qwen3.7-plus"
    assert qwen.supports_vision is True
    assert deepseek.base_url == "https://api.deepseek.com"
    assert deepseek.supports_vision is False
