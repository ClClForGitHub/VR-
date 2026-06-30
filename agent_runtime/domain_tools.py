"""Domain-tool registry from DOC-006.

The registry is deliberately small and deterministic: LLM nodes should receive
only the domain tools allowed in the current workflow phase, never the raw MCP
or Blender Python surface.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent_runtime.state import WorkflowPhase


RiskLevel = Literal["low", "medium", "high"]


class DomainToolSpec(BaseModel):
    name: str
    description: str
    allowed_phases: list[WorkflowPhase]
    implementation: str
    underlying_tools: list[str] = Field(default_factory=list)
    llm_visible: bool = True
    risk_level: RiskLevel = "medium"


TOOLS_BY_PHASE: dict[WorkflowPhase, list[str]] = {
    WorkflowPhase.SCENE_SPEC_DRAFT: [
        "compile_scene_spec",
        "bind_reference_images",
    ],
    WorkflowPhase.CONCEPT_GENERATION: [
        "generate_concept_images",
    ],
    WorkflowPhase.CONCEPT_REVIEW: [
        "parse_review_patch",
        "regenerate_concept_images",
        "approve_concept",
    ],
    WorkflowPhase.SUBJECT_ASSET_GENERATION: [
        "build_subject_asset",
        "check_subject_asset_quality",
    ],
    WorkflowPhase.SUBJECT_ASSET_QA: [
        "check_subject_asset_quality",
        "render_preview",
    ],
    WorkflowPhase.SCENE_ASSET_GENERATION: [
        "build_scene_asset",
        "adapt_scene_asset",
    ],
    WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION: [
        "get_blender_scene_summary",
        "import_subject_asset",
        "import_scene_asset",
        "place_subject",
        "setup_camera",
        "setup_lighting",
        "export_viewer_scene",
        "render_preview",
    ],
    WorkflowPhase.BLENDER_EDIT: [
        "get_blender_scene_summary",
        "move_subject",
        "rotate_subject",
        "scale_subject",
        "delete_subject",
        "replace_subject_asset",
        "update_camera",
        "update_lighting",
        "set_simple_material",
        "export_viewer_scene",
        "render_preview",
    ],
    WorkflowPhase.DELIVERY: [
        "save_blend_file",
        "export_scene_package",
    ],
}


DOMAIN_TOOL_SPECS: dict[str, DomainToolSpec] = {
    "compile_scene_spec": DomainToolSpec(
        name="compile_scene_spec",
        description="Compile structured scene understanding into a validated SceneSpec.",
        allowed_phases=[WorkflowPhase.SCENE_SPEC_DRAFT],
        implementation="agent_runtime.state",
        risk_level="low",
    ),
    "bind_reference_images": DomainToolSpec(
        name="bind_reference_images",
        description="Validate explicit user bindings for uploaded reference images.",
        allowed_phases=[WorkflowPhase.SCENE_SPEC_DRAFT],
        implementation="agent_runtime.state",
        risk_level="low",
    ),
    "generate_concept_images": DomainToolSpec(
        name="generate_concept_images",
        description="Generate fixed V1 concept image classes from a ConceptPromptPack.",
        allowed_phases=[WorkflowPhase.CONCEPT_GENERATION],
        implementation="image_generation_adapter",
        risk_level="medium",
    ),
    "parse_review_patch": DomainToolSpec(
        name="parse_review_patch",
        description="Parse user concept feedback into a structured ReviewPatch.",
        allowed_phases=[WorkflowPhase.CONCEPT_REVIEW],
        implementation="llm_node",
        risk_level="low",
    ),
    "regenerate_concept_images": DomainToolSpec(
        name="regenerate_concept_images",
        description="Regenerate concept images from structured feedback.",
        allowed_phases=[WorkflowPhase.CONCEPT_REVIEW],
        implementation="image_generation_adapter",
        risk_level="medium",
    ),
    "approve_concept": DomainToolSpec(
        name="approve_concept",
        description="Mark the current ConceptBundle as approved.",
        allowed_phases=[WorkflowPhase.CONCEPT_REVIEW],
        implementation="agent_runtime.state",
        risk_level="low",
    ),
    "build_subject_asset": DomainToolSpec(
        name="build_subject_asset",
        description="Call the existing Hunyuan3D service to create a subject GLB asset.",
        allowed_phases=[WorkflowPhase.SUBJECT_ASSET_GENERATION],
        implementation="hunyuan3d_service_adapter",
        underlying_tools=["Hunyuan3D-2.1 FastAPI"],
        risk_level="medium",
    ),
    "check_subject_asset_quality": DomainToolSpec(
        name="check_subject_asset_quality",
        description="Check generated subject asset metadata and visual usability.",
        allowed_phases=[WorkflowPhase.SUBJECT_ASSET_GENERATION, WorkflowPhase.SUBJECT_ASSET_QA],
        implementation="agent_runtime.artifacts",
        risk_level="low",
    ),
    "build_scene_asset": DomainToolSpec(
        name="build_scene_asset",
        description="Call the existing HY-World/WorldMirror service to create a scene asset.",
        allowed_phases=[WorkflowPhase.SCENE_ASSET_GENERATION],
        implementation="worldmirror_service_adapter",
        underlying_tools=["HY-World-2.0"],
        risk_level="medium",
    ),
    "adapt_scene_asset": DomainToolSpec(
        name="adapt_scene_asset",
        description="Adapt scene generation output into Blender-importable assets.",
        allowed_phases=[WorkflowPhase.SCENE_ASSET_GENERATION],
        implementation="scene_asset_adapter",
        risk_level="medium",
    ),
    "get_blender_scene_summary": DomainToolSpec(
        name="get_blender_scene_summary",
        description="Read the current authoritative Blender scene summary through the Blender MCP channel.",
        allowed_phases=[WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION, WorkflowPhase.BLENDER_EDIT],
        implementation="agent_runtime.blender_mcp.sync_blender_scene_state_from_objects_summary",
        underlying_tools=["blender_lab.get_objects_summary"],
        risk_level="low",
    ),
    "import_subject_asset": DomainToolSpec(
        name="import_subject_asset",
        description="Import a subject GLB into the authoritative Blender scene.",
        allowed_phases=[WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab", "tools/compose_blender_scene.py"],
        risk_level="medium",
    ),
    "import_scene_asset": DomainToolSpec(
        name="import_scene_asset",
        description="Import a scene GLB into the authoritative Blender scene.",
        allowed_phases=[WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab", "tools/compose_blender_scene.py"],
        risk_level="medium",
    ),
    "place_subject": DomainToolSpec(
        name="place_subject",
        description="Apply a validated transform to place a subject in Blender.",
        allowed_phases=[WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "setup_camera": DomainToolSpec(
        name="setup_camera",
        description="Create or update the Blender camera for the current scene.",
        allowed_phases=[WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "setup_lighting": DomainToolSpec(
        name="setup_lighting",
        description="Create or update Blender lighting for the current scene.",
        allowed_phases=[WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "export_viewer_scene": DomainToolSpec(
        name="export_viewer_scene",
        description="Export a GLB/glTF viewer snapshot and scene_state.json from Blender.",
        allowed_phases=[WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION, WorkflowPhase.BLENDER_EDIT],
        implementation="ScenePreviewExporter",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "render_preview": DomainToolSpec(
        name="render_preview",
        description="Render a high-quality Blender preview using the existing preview script.",
        allowed_phases=[
            WorkflowPhase.SUBJECT_ASSET_QA,
            WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
            WorkflowPhase.BLENDER_EDIT,
        ],
        implementation="agent_runtime.script_adapters.build_render_glb_preview_command",
        underlying_tools=["tools/render_glb_preview.py"],
        risk_level="medium",
    ),
    "move_subject": DomainToolSpec(
        name="move_subject",
        description="Move a subject object in Blender.",
        allowed_phases=[WorkflowPhase.BLENDER_EDIT],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "rotate_subject": DomainToolSpec(
        name="rotate_subject",
        description="Rotate a subject object in Blender.",
        allowed_phases=[WorkflowPhase.BLENDER_EDIT],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "scale_subject": DomainToolSpec(
        name="scale_subject",
        description="Scale a subject object in Blender.",
        allowed_phases=[WorkflowPhase.BLENDER_EDIT],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "delete_subject": DomainToolSpec(
        name="delete_subject",
        description="Delete a subject object from Blender after validation.",
        allowed_phases=[WorkflowPhase.BLENDER_EDIT],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="high",
    ),
    "replace_subject_asset": DomainToolSpec(
        name="replace_subject_asset",
        description="Replace one subject asset while preserving scene context.",
        allowed_phases=[WorkflowPhase.BLENDER_EDIT],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab", "Hunyuan3D-2.1 FastAPI"],
        risk_level="high",
    ),
    "update_camera": DomainToolSpec(
        name="update_camera",
        description="Update camera location, angle, and focal settings.",
        allowed_phases=[WorkflowPhase.BLENDER_EDIT],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "update_lighting": DomainToolSpec(
        name="update_lighting",
        description="Update lighting style and intensity.",
        allowed_phases=[WorkflowPhase.BLENDER_EDIT],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "set_simple_material": DomainToolSpec(
        name="set_simple_material",
        description="Apply simple material changes to selected objects.",
        allowed_phases=[WorkflowPhase.BLENDER_EDIT],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "save_blend_file": DomainToolSpec(
        name="save_blend_file",
        description="Save the authoritative Blender file for delivery.",
        allowed_phases=[WorkflowPhase.DELIVERY],
        implementation="BlenderDomainTools",
        underlying_tools=["blender_lab"],
        risk_level="medium",
    ),
    "export_scene_package": DomainToolSpec(
        name="export_scene_package",
        description="Create the final delivery package.",
        allowed_phases=[WorkflowPhase.DELIVERY],
        implementation="DeliveryPackager",
        risk_level="medium",
    ),
}


def allowed_tool_names(phase: WorkflowPhase) -> list[str]:
    return list(TOOLS_BY_PHASE.get(phase, []))


def allowed_tool_specs(phase: WorkflowPhase) -> list[DomainToolSpec]:
    return [DOMAIN_TOOL_SPECS[name] for name in allowed_tool_names(phase)]


def is_tool_allowed(phase: WorkflowPhase, tool_name: str) -> bool:
    return tool_name in TOOLS_BY_PHASE.get(phase, [])


def assert_tool_allowed(phase: WorkflowPhase, tool_name: str) -> None:
    if not is_tool_allowed(phase, tool_name):
        allowed = ", ".join(allowed_tool_names(phase)) or "<none>"
        raise ValueError(f"tool {tool_name!r} is not allowed in phase {phase.value}; allowed: {allowed}")


def validate_registry() -> None:
    missing_specs = sorted(
        {
            name
            for names in TOOLS_BY_PHASE.values()
            for name in names
            if name not in DOMAIN_TOOL_SPECS
        }
    )
    if missing_specs:
        raise ValueError(f"TOOLS_BY_PHASE references missing specs: {missing_specs}")

    for phase, names in TOOLS_BY_PHASE.items():
        for name in names:
            spec = DOMAIN_TOOL_SPECS[name]
            if phase not in spec.allowed_phases:
                raise ValueError(f"tool {name!r} is listed for {phase.value} but spec does not allow it")
