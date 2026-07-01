import base64
import json
from pathlib import Path

import pytest

from agent_runtime.codex_self_mcp import CodexSelfMCPCallPlan, CodexSelfMCPRunResult
from agent_runtime.concept_image_execution import (
    CodexSelfMCPImage2ConceptBackend,
)
from agent_runtime.image2_reference_adapter import (
    Image2ReferenceAttachment,
    build_attachment_manifest,
    inspect_codex_self_image2_log,
    prepare_viewable_attachment_manifest,
)


def test_build_attachment_manifest_records_paths_hashes_and_roles(tmp_path: Path) -> None:
    subject = tmp_path / "subject.png"
    scene = tmp_path / "scene.png"
    subject.write_bytes(b"subject-image")
    scene.write_bytes(b"scene-image")

    subject_manifest = build_attachment_manifest(
        input_reference_image_ids=["image_subject"],
        input_image_paths=[str(subject)],
        source_requirement_ids=[],
        source_image_paths=[],
        output_type="subject_concept",
    )
    target_manifest = build_attachment_manifest(
        input_reference_image_ids=[],
        input_image_paths=[],
        source_requirement_ids=["subject_concept:robot", "scene_concept:studio"],
        source_image_paths=[str(subject), str(scene)],
        output_type="target_render",
    )

    assert subject_manifest[0].label == "Image 1"
    assert subject_manifest[0].role == "subject_reference"
    assert subject_manifest[0].image_id == "image_subject"
    assert subject_manifest[0].sha256
    assert [item.source_requirement_id for item in target_manifest] == [
        "subject_concept:robot",
        "scene_concept:studio",
    ]
    assert [item.role for item in target_manifest] == ["generated_concept_reference", "generated_concept_reference"]


def test_prepare_viewable_attachment_manifest_converts_non_native_image_suffix(tmp_path: Path) -> None:
    pytest.importorskip("PIL.Image")
    reference = tmp_path / "reference.avif"
    reference.write_bytes(base64.b64decode(_TINY_PNG_BASE64))
    manifest = build_attachment_manifest(
        input_reference_image_ids=["image_subject"],
        input_image_paths=[str(reference)],
        source_requirement_ids=[],
        source_image_paths=[],
        output_type="subject_concept",
    )

    prepared, issues = prepare_viewable_attachment_manifest(manifest, view_dir=tmp_path / "reference_views")

    assert issues == []
    assert prepared[0].path == str(reference.resolve())
    assert prepared[0].mime_type == "image/avif"
    assert prepared[0].view_path is not None
    assert prepared[0].view_path != prepared[0].path
    assert prepared[0].view_mime_type == "image/png"
    assert Path(prepared[0].view_path).exists()


def test_prepare_viewable_attachment_manifest_converts_mislabeled_webp(tmp_path: Path) -> None:
    pytest.importorskip("PIL.Image")
    from PIL import Image

    reference = tmp_path / "reference.png"
    Image.new("RGB", (12, 8), "red").save(reference, format="WEBP")
    manifest = build_attachment_manifest(
        input_reference_image_ids=["image_subject"],
        input_image_paths=[str(reference)],
        source_requirement_ids=[],
        source_image_paths=[],
        output_type="subject_concept",
    )

    prepared, issues = prepare_viewable_attachment_manifest(manifest, view_dir=tmp_path / "reference_views")

    assert issues == []
    assert prepared[0].path == str(reference.resolve())
    assert prepared[0].mime_type == "image/png"
    assert prepared[0].view_path is not None
    assert prepared[0].view_path != prepared[0].path
    assert prepared[0].view_mime_type == "image/png"
    with Image.open(prepared[0].view_path) as image:
        assert image.format == "PNG"


