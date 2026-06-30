# Agent Prompt Catalog

Generated from `agent_runtime.agent_prompts`; edit the code contract, then regenerate this file.

## Prompt Template

Every node prompt is built by `build_node_prompt(node_name, context_json=...)`:

```text
You are {node_name}.
Current task: {responsibility}
Current WorkflowPhase: {phase}.
Allowed domain tools for planning only: {allowed_tools}.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{context_json}
output_json_schema:
{output_json_schema}
```

## Node Table

| Node | Phase | Output | MLLM | User Gate | Allowed Tools |
| --- | --- | --- | --- | --- | --- |
| `UserIntentRouter` | `INTAKE` | `UserIntentRouterOutput` | no | no | - |
| `ReferenceBindingValidator` | `INTAKE` | `ReferenceBindingValidatorOutput` | no | no | - |
| `SceneInterpreter` | `SCENE_SPEC_DRAFT` | `SceneInterpreterOutput` | yes | no | - |
| `SceneSpecCompiler` | `SCENE_SPEC_DRAFT` | `SceneSpec` | no | no | compile_scene_spec, bind_reference_images |
| `ConceptPromptPlanner` | `CONCEPT_GENERATION` | `ConceptPromptPlannerOutput` | no | no | generate_concept_images |
| `ConceptVisualQA` | `CONCEPT_REVIEW` | `VisualQAResult` | yes | no | - |
| `FeedbackPatchParser` | `CONCEPT_REVIEW` | `FeedbackPatchParserOutput` | no | yes | parse_review_patch, regenerate_concept_images, approve_concept |
| `RegenerationRouter` | `CONCEPT_REVIEW` | `RegenerationRouterOutput` | no | no | - |
| `SceneAssetAdapterPlanner` | `SCENE_ASSET_ADAPTATION` | `SceneAssetAdapterPlannerOutput` | no | no | build_scene_asset, adapt_scene_asset |
| `BlenderAssemblyPlanner` | `BLENDER_ASSEMBLY_PLANNING` | `BlenderAssemblyPlan` | no | no | get_blender_scene_summary, import_subject_asset, import_scene_asset, place_subject, setup_camera, setup_lighting, export_viewer_scene, render_preview |
| `BlenderPreviewReviewGate` | `BLENDER_PREVIEW` | `BlenderPreviewReviewGateOutput` | no | yes | - |
| `BlenderEditRouter` | `BLENDER_EDIT` | `BlenderEditRouterOutput` | no | no | get_blender_scene_summary, move_subject, rotate_subject, scale_subject, delete_subject, replace_subject_asset, update_camera, update_lighting, set_simple_material, export_viewer_scene, render_preview |

## Node Responsibilities

### UserIntentRouter

- Phase: `INTAKE`
- Responsibility: Classify the user turn under the current phase without changing state.
- Output model: `UserIntentRouterOutput`
- Context keys: phase, latest_user_turn, pending_action
- Allowed domain tools: none

```text
You are UserIntentRouter.
Current task: Classify the user turn under the current phase without changing state.
Current WorkflowPhase: INTAKE.
Allowed domain tools for planning only: none.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "latest_user_turn": {
    "image_ids": [
      "image_subject_001"
    ],
    "text": "请根据参考图生成一个可以放进 Blender 场景的主体模型。"
  },
  "pending_action": null,
  "phase": "INTAKE"
}
output_json_schema:
{
  "$defs": {
    "UserIntent": {
      "enum": [
        "NEW_SCENE_REQUEST",
        "CONCEPT_FEEDBACK",
        "CONCEPT_APPROVAL",
        "BLENDER_EDIT",
        "BLENDER_APPROVAL",
        "SUBJECT_REDO_REQUEST",
        "SCENE_REDO_REQUEST",
        "GENERAL_QUESTION"
      ],
      "title": "UserIntent",
      "type": "string"
    }
  },
  "properties": {
    "clarification_question": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Clarification Question"
    },
    "confidence": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Confidence"
    },
    "intent": {
      "anyOf": [
        {
          "$ref": "#/$defs/UserIntent"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "requires_clarification": {
      "default": false,
      "title": "Requires Clarification",
      "type": "boolean"
    },
    "route_reason": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Route Reason"
    }
  },
  "title": "UserIntentRouterOutput",
  "type": "object"
}
```

### ReferenceBindingValidator

- Phase: `INTAKE`
- Responsibility: Validate explicit image-purpose declarations and request clarification when missing.
- Output model: `ReferenceBindingValidatorOutput`
- Context keys: user_text, input_images, declared_bindings
- Allowed domain tools: none

