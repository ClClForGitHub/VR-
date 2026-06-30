"""Apply validated ConceptPromptPlanner output to AgentProjectState."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_runtime.agent_prompts import (
    ConceptPromptPlannerOutput,
    concept_prompt_pack_from_planner_output,
)
from agent_runtime.llm_nodes import LLMNodeExecutionResult
from agent_runtime.state import AgentProjectState, ConceptBundle, ConceptPromptPack, WorkflowPhase
from agent_runtime.state_views import apply_state_updates


class ConceptPromptApplicationResult(BaseModel):
    ok: bool
    concept_version: int | None = None
    prompt_pack: ConceptPromptPack | None = None
    next_phase: WorkflowPhase | None = None
    issues: list[str] = Field(default_factory=list)


def apply_concept_prompt_planner_output(
    *,
    state: AgentProjectState,
    planner_output: ConceptPromptPlannerOutput | LLMNodeExecutionResult | dict[str, Any],
) -> tuple[ConceptPromptApplicationResult, AgentProjectState]:
    """Store a validated ConceptPromptPack in the existing ConceptBundle path."""

    output = _normalize_planner_output(planner_output)
    if output is None:
        return (
            ConceptPromptApplicationResult(
                ok=False,
                next_phase=state.phase,
                issues=["missing_valid_concept_prompt_planner_output"],
            ),
            state,
        )

    prompt_pack = concept_prompt_pack_from_planner_output(output)
    concept_bundle = _updated_concept_bundle(
        state.concept_bundle,
        prompt_pack=prompt_pack,
        clear_outputs=_has_pending_review_patch(state),
    )
    updated = apply_state_updates(
        state,
        node_name="ConceptPromptPlanner",
        updates={
            "concept_bundle": concept_bundle,
            "phase": WorkflowPhase.CONCEPT_GENERATION,
        },
    )
    return (
        ConceptPromptApplicationResult(
            ok=True,
            concept_version=concept_bundle.concept_version,
            prompt_pack=prompt_pack,
            next_phase=WorkflowPhase.CONCEPT_GENERATION,
        ),
        updated,
    )


def _normalize_planner_output(
    value: ConceptPromptPlannerOutput | LLMNodeExecutionResult | dict[str, Any],
) -> ConceptPromptPlannerOutput | None:
    if isinstance(value, ConceptPromptPlannerOutput):
        return value
    if isinstance(value, LLMNodeExecutionResult):
        if not value.ok or value.parsed_output is None:
            return None
        return ConceptPromptPlannerOutput(**value.parsed_output)
    if isinstance(value, dict):
        return ConceptPromptPlannerOutput(**value)
    return None


def _updated_concept_bundle(
    existing: ConceptBundle | None,
    *,
    prompt_pack: ConceptPromptPack,
    clear_outputs: bool = False,
) -> ConceptBundle:
    if existing is None:
        return ConceptBundle(
            concept_version=1,
            prompt_pack=prompt_pack,
            approved=False,
            approved_at=None,
        )
    return ConceptBundle(
        concept_version=existing.concept_version + 1,
        final_preview_image_id=None if clear_outputs else existing.final_preview_image_id,
        subject_concept_images={} if clear_outputs else dict(existing.subject_concept_images),
        scene_concept_image_ids=[] if clear_outputs else list(existing.scene_concept_image_ids),
        prompt_pack=prompt_pack,
        visual_qa=None,
        approved=False,
        approved_at=None,
    )


def _has_pending_review_patch(state: AgentProjectState) -> bool:
    return any(patch.status == "pending" for patch in state.review_patches)
