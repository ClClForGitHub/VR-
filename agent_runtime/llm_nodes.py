"""Controlled execution wrapper for V1 LLM nodes.

LLM output is treated as a candidate only. This module builds the prompt
contract, optionally calls an OpenAI-compatible provider, parses JSON, and
validates the result with the node's Pydantic output model.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import BaseModel, Field

from agent_runtime.agent_prompts import OUTPUT_MODELS_BY_NODE, BuiltNodePrompt, build_node_prompt
from agent_runtime.llm_providers import (
    LLMChatResult,
    LLMProviderConfig,
    OpenAICompatibleChatClient,
    api_key_for_provider,
)


ClientFactory = Callable[[LLMProviderConfig, str], OpenAICompatibleChatClient]


class LLMNodeExecutionResult(BaseModel):
    ok: bool
    node_name: str
    provider: str | None = None
    model: str | None = None
    dry_run: bool = False
    prompt: BuiltNodePrompt
    output_model_name: str
    parsed_output: dict[str, Any] | None = None
    raw_text: str | None = None
    request_summary: dict[str, Any] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None


def run_llm_node(
    *,
    node_name: str,
    context_json: dict[str, Any],
    provider_configs: list[LLMProviderConfig],
    env: dict[str, str] | None = None,
    client_factory: ClientFactory | None = None,
    response_text: str | None = None,
    dry_run: bool = False,
    timeout: float = 60,
    max_tokens: int = 1200,
) -> LLMNodeExecutionResult:
    """Run a controlled LLM node boundary.

    `response_text` is a test/fixture path: no provider is called, but the same
    parse and Pydantic validation path is used. `dry_run` builds the request
    without requiring an API key. Live calls require a configured key.
    """

    output_model = OUTPUT_MODELS_BY_NODE[node_name]
    prompt = build_node_prompt(node_name, context_json=context_json, output_model=output_model)
    if response_text is not None:
        return _parse_and_validate(
            node_name=node_name,
            prompt=prompt,
            output_model=output_model,
            raw_text=response_text,
            provider=None,
            model=None,
            dry_run=False,
            request_summary={"fixture_response": True},
        )

    config = _select_provider_config(provider_configs, env=env, require_key=not dry_run)
    if config is None:
        issue = "missing_provider_config" if not provider_configs else "missing_provider_api_key"
        return LLMNodeExecutionResult(
            ok=False,
            node_name=node_name,
            prompt=prompt,
            output_model_name=output_model.__name__,
            issues=[issue],
            error=issue,
        )

    messages = _messages_for_prompt(prompt)
    extra_body = _provider_extra_body_for_node(config, node_name=node_name, env=env)
    request_summary = {
        "provider": config.provider,
        "model": config.model,
        "message_count": len(messages),
        "response_format_json": True,
        "key_suffix": config.api_key_suffix,
        "node_name": node_name,
    }
    if extra_body:
        request_summary["extra_body_keys"] = sorted(extra_body)
        if "enable_search" in extra_body:
            request_summary["enable_search"] = bool(extra_body.get("enable_search"))
        search_options = extra_body.get("search_options")
        if isinstance(search_options, dict):
            request_summary["search_options"] = {
                key: value
                for key, value in search_options.items()
                if key in {"forced_search", "search_strategy"}
            }
    if dry_run:
        return LLMNodeExecutionResult(
            ok=True,
            node_name=node_name,
            provider=config.provider,
            model=config.model,
            dry_run=True,
            prompt=prompt,
            output_model_name=output_model.__name__,
            request_summary={**request_summary, "dry_run": True},
            issues=["llm_node_dry_run"],
        )

    api_key = api_key_for_provider(config, env=env)
    if not api_key:
        return LLMNodeExecutionResult(
            ok=False,
            node_name=node_name,
            provider=config.provider,
            model=config.model,
            prompt=prompt,
            output_model_name=output_model.__name__,
            request_summary=request_summary,
            issues=["missing_api_key"],
            error=f"missing {config.api_key_env}",
        )

    factory = client_factory or (
        lambda provider_config, key: OpenAICompatibleChatClient(
            provider_config,
            api_key=key,
            timeout=timeout,
        )
    )
    client = factory(config, api_key)
    chat_result = client.chat(
        messages=messages,
        model=config.model,
        temperature=0.0,
        max_tokens=max_tokens,
        response_format_json=True,
        extra_body=extra_body,
    )
    if not chat_result.ok or chat_result.content is None:
        return _failed_provider_result(
            node_name=node_name,
            prompt=prompt,
            output_model_name=output_model.__name__,
            chat_result=chat_result,
            provider=config.provider,
            model=config.model,
        )

    return _parse_and_validate(
        node_name=node_name,
        prompt=prompt,
        output_model=output_model,
        raw_text=chat_result.content,
        provider=config.provider,
        model=config.model,
        dry_run=False,
        request_summary=chat_result.request_summary,
    )


def _messages_for_prompt(prompt: BuiltNodePrompt) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": prompt.system_prompt},
        {
            "role": "user",
            "content": "Return the validated JSON object for this node using only the supplied context_json.",
        },
    ]


def _select_provider_config(
    provider_configs: list[LLMProviderConfig],
    *,
    env: dict[str, str] | None,
    require_key: bool,
) -> LLMProviderConfig | None:
    for config in sorted(provider_configs, key=lambda item: item.priority):
        if not require_key or api_key_for_provider(config, env=env):
            return config
    return None


def _provider_extra_body_for_node(
    config: LLMProviderConfig,
    *,
    node_name: str,
    env: dict[str, str] | None,
) -> dict[str, Any] | None:
    if config.provider != "qwen":
        return None
    values = env or {}
    enabled = _env_bool(values.get("QWEN_ENABLE_SEARCH"), default=True)
    if not enabled:
        return None
    nodes = {
        item.strip()
        for item in values.get(
            "AGENT_LLM_WEB_SEARCH_NODES",
            "SceneSpecCompiler,ConceptPromptPlanner",
        ).split(",")
        if item.strip()
    }
    if node_name not in nodes:
        return None
    search_options = _search_options(values)
    return {
        "enable_search": True,
        "search_options": search_options,
    }


def _search_options(values: dict[str, str]) -> dict[str, Any]:
    raw = values.get("QWEN_SEARCH_OPTIONS_JSON")
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            payload.setdefault("forced_search", True)
            return payload
    return {
        "forced_search": _env_bool(values.get("QWEN_FORCED_SEARCH"), default=True),
        "search_strategy": values.get("QWEN_SEARCH_STRATEGY", "max"),
    }


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _failed_provider_result(
    *,
    node_name: str,
    prompt: BuiltNodePrompt,
    output_model_name: str,
    chat_result: LLMChatResult,
    provider: str,
    model: str,
) -> LLMNodeExecutionResult:
    return LLMNodeExecutionResult(
        ok=False,
        node_name=node_name,
        provider=provider,
        model=model,
        prompt=prompt,
        output_model_name=output_model_name,
        request_summary=chat_result.request_summary,
        issues=["provider_call_failed"],
        error=chat_result.error,
    )


def _parse_and_validate(
    *,
    node_name: str,
    prompt: BuiltNodePrompt,
    output_model: type[BaseModel],
    raw_text: str,
    provider: str | None,
    model: str | None,
    dry_run: bool,
    request_summary: dict[str, Any],
) -> LLMNodeExecutionResult:
    try:
        parsed = _parse_json_object(raw_text)
    except ValueError as exc:
        return LLMNodeExecutionResult(
            ok=False,
            node_name=node_name,
            provider=provider,
            model=model,
            dry_run=dry_run,
            prompt=prompt,
            output_model_name=output_model.__name__,
            raw_text=raw_text,
            request_summary=request_summary,
            issues=["json_parse_failed"],
            error=str(exc),
        )

    try:
        model_instance = _validate_model(output_model, parsed)
    except Exception as exc:
        return LLMNodeExecutionResult(
            ok=False,
            node_name=node_name,
            provider=provider,
            model=model,
            dry_run=dry_run,
            prompt=prompt,
            output_model_name=output_model.__name__,
            raw_text=raw_text,
            request_summary=request_summary,
            issues=["pydantic_validation_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )

    return LLMNodeExecutionResult(
        ok=True,
        node_name=node_name,
        provider=provider,
        model=model,
        dry_run=dry_run,
        prompt=prompt,
        output_model_name=output_model.__name__,
        parsed_output=_model_dump(model_instance),
        raw_text=raw_text,
        request_summary=request_summary,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("response did not contain a JSON object")
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("response JSON root must be an object")
    return parsed


def _validate_model(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    if hasattr(model, "model_validate"):
        return model.model_validate(payload)
    return model.parse_obj(payload)


def _model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
