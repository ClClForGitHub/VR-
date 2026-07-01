import json
from pathlib import Path

from agent_runtime.round04_live_samples import load_round04_case_manifest
from scripts.run_round04_live_user_samples import run_case


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures/live_user_samples/round04"


def test_round04_runner_contract_mode_creates_blocked_evidence_without_fake_outputs(tmp_path: Path) -> None:
    case_dir = FIXTURES_ROOT / "case_03_lunar_rover"
    manifest = load_round04_case_manifest(case_dir / "case_manifest.json")

    result = run_case(
        case_dir=case_dir,
        manifest=manifest,
        output_root=tmp_path / "round04_live_user_samples",
        live=False,
        overwrite=False,
        max_concept_regens=2,
    )
    run_dir = Path(result["run_dir"])
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))
    case_report = json.loads((run_dir / "case_live_report.json").read_text(encoding="utf-8"))
    calls = [
        json.loads(line)
        for line in (run_dir / "live_generation_calls.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert result["status"] == "blocked"
    assert state["phase"] == "CONCEPT_GENERATION"
    assert len(state["input_images"]) == 1
    assert len(state["reference_bindings"]) == 1
    assert frontend_status["concept_requirements"]
    assert case_report["status"] == "blocked"
    assert "contract_only_run_live_services_not_requested" in case_report["issues"]
    assert any(call["generation_mode"] == "image_guided" and call["input_image_paths"] for call in calls)
    assert all(call["output_image_path"] is None for call in calls)
    assert (run_dir / "runtime_api_bundle_snapshot.json").is_file()
