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
