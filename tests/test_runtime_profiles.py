import pytest

from agent_runtime.runtime_profiles import get_hunyuan3d_profile, hunyuan3d_profile_public_summary
from agent_runtime.runtime_profiles import (
    HUNYUAN3D_GENERATION_PROFILES,
    hunyuan3d_profile_restart_impact,
    select_hunyuan3d_profile_for_subject,
)
from agent_runtime.state import SubjectSpec


def test_hunyuan3d_default_profile_matches_current_high_quality_service_defaults() -> None:
    profile = get_hunyuan3d_profile()

    assert profile.profile_id == "hq_textured_1m_768"
    assert profile.texture is True
    assert profile.octree_resolution == 768
    assert profile.face_count == 1000000
    assert profile.num_inference_steps == 50
    assert profile.suggested_executor == "sub_agent"


def test_hunyuan3d_fast_smoke_profile_is_explicitly_lower_quality() -> None:
    profile = get_hunyuan3d_profile("fast_shape_50k_768")
    kwargs = profile.payload_kwargs(seed=7, randomize_seed=False)

    assert kwargs["texture"] is False
    assert kwargs["face_count"] == 50000
    assert kwargs["num_inference_steps"] == 30
    assert kwargs["seed"] == 7
    assert kwargs["randomize_seed"] is False


def test_hunyuan3d_profile_summary_includes_payload_defaults() -> None:
    summary = hunyuan3d_profile_public_summary("hq_shape_1m_768")

    assert summary["payload_defaults"]["texture"] is False
    assert summary["payload_defaults"]["octree_resolution"] == 768
    assert summary["payload_defaults"]["face_count"] == 1000000


def test_unknown_hunyuan3d_profile_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown Hunyuan3D generation profile"):
        get_hunyuan3d_profile("missing")


def test_current_hunyuan3d_profiles_are_request_only_and_do_not_require_restart() -> None:
    for profile_id in HUNYUAN3D_GENERATION_PROFILES:
        impact = hunyuan3d_profile_restart_impact(profile_id)

        assert impact.restart_required is False
        assert "texture" in impact.request_payload_fields
        assert "face_count" in impact.request_payload_fields
        assert "texture_resolution" in impact.service_start_fields
        assert "max_num_view" in impact.service_start_fields


def test_balanced_subject_profile_selector_keeps_only_hero_characters_textured() -> None:
    hero = _subject("subject_hero", category="character", priority="hero")
    important = _subject("subject_sidekick", category="character", priority="important")
    prop = _subject("subject_prop", category="prop", priority="important")

    assert select_hunyuan3d_profile_for_subject(hero).profile_id == "hq_textured_1m_768"
    assert select_hunyuan3d_profile_for_subject(important).profile_id == "hq_shape_1m_768"
    assert select_hunyuan3d_profile_for_subject(prop).profile_id == "fast_shape_50k_768"


def test_throughput_subject_profile_selector_uses_shape_and_draft_profiles() -> None:
    hero = _subject("subject_hero_vehicle", category="vehicle", priority="hero")
    background = _subject("subject_bg", category="environment_asset", priority="background")

    assert (
        select_hunyuan3d_profile_for_subject(hero, policy="throughput_per_subject").profile_id
        == "hq_shape_1m_768"
    )
    assert (
        select_hunyuan3d_profile_for_subject(background, policy="throughput_per_subject").profile_id
        == "draft_shape_100k_512"
    )


def _subject(subject_id: str, *, category: str, priority: str) -> SubjectSpec:
    return SubjectSpec(
        subject_id=subject_id,
        display_name=subject_id,
        category=category,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        description=f"{subject_id} test subject",
    )