```text
You are ReferenceBindingValidator.
Current task: Validate explicit image-purpose declarations and request clarification when missing.
Current WorkflowPhase: INTAKE.
Allowed domain tools for planning only: none.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "declared_bindings": [
    {
      "image_id": "image_subject_001",
      "target_id": "subject_hero",
      "target_type": "subject",
      "usage": "subject_reference"
    },
    {
      "image_id": "image_scene_001",
      "target_id": "scene_main",
      "target_type": "scene",
      "usage": "scene_reference"
    },
    {
      "image_id": "image_style_001",
      "target_type": "style",
      "usage": "style_reference"
    }
  ],
  "input_images": [
    {
      "image_id": "image_subject_001",
      "user_declared_label": "图1 主体"
    },
    {
      "image_id": "image_scene_001",
      "user_declared_label": "图2 场景"
    },
    {
      "image_id": "image_style_001",
      "user_declared_label": "图3 风格"
    }
  ],
  "user_text": "图1是主体参考，图2是场景参考，图3只控制棉花质感。"
}
output_json_schema:
{
  "$defs": {
    "ReferenceBindingPlan": {
      "properties": {
        "binding_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Binding Id"
        },
        "confidence": {
          "default": 1.0,
          "title": "Confidence",
          "type": "number"
        },
        "explicit_in_user_text": {
          "default": true,
          "title": "Explicit In User Text",
          "type": "boolean"
        },
        "image_id": {
          "title": "Image Id",
          "type": "string"
        },
        "notes": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Notes"
        },
        "source_text_span": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Source Text Span"
        },
        "target_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Id"
        },
        "target_type": {
          "enum": [
            "subject",
            "scene",
            "style",
            "pose",
            "texture",
            "layout"
          ],
          "title": "Target Type",
          "type": "string"
        },
        "usage": {
          "enum": [
            "subject_reference",
            "scene_reference",
            "style_reference",
            "pose_reference",
            "texture_reference",
            "layout_reference"
          ],
          "title": "Usage",
          "type": "string"
        }
      },
      "required": [
        "image_id",
        "target_type",
        "usage"
      ],
      "title": "ReferenceBindingPlan",
      "type": "object"
    }
  },
  "properties": {
    "issues": {
      "items": {
        "type": "string"
      },
      "title": "Issues",
      "type": "array"
    },
    "open_questions": {
      "items": {
        "type": "string"
      },
      "title": "Open Questions",
      "type": "array"
    },
    "requires_clarification": {
      "default": false,
      "title": "Requires Clarification",
      "type": "boolean"
    },
    "valid_bindings": {
      "items": {
        "$ref": "#/$defs/ReferenceBindingPlan"
      },
      "title": "Valid Bindings",
      "type": "array"
    }
  },
  "title": "ReferenceBindingValidatorOutput",
  "type": "object"
}
```

### SceneInterpreter

- Phase: `SCENE_SPEC_DRAFT`
- Responsibility: Extract scene intent, subjects, environment, style, and open questions.
- Output model: `SceneInterpreterOutput`
- Context keys: user_text, input_images, reference_bindings
- Allowed domain tools: none

```text
You are SceneInterpreter.
Current task: Extract scene intent, subjects, environment, style, and open questions.
Current WorkflowPhase: SCENE_SPEC_DRAFT.
Allowed domain tools for planning only: none.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "input_images": [
    {
      "image_id": "image_subject_001",
      "user_declared_label": "主体参考"
    },
    {
      "image_id": "image_scene_001",
      "user_declared_label": "街角参考"
    }
  ],
  "reference_bindings": [
    {
      "binding_id": "binding_subject_001",
      "image_id": "image_subject_001",
      "target_id": "subject_plush",
      "target_type": "subject",
      "usage": "subject_reference"
    },
    {
      "binding_id": "binding_scene_001",
      "image_id": "image_scene_001",
      "target_id": "scene_shop_corner",
      "target_type": "scene",
      "usage": "scene_reference"
    }
  ],
  "user_text": "做一个软萌黄色玩偶站在小型展示台前，背景是明亮街角店铺。"
}
output_json_schema:
{
  "properties": {
    "environment_summary": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Environment Summary"
    },
    "open_questions": {
      "items": {
        "type": "string"
      },
      "title": "Open Questions",
      "type": "array"
    },
    "style_summary": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Style Summary"
    },
    "subject_summaries": {
      "items": {
        "type": "string"
      },
      "title": "Subject Summaries",
      "type": "array"
    },
    "user_goal": {
      "title": "User Goal",
      "type": "string"
    }
  },
  "required": [
    "user_goal"
  ],
  "title": "SceneInterpreterOutput",
  "type": "object"
}
```

### SceneSpecCompiler

- Phase: `SCENE_SPEC_DRAFT`
- Responsibility: Normalize interpretation and bindings into a validated SceneSpec candidate.
- Output model: `SceneSpec`
- Context keys: interpretation, reference_bindings, previous_scene_spec
- Allowed domain tools: compile_scene_spec, bind_reference_images

