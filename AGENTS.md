# AGENTS.md

Project-level instructions for coding agents working in this repository.

Global agent instructions still apply. These project rules take precedence when
they are more specific.

## Project Goal

Build a real image/text-to-Blender-scene agent, not only scaffolding.

The V1 delivery target is one inspectable end-to-end demo:

```text
user prompt/reference
  -> SceneSpec
  -> concept image(s)
  -> subject GLB
  -> scene/world asset
  -> Blender assembly
  -> viewer export
  -> frontend_status.json
  -> delivery package
```

## Highest Execution Plan

The governing plan for this repository is the combined plan from:

1. the user's current direction in the active conversation;
2. the V1 Chinese design docs under
   `blender_scene_agent_docs_v1_zh_v0_3/blender_scene_agent_docs_v1_zh_v0_3/`;
3. current active docs under `docs/`;
4. current code, tests, runtime evidence, and generated artifacts.

`docs/olddocs/` is a historical/reference archive. Do not treat files under
`docs/olddocs/` as the governing plan unless the user explicitly asks for a
historical audit or comparison.

When these disagree, current user instruction and current repository/runtime
evidence win. Update stale docs after verification instead of adding a second
conflicting note.

The highest-level workflow is:

```text
natural-language request + reference images
  -> explicit reference-image bindings
  -> structured SceneSpec / open questions
  -> ConceptPromptPack
  -> generated or registered concept images
  -> user confirmation gate #1
  -> subject and scene asset generation/adaptation
  -> Blender authoritative assembly
  -> Web viewer snapshot plus optional Blender render preview
  -> user confirmation gate #2
  -> delivery package
```

This is a state-driven workflow, not an open-ended ReAct agent. LLM/MLLM nodes
may understand, normalize, plan, route, and QA. They must not become the fact
source, directly execute raw MCP tools, or hide live service calls.

## Current Operating Principle

Visible artifacts beat abstract scaffolding.

Do not count a feature as complete unless it has:

- a concrete output artifact or an explicit dry-run/fake-service boundary;
- `state.json` / `summary.json` / `frontend_status.json` where applicable;
- a verification command and result;
- a short note in the relevant project doc.

The current priority is the agent control layer that makes the product flow
real: prompt contracts, reference-image schema, controller gates, and artifact
ingestion paths. Do not spend another slice only adding service-wrapper
scaffolding unless it directly unblocks the end-to-end workflow above.

## Execution Harness

For any non-trivial implementation, planning, workflow, runtime,
frontend-status, or model-service work, read and follow:

```text
docs/agent_execution_harness/README.md
docs/agent_execution_harness/task_packet_template.md
docs/agent_execution_harness/runtime_flow_rules.md
docs/agent_execution_harness/live_test_policy.md
docs/agent_execution_harness/documentation_maintenance.md
```

Use the task packet format for scoped work. Do not treat dry-run, fixture, or
delegated evidence as live completion. Do not bypass runtime user-action gates
or handoff-apply boundaries. Record tests, changed files, live calls, errors,
and documentation updates in the final report.

## Sub-Agent Policy

The user has authorized this conversation to spawn any number of sub-agents when
useful.

Agents may independently spawn sub-agents for:

- read-only audits of existing code, scripts, docs, and runtime state;
- disjoint implementation slices with clearly assigned file ownership;
- independent verification or smoke-test review;
- directory/repo hygiene audits;
- service-readiness checks that do not submit long-running jobs.

Rules for sub-agents:

- Use sub-agents to materially advance the task, not to duplicate the main
  agent's work.
- Give each sub-agent a narrow, concrete scope.
- For coding sub-agents, assign disjoint write ownership.
- Sub-agents must not revert unrelated user or agent changes.
- Sub-agent results must be integrated into this repository's docs/state, not
  left only in chat.
- Long-running live generation jobs still require an explicit main-agent command
  boundary and should record command, output directory, state, summary, and logs.

## Reuse-First Rule

This repository already contains substantial infrastructure. Before adding a new
module, service wrapper, viewer, generation client, queue, or state store:

1. search existing code/docs/scripts;
2. identify the reusable component;
3. extend or wrap it if practical;
4. record the reuse decision when the change is non-trivial.

Do not create parallel implementations of:

- Hunyuan3D service access;
- HY-World/WorldMirror service access;
- Blender compose/export helpers;
- GLB viewer runtime;
- artifact storage;
- project state/checkpoints;
- pending-action/review-patch feedback handling.

DOC-003 contains a known pasted-string issue in one phase tool whitelist around
viewer export/render preview. Treat `agent_runtime/domain_tools.py` as the local
executable domain-tool registry, with `export_viewer_scene` and `render_preview`
kept as separate tools.

## Prompt, Schema, And Controller Rules

For non-trivial prompt, schema, controller, or workflow work, read the relevant
V1 plan docs first:

- `DOC-002_Product_Workflow_Spec_v0.2_zh.md`
- `DOC-003_Agent_Workflow_Design_v0.2_zh.md`
- `DOC-004_State_and_JSON_Schema_Spec_v0.2_zh.md`
- `DOC-008_LLM_Node_and_Prompt_Spec_v0.2_zh.md`

Required implementation boundaries:

- All key LLM nodes output JSON validated by Pydantic models.
- Each LLM node receives only the minimal context view needed for that node.
- Uploaded/reference images must have explicit user-declared bindings before
  high-cost generation proceeds.
- Missing image purpose, missing SceneSpec fields, uncertain visual QA, and
  unclear user approval must become `PendingAction` or open questions.
- User concept feedback becomes `ReviewPatch[]` before regeneration.
- Hunyuan3D runs only after concept approval, except for explicit diagnostic
  tests.
- Blender remains the authoritative editable scene; the Web viewer is a
  derived GLB/glTF + `scene_state.json` snapshot.
- Raw Blender MCP tools stay behind domain tools and phase whitelists.

## Directory And Git Policy

Follow `docs/repo_layout.md`.

Track source, tests, lightweight docs, scripts, web runtime code, and selected
small reusable assets. Do not track:

- API keys or `.env*`;
- local virtual environments;
- `models/`;
- `outputs/`;
- `run_logs/`;
- Hunyuan3D/HY-World service repos;
- model/checkpoint binaries;
- `node_modules/`, build outputs, caches.

Use git for evidence after it has been initialized:

```bash
git status --short
git status --ignored --short
```

Do not commit unless the user explicitly asks.

## Runtime Safety

Allowed by default:

- read-only inspection;
- local tests;
- dry-runs;
- fake-service tests;
- status checks;
- registering explicitly provided local artifacts.

Needs an explicit command boundary with recorded outputs:

- live Qwen/DeepSeek requests;
- ChatGPT/image-generation calls intended as project artifacts;
- live Hunyuan3D generation;
- live HY-World/WorldMirror upload/reconstruct jobs;
- non-dry-run Blender edits through MCP.

## Required Docs

Use:

- `docs/README.md` as the docs index;
- `docs/agent_execution_harness/README.md` as the execution harness entrypoint;
- `docs/agent_execution_harness/task_packet_template.md` for non-trivial task packets;
- `docs/agent_execution_harness/runtime_flow_rules.md` for state/runtime boundaries;
- `docs/agent_execution_harness/live_test_policy.md` for live-service boundaries;
- current active roadmap, status, demo, prompt, schema, controller, runtime, and
  layout docs when they exist directly under `docs/`.

Update docs when the actual state changes. Do not let docs claim live generation
has run unless it actually ran.
