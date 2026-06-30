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
    "hq_shape_1m_768": Hunyuan3DGenerationProfile(
        profile_id="hq_shape_1m_768",
        label="High quality shape-only 1M/768",
        description="High-detail geometry without texture generation.",
        texture=False,
        octree_resolution=768,
        num_inference_steps=50,
        num_chunks=200000,
        face_count=1000000,
        duration_class="long",
        suggested_executor="sub_agent",
        notes=["Useful when texture generation is not needed but geometry quality still matters."],
    ),
    "fast_shape_50k_768": Hunyuan3DGenerationProfile(
        profile_id="fast_shape_50k_768",
        label="Fast shape-only smoke 50K/768",
        description="Lower-face-count shape-only smoke profile for wiring and QA checks.",
        texture=False,
        octree_resolution=768,
        num_inference_steps=30,
        num_chunks=200000,
        face_count=50000,
        duration_class="medium",
        suggested_executor="background_worker",
        notes=["This is a runtime smoke preset, not final asset quality."],
    ),
    "draft_shape_100k_512": Hunyuan3DGenerationProfile(
        profile_id="draft_shape_100k_512",
        label="Draft shape-only 100K/512",
        description="Lower octree and face count for draft generation when fast feedback matters.",
        texture=False,
        octree_resolution=512,
        num_inference_steps=20,
        num_chunks=100000,
        face_count=100000,
        duration_class="short",
        suggested_executor="background_worker",
        notes=["Only use for draft iteration; do not treat as final output."],
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
    return data


def resolve_hunyuan3d_generation_kwargs(profile_id: str | None = None, **overrides: Any) -> dict[str, Any]:
    """Merge a named profile with explicit non-None overrides."""

    profile = get_hunyuan3d_profile(profile_id)
    return profile.payload_kwargs(**overrides)
