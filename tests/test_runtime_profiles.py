import pytest

from agent_runtime.runtime_profiles import get_hunyuan3d_profile, hunyuan3d_profile_public_summary


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

