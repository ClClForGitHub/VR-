import json
from pathlib import Path

import pytest

from agent_runtime.runtime_audit import audit_runtime_run
from agent_runtime.runtime_loop import run_bounded_runtime_loop
from agent_runtime.scenario_fixtures import (
    NaturalLanguageSceneCase,
    load_natural_language_scene_cases,
    materialize_runtime_scenario_case,
)


SCENARIO_CASES = load_natural_language_scene_cases()


def test_natural_language_fixture_matrix_has_expected_coverage() -> None:
    case_ids = [case.case_id for case in SCENARIO_CASES]
    categories = {case.category for case in SCENARIO_CASES}
    languages = {case.language for case in SCENARIO_CASES}

    assert len(case_ids) == len(set(case_ids))
    assert len(SCENARIO_CASES) >= 7
    assert {"zh", "en"} <= languages
    assert {
        "text_only_single_subject",
        "subject_scene_style_refs",
        "multi_subject_layout",
        "vehicle_texture_scene_refs",
        "clarification_required",
    } <= categories


def test_natural_language_fixture_matrix_includes_user_requested_samples() -> None:
    cases = {case.case_id: case for case in SCENARIO_CASES}

    assert {
        "scenario_zh_wuthering_chibi_beach_duo",
        "scenario_zh_little_gwen_chessboard_ref",
        "scenario_zh_explorer_rover_moon_regolith",
    } <= set(cases)
    assert cases["scenario_zh_wuthering_chibi_beach_duo"].expected.subject_ids == [
        "subject_phoebe_chibi",
        "subject_florollo_chibi",
        "subject_beach_chair",
        "subject_sand_castle",
    ]
    assert cases["scenario_zh_wuthering_chibi_beach_duo"].expected.subject_asset_ids_required == [
        "subject_phoebe_chibi",
        "subject_florollo_chibi",
    ]
    little_gwen = cases["scenario_zh_little_gwen_chessboard_ref"]
    assert Path(little_gwen.input_images[0].uri).is_file()
    assert little_gwen.declared_bindings[0]["target_id"] == "subject_little_gwen"
    assert little_gwen.expected.subject_ids == ["subject_little_gwen", "subject_chess_pieces"]
    assert little_gwen.expected.subject_asset_ids_required == ["subject_little_gwen"]
    assert little_gwen.expected.procedural_object_ids == ["subject_chess_pieces"]
    assert little_gwen.expected.scene_environment_type == "chessboard_stage"
    assert little_gwen.expected.reference_bound_subject_ids == ["subject_little_gwen"]
    assert cases["scenario_zh_explorer_rover_moon_regolith"].expected.subject_ids == [
        "subject_explorer_rover"
    ]