```text
You are SceneSpecCompiler.
Current task: Normalize interpretation and bindings into a validated SceneSpec candidate.
Current WorkflowPhase: SCENE_SPEC_DRAFT.
Allowed domain tools for planning only: compile_scene_spec, bind_reference_images.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "interpretation": {
    "environment_summary": "bright street-corner shop display",
    "open_questions": [],
    "style_summary": "soft cotton texture, cute, clean display",
    "subject_summaries": [
      "yellow plush-like hero subject"
    ],
    "user_goal": "Create a soft yellow plush-like hero subject in a bright street-corner shop display."
  },
  "previous_scene_spec": null,
  "reference_bindings": [
    {
      "binding_id": "binding_subject_001",
      "image_id": "image_subject_001",
      "target_id": "subject_plush",
      "target_type": "subject",
      "usage": "subject_reference"
    }
  ]
}
output_json_schema:
{
  "$defs": {
    "CameraSpec": {
      "properties": {
        "angle": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Angle"
        },
        "framing": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Framing"
        },
        "lens_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lens Hint"
        },
        "movement": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Movement"
        },
        "shot_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Shot Type"
        },
        "target_subject_ids": {
          "items": {
            "type": "string"
          },
          "title": "Target Subject Ids",
          "type": "array"
        }
      },
      "title": "CameraSpec",
      "type": "object"
    },
    "EnvironmentSpec": {
      "properties": {
        "background_elements": {
          "items": {
            "type": "string"
          },
          "title": "Background Elements",
          "type": "array"
        },
        "description": {
          "title": "Description",
          "type": "string"
        },
        "environment_type": {
          "title": "Environment Type",
          "type": "string"
        },
        "ground_surface": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Ground Surface"
        },
        "scene_reference_image_ids": {
          "items": {
            "type": "string"
          },
          "title": "Scene Reference Image Ids",
          "type": "array"
        },
        "time_of_day": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Time Of Day"
        },
        "weather": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Weather"
        }
      },
      "required": [
        "environment_type",
        "description"
      ],
      "title": "EnvironmentSpec",
      "type": "object"
    },
    "LightingSpec": {
      "properties": {
        "ambient": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Ambient"
        },
        "color_temperature": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Color Temperature"
        },
        "description": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Description"
        },
        "fill_light": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Fill Light"
        },
        "intensity_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Intensity Hint"
        },
        "key_light": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Key Light"
        },
        "rim_light": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Rim Light"
        }
      },
      "title": "LightingSpec",
      "type": "object"
    },
    "SpatialRelation": {
      "properties": {
        "distance_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Distance Hint"
        },
        "notes": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Notes"
        },
        "relation": {
          "enum": [
            "left_of",
            "right_of",
            "in_front_of",
            "behind",
            "on_top_of",
            "under",
            "near",
            "far_from",
            "inside",
            "surrounding",
            "facing",
            "beside",
            "centered_in"
          ],
          "title": "Relation",
          "type": "string"
        },
        "relation_id": {
          "title": "Relation Id",
          "type": "string"
        },
        "scale_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Scale Hint"
        },
        "source_subject_id": {
          "title": "Source Subject Id",
          "type": "string"
        },
        "target_region": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Region"
        },
        "target_subject_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Subject Id"
        }
      },
      "required": [
        "relation_id",
        "source_subject_id",
        "relation"
      ],
      "title": "SpatialRelation",
      "type": "object"
    },
    "StyleSpec": {
      "properties": {
        "color_palette": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Color Palette"
        },
        "mood": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Mood"
        },
        "notes": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Notes"
        },
        "realism_level": {
          "anyOf": [
            {
              "enum": [
                "realistic",
                "semi_realistic",
                "stylized",
                "cartoon",
                "illustrative"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Realism Level"
        },
        "rendering_style": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Rendering Style"
        },
        "style_keywords": {
          "items": {
            "type": "string"
          },
          "title": "Style Keywords",
          "type": "array"
        }
      },
      "title": "StyleSpec",
      "type": "object"
    },
    "SubjectSpec": {
      "properties": {
        "appearance": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Appearance"
        },
        "asset_strategy": {
          "default": "hunyuan3d_img2asset",
          "enum": [
            "hunyuan3d_img2asset",
            "blender_primitive",
            "procedural_blender",
            "scene_service_component",
            "existing_asset"
          ],
          "title": "Asset Strategy",
          "type": "string"
        },
        "category": {
          "enum": [
            "character",
            "animal",
            "prop",
            "vehicle",
            "furniture",
            "architecture_part",
            "environment_asset"
          ],
          "title": "Category",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        },
        "display_name": {
          "title": "Display Name",
          "type": "string"
        },
        "needs_2d_concept": {
          "default": true,
          "title": "Needs 2D Concept",
          "type": "boolean"
        },
        "needs_3d_asset": {
          "default": true,
          "title": "Needs 3D Asset",
          "type": "boolean"
        },
        "placement_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Placement Hint"
        },
        "pose_or_state": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pose Or State"
        },
        "preferred_subject_image_view": {
          "default": "three_quarter",
          "enum": [
            "three_quarter",
            "front",
            "side",
            "multi_view",
            "unspecified"
          ],
          "title": "Preferred Subject Image View",
          "type": "string"
        },
        "priority": {
          "default": "important",
          "enum": [
            "hero",
            "important",
            "background"
          ],
          "title": "Priority",
          "type": "string"
        },
        "reference_image_ids": {
          "items": {
            "type": "string"
          },
          "title": "Reference Image Ids",
          "type": "array"
        },
        "role_in_scene": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Role In Scene"
        },
        "scale_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Scale Hint"
        },
        "subject_id": {
          "title": "Subject Id",
          "type": "string"
        }
      },
      "required": [
        "subject_id",
        "display_name",
        "category",
        "description"
      ],
      "title": "SubjectSpec",
      "type": "object"
    }
  },
  "properties": {
    "camera": {
      "$ref": "#/$defs/CameraSpec"
    },
    "constraints": {
      "items": {
        "type": "string"
      },
      "title": "Constraints",
      "type": "array"
    },
    "environment": {
      "$ref": "#/$defs/EnvironmentSpec"
    },
    "lighting": {
      "$ref": "#/$defs/LightingSpec"
    },
    "open_questions": {
      "items": {
        "type": "string"
      },
      "title": "Open Questions",
      "type": "array"
    },
    "scene_id": {
      "title": "Scene Id",
      "type": "string"
    },
    "spatial_relations": {
      "items": {
        "$ref": "#/$defs/SpatialRelation"
      },
      "title": "Spatial Relations",
      "type": "array"
    },
    "style": {
      "$ref": "#/$defs/StyleSpec"
    },
    "subjects": {
      "items": {
        "$ref": "#/$defs/SubjectSpec"
      },
      "title": "Subjects",
      "type": "array"
    },
    "title": {
      "title": "Title",
      "type": "string"
    },
    "user_goal": {
      "title": "User Goal",
      "type": "string"
    },
    "version": {
      "default": 1,
      "title": "Version",
      "type": "integer"
    }
  },
  "required": [
    "scene_id",
    "title",
    "user_goal",
    "style",
    "environment",
    "lighting",
    "camera"
  ],
  "title": "SceneSpec",
  "type": "object"
}
```

