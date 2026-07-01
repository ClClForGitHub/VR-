# Round04B Codex Task Packet: Unblock Real Concept Image Execution

## Goal

Round04 correctly refused to fake results, but it exposed a blocking gap: the repo has no project-integrated live executor for multi-requirement concept generation with real reference-image attachments and target-render composition.

This round must implement that missing backend/runtime boundary, then run a canary live case. Do not run all 12 cases until the canary proves real concept artifacts exist and are applied through runtime state.

## Base branch

```bash
git fetch origin
git checkout round04-live-user-samples-full-flow
git pull --ff-only origin round04-live-user-samples-full-flow
git checkout -b round04b-live-concept-executor
```

## Must inspect first

Read these files before writing code:

```text
AGENTS.md
docs/agent_execution_harness/README.md
docs/agent_execution_harness/round_04_live_full_flow_user_samples.md
docs/agent_execution_harness/round_04_completion_report.md
agent_runtime/runtime_delegation.py
agent_runtime/runtime_worker.py
agent_runtime/runtime_handoff_apply.py
agent_runtime/codex_self_mcp.py
agent_runtime/llm_nodes.py
agent_runtime/llm_providers.py
agent_runtime/concept_planning.py
agent_runtime/frontend_status.py
scripts/run_round04_live_user_samples.py
tools/runtime_console_server.py
```

Also inspect the local codex-self helper before deciding whether it can be used:

```text
/home/team/zouzhiyuan/codex-self-mcp/
/home/team/zouzhiyuan/codex-self-mcp/scripts/call_codex_mcp.py
```

## Diagnosis to preserve

Round04 live mode currently does this:

- uploads user images and records chat;
- directly constructs SceneSpec and prompt pack from the manifest;
- writes blocked generation rows;
- does not call a live LLM, live image backend, Hunyuan3D, HY-World, or Blender.

Existing `codex_self_mcp` worker also deliberately rejects multi-requirement concept handoffs, required input images, and source requirement dependencies. That guard must not be deleted unless a real structured backend replaces it and tests prove image attachment works.

## Required implementation

### 1. Add a real concept image execution module

Add a module such as:

```text
agent_runtime/concept_image_execution.py
```

It must define typed contracts roughly like:

```text
ConceptImageExecutionRequest
ConceptImageExecutionCallRecord
ConceptImageExecutionResult
ConceptImageBackendCapability
ConceptImageBackend
```

The executor must consume the existing `concept_generation` handoff payload, not invent a second schema.

For each `ConceptImageRequirement`, it must run in dependency order:

1. `text_to_image`: prompt only.
2. `image_guided`: attach every resolved `input_reference_image_ids` file as actual image input.
3. `multi_image_composite`: resolve `source_requirement_ids` to earlier generated output paths and attach those generated images.

For every call, write one row to:

```text
<run_dir>/live_generation_calls.jsonl
```

Each row must include:

```json
{
  "requirement_id": "...",
  "output_type": "subject_concept | scene_concept | target_render",
  "generation_mode": "text_to_image | image_guided | multi_image_composite",
  "prompt": "...",
  "input_reference_image_ids": [],
  "input_image_paths": [],
  "source_requirement_ids": [],
  "source_image_paths": [],
  "backend": "...",
  "started_at": "...",
  "finished_at": "...",
  "output_image_path": "/absolute/path/to/generated.png",
  "ok": true,
  "issues": []
}
```

If image attachments are required but not supported, the call must fail with a clear issue. Do not silently downgrade to text-only.

### 2. Implement or prove a backend

Preferred backend order:

1. A structured codex-self/MCP backend, only if actual reference-image attachment and multi-image composition can be proven.
2. A direct configured image provider backend, only if it supports image-guided and multi-image-composite calls with real local files.
3. No fallback fake backend for live acceptance.

Add a read-only/capability command:

```text
scripts/probe_live_image_backend.py
```

It must test and report:

```text
text_to_image supported?
one reference image input supported?
two/multi image composite supported?
output file extraction supported?
where logs are written?
```

