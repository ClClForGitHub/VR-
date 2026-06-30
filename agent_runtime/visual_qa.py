"""MLLM visual QA helpers for subject assets."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from agent_runtime.llm_providers import (
    LLMProviderConfig,
    OpenAICompatibleChatClient,
    api_key_for_provider,
)


VisualQAStatus = Literal["pass", "fail", "uncertain"]
VisualQASuggestedAction = Literal["accept", "rerun_hunyuan3d", "ask_user", "manual_review"]


class SubjectAssetVisualQARequest(BaseModel):
    subject_id: str
    asset_id: str
    source_image_path: str
    preview_image_path: str
    subject_description: str | None = None


class SubjectAssetVisualQAResult(BaseModel):
    ok: bool
    provider: str | None = None
    model: str | None = None
    status: VisualQAStatus
    score: float
    issues: list[str] = Field(default_factory=list)
    suggested_action: VisualQASuggestedAction
    reasoning: str | None = None
    raw_text: str | None = None
    request_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


ClientFactory = Callable[[LLMProviderConfig, str], OpenAICompatibleChatClient]


def run_subject_asset_visual_qa(
    *,
    request: SubjectAssetVisualQARequest,
    provider_configs: list[LLMProviderConfig],
    env: dict[str, str] | None = None,
    client_factory: ClientFactory | None = None,
    dry_run: bool = False,
    timeout: float = 60,
) -> SubjectAssetVisualQAResult:
    config = _first_vision_provider(provider_configs)
    if config is None:
        return SubjectAssetVisualQAResult(
            ok=False,
            status="uncertain",
            score=0.5,
            issues=["no_vision_provider_configured"],
            suggested_action="manual_review",
            error="no provider with supports_vision=true",
        )
    api_key = api_key_for_provider(config, env=env)
    if not api_key:
        return SubjectAssetVisualQAResult(
            ok=False,
            provider=config.provider,
            model=config.vision_model,
            status="uncertain",
            score=0.5,
            issues=["missing_api_key"],
            suggested_action="manual_review",
            error=f"missing {config.api_key_env}",
        )
    selected_model = config.vision_model or config.model
    messages = build_subject_asset_visual_qa_messages(request)
    if dry_run:
        return SubjectAssetVisualQAResult(
            ok=True,
            provider=config.provider,
            model=selected_model,
            status="uncertain",
            score=0.5,
            issues=["visual_qa_dry_run"],
            suggested_action="manual_review",
            request_summary={
                "provider": config.provider,
                "model": selected_model,
                "source_image_path": request.source_image_path,
                "preview_image_path": request.preview_image_path,
                "message_count": len(messages),
                "key_suffix": config.api_key_suffix,
            },
        )
    factory = client_factory or (lambda provider_config, key: OpenAICompatibleChatClient(provider_config, api_key=key, timeout=timeout))
    client = factory(config, api_key)
    chat_result = client.chat(
        messages=messages,
        model=selected_model,
        temperature=0.0,
        max_tokens=800,
        response_format_json=True,
    )
    if not chat_result.ok or chat_result.content is None:
        return SubjectAssetVisualQAResult(
            ok=False,
            provider=config.provider,
            model=selected_model,
            status="uncertain",
            score=0.5,
            issues=["provider_call_failed"],
            suggested_action="manual_review",
            request_summary=chat_result.request_summary,
            error=chat_result.error,
        )
    parsed = _parse_json_object(chat_result.content)
    return _result_from_parsed(
        parsed,
        provider=config.provider,
        model=selected_model,
        raw_text=chat_result.content,
        request_summary=chat_result.request_summary,
    )


def build_subject_asset_visual_qa_messages(request: SubjectAssetVisualQARequest) -> list[dict[str, Any]]:
    description = request.subject_description or "No additional subject description was provided."
    text = (
        "You are checking whether a generated 3D subject asset preview still matches the source subject image. "
        "Compare image A (source subject concept/reference) with image B (rendered 3D asset preview). "
        "Return strict JSON with keys: status, score, issues, suggested_action, reasoning. "
        "status must be one of pass, fail, uncertain. score must be 0..1. "
        "suggested_action must be one of accept, rerun_hunyuan3d, ask_user, manual_review. "
        f"subject_id={request.subject_id}; asset_id={request.asset_id}; description={description}"
    )
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "text", "text": "Image A: source subject image."},
                {"type": "image_url", "image_url": {"url": image_data_url(request.source_image_path)}},
                {"type": "text", "text": "Image B: rendered 3D asset preview."},
                {"type": "image_url", "image_url": {"url": image_data_url(request.preview_image_path)}},
            ],
        }
    ]


def image_data_url(path: str | Path) -> str:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _first_vision_provider(configs: list[LLMProviderConfig]) -> LLMProviderConfig | None:
    for config in sorted(configs, key=lambda item: item.priority):
        if config.supports_vision and config.vision_model:
            return config
    return None


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
        if start == -1 or end == -1 or end <= start:
            return {"status": "uncertain", "score": 0.5, "issues": ["invalid_json"], "reasoning": text}
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return {"status": "uncertain", "score": 0.5, "issues": ["invalid_json"], "reasoning": text}
    return parsed if isinstance(parsed, dict) else {"status": "uncertain", "score": 0.5, "issues": ["invalid_json"]}


def _result_from_parsed(
    parsed: dict[str, Any],
    *,
    provider: str,
    model: str,
    raw_text: str,
    request_summary: dict[str, Any],
) -> SubjectAssetVisualQAResult:
    status = parsed.get("status")
    if status not in {"pass", "fail", "uncertain"}:
        status = "uncertain"
    score = parsed.get("score", 0.5)
    if not isinstance(score, int | float):
        score = 0.5
    score = max(0.0, min(1.0, float(score)))
    issues = parsed.get("issues", [])
    if isinstance(issues, str):
        issues = [issues]
    if not isinstance(issues, list):
        issues = ["invalid_issues"]
    suggested_action = parsed.get("suggested_action")
    if suggested_action not in {"accept", "rerun_hunyuan3d", "ask_user", "manual_review"}:
        suggested_action = _suggested_action_for_status(status)
    return SubjectAssetVisualQAResult(
        ok=True,
        provider=provider,
        model=model,
        status=status,
        score=score,
        issues=[str(issue) for issue in issues],
        suggested_action=suggested_action,
        reasoning=parsed.get("reasoning") if isinstance(parsed.get("reasoning"), str) else None,
        raw_text=raw_text,
        request_summary=request_summary,
    )


def _suggested_action_for_status(status: str) -> VisualQASuggestedAction:
    if status == "pass":
        return "accept"
    if status == "fail":
        return "rerun_hunyuan3d"
    return "ask_user"