### ConceptPromptPlanner

- Phase: `CONCEPT_GENERATION`
- Responsibility: Create prompts for final preview, subject concepts, and scene concepts.
- Output model: `ConceptPromptPlannerOutput`
- Context keys: scene_spec, active_review_patches, reference_bindings
- Allowed domain tools: generate_concept_images

```text
You are ConceptPromptPlanner.
Current task: Create prompts for final preview, subject concepts, and scene concepts.
Current WorkflowPhase: CONCEPT_GENERATION.
Allowed domain tools for planning only: generate_concept_images.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "active_review_patches": [],
  "reference_bindings": [
    {
      "image_id": "image_subject_001",
      "target_id": "subject_plush",
      "target_type": "subject",
      "usage": "subject_reference"
    }
  ],
  "scene_spec": {
    "scene_id": "scene_plush_shop",
    "subjects": [
      {
        "description": "soft yellow cotton-textured toy-like character",
        "display_name": "Yellow Plush Hero",
        "subject_id": "subject_plush"
      }
    ],
    "title": "Soft Plush Shop Display",
    "user_goal": "Generate a Blender-ready hero subject and simple shop-corner scene."
  }
}
output_json_schema:
{
  "properties": {
    "final_preview_prompt": {
      "title": "Final Preview Prompt",
      "type": "string"
    },
    "negative_prompt": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Negative Prompt"
    },
    "scene_prompts": {
      "items": {
        "type": "string"
      },
      "title": "Scene Prompts",
      "type": "array"
    },
    "subject_prompts": {
      "additionalProperties": {
        "type": "string"
      },
      "title": "Subject Prompts",
      "type": "object"
    }
  },
  "required": [
    "final_preview_prompt"
  ],
  "title": "ConceptPromptPlannerOutput",
  "type": "object"
}
```

### ConceptVisualQA

- Phase: `CONCEPT_REVIEW`
- Responsibility: Check generated concept images against the SceneSpec and references.
- Output model: `VisualQAResult`
- Context keys: scene_spec, concept_bundle, reference_bindings
- Allowed domain tools: none

```text
You are ConceptVisualQA.
Current task: Check generated concept images against the SceneSpec and references.
Current WorkflowPhase: CONCEPT_REVIEW.
Allowed domain tools for planning only: none.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "concept_bundle": {
    "subject_concept_images": {
      "subject_plush": [
        "artifact_concept_001"
      ]
    }
  },
  "reference_bindings": [
    {
      "image_id": "image_subject_001",
      "target_id": "subject_plush"
    }
  ],
  "scene_spec": {
    "scene_id": "scene_plush_shop",
    "subjects": [
      {
        "subject_id": "subject_plush"
      }
    ]
  }
}
output_json_schema:
{
  "properties": {
    "issues": {
      "items": {
        "type": "string"
      },
      "title": "Issues",
      "type": "array"
    },
    "mismatched_subject_ids": {
      "items": {
        "type": "string"
      },
      "title": "Mismatched Subject Ids",
      "type": "array"
    },
    "missing_subject_ids": {
      "items": {
        "type": "string"
      },
      "title": "Missing Subject Ids",
      "type": "array"
    },
    "ok": {
      "title": "Ok",
      "type": "boolean"
    },
    "recommendation": {
      "default": "accept",
      "enum": [
        "accept",
        "retry_generation",
        "ask_user",
        "continue_with_warning"
      ],
      "title": "Recommendation",
      "type": "string"
    },
    "score": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Score"
    }
  },
  "required": [
    "ok"
  ],
  "title": "VisualQAResult",
  "type": "object"
}
```

### FeedbackPatchParser

- Phase: `CONCEPT_REVIEW`
- Responsibility: Parse user feedback into ReviewPatch records without applying them.
- Output model: `FeedbackPatchParserOutput`
- Context keys: user_feedback, phase, scene_spec, concept_bundle
- Allowed domain tools: parse_review_patch, regenerate_concept_images, approve_concept

