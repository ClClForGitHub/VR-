"""OpenAI-compatible LLM provider adapters for agent testing.

Credentials are loaded from environment variables or a local env file. This
module never logs plaintext API keys; summaries expose only key suffixes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field


DEFAULT_AGENT_LLM_ENV_FILE = Path("/home/team/zouzhiyuan/image23D_Agent/.env.agent_llm.local")


class LLMProviderConfig(BaseModel):
    provider: str
    base_url: str
    api_key_env: str
    api_key_suffix: str | None = None
    model: str
    model_alias: str | None = None
    vision_model: str | None = None
    supports_vision: bool = False
    priority: int = 100

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class LLMChatResult(BaseModel):
    ok: bool
    provider: str
    model: str
    status: int | None = None
    content: str | None = None
    data: dict[str, Any] | None = None
    request_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class OpenAICompatibleChatClient:
    def __init__(self, config: LLMProviderConfig, *, api_key: str, timeout: float = 60) -> None:
        self.config = config
        self.api_key = api_key
        self.timeout = timeout

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_format_json: bool = False,
        extra_body: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> LLMChatResult:
        selected_model = model or self.config.model
        payload: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}
        if extra_body:
            payload.update(extra_body)
        request_summary = {
            "url": self.config.chat_completions_url,
            "model": selected_model,
            "message_count": len(messages),
            "response_format_json": response_format_json,
            "key_suffix": self.config.api_key_suffix,
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
            return LLMChatResult(
                ok=True,
                provider=self.config.provider,
                model=selected_model,
                request_summary={**request_summary, "dry_run": True},
            )
        result = _post_json(
            self.config.chat_completions_url,
            payload,
            api_key=self.api_key,
            timeout=self.timeout,
        )
        if not result["ok"]:
            return LLMChatResult(
                ok=False,
                provider=self.config.provider,
                model=selected_model,
                status=result.get("status"),
                request_summary=request_summary,
                error=result.get("error"),
                data=result.get("data"),
            )
        content = _extract_chat_content(result.get("data"))
        return LLMChatResult(
            ok=content is not None,
            provider=self.config.provider,
            model=selected_model,
            status=result.get("status"),
            content=content,
            data=result.get("data"),
            request_summary=request_summary,
            error=None if content is not None else "response did not contain choices[0].message.content",
        )


def load_agent_llm_env(env_file: str | Path | None = DEFAULT_AGENT_LLM_ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file is not None:
        path = Path(env_file).expanduser()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                values[key.strip()] = _strip_shell_quotes(value.strip())
    values.update({key: value for key, value in os.environ.items() if key.startswith(("QWEN_", "DEEPSEEK_", "AGENT_LLM_"))})
    return values


def build_provider_configs(
    *,
    env: dict[str, str] | None = None,
    env_file: str | Path | None = DEFAULT_AGENT_LLM_ENV_FILE,
) -> list[LLMProviderConfig]:
    values = dict(env) if env is not None else load_agent_llm_env(env_file)
    priority_names = [
        item.strip().lower()
        for item in values.get("AGENT_LLM_PROVIDER_PRIORITY", "qwen,deepseek").split(",")
        if item.strip()
    ]
    configs = [
        LLMProviderConfig(
            provider="qwen",
            base_url=values.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            api_key_env="QWEN_API_KEY",
            api_key_suffix=_suffix(values.get("QWEN_API_KEY")),
            model=values.get("QWEN_MODEL", "qwen3.7-max"),
            model_alias=values.get("QWEN_MODEL_ALIAS"),
            vision_model=values.get("QWEN_VISION_MODEL", "qwen3.7-plus"),
            supports_vision=True,
            priority=_priority(priority_names, "qwen"),
        ),
        LLMProviderConfig(
            provider="deepseek",
            base_url=values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            api_key_env="DEEPSEEK_API_KEY",
            api_key_suffix=_suffix(values.get("DEEPSEEK_API_KEY")),
            model=values.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            model_alias=values.get("DEEPSEEK_MODEL_ALIAS"),
            vision_model=values.get("DEEPSEEK_VISION_MODEL"),
            supports_vision=False,
            priority=_priority(priority_names, "deepseek"),
        ),
    ]
    return sorted(configs, key=lambda item: item.priority)


def provider_public_summary(configs: list[LLMProviderConfig]) -> list[dict[str, Any]]:
    return [
        {
            "provider": config.provider,
            "base_url": config.base_url,
            "api_key_env": config.api_key_env,
            "api_key_suffix": config.api_key_suffix,
            "model": config.model,
            "model_alias": config.model_alias,
            "vision_model": config.vision_model,
            "supports_vision": config.supports_vision,
            "priority": config.priority,
        }
        for config in configs
    ]


def api_key_for_provider(config: LLMProviderConfig, *, env: dict[str, str] | None = None) -> str | None:
    values = env if env is not None else load_agent_llm_env()
    return values.get(config.api_key_env)


def _post_json(url: str, payload: dict[str, Any], *, api_key: str, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read()
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "data": json.loads(raw_body.decode("utf-8")) if raw_body else None,
            }
    except HTTPError as exc:
        data = None
        try:
            raw = exc.read()
            data = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            data = None
        return {"ok": False, "status": exc.code, "data": data, "error": f"HTTPError: {exc}"}
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _extract_chat_content(data: dict[str, Any] | None) -> str | None:
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else None


def _strip_shell_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _suffix(value: str | None, length: int = 4) -> str | None:
    if not value:
        return None
    return value[-length:]


def _priority(priority_names: list[str], provider: str) -> int:
    try:
        return priority_names.index(provider)
    except ValueError:
        return 100
