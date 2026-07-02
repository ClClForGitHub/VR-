"""Execute structured concept-image handoffs through a bounded image backend.

The executor consumes the existing runtime handoff JSON produced by
``runtime_delegation`` and returns the existing ``RuntimeConceptImageResult``
shape consumed by ``runtime_handoff_apply``. It does not introduce another
state store or artifact registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.codex_self_mcp import CodexSelfMCPAdapter
from agent_runtime.image2_reference_adapter import (
    CodexSelfMCPImage2Adapter,
    Image2ReferenceAttachment,
    build_attachment_manifest,
    prepare_viewable_attachment_manifest,
)


ConceptGenerationMode = Literal["text_to_image", "image_guided", "multi_image_composite"]
ConceptOutputType = Literal["subject_concept", "scene_concept", "target_render"]


class ConceptImageExecutionRequest(BaseModel):
    run_dir: str
    handoff_id: str | None = None
    handoff_json: str | None = None
    backend_name: str
    dry_run: bool = False


class ConceptImageExecutionCallRecord(BaseModel):
    requirement_id: str
    concept_version: int | None = None
    output_type: ConceptOutputType
    generation_mode: ConceptGenerationMode
    prompt: str
    input_reference_image_ids: list[str] = Field(default_factory=list)
    input_image_paths: list[str] = Field(default_factory=list)
    source_requirement_ids: list[str] = Field(default_factory=list)
    source_image_paths: list[str] = Field(default_factory=list)
    attachment_manifest: list[dict[str, Any]] = Field(default_factory=list)
    backend: str
    started_at: str
    finished_at: str | None = None
    output_image_path: str | None = None
    artifact_id: str | None = None
    ok: bool = False
    issues: list[str] = Field(default_factory=list)


class ConceptImageExecutionResult(BaseModel):
    ok: bool
    run_dir: str
    backend: str
    status: Literal["completed", "blocked", "dry_run", "failed"]
    image_results: list[dict[str, Any]] = Field(default_factory=list)
    call_records: list[ConceptImageExecutionCallRecord] = Field(default_factory=list)
    live_generation_calls_jsonl: str
    issues: list[str] = Field(default_factory=list)
    capability: dict[str, Any] = Field(default_factory=dict)


class ConceptImageBackendCapability(BaseModel):
    backend_name: str
    text_to_image: bool = False
    image_guided_single_reference: bool = False
    multi_image_composite: bool = False
    output_extraction: bool = False
    structured_file_attachments: bool = False
    native_images_parameter: bool = False
    agent_view_image_reference: bool = False
    agent_view_image_then_generate: bool = False
    probe_log_path: str | None = None
    issues: list[str] = Field(default_factory=list)


class ConceptImageBackendGenerationRequest(BaseModel):
    requirement_id: str
    output_type: ConceptOutputType
    generation_mode: ConceptGenerationMode
    prompt: str
    negative_prompt: str | None = None
    input_reference_image_ids: list[str] = Field(default_factory=list)
    input_image_paths: list[str] = Field(default_factory=list)
    source_requirement_ids: list[str] = Field(default_factory=list)
    source_image_paths: list[str] = Field(default_factory=list)
    attachment_manifest: list[Image2ReferenceAttachment] = Field(default_factory=list)
    output_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConceptImageBackendGenerationResult(BaseModel):
    ok: bool
    backend: str
    output_image_path: str | None = None
    issues: list[str] = Field(default_factory=list)
    error: str | None = None
    raw_summary: dict[str, Any] = Field(default_factory=dict)


class ConceptImageBackend:
    """Backend interface for structured concept image generation."""

    backend_name = "concept_image_backend"

    def capability(self) -> ConceptImageBackendCapability:
        raise NotImplementedError

    def generate(self, request: ConceptImageBackendGenerationRequest) -> ConceptImageBackendGenerationResult:
        raise NotImplementedError


class CodexSelfMCPConceptImageBackend(ConceptImageBackend):
    """Codex-self backend with explicit capability limits.

    The current codex-self helper can call a prompt-only MCP image flow and
    extract the final image from the JSONL log. It does not expose a proven
    local-file attachment API, so image-guided and multi-image composite
    requirements are blocked instead of downgraded to text-only prompts.
    """

    backend_name = "codex_self_mcp"

    def __init__(self, adapter: CodexSelfMCPAdapter | None = None, *, timeout_seconds: float = 900) -> None:
        self.adapter = adapter or CodexSelfMCPAdapter()
        self.timeout_seconds = timeout_seconds

    def capability(self) -> ConceptImageBackendCapability:
        status = self.adapter.status(run_smoke=False)
        issues = list(status.issues)
        if status.client_script_exists:
            issues.append("codex_self_mcp_helper_has_no_local_file_attachment_arguments")
        return ConceptImageBackendCapability(
            backend_name=self.backend_name,
            text_to_image=bool(status.ok),
            image_guided_single_reference=False,
            multi_image_composite=False,
            output_extraction=status.client_script_exists,
            structured_file_attachments=False,
            issues=issues,
        )

    def generate(self, request: ConceptImageBackendGenerationRequest) -> ConceptImageBackendGenerationResult:
        if request.generation_mode != "text_to_image" or request.input_image_paths or request.source_image_paths:
            return ConceptImageBackendGenerationResult(
                ok=False,
                backend=self.backend_name,
                issues=["codex_self_mcp_does_not_support_structured_image_attachments"],
            )
        output_path = Path(request.output_path).expanduser()
        log_path = output_path.with_suffix(".codex_self_mcp.jsonl")
        prompt = _codex_self_prompt(request)
        plan = self.adapter.build_call_plan(
            prompt=prompt,
            cwd=output_path.parent,
            sandbox="read-only",
            approval_policy="never",
            timeout_seconds=self.timeout_seconds,
            log_path=log_path,
            extract_last_image_to=output_path,
        )
        run_result = self.adapter.run_call_plan(plan)
        issues = list(run_result.issues)
        if not run_result.ok:
            return ConceptImageBackendGenerationResult(
                ok=False,
                backend=self.backend_name,
                output_image_path=str(output_path) if output_path.exists() else None,
                issues=issues or ["codex_self_mcp_generation_failed"],
                raw_summary={"returncode": run_result.returncode, "log_path": str(log_path)},
            )
        if not output_path.exists():
            issues.append("codex_self_mcp_missing_extracted_image")
        return ConceptImageBackendGenerationResult(
            ok=not issues,
            backend=self.backend_name,
            output_image_path=str(output_path) if output_path.exists() else None,
            issues=issues,
            raw_summary={"returncode": run_result.returncode, "log_path": str(log_path)},
        )


class CodexSelfMCPImage2ConceptBackend(ConceptImageBackend):
    """Codex-self backend that uses child-agent ``view_image`` before generation."""

    backend_name = "codex_self_mcp_image2"

    def __init__(
        self,
        adapter: CodexSelfMCPAdapter | None = None,
        *,
        timeout_seconds: float = 900,
        verify_view_image: bool = False,
        probe_dir: str | Path | None = None,
    ) -> None:
        self.adapter = adapter or CodexSelfMCPAdapter()
        self.image2 = CodexSelfMCPImage2Adapter(self.adapter, timeout_seconds=timeout_seconds)
        self.verify_view_image = verify_view_image
        self.probe_dir = Path(probe_dir).expanduser().resolve() if probe_dir is not None else None

    def capability(self) -> ConceptImageBackendCapability:
        status = self.adapter.status(run_smoke=False)
        issues = list(status.issues)
        view_image_ok = bool(status.ok)
        probe_log_path = None
        if status.ok and self.verify_view_image:
            probe = self.image2.run_view_image_canary(probe_dir=self.probe_dir or Path("/tmp/codex_self_mcp_image2_probe"))
            view_image_ok = bool(probe.get("ok"))
            probe_log_path = str(probe.get("log_path") or "") or None
            issues.extend(probe.get("issues") or [])
        return ConceptImageBackendCapability(
            backend_name=self.backend_name,
            text_to_image=bool(status.ok),
            image_guided_single_reference=view_image_ok,
            multi_image_composite=view_image_ok,
            output_extraction=status.client_script_exists,
            structured_file_attachments=view_image_ok,
            native_images_parameter=False,
            agent_view_image_reference=view_image_ok,
            agent_view_image_then_generate=view_image_ok,
            probe_log_path=probe_log_path,
            issues=_unique(issues),
        )

    def generate(self, request: ConceptImageBackendGenerationRequest) -> ConceptImageBackendGenerationResult:
        result = self.image2.generate(
            prompt=request.prompt,
            attachments=request.attachment_manifest,
            output_path=request.output_path,
            requirement_id=request.requirement_id,
            output_type=request.output_type,
            generation_mode=request.generation_mode,
            negative_prompt=request.negative_prompt,
        )
        return ConceptImageBackendGenerationResult(
            ok=result.ok,
            backend=self.backend_name,
            output_image_path=result.output_path,
            issues=list(result.issues),
            raw_summary={
                "log_path": result.log_path,
                "viewed_image_paths": result.viewed_image_paths,
                "view_image_payload_paths": result.view_image_payload_paths,
                "image_generation_count": result.image_generation_count,
                "evidence": result.evidence,
            },
        )


def execute_concept_image_handoff(
    *,
    run_dir: str | Path,
    handoff_payload: dict[str, Any],
    backend: ConceptImageBackend,
    handoff_id: str | None = None,
    dry_run: bool = False,
) -> ConceptImageExecutionResult:
    """Run concept-generation requirements in handoff execution order."""

    path = Path(run_dir).expanduser().resolve()
    calls_path = path / "live_generation_calls.jsonl"
    output_dir = path / "runtime_worker" / "live_image"
    output_dir.mkdir(parents=True, exist_ok=True)
    capability = backend.capability()
    concept_generation = handoff_payload.get("concept_generation")
    if not isinstance(concept_generation, dict):
        issue = "missing_concept_generation_handoff_payload"
        return ConceptImageExecutionResult(
            ok=False,
            run_dir=str(path),
            backend=capability.backend_name,
            status="failed",
            live_generation_calls_jsonl=str(calls_path),
            issues=[issue],
            capability=_model_to_dict(capability),
        )

    requirements = _requirements_in_order(concept_generation)
    concept_version = _positive_int(concept_generation.get("concept_version"))
    preflight_issues = _handoff_backend_selection_issues(capability, requirements)
    generated_paths: dict[str, str] = {}
    image_results: list[dict[str, Any]] = []
    records: list[ConceptImageExecutionCallRecord] = []
    issues: list[str] = list(preflight_issues)

    for index, requirement in enumerate(requirements, start=1):
        record, image_result = _execute_requirement(
            path=path,
            output_dir=output_dir,
            requirement=requirement,
            index=index,
            concept_version=concept_version,
            backend=backend,
            capability=capability,
            generated_paths=generated_paths,
            preflight_issues=preflight_issues,
            dry_run=dry_run,
        )
        _append_jsonl(calls_path, _model_to_dict(record))
        records.append(record)
        if image_result is not None:
            image_results.append(image_result)
            generated_paths[record.requirement_id] = image_result["image_path"]
        if record.issues:
            issues.extend(record.issues)

    ok = bool(records) and all(record.ok for record in records)
    status: Literal["completed", "blocked", "dry_run", "failed"]
    if dry_run:
        status = "dry_run"
    elif ok:
        status = "completed"
    elif records:
        status = "blocked"
    else:
        status = "failed"
    return ConceptImageExecutionResult(
        ok=ok,
        run_dir=str(path),
        backend=capability.backend_name,
        status=status,
        image_results=image_results,
        call_records=records,
        live_generation_calls_jsonl=str(calls_path),
        issues=_unique(issues),
        capability=_model_to_dict(capability),
    )


def _execute_requirement(
    *,
    path: Path,
    output_dir: Path,
    requirement: dict[str, Any],
    index: int,
    concept_version: int | None,
    backend: ConceptImageBackend,
    capability: ConceptImageBackendCapability,
    generated_paths: dict[str, str],
    preflight_issues: list[str],
    dry_run: bool,
) -> tuple[ConceptImageExecutionCallRecord, dict[str, Any] | None]:
    requirement_id = str(requirement.get("requirement_id") or f"requirement_{index:03d}")
    output_type = _output_type(requirement.get("output_type"))
    generation_mode = _generation_mode(requirement.get("generation_mode"))
    input_reference_ids = _string_list(requirement.get("input_reference_image_ids"))
    input_paths, input_issues = _resolved_input_paths(requirement)
    source_ids = _string_list(requirement.get("source_requirement_ids"))
    source_paths = [generated_paths[source_id] for source_id in source_ids if source_id in generated_paths]
    missing_sources = [source_id for source_id in source_ids if source_id not in generated_paths]
    prompt = str(requirement.get("prompt") or "")
    attachment_manifest = build_attachment_manifest(
        input_reference_image_ids=input_reference_ids,
        input_image_paths=input_paths,
        source_requirement_ids=source_ids,
        source_image_paths=source_paths,
        output_type=output_type,
    )
    started_at = utc_now_iso()
    round_output_dir = output_dir / (f"v{concept_version:02d}" if concept_version is not None else "unversioned")
    artifact_id = _concept_artifact_id(requirement_id=requirement_id, concept_version=concept_version)
    output_path = round_output_dir / f"{index:02d}_{_safe_name(requirement_id)}.png"
    attachment_manifest, view_prep_issues = prepare_viewable_attachment_manifest(
        attachment_manifest,
        view_dir=round_output_dir / "reference_views" / _safe_name(requirement_id),
    )
    issues = list(preflight_issues)
    issues.extend(input_issues)
    issues.extend(view_prep_issues)
    issues.extend(f"missing_source_requirement_output:{source_id}" for source_id in missing_sources)
    issues.extend(_capability_issues(capability, generation_mode, input_paths=input_paths, source_paths=source_paths))
    if bool(requirement.get("must_use_image_inputs")) and not input_paths and not source_paths:
        issues.append(f"required_image_inputs_missing:{requirement_id}")
    if dry_run:
        issues.append("live_image_executor_dry_run_no_generation")

    record = ConceptImageExecutionCallRecord(
        requirement_id=requirement_id,
        concept_version=concept_version,
        output_type=output_type,
        generation_mode=generation_mode,
        prompt=prompt,
        input_reference_image_ids=input_reference_ids,
        input_image_paths=input_paths,
        source_requirement_ids=source_ids,
        source_image_paths=source_paths,
        attachment_manifest=[_model_to_dict(item) for item in attachment_manifest],
        backend=capability.backend_name,
        started_at=started_at,
        artifact_id=artifact_id,
        issues=_unique(issues),
    )
    if issues:
        record.finished_at = utc_now_iso()
        return record, None

    generation_request = ConceptImageBackendGenerationRequest(
        requirement_id=requirement_id,
        output_type=output_type,
        generation_mode=generation_mode,
        prompt=prompt,
        negative_prompt=requirement.get("negative_prompt"),
        input_reference_image_ids=input_reference_ids,
        input_image_paths=input_paths,
        source_requirement_ids=source_ids,
        source_image_paths=source_paths,
        attachment_manifest=attachment_manifest,
        output_path=str(output_path),
        metadata={"run_dir": str(path), "requirement": requirement},
    )
    generated = backend.generate(generation_request)
    record.backend = generated.backend or capability.backend_name
    record.finished_at = utc_now_iso()
    record.output_image_path = generated.output_image_path
    record.issues = _unique(list(generated.issues))
    record.ok = bool(generated.ok and generated.output_image_path and Path(generated.output_image_path).exists())
    if not record.ok and not record.issues:
        record.issues = ["concept_image_backend_returned_no_output"]
    if not record.ok:
        return record, None

    image_result = {
        "image_path": str(Path(generated.output_image_path).expanduser().resolve()),
        "subject_id": requirement.get("target_id") if output_type == "subject_concept" else None,
        "output_type": output_type,
        "requirement_id": requirement_id,
        "target_id": requirement.get("target_id"),
        "artifact_id": artifact_id,
        "final_preview": output_type == "target_render",
        "metadata": {
            "concept_version": concept_version,
            "generation_mode": generation_mode,
            "backend": record.backend,
            "input_reference_image_ids": input_reference_ids,
            "input_image_paths": input_paths,
            "source_requirement_ids": source_ids,
            "source_image_paths": source_paths,
            "attachment_manifest": [_model_to_dict(item) for item in attachment_manifest],
            "prompt_key": requirement.get("prompt_key"),
        },
    }
    return record, image_result


def _requirements_in_order(concept_generation: dict[str, Any]) -> list[dict[str, Any]]:
    raw_requirements = [item for item in concept_generation.get("requirements") or [] if isinstance(item, dict)]
    by_id = {str(item.get("requirement_id")): item for item in raw_requirements if item.get("requirement_id")}
    ordered = []
    seen = set()
    for requirement_id in _string_list(concept_generation.get("execution_order")):
        item = by_id.get(requirement_id)
        if item is not None:
            ordered.append(item)
            seen.add(requirement_id)
    ordered.extend(item for item in raw_requirements if item.get("requirement_id") not in seen)
    return ordered


def _handoff_backend_selection_issues(
    capability: ConceptImageBackendCapability,
    requirements: list[dict[str, Any]],
) -> list[str]:
    needs_image_guided = any(
        _generation_mode(requirement.get("generation_mode")) == "image_guided"
        and (
            bool(requirement.get("must_use_image_inputs"))
            or bool(requirement.get("input_reference_image_ids"))
            or bool(requirement.get("resolved_input_images"))
        )
        for requirement in requirements
    )
    needs_multi_image = any(
        _generation_mode(requirement.get("generation_mode")) == "multi_image_composite"
        for requirement in requirements
    )
    issues = []
    if needs_image_guided and not capability.image_guided_single_reference:
        issues.append(f"backend_missing_required_image_guided_support:{capability.backend_name}")
    if needs_multi_image and not capability.multi_image_composite:
        issues.append(f"backend_missing_required_multi_image_composite_support:{capability.backend_name}")
    if (needs_image_guided or needs_multi_image) and not capability.structured_file_attachments:
        issues.append(f"backend_missing_structured_file_attachment_support:{capability.backend_name}")
    return _unique(issues)


def _resolved_input_paths(requirement: dict[str, Any]) -> tuple[list[str], list[str]]:
    paths = []
    issues = []
    for image in requirement.get("resolved_input_images") or []:
        if not isinstance(image, dict):
            continue
        image_id = str(image.get("image_id") or "unknown_image")
        uri = image.get("uri")
        if not uri:
            issues.append(f"missing_input_reference_file:{image_id}")
            continue
        image_path = Path(str(uri)).expanduser()
        if not image_path.exists():
            issues.append(f"missing_input_reference_file:{image_id}:{image_path}")
            continue
        paths.append(str(image_path.resolve()))
    return paths, issues


def _capability_issues(
    capability: ConceptImageBackendCapability,
    generation_mode: ConceptGenerationMode,
    *,
    input_paths: list[str],
    source_paths: list[str],
) -> list[str]:
    if generation_mode == "text_to_image":
        return [] if capability.text_to_image else [f"backend_does_not_support_text_to_image:{capability.backend_name}"]
    if generation_mode == "image_guided":
        if input_paths and capability.image_guided_single_reference:
            return []
        return [f"backend_does_not_support_image_guided_inputs:{capability.backend_name}"]
    if generation_mode == "multi_image_composite":
        if source_paths and capability.multi_image_composite:
            return []
        return [f"backend_does_not_support_multi_image_composite:{capability.backend_name}"]
    return [f"unsupported_generation_mode:{generation_mode}"]


def _codex_self_prompt(request: ConceptImageBackendGenerationRequest) -> str:
    payload = {
        "requirement_id": request.requirement_id,
        "output_type": request.output_type,
        "generation_mode": request.generation_mode,
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "quality_boundary": "Generate exactly one concept image. Do not run repo commands.",
    }
    return "Generate one image for the following structured concept request:\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _output_type(value: Any) -> ConceptOutputType:
    if value in {"scene_concept", "target_render"}:
        return value
    return "subject_concept"


def _generation_mode(value: Any) -> ConceptGenerationMode:
    if value in {"image_guided", "multi_image_composite"}:
        return value
    return "text_to_image"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _concept_artifact_id(*, requirement_id: str, concept_version: int | None) -> str:
    safe_requirement = _safe_name(requirement_id)
    if concept_version is None or concept_version <= 1:
        return f"live_{safe_requirement}"
    return f"live_v{concept_version}_{safe_requirement}"


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned[:96] or "concept_image"


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