```text
You are FeedbackPatchParser.
Current task: Parse user feedback into ReviewPatch records without applying them.
Current WorkflowPhase: CONCEPT_REVIEW.
Allowed domain tools for planning only: parse_review_patch, regenerate_concept_images, approve_concept.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "concept_bundle": {
    "approved": false,
    "concept_version": 1
  },
  "phase": "CONCEPT_REVIEW",
  "scene_spec": {
    "scene_id": "scene_plush_shop"
  },
  "user_feedback": "主体更像棉花娃娃，头身比再夸张一点，背景减少杂物。"
}
output_json_schema:
{
  "$defs": {
    "ReviewPatch": {
      "properties": {
        "affected_artifact_ids": {
          "items": {
            "type": "string"
          },
          "title": "Affected Artifact Ids",
          "type": "array"
        },
        "instruction": {
          "title": "Instruction",
          "type": "string"
        },
        "patch_id": {
          "title": "Patch Id",
          "type": "string"
        },
        "patch_type": {
          "enum": [
            "appearance_change",
            "pose_change",
            "style_change",
            "lighting_change",
            "camera_change",
            "layout_change",
            "add_subject",
            "remove_subject",
            "replace_subject",
            "material_change",
            "move_object",
            "rotate_object",
            "scale_object",
            "redo_subject",
            "redo_scene"
          ],
          "title": "Patch Type",
          "type": "string"
        },
        "phase_created": {
          "$ref": "#/$defs/WorkflowPhase"
        },
        "source_turn_id": {
          "title": "Source Turn Id",
          "type": "string"
        },
        "status": {
          "default": "pending",
          "enum": [
            "pending",
            "applied",
            "rejected",
            "superseded"
          ],
          "title": "Status",
          "type": "string"
        },
        "structured_delta": {
          "additionalProperties": true,
          "title": "Structured Delta",
          "type": "object"
        },
        "target_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Id"
        },
        "target_type": {
          "enum": [
            "global",
            "scene",
            "subject",
            "camera",
            "lighting",
            "material",
            "blender_object"
          ],
          "title": "Target Type",
          "type": "string"
        }
      },
      "required": [
        "patch_id",
        "source_turn_id",
        "phase_created",
        "target_type",
        "patch_type",
        "instruction"
      ],
      "title": "ReviewPatch",
      "type": "object"
    },
    "WorkflowPhase": {
      "enum": [
        "INTAKE",
        "SCENE_SPEC_DRAFT",
        "SCENE_SPEC_READY",
        "CONCEPT_GENERATION",
        "CONCEPT_REVIEW",
        "CONCEPT_APPROVED",
        "SUBJECT_ASSET_GENERATION",
        "SUBJECT_ASSET_QA",
        "SCENE_ASSET_GENERATION",
        "SCENE_ASSET_ADAPTATION",
        "BLENDER_ASSEMBLY_PLANNING",
        "BLENDER_ASSEMBLY_EXECUTION",
        "BLENDER_PREVIEW",
        "BLENDER_EDIT",
        "DELIVERY",
        "FAILED"
      ],
      "title": "WorkflowPhase",
      "type": "string"
    }
  },
  "properties": {
    "clarification_question": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Clarification Question"
    },
    "patches": {
      "items": {
        "$ref": "#/$defs/ReviewPatch"
      },
      "title": "Patches",
      "type": "array"
    },
    "requires_clarification": {
      "default": false,
      "title": "Requires Clarification",
      "type": "boolean"
    }
  },
  "title": "FeedbackPatchParserOutput",
  "type": "object"
}
```

### RegenerationRouter

- Phase: `CONCEPT_REVIEW`
- Responsibility: Route ReviewPatch records to concept regeneration, 3D redo, Blender edit, or clarification.
- Output model: `RegenerationRouterOutput`
- Context keys: review_patches, current_phase, artifact_summary
- Allowed domain tools: none

```text
You are RegenerationRouter.
Current task: Route ReviewPatch records to concept regeneration, 3D redo, Blender edit, or clarification.
Current WorkflowPhase: CONCEPT_REVIEW.
Allowed domain tools for planning only: none.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "artifact_summary": {
    "concept_images": [
      "artifact_concept_001"
    ]
  },
  "current_phase": "CONCEPT_REVIEW",
  "review_patches": [
    {
      "instruction": "make the subject more cotton-doll-like",
      "patch_id": "patch_001",
      "patch_type": "appearance_change",
      "status": "pending",
      "target_id": "subject_plush",
      "target_type": "subject"
    }
  ]
}
output_json_schema:
{
  "$defs": {
    "WorkflowPhase": {
      "enum": [
        "INTAKE",
        "SCENE_SPEC_DRAFT",
        "SCENE_SPEC_READY",
        "CONCEPT_GENERATION",
        "CONCEPT_REVIEW",
        "CONCEPT_APPROVED",
        "SUBJECT_ASSET_GENERATION",
        "SUBJECT_ASSET_QA",
        "SCENE_ASSET_GENERATION",
        "SCENE_ASSET_ADAPTATION",
        "BLENDER_ASSEMBLY_PLANNING",
        "BLENDER_ASSEMBLY_EXECUTION",
        "BLENDER_PREVIEW",
        "BLENDER_EDIT",
        "DELIVERY",
        "FAILED"
      ],
      "title": "WorkflowPhase",
      "type": "string"
    }
  },
  "properties": {
    "affected_artifact_ids": {
      "items": {
        "type": "string"
      },
      "title": "Affected Artifact Ids",
      "type": "array"
    },
    "next_phase": {
      "$ref": "#/$defs/WorkflowPhase"
    },
    "reason": {
      "title": "Reason",
      "type": "string"
    },
    "route": {
      "enum": [
        "regenerate_concept",
        "redo_subject_asset",
        "redo_scene_asset",
        "blender_edit",
        "ask_user"
      ],
      "title": "Route",
      "type": "string"
    }
  },
  "required": [
    "route",
    "next_phase",
    "reason"
  ],
  "title": "RegenerationRouterOutput",
  "type": "object"
}
```

### SceneAssetAdapterPlanner

- Phase: `SCENE_ASSET_ADAPTATION`
- Responsibility: Plan how a scene service output should be adapted into Blender-consumable artifacts.
- Output model: `SceneAssetAdapterPlannerOutput`
- Context keys: scene_spec, scene_generation_output_summary
- Allowed domain tools: build_scene_asset, adapt_scene_asset

