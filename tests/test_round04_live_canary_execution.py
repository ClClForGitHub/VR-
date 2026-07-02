import json
import base64
from pathlib import Path

from agent_runtime.concept_image_execution import (
    ConceptImageBackend,
    ConceptImageBackendCapability,
    ConceptImageBackendGenerationRequest,
    ConceptImageBackendGenerationResult,
)
from agent_runtime.round04_live_samples import load_round04_case_manifests
from scripts.run_round04_live_user_samples import DEFAULT_FIXTURES_ROOT, run_case


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_round04_live_canary_reaches_concept_apply_when_backend_succeeds(tmp_path: Path) -> None:
    case_dir, manifest = next(
        (case_dir, manifest)
        for case_dir, manifest in load_round04_case_manifests(DEFAULT_FIXTURES_ROOT)
        if manifest.case_id == "case_03_lunar_rover"
    )
    backend = _FakeConceptBackend()

    result = run_case(
        case_dir=case_dir,
        manifest=manifest,
        output_root=tmp_path,
        live=True,
        overwrite=True,
        max_concept_regens=1,
        concept_image_backend=backend,
    )
    run_dir = Path(result["run_dir"])
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    rows = _read_jsonl(run_dir / "live_generation_calls.jsonl")

    assert result["status"] == "partial"
    assert summary["live_concept_worker"]["concept_generation_applied"] is True
    assert "live_generation" in summary["executed_stages"]
    assert state["phase"] == "SUBJECT_ASSET_GENERATION"
    assert state["concept_bundle"]["approved"] is True
    assert len(state["concept_bundle"]["subject_concept_images"]["subject_lunar_rover"]) == 1
    assert len(state["concept_bundle"]["scene_concept_image_ids"]) == 1
    assert state["concept_bundle"]["final_preview_image_id"].startswith("live_target_render")
    assert rows[0]["generation_mode"] == "image_guided"
    assert rows[0]["input_image_paths"]
    assert rows[-1]["generation_mode"] == "multi_image_composite"
    assert len(rows[-1]["source_image_paths"]) == 2
    assert all("no project-integrated image generation backend" not in issue for issue in result["issues"])
    assert len(backend.calls) == 3


def test_round04_chronological_canary_preserves_v1_v2_asset_library(tmp_path: Path) -> None:
    case_dir, manifest = next(
        (case_dir, manifest)
        for case_dir, manifest in load_round04_case_manifests(DEFAULT_FIXTURES_ROOT)
        if manifest.case_id == "case_01_tft_little_gwen"
    )
    backend = _FakeConceptBackend()

    result = run_case(
        case_dir=case_dir,
        manifest=manifest,
        output_root=tmp_path,
        live=True,
        overwrite=True,
        max_concept_regens=1,
        concept_image_backend=backend,
    )
    run_dir = Path(result["run_dir"])
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    rows = _read_jsonl(run_dir / "live_generation_calls.jsonl")

    v1_rows = [row for row in rows if row["concept_version"] == 1]
    v2_rows = [row for row in rows if row["concept_version"] == 2]
    v1_assets = [item for item in state["asset_library"] if item["generation_round"] == 1]
    v2_assets = [item for item in state["asset_library"] if item["generation_round"] == 2]

    assert result["status"] == "partial"
    assert [item["concept_version"] for item in summary["concept_rounds"]] == [1, 2]
    assert len(v1_rows) == 5
    assert len(v2_rows) == 6
    assert all(not row["input_image_paths"] for row in v1_rows if row["output_type"] != "target_render")
    assert sum(1 for row in v2_rows if row["input_image_paths"]) == 5
    assert len(v1_assets) == 5
    assert len(v2_assets) == 6
    assert any(item["artifact_id"].startswith("live_v2_") for item in v2_assets)
    assert state["concept_bundle"]["concept_version"] == 2
    assert state["review_patches"][0]["status"] == "applied"
    assert len(backend.calls) == 11


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
        output.write_bytes(PNG_BYTES)
        return ConceptImageBackendGenerationResult(ok=True, backend=self.backend_name, output_image_path=str(output))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
