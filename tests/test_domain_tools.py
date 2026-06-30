import pytest

from agent_runtime.domain_tools import (
    allowed_tool_names,
    assert_tool_allowed,
    validate_registry,
)
from agent_runtime.state import WorkflowPhase


def test_domain_tool_registry_is_internally_consistent() -> None:
    validate_registry()


def test_blender_edit_only_exposes_edit_safe_domain_tools() -> None:
    tools = allowed_tool_names(WorkflowPhase.BLENDER_EDIT)

    assert "get_blender_scene_summary" in tools
    assert "move_subject" in tools
    assert "export_viewer_scene" in tools
    assert "render_preview" in tools
    assert "build_subject_asset" not in tools


def test_blender_assembly_exposes_scene_summary_before_mutating_tools() -> None:
    tools = allowed_tool_names(WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION)

    assert tools[0] == "get_blender_scene_summary"
    assert "import_scene_asset" in tools
    assert "setup_camera" in tools


def test_subject_asset_qa_exposes_quality_and_preview_tools() -> None:
    tools = allowed_tool_names(WorkflowPhase.SUBJECT_ASSET_QA)

    assert tools == ["check_subject_asset_quality", "render_preview"]


def test_tool_phase_guard_rejects_wrong_phase() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        assert_tool_allowed(WorkflowPhase.CONCEPT_GENERATION, "delete_subject")