```text
You are SceneAssetAdapterPlanner.
Current task: Plan how a scene service output should be adapted into Blender-consumable artifacts.
Current WorkflowPhase: SCENE_ASSET_ADAPTATION.
Allowed domain tools for planning only: build_scene_asset, adapt_scene_asset.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "scene_generation_output_summary": {
    "output_files": [
      "scene.glb"
    ],
    "service": "hy_world"
  },
  "scene_spec": {
    "environment": {
      "environment_type": "shop_corner"
    },
    "scene_id": "scene_plush_shop"
  }
}
output_json_schema:
{
  "properties": {
    "import_mode": {
      "enum": [
        "mesh_import",
        "3dgs_layer",
        "point_cloud_proxy",
        "depth_camera_scaffold",
        "visual_reference_only",
        "procedural_proxy"
      ],
      "title": "Import Mode",
      "type": "string"
    },
    "notes": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Notes"
    },
    "requires_proxy_scene": {
      "default": false,
      "title": "Requires Proxy Scene",
      "type": "boolean"
    }
  },
  "required": [
    "import_mode"
  ],
  "title": "SceneAssetAdapterPlannerOutput",
  "type": "object"
}
```

### BlenderAssemblyPlanner

- Phase: `BLENDER_ASSEMBLY_PLANNING`
- Responsibility: Plan imports, placement, camera, and lighting for the authoritative Blender scene.
- Output model: `BlenderAssemblyPlan`
- Context keys: scene_spec, subject_assets, scene_asset, concept_bundle_summary
- Allowed domain tools: get_blender_scene_summary, import_subject_asset, import_scene_asset, place_subject, setup_camera, setup_lighting, export_viewer_scene, render_preview

```text
You are BlenderAssemblyPlanner.
Current task: Plan imports, placement, camera, and lighting for the authoritative Blender scene.
Current WorkflowPhase: BLENDER_ASSEMBLY_PLANNING.
Allowed domain tools for planning only: get_blender_scene_summary, import_subject_asset, import_scene_asset, place_subject, setup_camera, setup_lighting, export_viewer_scene, render_preview.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "concept_bundle_summary": "one approved hero subject concept",
  "scene_asset": {
    "mesh_uri": "/path/to/scene.glb",
    "scene_asset_id": "scene_asset_shop_001"
  },
  "scene_spec": {
    "camera": {
      "shot_type": "three quarter"
    },
    "scene_id": "scene_plush_shop"
  },
  "subject_assets": [
    {
      "asset_id": "asset_subject_plush_001",
      "subject_id": "subject_plush"
    }
  ]
}
output_json_schema:
{
  "$defs": {
    "CameraSpec": {
      "properties": {
        "angle": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Angle"
        },
        "framing": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Framing"
        },
        "lens_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lens Hint"
        },
        "movement": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Movement"
        },
        "shot_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Shot Type"
        },
        "target_subject_ids": {
          "items": {
            "type": "string"
          },
          "title": "Target Subject Ids",
          "type": "array"
        }
      },
      "title": "CameraSpec",
      "type": "object"
    },
    "LightingSpec": {
      "properties": {
        "ambient": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Ambient"
        },
        "color_temperature": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Color Temperature"
        },
        "description": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Description"
        },
        "fill_light": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Fill Light"
        },
        "intensity_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Intensity Hint"
        },
        "key_light": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Key Light"
        },
        "rim_light": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Rim Light"
        }
      },
      "title": "LightingSpec",
      "type": "object"
    },
    "PlacementPlan": {
      "properties": {
        "composition_notes": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Composition Notes"
        },
        "relation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Relation"
        },
        "relation_to_subject_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Relation To Subject Id"
        },
        "subject_id": {
          "title": "Subject Id",
          "type": "string"
        },
        "target_region": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Region"
        },
        "transform_hint": {
          "anyOf": [
            {
              "$ref": "#/$defs/TransformSpec"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        }
      },
      "required": [
        "subject_id"
      ],
      "title": "PlacementPlan",
      "type": "object"
    },
    "RenderSettings": {
      "properties": {
        "engine": {
          "default": "unknown",
          "enum": [
            "cycles",
            "eevee",
            "workbench",
            "unknown"
          ],
          "title": "Engine",
          "type": "string"
        },
        "frame_end": {
          "default": 1,
          "title": "Frame End",
          "type": "integer"
        },
        "frame_start": {
          "default": 1,
          "title": "Frame Start",
          "type": "integer"
        },
        "notes": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Notes"
        },
        "output_format": {
          "default": "PNG",
          "title": "Output Format",
          "type": "string"
        },
        "resolution_x": {
          "default": 1280,
          "title": "Resolution X",
          "type": "integer"
        },
        "resolution_y": {
          "default": 720,
          "title": "Resolution Y",
          "type": "integer"
        },
        "samples": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Samples"
        }
      },
      "title": "RenderSettings",
      "type": "object"
    },
    "ScaleEstimate": {
      "properties": {
        "confidence": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Confidence"
        },
        "reasoning_summary": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reasoning Summary"
        },
        "relative_scale_description": {
          "title": "Relative Scale Description",
          "type": "string"
        },
        "scale_factor_hint": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Scale Factor Hint"
        },
        "subject_id": {
          "title": "Subject Id",
          "type": "string"
        }
      },
      "required": [
        "subject_id",
        "relative_scale_description"
      ],
      "title": "ScaleEstimate",
      "type": "object"
    },
    "TransformSpec": {
      "properties": {
        "location": {
          "default": [
            0.0,
            0.0,
            0.0
          ],
          "maxItems": 3,
          "minItems": 3,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Location",
          "type": "array"
        },
        "rotation_euler": {
          "default": [
            0.0,
            0.0,
            0.0
          ],
          "maxItems": 3,
          "minItems": 3,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Rotation Euler",
          "type": "array"
        },
        "scale": {
          "default": [
            1.0,
            1.0,
            1.0
          ],
          "maxItems": 3,
          "minItems": 3,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Scale",
          "type": "array"
        }
      },
      "title": "TransformSpec",
      "type": "object"
    }
  },
  "properties": {
    "camera_plan": {
      "anyOf": [
        {
          "$ref": "#/$defs/CameraSpec"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "import_operations": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "title": "Import Operations",
      "type": "array"
    },
    "lighting_plan": {
      "anyOf": [
        {
          "$ref": "#/$defs/LightingSpec"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "notes": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Notes"
    },
    "placement_plans": {
      "items": {
        "$ref": "#/$defs/PlacementPlan"
      },
      "title": "Placement Plans",
      "type": "array"
    },
    "plan_id": {
      "title": "Plan Id",
      "type": "string"
    },
    "render_plan": {
      "anyOf": [
        {
          "$ref": "#/$defs/RenderSettings"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "scale_estimates": {
      "items": {
        "$ref": "#/$defs/ScaleEstimate"
      },
      "title": "Scale Estimates",
      "type": "array"
    }
  },
  "required": [
    "plan_id"
  ],
  "title": "BlenderAssemblyPlan",
  "type": "object"
}
```