@pytest.mark.parametrize(
    "case",
    [case for case in SCENARIO_CASES if case.expected.stop_reason == "delegated"],
    ids=lambda case: case.case_id,
)
def test_natural_language_scene_cases_run_to_delegated_generation(
    tmp_path: Path,
    case: NaturalLanguageSceneCase,
) -> None:
    run_dir = materialize_runtime_scenario_case(root=tmp_path, case=case)

    result = run_bounded_runtime_loop(
        run_dir,
        max_steps=8,
        dry_run=True,
        response_text_by_node=case.response_text_by_node(),
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    audit = audit_runtime_run(run_dir)

    assert result.ok is True
    assert result.stop_reason == case.expected.stop_reason
    assert state["phase"] == case.expected.final_phase
    assert [item["subject_id"] for item in state["scene_spec"]["subjects"]] == case.expected.subject_ids
    assert len(state["reference_bindings"]) == case.expected.reference_binding_count
    assert bool(state["concept_bundle"]["prompt_pack"]) is case.expected.has_prompt_pack
    if case.expected.scene_environment_type:
        assert state["scene_spec"]["environment"]["environment_type"] == case.expected.scene_environment_type
    if case.expected.subject_asset_ids_required:
        assert _subject_asset_ids_required(state) == case.expected.subject_asset_ids_required
    if case.expected.procedural_object_ids:
        assert _procedural_object_ids(state) == case.expected.procedural_object_ids
    if case.expected.reference_bound_subject_ids:
        assert _reference_bound_subject_ids(state) == case.expected.reference_bound_subject_ids
    if case.expected.concept_requirement_types:
        requirements = state["concept_bundle"]["prompt_pack"]["image_requirements"]
        assert [item["output_type"] for item in requirements] == case.expected.concept_requirement_types
    if case.case_id == "scenario_zh_wuthering_chibi_beach_duo":
        florollo = state["scene_spec"]["subjects"][1]
        assert florollo["subject_id"] == "subject_florollo_chibi"
        assert florollo["source_text_span"] == "弗糯糯"
        assert florollo["canonical_identity"] == "鸣潮 角色 弗洛洛"
    if case.case_id == "scenario_zh_little_gwen_chessboard_ref":
        prompt_pack = state["concept_bundle"]["prompt_pack"]
        requirements = {item["requirement_id"]: item for item in prompt_pack["image_requirements"]}
        subject_requirement = requirements["subject_concept:subject_little_gwen"]
        target_requirement = requirements["target_render:final_preview"]
        assert subject_requirement["generation_mode"] == "image_guided"
        assert subject_requirement["must_use_image_inputs"] is True
        assert subject_requirement["input_reference_image_ids"] == ["image_little_gwen_ref"]
        assert set(target_requirement["source_requirement_ids"]) == {
            "subject_concept:subject_little_gwen",
            "scene_concept:1",
        }
        assert target_requirement["generation_mode"] == "multi_image_composite"
        assert "No characters" in prompt_pack["scene_prompts"][0]
    if case.case_id == "scenario_zh_explorer_rover_moon_regolith":
        prompt_pack = state["concept_bundle"]["prompt_pack"]
        requirements = {item["requirement_id"]: item for item in prompt_pack["image_requirements"]}
        assert requirements["target_render:final_preview"]["source_requirement_ids"] == [
            "subject_concept:subject_explorer_rover",
            "scene_concept:1",
        ]
        assert "No rover" in prompt_pack["scene_prompts"][0]
    assert result.iterations[-1].domain_tool_name == "generate_concept_images"
    assert audit.ok is True
    _assert_prompt_outputs_are_reviewable(run_dir)


def test_unbound_reference_case_waits_for_user_before_llm_or_generation(tmp_path: Path) -> None:
    case = next(case for case in SCENARIO_CASES if case.case_id == "scenario_missing_reference_binding")
    run_dir = materialize_runtime_scenario_case(root=tmp_path, case=case)

    result = run_bounded_runtime_loop(run_dir, max_steps=3, dry_run=True)
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.stop_reason == "waiting_user"
    assert result.iterations[0].execution_status == case.expected.first_runtime_status
    assert result.iterations[0].node_name is None
    assert state["phase"] == "INTAKE"
    assert state["scene_spec"] is None
    assert state["concept_bundle"] is None


def _assert_prompt_outputs_are_reviewable(run_dir: Path) -> None:
    records = [
        json.loads(line)
        for line in (run_dir / "runtime_execution.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    output_paths = [Path(record["output_json"]) for record in records if record.get("output_json")]
    assert output_paths
    for output_path in output_paths:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        llm_result = payload["llm_result"]
        system_prompt = llm_result["prompt"]["system_prompt"]
        assert "context_json:" in system_prompt
        assert "output_json_schema:" in system_prompt
        assert "Do not execute tools" in system_prompt
        assert "Do not call raw MCP tools" in system_prompt
        assert "Do not invent artifact ids" in system_prompt
        assert payload["context_json"] is not None
        assert llm_result["parsed_output"] is not None


def _subject_asset_ids_required(state: dict) -> list[str]:
    return [
        subject["subject_id"]
        for subject in state["scene_spec"]["subjects"]
        if subject.get("needs_3d_asset") and subject.get("asset_strategy") in {"hunyuan3d_img2asset", "existing_asset"}
    ]


def _procedural_object_ids(state: dict) -> list[str]:
    return [
        subject["subject_id"]
        for subject in state["scene_spec"]["subjects"]
        if subject.get("asset_strategy") in {"procedural_blender", "scene_service_component", "blender_primitive"}
    ]


def _reference_bound_subject_ids(state: dict) -> list[str]:
    return [
        subject["subject_id"]
        for subject in state["scene_spec"]["subjects"]
        if subject.get("reference_image_ids")
    ]
