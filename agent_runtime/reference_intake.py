"""Reference-image intake contracts for the V1 controller layer.

This module does not attempt natural-language parsing by regex. It gives UI,
LLM, or manual intake code a typed boundary for explicit image bindings before
the workflow proceeds to SceneSpec compilation.
"""

from __future__ import annotations

from typing import Any, Literal

try:
    from pydantic import BaseModel, Field, field_validator
except ImportError:  # pragma: no cover - compatibility for Pydantic v1 environments
    from pydantic import BaseModel, Field, validator as field_validator

from agent_runtime.state import InputImage, ReferenceBinding, WorkflowPhase


ReferenceTargetType = Literal["subject", "scene", "style", "pose", "texture", "layout"]
ReferenceUsage = Literal[
    "subject_reference",
    "scene_reference",
    "style_reference",
    "pose_reference",
    "texture_reference",
    "layout_reference",
]


EXPECTED_USAGE_BY_TARGET: dict[str, str] = {
    "subject": "subject_reference",
    "scene": "scene_reference",
    "style": "style_reference",
    "pose": "pose_reference",
    "texture": "texture_reference",
    "layout": "layout_reference",
}


class ReferenceImageInput(BaseModel):
    image_id: str
    artifact_id: str | None = None
    uri: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    user_declared_label: str | None = None
    notes: str | None = None

    @classmethod
    def from_state_image(cls, image: InputImage) -> "ReferenceImageInput":
        return cls(
            image_id=image.image_id,
            artifact_id=image.artifact_id,
            uri=image.uri,
            mime_type=image.mime_type,
            width=image.width,
            height=image.height,
            user_declared_label=image.user_declared_label,
            notes=image.notes,
        )


class ReferenceBindingPlan(BaseModel):
    image_id: str
    target_type: ReferenceTargetType
    usage: ReferenceUsage
    target_id: str | None = None
    binding_id: str | None = None
    explicit_in_user_text: bool = True
    confidence: float = 1.0
    source_text_span: str | None = None
    notes: str | None = None

    @field_validator("confidence")
    def confidence_in_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    def expected_usage(self) -> str:
        return EXPECTED_USAGE_BY_TARGET[self.target_type]

    def to_reference_binding(self, *, index: int = 1) -> ReferenceBinding:
        binding_id = self.binding_id or f"binding_{index:03d}_{self.image_id}"
        return ReferenceBinding(
            binding_id=binding_id,
            image_id=self.image_id,
            target_type=self.target_type,
            target_id=self.target_id,
            usage=self.usage,
            explicit_in_user_text=self.explicit_in_user_text,
            confidence=self.confidence,
            notes=self.notes,
        )


class UserRequestIntake(BaseModel):
    user_text: str
    input_images: list[ReferenceImageInput] = Field(default_factory=list)
    declared_bindings: list[ReferenceBindingPlan] = Field(default_factory=list)
    turn_id: str | None = None
    project_id: str | None = None
    thread_id: str | None = None


class IntakeExtractionResult(BaseModel):
    ok: bool
    intake: UserRequestIntake
    reference_bindings: list[ReferenceBinding] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_prompt: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    next_phase: WorkflowPhase = WorkflowPhase.SCENE_SPEC_DRAFT


def build_reference_intake_payload(
    *,
    user_text: str,
    input_images: list[InputImage | ReferenceImageInput | dict[str, Any]] | None = None,
    declared_bindings: list[ReferenceBindingPlan | ReferenceBinding | dict[str, Any]] | None = None,
    turn_id: str | None = None,
    project_id: str | None = None,
    thread_id: str | None = None,
) -> UserRequestIntake:
    """Normalize user text, image metadata, and binding declarations."""

    return UserRequestIntake(
        user_text=user_text,
        input_images=[_normalize_image(image) for image in input_images or []],
        declared_bindings=[_normalize_binding_plan(binding) for binding in declared_bindings or []],
        turn_id=turn_id,
        project_id=project_id,
        thread_id=thread_id,
    )


