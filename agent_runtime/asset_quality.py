"""Subject-asset quality checks for the V1 runtime.

The evaluator keeps the cheap deterministic checks local and reuses the
existing render-preview script through the domain dispatcher when a Blender
preview is requested. It does not introduce another renderer or store binary
payloads in graph state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from agent_runtime.artifacts import FileArtifactStore, utc_now_iso
from agent_runtime.domain_dispatcher import ScriptDomainToolDispatcher
from agent_runtime.state import AgentProjectState, ArtifactType, Asset3DRecord
from agent_runtime.state_views import apply_state_updates
from agent_runtime.tool_executor import CommandExecutionOptions


QualityStatus = Literal["pass", "fail", "uncertain"]
SuggestedAction = Literal["accept", "rerun_hunyuan3d", "regenerate_subject_image", "ask_user", "manual_review"]
RepairAction = Literal["accept", "retry_hunyuan3d", "regenerate_subject_image", "ask_user", "manual_review"]
VisualQARunner = Callable[[Path, Path], dict[str, Any] | BaseModel]


class SubjectAssetQualityResult(BaseModel):
    asset_id: str
    subject_id: str
    source_image_id: str
    status: QualityStatus
    score: float
    issues: list[str] = Field(default_factory=list)
    suggested_action: SuggestedAction
    checks: dict[str, Any] = Field(default_factory=dict)
    visual_qa: dict[str, Any] | None = None
    preview_artifact_id: str | None = None
    preview_blend_artifact_id: str | None = None
    render_tool_call_id: str | None = None
    checked_at: str


class SubjectAssetRepairDecision(BaseModel):
    asset_id: str
    subject_id: str
    source_image_id: str
    quality_status: QualityStatus
    quality_score: float
    action: RepairAction
    reason: str
    retry_count: int = 0
    max_hunyuan_retries: int = 1
    concept_regen_count: int = 0
    max_concept_regens: int = 1
    user_visible: bool = False
    next_stage: str | None = None
    issues: list[str] = Field(default_factory=list)
    created_at: str


def evaluate_subject_asset(
    *,
    state: AgentProjectState,
    asset: Asset3DRecord,
    artifact_store: FileArtifactStore,
    root: str | Path | None = None,
    output_dir: str | Path | None = None,
    blender_path: str | Path | None = None,
    render_preview: bool = False,
    dry_run: bool = False,
    timeout_seconds: float = 180,
    min_size_bytes: int = 12,
    visual_qa_result: dict[str, Any] | BaseModel | None = None,
    source_image_path: str | Path | None = None,
    visual_qa_runner: VisualQARunner | None = None,
) -> tuple[SubjectAssetQualityResult, AgentProjectState]:
    glb_path = Path(asset.glb_uri).expanduser().resolve() if asset.glb_uri else None
    checks = _check_glb_file(glb_path, min_size_bytes=min_size_bytes)
    issues = list(checks["issues"])
    preview_artifact_id = asset.preview_image_id
    preview_blend_artifact_id = None
    render_tool_call_id = None
    preview_image_path_for_visual = None

    if render_preview:
        if root is None or output_dir is None:
            issues.append("preview_render_config_missing")
        elif glb_path is None or issues:
            issues.append("preview_render_skipped_due_to_asset_file_failure")
        else:
            render_result = _render_asset_preview(
                state=state,
                artifact_store=artifact_store,
                root=root,
                asset=asset,
                glb_path=glb_path,
                output_dir=output_dir,
                blender_path=blender_path,
                timeout_seconds=timeout_seconds,
                dry_run=dry_run,
            )
            state = render_result["state"]
            render_tool_call_id = render_result["tool_call_id"]
            preview_artifact_id = render_result["preview_artifact_id"] or preview_artifact_id
            preview_blend_artifact_id = render_result["preview_blend_artifact_id"]
            if not render_result["ok"]:
                issues.append("preview_render_failed")
            elif dry_run:
                issues.append("preview_render_dry_run")
            checks["preview_render"] = render_result["summary"]
            preview_path = render_result["summary"].get("preview_png")
            if render_result["ok"] and not dry_run and preview_path and Path(preview_path).exists():
                preview_image_path_for_visual = Path(preview_path)

    visual_qa_payload = _model_to_dict(visual_qa_result) if visual_qa_result is not None else None
    if visual_qa_payload is None and visual_qa_runner is not None:
        if source_image_path is None or preview_image_path_for_visual is None:
            issues.append("visual_qa_skipped_missing_images")
        else:
            visual_qa_payload = _model_to_dict(
                visual_qa_runner(Path(source_image_path).expanduser().resolve(), preview_image_path_for_visual)
            )
    if visual_qa_payload is not None:
        checks["visual_qa"] = visual_qa_payload
        _merge_visual_qa_issues(issues, visual_qa_payload)

    status, suggested_action, score = _quality_decision(issues)
    if visual_qa_payload is not None:
        status, suggested_action, score = _merge_visual_qa_decision(
            status,
            suggested_action,
            score,
            visual_qa_payload,
        )
    updated_asset = _asset_with_quality(
        asset,
        result_status=status,
        score=score,
        issues=issues,
        suggested_action=suggested_action,
        preview_artifact_id=preview_artifact_id,
    )
    state = apply_state_updates(
        state,
        node_name="SubjectAssetQualityEvaluator",
        updates={"subject_assets": _replace_asset(state.subject_assets, updated_asset)},
    )
    result = SubjectAssetQualityResult(
        asset_id=asset.asset_id,
        subject_id=asset.subject_id,
        source_image_id=asset.source_image_id,
        status=status,
        score=score,
        issues=issues,
        suggested_action=suggested_action,
        checks=checks,
        visual_qa=visual_qa_payload,
        preview_artifact_id=preview_artifact_id,
        preview_blend_artifact_id=preview_blend_artifact_id,
        render_tool_call_id=render_tool_call_id,
        checked_at=utc_now_iso(),
    )
    return result, state


def plan_subject_asset_repair(
    quality_result: SubjectAssetQualityResult,
    *,
    retry_count: int = 0,
    max_hunyuan_retries: int = 1,
    concept_regen_count: int = 0,
    max_concept_regens: int = 1,
    user_requested_review: bool = False,
) -> SubjectAssetRepairDecision:
    """Decide the next step after subject-asset QA without triggering it."""

    if user_requested_review:
        action: RepairAction = "ask_user"
        reason = "user_requested_review"
        user_visible = True
        next_stage = "USER_REVIEW"
    elif quality_result.status == "pass" and quality_result.suggested_action == "accept":
        action = "accept"
        reason = "quality_passed"
        user_visible = False
        next_stage = "BLENDER_ASSEMBLY_PLANNING"
    elif quality_result.status == "uncertain" or quality_result.suggested_action in {"ask_user", "manual_review"}:
        action = "ask_user" if quality_result.suggested_action == "ask_user" else "manual_review"
        reason = "quality_uncertain_requires_review"
        user_visible = True
        next_stage = "USER_REVIEW" if action == "ask_user" else "MANUAL_REVIEW"
    elif _should_regenerate_subject_image(quality_result.issues):
        if concept_regen_count < max_concept_regens:
            action = "regenerate_subject_image"
            reason = "semantic_or_shape_failure"
            user_visible = False
            next_stage = "CONCEPT_GENERATION"
        else:
            action = "manual_review"
            reason = "concept_regen_budget_exhausted"
            user_visible = True
            next_stage = "MANUAL_REVIEW"
    elif retry_count < max_hunyuan_retries:
        action = "retry_hunyuan3d"
        reason = "quality_failed_retry_available"
        user_visible = False
        next_stage = "SUBJECT_ASSET_GENERATION"
    else:
        action = "manual_review"
        reason = "hunyuan_retry_budget_exhausted"
        user_visible = True
        next_stage = "MANUAL_REVIEW"

    return SubjectAssetRepairDecision(
        asset_id=quality_result.asset_id,
        subject_id=quality_result.subject_id,
        source_image_id=quality_result.source_image_id,
        quality_status=quality_result.status,
        quality_score=quality_result.score,
        action=action,
        reason=reason,
        retry_count=retry_count,
        max_hunyuan_retries=max_hunyuan_retries,
        concept_regen_count=concept_regen_count,
        max_concept_regens=max_concept_regens,
        user_visible=user_visible,
        next_stage=next_stage,
        issues=list(quality_result.issues),
        created_at=utc_now_iso(),
    )


def apply_subject_asset_repair_decision(
    *,
    state: AgentProjectState,
    asset_id: str,
    decision: SubjectAssetRepairDecision,
) -> AgentProjectState:
    updated_assets = []
    for asset in state.subject_assets:
        if asset.asset_id != asset_id:
            updated_assets.append(asset)
            continue
        payload = _model_to_dict(asset)
        generation_params = dict(payload.get("generation_params") or {})
        generation_params["repair_decision"] = _model_to_dict(decision)
        payload["generation_params"] = generation_params
        if decision.action in {"retry_hunyuan3d", "regenerate_subject_image"}:
            payload["status"] = "needs_regen"
        elif decision.action in {"ask_user", "manual_review"}:
            payload["status"] = "uncertain"
        elif decision.action == "accept":
            payload["status"] = "succeeded"
        updated_assets.append(Asset3DRecord(**payload))
    return apply_state_updates(
        state,
        node_name="SubjectAssetRepairRouter",
        updates={"subject_assets": updated_assets},
    )


def quality_result_from_asset(asset: Asset3DRecord) -> SubjectAssetQualityResult | None:
    quality = (asset.generation_params or {}).get("quality")
    if not isinstance(quality, dict):
        return None
    status = quality.get("status")
    if status not in {"pass", "fail", "uncertain"}:
        return None
    suggested_action = quality.get("suggested_action") or "manual_review"
    if suggested_action not in {"accept", "rerun_hunyuan3d", "regenerate_subject_image", "ask_user", "manual_review"}:
        suggested_action = "manual_review"
    return SubjectAssetQualityResult(
        asset_id=asset.asset_id,
        subject_id=asset.subject_id,
        source_image_id=asset.source_image_id,
        status=status,
        score=float(asset.quality_score if asset.quality_score is not None else 0.0),
        issues=[str(item) for item in quality.get("issues", []) or []],
        suggested_action=suggested_action,
        checks={},
        checked_at=quality.get("checked_at") or utc_now_iso(),
    )


def _check_glb_file(glb_path: Path | None, *, min_size_bytes: int) -> dict[str, Any]:
    issues: list[str] = []
    checks: dict[str, Any] = {
        "glb_uri": str(glb_path) if glb_path is not None else None,
        "exists": False,
        "is_file": False,
        "size_bytes": None,
        "glb_magic": None,
        "glb_version": None,
        "declared_length": None,
        "issues": issues,
    }
    if glb_path is None:
        issues.append("missing_glb_uri")
        return checks
    if not glb_path.exists():
        issues.append("missing_file")
        return checks
    checks["exists"] = True
    if not glb_path.is_file():
        issues.append("not_a_file")
        return checks
    checks["is_file"] = True
    size_bytes = glb_path.stat().st_size
    checks["size_bytes"] = size_bytes
    if size_bytes < min_size_bytes:
        issues.append("file_too_small")
        return checks
    with glb_path.open("rb") as handle:
        header = handle.read(12)
    magic = header[:4]
    checks["glb_magic"] = magic.decode("ascii", errors="replace")
    if magic != b"glTF":
        issues.append("invalid_glb_magic")
        return checks
    version = int.from_bytes(header[4:8], "little")
    declared_length = int.from_bytes(header[8:12], "little")
    checks["glb_version"] = version
    checks["declared_length"] = declared_length
    if version != 2:
        issues.append("unsupported_glb_version")
    if declared_length != size_bytes:
        issues.append("glb_length_mismatch")
    return checks


def _render_asset_preview(
    *,
    state: AgentProjectState,
    artifact_store: FileArtifactStore,
    root: str | Path,
    asset: Asset3DRecord,
    glb_path: Path,
    output_dir: str | Path,
    blender_path: str | Path | None,
    timeout_seconds: float,
    dry_run: bool,
) -> dict[str, Any]:
    preview_dir = Path(output_dir).expanduser().resolve()
    preview_png = preview_dir / f"{asset.asset_id}_qa_preview.png"
    preview_blend = preview_dir / f"{asset.asset_id}_qa_preview.blend"
    result = ScriptDomainToolDispatcher(
        state=state,
        root=root,
        blender_path=blender_path,
    ).dispatch(
        "render_preview",
        {
            "input_glb": str(glb_path),
            "preview_png": str(preview_png),
            "preview_blend": str(preview_blend),
        },
        options=CommandExecutionOptions(timeout_seconds=timeout_seconds, dry_run=dry_run),
    )
    preview_artifact_id = None
    preview_blend_artifact_id = None
    if result.ok and not dry_run and preview_png.exists():
        preview_artifact_id = f"{asset.asset_id}_qa_preview_png"
        state.artifacts.append(
            artifact_store.register_file(
                preview_png,
                ArtifactType.BLENDER_PREVIEW_RENDER,
                artifact_id=preview_artifact_id,
                semantic_role="subject_asset_quality_preview",
                metadata={"stage": "subject_asset_qa", "asset_id": asset.asset_id},
            )
        )
    if result.ok and not dry_run and preview_blend.exists():
        preview_blend_artifact_id = f"{asset.asset_id}_qa_preview_blend"
        state.artifacts.append(
            artifact_store.register_file(
                preview_blend,
                ArtifactType.BLENDER_FILE,
                artifact_id=preview_blend_artifact_id,
                semantic_role="subject_asset_quality_preview_blend",
                metadata={"stage": "subject_asset_qa", "asset_id": asset.asset_id},
            )
        )
    return {
        "ok": result.ok,
        "state": state,
        "tool_call_id": result.tool_call_id,
        "preview_artifact_id": preview_artifact_id,
        "preview_blend_artifact_id": preview_blend_artifact_id,
        "summary": {
            "ok": result.ok,
            "dry_run": dry_run,
            "tool_call_status": result.tool_call_status,
            "tool_call_id": result.tool_call_id,
            "preview_png": str(preview_png),
            "preview_png_exists": preview_png.exists(),
            "preview_blend": str(preview_blend),
            "preview_blend_exists": preview_blend.exists(),
        },
    }


def _quality_decision(issues: list[str]) -> tuple[QualityStatus, SuggestedAction, float]:
    hard_failures = {
        "missing_glb_uri",
        "missing_file",
        "not_a_file",
        "file_too_small",
        "invalid_glb_magic",
        "unsupported_glb_version",
        "glb_length_mismatch",
    }
    if any(issue in hard_failures for issue in issues):
        return "fail", "rerun_hunyuan3d", 0.0
    if issues:
        return "uncertain", "ask_user", 0.5
    return "pass", "accept", 1.0


def _merge_visual_qa_issues(issues: list[str], visual_qa: dict[str, Any]) -> None:
    status = visual_qa.get("status")
    ok = visual_qa.get("ok", True)
    if ok is False:
        issues.append("visual_qa_provider_failed")
    elif status == "fail":
        issues.append("visual_similarity_failed")
    elif status == "uncertain":
        issues.append("visual_similarity_uncertain")
    for issue in visual_qa.get("issues", []) or []:
        issue_text = str(issue)
        if issue_text and issue_text not in issues:
            issues.append(issue_text)


def _merge_visual_qa_decision(
    status: QualityStatus,
    suggested_action: SuggestedAction,
    score: float,
    visual_qa: dict[str, Any],
) -> tuple[QualityStatus, SuggestedAction, float]:
    visual_status = visual_qa.get("status")
    visual_score = visual_qa.get("score")
    if isinstance(visual_score, int | float):
        score = min(score, max(0.0, min(1.0, float(visual_score))))
    if visual_status == "fail":
        issues = visual_qa.get("issues", []) or []
        if any(str(issue) in {"wrong_shape", "wrong_color", "wrong_subject", "semantic_mismatch"} for issue in issues):
            return "fail", "regenerate_subject_image", score
        return "fail", "rerun_hunyuan3d", score
    if visual_status == "uncertain" and status == "pass":
        return "uncertain", "ask_user", score
    return status, suggested_action, score


def _should_regenerate_subject_image(issues: list[str]) -> bool:
    semantic_or_shape_issues = {
        "visual_similarity_failed",
        "wrong_shape",
        "wrong_color",
        "wrong_subject",
        "semantic_mismatch",
    }
    return any(issue in semantic_or_shape_issues for issue in issues)


def _asset_with_quality(
    asset: Asset3DRecord,
    *,
    result_status: QualityStatus,
    score: float,
    issues: list[str],
    suggested_action: SuggestedAction,
    preview_artifact_id: str | None,
) -> Asset3DRecord:
    payload = _model_to_dict(asset)
    payload["status"] = _asset_status_for_quality(result_status)
    payload["quality_score"] = score
    payload["quality_notes"] = "; ".join(issues) if issues else "subject asset quality checks passed"
    payload["preview_image_id"] = preview_artifact_id
    generation_params = dict(payload.get("generation_params") or {})
    generation_params["quality"] = {
        "status": result_status,
        "issues": list(issues),
        "suggested_action": suggested_action,
        "checked_at": utc_now_iso(),
    }
    payload["generation_params"] = generation_params
    return Asset3DRecord(**payload)


def _asset_status_for_quality(result_status: QualityStatus) -> str:
    if result_status == "pass":
        return "succeeded"
    if result_status == "uncertain":
        return "uncertain"
    return "needs_regen"


def _replace_asset(existing: list[Asset3DRecord], updated_asset: Asset3DRecord) -> list[Asset3DRecord]:
    replaced = False
    output = []
    for item in existing:
        if item.asset_id == updated_asset.asset_id:
            output.append(updated_asset)
            replaced = True
        else:
            output.append(item)
    if not replaced:
        output.append(updated_asset)
    return output


def _model_to_dict(model) -> dict:
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