If the current codex-self helper cannot attach files, keep it blocked and document exactly why.

### 3. Integrate executor into runtime worker

Modify `agent_runtime/runtime_worker.py` so concept handoffs can be executed by the new backend, for example:

```text
backend="live_image"
```

or a clearer name discovered during implementation.

The worker must:

- read the handoff JSON;
- call the concept executor;
- produce `image_results` with one item per generated requirement;
- call the existing `apply_concept_handoff_result` / handoff-apply path;
- never edit `state.json` directly.

The existing `runtime_handoff_apply.py` already knows how to register subject_concept, scene_concept, and target_render artifacts. Reuse it.

### 4. Fix Round04 runner live path

`scripts/run_round04_live_user_samples.py` currently blocks immediately in live mode. Replace that path with real runtime execution for one canary.

Minimum acceptable canary:

```bash
python scripts/run_round04_live_user_samples.py \
  --case case_03_lunar_rover \
  --live \
  --overwrite \
  --max-concept-regens 1
```

For canary acceptance, concept generation must not be blocked. It must create real image artifacts and apply them into state.

### 5. Natural-language + reference-image live path

Round04 runner may use the manifest to simulate user uploads and explicit bindings. It must not use manifest expected subjects as the source of truth for live acceptance unless that mode is marked `seeded_non_acceptance`.

Add one of these modes explicitly:

```text
--live-llm-intake
```

or:

```text
--seeded-scene-spec
```

Acceptance mode must be `--live-llm-intake` for at least one canary unless provider access is unavailable. If provider access is unavailable, record that blocker and do not claim full live acceptance.

### 6. Downstream stages after concept artifacts exist

After concept artifacts are applied:

- select one subject concept for Hunyuan3D;
- run or hand off Hunyuan3D through the existing path;
- select scene/target concept for HY-World/WorldMirror or explicitly record why scene generation is blocked;
- only then run Blender assembly/export/preview through existing domain/runtime tools.

Do not start Hunyuan3D from a missing or fake concept file.

## Required tests

Add focused tests. Suggested files:

```text
tests/test_concept_image_execution_contract.py
tests/test_runtime_worker_live_image_backend.py
tests/test_round04_live_canary_execution.py
```

Tests must verify:

1. image-guided requirements fail when required local input paths cannot be attached;
2. target_render fails if source_requirement images are missing;
3. execution order resolves target_render source images from earlier outputs;
4. successful execution yields `image_results` compatible with handoff-apply;
5. `live_generation_calls.jsonl` has non-null `output_image_path` for successful calls;
6. Round04 canary does not report concept generation as blocked when the backend succeeds.

Test doubles are allowed only for unit tests. They must not be used as live acceptance.

## Required live commands

Run these in order and record results:

```bash
python scripts/probe_live_image_backend.py --write-report outputs/runs/round04b_probe/live_image_backend_probe.json
python -m pytest tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py -q
python -m pytest -q
python scripts/run_round04_live_user_samples.py --case case_03_lunar_rover --live --overwrite --max-concept-regens 1
```

If the canary cannot finish downstream Hunyuan3D/HY-World/Blender, it must at least pass real concept generation and clearly block at the next real missing boundary.

## Documentation updates

Update or add:

```text
docs/agent_execution_harness/round_04b_live_concept_executor_unblock.md
docs/agent_execution_harness/live_test_readiness_matrix.md
docs/agent_execution_harness/progress_log.md
docs/agent_execution_harness/decision_log.md
```

## Forbidden shortcuts

- Do not create placeholder PNGs.
- Do not copy input reference images as generated concept images.
- Do not write fake `output_image_path` rows.
- Do not directly edit `state.json` for generated artifacts.
- Do not bypass `runtime_handoff_apply`.
- Do not delete the existing codex-self guard unless a real replacement backend proves support.
- Do not run all 12 cases before the canary passes real concept generation.

## Commit/push

After tests and canary:

```bash
git status --short
git status --ignored --short
git add <intentional files>
git commit -m "Add Round04B live concept executor"
git push -u origin round04b-live-concept-executor
```
