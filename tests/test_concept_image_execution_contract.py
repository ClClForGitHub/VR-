import json
from pathlib import Path

from agent_runtime.concept_image_execution import (
    ConceptImageBackend,
    ConceptImageBackendCapability,
    ConceptImageBackendGenerationRequest,
    ConceptImageBackendGenerationResult,
    execute_concept_image_handoff,
)


def test_concept_image_execution_resolves_inputs_and_source_outputs(tmp_path: Path) -> None:
    reference = tmp_path / "subject_ref.png"
    reference.write_bytes(b"reference")
    backend = _FakeConceptBackend()

    result = execute_concept_image_handoff(
        run_dir=tmp_path,
        handoff_payload=_handoff_payload(reference),
        backend=backend,
        handoff_id="handoff_001",
    )
    rows = _read_jsonl(tmp_path / "live_generation_calls.jsonl")

    assert result.ok is True
    assert len(result.image_results) == 3
    assert [record.requirement_id for record in result.call_records] == [
        "subject_concept:rover",
        "scene_concept:moon",
        "target_render:final_preview",
    ]
    assert rows[0]["input_image_paths"] == [str(reference.resolve())]
    assert rows[0]["attachment_manifest"][0]["label"] == "Image 1"
    assert rows[0]["attachment_manifest"][0]["path"] == str(reference.resolve())
    assert rows[0]["attachment_manifest"][0]["role"] == "subject_reference"
    assert rows[2]["source_requirement_ids"] == ["subject_concept:rover", "scene_concept:moon"]
    assert len(rows[2]["source_image_paths"]) == 2
    assert [item["path"] for item in rows[2]["attachment_manifest"]] == rows[2]["source_image_paths"]
    assert result.image_results[2]["output_type"] == "target_render"
    assert result.image_results[2]["metadata"]["source_image_paths"] == rows[2]["source_image_paths"]
    assert result.image_results[2]["metadata"]["attachment_manifest"] == rows[2]["attachment_manifest"]
    assert len(backend.calls) == 3
    assert backend.calls[0].attachment_manifest[0].path == str(reference.resolve())
    assert [item.path for item in backend.calls[2].attachment_manifest] == rows[2]["source_image_paths"]


def test_concept_image_execution_blocks_missing_required_reference(tmp_path: Path) -> None:
    missing = tmp_path / "missing.png"

    result = execute_concept_image_handoff(
        run_dir=tmp_path,
        handoff_payload=_handoff_payload(missing),
        backend=_FakeConceptBackend(),
    )

    assert result.ok is False
    assert [item["requirement_id"] for item in result.image_results] == ["scene_concept:moon"]
    assert any(issue.startswith("missing_input_reference_file:ref_subject") for issue in result.issues)
    assert any(issue == "missing_source_requirement_output:subject_concept:rover" for issue in result.issues)


def test_concept_image_execution_does_not_downgrade_image_guided_to_text(tmp_path: Path) -> None:
    reference = tmp_path / "subject_ref.png"
    reference.write_bytes(b"reference")
    backend = _TextOnlyBackend()

    result = execute_concept_image_handoff(
        run_dir=tmp_path,
        handoff_payload=_handoff_payload(reference),
        backend=backend,
    )
    rows = _read_jsonl(tmp_path / "live_generation_calls.jsonl")

    assert result.ok is False
    assert any("backend_does_not_support_image_guided_inputs:text_only" in issue for issue in result.issues)
    assert rows[0]["ok"] is False
    assert rows[0]["output_image_path"] is None
    assert result.image_results == []
    assert backend.calls == []


class _FakeConceptBackend(ConceptImageBackend):
    backend_name = "fake_live_image"

    def __init__(self) -> None:
        self.calls: list[ConceptImageBackendGenerationRequest] = []

    def capability(self) -> ConceptImageBackendCapability:
        return ConceptImageBackendCapability(
            backend_name=self.backend_name,
            text_to_image=True,
            image_guided_single_reference=True,
            multi_image_composite=True,
            output_extraction=True,
            structured_file_attachments=True,
        )

    def generate(self, request: ConceptImageBackendGenerationRequest) -> ConceptImageBackendGenerationResult:
        self.calls.append(request)
        output = Path(request.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"fake image {request.requirement_id}".encode("utf-8"))
        return ConceptImageBackendGenerationResult(
            ok=True,
            backend=self.backend_name,
            output_image_path=str(output),
        )


class _TextOnlyBackend(_FakeConceptBackend):
    backend_name = "text_only"

    def capability(self) -> ConceptImageBackendCapability:
        return ConceptImageBackendCapability(
            backend_name=self.backend_name,
            text_to_image=True,
            image_guided_single_reference=False,
            multi_image_composite=False,
            output_extraction=True,
            structured_file_attachments=False,
        )


def _handoff_payload(reference_path: Path) -> dict:
    return {
        "concept_generation": {
            "execution_order": [
                "subject_concept:rover",
                "scene_concept:moon",
                "target_render:final_preview",
            ],
            "requirements": [
                {
                    "requirement_id": "subject_concept:rover",
                    "output_type": "subject_concept",
                    "target_id": "subject_rover",
                    "prompt_key": "subject_prompts.subject_rover",
                    "prompt": "Generate a subject-only lunar rover concept.",
                    "negative_prompt": "blurry",
                    "generation_mode": "image_guided",
                    "input_reference_image_ids": ["ref_subject"],
                    "resolved_input_images": [
                        {
                            "image_id": "ref_subject",
                            "uri": str(reference_path),
                            "exists": reference_path.exists(),
                        }
                    ],
                    "must_use_image_inputs": True,
                },
                {
                    "requirement_id": "scene_concept:moon",
                    "output_type": "scene_concept",
                    "target_id": "scene_moon",
                    "prompt_key": "scene_prompts.0",
                    "prompt": "Generate a moon base scene concept.",
                    "generation_mode": "text_to_image",
                },
                {
                    "requirement_id": "target_render:final_preview",
                    "output_type": "target_render",
                    "target_id": "scene_moon",
                    "prompt_key": "final_preview_prompt",
                    "prompt": "Composite the rover with the moon base.",
                    "generation_mode": "multi_image_composite",
                    "source_requirement_ids": ["subject_concept:rover", "scene_concept:moon"],
                    "must_use_image_inputs": True,
                },
            ],
        }
    }


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
