from pathlib import Path

from agent_runtime.round04_live_samples import (
    load_round04_case_manifests,
    validate_round04_case_manifests,
)


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures/live_user_samples/round04"


def test_round04_live_sample_manifests_cover_12_user_cases() -> None:
    result = validate_round04_case_manifests(FIXTURES_ROOT)
    loaded = load_round04_case_manifests(FIXTURES_ROOT)

    assert result.ok is True
    assert result.case_count == 12
    assert result.cases == [
        "case_01_tft_little_gwen",
        "case_02_wuthering_beach",
        "case_03_lunar_rover",
        "case_04_hsr_train",
        "case_05_xianxia_original",
        "case_06_cyberpunk_alley",
        "case_07_miniature_japanese_garden",
        "case_08_industrial_quadruped",
        "case_09_frieren_magic_bedroom",
        "case_10_helltaker_cafe",
        "case_11_stellar_blade_eve_tachy",
        "case_12_stellar_blade_raven_adam_xion",
    ]
    assert all((case_dir / "user_script.md").is_file() for case_dir, _manifest in loaded)


def test_round04_user_confirmed_ambiguous_cases_are_encoded() -> None:
    loaded = dict((manifest.case_id, (case_dir, manifest)) for case_dir, manifest in load_round04_case_manifests(FIXTURES_ROOT))
    case10_dir, case10 = loaded["case_10_helltaker_cafe"]
    lucifer_ref = next(image for image in case10.reference_images if image.image_id == "image_001")
    scene_ref = next(image for image in case10.reference_images if image.image_id == "image_002")

    assert lucifer_ref.declared_target_type == "subject"
    assert lucifer_ref.declared_target_id == "subject_lucifer_chibi"
    assert lucifer_ref.upload_stage == "concept_feedback_1"
    assert lucifer_ref.path == "reference_images/image_001.png"
    assert case10.reference_path(case10_dir, lucifer_ref).is_file()
    assert any("路西法" in note for note in case10.parse_notes)
    assert scene_ref.declared_target_type == "scene"
    assert scene_ref.slot == "@图片1"
    assert any("用户确认" in note for note in case10.parse_notes)

    _case4_dir, case4 = loaded["case_04_hsr_train"]
    assert any("模拟为同意" in action.text for action in case4.scripted_user_actions)