### BlenderPreviewReviewGate

- Phase: `BLENDER_PREVIEW`
- Responsibility: Decide whether user preview feedback approves delivery or routes edits/redos.
- Output model: `BlenderPreviewReviewGateOutput`
- Context keys: user_feedback, viewer_scene, blender_preview, scene_spec
- Allowed domain tools: none

```text
You are BlenderPreviewReviewGate.
Current task: Decide whether user preview feedback approves delivery or routes edits/redos.
Current WorkflowPhase: BLENDER_PREVIEW.
Allowed domain tools for planning only: none.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "blender_preview": {
    "blend_uri": "/path/to/scene.blend",
    "blender_scene_id": "blend_scene_001"
  },
  "scene_spec": {
    "scene_id": "scene_plush_shop"
  },
  "user_feedback": "可以交付，主体位置和视角都可以。",
  "viewer_scene": {
    "scene_glb_uri": "/path/to/viewer_scene.glb",
    "viewer_scene_id": "viewer_scene_001"
  }
}
output_json_schema:
{
  "$defs": {
    "ReviewPatch": {
      "properties": {
        "affected_artifact_ids": {
          "items": {
            "type": "string"
          },
          "title": "Affected Artifact Ids",
          "type": "array"
        },
        "instruction": {
          "title": "Instruction",
          "type": "string"
        },
        "patch_id": {
          "title": "Patch Id",
          "type": "string"
        },
        "patch_type": {
          "enum": [
            "appearance_change",
            "pose_change",
            "style_change",
            "lighting_change",
            "camera_change",
            "layout_change",
            "add_subject",
            "remove_subject",
            "replace_subject",
            "material_change",
            "move_object",
            "rotate_object",
            "scale_object",
            "redo_subject",
            "redo_scene"
          ],
          "title": "Patch Type",
          "type": "string"
        },
        "phase_created": {
          "$ref": "#/$defs/WorkflowPhase"
        },
        "source_turn_id": {
          "title": "Source Turn Id",
          "type": "string"
        },
        "status": {
          "default": "pending",
          "enum": [
            "pending",
            "applied",
            "rejected",
            "superseded"
          ],
          "title": "Status",
          "type": "string"
        },
        "structured_delta": {
          "additionalProperties": true,
          "title": "Structured Delta",
          "type": "object"
        },
        "target_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Id"
        },
        "target_type": {
          "enum": [
            "global",
            "scene",
            "subject",
            "camera",
            "lighting",
            "material",
            "blender_object"
          ],
          "title": "Target Type",
          "type": "string"
        }
      },
      "required": [
        "patch_id",
        "source_turn_id",
        "phase_created",
        "target_type",
        "patch_type",
        "instruction"
      ],
      "title": "ReviewPatch",
      "type": "object"
    },
    "WorkflowPhase": {
      "enum": [
        "INTAKE",
        "SCENE_SPEC_DRAFT",
        "SCENE_SPEC_READY",
        "CONCEPT_GENERATION",
        "CONCEPT_REVIEW",
        "CONCEPT_APPROVED",
        "SUBJECT_ASSET_GENERATION",
        "SUBJECT_ASSET_QA",
        "SCENE_ASSET_GENERATION",
        "SCENE_ASSET_ADAPTATION",
        "BLENDER_ASSEMBLY_PLANNING",
        "BLENDER_ASSEMBLY_EXECUTION",
        "BLENDER_PREVIEW",
        "BLENDER_EDIT",
        "DELIVERY",
        "FAILED"
      ],
      "title": "WorkflowPhase",
      "type": "string"
    }
  },
  "properties": {
    "approved": {
      "default": false,
      "title": "Approved",
      "type": "boolean"
    },
    "patches": {
      "items": {
        "$ref": "#/$defs/ReviewPatch"
      },
      "title": "Patches",
      "type": "array"
    },
    "reason": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Reason"
    },
    "requires_clarification": {
      "default": false,
      "title": "Requires Clarification",
      "type": "boolean"
    },
    "route": {
      "enum": [
        "deliver",
        "blender_edit",
        "redo_subject",
        "redo_scene",
        "ask_user"
      ],
      "title": "Route",
      "type": "string"
    }
  },
  "required": [
    "route"
  ],
  "title": "BlenderPreviewReviewGateOutput",
  "type": "object"
}
```

### BlenderEditRouter

