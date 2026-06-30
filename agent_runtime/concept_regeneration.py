"""ReviewPatch consumers for concept image regeneration.

The helpers here bridge structured user feedback back into the existing
ConceptBundle/artifact state path. They do not call an image model directly:
dry-run mode records the regeneration plan, and non-dry-run mode registers an
already produced subject concept image as the result of that plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.artifacts import FileArtifactStore
from agent_runtime.state import (
    AgentProjectState,
    ArtifactType,
    ConceptBundle,
    ReviewPatch,
    WorkflowPhase,
)
from agent_runtime.state_views import apply_state_updates


class ReviewPatchConceptRegenerationResult(BaseModel):
    ok: bool
    status: Literal["planned", "applied", "blocked"]
    dry_run: bool
    patch_id: str | None = None
    patch_type: str | None = None
    target_subject_id: str | None = None
    instruction: str | None = None
    previous_image_ids: list[str] = Field(default_factory=list)
    generated_image_artifact_id: str | None = None
    generated_image_uri: str | None = None
    invalidated_asset_ids: list[str] = Field(default_factory=list)
    marked_patch_applied: bool = False
    next_phase: WorkflowPhase | None = None
    issues: list[str] = Field(default_factory=list)
    plan: dict[str, Any] = Field(default_factory=dict)


def apply_review_patch_concept_regeneration(
    *,
    state: AgentProjectState,
    artifact_store: FileArtifactStore | None = None,
    patch_id: str | None = None,
    generated_image_path: str | Path | None = None,
    generated_image_artifact_id: str | None = None,
    dry_run: bool = True,
    copy_into_store: bool = True,
) -> tuple[ReviewPatchConceptRegenerationResult, AgentProjectState]:
    """Consume one pending subject ReviewPatch into the concept-image path.

    In dry-run mode, no artifact is registered and the ReviewPatch remains
    pending. In non-dry-run mode the caller must provide a generated image file;
    this function registers that file as a SUBJECT_CONCEPT_IMAGE, updates the
    subject's ConceptBundle image list, and marks the patch as applied.
    """

    patch = _select_pending_subject_patch(state.review_patches, patch_id=patch_id)
    if patch is None:
        return (
            ReviewPatchConceptRegenerationResult(
                ok=False,
                status="blocked",
                dry_run=dry_run,
                patch_id=patch_id,
                issues=[_missing_patch_issue(state.review_patches, patch_id=patch_id)],
                next_phase=state.phase,
            ),
            state,
        )

    validation_issues = _validate_subject_patch(patch)
    subject_id = patch.target_id
    previous_image_ids = _previous_subject_images(state, subject_id)
    invalidated_asset_ids = _invalidated_asset_ids(patch)
    plan = _build_regeneration_plan(
        patch=patch,
        previous_image_ids=previous_image_ids,
        invalidated_asset_ids=invalidated_asset_ids,
    )
    if validation_issues:
        return (
            ReviewPatchConceptRegenerationResult(
                ok=False,
                status="blocked",
                dry_run=dry_run,
                patch_id=patch.patch_id,
                patch_type=patch.patch_type,
                target_subject_id=subject_id,
                instruction=patch.instruction,
                previous_image_ids=previous_image_ids,
                invalidated_asset_ids=invalidated_asset_ids,
                issues=validation_issues,
                next_phase=state.phase,
                plan=plan,
            ),
            state,
        )

    if dry_run:
        updated_state = apply_state_updates(
            state,
            node_name="ImageGenerationExecutor",
            updates={"phase": WorkflowPhase.CONCEPT_GENERATION},
        )
        return (
            ReviewPatchConceptRegenerationResult(
                ok=True,
                status="planned",
                dry_run=True,
                patch_id=patch.patch_id,
                patch_type=patch.patch_type,
                target_subject_id=subject_id,
                instruction=patch.instruction,
                previous_image_ids=previous_image_ids,
                invalidated_asset_ids=invalidated_asset_ids,
                next_phase=WorkflowPhase.CONCEPT_GENERATION,
                plan=plan,
            ),
            updated_state,
        )

    if generated_image_path is None:
        return (
            ReviewPatchConceptRegenerationResult(
                ok=False,
                status="blocked",
                dry_run=False,
                patch_id=patch.patch_id,
                patch_type=patch.patch_type,
                target_subject_id=subject_id,
                instruction=patch.instruction,
                previous_image_ids=previous_image_ids,
                invalidated_asset_ids=invalidated_asset_ids,
                issues=["missing_generated_image_path"],
                next_phase=WorkflowPhase.CONCEPT_GENERATION,
                plan=plan,
            ),
            state,
        )
    if artifact_store is None:
        return (
            ReviewPatchConceptRegenerationResult(
                ok=False,
                status="blocked",
                dry_run=False,
                patch_id=patch.patch_id,
                patch_type=patch.patch_type,
                target_subject_id=subject_id,
                instruction=patch.instruction,
                previous_image_ids=previous_image_ids,
                invalidated_asset_ids=invalidated_asset_ids,
                issues=["artifact_store_required"],
                next_phase=WorkflowPhase.CONCEPT_GENERATION,
                plan=plan,
            ),
            state,
        )

    artifact_id = generated_image_artifact_id or f"{subject_id}_concept_{uuid4().hex[:12]}"
    if artifact_id in state.artifact_ids():
        return (
            ReviewPatchConceptRegenerationResult(
                ok=False,
                status="blocked",
                dry_run=False,
                patch_id=patch.patch_id,
                patch_type=patch.patch_type,
                target_subject_id=subject_id,
                instruction=patch.instruction,
                previous_image_ids=previous_image_ids,
                invalidated_asset_ids=invalidated_asset_ids,
                issues=[f"duplicate_artifact_id:{artifact_id}"],
                next_phase=WorkflowPhase.CONCEPT_GENERATION,
                plan=plan,
            ),
            state,
        )

    artifact = artifact_store.register_file(
        generated_image_path,
        ArtifactType.SUBJECT_CONCEPT_IMAGE,
        semantic_role="subject_concept_image",
        artifact_id=artifact_id,
        copy_into_store=copy_into_store,
        metadata={
            "stage": "review_patch_concept_regeneration",
            "patch_id": patch.patch_id,
            "target_subject_id": subject_id,
            "patch_type": patch.patch_type,
            "previous_image_ids": previous_image_ids,
            "invalidated_asset_ids": invalidated_asset_ids,
            "instruction": patch.instruction,
        },
    )
    concept_bundle = _concept_bundle_with_generated_subject_image(
        state.concept_bundle,
        subject_id=subject_id or "",
        artifact_id=artifact.artifact_id,
    )
    updated_patches = [
        _copy_model(item, status="applied") if item.patch_id == patch.patch_id else item
        for item in state.review_patches
    ]
    updated_state = apply_state_updates(
        state,
        node_name="ImageGenerationExecutor",
        updates={
            "artifacts": [*state.artifacts, artifact],
            "concept_bundle": concept_bundle,
            "review_patches": updated_patches,
            "phase": WorkflowPhase.SUBJECT_ASSET_GENERATION,
        },
    )
    return (
        ReviewPatchConceptRegenerationResult(
            ok=True,
            status="applied",
            dry_run=False,
            patch_id=patch.patch_id,
            patch_type=patch.patch_type,
            target_subject_id=subject_id,
            instruction=patch.instruction,
            previous_image_ids=previous_image_ids,
            generated_image_artifact_id=artifact.artifact_id,
            generated_image_uri=artifact.uri,
            invalidated_asset_ids=invalidated_asset_ids,
            marked_patch_applied=True,
            next_phase=WorkflowPhase.SUBJECT_ASSET_GENERATION,
            plan=plan,
        ),
        updated_state,
    )


def _select_pending_subject_patch(review_patches: list[ReviewPatch], *, patch_id: str | None) -> ReviewPatch | None:
    for patch in review_patches:
        if patch_id is not None and patch.patch_id != patch_id:
            continue
        if patch.status != "pending":
            continue
        if patch.target_type == "subject":
            return patch
    return None


def _missing_patch_issue(review_patches: list[ReviewPatch], *, patch_id: str | None) -> str:
    if patch_id is not None:
        return f"pending_subject_review_patch_not_found:{patch_id}"
    if review_patches:
        return "missing_pending_subject_review_patch"
    return "missing_review_patch"


def _validate_subject_patch(patch: ReviewPatch) -> list[str]:
    issues = []
    if patch.target_type != "subject":
        issues.append(f"unsupported_review_patch_target:{patch.target_type}")
    if not patch.target_id:
        issues.append("review_patch_missing_target_subject_id")
    if patch.patch_type not in _supported_subject_patch_types():
        issues.append(f"unsupported_subject_patch_type:{patch.patch_type}")
    return issues


def _supported_subject_patch_types() -> set[str]:
    return {
        "appearance_change",
        "pose_change",
        "style_change",
        "replace_subject",
        "redo_subject",
    }


def _previous_subject_images(state: AgentProjectState, subject_id: str | None) -> list[str]:
    if not subject_id or state.concept_bundle is None:
        return []
    return list(state.concept_bundle.subject_concept_images.get(subject_id, []))


def _invalidated_asset_ids(patch: ReviewPatch) -> list[str]:
    structured_delta = patch.structured_delta or {}
    values = []
    asset_id = structured_delta.get("asset_id")
    if asset_id:
        values.append(str(asset_id))
    for artifact_id in patch.affected_artifact_ids:
        if artifact_id and str(artifact_id).startswith("asset_") and str(artifact_id) not in values:
            values.append(str(artifact_id))
    return values


def _build_regeneration_plan(
    *,
    patch: ReviewPatch,
    previous_image_ids: list[str],
    invalidated_asset_ids: list[str],
) -> dict[str, Any]:
    return {
        "domain_tool_name": "regenerate_concept_images",
        "implementation": "image_generation_adapter",
        "target_type": patch.target_type,
        "target_subject_id": patch.target_id,
        "patch_id": patch.patch_id,
        "patch_type": patch.patch_type,
        "instruction": patch.instruction,
        "previous_image_ids": previous_image_ids,
        "invalidated_asset_ids": invalidated_asset_ids,
        "output_artifact_type": ArtifactType.SUBJECT_CONCEPT_IMAGE.value,
    }


def _concept_bundle_with_generated_subject_image(
    concept_bundle: ConceptBundle | None,
    *,
    subject_id: str,
    artifact_id: str,
) -> ConceptBundle:
    if concept_bundle is None:
        return ConceptBundle(
            concept_version=1,
            subject_concept_images={subject_id: [artifact_id]},
            approved=False,
        )
    payload = _model_dump_python(concept_bundle)
    subject_images = {
        key: list(value)
        for key, value in payload.get("subject_concept_images", {}).items()
    }
    subject_images.setdefault(subject_id, []).append(artifact_id)
    payload.update(
        {
            "concept_version": int(payload.get("concept_version", 0)) + 1,
            "final_preview_image_id": None,
            "subject_concept_images": subject_images,
            "visual_qa": None,
            "approved": False,
            "approved_at": None,
        }
    )
    return ConceptBundle(**payload)


def _copy_model(model: Any, **updates: Any) -> Any:
    if hasattr(model, "model_copy"):
        return model.model_copy(update=updates)
    return model.copy(update=updates)


def _model_dump_python(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="python")
    return model.dict()
