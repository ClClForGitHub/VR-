# Agent Prompt Contract

Updated: 2026-06-28

## Purpose

This file records the prompt and output contract for the V1 agent layer. The
agent is a state-driven workflow. LLM/MLLM nodes are controlled helpers for
structured understanding, planning, routing, and QA. They do not execute tools,
do not own state, and do not invent artifact results.

## Source Plan

Use this contract with:

- `DOC-003_Agent_Workflow_Design_v0.2_zh.md`
- `DOC-004_State_and_JSON_Schema_Spec_v0.2_zh.md`
- `DOC-008_LLM_Node_and_Prompt_Spec_v0.2_zh.md`
- `agent_runtime/state.py`
- `agent_runtime/state_views.py`
- `agent_runtime/domain_tools.py`

## Required Prompt Shape

Every key LLM node prompt must include:

- node name;
- node responsibility;
- current `WorkflowPhase`;
- minimal `context_json`;
- output JSON Schema;
- allowed domain tools for planning only, when relevant;
- a hard instruction to output JSON only;
- a hard instruction not to call raw MCP tools or invent tool results.

The implementation helper is `agent_runtime.agent_prompts.build_node_prompt`.

## User-Reviewable Prompt Catalog

`docs/agent_prompt_catalog.md` is generated from the live prompt contracts by:

```bash
python scripts/export_agent_prompts.py --write docs/agent_prompt_catalog.md
```

It contains each current node's responsibility, phase, allowed planning tools,
sample `context_json`, and JSON output schema. Regenerate it after changing
`agent_runtime/agent_prompts.py`; do not hand-edit the generated prompt body as
the source of truth.

The catalog intentionally preserves Chinese user text in readable form so prompt
review can catch multilingual/runtime issues that are easy to miss in code.

## Natural-Language Fixture Matrix

`tests/fixtures/natural_language_scene_cases.json` records executable user
request scenarios for prompt/runtime regression checks. Current coverage
includes:

- text-only single subject;
- Chinese subject/scene/style reference bindings;
- multi-subject layout binding;
- vehicle texture reference binding;
- furniture/style reference binding;
- architecture/courtyard request;
- missing reference binding clarification.

`tests/test_natural_language_scene_fixtures.py` materializes those cases as
runtime-console runs and drives the bounded runtime loop through the same
Pydantic parse/apply path used by provider output.

The user-provided regression samples for beach duo, Little Gwen on a
chessboard, and explorer rover on lunar regolith are part of this matrix.
They must preserve the boundary between:

- subject assets that need subject concept images and Hunyuan3D/existing 3D
  assets;
- procedural or scene-service props that belong to scene/world construction;
- uploaded reference images that bind only to their declared subject, scene,
  style, pose, texture, or layout target.

`ConceptPromptPlanner` output now materializes `image_requirements` in
`ConceptPromptPack`. The default review set is:

- one `subject_concept` requirement per SceneSpec subject with
  `needs_2d_concept=true`;
- at least one `scene_concept` requirement for environment, props, lighting, and
  layout;
- one `target_render` requirement for the intended final composition.

The runtime rejects planner output that sends procedural props into
`subject_prompts` when the SceneSpec marks those props as not needing subject
concept generation.

`ConceptImageRequirement` now also records generation dependencies:

- `input_reference_image_ids`: uploaded/reference images that must be passed as
  image inputs, not merely mentioned in text;
- `generation_mode`: `text_to_image`, `image_guided`, or
  `multi_image_composite`;
- `source_requirement_ids`: generated concept requirements that a later target
  render must use as visual sources;
- `must_use_image_inputs`: a hard flag for image-guided or composite requests;
- `quality_bar`: the review bar for the generated image.

For reference-bound subjects, the subject concept requirement must be
`image_guided` and include the subject's `reference_image_ids`. For final target
renders, the requirement must be `multi_image_composite` and depend on the
subject concept and scene concept requirements. This prevents a text prompt such
as "use image 1" from silently becoming a text-only generation request.

For any subject that names an IP, franchise, game, anime, brand, or specific
character, the runtime must obtain explicit identity-research evidence before
writing final generation prompts. The preferred path is an upstream
search-capable agent/tool that searches the web, prefers official sources, and
records the resolved identity, aliases, and uncertainty in the context. The
`ConceptPromptPlanner` must not rely on hidden model memory for IP identity; if
research evidence is missing, it should set `requires_clarification=true` or add
`identity_notes` that block silent identity substitution.

When an image requirement has `input_reference_image_ids`, downstream image MCP
calls must upload/attach the corresponding files as actual image inputs. When a
target render requirement has `source_requirement_ids`, downstream image MCP
calls must resolve those generated subject/scene images and attach them as
visual references. Mentioning "use image 1" in text is not sufficient.

The user-provided samples are regression cases:

- the Wuthering Waves beach sample preserves user text `弗糯糯` as a source
  alias while resolving the intended canonical character identity to `弗洛洛`;
- the Little Gwen sample binds `image_little_gwen_ref` to
  `subject_little_gwen` and requires the subject concept generation to consume
  that image input;
- the rover sample requires fresh subject/scene concept requirements before the
  final target render, instead of reusing an old QA preview as a concept image.

## Required Node Boundaries

Key V1 nodes:

- `UserIntentRouter`
- `ReferenceBindingValidator`
- `SceneInterpreter`
- `SceneSpecCompiler`
- `ConceptPromptPlanner`
- `ConceptVisualQA`
- `FeedbackPatchParser`
- `RegenerationRouter`
- `SceneAssetAdapterPlanner`
- `BlenderAssemblyPlanner`
- `BlenderPreviewReviewGate`
- `BlenderEditRouter`

All key outputs must be represented by Pydantic models or existing state models
before they are allowed to change `AgentProjectState`.

## User Gates

Default confirmation gates:

- Gate #1: `CONCEPT_REVIEW`
  - User must approve the concept bundle before subject/scene generation.
  - Feedback becomes `ReviewPatch[]`.

- Gate #2: `BLENDER_PREVIEW`
  - User must approve the assembled Blender/viewer result before delivery.
  - Feedback is routed by `BlenderEditRouter`.

3D subject assets are not a default mandatory user gate. They interrupt only
when QA fails, is uncertain, or the user asks to inspect them.

## Live Tool Boundary

LLM nodes may propose tool intents, but code executes tools. Live Qwen/DeepSeek,
image generation, Hunyuan3D, HY-World, and non-dry-run Blender MCP calls require
an explicit command boundary and recorded outputs.