- Phase: `BLENDER_EDIT`
- Responsibility: Route a user edit request to safe Blender domain tools or upstream regeneration.
- Output model: `BlenderEditRouterOutput`
- Context keys: user_edit_text, blender_scene, scene_spec, allowed_edit_tools
- Allowed domain tools: get_blender_scene_summary, move_subject, rotate_subject, scale_subject, delete_subject, replace_subject_asset, update_camera, update_lighting, set_simple_material, export_viewer_scene, render_preview

```text
You are BlenderEditRouter.
Current task: Route a user edit request to safe Blender domain tools or upstream regeneration.
Current WorkflowPhase: BLENDER_EDIT.
Allowed domain tools for planning only: get_blender_scene_summary, move_subject, rotate_subject, scale_subject, delete_subject, replace_subject_asset, update_camera, update_lighting, set_simple_material, export_viewer_scene, render_preview.
Use only the supplied context_json. Do not use hidden conversation memory as fact.
Do not execute tools. Do not call raw MCP tools. Do not invent artifact ids, job ids, file paths, or tool results.
If required information is missing, set the model's clarification/open-question fields instead of guessing.
Output only one JSON object. Do not include Markdown or extra natural language.
context_json:
{
  "allowed_edit_tools": [
    "move_subject",
    "update_camera",
    "update_lighting",
    "export_viewer_scene"
  ],
  "blender_scene": {
    "blender_scene_id": "blend_scene_001",
    "objects": [
      {
        "blender_name": "Hero",
        "object_id": "hero",
        "object_type": "subject_asset",
        "subject_id": "subject_plush"
      }
    ]
  },
  "scene_spec": {
    "scene_id": "scene_plush_shop"
  },
  "user_edit_text": "把主体往前移动一点，镜头低一点，灯光更柔和。"
}
output_json_schema:
{
  "$defs": {
    "BlenderEditDomainToolCall": {
      "properties": {
        "arguments": {
          "additionalProperties": true,
          "title": "Arguments",
          "type": "object"
        },
        "domain_tool_name": {
          "title": "Domain Tool Name",
          "type": "string"
        },
        "patch_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Patch Id"
        },
        "reason": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reason"
        }
      },
      "required": [
        "domain_tool_name"
      ],
      "title": "BlenderEditDomainToolCall",
      "type": "object"
    },
    "ReviewPatch": {
      "properties": {
        "affected_artifact_ids": {
          "items": {
            "type": "string"
          },
          "title": "Affected Artifact Ids",
          "type": "array"
        },
        "instruction": {
          "title": "Instruction",
          "type": "string"
        },
        "patch_id": {
          "title": "Patch Id",
          "type": "string"
        },
        "patch_type": {
          "enum": [
            "appearance_change",
            "pose_change",
            "style_change",
            "lighting_change",
            "camera_change",
            "layout_change",
            "add_subject",
            "remove_subject",
            "replace_subject",
            "material_change",
            "move_object",
            "rotate_object",
            "scale_object",
            "redo_subject",
            "redo_scene"
          ],
          "title": "Patch Type",
          "type": "string"
        },
        "phase_created": {
          "$ref": "#/$defs/WorkflowPhase"
        },
        "source_turn_id": {
          "title": "Source Turn Id",
          "type": "string"
        },
        "status": {
          "default": "pending",
          "enum": [
            "pending",
            "applied",
            "rejected",
            "superseded"
          ],
          "title": "Status",
          "type": "string"
        },
        "structured_delta": {
          "additionalProperties": true,
          "title": "Structured Delta",
          "type": "object"
        },
        "target_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Id"
        },
        "target_type": {
          "enum": [
            "global",
            "scene",
            "subject",
            "camera",
            "lighting",
            "material",
            "blender_object"
          ],
          "title": "Target Type",
          "type": "string"
        }
      },
      "required": [
        "patch_id",
        "source_turn_id",
        "phase_created",
        "target_type",
        "patch_type",
        "instruction"
      ],
      "title": "ReviewPatch",
      "type": "object"
    },
    "WorkflowPhase": {
      "enum": [
        "INTAKE",
        "SCENE_SPEC_DRAFT",
        "SCENE_SPEC_READY",
        "CONCEPT_GENERATION",
        "CONCEPT_REVIEW",
        "CONCEPT_APPROVED",
        "SUBJECT_ASSET_GENERATION",
        "SUBJECT_ASSET_QA",
        "SCENE_ASSET_GENERATION",
        "SCENE_ASSET_ADAPTATION",
        "BLENDER_ASSEMBLY_PLANNING",
        "BLENDER_ASSEMBLY_EXECUTION",
        "BLENDER_PREVIEW",
        "BLENDER_EDIT",
        "DELIVERY",
        "FAILED"
      ],
      "title": "WorkflowPhase",
      "type": "string"
    }
  },
  "properties": {
    "allowed_domain_tool_names": {
      "items": {
        "type": "string"
      },
      "title": "Allowed Domain Tool Names",
      "type": "array"
    },
    "domain_tool_calls": {
      "items": {
        "$ref": "#/$defs/BlenderEditDomainToolCall"
      },
      "title": "Domain Tool Calls",
      "type": "array"
    },
    "patches": {
      "items": {
        "$ref": "#/$defs/ReviewPatch"
      },
      "title": "Patches",
      "type": "array"
    },
    "reason": {
      "title": "Reason",
      "type": "string"
    },
    "route": {
      "enum": [
        "pure_blender_edit",
        "redo_subject",
        "redo_scene",
        "return_to_concept",
        "ask_user"
      ],
      "title": "Route",
      "type": "string"
    }
  },
  "required": [
    "route",
    "reason"
  ],
  "title": "BlenderEditRouterOutput",
  "type": "object"
}
```
