import json

from agent_runtime.llm_nodes import run_llm_node
from agent_runtime.llm_providers import LLMChatResult, build_provider_configs


class FakeChatClient:
    calls = []

    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def chat(self, **kwargs):
        self.__class__.calls.append(kwargs)
        request_summary = {
            "model": kwargs["model"],
            "response_format_json": kwargs["response_format_json"],
        }
        if kwargs.get("extra_body"):
            request_summary["enable_search"] = bool(kwargs["extra_body"].get("enable_search"))
            request_summary["search_options"] = kwargs["extra_body"].get("search_options")
        return LLMChatResult(
            ok=True,
            provider=self.config.provider,
            model=kwargs["model"],
            content=json.dumps(
                {
                    "final_preview_prompt": "A clean stylized workshop with one friendly hero robot.",
                    "subject_prompts": {"subject_robot": "front three-quarter view of a friendly robot"},
                    "scene_prompts": ["compact workshop background"],
                    "negative_prompt": "blurry, low quality",
                }
            ),
            request_summary=request_summary,
        )


def test_llm_node_dry_run_builds_qwen_request_without_plaintext_key() -> None:
    configs = build_provider_configs(env={"QWEN_API_KEY": "fake-qwen-secret"})

    result = run_llm_node(
        node_name="ConceptPromptPlanner",
        context_json={"scene_spec": {"scene_id": "scene_001"}},
        provider_configs=configs,
        env={},
        dry_run=True,
    )

    assert result.ok is True
    assert result.provider == "qwen"
    assert result.dry_run is True
    assert result.issues == ["llm_node_dry_run"]
    assert result.request_summary["key_suffix"] == "cret"
    assert "fake-qwen-secret" not in str(result)


def test_llm_node_fixture_response_is_validated_by_pydantic() -> None:
    result = run_llm_node(
        node_name="ConceptPromptPlanner",
        context_json={"scene_spec": {"scene_id": "scene_001"}},
        provider_configs=[],
        response_text=json.dumps(
            {
                "final_preview_prompt": "A robot in a small workshop.",
                "subject_prompts": {"subject_robot": "robot concept"},
                "scene_prompts": ["workshop scene"],
            }
        ),
    )

    assert result.ok is True
    assert result.parsed_output["final_preview_prompt"] == "A robot in a small workshop."


def test_llm_node_reports_schema_validation_errors() -> None:
    result = run_llm_node(
        node_name="ConceptPromptPlanner",
        context_json={"scene_spec": {"scene_id": "scene_001"}},
        provider_configs=[],
        response_text=json.dumps({"subject_prompts": {}}),
    )

    assert result.ok is False
    assert result.issues == ["pydantic_validation_failed"]
    assert "final_preview_prompt" in (result.error or "")


def test_llm_node_live_path_uses_injected_client_and_json_mode() -> None:
    FakeChatClient.calls = []
    configs = build_provider_configs(env={"QWEN_API_KEY": "fake-qwen-secret"})

    result = run_llm_node(
        node_name="ConceptPromptPlanner",
        context_json={"scene_spec": {"scene_id": "scene_001"}},
        provider_configs=configs,
        env={"QWEN_API_KEY": "fake-qwen-secret"},
        client_factory=lambda config, api_key: FakeChatClient(config, api_key),
    )

    assert result.ok is True
    assert result.provider == "qwen"
    assert result.model == "qwen3.7-max"
    assert result.request_summary["response_format_json"] is True
    assert result.request_summary["enable_search"] is True
    assert result.request_summary["search_options"]["forced_search"] is True
    assert FakeChatClient.calls[-1]["extra_body"]["enable_search"] is True
    assert result.parsed_output["subject_prompts"]["subject_robot"].startswith("front")


def test_llm_node_search_can_be_disabled_for_qwen() -> None:
    FakeChatClient.calls = []
    configs = build_provider_configs(env={"QWEN_API_KEY": "fake-qwen-secret"})

    result = run_llm_node(
        node_name="ConceptPromptPlanner",
        context_json={"scene_spec": {"scene_id": "scene_001"}},
        provider_configs=configs,
        env={"QWEN_API_KEY": "fake-qwen-secret", "QWEN_ENABLE_SEARCH": "false"},
        client_factory=lambda config, api_key: FakeChatClient(config, api_key),
    )

    assert result.ok is True
    assert "enable_search" not in result.request_summary
    assert FakeChatClient.calls[-1]["extra_body"] is None
