"""Apply validated ConceptPromptPlanner output to AgentProjectState."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_runtime.agent_prompts import (
    ConceptPromptPlannerOutput,
    concept_prompt_pack_from_planner_output,
)
from agent_runtime.llm_nodes import LLMNodeExecutionResult
from agent_runtime.state import AgentProjectState, ConceptBundle, ConceptPromptPack, SceneSpec, WorkflowPhase
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

    issues = _planner_output_issues(scene_spec=state.scene_spec, output=output)
    if issues:
        return (
            ConceptPromptApplicationResult(
                ok=False,
                next_phase=state.phase,
                issues=issues,
            ),
            state,
        )

    prompt_pack = concept_prompt_pack_from_planner_output(output, scene_spec=state.scene_spec)
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


def _planner_output_issues(
    *,
    scene_spec: SceneSpec | None,
    output: ConceptPromptPlannerOutput,
) -> list[str]:
    issues: list[str] = []
    if output.requires_clarification:
        issue = "planner_requires_clarification"
        if output.open_questions:
            issue = f"{issue}:{' | '.join(output.open_questions)}"
        issues.append(issue)
    if not output.scene_prompts:
        issues.append("missing_scene_concept_prompt")
    if not output.final_preview_prompt.strip():
        issues.append("missing_final_preview_prompt")
    if scene_spec is None:
        if not output.subject_prompts:
            issues.append("missing_subject_concept_prompts")
        return issues

    subjects_by_id = {subject.subject_id: subject for subject in scene_spec.subjects}
    required_subject_ids = {
        subject.subject_id
        for subject in scene_spec.subjects
        if subject.needs_2d_concept
    }
    missing_required = sorted(required_subject_ids - set(output.subject_prompts))
    issues.extend(f"missing_subject_concept_prompt:{subject_id}" for subject_id in missing_required)

    for subject_id in sorted(output.subject_prompts):
        subject = subjects_by_id.get(subject_id)
        if subject is None:
            issues.append(f"unknown_subject_concept_prompt:{subject_id}")
        elif not subject.needs_2d_concept:
            issues.append(f"unexpected_subject_concept_prompt:{subject_id}")

    prompt_pack = concept_prompt_pack_from_planner_output(output, scene_spec=scene_spec)
    requirements_by_key = {
        requirement.prompt_key: requirement
        for requirement in prompt_pack.image_requirements
    }
    for subject in scene_spec.subjects:
        if not subject.needs_2d_concept or not subject.reference_image_ids:
            continue
        requirement = requirements_by_key.get(f"subject_prompts.{subject.subject_id}")
        if requirement is None:
            issues.append(f"missing_subject_reference_requirement:{subject.subject_id}")
            continue
        missing_refs = sorted(set(subject.reference_image_ids) - set(requirement.input_reference_image_ids))
        if missing_refs:
            issues.append(f"missing_subject_reference_inputs:{subject.subject_id}:{','.join(missing_refs)}")
        if requirement.generation_mode != "image_guided" or not requirement.must_use_image_inputs:
            issues.append(f"subject_reference_not_image_guided:{subject.subject_id}")

    target_requirements = [
        requirement
        for requirement in prompt_pack.image_requirements
        if requirement.output_type == "target_render"
    ]
    required_sources = {
        requirement.requirement_id
        for requirement in prompt_pack.image_requirements
        if requirement.output_type in {"subject_concept", "scene_concept"}
    }
    if required_sources:
        if not target_requirements:
            issues.append("missing_target_render_requirement")
        else:
            for requirement in target_requirements:
                missing_sources = sorted(required_sources - set(requirement.source_requirement_ids))
                if missing_sources:
                    issues.append(
                        f"target_render_missing_source_requirements:{requirement.requirement_id}:{','.join(missing_sources)}"
                    )
                if requirement.generation_mode != "multi_image_composite" or not requirement.must_use_image_inputs:
                    issues.append(f"target_render_not_multi_image_composite:{requirement.requirement_id}")
    return issues