def test_codex_self_image2_backend_requires_view_image_evidence(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    _write_test_png(reference)
    adapter = _FakeCodexAdapter(reference_path=reference, include_view_image=True)
    backend = CodexSelfMCPImage2ConceptBackend(adapter=adapter)
    request = _request(reference, tmp_path / "generated.png")

    result = backend.generate(request)
    evidence = inspect_codex_self_image2_log(adapter.log_path)

    assert result.ok is True
    assert result.output_image_path == str((tmp_path / "generated.png").resolve())
    assert result.raw_summary["viewed_image_paths"] == [str(reference.resolve())]
    assert result.raw_summary["view_image_payload_paths"] == [str(reference.resolve())]
    assert evidence.image_generation_count == 1
    assert Path(result.output_image_path).read_bytes() == b"generated-image"


def test_codex_self_image2_backend_fails_without_view_image_evidence(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    _write_test_png(reference)
    adapter = _FakeCodexAdapter(reference_path=reference, include_view_image=False)
    backend = CodexSelfMCPImage2ConceptBackend(adapter=adapter)

    result = backend.generate(_request(reference, tmp_path / "generated.png"))

    assert result.ok is False
    assert any(issue.startswith("codex_self_image2_missing_view_image_call") for issue in result.issues)


def test_codex_self_image2_backend_fails_when_view_image_returns_no_payload(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    _write_test_png(reference)
    adapter = _FakeCodexAdapter(reference_path=reference, include_view_image=True, include_payload=False)
    backend = CodexSelfMCPImage2ConceptBackend(adapter=adapter)

    result = backend.generate(_request(reference, tmp_path / "generated.png"))

    assert result.ok is False
    assert any(issue.startswith("codex_self_image2_missing_view_image_payload") for issue in result.issues)
    assert any(issue.startswith("view_image_payload_unprocessed") for issue in result.issues)


class _FakeCodexAdapter:
    def __init__(self, *, reference_path: Path, include_view_image: bool, include_payload: bool = True) -> None:
        self.reference_path = reference_path
        self.include_view_image = include_view_image
        self.include_payload = include_payload
        self.log_path = Path("/tmp/missing.jsonl")

    def status(self, **_kwargs):
        return type(
            "Status",
            (),
            {
                "ok": True,
                "issues": [],
                "client_script_exists": True,
            },
        )()

    def build_call_plan(self, **kwargs) -> CodexSelfMCPCallPlan:
        self.log_path = Path(kwargs["log_path"]).expanduser().resolve()
        return CodexSelfMCPCallPlan(
            command=["fake-codex-self-image2"],
            cwd=str(Path(kwargs["cwd"]).resolve()),
            sandbox=kwargs["sandbox"],
            approval_policy=kwargs["approval_policy"],
            timeout_seconds=kwargs["timeout_seconds"],
            log_path=str(self.log_path),
            prompt_source="file",
            prompt_file=str(kwargs["prompt_file"]),
            extract_last_image_to=str(kwargs["extract_last_image_to"]),
        )

    def run_call_plan(self, plan: CodexSelfMCPCallPlan) -> CodexSelfMCPRunResult:
        output_path = Path(plan.extract_last_image_to)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"generated-image")
        rows = []
        if self.include_view_image:
            rows.append(
                {
                    "method": "codex/event",
                    "params": {
                        "msg": {
                            "type": "raw_response_item",
                            "item": {
                                "type": "function_call",
                                "name": "view_image",
                                "arguments": json.dumps({"path": str(self.reference_path.resolve())}),
                                "call_id": "call_view",
                            },
                        }
                    },
                }
            )
            rows.append(
                {
                    "method": "codex/event",
                    "params": {
                        "msg": {
                            "type": "view_image_tool_call",
                            "path": str(self.reference_path.resolve()),
                        }
                    },
                }
            )
            rows.append(
                {
                    "method": "codex/event",
                    "params": {
                        "msg": {
                            "type": "raw_response_item",
                            "item": {
                                "type": "function_call_output",
                                "call_id": "call_view",
                                "output": (
                                    [{"type": "input_image", "image_url": "data:image/png;base64,ZmFrZQ=="}]
                                    if self.include_payload
                                    else [{"type": "input_text", "text": "image content omitted because it could not be processed"}]
                                ),
                            },
                        }
                    },
                }
            )
        rows.append(
            {
                "method": "codex/event",
                "params": {
                    "msg": {
                        "type": "image_generation_end",
                        "call_id": "ig_fake",
                        "result": base64.b64encode(b"generated-image").decode("ascii"),
                    }
                },
            }
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        return CodexSelfMCPRunResult(ok=True, returncode=0, stdout_tail="ok", stderr_tail="", plan=plan)


def _request(reference: Path, output: Path):
    from agent_runtime.concept_image_execution import ConceptImageBackendGenerationRequest

    manifest = build_attachment_manifest(
        input_reference_image_ids=["image_subject"],
        input_image_paths=[str(reference)],
        source_requirement_ids=[],
        source_image_paths=[],
        output_type="subject_concept",
    )
    return ConceptImageBackendGenerationRequest(
        requirement_id="subject_concept:robot",
        output_type="subject_concept",
        generation_mode="image_guided",
        prompt="Create a robot subject concept.",
        input_reference_image_ids=["image_subject"],
        input_image_paths=[str(reference)],
        attachment_manifest=manifest,
        output_path=str(output),
    )


def _write_test_png(path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "blue").save(path, format="PNG")


_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
