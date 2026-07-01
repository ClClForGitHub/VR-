from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "docs" / "agent_execution_harness"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_agent_execution_harness_docs_exist() -> None:
    expected = [
        "README.md",
        "task_packet_template.md",
        "runtime_flow_rules.md",
        "live_test_policy.md",
        "documentation_maintenance.md",
        "module_checklist.md",
        "progress_log.md",
        "decision_log.md",
        "design_notes.md",
    ]
    missing = [name for name in expected if not (HARNESS / name).exists()]
    assert not missing, f"Missing harness docs: {missing}"


def test_harness_readme_records_core_runtime_boundaries() -> None:
    text = _read(HARNESS / "README.md")
    required_terms = [
        "state.json",
        "frontend_status.json",
        "delegated",
        "dry-run",
        "user-action",
        "handoff-apply",
        "input_image_paths",
        "outputs/runs",
    ]
    missing = [term for term in required_terms if term not in text]
    assert not missing, f"README.md missing required terms: {missing}"


def test_runtime_flow_rules_cover_user_gates_and_image_inputs() -> None:
    text = _read(HARNESS / "runtime_flow_rules.md")
    required_terms = [
        "CONCEPT_REVIEW",
        "BLENDER_PREVIEW",
        "runtime_user_action.jsonl",
        "runtime_handoff_apply.jsonl",
        "image_guided",
        "multi_image_composite",
        "source_requirement_ids",
    ]
    missing = [term for term in required_terms if term not in text]
    assert not missing, f"runtime_flow_rules.md missing required terms: {missing}"


def test_task_packet_template_requires_tests_and_report() -> None:
    text = _read(HARNESS / "task_packet_template.md")
    required_terms = [
        "Allowed file scope",
        "Forbidden shortcuts",
        "Tests",
        "Live-test plan",
        "Acceptance criteria",
        "Final report requirements",
        "git diff --stat",
        "git status --short",
    ]
    missing = [term for term in required_terms if term not in text]
    assert not missing, f"task_packet_template.md missing required terms: {missing}"


def test_live_test_policy_requires_explicit_boundary() -> None:
    text = _read(HARNESS / "live_test_policy.md")
    required_terms = [
        "Approval required",
        "Service status checks",
        "Live command",
        "Output directory",
        "Expected files",
        "Success criteria",
        "Stop criteria",
    ]
    missing = [term for term in required_terms if term not in text]
    assert not missing, f"live_test_policy.md missing required terms: {missing}"