def build_reference_intake_result(
    *,
    user_text: str,
    input_images: list[InputImage | ReferenceImageInput | dict[str, Any]] | None = None,
    declared_bindings: list[ReferenceBindingPlan | ReferenceBinding | dict[str, Any]] | None = None,
    turn_id: str | None = None,
    project_id: str | None = None,
    thread_id: str | None = None,
    require_all_images_bound: bool = True,
) -> IntakeExtractionResult:
    """Validate explicit reference bindings for the next SceneSpec step."""

    intake = build_reference_intake_payload(
        user_text=user_text,
        input_images=input_images,
        declared_bindings=declared_bindings,
        turn_id=turn_id,
        project_id=project_id,
        thread_id=thread_id,
    )
    issues = _binding_issues(intake, require_all_images_bound=require_all_images_bound)
    if issues:
        questions = _open_questions_for_issues(issues)
        return IntakeExtractionResult(
            ok=False,
            intake=intake,
            requires_clarification=True,
            clarification_prompt=_clarification_prompt(intake),
            open_questions=questions,
            issues=issues,
            next_phase=WorkflowPhase.INTAKE,
        )

    bindings = [
        binding_plan.to_reference_binding(index=index)
        for index, binding_plan in enumerate(intake.declared_bindings, start=1)
    ]
    return IntakeExtractionResult(
        ok=True,
        intake=intake,
        reference_bindings=bindings,
        requires_clarification=False,
        next_phase=WorkflowPhase.SCENE_SPEC_DRAFT,
    )


def _normalize_image(image: InputImage | ReferenceImageInput | dict[str, Any]) -> ReferenceImageInput:
    if isinstance(image, ReferenceImageInput):
        return image
    if isinstance(image, InputImage):
        return ReferenceImageInput.from_state_image(image)
    return ReferenceImageInput(**image)


def _normalize_binding_plan(
    binding: ReferenceBindingPlan | ReferenceBinding | dict[str, Any],
) -> ReferenceBindingPlan:
    if isinstance(binding, ReferenceBindingPlan):
        return binding
    if isinstance(binding, ReferenceBinding):
        return ReferenceBindingPlan(
            binding_id=binding.binding_id,
            image_id=binding.image_id,
            target_type=binding.target_type,
            target_id=binding.target_id,
            usage=binding.usage,
            explicit_in_user_text=binding.explicit_in_user_text,
            confidence=binding.confidence,
            notes=binding.notes,
        )
    return ReferenceBindingPlan(**binding)


def _binding_issues(intake: UserRequestIntake, *, require_all_images_bound: bool) -> list[str]:
    issues: list[str] = []
    image_ids = {image.image_id for image in intake.input_images}
    if not intake.user_text.strip():
        issues.append("empty_user_text")
    for binding in intake.declared_bindings:
        if binding.image_id not in image_ids:
            issues.append(f"binding_unknown_image:{binding.image_id}")
        if not binding.explicit_in_user_text:
            issues.append(f"implicit_binding_not_allowed:{binding.image_id}")
        if binding.usage != binding.expected_usage():
            issues.append(
                f"binding_usage_mismatch:{binding.image_id}:{binding.target_type}:{binding.usage}"
            )
    if require_all_images_bound and image_ids:
        bound_image_ids = {binding.image_id for binding in intake.declared_bindings}
        for image_id in sorted(image_ids - bound_image_ids):
            issues.append(f"image_missing_binding:{image_id}")
    return issues


def _open_questions_for_issues(issues: list[str]) -> list[str]:
    questions: list[str] = []
    if any(issue.startswith("image_missing_binding:") for issue in issues):
        questions.append("Please declare what each uploaded image should control.")
    if any(issue.startswith("binding_unknown_image:") for issue in issues):
        questions.append("Please use only the stable image IDs shown by the project.")
    if any(issue.startswith("binding_usage_mismatch:") for issue in issues):
        questions.append("Please make each image usage match its target type.")
    if any(issue.startswith("implicit_binding_not_allowed:") for issue in issues):
        questions.append("Please confirm image bindings explicitly in user text.")
    if "empty_user_text" in issues:
        questions.append("Please describe the scene you want to create.")
    return questions


def _clarification_prompt(intake: UserRequestIntake) -> str:
    image_ids = ", ".join(image.image_id for image in intake.input_images) or "<no images>"
    return (
        "Please declare the purpose of each uploaded image before generation. "
        f"Available image IDs: {image_ids}. Example: "
        "subject_hero reference: image_001; scene reference: image_002; "
        "style reference: image_003."
    )
