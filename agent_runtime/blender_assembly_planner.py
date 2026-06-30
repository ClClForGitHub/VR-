"""Deterministic Blender assembly plan helpers.

This module turns the current `SceneSpec` into the small JSON contract consumed
by `tools/compose_blender_scene.py`. It is intentionally a thin planning layer:
LLM nodes can later emit the same contract, while the existing compose script
remains the execution boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.state import AgentProjectState, SceneSpec, SubjectSpec


class ComposeScenePlan(BaseModel):
    plan_id: str
    planner: Literal["deterministic_v1"] = "deterministic_v1"
    created_at: str = Field(default_factory=utc_now_iso)
    subject_id: str | None = None
    scene_asset_id: str | None = None
    subject_asset_id: str | None = None
    target_region: str = "front_left"
    target_region_normalized: tuple[float, float] = (-0.18, 0.18)
    target_height_ratio: float = 0.42
    camera_direction: tuple[float, float, float] = (1.25, -1.55, 0.85)
    camera_distance_multiplier: float = 2.8
    camera_ortho_scale_factor: float = 1.55
    render_resolution: tuple[int, int] = (1400, 900)
    placement_reason: str = "Fallback placement: subject visible in front-left third of the scene."
    camera_reason: str = "Fallback camera: three-quarter orthographic preview."
    notes: str | None = None


def build_compose_scene_plan(
    state: AgentProjectState,
    *,
    scene_asset_id: str = "workflow_scene_glb",
    subject_asset_id: str = "workflow_subject_glb",
) -> ComposeScenePlan:
    """Build a deterministic compose plan from the authoritative state."""

    scene_spec = state.scene_spec
    subject = _primary_subject(scene_spec) if scene_spec is not None else None
    target_region, normalized, placement_reason = _placement_from_scene(scene_spec, subject)
    camera_direction, distance, ortho, camera_reason = _camera_from_scene(scene_spec)
    height_ratio, scale_reason = _height_ratio_from_subject(subject)
    subject_id = subject.subject_id if subject is not None else None
    notes = "; ".join(part for part in [scale_reason, _scene_notes(scene_spec)] if part)
    return ComposeScenePlan(
        plan_id=f"compose_plan_{subject_id or 'fallback'}_v1",
        subject_id=subject_id,
        scene_asset_id=scene_asset_id,
        subject_asset_id=subject_asset_id,
        target_region=target_region,
        target_region_normalized=normalized,
        target_height_ratio=height_ratio,
        camera_direction=camera_direction,
        camera_distance_multiplier=distance,
        camera_ortho_scale_factor=ortho,
        placement_reason=placement_reason,
        camera_reason=camera_reason,
        notes=notes or None,
    )


def _primary_subject(scene_spec: SceneSpec | None) -> SubjectSpec | None:
    if scene_spec is None or not scene_spec.subjects:
        return None
    priority_rank = {"hero": 0, "important": 1, "background": 2}
    return sorted(scene_spec.subjects, key=lambda item: (priority_rank.get(item.priority, 1), item.subject_id))[0]


def _placement_from_scene(
    scene_spec: SceneSpec | None,
    subject: SubjectSpec | None,
) -> tuple[str, tuple[float, float], str]:
    text_parts: list[str] = []
    if subject is not None and subject.placement_hint:
        text_parts.append(subject.placement_hint)
    if scene_spec is not None and subject is not None:
        for relation in scene_spec.spatial_relations:
            if relation.source_subject_id != subject.subject_id:
                continue
            text_parts.extend(
                str(part)
                for part in [relation.relation, relation.target_region, relation.distance_hint, relation.notes]
                if part
            )
    text = " ".join(text_parts).lower()
    if any(token in text for token in ["center", "middle", "中央", "中心", "centered_in"]):
        return "center", (0.0, 0.0), "SceneSpec requests centered placement."
    if any(token in text for token in ["right", "右"]):
        return "front_right", (0.20, 0.14), "SceneSpec requests right-side placement."
    if any(token in text for token in ["left", "左"]):
        return "front_left", (-0.20, 0.14), "SceneSpec requests left-side placement."
    if any(token in text for token in ["front", "前景", "in_front_of"]):
        return "front_center", (0.0, -0.22), "SceneSpec requests foreground placement."
    if any(token in text for token in ["behind", "back", "后方"]):
        return "back_center", (0.0, 0.24), "SceneSpec requests background placement."
    if any(token in text for token in ["near", "beside", "旁边", "附近"]):
        return "near_scene_focus", (-0.12, 0.12), "SceneSpec requests nearby placement."
    return "front_left", (-0.18, 0.18), "No explicit placement hint; using front-left composition."


def _height_ratio_from_subject(subject: SubjectSpec | None) -> tuple[float, str]:
    if subject is None:
        return 0.42, "No subject spec; using default target height ratio 0.42."
    text = " ".join(str(part) for part in [subject.scale_hint, subject.category, subject.priority] if part).lower()
    if any(token in text for token in ["tiny", "small", "mini", "小"]):
        return 0.24, "Subject scale hint suggests a small asset."
    if any(token in text for token in ["large", "giant", "tall", "huge", "大"]):
        return 0.50, "Subject scale hint suggests a large asset."
    if subject.priority == "background":
        return 0.20, "Background subject uses a smaller height ratio."
    if subject.priority == "hero":
        return 0.44, "Hero subject uses a prominent height ratio."
    if subject.category in {"prop", "furniture"}:
        return 0.30, "Prop/furniture subject uses a moderate height ratio."
    return 0.38, "Important subject uses a balanced height ratio."


def _camera_from_scene(scene_spec: SceneSpec | None) -> tuple[tuple[float, float, float], float, float, str]:
    if scene_spec is None:
        return (1.25, -1.55, 0.85), 2.8, 1.55, "No SceneSpec camera; using fallback three-quarter camera."
    text = " ".join(
        str(part)
        for part in [
            scene_spec.camera.shot_type,
            scene_spec.camera.angle,
            scene_spec.camera.framing,
            scene_spec.camera.lens_hint,
        ]
        if part
    ).lower()
    direction = (1.25, -1.55, 0.85)
    distance = 2.8
    ortho = 1.55
    reason = "SceneSpec camera mapped to medium three-quarter orthographic preview."
    if any(token in text for token in ["close", "portrait", "特写", "近景"]):
        distance = 2.25
        ortho = 1.18
        reason = "SceneSpec requests close framing."
    elif any(token in text for token in ["wide", "full", "全景", "广角"]):
        distance = 3.35
        ortho = 1.90
        reason = "SceneSpec requests wide/full-scene framing."
    if any(token in text for token in ["front", "正面"]):
        direction = (0.0, -1.75, 0.65)
        reason += " Front angle requested."
    elif any(token in text for token in ["high", "top", "俯视", "高角度"]):
        direction = (1.0, -1.35, 1.35)
        reason += " High angle requested."
    elif any(token in text for token in ["low", "仰视", "低角度"]):
        direction = (1.35, -1.65, 0.45)
        reason += " Low angle requested."
    return direction, distance, ortho, reason


def _scene_notes(scene_spec: SceneSpec | None) -> str | None:
    if scene_spec is None:
        return None
    notes = []
    if scene_spec.environment.ground_surface:
        notes.append(f"ground={scene_spec.environment.ground_surface}")
    if scene_spec.lighting.description:
        notes.append(f"lighting={scene_spec.lighting.description}")
    return ", ".join(notes) if notes else None
