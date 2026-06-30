"""Human-readable prompt catalog for V1 agent node review."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from agent_runtime.agent_prompts import NODE_SPECS, build_node_prompt


SAMPLE_CONTEXTS: dict[str, dict[str, Any]] = {
    "UserIntentRouter": {
        "phase": "INTAKE",
        "latest_user_turn": {
            "text": "请根据参考图生成一个可以放进 Blender 场景的主体模型。",
            "image_ids": ["image_subject_001"],
        },
        "pending_action": None,
    },
    "ReferenceBindingValidator": {
        "user_text": "图1是主体参考，图2是场景参考，图3只控制棉花质感。",
        "input_images": [
            {"image_id": "image_subject_001", "user_declared_label": "图1 主体"},
            {"image_id": "image_scene_001", "user_declared_label": "图2 场景"},
            {"image_id": "image_style_001", "user_declared_label": "图3 风格"},
        ],
        "declared_bindings": [
            {
                "image_id": "image_subject_001",
                "target_type": "subject",
                "target_id": "subject_hero",
                "usage": "subject_reference",
            },
            {
                "image_id": "image_scene_001",
                "target_type": "scene",
                "target_id": "scene_main",
                "usage": "scene_reference",
            },
            {
                "image_id": "image_style_001",
                "target_type": "style",
                "usage": "style_reference",
            },
        ],
    },
    "SceneInterpreter": {
        "user_text": "做一个软萌黄色玩偶站在小型展示台前，背景是明亮街角店铺。",
        "input_images": [
            {"image_id": "image_subject_001", "user_declared_label": "主体参考"},
            {"image_id": "image_scene_001", "user_declared_label": "街角参考"},
        ],
        "reference_bindings": [
            {
                "binding_id": "binding_subject_001",
                "image_id": "image_subject_001",
                "target_type": "subject",
                "target_id": "subject_plush",
                "usage": "subject_reference",
            },
            {
                "binding_id": "binding_scene_001",
                "image_id": "image_scene_001",
                "target_type": "scene",
                "target_id": "scene_shop_corner",
                "usage": "scene_reference",
            },
        ],
    },
    "SceneSpecCompiler": {
        "interpretation": {
            "user_goal": "Create a soft yellow plush-like hero subject in a bright street-corner shop display.",
            "subject_summaries": ["yellow plush-like hero subject"],
            "environment_summary": "bright street-corner shop display",
            "style_summary": "soft cotton texture, cute, clean display",
            "open_questions": [],
        },
        "reference_bindings": [
            {
                "binding_id": "binding_subject_001",
                "image_id": "image_subject_001",
                "target_type": "subject",
                "target_id": "subject_plush",
                "usage": "subject_reference",
            }
        ],
        "previous_scene_spec": None,
    },
    "ConceptPromptPlanner": {
        "scene_spec": {
            "scene_id": "scene_plush_shop",
            "title": "Soft Plush Shop Display",
            "user_goal": "Generate a Blender-ready hero subject and simple shop-corner scene.",
            "subjects": [
                {
                    "subject_id": "subject_plush",
                    "display_name": "Yellow Plush Hero",
                    "description": "soft yellow cotton-textured toy-like character",
                }
            ],
        },
        "active_review_patches": [],
        "reference_bindings": [
            {
                "image_id": "image_subject_001",
                "target_type": "subject",
                "target_id": "subject_plush",
                "usage": "subject_reference",
            }
        ],
    },
    "ConceptVisualQA": {
        "scene_spec": {"scene_id": "scene_plush_shop", "subjects": [{"subject_id": "subject_plush"}]},
        "concept_bundle": {"subject_concept_images": {"subject_plush": ["artifact_concept_001"]}},
        "reference_bindings": [{"image_id": "image_subject_001", "target_id": "subject_plush"}],
    },
    "FeedbackPatchParser": {
        "user_feedback": "主体更像棉花娃娃，头身比再夸张一点，背景减少杂物。",
        "phase": "CONCEPT_REVIEW",
        "scene_spec": {"scene_id": "scene_plush_shop"},
        "concept_bundle": {"concept_version": 1, "approved": False},
    },
    "RegenerationRouter": {
        "review_patches": [
            {
                "patch_id": "patch_001",
                "target_type": "subject",
                "target_id": "subject_plush",
                "patch_type": "appearance_change",
                "instruction": "make the subject more cotton-doll-like",
                "status": "pending",
            }
        ],
        "current_phase": "CONCEPT_REVIEW",
        "artifact_summary": {"concept_images": ["artifact_concept_001"]},
    },
    "SceneAssetAdapterPlanner": {
        "scene_spec": {"scene_id": "scene_plush_shop", "environment": {"environment_type": "shop_corner"}},
        "scene_generation_output_summary": {"service": "hy_world", "output_files": ["scene.glb"]},
    },
    "BlenderAssemblyPlanner": {
        "scene_spec": {"scene_id": "scene_plush_shop", "camera": {"shot_type": "three quarter"}},
        "subject_assets": [{"asset_id": "asset_subject_plush_001", "subject_id": "subject_plush"}],
        "scene_asset": {"scene_asset_id": "scene_asset_shop_001", "mesh_uri": "/path/to/scene.glb"},
        "concept_bundle_summary": "one approved hero subject concept",
    },
    "BlenderPreviewReviewGate": {
        "user_feedback": "可以交付，主体位置和视角都可以。",
        "viewer_scene": {"viewer_scene_id": "viewer_scene_001", "scene_glb_uri": "/path/to/viewer_scene.glb"},
        "blender_preview": {"blender_scene_id": "blend_scene_001", "blend_uri": "/path/to/scene.blend"},
        "scene_spec": {"scene_id": "scene_plush_shop"},
    },
    "BlenderEditRouter": {
        "user_edit_text": "把主体往前移动一点，镜头低一点，灯光更柔和。",
        "blender_scene": {
            "blender_scene_id": "blend_scene_001",
            "objects": [
                {
                    "object_id": "hero",
                    "blender_name": "Hero",
                    "subject_id": "subject_plush",
                    "object_type": "subject_asset",
                }
            ],
        },
        "scene_spec": {"scene_id": "scene_plush_shop"},
        "allowed_edit_tools": ["move_subject", "update_camera", "update_lighting", "export_viewer_scene"],
    },
}


def render_prompt_catalog(*, include_full_prompts: bool = True) -> str:
    lines: list[str] = [
        "# Agent Prompt Catalog",
        "",
        "Generated from `agent_runtime.agent_prompts`; edit the code contract, then regenerate this file.",
        "",
        "## Prompt Template",
        "",
        "Every node prompt is built by `build_node_prompt(node_name, context_json=...)`:",
        "",
        "```text",
        "You are {node_name}.",
        "Current task: {responsibility}",
        "Current WorkflowPhase: {phase}.",
        "Allowed domain tools for planning only: {allowed_tools}.",
        "Use only the supplied context_json. Do not use hidden conversation memory as fact.",
        "Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.",
        "If required information is missing, set the model's clarification/open-question fields instead of guessing.",
        "Output only one JSON object. Do not include Markdown or extra natural language.",
        "context_json:",
        "{context_json}",
        "output_json_schema:",
        "{output_json_schema}",
        "```",
        "",
        "## Node Table",
        "",
        "| Node | Phase | Output | MLLM | User Gate | Allowed Tools |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for spec in NODE_SPECS.values():
        tools = ", ".join(spec.allowed_domain_tools) if spec.allowed_domain_tools else "-"
        lines.append(
            f"| `{spec.node_name}` | `{spec.phase.value}` | `{spec.output_model_name}` | "
            f"{'yes' if spec.uses_mllm else 'no'} | {'yes' if spec.user_gate else 'no'} | {tools} |"
        )
    lines.extend(["", "## Node Responsibilities", ""])
    for spec in NODE_SPECS.values():
        tools = ", ".join(spec.allowed_domain_tools) if spec.allowed_domain_tools else "none"
        context_keys = ", ".join(spec.context_keys) if spec.context_keys else "none"
        lines.extend(
            [
                f"### {spec.node_name}",
                "",
                f"- Phase: `{spec.phase.value}`",
                f"- Responsibility: {spec.responsibility}",
                f"- Output model: `{spec.output_model_name}`",
                f"- Context keys: {context_keys}",
                f"- Allowed domain tools: {tools}",
                "",
            ]
        )
        if include_full_prompts:
            prompt = build_node_prompt(spec.node_name, context_json=SAMPLE_CONTEXTS.get(spec.node_name, {}))
            lines.extend(["```text", prompt.system_prompt.rstrip(), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_prompt_catalog(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_prompt_catalog(), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the V1 agent prompt catalog.")
    parser.add_argument(
        "--write",
        type=Path,
        default=None,
        help="Write the catalog to this markdown path instead of stdout.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Render node metadata without full sample prompts.",
    )
    args = parser.parse_args(argv)
    text = render_prompt_catalog(include_full_prompts=not args.summary_only)
    if args.write is not None:
        target = args.write.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
