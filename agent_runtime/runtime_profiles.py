"""Runtime service profiles for the V1 agent runtime.

These profiles describe the already-running local services and their intended
generation presets. They do not start services and do not replace the existing
service adapters.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RuntimeExecutor = Literal["main_runtime", "background_worker", "sub_agent", "user", "external_service"]
RuntimeDurationClass = Literal["interactive", "short", "medium", "long"]
Hunyuan3DProfileSelectionPolicy = Literal["global", "balanced_per_subject", "throughput_per_subject"]

HUNYUAN3D_REQUEST_PAYLOAD_FIELDS = frozenset(
    {
        "image",
        "remove_background",
        "texture",
        "seed",
        "randomize_seed",
        "octree_resolution",
        "num_inference_steps",
        "guidance_scale",
        "num_chunks",
        "face_count",
    }
)
HUNYUAN3D_SERVICE_START_FIELDS = frozenset(
    {
        "model_path",
        "subfolder",
        "texgen_model_path",
        "dino_ckpt_path",
        "texture_resolution",
        "max_num_view",
        "low_vram_mode",
        "cache_path",
        "device",
        "mc_algo",
        "enable_flashvdm",
        "compile",
        "host",
        "port",
    }
)


class RuntimeServiceConfig(BaseModel):
    """Known local service surfaces used by the runtime."""

    root: str = "/home/team/zouzhiyuan/image23D_Agent"
    hunyuan3d_base_url: str = "http://127.0.0.1:8091"
    worldmirror_base_url: str = "http://127.0.0.1:8081"
    glb_viewer_base_url: str = "http://127.0.0.1:8092"
    blender_web_http_url: str = "http://127.0.0.1:8300"
    blender_web_https_url: str = "https://127.0.0.1:8301"
    blender_mcp_host: str = "127.0.0.1"
    blender_mcp_port: int = 9876
    hunyuan3d_start_texture_resolution: int = 768
    hunyuan3d_start_max_num_view: int = 8
    hunyuan3d_low_vram_mode: bool = True
    default_hunyuan3d_profile_id: str = "hq_textured_1m_768"
    default_hunyuan3d_profile_policy: Hunyuan3DProfileSelectionPolicy = "balanced_per_subject"
    hunyuan3d_safe_concurrency_limit: int = 1


class Hunyuan3DGenerationProfile(BaseModel):
    """A named payload preset for the existing Hunyuan3D FastAPI service."""

    profile_id: str
    label: str
    description: str
    texture: bool = True
    remove_background: bool = True
    seed: int = Field(default=1234, ge=0, le=2**32 - 1)
    randomize_seed: bool = True
    octree_resolution: int = Field(default=768, ge=64, le=1024)
    num_inference_steps: int = Field(default=50, ge=1, le=100)
    guidance_scale: float = Field(default=5.0, ge=0.1, le=20.0)
    num_chunks: int = Field(default=200000, ge=1000, le=5000000)
    face_count: int = Field(default=1000000, ge=1000, le=1000000)
    duration_class: RuntimeDurationClass = "long"
    suggested_executor: RuntimeExecutor = "sub_agent"
    notes: list[str] = Field(default_factory=list)

    def payload_kwargs(self, **overrides: Any) -> dict[str, Any]:
        """Return adapter kwargs for Hunyuan3DServiceAdapter.build_payload."""

        data = {
            "remove_background": self.remove_background,
            "texture": self.texture,
            "seed": self.seed,
            "randomize_seed": self.randomize_seed,
            "octree_resolution": self.octree_resolution,
            "num_inference_steps": self.num_inference_steps,
            "guidance_scale": self.guidance_scale,
            "num_chunks": self.num_chunks,
            "face_count": self.face_count,
        }
        data.update({key: value for key, value in overrides.items() if value is not None})
        return data


class Hunyuan3DProfileRestartImpact(BaseModel):
    """Whether a profile can run against the currently started FastAPI service."""

    profile_id: str
    restart_required: bool
    request_payload_fields: list[str]
    service_start_fields: list[str]
    service_start_contract: dict[str, Any]
    reason: str
    concurrency_note: str


class Hunyuan3DSubjectProfileSelection(BaseModel):
    """Per-subject Hunyuan3D profile routing decision."""

    subject_id: str
    profile_id: str
    category: str | None = None
    priority: str | None = None
    policy: Hunyuan3DProfileSelectionPolicy
    payload_kwargs: dict[str, Any]
    restart_required: bool
    reason: str


HUNYUAN3D_GENERATION_PROFILES: dict[str, Hunyuan3DGenerationProfile] = {
    "hq_textured_1m_768": Hunyuan3DGenerationProfile(
        profile_id="hq_textured_1m_768",
        label="High quality textured 1M/768",
        description="Default high-quality Hunyuan3D asset generation matching the current 768 texture service.",
        texture=True,
        octree_resolution=768,
        num_inference_steps=50,
        num_chunks=200000,
        face_count=1000000,
        duration_class="long",
        suggested_executor="sub_agent",
        notes=[
            "Matches the current FastAPI service started with --texture-resolution 768.",
            "High face count and texture generation should be treated as a long-running job.",
        ],
    ),
    "fast_shape_50k_768": Hunyuan3DGenerationProfile(
        profile_id="fast_shape_50k_768",
        label="Fast textured 50K/768",
        description="Lower-face-count textured profile for routine assets and throughput-sensitive full runs.",
        texture=True,
        octree_resolution=768,
        num_inference_steps=30,
        num_chunks=200000,
        face_count=50000,
        duration_class="long",
        suggested_executor="sub_agent",
        notes=[
            "Keeps texture generation enabled while reducing geometry steps and face count.",
            "Treat as a live generation job; lower face count does not make texture generation instant.",
        ],
    ),
}


def get_hunyuan3d_profile(profile_id: str | None = None) -> Hunyuan3DGenerationProfile:
    selected = profile_id or RuntimeServiceConfig().default_hunyuan3d_profile_id
    try:
        return HUNYUAN3D_GENERATION_PROFILES[selected]
    except KeyError as exc:
        available = ", ".join(sorted(HUNYUAN3D_GENERATION_PROFILES))
        raise KeyError(f"unknown Hunyuan3D generation profile: {selected}; available: {available}") from exc


def hunyuan3d_profile_public_summary(profile_id: str | None = None) -> dict[str, Any]:
    profile = get_hunyuan3d_profile(profile_id)
    data = profile.model_dump(mode="json") if hasattr(profile, "model_dump") else profile.dict()
    data["payload_defaults"] = profile.payload_kwargs()
    data["restart_impact"] = hunyuan3d_profile_restart_impact(profile.profile_id).model_dump(mode="json")
    return data


def resolve_hunyuan3d_generation_kwargs(profile_id: str | None = None, **overrides: Any) -> dict[str, Any]:
    """Merge a named profile with explicit non-None overrides."""

    profile = get_hunyuan3d_profile(profile_id)
    return profile.payload_kwargs(**overrides)


def hunyuan3d_profile_restart_impact(
    profile_id: str | None = None,
    *,
    service_config: RuntimeServiceConfig | None = None,
) -> Hunyuan3DProfileRestartImpact:
    """Report whether a profile changes service-start-only Hunyuan3D settings."""

    config = service_config or RuntimeServiceConfig()
    profile = get_hunyuan3d_profile(profile_id)
    payload = profile.payload_kwargs()
    request_fields = sorted(key for key in payload if key in HUNYUAN3D_REQUEST_PAYLOAD_FIELDS)
    return Hunyuan3DProfileRestartImpact(
        profile_id=profile.profile_id,
        restart_required=False,
        request_payload_fields=request_fields,
        service_start_fields=sorted(HUNYUAN3D_SERVICE_START_FIELDS),
        service_start_contract={
            "texture_resolution": config.hunyuan3d_start_texture_resolution,
            "max_num_view": config.hunyuan3d_start_max_num_view,
            "low_vram_mode": config.hunyuan3d_low_vram_mode,
            "base_url": config.hunyuan3d_base_url,
        },
        reason=(
            "Current Hunyuan3D profiles only set request payload fields accepted by "
            "/send and do not override model path, texgen model path, texture "
            "resolution, max view count, cache path, or device startup options."
        ),
        concurrency_note=(
            "The local /send endpoint accepts multiple requests by starting threads, "
            "but ModelWorker.generate does not acquire a real queue/semaphore. Keep "
            "the safe default at one active Hunyuan3D job per service unless a live "
            "bounded concurrency canary proves otherwise."
        ),
    )


def select_hunyuan3d_profile_for_subject(
    subject: Any,
    *,
    policy: Hunyuan3DProfileSelectionPolicy = "balanced_per_subject",
    default_profile_id: str | None = None,
) -> Hunyuan3DSubjectProfileSelection:
    """Select a request-level Hunyuan3D profile for one SceneSpec-like subject."""

    subject_id = str(_subject_attr(subject, "subject_id", "subject"))
    category = _optional_str(_subject_attr(subject, "category", None))
    priority = _optional_str(_subject_attr(subject, "priority", None)) or "important"
    fallback = default_profile_id or RuntimeServiceConfig().default_hunyuan3d_profile_id
    profile_id, reason = _profile_id_for_subject(
        category=category,
        priority=priority,
        policy=policy,
        fallback_profile_id=fallback,
    )
    profile = get_hunyuan3d_profile(profile_id)
    impact = hunyuan3d_profile_restart_impact(profile.profile_id)
    return Hunyuan3DSubjectProfileSelection(
        subject_id=subject_id,
        profile_id=profile.profile_id,
        category=category,
        priority=priority,
        policy=policy,
        payload_kwargs=profile.payload_kwargs(),
        restart_required=impact.restart_required,
        reason=reason,
    )


def select_hunyuan3d_profiles_for_subjects(
    subjects: list[Any],
    *,
    policy: Hunyuan3DProfileSelectionPolicy = "balanced_per_subject",
    default_profile_id: str | None = None,
) -> dict[str, Hunyuan3DSubjectProfileSelection]:
    """Build a stable subject_id -> profile decision map."""

    return {
        selection.subject_id: selection
        for selection in (
            select_hunyuan3d_profile_for_subject(
                subject,
                policy=policy,
                default_profile_id=default_profile_id,
            )
            for subject in subjects
        )
    }


def _profile_id_for_subject(
    *,
    category: str | None,
    priority: str,
    policy: Hunyuan3DProfileSelectionPolicy,
    fallback_profile_id: str,
) -> tuple[str, str]:
    if policy == "global":
        return fallback_profile_id, "global profile override"

    if policy == "throughput_per_subject":
        if priority == "hero" and category in {"character", "animal", "vehicle"}:
            return "hq_textured_1m_768", "throughput policy keeps hero subjects on the high-quality textured profile"
        return "fast_shape_50k_768", "throughput policy uses the fast textured 50K profile for all non-hero assets"

    if priority == "hero" and category in {"character", "animal"}:
        return "hq_textured_1m_768", "balanced policy keeps hero organic subjects textured"
    if priority == "hero" and category == "vehicle":
        return "hq_textured_1m_768", "balanced policy keeps hero vehicles on the high-quality textured profile"
    if category in {"character", "animal"}:
        return "hq_textured_1m_768", "balanced policy keeps character/animal subjects on the high-quality textured profile"
    if category in {"vehicle", "furniture"}:
        return "fast_shape_50k_768", "balanced policy uses the fast textured profile for non-hero vehicle/furniture assets"
    if category in {"prop", "architecture_part", "environment_asset"}:
        return "fast_shape_50k_768", "balanced policy uses the fast textured profile for simple scene assets"
    return fallback_profile_id, "balanced policy fallback profile"


def _subject_attr(subject: Any, key: str, default: Any) -> Any:
    if isinstance(subject, dict):
        return subject.get(key, default)
    return getattr(subject, key, default)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
