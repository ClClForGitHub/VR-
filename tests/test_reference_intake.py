from agent_runtime.reference_intake import (
    ReferenceBindingPlan,
    build_reference_intake_payload,
    build_reference_intake_result,
)
from agent_runtime.state import InputImage, WorkflowPhase


def _input_image(image_id: str = "image_001") -> InputImage:
    return InputImage(
        image_id=image_id,
        artifact_id=f"artifact_{image_id}",
        uri=f"/tmp/{image_id}.png",
        mime_type="image/png",
    )


def test_reference_intake_accepts_explicit_subject_binding() -> None:
    result = build_reference_intake_result(
        user_text="Create a small hero robot. subject_hero reference: image_001",
        input_images=[_input_image()],
        declared_bindings=[
            ReferenceBindingPlan(
                image_id="image_001",
                target_type="subject",
                target_id="subject_hero",
                usage="subject_reference",
                source_text_span="subject_hero reference: image_001",
            )
        ],
    )

    assert result.ok is True
    assert result.requires_clarification is False
    assert result.next_phase == WorkflowPhase.SCENE_SPEC_DRAFT
    assert result.reference_bindings[0].image_id == "image_001"
    assert result.reference_bindings[0].target_id == "subject_hero"


def test_reference_intake_blocks_unbound_uploaded_images() -> None:
    result = build_reference_intake_result(
        user_text="Create a small hero robot.",
        input_images=[_input_image()],
        declared_bindings=[],
    )

    assert result.ok is False
    assert result.requires_clarification is True
    assert result.next_phase == WorkflowPhase.INTAKE
    assert "image_missing_binding:image_001" in result.issues
    assert "image_001" in (result.clarification_prompt or "")


def test_reference_intake_rejects_implicit_binding() -> None:
    result = build_reference_intake_result(
        user_text="Create a small hero robot.",
        input_images=[_input_image()],
        declared_bindings=[
            {
                "image_id": "image_001",
                "target_type": "subject",
                "usage": "subject_reference",
                "explicit_in_user_text": False,
            }
        ],
    )

    assert result.ok is False
    assert "implicit_binding_not_allowed:image_001" in result.issues


def test_reference_intake_payload_normalizes_state_images() -> None:
    payload = build_reference_intake_payload(
        user_text="scene reference: image_scene",
        input_images=[_input_image("image_scene")],
        declared_bindings=[
            {
                "image_id": "image_scene",
                "target_type": "scene",
                "usage": "scene_reference",
            }
        ],
    )

    assert payload.input_images[0].artifact_id == "artifact_image_scene"
    assert payload.declared_bindings[0].target_type == "scene"

