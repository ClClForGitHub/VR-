# V1 Landing Progress

Last updated: 2026-06-30

## Current Objective

Land the `blender_scene_agent_docs_v1_zh_v0_3` plan into code, tests, audits, and actionable next steps without rebuilding infrastructure that already exists in this workspace.

## Standing Landing Rule

Future V1 landing work must start from existing infrastructure inventory, not from a blank implementation plan.

Before adding a new service wrapper, Blender script, viewer path, MCP adapter, orchestration node, asset checker, or smoke runner:

1. Run or update the read-only inventory:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.infra_inventory --root /home/team/zouzhiyuan/image23D_Agent --json
   ```

2. Check the existing scripts/tools/docs that overlap with the new work:

   ```text
   docs/runtime_environment_plan.md
   docs/blender_asset_pipeline_contract.md
   docs/agent_llm_provider_notes.md
   scripts/start_a40_services.sh
   scripts/status_a40_services.sh
   scripts/start_blender51_lab_mcp_bridge.sh
   scripts/status_blender51_lab_mcp_bridge.sh
   scripts/status_glb_viewer.sh
   scripts/start_runtime_console.sh
   scripts/status_runtime_console.sh
   scripts/stop_runtime_console.sh
   tools/compose_blender_scene.py
   tools/render_glb_preview.py
   tools/export_viewer_scene.py
   tools/glb_viewer_server.py
   tools/runtime_console_server.py
   Hunyuan3D-2.1/
   HY-World-2.0/
   third_party/
   web/
   outputs/
   run_logs/
   /home/team/zouzhiyuan/codex-self-mcp
   ```

3. Prefer a thin adapter over a replacement implementation when an existing entry already provides the behavior.

4. If reuse is not possible, record the reason in this progress file or the relevant task plan before writing the new component.

## Implemented In This Slice

Added a thin runtime layer under `agent_runtime/`:

- `agent_runtime/state.py`
  - Pydantic models for V1 workflow phases, user intents, artifact types, user turns, input images, reference bindings, artifact records, and project state.
  - Implements the core DOC-004 fact-source schemas: `SceneSpec`, `SubjectSpec`, `SpatialRelation`, `ConceptBundle`, `ReviewPatch`, `Asset3DRecord`, `Scene3DRecord`, `BlenderSceneState`, `ViewerSceneState`, `RenderSettings`, placement planning records, `PendingAction`, `ToolCallRecord`, and `WorkflowError`.
  - Keeps compatibility fields needed by the existing tool executor and viewer export helper while exposing DOC-004-compatible fields for future nodes.
  - Enforces the V1 boundary that implicit reference-image bindings are rejected unless an operator override is added later.

- `agent_runtime/artifacts.py`
  - Filesystem artifact metadata store.
  - Registers existing files or copies files into a store.
  - Records only metadata in state: artifact id, type, URI, MIME type, size, SHA256, version, timestamps, and metadata.
  - Adds explicit MIME handling for `.glb`, `.gltf`, and `.blend`.

- `agent_runtime/persistence.py`
  - Adds a file-backed `AgentProjectState` checkpoint store aligned with DOC-003 checkpoint recovery and DOC-005 project-version snapshot semantics.
  - Writes immutable JSON state snapshots under `checkpoints/snapshots/`, append-only `checkpoints.jsonl`, and append-only `events.jsonl`.
  - Records checkpoint id, project id, thread id, phase, state schema version, parent checkpoint id, reason, node name, artifact ids, important artifact ids, tool-call count, snapshot URI, and snapshot SHA256.
  - Supports checkpoint save/load/latest/restore and records `checkpoint_created` / `checkpoint_restored` events.
  - Supports parent checkpoint ids, so workflow stage checkpoints and final workflow checkpoints can form an auditable recovery chain.
  - Exposes a small `langgraph_thread_config(...)` helper for later LangGraph wiring without introducing a graph runner yet.

- `agent_runtime/langgraph_adapter.py`
  - Adds real LangGraph dependency diagnostics without pretending the current local runner is already a LangGraph graph.
  - Checks whether `langgraph`, `langgraph.graph`, and `langgraph.checkpoint` are importable and reports missing modules explicitly.
  - Builds a checkpoint wiring plan from `AgentProjectState`, `langgraph_thread_config(...)`, and `FileStateCheckpointStore` paths.
  - Records pending work needed before true graph execution: install/enable LangGraph, implement a checkpointer adapter, wire DOC-003 node boundaries, and run a real graph smoke.

- `agent_runtime/infra_inventory.py`
  - Read-only inventory of reusable project infrastructure.
  - Checks required docs, service scripts, Blender/GLB tools, local Hunyuan3D/HY-World repos, `third_party/`, `web/`, and optional `codex-self-mcp`, Blender, and Codex CLI.
  - This is the code-level enforcement hook for the "do not rebuild existing wheels" rule.

- `agent_runtime/codex_self_mcp.py`
  - Adds a thin adapter over `/home/team/zouzhiyuan/codex-self-mcp`.
  - Checks the existing client script, local Codex CLI, `codex login status`, `codex mcp-server` support, and `codex mcp list` evidence.
  - Builds explicit `scripts/call_codex_mcp.py` command plans for inline prompts or prompt files, including cwd, sandbox, approval policy, timeout, log path, and optional image-result extraction.
  - Adds `run_call_plan(...)` to return structured stdout/stderr/return-code results when an explicitly confirmed caller executes a planned handoff.
  - Supports an explicit `MCP_OK` smoke path; smoke is not run by default.
  - Keeps `codex-self-mcp` as a sub-agent/MCP channel, not an ordinary Qwen/DeepSeek-style LLM provider.

- `agent_runtime/mcp_client_manager.py`
  - Adds the DOC-006 `MCPClientManager` boundary without creating a new MCP transport.
  - Registers the existing `blender_lab` channel and `/home/team/zouzhiyuan/codex-self-mcp` sub-agent channel as managed server entries.
  - Caches the allowed raw tool surface for Blender Lab MCP: `get_objects_summary` and fixed-template `execute_blender_code`.
  - Provides health checks, missing raw-caller diagnostics, raw tool call logging, and a `raw_tool_caller_for(...)` injection bridge for domain dispatchers.
  - Keeps raw tool execution behind deterministic runtime injection; no LLM node receives the full raw MCP tool surface.

- `agent_runtime/blender_mcp.py`
  - Adds a thin Blender Lab MCP status adapter over existing infrastructure instead of creating another Blender controller.
  - Reuses `scripts/status_blender51_lab_mcp_bridge.sh`, the current Codex `mcp list`, and the existing Blender Lab bridge socket at `127.0.0.1:9876`.
  - Reports Blender version, bridge running state, socket availability, Codex CLI path, whether `blender_lab` is configured, and explicit issues.
  - Adds `BlenderLabSocketRawToolCaller`, a local raw-caller bridge over the existing Blender Lab add-on socket and bundled third-party toolcode.
  - The socket caller supports only the allowed raw V1 surface needed by the safe planner: `get_objects_summary` and fixed-template `execute_blender_code`.
  - Adds a deterministic `sync_blender_scene_state_from_objects_summary(...)` helper that converts the raw `get_objects_summary` MCP response into `BlenderSceneState`.
  - Adds `build_safe_blender_mcp_operation_plan(...)` to map selected V1 Blender domain tools into constrained `get_objects_summary` or fixed-template `execute_blender_code` raw MCP call plans.
  - Validates phase allowlists, object identity against `BlenderSceneState`, transform vector shape, camera/light/material parameters, and destructive delete confirmation before producing a raw MCP plan.
  - Keeps raw MCP tools out of the LLM-visible surface; this module is a read/status/synchronization and safe-plan adapter, not a new arbitrary Blender Python execution surface.

- `agent_runtime/domain_tools.py`
  - Deterministic DOC-006 domain-tool registry.
  - Maps workflow phases to allowed domain tools.
  - Provides guards so LLM nodes cannot request raw or phase-inappropriate tools.
  - Adds the DOC-006 required `get_blender_scene_summary` domain tool for Blender assembly/edit phases.

- `agent_runtime/domain_dispatcher.py`
  - Adds DOC-006 domain-tool dispatchers over existing local infrastructure.
  - Dispatches `import_scene_asset`, `export_viewer_scene`, and `render_preview` to existing script adapters and `ToolExecutor`.
  - Keeps phase guards, dry-run behavior, stdout/stderr capture, and tool-call logging centralized in `ToolExecutor`.
  - Dispatches safe Blender Lab MCP-backed domain tools through `BlenderMCPDomainToolDispatcher`.
  - Uses `build_safe_blender_mcp_operation_plan(...)` before any raw MCP call, then calls an injected raw MCP tool caller so runtime wiring stays outside the business logic.
  - Can construct `BlenderMCPDomainToolDispatcher` from `MCPClientManager`, so future runtime code has one managed raw-call boundary instead of ad hoc per-node injection.
  - Supports dry-run plan logging, real raw tool execution, `get_objects_summary` readback, `BlenderSceneState` resynchronization through `SceneStateSynchronizer`, and `ToolCallRecord` / `WorkflowError` recording.
  - Records failed plan validation and sync failures explicitly instead of treating raw MCP success as sufficient scene-state success.
  - Dispatches `build_subject_asset` to the existing Hunyuan3D FastAPI service adapter through explicit `submit_async`, `check_status`, and `save_completed` operations.
  - Registers completed Hunyuan3D subject assets through `FileArtifactStore` and updates `AgentProjectState.subject_assets` through the DOC-004 mutation guard.
  - Dispatches WorldMirror/HY-World scene-asset status, generation call planning, explicit queued input upload, queued reconstruction submission/polling, and output adaptation through `WorldMirrorDomainToolDispatcher`.
  - Supports explicit `build_scene_asset:runtime_status`, `build_scene_asset:prepare_generation`, `build_scene_asset:upload_inputs`, `build_scene_asset:poll_upload`, `build_scene_asset:submit_generation`, `build_scene_asset:poll_generation`, `adapt_scene_asset:inspect_output`, and `adapt_scene_asset:register_existing_output` operations without hiding long-running generation.
  - `prepare_generation` builds the Gradio upload/reconstruct call plan and records `submits_long_running_job=false`; it does not submit the HY-World reconstruction job.
  - `upload_inputs` and `poll_upload` require explicit confirmation outside dry-run and expose the `_on_upload` event-id and `target_dir` boundary.
  - `submit_generation` and `poll_generation` require explicit confirmation flags outside dry-run and record whether they may trigger long-running queued work.
  - Redacts image/model base64 payloads in tool-call arguments and outputs.
  - Rejects unsupported domain tools instead of silently falling back to raw tools.

- `agent_runtime/service_adapters.py`
  - Adds adapters for existing services started by `scripts/start_a40_services.sh`.
  - `Hunyuan3DServiceAdapter` follows the current local `Hunyuan3D-2.1/api_models.py` request schema and supports health checks, payload building, async task submit/status, and base64 GLB saving.
  - `WorldMirrorServiceAdapter` checks the existing HY-World Gradio runtime through `/` and `/config`.
  - The WorldMirror status adapter handles Gradio's `/config` HEAD 405 behavior by falling back to GET.
  - Extracts the live Gradio `/config` contract for `_on_upload` and `gradio_demo`, including api prefix, protocol, queue/connection mode, input ids, output ids, and component metadata.
  - Builds explicit WorldMirror generation call plans with upload/reconstruct URLs and payload shapes for either local input files or an existing `target_dir` workspace.
  - Adds Gradio queued-call primitives for `POST /gradio_api/call/<api_name>` event-id submission and `GET /gradio_api/call/<api_name>/<event_id>` SSE polling.
  - Adds SSE event parsing for Gradio queue responses, target-dir extraction from `_on_upload` results, upload-submit helpers for local input files, and reconstruction-submit helpers for `target_dir` workspaces.
  - Generation submission remains explicit and is not called by status checks, unit tests, or the `prepare_generation` workflow stage.

- `agent_runtime/llm_providers.py`
  - Adds a small OpenAI-compatible chat adapter for later agent LLM testing.
  - Loads Qwen and DeepSeek configuration from environment variables or the local ignored env file.
  - Exposes provider summaries with key suffixes only; plaintext keys are never written to ordinary docs or runner summaries.
  - Keeps Qwen first in provider priority and marks DeepSeek as text-only until a vision-capable DeepSeek path is explicitly configured.

- `agent_runtime/visual_qa.py`
  - Adds MLLM subject-asset visual QA scaffolding for comparing a source subject image with a rendered asset preview.
  - Builds strict JSON-response chat-completion requests and supports dry-run mode for request-shape validation without sending API calls.
  - Selects the first configured vision-capable provider, currently Qwen via `QWEN_VISION_MODEL`.
  - Parses provider JSON into `SubjectAssetVisualQAResult` with `pass` / `fail` / `uncertain`, score, issues, suggested action, and reasoning.

- `agent_runtime/delivery_handoff.py`
  - Builds front-end/delivery handoff metadata from `AgentProjectState.viewer_scene` and existing viewer artifact metadata.
  - Extracts viewer scene/state artifact ids, object count, viewer URLs, runtime/model-check status, preview id, and blend-file id.
  - Reports `ready`, `verified`, and explicit missing-field issues instead of hiding incomplete delivery state.
  - Does not start a viewer service or define another scene serialization format.

- `agent_runtime/frontend_status.py`
  - Builds DOC-002-style front-end status snapshots from `AgentProjectState` and workflow summaries.
  - Reports project/thread id, phase, current stage, current node, progress label, requested/executed stages, stage progress, pending user/manual action, artifact ids, subject asset ids, scene/viewer/blender ids, and tool-call count.
  - Summarizes `PendingAction` into a small UI-facing handoff record for user/manual review without creating another queue or state source.
  - Marks runs as `completed`, `attention_required`, or `needs_user_action` from the authoritative state and checkpoint-backed stage summary.

- `agent_runtime/review_patches.py`
  - Converts an existing `PendingAction` plus explicit user feedback text into a structured DOC-005 `ReviewPatch`.
  - Supports the current subject-asset repair handoff shape: target subject id, source image id, asset id, repair decision, affected artifact ids, pending action id, and pending status.
  - Clears the pending action by default and moves the state to `CONCEPT_REVIEW`, preparing the later concept-regeneration route without calling an LLM or image generator.
  - Reuses `AgentProjectState`, `ReviewPatch`, `PendingAction`, and `apply_state_updates(...)`; it does not introduce another feedback queue or state store.

- `agent_runtime/concept_regeneration.py`
  - Consumes pending subject-targeted `ReviewPatch` records back into the existing `ConceptBundle` / `SUBJECT_CONCEPT_IMAGE` artifact path.
  - Dry-run mode records the regeneration plan, target subject, prior concept-image ids, invalidated asset ids, and intended `regenerate_concept_images` domain-tool boundary without calling an image model.
  - Non-dry-run mode requires an already produced/generated image path, registers it through `FileArtifactStore`, appends it to `ConceptBundle.subject_concept_images`, clears stale concept approval/visual-QA fields, and marks the patch as applied.
  - Reuses `AgentProjectState`, `ConceptBundle`, `ReviewPatch`, `FileArtifactStore`, and `apply_state_updates(...)`; it does not introduce another feedback queue or image-generation client.

- `agent_runtime/delivery_package.py`
  - Adds the deterministic V1 `DeliveryPackager` path from DOC-003/DOC-009.
  - Builds a package directory and zip from existing `AgentProjectState` artifact references.
  - Includes `.blend`, final preview render, `viewer_scene.glb` / `.gltf`, `scene_state.json`, subject assets, scene assets, `metadata.json`, and `version_manifest.json` when available.
  - Runs QG-009-style completeness checks and reports missing `.blend`, preview, viewer scene, viewer state, subject assets, or scene assets as explicit issues.
  - Registers the zip as an `EXPORT_PACKAGE` artifact when an artifact store is provided.

- `agent_runtime/scene_assets.py`
  - Adds SceneAssetAdapter helpers for existing WorldMirror/HY-World output directories.
  - Inspects output directories for `scene_All*.glb`, other scene GLB candidates, `camera_params.json`, `gaussians.ply`, `gaussians_kiri.ply`, `predictions.npz`, and input image count.
  - Selects direct mesh import when a scene GLB is present; falls back to warning states for gaussian or depth/camera reference outputs.
  - Registers existing WorldMirror outputs through `FileArtifactStore` and updates `AgentProjectState.scene_asset` through the DOC-004 `SceneAssetAdapter` mutation guard.

- `agent_runtime/asset_quality.py`
  - Adds QG-004 subject asset QA primitives from DOC-007/DOC-009.
  - Checks saved GLB URI, file existence, size, GLB magic/version, and declared length.
  - Produces `SubjectAssetQualityResult` with `pass` / `fail` / `uncertain`, score, issues, suggested action, and check evidence.
  - Updates `AgentProjectState.subject_assets` through the `SubjectAssetQualityEvaluator` mutation guard.
  - Optionally reuses the existing `render_preview` domain tool for preview-render QA; it does not add another renderer.
  - Can merge an injected or runner-produced MLLM visual QA result into the deterministic GLB QA decision.
  - Adds `SubjectAssetRepairDecision`, `plan_subject_asset_repair(...)`, `apply_subject_asset_repair_decision(...)`, and `quality_result_from_asset(...)` for the DOC-007 post-QA retry/fallback boundary.
  - Plans accept, one-shot Hunyuan3D retry, concept-image regeneration, user review, or manual review from QA status, visual issues, retry counts, and operator-requested review.
  - Keeps default failed/clear retry decisions internal to the workflow and marks only uncertain, requested-review, or exhausted/manual cases as user-visible.

- `agent_runtime/state_views.py`
  - Derives DOC-004 context views from `AgentProjectState` without creating a second fact source.
  - Implements `SceneInterpreterContext`, `ConceptPromptPlannerContext`, `BlenderAssemblyPlannerContext`, and `BlenderEditRouterContext` builders.
  - Adds deterministic concept/prompt summaries for LLM context without asking another LLM to summarize.
  - Adds DOC-004 mutation guards for controlled fact-source fields: `scene_spec`, `concept_bundle`, `subject_assets`, `scene_asset`, `blender_scene`, and `viewer_scene`.
  - Provides `apply_state_updates(...)` to return a validated state copy only after node ownership checks pass.

- `agent_runtime/workflow_runner.py`
  - Adds a small local workflow runner around existing project infrastructure.
  - Uses one `AgentProjectState` across compose, viewer export, viewer check, artifact registration, tool-call logging, `blender_scene`, and `viewer_scene`.
  - Reuses `agent_runtime.domain_dispatcher`, `agent_runtime.script_adapters`, `agent_runtime.tool_executor`, `agent_runtime.state_views.apply_state_updates`, `tools/compose_blender_scene.py`, `tools/export_viewer_scene.py`, and `agent_runtime.viewer.check_viewer_model`.
  - Records stage-level `context_views` summaries so runner output shows which DOC-004 typed context view or state projection each stage used, whether it was available, and which domain tools were phase-visible.
  - Supports explicit ordered stage selection with `--stages compose`, `--stages compose,export_viewer`, or the default full `compose,export_viewer,viewer_check`.
  - Adds a separate `subject-asset` workflow entrypoint that reuses `Hunyuan3DDomainToolDispatcher`, `Hunyuan3DServiceAdapter`, `FileArtifactStore`, and the same single `AgentProjectState` pattern.
  - The `subject-asset` workflow supports explicit `submit`, `check_status`, `save_completed`, `quality_check`, `repair_decision`, and `repair_execute` stages. It does not poll indefinitely and does not submit live generation unless the caller explicitly requests a non-dry-run submit or explicitly confirms repair execution.
  - The `quality_check` stage can validate a saved asset from the same run or an existing GLB path supplied through `--output-glb`, and registers that existing GLB into `ArtifactStore` for lineage.
  - The `quality_check` stage can request preview-render QA through `--qa-render-preview` and MLLM visual-QA request validation through `--qa-visual-dry-run`; `--qa-visual-live` is explicit and was not exercised in this slice.
  - The `repair_decision` stage records the next action after subject-asset QA: accept, retry Hunyuan3D once, regenerate the source concept image for semantic failures, ask the user for uncertain/requested review, or route to manual review when retries are exhausted.
  - The `repair_decision` stage updates the subject asset status/metadata in `AgentProjectState` and checkpoint output only; it does not itself submit another Hunyuan3D job or call an image-generation/API provider.
  - The `repair_execute` stage handles the planned action boundary: accept passed assets, dry-run Hunyuan3D retry plans through the existing dispatcher, block unconfirmed live retries, route subject-image regeneration back to `CONCEPT_GENERATION`, and create `PendingAction` records for user/manual review.
  - `repair_execute` stores execution evidence in subject asset metadata and stage/final checkpoints. A real Hunyuan3D retry can only be submitted by requesting this stage outside dry-run and passing `--confirm-repair-execute`.
  - The `local-e2e` workflow now writes `delivery_handoff.json` beside `summary.json` when a delivery handoff summary is available.
  - Adds a `scene-asset` workflow entrypoint for explicit WorldMirror runtime status, generation call planning, queued upload, queued reconstruct submit/poll boundaries, existing output inspection, and existing output registration.
  - The `scene-asset` workflow also supports `prepare_generation`, which records the WorldMirror upload/reconstruct call plan without invoking the long-running reconstruction job.
  - The `scene-asset` workflow supports `upload_inputs` and `poll_upload`; when `poll_upload` returns a `target_dir`, the same run can pass it forward as the effective workspace for `submit_generation`.
  - The `scene-asset` workflow supports `submit_generation` and `poll_generation`, both guarded by explicit confirmation flags outside dry-run.
  - The `scene-asset` workflow supports `save_generation`, which reuses existing WorldMirror output registration as the evidence-backed save path.
  - The default `scene-asset` workflow does not invoke long-running WorldMirror generation; it records runtime status, prepares explicit call plans, and adapts already-produced output directories unless the caller explicitly requests and confirms submit/poll stages.
  - Adds a `delivery-package` workflow entrypoint that consumes a saved `AgentProjectState` JSON and writes a deterministic zip package plus `metadata.json` and `version_manifest.json`.
  - Adds a `review-patch` workflow entrypoint that consumes a saved pending-action `AgentProjectState` JSON and explicit user feedback, writes a structured `ReviewPatch`, clears the pending action by default, records a checkpoint, and writes `frontend_status.json`.
  - Adds a `concept-seed` workflow entrypoint that registers an existing/generated local subject concept image into `ConceptBundle`, `FileArtifactStore`, stage checkpoints, and `frontend_status.json`.
  - Adds a `concept-regeneration` workflow entrypoint that consumes pending subject `ReviewPatch` records, dry-runs the regeneration plan by default, or registers an explicit generated image as a new `SUBJECT_CONCEPT_IMAGE` artifact and marks the patch applied when `--no-dry-run --generated-image-path` is supplied.
  - Adds a `codex-self` workflow entrypoint for explicit sub-agent handoff status checks, command-plan generation, and optional execution.
  - The `codex-self` workflow defaults to `status,plan_handoff`, writes state/summary/tool-log/checkpoints, and does not execute a sub-agent by default.
  - `codex-self execute_handoff` requires both a requested stage and explicit confirmation outside dry-run.
  - Adds a `blender-edit` workflow entrypoint that consumes a saved `AgentProjectState`, switches to `BLENDER_EDIT`, runs one safe Blender MCP-backed domain tool through `BlenderMCPDomainToolDispatcher`, syncs `BlenderSceneState` when a raw caller is injected, and writes state/log/checkpoint outputs.
  - The `blender-edit` CLI supports dry-run planning and state/checkpoint output; non-dry-run execution is explicit through `--raw-caller blender-lab-socket` or a Python-injected raw caller.
  - The `blender-edit` workflow can optionally refresh viewer export when a raw caller and authoritative `.blend` path are available, but this is not exercised by the plain dry-run CLI path.
  - Writes `checkpoints/` for every workflow output through `FileStateCheckpointStore`, so `summary.json` now points to the saved state snapshot, checkpoint index, and checkpoint event log.
  - Records stage-level checkpoint snapshots for executed stages in `local-e2e`, `subject-asset`, `scene-asset`, and `delivery-package`, then records a final workflow-output checkpoint whose parent is the last stage checkpoint.
  - Exposes `stage_checkpoints` in runner summaries with stage, workflow, reason, node name, parent checkpoint id, artifact ids, and snapshot hash for recovery/audit handoff.
  - Writes `frontend_status.json` for every workflow output, derived from the same `AgentProjectState`, stage checkpoints, and runner summary.
  - Provides CLI entrypoint:

    ```bash
    python -m agent_runtime.workflow_runner local-e2e ...
    python -m agent_runtime.workflow_runner subject-asset ...
    python -m agent_runtime.workflow_runner scene-asset ...
    python -m agent_runtime.workflow_runner delivery-package ...
    python -m agent_runtime.workflow_runner review-patch ...
    python -m agent_runtime.workflow_runner concept-seed ...
    python -m agent_runtime.workflow_runner concept-regeneration ...
    python -m agent_runtime.workflow_runner codex-self ...
    python -m agent_runtime.workflow_runner blender-edit ...
    ```

- `agent_runtime/script_adapters.py`
  - Command builders that wrap existing Blender scripts rather than replacing them.
  - Supports `tools/render_glb_preview.py`, `tools/compose_blender_scene.py`, and `tools/export_viewer_scene.py`.
  - Does not execute Blender directly; it returns explicit command plans for workflow/tool-executor nodes.

- `agent_runtime/tool_executor.py`
  - Phase-guarded command execution for domain tools.
  - Records structured `ToolCallRecord` entries into `AgentProjectState`.
  - Fills DOC-004-compatible `tool_name`, `arguments_summary`, `finished_at`, and `error_message` fields while preserving existing execution metadata.
  - Records `WorkflowError` on nonzero exits and timeouts.
  - Supports dry-run command logging and real subprocess execution.

- `agent_runtime/smoke.py`
  - Reusable smoke CLI for an existing GLB -> artifact store -> existing Blender preview script -> state/log/artifact outputs.
  - Reusable scene+subject composition smoke through the existing Blender composition script.
  - Reusable viewer export smoke for `viewer_scene.glb` and `scene_state.json`.
  - Validates live `scene_state.json` through `ViewerSceneState` and writes the parsed snapshot back to `AgentProjectState.viewer_scene`.
  - Orchestrated local E2E smoke: existing scene GLB + subject GLB -> Blender composition -> viewer export -> GLB viewer HEAD checks.
  - Resets smoke metadata and stale preview outputs by default so repeated smoke runs stay clean.

- `agent_runtime/viewer.py`
  - Builds GLB viewer asset/viewer URLs for absolute model paths.
  - Performs HEAD checks against the existing GLB viewer runtime.

- `agent_runtime/viewer_runtime.py`
  - Adds a thin runtime/status adapter around the existing `tools/glb_viewer_server.py` HTTP surface.
  - Checks viewer index and `/api/list` availability through HEAD requests.
  - Builds viewer artifact metadata with `asset_url`, `viewer_url`, runtime status, and model check results.
  - Annotates `VIEWER_SCENE_GLB` / `VIEWER_SCENE_GLTF` artifact records without creating another viewer implementation.

- `tools/export_viewer_scene.py`
  - Opens an authoritative `.blend` file in Blender.
  - Exports `viewer_scene.glb`.
  - Writes `scene_state.json` with object records, transforms, bounds, camera data, source blend path, and artifact-id placeholders.
  - The smoke layer patches artifact ids before registering `scene_state.json`, so the recorded hash covers the final traceable state file.

- `docs/agent_llm_provider_notes.md`
  - Records the user-supplied agent LLM provider priority without storing plaintext keys in ordinary documentation.
  - Qwen is the preferred provider for later agent testing, with DeepSeek as fallback/comparison.
  - Plaintext credentials are kept only in `/home/team/zouzhiyuan/image23D_Agent/.env.agent_llm.local`, which is ignored by the root `.gitignore` and should be loaded through environment variables.

Added tests under `tests/`:

- artifact store registration and no-binary-in-state behavior;
- artifact copy-into-store behavior;
- infrastructure inventory required-item checks;
- V1 reference-binding validation.
- domain-tool registry consistency and phase guards;
- command builders for existing Blender preview/composition scripts.
- ToolExecutor dry-run, success, failure, and phase-guard behavior;
- render-existing-GLB smoke dry-run state/log writing.
- compose-existing-scene smoke dry-run state/log writing;
- export-viewer-scene smoke dry-run state/log writing.
- local E2E smoke dry-run orchestration;
- viewer URL construction and failure reporting.
- DOC-004 core project-state fact-source models;
- DOC-004 score/version validators;
- compatibility with the current viewer exporter `scene_state.json` snapshot shape.
- DOC-004 context-view builders and minimal-context filtering;
- DOC-004 controlled state mutation guards for allowed and forbidden node updates.
- workflow runner dry-run single-state orchestration;
- workflow runner artifact metadata reset behavior.
- workflow runner Hunyuan3D subject-asset dry-run submit, submit/status/save artifact registration, missing-job failure, and stage-order validation;
- workflow runner stage `context_views` summaries for compose, subject-asset generation, and subject-asset QA;
- workflow runner subject-asset `repair_decision` stage for failed-QA retry plans and passed-QA acceptance plans;
- workflow runner subject-asset `repair_execute` stage for accept handling, dry-run retry planning, unconfirmed-live retry blocking, action-specific context tool exposure, checkpoint output, and user/manual-review pending actions;
- workflow runner WorldMirror scene-asset runtime-status, prepare-generation call planning, upload-input confirmation, upload-poll target-dir chaining, submit-generation confirmation, poll-generation confirmation, save-generation output registration, inspect-output, existing-output registration, and invalid-stage handling;
- WorldMirror generation contract extraction, call-plan construction for both local file upload and existing workspace inputs, queued upload submit, upload target-dir extraction, queued reconstruction submit, SSE poll parsing, and workspace-required guards before reconstruct submit;
- delivery/front-end handoff metadata ready/verified/missing-state behavior;
- frontend status snapshot generation for completed, failed/attention, and pending-user-action workflow states;
- ReviewPatch creation from subject-asset pending actions, missing-pending-action failure behavior, pending-action clearing, frontend-status review-patch id reporting, and `review-patch` workflow checkpoint output;
- initial concept seed workflow registration into artifact store, ConceptBundle, checkpoint output, and frontend status;
- ReviewPatch concept-regeneration consumption for dry-run planning, generated subject image artifact registration, ConceptBundle version/approval reset, applied patch status, missing-patch blocking, and `concept-regeneration` workflow checkpoint/frontend output;
- delivery package completeness checks, manifest/metadata writing, zip creation, and `EXPORT_PACKAGE` artifact registration;
- WorldMirror output inspection and SceneAssetAdapter state/artifact registration;
- QG-004 subject asset QA pass/fail/uncertain behavior, `SUBJECT_ASSET_QA` phase tool exposure, and optional `render_preview` dry-run integration;
- MLLM visual-QA dry-run/mocked-provider parsing and subject-asset QA result merging;
- DOC-007 subject asset repair-decision planning for failed GLB QA, uncertain visual QA, semantic visual failures, retry budgets, user-visible review routing, and state mutation through `SubjectAssetRepairRouter`;
- Qwen/DeepSeek provider config loading, defaults, priority, suffix-only public summaries, and vision boundary handling;
- script-backed domain-tool dispatcher success, missing-argument, unsupported-tool, and phase-guard behavior;
- Hunyuan3D-backed `build_subject_asset` dispatcher dry-run, submit/status/save, artifact registration, base64 redaction, and phase-guard behavior;
- Blender Lab MCP-backed dispatcher dry-run plan logging, real raw-tool execution through an injected caller, `BlenderSceneState` readback synchronization, failed-plan logging, sync-failure logging, and phase-guard behavior;
- Blender Lab socket raw-caller toolcode reuse, bridge host/port environment routing, execute-code argument validation, and unsupported raw-tool rejection;
- workflow runner `blender-edit` dry-run planning/checkpoint output, injected raw-caller execution and sync behavior, explicit `blender-lab-socket` raw-caller source execution, rejected-operation state/error recording, and non-dry-run missing-caller guard;
- workflow runner explicit stage selection and invalid stage rejection.
- workflow runner `codex-self` status/plan/execute-handoff confirmation behavior and structured fake execution results;
- file-backed `AgentProjectState` checkpoint save/load/latest/restore behavior, checkpoint events, snapshot SHA256, and LangGraph thread config.
- LangGraph dependency diagnostics, missing-parent-module handling, ready-module reporting, and checkpoint wiring-plan generation from `FileStateCheckpointStore`.
- workflow runner automatic stage/final checkpoint output, checkpoint parent chains, reason mapping, and checkpoint reset behavior across repeated runs.
- codex-self-mcp local status probing, command planning, explicit smoke behavior, and missing-helper/CLI reporting.
- MCPClientManager default server/tool registration, health diagnostics, injected raw-caller execution logging, missing-caller failure reporting, unregistered-tool rejection, and Blender dispatcher integration through the manager boundary.
- Blender Lab MCP local status probing, raw `get_objects_summary` to `BlenderSceneState` synchronization behavior, safe domain-operation plan generation, and destructive-operation confirmation guards.
- viewer runtime/status adapter behavior;
- viewer artifact metadata URL/check annotation.
- Hunyuan3D payload validation, health/status client behavior, base64 model saving, and current API schema boundaries;
- HY-World WorldMirror Gradio runtime status behavior, including GET fallback for `/config`.

## Verification

Commands run from `/home/team/zouzhiyuan/image23D_Agent`:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests -p no:cacheprovider
```

Result:

```text
200 passed in 1.43s
```

```bash
python -m compileall -q agent_runtime tools tests
find agent_runtime tools tests -type d -name __pycache__ -prune -exec rm -r {} +
```

Result:

```text
compileall passed; generated __pycache__ directories were removed.
```

```bash
rg -n 'sk-[A-Za-z0-9]+' docs agent_runtime tests scripts .gitignore
```

Result:

```text
No matches. Exit code 1 is expected for ripgrep when no secret-like strings are found.
```

```bash
python -m agent_runtime.infra_inventory --root /home/team/zouzhiyuan/image23D_Agent --json
```

Result summary:

```json
{
  "total": 20,
  "required": 15,
  "missing_required": [],
  "non_executable_required": [],
  "ok": true
}
```

MCP manager and LangGraph diagnostic audit:

```text
MCPClientManager registered blender_lab as the primary injected channel and codex_self_mcp as the sub-agent stdio channel.
blender_lab adapter_status.ok=true with Blender 5.1.2, bridge running, socket open, Codex CLI found, and blender_lab present in codex mcp list.
BlenderLabSocketRawToolCaller can read the live current Blender scene through the existing 127.0.0.1:9876 bridge.
codex_self_mcp manager health is ok=true through the existing helper and Codex CLI login; no Qwen/DeepSeek key was used.
check_langgraph_runtime reports installed=false with missing langgraph, langgraph.graph, and langgraph.checkpoint modules.
```

Blender edit socket workflow audit:

```text
Read-only non-dry-run CLI smoke passed with --raw-caller blender-lab-socket and get_blender_scene_summary.
The read-only smoke synchronized BlenderSceneState from the live scene: scene=Scene, active_object=Camera, object_count=3.
Controlled no-op edit smoke passed with --raw-caller blender-lab-socket and move_subject on 4fee0d5d-84e9-4bc2-979f-6c5ee338b485_texturing.obj to [0, 0, 0].
The no-op edit executed fixed-template execute_blender_code, then read back get_objects_summary, wrote state/tool logs, and recorded stage/final checkpoints under outputs/v1_landing_blender_edit_socket_noop_move/.
Post-smoke transform audit confirmed the mesh location remained [0.0, 0.0, 0.0].
```

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
import json
from agent_runtime.llm_providers import build_provider_configs, load_agent_llm_env, provider_public_summary

env = load_agent_llm_env('/home/team/zouzhiyuan/image23D_Agent/.env.agent_llm.local')
print(json.dumps(provider_public_summary(build_provider_configs(env=env)), ensure_ascii=False, indent=2, sort_keys=True))
PY
```

Agent LLM provider dry-run summary:

```json
[
  {
    "api_key_env": "QWEN_API_KEY",
    "api_key_suffix": "eeef",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen3.7-max",
    "model_alias": "QWEN 3.7max",
    "priority": 0,
    "provider": "qwen",
    "supports_vision": true,
    "vision_model": "qwen3.7-plus"
  },
  {
    "api_key_env": "DEEPSEEK_API_KEY",
    "api_key_suffix": "9c68",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "model_alias": "DeepSeek V4 flash",
    "priority": 1,
    "provider": "deepseek",
    "supports_vision": false,
    "vision_model": null
  }
]
```

Provider dry-run audit:

```text
Qwen remains the first provider.
Only API key suffixes were printed.
No chat-completions request was sent.
The local env file is ignored by .gitignore and has mode 600.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
import json
from agent_runtime.codex_self_mcp import CodexSelfMCPAdapter
status = CodexSelfMCPAdapter().status(
    run_smoke=True,
    smoke_cwd='/home/team/zouzhiyuan/safe',
    timeout_seconds=120,
)
print(json.dumps(status.model_dump(mode='json'), ensure_ascii=False, indent=2, sort_keys=True))
PY
```

Codex self MCP status summary:

```json
{
  "ok": true,
  "client_script_exists": true,
  "codex_cli_found": true,
  "login_status_ok": true,
  "mcp_server_supported": true,
  "configured_in_codex_mcp_list": false,
  "mcp_list_servers": ["blender_lab"],
  "smoke_ok": true,
  "issues": []
}
```

Codex self MCP audit:

```text
The actual local smoke returned MCP_OK through codex mcp-server.
Codex is logged in using ChatGPT, so this local self-MCP path did not require the Qwen/DeepSeek API keys.
The current Codex MCP list only includes blender_lab; direct stdio use through codex mcp-server still works.
The adapter records command plans and status evidence; workflow-level handoff planning is now wired, while full autonomous agent task routing remains future work.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner codex-self \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_codex_self_handoff_plan \
  --cwd /home/team/zouzhiyuan/image23D_Agent \
  --prompt "请作为子 agent 审阅当前 V1 landing handoff 摘要，只返回你会检查的三项，不要运行命令。" \
  --sandbox read-only \
  --approval-policy never \
  --stages status,plan_handoff \
  --dry-run
```

Codex self MCP workflow dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "executed_stages": ["status", "plan_handoff"],
  "status_ok": true,
  "plan_prompt_source": "inline",
  "plan_sandbox": "read-only",
  "plan_approval_policy": "never",
  "plan_cwd": "/home/team/zouzhiyuan/image23D_Agent",
  "checkpoint_reasons": [
    "codex_self_mcp_status_checked",
    "codex_self_mcp_handoff_planned"
  ]
}
```

Codex self MCP workflow audit:

```text
The workflow reused CodexSelfMCPAdapter and /home/team/zouzhiyuan/codex-self-mcp/scripts/call_codex_mcp.py.
The dry-run checked local Codex/codex-self-mcp status and wrote the handoff command plan.
No execute_handoff stage was requested, so no sub-agent task was run.
No Qwen or DeepSeek API key was used.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
import json
from agent_runtime.blender_mcp import BlenderMCPAdapter
status = BlenderMCPAdapter().status(timeout_seconds=30)
payload = status.model_dump(mode='json')
payload['status_output_tail'] = '<omitted>' if payload.get('status_output_tail') else None
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
PY
```

Blender MCP adapter status summary:

```json
{
  "ok": true,
  "blender_version": "Blender 5.1.2",
  "bridge_running": true,
  "socket_open": true,
  "configured_in_codex_mcp_list": true,
  "mcp_list_servers": ["blender_lab"],
  "issues": []
}
```

Blender MCP readback audit:

```text
The current session exposed blender_lab tools through tool discovery.
`get_objects_summary` returned scene_name=Scene, object_mode=OBJECT, active_object=Camera, and three objects in the current background Blender scene.
`get_blendfile_summary_path_info` returned is_saved=false and filepath="" for the current background scene.
`get_screenshot_of_window_as_json` returned an expected background-mode window-layout error, so window screenshots are not used as state evidence here.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner blender-edit \
  --state-json /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_adapter_workflow_e2e/state.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_blender_edit_dryrun \
  --tool get_blender_scene_summary \
  --dry-run
```

Blender edit workflow dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "phase": "BLENDER_EDIT",
  "domain_tool_name": "get_blender_scene_summary",
  "executed_stages": ["blender_edit"],
  "skipped_stages": {
    "export_viewer": "not_requested",
    "viewer_check": "not_requested"
  },
  "blender_edit": {
    "ok": true,
    "tool_call_status": "succeeded",
    "outputs": {
      "planned": true,
      "raw_tool_name": "get_objects_summary",
      "safety_notes": ["read_only_scene_summary"]
    }
  }
}
```

Blender edit workflow audit:

```text
The workflow consumed an existing single-state local E2E output state.
The CLI dry-run did not call raw MCP tools.
The workflow wrote state.json, tool_call_log.json, summary.json, and stage/final checkpoints under outputs/v1_landing_blender_edit_dryrun/.
The stage checkpoint reason was blender_edit_applied and the final checkpoint parent pointed to that stage checkpoint.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
import json
from agent_runtime.service_adapters import Hunyuan3DServiceAdapter, WorldMirrorServiceAdapter
print(json.dumps({
    "hunyuan3d": Hunyuan3DServiceAdapter(base_url="http://127.0.0.1:8091", timeout=10).health(),
    "worldmirror": WorldMirrorServiceAdapter(base_url="http://127.0.0.1:8081", timeout=10).runtime_status(),
}, ensure_ascii=False, indent=2, sort_keys=True))
PY
```

Service adapter status summary:

```json
{
  "hunyuan3d": {
    "ok": true,
    "health": {
      "status": 200,
      "content_type": "application/json",
      "data": {
        "status": "healthy",
        "worker_id": "89945b"
      }
    },
    "openapi": {
      "status": 200,
      "content_type": "application/json",
      "content_length": 7405
    }
  },
  "worldmirror": {
    "ok": true,
    "index": {
      "status": 200,
      "content_type": "text/html; charset=utf-8",
      "content_length": 176499
    },
    "config": {
      "status": 200,
      "content_type": "application/json",
      "content_length": 101521
    }
  }
}
```

Service adapter audit:

```text
Hunyuan3D adapter status checks used /health and /openapi.json only.
WorldMirror adapter status checks used / and /config; /config required GET fallback because Gradio returns 405 for HEAD.
No Hunyuan3D or WorldMirror generation job was submitted in this check.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner scene-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_scene_asset_prepare_generation \
  --scene-asset-id scene_asset_prepare_001 \
  --worldmirror-workspace-dir /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326 \
  --stages prepare_generation
```

WorldMirror prepare-generation summary:

```json
{
  "ok": true,
  "executed_stages": ["prepare_generation"],
  "prepared": true,
  "submits_long_running_job": false,
  "upload_url": "http://127.0.0.1:8081/gradio_api/call/_on_upload",
  "reconstruct_url": "http://127.0.0.1:8081/gradio_api/call/gradio_demo",
  "reconstruct_payload": {
    "data": [
      "/home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326",
      "All",
      true,
      false,
      true,
      true
    ]
  },
  "workspace_source": "provided_workspace_dir",
  "checkpoint_reason": "scene_generation_call_prepared"
}
```

WorldMirror prepare-generation audit:

```text
The workflow extracted the live Gradio 5.33.0 contract from /config.
The detected API prefix is /gradio_api with queued SSE endpoints.
The upload endpoint is _on_upload and the reconstruction endpoint is gradio_demo.
The stage wrote state.json, summary.json, tool_call_log.json, and stage/final checkpoints under outputs/v1_landing_scene_asset_prepare_generation/.
No long-running HY-World reconstruction job was submitted.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner scene-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_scene_asset_upload_inputs_dryrun \
  --scene-asset-id scene_asset_upload_001 \
  --worldmirror-input-files /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/example_images/example_000.png \
  --stages upload_inputs \
  --dry-run
```

WorldMirror upload-inputs dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "executed_stages": ["upload_inputs"],
  "submitted": false,
  "submits_long_running_job": false,
  "requires_confirmation": true,
  "upload_url": "http://127.0.0.1:8081/gradio_api/call/_on_upload",
  "upload_payload_file": "/home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/example_images/example_000.png",
  "time_interval": 1.0,
  "checkpoint_reason": "scene_generation_inputs_upload_stage_completed"
}
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner scene-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_scene_asset_poll_upload_dryrun \
  --scene-asset-id scene_asset_upload_poll_001 \
  --worldmirror-upload-event-id upload_evt_placeholder \
  --stages poll_upload \
  --dry-run
```

WorldMirror poll-upload dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "executed_stages": ["poll_upload"],
  "event_id": "upload_evt_placeholder",
  "polled": false,
  "submits_long_running_job": false,
  "requires_confirmation": true,
  "checkpoint_reason": "scene_generation_upload_poll_stage_completed"
}
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner scene-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_scene_asset_submit_generation_dryrun \
  --scene-asset-id scene_asset_submit_001 \
  --worldmirror-workspace-dir /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326 \
  --stages submit_generation \
  --dry-run
```

WorldMirror submit-generation dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "executed_stages": ["submit_generation"],
  "submitted": false,
  "submits_long_running_job": false,
  "requires_confirmation": true,
  "reconstruct_url": "http://127.0.0.1:8081/gradio_api/call/gradio_demo",
  "checkpoint_reason": "scene_generation_submit_stage_completed"
}
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner scene-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_scene_asset_poll_generation_dryrun \
  --scene-asset-id scene_asset_poll_001 \
  --worldmirror-event-id evt_placeholder \
  --stages poll_generation \
  --dry-run
```

WorldMirror poll-generation dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "executed_stages": ["poll_generation"],
  "event_id": "evt_placeholder",
  "polled": false,
  "submits_long_running_job": false,
  "requires_confirmation": true,
  "checkpoint_reason": "scene_generation_poll_stage_completed"
}
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner scene-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_scene_asset_save_generation_existing \
  --scene-asset-id scene_asset_save_001 \
  --worldmirror-output-dir /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326 \
  --stages save_generation
```

WorldMirror save-generation existing-output summary:

```json
{
  "ok": true,
  "executed_stages": ["save_generation"],
  "registered": true,
  "raw_output_type": "mesh",
  "blender_import_mode": "mesh_import",
  "adapted_artifact_ids": ["scene_asset_save_001_scene_glb"],
  "checkpoint_reason": "scene_generation_saved"
}
```

WorldMirror submit/poll/save audit:

```text
upload_inputs dry-run read the live /config contract and built the _on_upload payload shape, but did not POST to the Gradio queue.
poll_upload dry-run recorded the upload event-id/API boundary, but did not open the SSE stream.
submit_generation dry-run read the live /config contract and built the reconstruction call shape, but did not POST to the Gradio queue.
poll_generation dry-run recorded the event-id/API boundary, but did not open the SSE stream.
save_generation registered existing output files through SceneAssetAdapter and FileArtifactStore; it did not submit or poll HY-World generation.
No live HY-World long-running generation was submitted in these smokes.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner subject-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_subject_asset_dryrun \
  --subject-id subject_demo \
  --source-image-id subject_demo_concept \
  --image-path /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/example_images/example_000.png \
  --asset-id asset_subject_demo \
  --dry-run \
  --stages submit
```

Subject-asset workflow dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "requested_stages": ["submit"],
  "executed_stages": ["submit"],
  "skipped_stages": {
    "check_status": "not_requested",
    "save_completed": "not_requested"
  },
  "phase": "SUBJECT_ASSET_GENERATION",
  "artifact_ids": ["subject_demo_concept"],
  "subject_asset_count": 0,
  "tool_call_count": 1,
  "submit": {
    "ok": true,
    "tool_call_status": "succeeded",
    "outputs": {
      "submitted": false,
      "payload_fields": [
        "face_count",
        "guidance_scale",
        "image",
        "num_chunks",
        "num_inference_steps",
        "octree_resolution",
        "randomize_seed",
        "remove_background",
        "seed",
        "texture"
      ]
    }
  }
}
```

Subject-asset workflow audit:

```text
The dry-run registered the existing input image as SUBJECT_CONCEPT_IMAGE.
The dry-run recorded one build_subject_asset tool call.
No Hunyuan3D submit/status/save service call was made by this dry-run.
The summary exposes the image path and payload field names, not image base64.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner subject-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_subject_asset_qa_existing \
  --subject-id subject_existing_001 \
  --source-image-id source_existing_001 \
  --asset-id asset_existing_001 \
  --output-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --stages quality_check
```

Existing-GLB subject asset QA summary:

```json
{
  "ok": true,
  "phase": "SUBJECT_ASSET_QA",
  "requested_stages": ["quality_check"],
  "executed_stages": ["quality_check"],
  "artifact_ids": ["asset_existing_001"],
  "subject_asset_count": 1,
  "tool_call_count": 0,
  "quality_check": {
    "ok": true,
    "status": "pass",
    "score": 1.0,
    "issues": [],
    "suggested_action": "accept",
    "checks": {
      "glb_magic": "glTF",
      "glb_version": 2,
      "size_bytes": 720764,
      "declared_length": 720764
    }
  }
}
```

Subject asset QA audit:

```text
The existing Hunyuan3D GLB was registered as SUBJECT_3D_ASSET in ArtifactStore.
The workflow entered SUBJECT_ASSET_QA before running the quality check.
The deterministic QG-004 checks passed for GLB magic, version, size, and declared length.
No Blender preview render was requested in this QA run; preview-render QA remains available through --qa-render-preview.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner subject-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_subject_asset_repair_accept \
  --subject-id subject_repair_accept \
  --source-image-id source_repair_accept \
  --asset-id asset_repair_accept \
  --output-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --stages quality_check,repair_decision
```

Subject asset repair accept summary:

```json
{
  "ok": true,
  "executed_stages": ["quality_check", "repair_decision"],
  "quality_status": "pass",
  "repair_action": "accept",
  "user_visible": false,
  "next_stage": "BLENDER_ASSEMBLY_PLANNING",
  "checkpoint_reasons": [
    "subject_asset_quality_checked",
    "subject_asset_repair_decision_planned"
  ]
}
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner subject-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_subject_asset_repair_retry \
  --subject-id subject_repair_retry \
  --source-image-id source_repair_retry \
  --asset-id asset_repair_retry \
  --output-glb /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_subject_asset_repair_bad_input/bad.glb \
  --stages quality_check,repair_decision
```

Subject asset repair retry summary:

```json
{
  "ok": false,
  "executed_stages": ["quality_check", "repair_decision"],
  "quality_status": "fail",
  "issues": ["invalid_glb_magic"],
  "repair_action": "retry_hunyuan3d",
  "user_visible": false,
  "next_stage": "SUBJECT_ASSET_GENERATION",
  "checkpoint_reasons": [
    "quality_check_failed",
    "subject_asset_repair_decision_planned"
  ]
}
```

Subject asset repair-decision audit:

```text
The accept path keeps a passed existing GLB internal to the workflow and routes it to Blender assembly planning.
The retry path records a one-shot Hunyuan3D retry plan for a deterministic GLB-header failure without submitting a new generation job.
Both runs wrote state, summary, tool logs, and stage/final checkpoints; the repair decision is stored in subject asset metadata for later routing.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner subject-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_subject_asset_repair_execute_accept \
  --subject-id subject_repair_execute_accept \
  --source-image-id source_repair_execute_accept \
  --asset-id asset_repair_execute_accept \
  --output-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --stages quality_check,repair_decision,repair_execute
```

Subject asset repair execute accept summary:

```json
{
  "ok": true,
  "executed_stages": ["quality_check", "repair_decision", "repair_execute"],
  "quality_status": "pass",
  "repair_action": "accept",
  "repair_execute_status": "accepted",
  "tool_call_count": 0,
  "checkpoint_reasons": [
    "subject_asset_quality_checked",
    "subject_asset_repair_decision_planned",
    "subject_asset_repair_execution_handled"
  ]
}
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner subject-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_subject_asset_repair_execute_dryrun \
  --subject-id subject_repair_execute \
  --source-image-id source_repair_execute \
  --image-path /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/example_images/example_000.png \
  --asset-id asset_repair_execute \
  --output-glb /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_subject_asset_repair_bad_input/bad.glb \
  --dry-run \
  --stages quality_check,repair_decision,repair_execute
```

Subject asset repair execute dry-run retry summary:

```json
{
  "workflow_exit_code": 1,
  "workflow_ok": false,
  "quality_status": "fail",
  "quality_issues": ["invalid_glb_magic"],
  "repair_action": "retry_hunyuan3d",
  "repair_execute_status": "planned",
  "repair_execute_ok": true,
  "submitted": false,
  "tool_call_count": 1,
  "execution_phase": "SUBJECT_ASSET_GENERATION"
}
```

Subject asset repair-execute audit:

```text
The accept path completed with no Hunyuan3D tool call.
The retry dry-run path reused Hunyuan3DDomainToolDispatcher to build the submit_async payload shape and recorded submitted=false.
The dry-run retry workflow process exited 1 because the requested quality_check stage intentionally failed; the repair_execute stage itself was ok=true and checkpointed as handled.
Unconfirmed non-dry-run retry is covered by tests and is blocked before any service submit call.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner subject-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_frontend_status_pending_action \
  --subject-id subject_frontend_status \
  --source-image-id source_frontend_status \
  --asset-id asset_frontend_status \
  --output-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --qa-user-requested-review \
  --stages quality_check,repair_decision,repair_execute
```

Frontend status pending-action summary:

```json
{
  "status": "needs_user_action",
  "phase": "SUBJECT_ASSET_QA",
  "current_stage": "repair_execute",
  "current_node": "workflow_runner.subject_asset.repair_execute",
  "progress_label": "Waiting for ask_user_clarification",
  "pending_action": {
    "action_type": "ask_user_clarification",
    "asset_id": "asset_frontend_status",
    "payload_kind": "subject_asset_repair",
    "subject_id": "subject_frontend_status",
    "source_image_id": "source_frontend_status",
    "user_visible": true
  },
  "stage_progress": [
    "quality_check:completed",
    "repair_decision:completed",
    "repair_execute:completed"
  ]
}
```

Frontend status audit:

```text
The workflow wrote frontend_status.json beside state.json, summary.json, and tool_call_log.json.
The status snapshot is derived from AgentProjectState plus stage checkpoints; it is not a second state store.
The pending action came from the existing PendingAction model created by repair_execute; no UI queue or service was added.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner review-patch \
  --state-json /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_frontend_status_pending_action/state.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_review_patch_from_pending_action \
  --user-feedback "请重画这个主体概念图，让轮廓更接近参考图，再重新生成 3D。" \
  --source-turn-id turn_review_patch_smoke \
  --patch-id patch_review_patch_smoke
```

ReviewPatch workflow summary:

```json
{
  "ok": true,
  "phase": "CONCEPT_REVIEW",
  "pending_action_cleared": true,
  "review_patch_count": 1,
  "patch_id": "patch_review_patch_smoke",
  "patch_type": "redo_subject",
  "target_type": "subject",
  "target_id": "subject_frontend_status",
  "affected_artifact_ids": [
    "asset_frontend_status",
    "source_frontend_status"
  ],
  "checkpoint_reason": "review_patch_created",
  "frontend_status": {
    "status": "completed",
    "current_stage": "review_patch",
    "review_patch_ids": ["patch_review_patch_smoke"],
    "pending_action": null
  }
}
```

ReviewPatch workflow audit:

```text
The workflow consumed the previous pending-action state and wrote a structured ReviewPatch into state.review_patches.
The original PendingAction was cleared, the state phase became CONCEPT_REVIEW, and frontend_status.json reported the new review_patch_id.
No LLM, image-generation provider, Hunyuan3D retry, or UI queue was invoked.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner concept-regeneration \
  --state-json /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_review_patch_from_pending_action/state.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_concept_regeneration_dryrun \
  --patch-id patch_review_patch_smoke \
  --dry-run
```

Concept-regeneration dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "phase": "CONCEPT_GENERATION",
  "status": "planned",
  "patch_id": "patch_review_patch_smoke",
  "target_subject_id": "subject_frontend_status",
  "invalidated_asset_ids": ["asset_frontend_status"],
  "generated_image_artifact_id": null,
  "checkpoint_reason": "review_patch_concept_regeneration_handled"
}
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner concept-regeneration \
  --state-json /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_review_patch_from_pending_action/state.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_concept_regeneration_apply \
  --patch-id patch_review_patch_smoke \
  --generated-image-path /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/example_images/example_000.png \
  --generated-image-artifact-id source_frontend_status_regen_001 \
  --no-dry-run
```

Concept-regeneration apply summary:

```json
{
  "ok": true,
  "dry_run": false,
  "phase": "SUBJECT_ASSET_GENERATION",
  "status": "applied",
  "patch_id": "patch_review_patch_smoke",
  "target_subject_id": "subject_frontend_status",
  "generated_image_artifact_id": "source_frontend_status_regen_001",
  "generated_image_uri": "/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_concept_regeneration_apply/artifacts/subject_concept_image/source_frontend_status_regen_001.png",
  "marked_patch_applied": true,
  "checkpoint_reason": "review_patch_concept_regeneration_handled",
  "frontend_status": {
    "status": "completed",
    "current_stage": "apply_review_patch",
    "review_patch_ids": ["patch_review_patch_smoke"]
  }
}
```

Concept-regeneration audit:

```text
The dry-run path planned the existing regenerate_concept_images boundary and kept the patch pending.
The apply path registered an explicit local image as a SUBJECT_CONCEPT_IMAGE artifact, moved phase to SUBJECT_ASSET_GENERATION, and marked the ReviewPatch applied.
No image-generation API, LLM provider, Hunyuan3D retry, or new feedback queue was invoked.
```

## First Real Local Demo - 2026-06-28

Detailed report:

```text
/home/team/zouzhiyuan/image23D_Agent/docs/v1_real_demo_20260628_report.md
```

Run root:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/
```

Summary:

```json
{
  "concept_seed": {
    "ok": true,
    "artifact_id": "demo_robot_concept_001",
    "phase": "SUBJECT_ASSET_GENERATION"
  },
  "hunyuan3d_live_subject": {
    "ok": true,
    "job_id": "f72e91e2-e600-40a2-8f37-4f44f817f87f",
    "service_status": "completed_shape_only",
    "asset_id": "demo_robot_asset_001",
    "qa_status": "pass",
    "qa_score": 1.0,
    "glb": "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/subject_asset_live_save/subject_assets/demo_robot_asset_001.glb"
  },
  "blender_viewer": {
    "ok": true,
    "blend": "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/compose/composed_scene.blend",
    "preview": "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/compose/composed_preview.png",
    "viewer_glb": "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/viewer_export/viewer_scene.glb",
    "viewer_url": "http://127.0.0.1:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/viewer_export/viewer_scene.glb"
  },
  "delivery_package": {
    "ok": true,
    "zip": "/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/delivery_package/package/delivery_20260628_p0_real_demo.zip"
  }
}
```

Known demo limits:

```text
The chat/session image-generation call produced a visible image but did not expose a local file path, so the reproducible run used an existing local sample image as concept input.
The Hunyuan3D run used --no-texture and returned completed_shape_only.
The scene GLB came from an existing HY-World output directory; fresh HY-World live generation remains a later run.
The Blender preview is a pipeline proof, not a polished final composition.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.smoke \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --input-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_render_smoke \
  --timeout 180
```

Result summary:

```json
{
  "artifact_ids": [
    "smoke_input_glb",
    "smoke_preview_blend",
    "smoke_preview_png"
  ],
  "dry_run": false,
  "ok": true,
  "preview_blend_exists": true,
  "preview_png_exists": true,
  "tool_call_status": "succeeded"
}
```

Smoke output artifacts:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_render_smoke/preview.png
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_render_smoke/preview.blend
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_render_smoke/state.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_render_smoke/tool_call_log.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_render_smoke/artifacts/artifacts.jsonl
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.smoke compose \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_compose_smoke \
  --timeout 300
```

Result summary:

```json
{
  "artifact_ids": [
    "smoke_composed_blend",
    "smoke_composed_preview_png",
    "smoke_scene_glb",
    "smoke_subject_glb"
  ],
  "dry_run": false,
  "ok": true,
  "output_blend_exists": true,
  "preview_png_exists": true,
  "tool_call_status": "succeeded"
}
```

Compose smoke output artifacts:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_compose_smoke/composed_preview.png
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_compose_smoke/composed_scene.blend
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_compose_smoke/state.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_compose_smoke/tool_call_log.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_compose_smoke/artifacts/artifacts.jsonl
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.smoke export-viewer \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --input-blend /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_compose_smoke/composed_scene.blend \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_export_smoke \
  --timeout 180
```

Result summary:

```json
{
  "artifact_ids": [
    "smoke_scene_state_json",
    "smoke_source_blend",
    "smoke_viewer_scene_glb"
  ],
  "dry_run": false,
  "ok": true,
  "scene_state_json_exists": true,
  "tool_call_status": "succeeded",
  "viewer_glb_exists": true
}
```

Viewer export smoke output artifacts:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_export_smoke/viewer_scene.glb
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_export_smoke/scene_state.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_export_smoke/state.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_export_smoke/tool_call_log.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_export_smoke/artifacts/artifacts.jsonl
```

Viewer export audit:

```text
scene_state.json has viewer_scene_artifact_id=smoke_viewer_scene_glb.
scene_state.json has viewer_state_artifact_id=smoke_scene_state_json.
scene_state.json records 7 objects and Preview_Camera.
GLB viewer HEAD /asset for viewer_scene.glb returned 200 model/gltf-binary.
GLB viewer HEAD /viewer for viewer_scene.glb returned 200 text/html.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.smoke export-viewer \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --input-blend /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_compose_smoke/composed_scene.blend \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_schema_export_smoke \
  --timeout 180
```

Result summary:

```json
{
  "artifact_ids": [
    "smoke_scene_state_json",
    "smoke_source_blend",
    "smoke_viewer_scene_glb"
  ],
  "dry_run": false,
  "ok": true,
  "scene_state_json_exists": true,
  "tool_call_status": "succeeded",
  "viewer_glb_exists": true,
  "viewer_scene_object_count": 7
}
```

Schema export audit:

```text
state.json now contains AgentProjectState.viewer_scene.
viewer_scene_id=viewer_scene.
viewer_scene_artifact_id=smoke_viewer_scene_glb.
viewer_state_artifact_id=smoke_scene_state_json.
viewer_scene.objects length=7.
viewer_scene.camera preserves the existing exporter camera snapshot keys.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.smoke e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke \
  --compose-timeout 300 \
  --export-timeout 180 \
  --viewer-timeout 10
```

Result summary:

```json
{
  "ok": true,
  "compose": {
    "ok": true,
    "tool_call_status": "succeeded"
  },
  "export_viewer": {
    "ok": true,
    "tool_call_status": "succeeded"
  },
  "viewer_check": {
    "ok": true,
    "asset": {
      "status": 200,
      "content_type": "model/gltf-binary",
      "content_length": 39159564
    },
    "viewer": {
      "status": 200,
      "content_type": "text/html; charset=utf-8"
    }
  }
}
```

Local E2E smoke artifacts:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/summary.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/compose/composed_preview.png
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/compose/composed_scene.blend
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/compose/state.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/compose/tool_call_log.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/viewer_export/viewer_scene.glb
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/viewer_export/scene_state.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/viewer_export/state.json
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_e2e_smoke/viewer_export/tool_call_log.json
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_workflow_runner_e2e \
  --compose-timeout 300 \
  --export-timeout 180 \
  --viewer-timeout 10
```

Workflow runner result summary:

```json
{
  "ok": true,
  "single_project_state": true,
  "phase": "BLENDER_PREVIEW",
  "tool_call_count": 2,
  "artifact_ids": [
    "workflow_composed_blend",
    "workflow_composed_preview_png",
    "workflow_scene_glb",
    "workflow_scene_state_json",
    "workflow_subject_glb",
    "workflow_viewer_scene_glb"
  ],
  "compose": {
    "ok": true,
    "tool_call_status": "succeeded",
    "output_blend_exists": true,
    "preview_png_exists": true
  },
  "export_viewer": {
    "ok": true,
    "tool_call_status": "succeeded",
    "viewer_glb_exists": true,
    "scene_state_json_exists": true,
    "viewer_scene_object_count": 7
  },
  "viewer_check": {
    "ok": true,
    "asset": {
      "status": 200,
      "content_type": "model/gltf-binary",
      "content_length": 39159564
    },
    "viewer": {
      "status": 200,
      "content_type": "text/html; charset=utf-8"
    }
  }
}
```

Workflow runner audit:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_workflow_runner_e2e/state.json records one AgentProjectState for the whole local E2E path.
The state records 2 tool calls: import_scene_asset and export_viewer_scene.
The state records blender_scene_id=composed_scene.
The state records viewer_scene_id=viewer_scene with 7 objects.
The CLI dry-run path was also checked at /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_workflow_runner_dryrun and produced no runpy warning after removing package-level eager import.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_workflow_runner_compose_only_dryrun \
  --dry-run \
  --stages compose
```

Stage-selection dry-run summary:

```json
{
  "ok": true,
  "dry_run": true,
  "requested_stages": ["compose"],
  "executed_stages": ["compose"],
  "skipped_stages": {
    "export_viewer": "not_requested",
    "viewer_check": "not_requested"
  },
  "tool_call_count": 1,
  "single_project_state": true
}
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_dispatcher_workflow_e2e \
  --compose-timeout 300 \
  --export-timeout 180 \
  --viewer-timeout 10
```

Dispatcher workflow result summary:

```json
{
  "ok": true,
  "requested_stages": ["compose", "export_viewer", "viewer_check"],
  "executed_stages": ["compose", "export_viewer", "viewer_check"],
  "skipped_stages": {},
  "single_project_state": true,
  "phase": "BLENDER_PREVIEW",
  "tool_call_count": 2,
  "export_viewer": {
    "ok": true,
    "viewer_scene_object_count": 7
  },
  "viewer_check": {
    "ok": true,
    "asset": {
      "status": 200,
      "content_type": "model/gltf-binary",
      "content_length": 39159564
    },
    "viewer": {
      "status": 200,
      "content_type": "text/html; charset=utf-8"
    }
  }
}
```

Dispatcher workflow audit:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_dispatcher_workflow_e2e/state.json records phase=BLENDER_PREVIEW.
The state records 2 tool calls.
import_scene_asset raw argv points to tools/compose_blender_scene.py.
export_viewer_scene raw argv points to tools/export_viewer_scene.py.
The state records viewer_scene_id=viewer_scene with 7 objects.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/Hunyuan3D-2.1/assets/1.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_adapter_workflow_e2e \
  --compose-timeout 300 \
  --export-timeout 180 \
  --viewer-timeout 10
```

Viewer adapter workflow result summary:

```json
{
  "ok": true,
  "executed_stages": ["compose", "export_viewer", "viewer_check"],
  "phase": "BLENDER_PREVIEW",
  "tool_call_count": 2,
  "export_viewer": {
    "ok": true,
    "viewer_scene_object_count": 7
  },
  "viewer_check": {
    "ok": true,
    "runtime": {
      "ok": true,
      "index": {
        "status": 200,
        "content_type": "text/html; charset=utf-8"
      },
      "api_list": {
        "status": 200,
        "content_type": "application/json; charset=utf-8"
      }
    },
    "asset": {
      "status": 200,
      "content_type": "model/gltf-binary",
      "content_length": 39159564
    },
    "viewer": {
      "status": 200,
      "content_type": "text/html; charset=utf-8"
    }
  }
}
```

Viewer artifact metadata audit:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_adapter_workflow_e2e/state.json records workflow_viewer_scene_glb.metadata.viewer.
metadata.viewer.asset_url points to /asset?path=/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_adapter_workflow_e2e/viewer_export/viewer_scene.glb.
metadata.viewer.viewer_url points to /viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_adapter_workflow_e2e/viewer_export/viewer_scene.glb.
metadata.viewer.runtime_status.ok=true.
metadata.viewer.model_check.ok=true.
metadata.viewer.model_check.asset.content_type=model/gltf-binary.
```

```bash
bash scripts/status_visualization_stack.sh
```

Result summary:

```text
GLB viewer running on http://10.2.16.106:8092/.
Codex MCP config includes enabled blender_lab server.
Blender 5.1.2 Lab MCP bridge running; socket open on 127.0.0.1:9876.
Docker is not usable by the current user.
```

Observed runtime note:

```text
GLB viewer recent log includes one BrokenPipeError from a client disconnect while sending an asset.
Subsequent viewer and asset HEAD/GET checks returned 200, so this is recorded as a runtime log warning rather than a current availability failure.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner scene-asset \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_scene_asset_register_existing \
  --scene-asset-id scene_asset_existing_001 \
  --worldmirror-output-dir /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326 \
  --source-scene-concept-image-ids scene_concept_existing_001 \
  --stages inspect_output,register_existing_output
```

Scene-asset workflow existing-output summary:

```json
{
  "ok": true,
  "phase": "SCENE_ASSET_GENERATION",
  "executed_stages": ["inspect_output", "register_existing_output"],
  "artifact_ids": [
    "scene_asset_existing_001_camera_params_json",
    "scene_asset_existing_001_gaussian_ply",
    "scene_asset_existing_001_predictions_npz",
    "scene_asset_existing_001_scene_glb"
  ],
  "scene_asset": {
    "scene_asset_id": "scene_asset_existing_001",
    "service": "hy_world",
    "raw_output_type": "mesh",
    "blender_import_mode": "mesh_import",
    "status": "adapted",
    "adapted_artifact_ids": ["scene_asset_existing_001_scene_glb"]
  }
}
```

Scene-asset workflow audit:

```text
The runner inspected an existing HY-World output directory and registered metadata for the primary scene GLB, camera params, gaussian PLY, and predictions NPZ.
No live WorldMirror generation was invoked.
The selected primary Blender path is direct mesh import through scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb.
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner delivery-package \
  --state-json /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_viewer_adapter_workflow_e2e/state.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_delivery_package \
  --package-id delivery_v1_landing_viewer_adapter
```

Delivery package workflow summary:

```json
{
  "ok": true,
  "phase": "DELIVERY",
  "package": {
    "ok": true,
    "package_artifact_id": "delivery_v1_landing_viewer_adapter",
    "package_zip": "/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_delivery_package/package/delivery_v1_landing_viewer_adapter.zip",
    "metadata_json": "/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_delivery_package/package/delivery_v1_landing_viewer_adapter/metadata.json",
    "version_manifest_json": "/home/team/zouzhiyuan/image23D_Agent/outputs/v1_landing_delivery_package/package/delivery_v1_landing_viewer_adapter/version_manifest.json",
    "issues": []
  }
}
```

Delivery package audit:

```text
The package contains the authoritative .blend, preview PNG, viewer_scene.glb, scene_state.json, subject GLB, scene GLB, metadata.json, and version_manifest.json.
The package was created from existing workflow artifacts; no Blender export, viewer service, Hunyuan3D generation, or WorldMirror generation was invoked.
The zip was registered as an EXPORT_PACKAGE artifact in the delivery workflow state.
```

## 2026-06-28 Agent Control Contract Slice

Added the state-driven agent control layer required by the V1 plan:

- `agent_runtime/reference_intake.py` validates explicit reference-image
  bindings before SceneSpec or high-cost generation.
- `agent_runtime/agent_prompts.py` defines JSON-only prompt contracts for key
  LLM/MLLM nodes and keeps raw MCP/tool execution outside LLM prompts.
- `agent_runtime/controller.py` maps `AgentProjectState` to the next safe node,
  domain tool, or user gate.
- `docs/agent_prompt_contract.md`, `docs/reference_image_schema.md`, and
  `docs/controller_design.md` document the contract.
- `AGENTS.md` now records the combined highest execution plan and prompt/schema
  controller priority.

Focused verification:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q \
  tests/test_reference_intake.py tests/test_agent_prompts.py tests/test_controller.py \
  -p no:cacheprovider
```

Result:

```text
13 passed in 0.32s
```

Compile verification:

```bash
python -m compileall -q agent_runtime tests
```

Result: passed.

Full repository verification after the slice:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests -p no:cacheprovider
python -m compileall -q agent_runtime tools tests
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.infra_inventory \
  --root /home/team/zouzhiyuan/image23D_Agent --json
rg -n "(^|[^A-Za-z0-9])sk-[A-Za-z0-9]{20,}" \
  AGENTS.md docs .gitignore agent_runtime tests scripts tools web
```

Result:

```text
213 passed in 1.46s
compileall passed
infra inventory ok=true; all then-required items present
secret scan clean; rg returned no matches
```

## 2026-06-28 Live Qwen LLM Node Smoke

Added `agent_runtime/llm_nodes.py` as the controlled execution boundary for V1
LLM nodes:

- builds node prompts from `agent_runtime.agent_prompts`;
- calls the existing OpenAI-compatible provider adapter;
- requests JSON output;
- parses provider text into a JSON object;
- validates it with the node's Pydantic output model;
- records only redacted request summaries and parsed outputs.

Focused verification:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q \
  tests/test_llm_nodes.py tests/test_agent_prompts.py -p no:cacheprovider
python -m compileall -q agent_runtime tests
```

Result:

```text
7 passed in 0.42s
compileall passed
```

Live Qwen smoke command boundary:

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
# Loads .env.agent_llm.local, runs ConceptPromptPlanner through run_llm_node,
# redacts the prompt contract, and writes summary.json under outputs/.
PY
```

Live result:

```text
ok=true
provider=qwen
model=qwen3.7-max
endpoint=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
response_format_json=true
key_suffix=eeef
summary=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_llm_node_qwen_smoke/summary.json
```

The parsed output passed `ConceptPromptPlannerOutput` validation and produced
`final_preview_prompt`, one subject prompt, one scene prompt, and a negative
prompt. A targeted scan of the saved summary found no plaintext API key.

## 2026-06-28 Codex-Self Generated Concept To Delivery Demo

Added the missing controlled state bridge from an LLM prompt-pack output to the
existing concept workflow:

- `agent_runtime/concept_planning.py` applies a validated
  `ConceptPromptPlannerOutput` into `AgentProjectState.concept_bundle`.
- It uses `state_views.apply_state_updates(...)`, clears stale concept
  approval/QA, and does not let the LLM mutate state directly.
- `tests/test_concept_planning.py` covers direct model input, LLM-node result
  input, stale approval reset, and invalid-result blocking.

Added `codex-self-mcp` image-log ingestion:

- `CodexSelfMCPAdapter.run_call_plan(...)` now returns a structured timeout
  result instead of surfacing a raw `TimeoutExpired` traceback.
- `extract_last_image_from_codex_mcp_log(...)` extracts the last
  `image_generation` base64 payload from a codex MCP JSONL log into a project
  image file.

Focused verification before the live chain:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q \
  tests/test_codex_self_mcp.py tests/test_llm_nodes.py tests/test_concept_planning.py \
  -p no:cacheprovider
python -m compileall -q agent_runtime tests
```

Result:

```text
15 passed in 0.44s
compileall passed
```

Live concept image path:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/generated_robot_concept.png
```

The image was generated through `codex-self-mcp`, extracted from
`codex_self_mcp_call.jsonl`, then registered through the existing
`concept-seed` workflow as:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/concept_seed/artifacts/subject_concept_image/codex_self_robot_concept_001.png
```

Hunyuan3D live subject asset:

```text
job_id=9c8c6a2a-b637-4180-a27b-2ebfcde9e974
status=completed_shape_only
qa_ok=true
qa_score=1.0
glb=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/subject_asset_status_save/subject_assets/codex_self_robot_asset_001.glb
```

Blender/viewer result:

```text
local-e2e ok=true
executed_stages=compose,export_viewer,viewer_check
viewer_model_ok=true
viewer_runtime_ok=true
viewer_scene_object_count=7
viewer_scene=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/viewer_export/viewer_scene.glb
preview=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/compose/composed_preview.png
```

Delivery package:

```text
ok=true
issues=[]
zip=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/delivery_package/package/codex_self_robot_demo_20260628.zip
```

Full repository verification after this slice:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests -p no:cacheprovider
python -m compileall -q agent_runtime tools tests
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.infra_inventory \
  --root /home/team/zouzhiyuan/image23D_Agent --json
rg -n "(^|[^A-Za-z0-9])sk-[A-Za-z0-9]{20,}" \
  AGENTS.md docs .gitignore agent_runtime tests scripts tools web
```

Result:

```text
223 passed in 1.50s
compileall passed
infra inventory ok=true; all then-required items present
secret scan clean; rg returned no matches
```

Known quality boundary:

```text
The concept image, subject GLB, Blender compose, viewer export, and package are
real artifacts. The assembly placement is still a technical smoke path: the
robot is present but small, and final scale/camera/layout intelligence is not
yet driven by a mature SceneSpec or Blender planner.
```

## 2026-06-28 Agent Runtime Planning Slice

Shifted the main implementation focus from manual demo execution to runtime
contracts:

- `agent_runtime/runtime_profiles.py`
  - Defines known local service URLs and Hunyuan3D generation profiles.
  - Records the current high-quality default as textured `1M` faces with
    octree `768`, `50` steps, `200000` chunks, and texture enabled.
  - Adds explicit smoke/draft profiles so fast tests do not masquerade as
    final quality.
- `agent_runtime/runtime_jobs.py`
  - Converts `ControllerPlan` actions into `RuntimeJobSpec` records.
  - Marks long-running generation jobs for sub-agent/background execution.
  - Exposes existing GLB viewer and Blender Web surfaces through
    `RuntimeWebSurface`.
- `agent_runtime/runtime_runs.py`
  - Discovers existing `outputs/runs/<run_id>/` directories.
  - Reads `state.json`, `summary.json`, `frontend_status.json`,
    `delivery_handoff.json`, and `scene_state.json`.
  - Rewrites local viewer/Blender Web URLs to public browser-facing bases.
- `workflow_runner subject-asset`
  - Adds `--hunyuan-profile`, `--octree-resolution`, `--num-chunks`, and
    `--remove-background/--no-remove-background`.
  - Keeps explicit CLI values as overrides over profile defaults.

Focused verification:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q \
  tests/test_runtime_profiles.py tests/test_runtime_jobs.py tests/test_runtime_runs.py \
  tests/test_service_adapters.py tests/test_domain_dispatcher.py tests/test_workflow_runner.py \
  -p no:cacheprovider
python -m compileall -q agent_runtime tests
```

Result:

```text
113 passed in 0.92s
compileall passed
```

## 2026-06-28 Runtime Console MVP Slice

Implemented the first usable browser runtime console as a thin surface over
existing run artifacts:

- `agent_runtime/runtime_console.py`
  - creates intake-only console runs under `outputs/runs/<run_id>/`;
  - writes `state.json`, `summary.json`, and `frontend_status.json`;
  - appends chat to `runtime_console/chat.jsonl`;
  - mirrors user chat turns into `AgentProjectState.user_turns`;
  - saves uploaded files under `runtime_console/uploads/`;
  - registers uploaded images as `INPUT_IMAGE` artifacts and
    `AgentProjectState.input_images`.
- `tools/runtime_console_server.py`
  - serves a small HTTP API and the static console UI;
  - lists existing runs through `runtime_runs`;
  - returns run bundles, chat logs, upload logs, and public viewer URLs;
  - accepts JSON chat and multipart/JSON image uploads.
- `web/runtime_console/`
  - left panel: run list, new run, chat log, image upload, message send;
  - center panel: embedded existing GLB viewer when `viewer_scene.glb` exists;
  - right panel: status, object list, and delivery links derived from run
    files.
- `scripts/start_runtime_console.sh`,
  `scripts/status_runtime_console.sh`, `scripts/stop_runtime_console.sh`
  - manage the console on default port `8093`, matching the existing viewer
    script style.
- `agent_runtime/infra_inventory.py`
  - now treats runtime console scripts, server, and static UI as required
    project infrastructure.

This MVP deliberately reuses `tools/glb_viewer_server.py` for GLB preview and
Blender Web for `.blend` access. It is not a new viewer, not a second workflow
state store, and not yet an autonomous agent dispatcher.

Current known gaps:

- chat/upload can build a runtime plan and the operator can trigger one safe
  runtime step, but there is not yet a continuous autonomous dispatcher loop;
- uploads are stored and registered, but reference-purpose binding still needs
  the existing intake/validator path;
- approval/retry controls are not yet first-class buttons;
- object click/highlight is not integrated with the embedded GLB viewer.

Full repository verification after this slice:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests -p no:cacheprovider
python -m compileall -q agent_runtime tools tests
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.infra_inventory \
  --root /home/team/zouzhiyuan/image23D_Agent --json
rg -n "(^|[^A-Za-z0-9])sk-[A-Za-z0-9]{20,}" \
  AGENTS.md docs .gitignore agent_runtime tests scripts tools web \
  third_party/README.md assets/mmd_motions/README.md
```

Result:

```text
252 passed in 1.66s
compileall passed
infra inventory ok=true, required 20/20 present
secret scan clean; rg returned no matches
```

Runtime console service smoke:

```bash
./scripts/start_glb_viewer.sh
./scripts/start_runtime_console.sh
curl -sS -X POST http://127.0.0.1:8093/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"runtime_console_smoke_20260628_152758"}'
curl -sS -X POST \
  http://127.0.0.1:8093/api/runs/runtime_console_smoke_20260628_152758/chat \
  -H 'Content-Type: application/json' \
  -d '{"role":"user","text":"请根据这张参考图生成一个适合放进 Blender 场景的主体模型。"}'
curl -sS -X POST \
  http://127.0.0.1:8093/api/runs/runtime_console_smoke_20260628_152758/upload \
  -F file=@Hunyuan3D-2.1/assets/example_images/example_000.png
```

Result:

```text
Runtime console started on http://10.2.16.106:8093/
GLB viewer already running on http://10.2.16.106:8092/
smoke run phase=INTAKE, user_turns=1, input_images=1
expected missing files for intake-only smoke: delivery_handoff.json, scene_state.json
node --check web/runtime_console/app.js passed
python -m html.parser web/runtime_console/index.html passed
browser screenshot check not run: Playwright/Chromium is not installed locally
```

## 2026-06-28 Runtime Console Linkage Repair

User screenshot showed an empty preview because the console selected the latest
intake-only smoke run and the run reader treated parent run directories as the
only runtime bundle directory. The real viewer artifacts were under visual child
stages such as:

```text
outputs/runs/20260628_p0_real_demo/blender_viewer/viewer_export/viewer_scene.glb
outputs/runs/20260628_p0_real_demo/blender_viewer/viewer_export/scene_state.json
outputs/runs/20260628_p0_real_demo/blender_viewer/delivery_handoff.json
outputs/runs/20260628_codex_self_robot_concept/blender_viewer/viewer_export/viewer_scene.glb
outputs/runs/20260628_codex_self_robot_concept/blender_viewer/viewer_export/scene_state.json
outputs/runs/20260628_codex_self_robot_concept/blender_viewer/delivery_handoff.json
```

Implemented:

- `runtime_runs` discovers parent runs plus runtime child stages.
- Visual runs sort ahead of intake-only smoke runs.
- `RuntimeRunBundle` reports `run_key`, `display_name`, `relative_path`,
  `effective_run_dir`, and `file_manifest`.
- Passing a parent run resolves `effective_run_dir` to the best visual child
  stage when available.
- `tools/runtime_console_server.py` resolves encoded `run_key` routes and
  exposes safe run-local JSON/file reads through
  `/api/runs/<run_key>/file?path=...`.
- Frontend API calls use `run_key`, default to the first visual run, and render
  a Files panel with existing/missing JSON/model paths.
- UI skin changed to a light, simple creator-console layout in
  `web/runtime_console/polish.css`, matching the user's reference direction.

Verification:

```text
GET /api/runs first item:
20260628_codex_self_robot_concept, has_viewer_scene=true

GET /api/runs/<first_run_key>:
effective_run_dir=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer
viewer_scene_url=http://10.2.16.106:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/viewer_export/viewer_scene.glb
missing_required=[]

GET /api/runs/<stage_run_key>/file?path=state.json:
project_id=v1_local_e2e_workflow, phase=BLENDER_PREVIEW
```

## 2026-06-28 Runtime Console Layout And Plan Slice

Adjusted the console information architecture to match the user's simple
creator-tool reference:

- left column is run navigation only;
- center column contains 3D preview plus chat/upload composer;
- right column contains status, runtime plan/jobs, objects, files, and delivery
  links.

Added runtime planning from console state:

- `agent_runtime/runtime_dispatch.py` builds a controller plan and runtime job
  plan from the selected run's `state.json`;
- `POST /api/runs/<run_key>/plan` writes `runtime_plan.json`;
- `GET /api/runs/<run_key>/runtime-plan` reads the saved plan;
- `RuntimeRunBundle.runtime_plan` and `file_manifest` expose the saved plan to
  the frontend;
- chat/upload attempts to refresh the saved plan but does not block the user if
  a historical run has no `state.json`.

Verification:

```text
new run runtime_console_plan_smoke_20260628_155716
POST /chat succeeded
POST /plan produced ok=true, phase=INTAKE, jobs=3
first job: ReferenceBindingValidator, kind=llm_node
bundle.runtime_plan=true
file_manifest runtime_plan exists=true
```

## 2026-06-28 Runtime Execution Step Slice

Plan basis:

- uploaded `DOC-003_Agent_Workflow_Design_v0.2_zh.md` requires a
  workflow-first runtime with explicit checkpoints/gates, not an unbounded
  hidden ReAct loop;
- the V1 minimum order says state schema/artifact store and runtime inventory
  must come before Hunyuan3D, Blender, viewer sync, edit loop, and delivery;
- the current gap after `runtime_plan.json` was durable execution state for
  planned jobs.

Implementation:

- added `agent_runtime/runtime_execution.py`;
- added `POST /api/runs/<run_key>/step` and
  `GET /api/runs/<run_key>/runtime-execution`;
- added `runtime_execution.jsonl`, `runtime_execution_summary.json`, and
  per-step JSON outputs under `runtime_execution/`;
- exposed execution files through `RuntimeRunBundle.file_manifest`;
- added a small console `Step` button that triggers one dry-run-safe step.

Execution semantics:

- `user_gate` jobs record `waiting_user`;
- ordinary `main_runtime` LLM jobs dry-run through the existing
  `agent_runtime.llm_nodes` provider boundary and save prompt/context/result
  JSON;
- long-running, background-worker, and sub-agent jobs record `delegated` with
  command/profile hints;
- unsupported main-runtime jobs record `blocked`;
- no LLM candidate output is written into `state.json` in this slice.

Verification:

```text
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q \
  tests/test_runtime_execution.py tests/test_runtime_dispatch.py \
  tests/test_runtime_runs.py tests/test_runtime_console.py -p no:cacheprovider

16 passed in 0.48s
```

HTTP smoke after restarting `tools/runtime_console_server.py`:

```text
run_id=runtime_console_step_smoke_20260628_161516
POST /api/runs -> created_ok=true
POST /chat -> 201
POST /plan -> plan_ok=true, phase=INTAKE, job_count=3
POST /step -> step_ok=true, step_status=dry_run, step_node=ReferenceBindingValidator
GET /runtime-execution -> total_records=1
bundle file_manifest runtime_execution exists=true
bundle file_manifest runtime_execution_summary exists=true
```

## 2026-06-28 Runtime Semantic Audit Slice

Reason:

- Unit tests for runtime modules are useful but mostly validate our own module
  contracts.
- The uploaded DOC plan needs an evidence chain from real inputs to persisted
  state, plan, execution, and artifacts.

Implementation:

- added `agent_runtime/runtime_audit.py`;
- added `python -m agent_runtime.runtime_audit <run_dir> --json`;
- added `tests/test_runtime_audit.py` as a small regression guard;
- added `docs/v1_plan_gap_matrix.md` to track the uploaded DOC-003 minimum
  implementation sequence.

Audit semantics:

- parse `state.json`, `runtime_plan.json`, `runtime_execution.jsonl`, and
  `runtime_execution_summary.json`;
- verify chat JSONL user rows are mirrored into
  `AgentProjectState.user_turns`;
- verify runtime plan project/thread/phase matches `state.json`;
- verify runtime jobs match controller actions;
- verify execution records refer to jobs from `runtime_plan.json`;
- verify execution summary counts/latest/pending ids match execution log and
  plan;
- verify per-step output JSON exists under the run directory;
- verify LLM dry-run output contains prompt/context evidence but no parsed
  state candidate;
- verify `ReferenceBindingValidator` context uses the latest state user turn;
- verify uploaded unbound reference images produce a user gate instead of an
  invented binding.

Real run audits:

```text
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.runtime_audit \
  outputs/runs/runtime_console_step_smoke_20260628_161516 --json

ok=true, error_count=0, warning_count=0
checks include:
chat_user_turns_mirrored_to_state
plan_phase_matches_state
execution_summary_matches_log
reference_binding_context_uses_latest_user_turn
```

```text
runtime_console_usergate_audit_20260628_163614
POST /upload -> image_id=image_upload_9870ddf68380
POST /plan -> plan_ok=false, blocked=true, first_job_kind=user_gate
POST /step -> step_status=waiting_user

PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.runtime_audit \
  outputs/runs/runtime_console_usergate_audit_20260628_163614 --json

ok=true, error_count=0, warning_count=0
checks include:
user_gate_matches_unbound_images
execution_summary_matches_log
execution_summary_job_ids_match_plan
```

## 2026-06-28 Runtime State Apply Slice

Reason:

- `runtime_execution.jsonl` was durable evidence, but parsed LLM candidates
  still did not advance `state.json`.
- The next DOC-003 runtime step is a controlled state mutation/checkpoint
  boundary, not another self-contained unit test.

Implementation:

- added `agent_runtime/runtime_state_apply.py`;
- added `POST /api/runs/<run_key>/apply` and
  `GET /api/runs/<run_key>/runtime-apply`;
- added `runtime_apply.jsonl` and `runtime_apply_summary.json`;
- apply now writes `state.json`, `summary.json`, `frontend_status.json`,
  checkpoint snapshots under `checkpoints/`, and then rebuilds
  `runtime_plan.json`;
- `RuntimeRunBundle.file_manifest` now exposes apply logs/summaries;
- the console plan panel now has a small `Apply` button and displays the last
  apply record.

Apply semantics:

- applies only completed execution records with parsed JSON;
- skips dry-run outputs and records without parsed candidates;
- supports `ReferenceBindingValidator`, `SceneSpecCompiler`, and
  `ConceptPromptPlanner`;
- preserves DOC-004 ownership boundaries by using existing state apply helpers
  and node-specific adapters;
- successful `SceneSpecCompiler` apply updates `scene_spec`, advances phase to
  `SCENE_SPEC_READY` when there are no open questions, checkpoints the state,
  and rebuilds the next plan.

Real HTTP apply smoke:

```text
run_id=runtime_apply_scene_spec_audit_20260628_164709
fixture candidate=node SceneSpecCompiler, status=completed
POST /apply -> apply_ok=true, apply_status=applied
applied_fields=["scene_spec", "phase"]
state_phase=SCENE_SPEC_READY
scene_id=scene_001
checkpoint_id=ckpt_runtime_apply_scene_spec_audit_20260628_164709_runtime_console_20260628T084709Z_db8b14fde0
next_plan_phase=SCENE_SPEC_READY
next_job=ConceptPromptPlanner
bundle_apply_summary=true
```

Semantic audit:

```text
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.runtime_audit \
  outputs/runs/runtime_apply_scene_spec_audit_20260628_164709 --json

ok=true, error_count=0, warning_count=0
checks include:
runtime_apply_summary_matches_log
runtime_apply_checkpoints_exist
execution_output_matches_record
```

Targeted verification:

```text
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q \
  tests/test_runtime_state_apply.py tests/test_runtime_audit.py \
  tests/test_runtime_execution.py tests/test_runtime_runs.py \
  tests/test_runtime_console.py -p no:cacheprovider

19 passed in 0.42s
```

Sub-agent read-only audits during this slice confirmed:

```text
Hunyuan3D service launch: port 8091, texture-resolution 768, max-num-view 8, low_vram_mode.
Runtime request defaults: texture=true, octree_resolution=768, steps=50, chunks=200000, face_count=1000000.
GLB viewer: port 8092, handles .glb/.gltf only.
Blender Web Docker: ports 8300/8301 when running, intended for .blend access.
Blender Lab MCP: 127.0.0.1:9876 for control/edit, not a front-end display page.
```

## Reuse Audit

This slice intentionally did not replace existing infrastructure:

- Blender scene composition stays in `tools/compose_blender_scene.py`.
- GLB preview rendering stays in `tools/render_glb_preview.py`.
- Viewer GLB/state export now has one canonical helper: `tools/export_viewer_scene.py`.
- Web GLB viewing stays in `tools/glb_viewer_server.py` and `web/`.
- Runtime console browsing/chat/upload stays in
  `tools/runtime_console_server.py`, `web/runtime_console/`, and
  `agent_runtime.runtime_console`; it embeds the existing GLB viewer instead of
  implementing another 3D viewer or front-end state store.
- Service lifecycle stays in `scripts/start_a40_services.sh`, `scripts/status_a40_services.sh`, and related scripts.
- Blender MCP bridge lifecycle stays in `scripts/start_blender51_lab_mcp_bridge.sh` and `scripts/status_blender51_lab_mcp_bridge.sh`.
- `codex-self-mcp` is wrapped through `CodexSelfMCPAdapter` and `workflow_runner codex-self` as an optional sub-agent channel; it reuses the existing helper script and local Codex CLI instead of being treated as a normal LLM provider or a new MCP server implementation.
- Blender Lab MCP is wrapped through `BlenderMCPAdapter` for status/readback evidence, `BlenderLabSocketRawToolCaller` for explicit local socket raw calls, `sync_blender_scene_state_from_objects_summary(...)` for state synchronization, `build_safe_blender_mcp_operation_plan(...)` for constrained raw MCP call planning, `BlenderMCPDomainToolDispatcher` for deterministic raw-tool execution/logging, and `workflow_runner blender-edit` for dry-run/edit workflow output; raw MCP tools are still kept behind deterministic adapters and are not exposed directly to LLM nodes.
- `MCPClientManager` registers and calls existing MCP channels only; it does not implement a new MCP transport or expose raw tools to LLM nodes.
- DOC-006 tool exposure is now represented by `agent_runtime/domain_tools.py` instead of being reinterpreted separately in each future node.
- The live render smoke used `tools/render_glb_preview.py` through `agent_runtime.script_adapters` and `agent_runtime.tool_executor`; it did not add a second renderer.
- The live compose smoke used `tools/compose_blender_scene.py`; it did not add a second composition implementation.
- The live viewer export smoke added the missing V1 export helper and registered it in infrastructure inventory to avoid future parallel implementations.
- The local E2E smoke reuses the render/compose/export/viewer helpers and only orchestrates them; it does not introduce new generation, composition, or viewer implementations.
- The DOC-004 schema expansion did not add new generation or scene-edit logic; it only gives existing and future components a shared typed contract.
- The DOC-004 context-view and mutation-guard expansion only derives typed views from `AgentProjectState`; it does not add parallel state storage or duplicate any existing service/tool implementation.
- The workflow runner composes existing adapters and scripts into one stateful path; it does not replace `tools/compose_blender_scene.py`, `tools/export_viewer_scene.py`, `ToolExecutor`, or `glb_viewer_server.py`.
- The subject-asset workflow runner reuses `Hunyuan3DDomainToolDispatcher` and `Hunyuan3DServiceAdapter`; it does not add a parallel Hunyuan3D client or a hidden polling loop.
- Subject asset QA reuses `FileArtifactStore`, `AgentProjectState`, `state_views.apply_state_updates`, and optionally the existing `render_preview` domain tool; it does not add another preview renderer or bypass tool phase guards.
- Subject asset repair-decision routing reuses `Asset3DRecord`, `AgentProjectState`, stored QA metadata, and `state_views.apply_state_updates` through the `SubjectAssetRepairRouter` owner; it does not add another generator, renderer, or retry executor.
- Subject asset repair execution reuses `Hunyuan3DDomainToolDispatcher` for retry dry-runs/submits, `PendingAction` for user/manual review, `AgentProjectState` for state updates, and the existing checkpoint recorder; it does not add another Hunyuan3D client, concept-image generator, or UI queue.
- ReviewPatch handoff reuses `PendingAction`, `ReviewPatch`, `AgentProjectState`, `apply_state_updates(...)`, and workflow checkpoints; it does not add an LLM parser, UI queue, or parallel feedback store.
- ReviewPatch concept regeneration reuses `ReviewPatch`, `ConceptBundle`, `FileArtifactStore`, `AgentProjectState`, `apply_state_updates(...)`, and workflow checkpoints; it does not add another image-generation client, feedback queue, or concept state store.
- The script-backed domain-tool dispatcher maps Blender domain tool names to existing script adapters and keeps execution delegated to `ToolExecutor`.
- The Hunyuan3D `build_subject_asset` dispatcher wraps `Hunyuan3DServiceAdapter`; it does not create a second Hunyuan3D client or store binary model payloads in state.
- The viewer runtime adapter wraps the existing GLB viewer HTTP surface; it does not start another viewer server or duplicate `tools/glb_viewer_server.py`.
- The Hunyuan3D/HY-World service adapters wrap the existing `scripts/start_a40_services.sh` services and current local API/runtime contracts; they do not start new model services or submit hidden generation jobs.
- The WorldMirror service adapter reads the existing HY-World Gradio `/config` contract, builds call plans for `_on_upload` / `gradio_demo`, uses Gradio's existing queued `/call` + SSE protocol for explicit upload/reconstruct submit/poll primitives, and extracts upload `target_dir`; it does not create another HY-World runtime, output converter, or hidden generation runner.
- The WorldMirror scene-asset adapter consumes existing `HY-World-2.0/gradio_demo_output` files and registers metadata only; it does not create another HY-World client, output converter, or generation runner.
- Agent LLM keys are documented by provider, priority, and suffix only in `docs/agent_llm_provider_notes.md`; plaintext is confined to the local ignored env file.
- The LLM provider adapter and visual-QA path currently support dry-run and mocked-provider tests; no live Qwen or DeepSeek request was sent in this slice.
- Workflow runner stage context reporting reuses `state_views` and `domain_tools`; it does not add a second state source or a new orchestration protocol.
- Frontend status snapshots reuse `AgentProjectState`, `PendingAction`, runner summaries, and checkpoint metadata; they are UI/handoff views, not another workflow state store or event bus.
- Delivery handoff metadata is derived from `AgentProjectState.viewer_scene` and viewer artifact metadata; it does not add another viewer server, exporter, or delivery package format.
- Delivery packaging copies existing artifact files into a deterministic package directory and zip; it does not re-export Blender, start viewer services, or duplicate artifact storage semantics.
- Checkpoint persistence stores JSON state snapshots and JSONL indexes/events only; it does not duplicate binary artifact storage or replace `FileArtifactStore`.
- `langgraph_adapter.py` records dependency and checkpoint-wiring diagnostics only; it does not fake a LangGraph graph while the real dependency is absent.
- The agent control contract slice reuses `AgentProjectState`, existing
  `ReferenceBinding`, `ConceptBundle`, `ReviewPatch`, `Asset3DRecord`,
  `BlenderSceneState`, `ViewerSceneState`, and `domain_tools`; it does not add a
  second state store, queue, MCP surface, generation service, or viewer.
- The LLM node execution slice reuses `agent_prompts.py` and
  `llm_providers.py`; it does not add a second provider client or allow LLM
  nodes to write state directly.
- The concept-planning state bridge reuses `ConceptBundle`,
  `ConceptPromptPack`, `AgentProjectState`, and
  `state_views.apply_state_updates(...)`; it does not add a second concept
  store or LLM-owned state mutation path.
- The codex-self image extraction path consumes the existing
  `codex-self-mcp` JSONL output and registers the result through
  `concept-seed`; it does not add a second image store or bypass artifact
  registration.
- The runtime planning slice does not add another runner, viewer, state store,
  or service client. It wraps controller actions as job specs, centralizes
  Hunyuan3D generation profiles, and reads existing run outputs for front-end
  handoff.
- The runtime console MVP adds a browser control surface over existing run
  files. It records chat/upload evidence into the run directory and updates
  `AgentProjectState` for user turns/input images, but it does not replace
  checkpoints, `frontend_status.json`, `delivery_handoff.json`, or the GLB
  viewer.
- The runtime execution-step slice reuses `runtime_plan.json`,
  `llm_nodes.py`, provider configs, and `AgentProjectState` context views. It
  only adds durable execution evidence for one planned step, and it delegates
  long/background/sub-agent work instead of hiding service calls in the console
  request.
- The runtime bounded-loop and delegated-handoff slices reuse
  `runtime_plan.json`, `runtime_execution.jsonl`, `runtime_apply.jsonl`,
  checkpoints, `AgentProjectState`, and the existing codex-self/Hunyuan
  command hints. They do not execute long model jobs in the HTTP request or add
  a parallel queue/state store.

## 2026-06-28 Runtime Loop And Handoff Slice

Implemented:

- `agent_runtime/runtime_loop.py`
  - Adds bounded `step -> apply -> rebuild plan` orchestration.
  - Stops at `waiting_user`, `delegated`, `blocked`, `failed`,
    `dry_run_needs_live_or_fixture`, `completed_no_jobs`, or `max_steps`.
  - Writes `runtime_loop.jsonl` and `runtime_loop_summary.json`.
- `agent_runtime/runtime_delegation.py`
  - Converts a recorded delegated execution into a run-local handoff package
    for worker/sub-agent execution.
  - Writes `runtime_handoff.jsonl`, `runtime_handoff_summary.json`, and
    `runtime_handoff/<handoff_id>.json`.
- `agent_runtime/runtime_handoff_apply.py`
  - Applies worker/sub-agent handoff results back into runtime state.
  - Concept-image results are registered as `SUBJECT_CONCEPT_IMAGE` artifacts,
    update `ConceptBundle`, move to concept review, checkpoint, and rebuild
    plan.
  - Subject-asset results are registered as `SUBJECT_3D_ASSET` artifacts,
    update `subject_assets`, move to subject asset QA, checkpoint, and rebuild
    plan.
- `agent_runtime/runtime_execution.py`
  - Supports fixture/live response text per node through the same JSON
    parse/Pydantic validation path as provider output.
  - Treats only `completed` records as handled for job selection; dry-run,
    user-gate, delegated, and blocked records remain retry-visible evidence.
  - Lets `SceneSpecCompiler` use `SceneInterpreter` candidate output only when
    the candidate is completed successfully and matches the current latest user
    turn.
- `agent_runtime/runtime_audit.py`
  - Audits loop and handoff summary/log consistency and handoff JSON paths.
- `tools/runtime_console_server.py`
  - Adds `POST /api/runs/<run_key>/loop`,
    `GET /api/runs/<run_key>/runtime-loop`,
    `POST /api/runs/<run_key>/handoff`, and
    `GET /api/runs/<run_key>/runtime-handoff`.
- `web/runtime_console/`
  - Adds Loop/Handoff controls, a main preview status strip, uploaded reference
    chips, grouped file manifest display, and clearer empty-preview messaging.

Verification:

```text
pytest -q
261 passed in 1.31s

python -m py_compile agent_runtime/runtime_delegation.py agent_runtime/runtime_handoff_apply.py \
  agent_runtime/runtime_loop.py agent_runtime/runtime_execution.py agent_runtime/runtime_audit.py \
  agent_runtime/runtime_runs.py tools/runtime_console_server.py agent_runtime/__init__.py

node --check web/runtime_console/app.js
```

Real HTTP evidence:

```text
run_id=runtime_handoff_http_audit_20260628_001
loop_stop=delegated
handoff_status=planned
handoff_tool=generate_concept_images
handoff_json=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/runtime_handoff_http_audit_20260628_001/runtime_handoff/handoff_53a76129eca4.json
audit_ok=true errors=0 warnings=0 checks=34

run_id=runtime_handoff_apply_http_audit_20260628_001
handoff_apply=concept image
state_phase=CONCEPT_REVIEW
audit_ok=true errors=0 warnings=0 checks=38

run_id=runtime_subject_asset_handoff_apply_http_20260628_002
handoff_apply=subject GLB
state_phase=SUBJECT_ASSET_QA
next_plan_tool=build_scene_asset
audit_ok=true errors=0 warnings=0 checks=26
```

## Current Limitations

- The runtime layer is not yet a full LangGraph workflow.
- The prompt/schema/controller layer is now implemented as deterministic
  contracts and tests. `ConceptPromptPlanner` has one successful live Qwen
  JSON/Pydantic smoke, and its output can now be applied to workflow state as a
  `ConceptPromptPack`. This is still not a full multi-node autonomous agent
  loop.
- DOC-004 core state schemas, context-view builders, controlled-field mutation guards, file-backed state checkpoints, DOC-006 `MCPClientManager`, and a small single-state local workflow runner are implemented, but they are not yet wired into a full LangGraph node graph/checkpointer.
- The current Python environment does not have `langgraph` installed (`ModuleNotFoundError: No module named 'langgraph'`), so real graph/checkpointer integration should wait for an explicit dependency/environment decision.
- Workflow runner outputs now write stage-level checkpoints for executed runner stages plus a final checkpoint per run. This covers the currently implemented runner stages, but not every future DOC-003 node boundary such as SceneSpec creation, ConceptBundle generation, concept approval, Blender edit application, or high-quality preview rendering.
- Workflow runner outputs now also write `frontend_status.json` for front-end phase/node/progress and pending-action handoff. This is a derived view and does not replace `state.json`, `summary.json`, checkpoints, or future API endpoints.
- A runtime console MVP now exists on port `8093` with run selection,
  chat input, reference-image upload, embedded GLB viewer, object list, and
  delivery links. It can build a runtime plan and execute one safe dry-run step
  with durable logs; it is still not a full autonomous multi-step dispatcher,
  and uploaded references still need the explicit reference-binding validator
  path before high-cost generation.
- Script-backed domain-tool dispatch exists for `import_scene_asset`, `export_viewer_scene`, and `render_preview`; Hunyuan3D-backed domain dispatch exists for `build_subject_asset`; WorldMirror-backed dispatch exists for runtime status, generation call planning, explicit queued upload/reconstruct submit/poll boundaries, and existing-output scene adaptation; Blender Lab MCP-backed dispatch exists for safe selected read/edit operations through an injected raw MCP caller; `blender-edit` workflow/CLI dry-run exists; delivery package creation exists as a workflow entrypoint. Live `ConceptPromptPlanner` through Qwen and live Hunyuan3D subject generation have been exercised; live HY-World generation submission has not.
- Hunyuan3D service adapter supports payload/health/async status primitives, and its dispatcher is wired into a separate `workflow_runner subject-asset` path with explicit submit/status/save stages.
- Hunyuan3D live generation has now been submitted once for the 2026-06-28 real demo. The completed run was shape-only (`--no-texture`) and saved `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/subject_asset_live_save/subject_assets/demo_robot_asset_001.glb`.
- Subject asset QA has deterministic GLB metadata/header checks, optional preview-render wiring, dry-run/mocked MLLM visual-similarity scaffolding, post-QA repair-decision routing, and an explicit repair execution boundary; live provider visual QA has not been run yet.
- Subject asset repair execution can accept passed assets, plan Hunyuan3D retry dry-runs, block unconfirmed live retries, route subject-image regeneration to the concept-generation phase, and create pending actions for user/manual review.
- ReviewPatch handoff can turn pending subject-asset repair feedback into a structured `ReviewPatch`, clear the pending action, and move state to `CONCEPT_REVIEW`.
- ReviewPatch concept regeneration can dry-run the `regenerate_concept_images` plan and can register an explicit generated/manual image as a new `SUBJECT_CONCEPT_IMAGE` artifact, update `ConceptBundle`, clear stale concept approval/QA, and mark the patch applied.
- Actual Hunyuan3D repair retry submission remains guarded by `--confirm-repair-execute` outside dry-run; codex-self image generation can now be ingested as a project artifact, but a first-class project-native image-model provider and richer manual-review UI flows are still future stages.
- HY-World service adapter supports runtime status, extracts the live Gradio `_on_upload` / `gradio_demo` contract, can submit queued uploads for local input files, can extract upload `target_dir`, can submit queued reconstruction calls for a `target_dir`, and can parse SSE polling results.
- The `scene-asset` workflow can prepare upload/reconstruct call plans, dry-run queued upload/reconstruct submit/poll stages, pass upload `target_dir` into reconstruct submit within one run, and save/register existing WorldMirror output directories.
- Live long-running HY-World upload/reconstruct submit/poll has not been exercised yet; the first real demo used an existing HY-World scene GLB.
- Viewer runtime/status adapter is implemented for the existing GLB viewer and records viewer URLs/checks in artifact metadata.
- Delivery/front-end handoff metadata, generic front-end status snapshots, and deterministic export package creation are implemented, but richer release packaging/signing/upload flows are not implemented yet.
- Live Hunyuan3D shape-only subject generation was made in the 2026-06-28 real demos. No live WorldMirror/HY-World generation call was made.
- Live Blender preview render, scene composition, and viewer export now pass for the 2026-06-28 real demo artifacts.
- Local E2E smoke now passes for existing artifacts and verifies GLB viewer reachability.
- Local workflow runner E2E now passes for existing artifacts and records one project state across compose, viewer export, and viewer reachability.
- Scene-asset workflow can inspect and register an existing WorldMirror output directory into `AgentProjectState.scene_asset`.
- The compose smoke placement is still a basic existing-script placement smoke, not final layout intelligence.
- Qwen and DeepSeek API keys have been supplied and recorded locally for later testing, with Qwen preferred. Provider loading and dry-run request construction are implemented, and one live Qwen `ConceptPromptPlanner` smoke passed; broader live provider testing is still deferred until the close-out phase.
- `codex-self-mcp` status probing, command planning, explicit smoke, and workflow-level handoff planning are implemented; real sub-agent execution is guarded by `execute_handoff` plus explicit confirmation, and full autonomous task routing remains future work.
- Blender Lab MCP status/readback probing, safe V1 operation plan generation, `MCPClientManager` raw-call boundary, dispatcher-level raw MCP execution/logging, `blender-edit` workflow dry-run, and explicit socket-backed non-dry-run CLI smoke are implemented for selected safe operations.

## Next Steps

0. Before each next step, refresh the infrastructure inventory and decide whether the task should reuse, wrap, or extend an existing component. Do not create parallel implementations without recording the reuse decision.

1. Continue non-API workflow hardening: use the runner `context_views`, `delivery_handoff`, and stage checkpoint summaries as the handoff surface for future LangGraph node inputs.

2. Extend the runtime execution step into a bounded dispatcher loop: intake ->
   reference binding -> LLM node candidate output -> controlled state update ->
   background/sub-agent execution -> status refresh. Keep long model jobs out
   of the main request thread.

3. Decide whether to install/use `langgraph` in this environment, then wrap `FileStateCheckpointStore` with the actual LangGraph graph/checkpointer integration and add checkpoint save points for DOC-003 nodes not represented by the current runner stages.

4. Run the next real demo improvement: carry the project-ingested generated
   concept and Qwen prompt pack through a single richer stateful workflow, then
   rerun Hunyuan3D with texture enabled if runtime budget allows.

5. Extend the `codex-self` handoff workflow only when needed with richer result ingestion and parent/child task routing; keep it operator-triggered and separate from ordinary LLM providers.

6. Extend delivery packaging only if needed with richer release packaging/signing/upload flows; the deterministic local zip path is implemented.

7. When the user wants a fresh scene asset, execute the confirmed HY-World upload -> upload-poll -> reconstruct-submit -> reconstruct-poll -> save path on a small chosen input, then record event ids, SSE completion evidence, output directory, and registered artifacts.

8. Extend subject asset QA from dry-run/mocked visual QA to explicit live Qwen testing when API close-out is requested; keep DeepSeek as fallback/comparison only if a vision-capable model path is configured.

9. Verify exact current API base URLs/model IDs during the final API close-out phase, prefer Qwen 3.7max, and use both providers for heavier close-out testing where applicable.

## 2026-06-28 Prompt Review, Scenario Fixtures, And Result Apply Extension

Goal: push the V1 runtime from code-readable scaffolding toward user-reviewable
and fixture-tested agent behavior, without adding a second queue/state system.

Implemented:

- `agent_runtime/prompt_catalog.py` and `scripts/export_agent_prompts.py`
  generate `docs/agent_prompt_catalog.md` from live node specs.
- `agent_runtime/agent_prompts.py` now keeps Chinese `context_json` readable in
  built prompts instead of escaping it as Unicode sequences.
- `tests/fixtures/natural_language_scene_cases.json` defines executable
  natural-language scenarios covering Chinese/English, text-only requests,
  explicit subject/scene/style/texture/layout bindings, multi-subject layouts,
  architecture requests, and missing-binding clarification.
- `agent_runtime/scenario_fixtures.py` materializes those scenarios as
  runtime-console run directories.
- `tests/test_natural_language_scene_fixtures.py` drives the bounded runtime
  loop through fixture provider output and checks state, prompt output files,
  audit status, and delegated generation stop points.
- `agent_runtime/runtime_handoff_apply.py` now supports:
  - `scene_asset_results`: registers WorldMirror/HY-World output directories
    through the existing scene-asset adapter and rebuilds the plan toward
    Blender assembly.
  - `blender_results`: registers `.blend`, `viewer_scene.glb`, optional
    `scene_state.json`, and optional preview render artifacts, updates
    `BlenderSceneState`/`ViewerSceneState`, moves to `BLENDER_PREVIEW`, and
    rebuilds the user approval gate.
- `tools/runtime_console_server.py` exposes the new result payload types through
  the existing `POST /api/runs/<run_key>/handoff-apply` endpoint.

Verification:

```text
python -m pytest -q
280 passed in 1.76s

python -m py_compile agent_runtime/agent_prompts.py agent_runtime/prompt_catalog.py \
  agent_runtime/scenario_fixtures.py agent_runtime/runtime_handoff_apply.py \
  tools/runtime_console_server.py agent_runtime/__init__.py

node --check web/runtime_console/app.js
```

Status update:

- File/runtime control plane is now approximately 86% of the uploaded V1 plan.
- The real autonomous image-to-Blender-scene agent is approximately 80% complete
  for the V1 control-plane definition: prompt review, multi-scenario intake
  fixtures, concept/subject/scene/Blender result apply, checkpoints, frontend
  status, and preview approval gate are all represented in code and tests.
- Remaining gaps at this point were confirmed live worker/sub-agent execution
  beyond dry-run/fixture, broader live Qwen/DeepSeek node tests, first-class
  image-provider integration, textured Hunyuan close-out, live HY-World
  evidence, richer UI approval/retry controls, and final polished acceptance
  run. The fresh codex-self concept-image worker gap was closed later in this
  file; Hunyuan/HY-World/final acceptance remain open.

## 2026-06-29 Runtime Console Chinese Creator UI Pass

Goal: address the user's review that the browser console was visually unclear,
too English/log-like, and did not show the workflow phases clearly, while
preserving the existing runtime API, file manifest, and GLB viewer reuse.

Implemented:

- `web/runtime_console/index.html`
  - changed the console to Chinese labels;
  - moved chat/reference upload into the left work rail beside run navigation;
  - kept the center focused on phase/progress plus the 3D preview;
  - kept the right rail for status, next jobs, objects, files, and delivery.
- `web/runtime_console/app.js`
  - added a Chinese V1 phase timeline:
    `需求 -> 理解 -> 概念图 -> 主体3D -> 场景资产 -> Blender -> 预览验收 -> 交付`;
  - added a Chinese next-action banner derived from `runtime_plan`;
  - translated phase/status/node/file labels used in the status strip,
    inspector, run list, and file manifest;
  - translated common internal `current_stage` ids such as
    `runtime_state_apply`, `quality_check`, `viewer_check`, and
    `delivery_package` into readable Chinese step names;
  - collapsed long local file paths behind `<details>` to reduce right-side
    noise while keeping path evidence available.
- `web/runtime_console/styles.css` and `web/runtime_console/polish.css`
  - replaced the old sparse engineering-panel look with a compact light
    creator-console layout inspired by mainstream design-system workbenches;
  - increased contrast and spacing discipline;
  - added stage timeline, next-action banner, and responsive behavior.
- `docs/agent_runtime_contract.md` and `docs/v1_overall_status.md`
  - updated the UI contract/status so future work follows the new layout.

Verification:

```text
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py -p no:cacheprovider
10 passed in 0.33s

./scripts/stop_runtime_console.sh
./scripts/start_runtime_console.sh
./scripts/status_runtime_console.sh
Runtime console started: pid=3967708
URL: http://10.2.16.106:8093/

curl -sS http://127.0.0.1:8093/
confirmed Chinese UI labels: image23D 创作控制台, 运行记录, 对话与参考图,
当前状态, 下一步, 打开 GLB

curl -sS http://127.0.0.1:8093/styles.css
confirmed served CSS includes stage-timeline, next-action-banner, and the new
320px / preview / 360px workbench grid.

curl -sS http://127.0.0.1:8093/api/runs
confirmed the console API still lists existing visual runs with
has_viewer_scene=true.
```

Limitations:

- Browser screenshot verification was not run because this environment lacks
  Playwright/Chromium.
- The UI still needs first-class approval/retry/object-inspection controls; the
  current pass makes the existing control plane readable and stage-oriented.

## 2026-06-29 Runtime Console Inspector Polish

Goal: address the user's review that the 8093 console looked like a sparse
debug surface with too much raw English/technical state in the right rail,
while keeping the existing runtime APIs and DOM button ids intact.

Implemented:

- `web/runtime_console/index.html`
  - changed toolbar actions to `打开预览` and `打开工程文件`;
  - renamed the right rail to `当前步骤` / `本步操作`;
  - moved `场景对象`, `运行文件`, and `交付入口` into native collapsible
    inspector sections so paths and low-priority artifacts no longer dominate
    the first view.
- `web/runtime_console/styles.css`
  - changed the main grid to responsive clamp-based three columns;
  - changed the phase timeline to a horizontal scrollable stepper instead of
    cramped eight fixed columns;
  - made the right rail read more like an inspector: fewer shadows, thinner
    row accents, collapsible details, and clearer primary action buttons;
  - kept the inspector visible at the 1060px breakpoint by moving it below the
    main columns instead of hiding it.
- `web/runtime_console/polish.css`
  - removed card shadows from object/file/job rows while keeping light polish
    on the preview, run items, and chat messages.
- `web/runtime_console/app.js`
  - added `codex_self_log` label `Codex 图像日志`;
  - added readable fallbacks for `workflow_runner.*`, snake-case ids,
    `main_runtime`, `background_worker`, `fixture`, and common object types
    such as `EMPTY`, `MESH`, `CAMERA`, and `LIGHT`;
  - displays `world` as `环境根节点` and `geometry_0`-style ids as
    `场景网格 N`;
  - moves raw object ids, long URLs, and local paths into `技术详情`;
  - converts common request/upload errors to Chinese before display.

Verification:

```text
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html

HTTP static check on running console pid=760938:
/           200 text/html; charset=utf-8 4432
/app.js     200 text/javascript; charset=utf-8 40226
/styles.css 200 text/css; charset=utf-8 17221
/polish.css 200 text/css; charset=utf-8 1322
```

Limitations:

- Browser screenshot verification still cannot run in this environment because
  Playwright and system Chromium/Chrome are not installed.
- This pass improves readability and hierarchy; it does not yet add the
  first-class approve/retry buttons or object-level viewer operations.

## 2026-06-29 Runtime Worker Execution Bridge

Goal: advance the V1 runtime from "delegated handoff package exists" to a
bounded worker/sub-agent execution bridge, without putting long jobs back into
the HTTP step loop and without adding a second queue/state store.

Implemented:

- `agent_runtime/runtime_worker.py`
  - selects the next planned `RuntimeDelegatedHandoffRecord`;
  - writes `runtime_worker.jsonl`, `runtime_worker_summary.json`, and
    per-attempt JSON under `runtime_worker/`;
  - supports a deterministic `fixture` backend for local worker result
    registration tests;
  - supports a guarded `codex_self_mcp` backend that plans/dry-runs by default
    and requires `confirm_execute=True` for live execution;
  - supports a `codex_self_log` backend that ingests a completed codex-self MCP
    JSONL log, extracts the final image-generation result with the existing
    codex-self decoder, and applies the extracted image through the same
    handoff-result path;
  - applies successful worker outputs only through the existing
    `apply_concept_handoff_result`, `apply_subject_asset_handoff_result`,
    `apply_scene_asset_handoff_result`, or `apply_blender_assembly_result`
    functions.
- `agent_runtime/runtime_delegation.py`
  - handoff JSON now includes a `runtime_job` snapshot from `runtime_plan.json`,
    so execution adapters do not need to parse `command_hint`.
- `agent_runtime/runtime_runs.py`
  - `RuntimeRunBundle` now exposes `runtime_worker_summary`;
  - `file_manifest` now includes `runtime_worker` and
    `runtime_worker_summary`.
- `tools/runtime_console_server.py`
  - adds `GET /api/runs/<run_key>/runtime-worker`;
  - adds `POST /api/runs/<run_key>/worker`.
- `web/runtime_console/`
  - adds a "试跑子任务" control that runs the fixture backend in dry-run mode;
  - surfaces the latest worker attempt in the right-side job panel and main
    status strip.
- `tests/test_runtime_worker.py`
  - verifies dry-run worker evidence without state mutation;
  - verifies fixture concept result -> handoff-apply -> state/checkpoint/
    frontend status/runtime plan;
  - verifies missing fixture output fails without marking the handoff handled.
  - verifies `codex_self_mcp` non-dry-run cannot call the adapter without
    `confirm_execute`;
  - verifies a confirmed fake codex-self adapter can produce an extracted
    concept image and apply it through the existing handoff-apply path;
  - verifies a successful codex-self run with no extracted image is `failed`
    and does not mark the handoff handled.
  - verifies completed codex-self MCP JSONL logs can be decoded, registered as
    concept images, and applied to `ConceptBundle`;
  - verifies codex-self logs without image-generation results fail without
    marking the handoff handled.

Verification:

```text
python -m py_compile agent_runtime/runtime_worker.py \
  agent_runtime/runtime_delegation.py agent_runtime/runtime_runs.py \
  tools/runtime_console_server.py agent_runtime/__init__.py

node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html

pytest -q tests/test_runtime_worker.py -p no:cacheprovider
6 passed in 0.61s

pytest -q tests/test_runtime_delegation.py tests/test_runtime_execution.py \
  tests/test_runtime_loop.py tests/test_runtime_runs.py tests/test_runtime_console.py \
  tests/test_codex_self_mcp.py -p no:cacheprovider
33 passed in 0.60s

pytest -q -p no:cacheprovider
280 passed in 1.76s

HTTP smoke after restarting `tools/runtime_console_server.py`:
run_id=runtime_worker_http_smoke_20260629T080329Z
loop_stop=delegated
handoff_status=planned
worker_status=dry_run
runtime_worker manifest files present:
  runtime_worker
  runtime_worker_summary

Codex-self worker guard HTTP smoke:
run_id=runtime_worker_codex_guard_20260629T081100Z
loop_stop=delegated
handoff_status=planned
worker_backend=codex_self_mcp
worker_status=dry_run
worker_issues=["codex_self_worker_requires_confirm_execute"]
state_phase_after_guard=CONCEPT_GENERATION
apply_summary_exists=false
```

Boundary:

- `execute_next_runtime_job()` still stops at delegated long jobs.
- `runtime_worker` is execution evidence only; state changes still go through
  `runtime_handoff_apply`.
- Live codex-self/Hunyuan/HY-World/Blender worker execution remains behind
  explicit confirmation and existing service adapters.

## 2026-06-29 Codex-Self Log Worker Ingestion

Goal: make the sub-agent/file-transfer boundary concrete. A codex-self or
external worker can now hand the main runtime a completed MCP JSONL log; the
runtime extracts the generated image, registers it, checkpoints state, and
rebuilds the next plan without a manual path copy or a parallel queue.

Implemented:

- `agent_runtime/runtime_worker.py`
  - adds backend `codex_self_log`;
  - requires an explicit `fixture_payload.log_path`;
  - decodes the last image-generation result through
    `extract_last_image_from_codex_mcp_log(...)`;
  - writes the extracted image under `runtime_worker/` by default;
  - applies the image as a concept handoff result through
    `apply_concept_handoff_result(...)`.
- `web/runtime_console/app.js`
  - labels the backend as `Codex 图像日志` instead of showing the raw backend
    id in the worker panel.
- `tests/test_runtime_worker.py`
  - covers successful log ingestion into `CONCEPT_REVIEW`;
  - covers missing-image logs as failed and unhandled attempts.

Verification:

```text
python -m py_compile agent_runtime/runtime_worker.py tests/test_runtime_worker.py \
  tools/runtime_console_server.py

node --check web/runtime_console/app.js

pytest -q tests/test_runtime_worker.py -p no:cacheprovider
8 passed in 0.69s

pytest -q tests/test_runtime_worker.py tests/test_codex_self_mcp.py \
  tests/test_runtime_delegation.py tests/test_runtime_runs.py \
  tests/test_runtime_loop.py tests/test_runtime_execution.py -p no:cacheprovider
37 passed in 0.93s

pytest -q -p no:cacheprovider
282 passed in 1.95s
```

HTTP smoke after restarting `tools/runtime_console_server.py`:

```text
run_id=runtime_worker_codex_log_smoke_20260629T084200Z
loop_stop=delegated
handoff_status=planned
worker_backend=codex_self_log
worker_status=applied
applied_artifact_ids=["subject_robot_codex_log_http_001"]
state_phase=CONCEPT_REVIEW
final_preview_image_id=subject_robot_codex_log_http_001
runtime_worker manifest present=true
```

Notes:

- The first HTTP attempt without fixture LLM responses stopped correctly at
  `dry_run_needs_live_or_fixture`, proving the console does not silently fake
  LLM node outputs.
- A stale console process returned 400 for the new backend before restart. The
  console is now restarted on pid `760938`.
- This closes the completed-log ingestion/file-transfer path. It does not yet
  claim a freshly submitted live image-generation provider job. That later
  fresh codex-self worker path is closed by the
  `2026-06-29 Fresh Codex-Self Concept Worker` entry below.

## 2026-06-29 Concept Review User Gate Actions

Goal: make the first V1 user gate interactive. After concept images are
registered into `CONCEPT_REVIEW`, the runtime console can now either approve
the concept and continue to subject-asset generation, or convert explicit user
feedback into a pending `ReviewPatch` and route back to concept regeneration.

Implemented:

- `agent_runtime/runtime_user_actions.py`
  - adds a controlled user-action mutation boundary;
  - writes `runtime_user_action.jsonl` and
    `runtime_user_action_summary.json`;
  - `approve_concept` validates `CONCEPT_REVIEW` and existing concept outputs,
    marks `ConceptBundle.approved=true`, writes `approved_at`, advances phase
    to `CONCEPT_APPROVED`, checkpoints, refreshes `frontend_status.json`, and
    rebuilds the plan toward `build_subject_asset`;
  - `request_concept_changes` requires feedback text, creates a pending
    `ReviewPatch` with lineage to the user turn/action and affected concept
    artifacts, checkpoints, refreshes status, and rebuilds the plan toward
    `RegenerationRouter -> ConceptPromptPlanner -> regenerate_concept_images`.
- `tools/runtime_console_server.py`
  - adds `POST /api/runs/<run_key>/user-action`;
  - adds `GET /api/runs/<run_key>/runtime-user-action`.
- `agent_runtime/runtime_runs.py`
  - exposes `runtime_user_action_summary` in `RuntimeRunBundle`;
  - adds `runtime_user_action` and `runtime_user_action_summary` to the file
    manifest.
- `web/runtime_console/`
  - shows a concept-review gate panel when phase is `CONCEPT_REVIEW`;
  - provides `确认概念图` and `按输入意见重做`;
  - records feedback text into chat before calling the user-action endpoint;
  - surfaces the latest user action in the right-side job list.
- `tests/test_runtime_user_actions.py`
  - covers approval -> `CONCEPT_APPROVED` -> `build_subject_asset`;
  - covers feedback -> pending `ReviewPatch` -> regeneration plan;
  - covers invalid gate execution without state mutation.

Verification:

```text
python -m py_compile agent_runtime/runtime_user_actions.py \
  agent_runtime/runtime_runs.py tools/runtime_console_server.py \
  tests/test_runtime_user_actions.py

node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html

pytest -q tests/test_runtime_user_actions.py -p no:cacheprovider
3 passed in 0.34s

pytest -q tests/test_runtime_user_actions.py tests/test_runtime_worker.py \
  tests/test_runtime_runs.py tests/test_runtime_console.py tests/test_controller.py \
  -p no:cacheprovider
27 passed in 0.88s

pytest -q -p no:cacheprovider
285 passed in 1.95s
```

HTTP smokes after restarting `tools/runtime_console_server.py`:

```text
run_id=runtime_user_gate_approve_smoke_20260629T091500Z
loop_stop=delegated
handoff_status=planned
worker_status=applied
approval_status=applied
phase=CONCEPT_APPROVED
concept_approved=true
first_plan_tool=build_subject_asset
manifest_has_user_action=true

run_id=runtime_user_gate_feedback_smoke_20260629T091700Z
feedback_status=applied
phase=CONCEPT_REVIEW
review_patch_count=1
review_patch_status=pending
plan_sequence=[
  RegenerationRouter,
  ConceptPromptPlanner,
  regenerate_concept_images
]
```

Boundary:

- This section implemented the concept-review gate first. The following
  `Blender Preview User Gate Actions` section extends the same mechanism to
  `BLENDER_PREVIEW`.
- The approval action does not submit Hunyuan3D directly; it only rebuilds the
  next plan so subject generation remains behind the existing worker/service
  boundary.

## 2026-06-29 Blender Preview User Gate Actions

Goal: finish the second V1 user gate. After Blender/viewer outputs are
registered into `BLENDER_PREVIEW`, the runtime console can now either approve
the preview and continue to delivery, or convert explicit user feedback into a
pending `ReviewPatch` and route to the existing `BLENDER_EDIT` plan.

Implemented:

- `agent_runtime/runtime_user_actions.py`
  - extends `RuntimeUserActionType` with `approve_blender_preview` and
    `request_blender_changes`;
  - `approve_blender_preview` validates `BLENDER_PREVIEW`, `blender_scene`, and
    `viewer_scene`, advances phase to `DELIVERY`, checkpoints, refreshes
    `frontend_status.json`, and rebuilds the delivery plan;
  - `request_blender_changes` requires feedback text, creates a pending
    `ReviewPatch` with Blender/viewer lineage and affected preview artifacts,
    moves phase to `BLENDER_EDIT`, checkpoints, refreshes status, and rebuilds
    the plan toward `BlenderEditRouter -> export_viewer_scene -> render_preview`.
- `tools/runtime_console_server.py`
  - routes the new user-action types through the existing
    `POST /api/runs/<run_key>/user-action` endpoint.
- `web/runtime_console/app.js`
  - shows `确认预览并交付` and `按输入意见调整` when phase is
    `BLENDER_PREVIEW`;
  - records preview feedback into chat before calling `request_blender_changes`;
  - labels the new user actions in the job evidence panel.
- `tests/test_runtime_user_actions.py`
  - covers preview approval -> `DELIVERY` -> delivery job;
  - covers preview feedback -> pending `ReviewPatch` -> `BLENDER_EDIT` plan;
  - covers invalid preview approval without state mutation.

Verification:

```text
python -m py_compile agent_runtime/runtime_user_actions.py \
  tools/runtime_console_server.py tests/test_runtime_user_actions.py

node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html

pytest -q tests/test_runtime_user_actions.py -p no:cacheprovider
6 passed in 0.39s

pytest -q tests/test_runtime_user_actions.py tests/test_runtime_runs.py \
  tests/test_runtime_console.py tests/test_controller.py tests/test_runtime_delegation.py \
  -p no:cacheprovider
28 passed in 0.55s

pytest -q -p no:cacheprovider
288 passed in 2.03s
```

HTTP smokes after restarting `tools/runtime_console_server.py`:

```text
run_id=runtime_blender_preview_approve_smoke_20260629T095000Z
status=applied
phase=DELIVERY
first_plan_kind=delivery
user_action_summary=approve_blender_preview

run_id=runtime_blender_preview_feedback_smoke_20260629T095100Z
status=applied
phase=BLENDER_EDIT
review_patch_status=pending
plan_sequence=[
  BlenderEditRouter,
  export_viewer_scene,
  render_preview
]
user_action_summary=request_blender_changes
```

Boundary:

- This closes the first-class UI/runtime action surface for both V1 user gates:
  concept review and Blender preview review.
- The Blender edit action still plans through the existing safe edit/export/
  render boundary. It does not execute a non-dry-run Blender edit by itself.

## 2026-06-29 Runtime Console Creator-Workbench UI Pass

Goal: make the frontend reviewable as a product surface instead of a runtime
debugger. The user-facing screen should show the run list, chat/reference
upload, 3D preview, current phase, next action, asset readiness, and delivery
links. Raw ids, absolute paths, file manifests, and runtime logs remain
available, but behind the default-closed developer details panel.

Implementation:

- `web/runtime_console/index.html`
  - moved chat/reference upload out of the left sidebar and into the center
    creator area under the GLB preview;
  - changed the right rail to `当前阶段`, `资产清单`, `交付`, and default-closed
    `开发详情`;
  - kept existing element ids used by the vanilla JS runtime so no new state
    source or framework was introduced.
- `web/runtime_console/app.js`
  - added a UI view-model for business asset readiness: reference images,
    concept images, subject GLB, scene asset, Blend project, and web preview;
  - added a phase hero and cleaner run-list labels;
  - removed visible `viewer_scene.glb` wording from user-facing empty states;
  - kept runtime plan, files, objects, and tool evidence in the developer
    details path.
- `web/runtime_console/polish.css`
  - added the creator-workbench layout: left run list, center preview + chat,
    right Chinese phase/asset/delivery rail;
  - increased text contrast and minimum practical UI font sizes;
  - changed the phase timeline into a vertical right-rail stepper.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py -p no:cacheprovider
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py -p no:cacheprovider
```

Results:

```text
node --check passed
html.parser passed
4 passed in 0.32s
10 passed in 0.35s
```

HTTP/static checks against the live console on `8093`:

```text
GET / returned 200 with Cache-Control: no-store
index.html contains: 创作对话, 资产清单, 当前阶段, 开发详情
index.html does not contain: Open GLB, Build Plan, viewer_scene.glb
app.js contains: renderAssets, runDisplayTitle, 当前还没有 3D 预览
app.js does not contain: Open GLB, Build Plan, viewer_scene.glb
```

Runtime bundle smoke:

```text
run_count=34
selected=r_MjAyNjA2MjhfY29kZXhfc2VsZl9yb2JvdF9jb25jZXB0
phase=BLENDER_PREVIEW
manifest_files=23
has_web_surface=True
```

Boundary:

- This is still the existing static vanilla JS console served by
  `tools/runtime_console_server.py`; no React/Ant Design/Open WebUI fork was
  introduced.
- The environment did not expose Chromium/Playwright, so this slice was
  verified by HTML/JS parsing, DOM-id checks, HTTP content checks, API bundle
  smoke, and existing Python tests rather than a screenshot test.

## 2026-06-29 Runtime Console User-Review Correction

Goal: respond to the user review that the console still looked like a sparse
debugger: too much pale whitespace, right-rail technical/status leakage, weak
stage presentation, and an ugly native file picker. Keep the existing runtime
API/DOM ids intact while making the first screen closer to a simple creator
workbench.

Implementation:

- `web/runtime_console/index.html`
  - added a narrow product nav rail before the run list;
  - added non-empty loading placeholders for run list, phase, next action,
    assets, and delivery so the first paint is not blank while API fetches;
  - changed the upload form to keep `uploadInput` but expose a clean
    "添加参考图" drop/attachment affordance.
- `web/runtime_console/app.js`
  - added empty-run handling instead of leaving the run list blank;
  - added `viewerTitle(...)` and `runNameLabel(...)` so run names and preview
    titles no longer expose raw run ids as the main label;
  - removed the user-facing "查看状态快照" / run-directory delivery item;
  - keeps paths and ids only in nested technical detail sections.
- `web/runtime_console/polish.css`
  - added the four-column shell: nav rail, run list, center preview/composer,
    right phase/asset/delivery rail;
  - hid the native file input and styled the reference upload affordance;
  - raised contrast and made the right rail default information readable
    before any debug details are opened.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py -p no:cacheprovider
./scripts/stop_runtime_console.sh && ./scripts/start_runtime_console.sh && ./scripts/status_runtime_console.sh
```

Results:

```text
node --check passed
html.parser passed
10 passed in 0.35s
runtime console restarted on http://10.2.16.106:8093/ with pid=3585653
```

HTTP/API checks after restart:

```text
GET / contains: workspace-nav, 添加参考图
GET /app.js does not contain: Open GLB, Open Blend, Build Plan, Step Dry,
  Scene Preview, 查看状态快照, frontend_status_path || bundle.run_dir
run_count=36
first_run=20260629_scene_spec_assembly_non_dryrun
first_run has_viewer_scene=True
first_run has_scene_state=True
```

Browser evidence:

```text
/tmp/image23d_console_frontend_after.png
```

The screenshot verifies the new shell, non-empty loading state, right-rail phase
card, asset/delivery placeholders, and styled reference upload. Firefox
headless captures before async run data finishes loading, so API evidence above
is used to verify that the live browser will load visual runs after fetch.

Boundary:

- This still does not introduce a React/Ant Design/Open WebUI fork. The reason
  is reuse-first: the existing static console already owns chat, upload,
  user-gate actions, worker controls, run discovery, and file routing.
- The next frontend quality step is a proper loaded-state browser automation
  check with a browser driver, plus richer thumbnails/object-level controls.

## 2026-06-29 Deterministic Blender Assembly Plan Input

Goal: move Blender composition beyond hard-coded smoke placement without
creating a second Blender pipeline. The existing compose script should accept a
structured placement/camera plan, and the workflow runner should produce and
record that plan as first-class run evidence.

Implementation:

- `agent_runtime/blender_assembly_planner.py`
  - added `ComposeScenePlan`;
  - added `build_compose_scene_plan(...)`, mapping `SceneSpec` subject priority,
    scale hints, placement hints, spatial relations, and camera hints into:
    target region, normalized scene placement, target height ratio, camera
    direction, camera distance multiplier, orthographic scale factor, render
    resolution, and reasoning text;
  - keeps a deterministic fallback when `state.scene_spec` is absent.
- `tools/compose_blender_scene.py`
  - keeps the original four-argument mode;
  - accepts an optional fifth `assembly_plan.json`;
  - uses plan fields for subject target height/region, camera direction,
    camera distance, orthographic framing, and render resolution.
- `agent_runtime/script_adapters.py`
  - `build_compose_blender_scene_command(...)` now accepts optional
    `assembly_plan_json` and appends it to the existing Blender command.
- `agent_runtime/domain_dispatcher.py`
  - `import_scene_asset` preserves optional `assembly_plan_json` in command
    arguments and tool-call logging.
- `agent_runtime/workflow_runner.py`
  - `_run_compose_stage(...)` writes `compose/assembly_plan.json`;
  - passes that plan through the existing `ScriptDomainToolDispatcher`;
  - includes the plan JSON path and plan body in `summary.json`;
  - records plan id/path in compose-stage checkpoint metadata.
- `docs/blender_asset_pipeline_contract.md`
  - documents the current compose plan contract and where it is recorded.

Verification:

```bash
python -m py_compile \
  agent_runtime/blender_assembly_planner.py \
  tools/compose_blender_scene.py \
  agent_runtime/script_adapters.py \
  agent_runtime/domain_dispatcher.py \
  agent_runtime/workflow_runner.py

pytest -q tests/test_blender_assembly_planner.py \
  tests/test_script_adapters.py tests/test_workflow_runner.py \
  -p no:cacheprovider

pytest -q tests/test_domain_dispatcher.py tests/test_smoke.py \
  -p no:cacheprovider
```

Results:

```text
py_compile passed
56 passed in 0.82s
35 passed in 0.41s
```

Dry-run artifact smoke:

```bash
python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/subject_asset_status_save/subject_assets/codex_self_robot_asset_001.glb \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_blender_assembly_plan_smoke \
  --dry-run \
  --stages compose
```

Smoke evidence:

```text
output_dir=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_blender_assembly_plan_smoke
assembly_plan_json=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_blender_assembly_plan_smoke/compose/assembly_plan.json
plan_id=compose_plan_fallback_v1
target_region=front_left
target_height_ratio=0.42
camera_ortho_scale_factor=1.55
tool_call_status=succeeded
stage_checkpoint_metadata includes assembly_plan_id and assembly_plan_json
```

Boundary:

- No live Hunyuan3D, HY-World, or non-dry-run Blender job was submitted in this
  slice.
- This is deterministic placement/camera planning, not a mature visual/LLM
  Blender layout planner. It creates the executable contract that a later
  `BlenderAssemblyPlanner` LLM node can emit.

## 2026-06-29 SceneSpec Non-Dry-Run Assembly And Package

Goal: close the immediate P4/P6 gap after adding `assembly_plan.json`: feed a
real saved `SceneSpec` into a non-dry-run compose/export/viewer-check pass, then
package the resulting Blender/viewer artifacts with deterministic delivery
metadata.

Run:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun
```

SceneSpec input:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/scene_spec.json
```

Local non-dry-run command:

```bash
python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260627_153319_490326/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/subject_asset_status_save/subject_assets/codex_self_robot_asset_001.glb \
  --scene-spec-json /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/scene_spec.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun \
  --viewer-base-url http://10.2.16.106:8092 \
  --compose-timeout 600 \
  --export-timeout 300 \
  --viewer-timeout 10
```

Non-dry-run result:

```text
phase=BLENDER_PREVIEW
delivery_handoff.ready=true
delivery_handoff.verified=true
viewer_model_ok=true
viewer_runtime_ok=true
viewer_scene_object_count=7
assembly_plan_id=compose_plan_subject_plush_v1
target_region=front_right
target_height_ratio=0.5
```

Key artifacts:

```text
compose/assembly_plan.json
compose/composed_scene.blend
compose/composed_preview.png
viewer_export/viewer_scene.glb
viewer_export/scene_state.json
frontend_status.json
delivery_handoff.json
summary.json
tool_call_log.json
```

Delivery package command:

```bash
python -m agent_runtime.workflow_runner delivery-package \
  --state-json /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/state.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/delivery_package \
  --package-id scene_spec_assembly_20260629
```

Delivery package result:

```text
ok=true
package_zip=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/delivery_package/package/scene_spec_assembly_20260629.zip
zip_size_bytes=146769224
issues=[]
packaged_state_phase=DELIVERY
packaged_frontend_status_phase=DELIVERY
```

Independent zip/manifest verification:

```text
metadata.json present
version_manifest.json present
files/blender/workflow_composed_blend.blend present
files/preview/workflow_composed_preview_png.png present
files/viewer_scene/workflow_viewer_scene_glb.glb present
files/viewer_state/workflow_scene_state_json.json present
files/subject_assets/workflow_subject_glb.glb present
files/scene_assets/workflow_scene_glb.glb present
manifest item_count=6
```

Verification:

```bash
python -m py_compile agent_runtime/workflow_runner.py tests/test_workflow_runner.py
pytest -q tests/test_workflow_runner.py tests/test_blender_assembly_planner.py -p no:cacheprovider
pytest -q tests/test_workflow_runner.py tests/test_blender_assembly_planner.py tests/test_runtime_runs.py -p no:cacheprovider
pytest -q -p no:cacheprovider
```

Results:

```text
py_compile passed
52 passed in 0.75s
58 passed in 0.69s
292 passed in 2.08s
```

Runtime console discoverability:

```text
GET /api/runs returns run 20260629_scene_spec_assembly_non_dryrun first
has_viewer_scene=true
has_scene_state=true
frontend_status.phase=BLENDER_PREVIEW for source run
delivery_package/frontend_status.phase=DELIVERY for packaged run
```

Boundary:

- This run reuses an existing HY-World scene GLB and an existing generated
  subject GLB; it does not prove live HY-World submission or textured
  Hunyuan3D generation.
- Scene composition is now real and packageable, but still needs a
  visual/user edit loop before it should be treated as polished output.

## 2026-06-29 Codex-Self Non-Dry-Run Text Execute Smoke

Goal: move the codex-self/sub-agent channel beyond status/plan/dry-run guard
evidence with one confirmed non-dry-run execution, while keeping the task
small, text-only, and non-mutating.

Command:

```bash
python -m agent_runtime.workflow_runner codex-self \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_codex_self_execute_text_smoke \
  --cwd /home/team/zouzhiyuan/image23D_Agent \
  --prompt '请只回复 CODEX_SELF_EXECUTE_OK，不要运行命令，不要生成图片，不要改文件。' \
  --stages status,plan_handoff,execute_handoff \
  --no-dry-run \
  --confirm-execute \
  --timeout 120
```

Result:

```text
ok=true
dry_run=false
executed_stages=[status, plan_handoff, execute_handoff]
execute_handoff.ok=true
returncode=0
stdout_tail contains CODEX_SELF_EXECUTE_OK
```

Evidence:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_codex_self_execute_text_smoke/summary.json
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_codex_self_execute_text_smoke/codex_self_mcp_call.jsonl
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_codex_self_execute_text_smoke/checkpoints/checkpoints.jsonl
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_codex_self_execute_text_smoke/frontend_status.json
```

The JSONL log records a real codex MCP session with `task_started`,
`mcp_startup_complete`, final assistant content `CODEX_SELF_EXECUTE_OK`, and
`task_complete`.

Boundary:

- This proves the codex-self execution channel can run a real non-dry-run
  sub-agent call and record durable output.
- It does not yet prove `runtime_worker -> codex_self_mcp -> image extraction
  -> handoff-apply` for a fresh concept image. That remains the next worker
  close-out item at this point in the log; it is closed by the
  `2026-06-29 Fresh Codex-Self Concept Worker` entry below.

## 2026-06-29 Runtime Console Review Fix

Goal: respond to the user-facing frontend review issue where the console still
looked like an internal runtime/debug surface, with English/runtime fields and
file/path details too prominent in the default right panel.

Changes:

- `web/runtime_console/app.js`
  - default right status strip now shows only product-facing items:
    `阶段`, `下一步`, `预览`, and `资产`;
  - viewer and Blend toolbar links now stay disabled as `等待预览` /
    `等待工程` until the selected run actually has those outputs;
  - delivery panel no longer expands raw URLs, artifact ids, or local paths in
    the default product surface;
  - blend/delivery buttons are shown only when the underlying artifact or
    handoff evidence exists;
  - stage, next-action, preview, and asset summaries use Chinese user-facing
    labels instead of runtime job/file terminology.
- `web/runtime_console/index.html`
  - initial toolbar copy changed from active-looking open buttons to disabled
    loading-state labels.
- `web/runtime_console/polish.css`
  - sub-agent CSS pass tightened the creator-console shell, improved contrast,
    made the inspector quieter, and changed the asset checklist to a readable
    single-column layout.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
python - <<'PY'
from pathlib import Path
s=Path('web/runtime_console/polish.css').read_text()
assert s.count('{') == s.count('}')
assert 'a.disabled' in s
PY
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py -p no:cacheprovider
```

Results:

```text
app.js syntax passed
index.html parser passed
css sanity ok, 1612 lines
10 passed in 0.36s
```

Runtime checks:

```text
runtime console: http://10.2.16.106:8093/ running
GLB viewer: http://10.2.16.106:8092/ running
default API visual candidate: 20260629_scene_spec_assembly_non_dryrun
frontend_status.phase=BLENDER_PREVIEW
viewer_url present=true
file_manifest.missing_required=[]
```

Headless screenshot:

```text
/tmp/image23d_runtime_console_review.png
```

Note: Firefox `--screenshot` captures before the asynchronous `/api/runs`
selection finishes, so the screenshot is useful for static shell/readability
only. The API check above proves the loaded default candidate is the
SceneSpec-driven run with an exported viewer scene.

## 2026-06-29 Fresh Codex-Self Concept Worker

Goal: close the gap between completed-log/fake-worker tests and a freshly
submitted runtime-worker concept-image job:

```text
runtime console run
  -> bounded loop
  -> delegated generate_concept_images handoff
  -> runtime_worker backend=codex_self_mcp
  -> MCP image_generation event
  -> extracted PNG
  -> handoff-apply
  -> ConceptBundle / frontend_status / checkpoint
```

Implementation fixes:

- `agent_runtime/runtime_delegation.py`
  - concept handoff prompt now gives a bounded worker contract:
    generate exactly one image, call image generation once when available,
    let the parent runtime extract the last MCP image result, do not mutate
    state/logs, and return compact JSON;
  - embeds a structured snapshot of SceneSpec, reference images,
    reference-image bindings, final preview prompt, subject prompts, expected
    subject ids, and runtime job id.
- `agent_runtime/runtime_worker.py`
  - concept jobs now build codex-self call plans with `sandbox=read-only`;
  - creates `runtime_worker/` before invoking the external
    `/home/team/zouzhiyuan/codex-self-mcp/scripts/call_codex_mcp.py` helper,
    fixing the real helper failure where the log parent directory did not
    exist.
- Tests updated in `tests/test_runtime_delegation.py` and
  `tests/test_runtime_worker.py` to lock the prompt contract, reference-image
  context serialization, read-only concept worker sandbox, and pre-existing log
  directory.

Completed-log smoke:

```text
run=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_log_concept_smoke
backend=codex_self_log
worker_status=applied
state_phase=CONCEPT_REVIEW
frontend_phase=CONCEPT_REVIEW
artifact_id=subject_plush_codex_log_concept_001
audit_ok=true
```

First live attempt and bug evidence:

```text
run=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115619Z
backend=codex_self_mcp
worker_status=failed
issue=codex_self_mcp_call_failed
stderr=FileNotFoundError opening runtime_worker/<worker_id>_codex_self.jsonl
```

Fresh live success after the directory fix:

```text
run=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
backend=codex_self_mcp
worker_status=applied
apply_status=applied
state_phase=CONCEPT_REVIEW
frontend_phase=CONCEPT_REVIEW
artifact_id=job_01_concept_generation_generate_concept_images_worker_a6cacea6151b
checkpoint_id=ckpt_20260629_runtime_worker_codex_self_live_concept_20260629T115755Z_runtime_console_20260629T115936Z_4766c6a0cc
audit_ok=true
audit_error_count=0
audit_warning_count=0
```

Generated image evidence:

```text
runtime_worker/worker_a6cacea6151b_concept.png
artifacts/subject_concept_image/job_01_concept_generation_generate_concept_images_worker_a6cacea6151b.png
PNG image data, 1024 x 1536, 8-bit/color RGB, non-interlaced
artifact_size=2098688
```

The visual output is a yellow plush mascot in a flower-studio setting, matching
the bounded worker prompt.

Verification:

```bash
python -m py_compile agent_runtime/runtime_worker.py agent_runtime/runtime_delegation.py tests/test_runtime_worker.py tests/test_runtime_delegation.py
pytest -q tests/test_runtime_worker.py tests/test_runtime_delegation.py tests/test_codex_self_mcp.py -p no:cacheprovider
pytest -q tests/test_runtime_worker.py tests/test_runtime_delegation.py tests/test_codex_self_mcp.py tests/test_runtime_runs.py -p no:cacheprovider
pytest -q -p no:cacheprovider
```

Results:

```text
py_compile passed
23 passed in 0.87s
29 passed in 0.85s
293 passed in 1.95s
```

Boundary:

- This closes the fresh concept-image worker path through codex-self MCP.
- It does not yet prove textured Hunyuan3D subject generation from this new
  concept image, live HY-World scene generation, or a fresh concept-to-final
  Blender package run without reused 3D assets.

## 2026-06-29 Runtime Console And Subject-Asset Handoff Close-Out

Goal: address the user's console review and continue the real runtime chain
from the freshly generated concept image toward Hunyuan3D subject generation.

Frontend/runtime console changes:

- `web/runtime_console/index.html`
  - adds a concept-image preview element inside the main preview area;
  - versions `styles.css`, `polish.css`, and `app.js` URLs so browser refreshes
    do not keep stale UI assets.
- `web/runtime_console/app.js`
  - default run selection now prefers the newest run by `modified_at` instead
    of jumping to older visual runs;
  - when no `viewer_scene.glb` exists yet, the center preview shows the
    registered concept PNG from `state.artifacts` through the existing
    `/api/runs/<run_key>/file?path=...` endpoint;
  - translates more internal run names and keeps raw file paths under
    `开发详情`.
- `web/runtime_console/polish.css`
  - sub-agent visual pass tightened the console into a brighter four-column
    creator layout;
  - concept preview image is centered, contained, and no longer leaves the
    concept-review run as a blank 3D panel.

Directory-linkage fix:

- `agent_runtime/runtime_runs.py`
  - parent run `effective_run_dir` no longer auto-switches to ordinary
    workflow child directories such as `subject_asset_handoff_*`;
  - only visual/delivery child stages with `viewer_scene`, `scene_state`, or
    `delivery_handoff.json` can become the parent run's display surface.
- Regression coverage:
  `tests/test_runtime_runs.py::test_nonvisual_workflow_child_does_not_override_parent_run`.

Controller/handoff prompt fix:

- `agent_runtime/runtime_delegation.py`
  - `build_subject_asset` handoff prompts now include approved concept image
    artifact ids/URIs, subject specs, concept bundle ids, runtime execution
    summary, Hunyuan profile evidence, and hard boundaries:
    no direct state/log edits, no parallel artifact store, use existing
    `workflow_runner`/Hunyuan3D path, and return JSON suitable for
    handoff-apply.
- Regression coverage:
  `tests/test_runtime_delegation.py::test_runtime_delegation_subject_asset_prompt_includes_concept_artifact_and_profile`.

Runtime chain evidence:

```text
run=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
concept_artifact=job_01_concept_generation_generate_concept_images_worker_a6cacea6151b
concept_action=approve_concept
concept_checkpoint=ckpt_20260629_runtime_worker_codex_self_live_concept_20260629T115755Z_runtime_console_20260629T125120Z_c3785c350e
state_phase_after_approval=CONCEPT_APPROVED
first_runtime_job=build_subject_asset
profile=hq_textured_1m_768
handoff_id=handoff_4016b4726e01
handoff_prompt_has_concept_uri=true
handoff_prompt_has_hunyuan_profile=true
handoff_prompt_has_state_boundary=true
```

Live Hunyuan3D submit evidence:

```text
service=http://127.0.0.1:8091
health=200 {"status":"healthy","worker_id":"89945b"}
output_dir=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/subject_asset_handoff_8fdfad06d643
job_record=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/subject_asset_handoff_8fdfad06d643/live_hunyuan_job_record.json
asset_id=subject_plush_asset_hq_001
job_id=360a38c9-f8f9-44da-9a5c-ed19ece6a7a5
submit_stage=ok
profile=hq_textured_1m_768
texture=true
face_count=1000000
octree_resolution=768
num_inference_steps=50
```

Follow-up status evidence:

```text
2026-06-29T12:55:32Z status=processing
2026-06-29T12:57:54Z status=processing
2026-06-29T13:02:59Z status_request_timeout=30s
2026-06-29 20:59:20 Asia/Shanghai service_log=shape_generation_done_251s_texture_in_progress
```

The timeout is recorded as a service-poll boundary while the long textured
Hunyuan job is running; the submit itself succeeded and wrote
`summary.json`, `state.json`, `frontend_status.json`, `tool_call_log.json`, and
checkpoint records under the subject-asset output directory.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_runs.py tests/test_runtime_delegation.py -p no:cacheprovider
pytest -q tests/test_runtime_delegation.py tests/test_runtime_user_actions.py tests/test_runtime_runs.py -p no:cacheprovider
pytest -q -p no:cacheprovider
```

Results:

```text
node/html/CSS brace checks passed
15 passed in 0.55s
20 passed in 0.61s
295 passed in 2.80s
```

Boundary:

- The latest UI now shows the generated concept PNG before GLB export exists.
- The parent run state no longer gets hijacked by ordinary workflow child
  output directories.
- The high-quality textured Hunyuan job is submitted, but the GLB has not yet
  been saved, QAed, or handoff-applied back into the parent run.

## 2026-06-29 Runtime Console UI3 Product Pass And Live GLB Close-Out

Goal: respond to the user's front-end review by making the console read as a
creation workspace, not a debug page, while preserving the existing runtime API
and artifact paths.

UI3 front-end changes:

- `web/runtime_console/polish.css`
  - replaced the accumulated multi-pass overrides with one product-facing
    skin;
  - keeps the three-product-column layout plus narrow icon rail, but gives the
    center preview/composer the visual priority;
  - makes the right inspector a phase/asset/delivery acceptance panel by
    default, with runtime logs and file paths under the closed `开发详情`
    drawer;
  - adds vertical phase progress descriptions, concept thumbnails in the asset
    list, disabled delivery rows, and explicit pending/ready states.
- `web/runtime_console/app.js`
  - hides `system` chat messages from the product chat stream;
  - stops unknown task ids/job ids from becoming visible user-facing titles;
  - rewrites next-action copy away from runtime terminology and toward user
    creation actions;
  - always renders four delivery targets: 3D preview, GLB, Blend, and delivery
    package, with unavailable items disabled instead of disappearing;
  - maps unknown technical run names such as runtime/worker/handoff records to
    `生成任务记录` in the run list;
  - preserves raw ids, checkpoint paths, JSON/JSONL files, and paths only in
    the development details drawer.
- `web/runtime_console/index.html`
  - bumped static asset cache keys to `20260629-ui3`.

Live runtime state correction:

```text
run=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
phase=SUBJECT_ASSET_QA
concept_artifact=job_01_concept_generation_generate_concept_images_worker_a6cacea6151b
concept_approved=true
subject_asset=subject_plush_asset_hq_001
subject_glb=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/artifacts/subject_3d_asset/subject_plush_asset_hq_001.glb
subject_glb_size=30628780
deterministic_qa=pass score=1.0 glb_magic=glTF glb_version=2
parent_handoff_apply=handoff_apply_00bb8e90c771
parent_checkpoint=ckpt_20260629_runtime_worker_codex_self_live_concept_20260629T115755Z_runtime_console_20260629T131501Z_154a937db3
next_runtime_jobs=build_scene_asset, adapt_scene_asset
```

WorldMirror scene-asset boundary already started:

```text
scene_asset_output_dir=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/scene_asset_worldmirror_live
stages=runtime_status,prepare_generation
service=http://127.0.0.1:8081
prepare_generation=ok
long_running_submit=not yet submitted
```

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
python -m json.tool outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/subject_asset_handoff_8fdfad06d643/live_hunyuan_job_record.json
pytest -q tests/test_runtime_runs.py tests/test_runtime_delegation.py -p no:cacheprovider
curl -s http://127.0.0.1:8093/ | rg -n "ui3|阶段进度|开发详情"
curl -s http://127.0.0.1:8093/app.js?v=20260629-ui3 | rg -n "主体概念已经确认|下载交付包|生成任务记录"
firefox --headless --window-size=1600,1000 --screenshot run_logs/frontend_checks/runtime_console_ui3_1600x1000.png http://127.0.0.1:8093/
```

Results:

```text
frontend static checks ok
live_hunyuan_job_record.json json-ok
15 passed in 0.51s
ui3 static assets served by the runtime console
headless Firefox screenshot saved; it captures the initial loading state before
the async run-list fetch completes, so final browser review should be done in
the live page after refresh.
```

Current boundary:

- The front-end is now suitable for review at
  `http://10.2.16.106:8093/` after browser refresh.
- The fresh run has a real concept PNG and real Hunyuan textured GLB registered
  in parent state.
- The next V1 chain step is live WorldMirror upload/reconstruct/save, then
  handoff-apply, Blender assembly, viewer export, and final delivery.

## 2026-06-29 Runtime Console UI5 Review Fix

After user review of the runtime console screenshot, the console received a
focused product-facing pass:

- `web/runtime_console/index.html`
  - bumped static keys to `20260629-ui5` so browser refreshes load the current
    console code;
  - keeps chat/upload/preview/phase/asset/delivery on the main surface.
- `web/runtime_console/app.js`
  - adds a UI version reset for local run selection, so UI5 refreshes prefer the
    current live runtime run instead of a stale selected run;
  - prefers the current live run
    `20260629_runtime_worker_codex_self_live_concept_20260629T115755Z`;
  - hides development-only detail behind `?dev=1`;
  - stops unknown stage/status enum fallbacks from surfacing raw English in the
    user-facing panels;
  - shows shortened file details only in development mode.
- `web/runtime_console/polish.css`
  - hides the `开发详情` drawer unless `?dev=1` is present;
  - strengthens the stage timeline active/done states with visible labels;
  - improves empty preview contrast so it reads as a product state instead of a
    blank canvas.
- `tools/runtime_console_server.py`
  - adds PNG/JPEG/WebP/GLB MIME types for run files, fixing concept preview
    serving as `image/png` instead of `application/octet-stream`.

Live checks:

```text
runtime_console_pid=3217342
url=http://10.2.16.106:8093/
ui_version=20260629-ui5
cache_control=no-store
default_run=20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
default_phase=SUBJECT_ASSET_QA
subject_asset_ids=["subject_plush_asset_hq_001"]
concept_png_mime=image/png
```

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
python -m py_compile tools/runtime_console_server.py
pytest -q tests/test_runtime_runs.py tests/test_runtime_delegation.py tests/test_service_adapters.py -p no:cacheprovider
scripts/status_runtime_console.sh
```

Results:

```text
JS/HTML/Python checks passed.
37 passed in 0.54s.
Runtime console restarted and serving UI5 on port 8093.
Headless Firefox screenshot saved to
run_logs/frontend_checks/runtime_console_ui5_1600x1000.png, but Firefox captures
the initial loading frame before async run data finishes; API checks confirm the
live concept image and current run data are available.
```

## 2026-06-29 Runtime Console UI6 Creator-Desk Pass

Goal: respond to the latest user review that the console still looked like a
debug dashboard, with English/internal details visible and unclear phase
progress. This pass keeps the existing static runtime console/API and GLB viewer
reuse, but makes the default page reviewable as a creator workbench.

Implementation:

- `web/runtime_console/index.html`
  - bumped static assets to `20260629-ui6`;
  - added no-store meta hints;
  - tightened visible Chinese copy around preview, chat, upload, phase, assets,
    and delivery.
- `web/runtime_console/app.js`
  - bumped `UI_VERSION` to `20260629-ui6`, forcing stale local run selection to
    reset on refresh;
  - moved `BLENDER_EDIT` into the preview/review phase group instead of the
    assembly group;
  - hides long concept prompts behind `?dev=1`;
  - removes visible fallback to unknown internal enum/tool ids in user-facing
    labels;
  - adds root state classes such as `has-preview`, `has-concept-preview`,
    `needs-user-action`, `phase-*`, and stable asset/delivery classes for
    future visual work.
- `web/runtime_console/polish.css`
  - a sub-agent-owned visual-only pass made the page closer to a clean AI
    creation desk: white creator surface, denser left run list, clearer preview
    panel, chat/upload composer, right-side phase/asset/delivery cards, stronger
    contrast, and hidden developer details unless `?dev=1`;
  - added state-class styling for concept preview, viewer preview, user action,
    and complete asset states.

Live checks:

```text
runtime_console_pid=3821224
url=http://10.2.16.106:8093/
ui_version=20260629-ui6
default_run=20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
default_phase=SCENE_ASSET_ADAPTATION
concept_png_status=200
concept_png_mime=image/png
concept_png_size=2098688
concept_png_signature_ok=true
state_assets=subject:1, scene_asset:true, blender:false, viewer:false
```

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
python - <<'PY'
from pathlib import Path
css=Path('web/runtime_console/polish.css').read_text()
print('brace_balance', css.count('{')-css.count('}'))
PY
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py -p no:cacheprovider
./scripts/stop_runtime_console.sh && ./scripts/start_runtime_console.sh && ./scripts/status_runtime_console.sh
```

Results:

```text
JS/HTML checks passed.
CSS brace balance 0.
11 passed in 0.35s.
Runtime console restarted and serving UI6 on port 8093.
Firefox screenshot saved to
run_logs/frontend_checks/runtime_console_ui6_1600x1000.png; Firefox still
captures the initial loading frame before async run data finishes, but API
checks confirm the default browser-selected run, phase, and concept PNG are
available.
```

Current boundary:

- The frontend is ready for user refresh/review at `http://10.2.16.106:8093/`.
- The current live run has real concept PNG, subject GLB, and scene asset
  registered. The Blender/viewer close-out below completes the 3D preview for
  this same run.

## 2026-06-29 Live Blender Assembly And Viewer Close-Out

Goal: remove the "nothing visible" boundary for the current live run by using
the existing local E2E Blender path, not by creating another viewer or state
store.

Inputs:

```text
parent_run=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
scene_glb=/home/team/zouzhiyuan/image23D_Agent/HY-World-2.0/gradio_demo_output/input_images_20260629_214300_645346/scene_All_camTrue_meshTrue_edgesTrue_skyFalse.glb
subject_glb=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/artifacts/subject_3d_asset/subject_plush_asset_hq_001.glb
scene_spec_json=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live/scene_spec.json
blender=/home/team/zouzhiyuan/blender-4.2.0-linux-x64/blender
viewer_base_url=http://10.2.16.106:8092
```

Execution:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner local-e2e \
  --scene-glb "$scene_glb" \
  --asset-glb "$subject_glb" \
  --scene-spec-json "$scene_spec_json" \
  --output-dir "$parent_run/blender_scene_live" \
  --blender-path /home/team/zouzhiyuan/blender-4.2.0-linux-x64/blender \
  --viewer-base-url http://10.2.16.106:8092 \
  --compose-timeout 900 \
  --export-timeout 900 \
  --viewer-timeout 60 \
  --stages compose,export_viewer,viewer_check
```

Results:

```text
ok=true
phase=BLENDER_PREVIEW
blend=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live/compose/composed_scene.blend
preview_png=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live/compose/composed_preview.png
viewer_scene=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live/viewer_export/viewer_scene.glb
scene_state=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live/viewer_export/scene_state.json
viewer_url=http://10.2.16.106:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live/viewer_export/viewer_scene.glb
viewer_scene_object_count=7
viewer_asset_content_type=model/gltf-binary
viewer_asset_content_length=220281068
```

Parent run apply:

```text
apply_id=handoff_apply_7c98e56bc30e
checkpoint_id=ckpt_20260629_runtime_worker_codex_self_live_concept_20260629T115755Z_runtime_console_20260629T145213Z_f859e8fc83
applied_fields=artifacts, blender_scene, viewer_scene, phase
parent_phase=BLENDER_PREVIEW
frontend_status.phase=BLENDER_PREVIEW
```

Verification:

```text
runtime console API now reports:
run_has_viewer_scene=true
run_has_scene_state=true
viewer_url present=true
state_blender=true
state_viewer=true
GLB viewer asset status=200
GLB viewer asset MIME=model/gltf-binary
GLB magic=glTF
```

Notes:

- The front-end can now show the 3D preview for this run after refresh.
- The Blender preview image is nonblank and shows the yellow subject in the
  reconstructed scene.
- HY-World scene geometry quality is imperfect/fragmented; this is a model
  quality and generation-parameter issue to address in the next tuning pass, not
  a missing-file or viewer-link issue.

## 2026-06-29 Preview Gate And Delivery Preflight Fix

Goal: continue after the live Blender/viewer close-out without falsely marking
the run delivered before the user has approved the preview.

Findings:

- Parent state was correctly at `BLENDER_PREVIEW`, but
  `frontend_status.json` still inherited stale `concept_approval` stage/node
  from an older summary.
- The runtime console API selected `blender_scene_live` as the effective visual
  directory, which exposed child `viewer_check` status instead of the parent
  user gate.
- Delivery preflight package files were complete, but `delivery_handoff` was not
  ready because the handoff builder only accepted nested `metadata.viewer`
  fields while the parent handoff-apply artifact had flat `viewer_base_url`
  metadata.

Implementation:

- `agent_runtime/frontend_status.py`
  - now derives current user-gate stage/node from authoritative
    `AgentProjectState.phase` for `CONCEPT_REVIEW` and `BLENDER_PREVIEW`;
  - reports `needs_user_action`, `BlenderPreviewReviewGate`, and
    `Waiting for approve_blender_preview` for the current preview gate.
- `agent_runtime/delivery_handoff.py`
  - now accepts flat viewer metadata such as `viewer_base_url`, `asset_url`,
    `viewer_url`, `runtime_status`, and `model_check`;
  - uses existing `build_viewer_urls(...)` instead of inventing a URL format.
- `agent_runtime/runtime_runs.py`
  - separates parent control state from visual child artifacts: parent
    `state/frontend_status/runtime_plan` remain authoritative, while
    `viewer_scene.glb` and `scene_state.json` can still come from the best
    visual child directory.
- Tests added/updated in:
  - `tests/test_frontend_status.py`;
  - `tests/test_delivery_handoff.py`;
  - `tests/test_runtime_runs.py`.

Current live run repair:

```text
parent_run=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
phase=BLENDER_PREVIEW
frontend_status.status=needs_user_action
frontend_status.current_stage=blender_preview_approval
frontend_status.current_node=BlenderPreviewReviewGate
frontend_status.progress_label=Waiting for approve_blender_preview
runtime_plan.requires_user=true
viewer_url_present=true
delivery_handoff_ready=true
delivery_handoff_verified=true
```

Preflight package:

```text
zip=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/delivery_preflight/package/live_preview_delivery_preflight_20260629.zip
package_ok=true
issues=[]
has_blend_file=true
has_preview_render=true
has_viewer_scene=true
has_viewer_state=true
subject_asset_count=1
scene_asset_count=4
delivery_handoff_ready=true
delivery_handoff_verified=true
parent_phase_after_preflight=BLENDER_PREVIEW
```

Verification:

```bash
pytest -q tests/test_runtime_runs.py tests/test_runtime_console.py \
  tests/test_frontend_status.py tests/test_delivery_handoff.py \
  tests/test_delivery_package.py \
  tests/test_runtime_delegation.py::test_runtime_handoff_apply_registers_blender_outputs_and_waits_for_preview_approval \
  -p no:cacheprovider
python -m py_compile agent_runtime/runtime_runs.py agent_runtime/frontend_status.py agent_runtime/delivery_handoff.py
./scripts/stop_runtime_console.sh && ./scripts/start_runtime_console.sh
```

Results:

```text
22 passed in 0.45s.
Runtime console restarted on http://10.2.16.106:8093/.
API check confirms the parent run now reports the Blender preview user gate
while still exposing the child viewer GLB URL.
```

## 2026-06-29 Runtime Console UI7 Public/Dev Split

Goal: respond to the user-facing UI review: the console must look like a clean
creation workspace, not a debug dashboard with English runtime internals.

Implementation:

- Bumped the served runtime console assets from `ui6` to `ui7` to avoid browser
  cache showing the older `New / Open GLB / Build Plan / Status` UI.
- Rebuilt `web/runtime_console/polish.css` as a single creator-desk stylesheet
  instead of many stacked override passes.
- Simplified the public phase timeline to five product steps:
  `需求 -> 概念图 -> 3D 资产 -> 场景预览 -> 交付`.
- Added a persistent `待你确认` card:
  - concept review shows concept confirmation actions;
  - Blender preview shows preview approval / edit-feedback actions;
  - phases without a user gate say that no user action is currently required.
- Kept runtime internals (`statusList`, `jobList`, `fileList`, `objectList`,
  dry-run buttons, handoff controls, paths, and object ids) behind `?dev=1`.
- Kept the existing runtime API wiring intact: run list, chat, image upload,
  viewer URL, Blend URL, asset readiness, user actions, and delivery links still
  come from the existing runtime endpoints.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
pytest -q -p no:cacheprovider
./scripts/stop_runtime_console.sh && ./scripts/start_runtime_console.sh
```

Results:

```text
CSS brace delta: 0
16 passed in 0.37s
Runtime console restarted on http://10.2.16.106:8093/ with pid=428082
Served HTML contains ui7=true
Served HTML contains old strings Open GLB/Open Blend/Build Plan/Step Dry=false
Current live run phase=BLENDER_PREVIEW
Current live run status=needs_user_action
Current live run viewer_url_present=true
Current live run missing_required=[]
```

Manual visual evidence:

```text
Public-mode screenshot:
/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui7_public.png

Dev-mode screenshot:
/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui7_dev.png
```

Note: Firefox command-line screenshots capture the async page before runtime
data has finished loading, so the screenshot is useful for the initial shell and
old-string removal. The current live run data was verified through the runtime
API after restart.

## 2026-06-29 Formal Delivery Runtime Execution

Goal: close the gap between the Blender-preview approval gate and a formal
parent-run delivery package. Before this pass, `approve_blender_preview` moved
the state to `DELIVERY` and generated a `kind=delivery` job, but `/step` could
only execute LLM-node jobs and would block on delivery.

Implementation:

- `agent_runtime/controller.py`
  - now treats a valid `EXPORT_PACKAGE` artifact with `metadata.ok=true` and an
    existing zip file as delivery-complete;
  - prevents the `DELIVERY` phase from repeatedly creating new delivery jobs
    after a package has been created.
- `agent_runtime/runtime_execution.py`
  - now executes `kind=delivery` jobs with the existing
    `build_delivery_package(...)` path;
  - writes the updated parent `state.json`, `delivery_handoff.json`,
    `summary.json`, `frontend_status.json`, checkpoint, execution output JSON,
    and rebuilt `runtime_plan.json`;
  - keeps `dry_run=True` non-mutating for delivery readiness checks.
- `agent_runtime/runtime_runs.py`
  - now includes the formal delivery zip in the run `file_manifest` as
    `delivery_package`.
- `web/runtime_console/app.js`
  - after the user clicks `确认预览并交付`, the UI applies
    `approve_blender_preview` and then runs one non-dry-run delivery step;
  - this is still user-gated and does not run until the preview approval button
    is clicked.

Sub-agent audit:

- A read-only sub-agent independently confirmed the missing runtime seam:
  `approve_blender_preview -> DELIVERY plan` existed, but `/step` previously
  returned `unsupported_main_runtime_job_kind` for `kind=delivery`.

Tests added/expanded:

- `tests/test_controller.py`
  - delivery-complete controller stop when a valid export package exists.
- `tests/test_runtime_execution.py`
  - direct delivery job builds a formal package and rebuilds the plan;
  - preview approval followed by delivery step builds the formal package.
- `tests/test_runtime_loop.py`
  - bounded loop can execute delivery and stop at `completed_no_jobs`.
- `tests/test_runtime_runs.py`
  - runtime bundle/file manifest exposes the formal delivery zip.

Verification:

```bash
python -m py_compile agent_runtime/controller.py agent_runtime/runtime_execution.py agent_runtime/runtime_runs.py
node --check web/runtime_console/app.js
pytest -q tests/test_runtime_loop.py tests/test_runtime_runs.py tests/test_runtime_execution.py \
  tests/test_runtime_user_actions.py tests/test_controller.py tests/test_runtime_jobs.py \
  tests/test_delivery_package.py tests/test_delivery_handoff.py tests/test_runtime_console.py \
  tests/test_frontend_status.py -p no:cacheprovider
pytest -q -p no:cacheprovider
./scripts/stop_runtime_console.sh && ./scripts/start_runtime_console.sh
```

Results:

```text
Targeted runtime/UI/delivery suite: 51 passed in 0.63s
Full current test suite: 304 passed in 2.02s
Runtime console restarted on http://10.2.16.106:8093/ with pid=743998
Served HTML contains ui7=true
Served HTML old English debug strings=false
Current live run phase=BLENDER_PREVIEW
Current live run status=needs_user_action
Current live run node=BlenderPreviewReviewGate
Current live run viewer_url_present=true
Current live run missing_required=[]
Current live run delivery_package_ready=false
```

Important boundary:

- This implementation enables the formal post-approval delivery path.
- The current live run was not automatically approved or delivered during this
  pass; it remains at the Blender preview user gate until the user confirms the
  preview.

## 2026-06-30 Runtime Console UI8 User-Facing Correction

Goal: respond to the latest user review screenshot where the console still felt
like a debug/runtime page: old English controls, weak phase visibility, too many
internal run records, and exposed implementation terms.

Implementation:

- Bumped static assets from `ui7` to `ui8` in
  `web/runtime_console/index.html` and `web/runtime_console/app.js`, forcing the
  browser to drop the stale `Open GLB / Build Plan / Status` surface.
- Kept the existing static runtime console/API instead of introducing a parallel
  React/Ant Design/Open WebUI fork for this pass.
- Public run list now hides child-stage, smoke, audit, dry-run, and preflight
  records by default; `?dev=1` still shows the full runtime inventory.
- Public mode now avoids user-facing `GLB`, `Blend`, `runtime`, `job_id`,
  `checkpoint_id`, and path-style language where practical:
  - `主体 GLB` -> `主体模型`;
  - `Blend 工程` -> `工程文件`;
  - `下载 GLB` -> `下载 3D 模型`;
  - loading text uses `运行服务`, not `runtime`.
- The five-step phase timeline now reads as product stages:
  `需求绑定 -> 概念确认 -> 模型生成 -> 场景验收 -> 交付下载`.
- Each stage row now carries an explicit state chip (`已完成`, `当前阶段`,
  `待你确认`, `待开始`) instead of relying on faint color alone.
- Default public mode no longer renders the debug lists at all; `statusList`,
  `jobList`, `objectList`, and `fileList` are only populated in `?dev=1`.
- The empty preview area now looks like a product empty state and explains the
  next user-visible step without mentioning `viewer_scene.glb`.

Sub-agent note:

- A new sub-agent could not be spawned because the current thread had already
  reached the sub-agent concurrency limit.
- Existing completed sub-agent audits were reused. Their shared conclusion was
  to keep the public surface to a three-panel creator layout and move runtime
  internals behind `?dev=1`.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
python - <<'PY'
from pathlib import Path
text=Path('web/runtime_console/polish.css').read_text()
print('brace_balance', text.count('{')-text.count('}'))
print('ui8_index', '20260630-ui8' in Path('web/runtime_console/index.html').read_text())
print('ui8_app', '20260630-ui8' in Path('web/runtime_console/app.js').read_text())
PY
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
./scripts/stop_runtime_console.sh && ./scripts/start_runtime_console.sh
curl -s http://10.2.16.106:8093/ | rg -n "20260630-ui8|Open GLB|Build Plan|Status|Phase|Workflow|Tools|阶段进度"
curl -s http://10.2.16.106:8093/app.js | rg -n "20260630-ui8|下载 3D 模型|主体 GLB|Open GLB|Build Plan"
firefox --headless --window-size=1600,1000 --screenshot \
  /home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui8_public.png \
  'http://127.0.0.1:8093/?v=ui8-check'
```

Results:

```text
brace_balance 0
ui8_index True
ui8_app True
17 passed in 0.40s
304 passed in 1.98s
Runtime console restarted on http://10.2.16.106:8093/ with pid=921562
Served HTML contains ui8=true
Served app.js contains old visible English debug strings=false
Served HTML contains old visible English debug labels=false
Note: raw DOM id runStatusStrip still contains "Status"; it is not visible UI text.
Served app.js contains ui8=true
Served app.js contains "下载 3D 模型"=true
Served app.js contains old "主体 GLB/Open GLB/Build Plan" strings=false
Runtime API /api/runs returned 35 records.
```

Visual evidence:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui8_public.png
```

Note: Firefox command-line screenshot still captures before all async run data
finishes loading. It is useful for checking the shell, color, spacing, resource
version, and old-string removal; runtime data loading was verified through the
console API.

## 2026-06-30 Runtime Console UI9 Creation-Workbench Correction

Goal: respond to the follow-up user screenshot where the public console still
felt like a debug dashboard: the right side was visually noisy, stage progress
was not the main story, and uploaded references/assets were not connected.

Implementation:

- Bumped static assets from `ui8` to `ui9` in
  `web/runtime_console/index.html` and `web/runtime_console/app.js`.
- Kept the existing static console, runtime API, and GLB viewer; no parallel
  frontend framework or duplicate viewer/runtime was introduced.
- Spawned a read-only UI sub-agent. Its audit confirmed the smallest useful
  fix is information architecture: public mode should show only phase/user
  gate, asset chain, delivery, chat/upload, and preview; runtime internals stay
  behind `?dev=1`.
- Public mode now hides the compact debug status strip together with the
  existing developer details panel. The right column is reduced to:
  `阶段进度`, `资产清单`, and `交付`.
- Upload chips now surface reference-image binding state:
  `用途待说明`, `主体参考`, `场景参考`, `风格参考`, `姿态参考`, `材质参考`, or
  `布局参考`, using existing `InputImage` / `ReferenceBinding` state.
- The asset panel now reads as a chain:
  `参考图 -> 概念图 -> 主体模型 -> 场景资产 -> 工程文件 -> 网页预览`.
  It highlights unbound reference images instead of silently treating any
  upload as ready.
- `polish.css` adds a final `ui9` public-workbench pass with stronger contrast,
  clearer active-stage treatment, numbered asset steps, and delivery-ready
  state styling.

Verification:

```bash
node --check web/runtime_console/app.js
curl -s http://10.2.16.106:8093/ | rg -n "20260630-ui9|20260630-ui8|Open GLB|Open Blend|Build Plan|Step Dry|Status|Phase|Workflow|Tools|阶段进度|资产清单|开发详情"
curl -s http://10.2.16.106:8093/app.js | rg -n "20260630-ui9|20260630-ui8|Open GLB|Open Blend|Build Plan|Step Dry|Status|Phase|Workflow|Tools|用途待说明|主体参考"
curl -s http://10.2.16.106:8093/polish.css | rg -n "ui9|run-status-strip|asset-step"
python -m py_compile tools/runtime_console_server.py agent_runtime/runtime_console.py agent_runtime/runtime_runs.py agent_runtime/frontend_status.py
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
firefox --headless --screenshot \
  /home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui9_public.png \
  --window-size 1600,1000 'http://10.2.16.106:8093/?v=ui9'
python - <<'PY'
import json, urllib.request
base='http://10.2.16.106:8093'
runs=json.load(urllib.request.urlopen(base+'/api/runs'))
key=runs[0]['run_key']
bundle=json.load(urllib.request.urlopen(base+'/api/runs/'+key))
print('runs', len(runs), 'first', runs[0]['display_name'], 'has_viewer', runs[0]['has_viewer_scene'])
print('phase', bundle.get('frontend_status',{}).get('phase'))
print('status', bundle.get('frontend_status',{}).get('status'))
print('viewer_url', bundle.get('web_surface',{}).get('viewer_scene_url'))
print('effective', bundle.get('effective_run_dir'))
print('uploads_endpoint', len(json.load(urllib.request.urlopen(base+'/api/runs/'+key+'/uploads'))))
PY
```

Results:

```text
node --check passed
Served HTML contains ui9=true and ui8=false.
Old visible strings Open GLB/Open Blend/Build Plan/Step Dry absent from served HTML/app.js.
Raw app.js still contains internal STATUS_LABELS/renderStatus function names, not public English UI.
17 passed in 0.40s
runs 35 first 20260629_runtime_worker_codex_self_live_concept_20260629T115755Z has_viewer True
phase BLENDER_PREVIEW
status needs_user_action
viewer_url present
effective /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live
uploads_endpoint 0
```

Visual evidence:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui9_public.png
```

Boundary:

- The Firefox CLI screenshot still captures before async run data finishes
  loading, so it verifies shell/layout/contrast rather than final hydrated run
  content.
- Hydrated run content was verified through the runtime API. The current live
  run remains at `BLENDER_PREVIEW / needs_user_action`; it was not approved or
  delivered during this UI pass.

## 2026-06-30 Blender Edit Router Planned Tool Bridge

Goal: continue the V1 runtime/control-plane plan after the UI pass by closing
the smallest high-value agent-runtime gap: natural-language Blender preview
feedback should be able to become concrete safe Blender edit domain-tool calls,
not only a routing note.

Implementation:

- `BlenderEditRouterOutput` already carried `domain_tool_calls`; this pass
  added focused verification that the field is wired end to end.
- `runtime_state_apply` now has verified coverage for applying a
  `BlenderEditRouter` candidate with `domain_tool_calls`. It validates the
  tools against the `BLENDER_EDIT` allowlist and stores the planned call list
  under `ReviewPatch.structured_delta["blender_edit_plan"]`.
- `controller` now has verified coverage for detecting pending
  `blender_edit_plan` patches and scheduling planned edit tools such as
  `move_subject` before `export_viewer_scene` and `render_preview`, without
  repeating `BlenderEditRouter`.
- `runtime_execution` now has verified coverage for dry-running a planned
  Blender edit domain tool through
  `build_safe_blender_mcp_operation_plan(...)`, recording the constrained raw
  MCP plan without live Blender mutation.
- `agent_runtime/prompt_catalog.py` sample context for `BlenderEditRouter` now
  uses real V1 edit tool names and object ids, and
  `docs/agent_prompt_catalog.md` was regenerated. The catalog now exposes
  `BlenderEditDomainToolCall` and `domain_tool_calls` in the output schema.
- The stale routing-only comment in `runtime_state_apply` was corrected so it
  no longer says the schema lacks concrete tool arguments.

Tests added/expanded:

- `tests/test_runtime_state_apply.py`
  - `BlenderEditRouter` output with an `update_camera` call stores
    `blender_edit_plan` in the pending `ReviewPatch`.
- `tests/test_controller.py`
  - a pending `blender_edit_plan` schedules
    `move_subject -> export_viewer_scene -> render_preview`.
- `tests/test_runtime_execution.py`
  - a dry-run planned `move_subject` job records the safe Blender MCP
    `execute_blender_code` operation plan and fixed Python template.

Verification:

```bash
python -m py_compile \
  agent_runtime/agent_prompts.py agent_runtime/prompt_catalog.py \
  agent_runtime/runtime_state_apply.py agent_runtime/controller.py \
  agent_runtime/runtime_execution.py agent_runtime/runtime_jobs.py

python -m agent_runtime.prompt_catalog --write docs/agent_prompt_catalog.md

pytest -q \
  tests/test_agent_prompts.py tests/test_prompt_catalog.py \
  tests/test_runtime_state_apply.py tests/test_controller.py \
  tests/test_runtime_execution.py tests/test_runtime_jobs.py \
  tests/test_blender_mcp.py -p no:cacheprovider
```

Results:

```text
py_compile passed
docs/agent_prompt_catalog.md contains BlenderEditDomainToolCall and domain_tool_calls
45 passed in 0.57s
Full current suite: 310 passed in 2.14s
```

Boundary:

- This is a dry-run-safe control-plane bridge. It proves the runtime can carry
  planned Blender edit tools from agent output into a safe raw MCP operation
  plan.
- It does not yet prove a live LLM-generated BlenderEditRouter output, nor a
  non-dry-run Blender MCP edit followed by real viewer/state refresh.

## 2026-06-30 Runtime Execution For Explicit Blender Edit Raw Caller

Goal: move the Blender edit loop one step beyond dry-run planning. The runtime
console step layer should be able to execute a planned Blender edit domain tool
when, and only when, an explicit raw MCP caller boundary is provided.

Implementation:

- `execute_next_runtime_job(...)` now accepts:
  - `blender_raw_tool_caller`: Python-injected raw caller for tests or explicit
    embedding;
  - `blender_raw_caller_source`: currently supports `"blender-lab-socket"` for
    the existing local Blender Lab socket bridge.
- The runtime console `/api/runs/<run_key>/step` payload now forwards
  `blender_raw_caller_source`. Public/default console use still sends dry-run
  steps unless the caller explicitly changes the request payload.
- Non-dry-run `BLENDER_EDIT` domain-tool execution still blocks if no explicit
  raw caller is present. This preserves the existing safety boundary.
- When a raw caller is present, runtime execution reuses
  `BlenderMCPDomainToolDispatcher` instead of adding a parallel MCP executor.
  The dispatcher executes the constrained raw MCP plan, then reads
  `get_objects_summary` back to resynchronize `BlenderSceneState`.
- Successful execution writes:
  - parent `state.json`;
  - checkpoint under `checkpoints/`;
  - `summary.json` with `latest_blender_edit_execution`;
  - refreshed `frontend_status.json`;
  - per-execution JSON under `runtime_execution/`;
  - `runtime_execution_summary.json`.
- Runtime execution intentionally does not rebuild `runtime_plan.json` after an
  edit tool succeeds. The current plan already contains
  `edit tool -> export_viewer_scene -> render_preview`, and the completed
  execution record lets the runtime continue to the next viewer-refresh job
  without re-queuing the same pending edit patch.

Tests added/expanded:

- `tests/test_runtime_execution.py`
  - non-dry-run planned Blender edit blocks without an explicit raw caller;
  - injected raw caller executes `move_subject`, calls
    `execute_blender_code -> get_objects_summary`, updates state/tool log,
    writes checkpoint/summary/frontend status, and leaves the next viewer
    refresh jobs pending.

Verification:

```bash
python -m py_compile \
  agent_runtime/runtime_execution.py tools/runtime_console_server.py \
  tests/test_runtime_execution.py

pytest -q \
  tests/test_runtime_execution.py tests/test_domain_dispatcher.py \
  tests/test_workflow_runner.py::test_blender_edit_workflow_executes_injected_raw_caller_and_syncs_scene \
  tests/test_runtime_jobs.py tests/test_controller.py -p no:cacheprovider
```

Results:

```text
py_compile passed
56 passed in 0.55s
Full current suite: 312 passed in 2.02s
```

Boundary:

- This proves non-dry-run runtime execution with an injected fake raw caller,
  state writeback, and continuation to viewer-refresh jobs.
- It does not yet execute a real `blender-lab-socket` edit from the runtime
  console, and it does not yet prove post-edit viewer export/render refresh in
  one live loop.

## 2026-06-30 Runtime Console UI10 Product Review Pass

Goal: respond to the user-facing screenshot review. The default console should
look like a creation workspace, not a debug/status dump, and it should default
to a run that can actually show the current scene/model when one exists.

Implementation:

- Bumped static assets to `20260630-ui10`, which also clears the old local
  selected-run cache.
- Public run sorting now strongly prioritizes `has_viewer_scene` and
  `has_scene_state` before generic status-only runs, so the current live
  `20260629_runtime_worker_codex_self_live_concept_20260629T115755Z` run is the
  default public selection.
- Low-value smoke/audit/dry-run records stay filtered in public mode; the
  hidden-count note now says only that low-value records were filtered, not
  that there are "internal" records.
- Viewer and Blend toolbar actions are hidden until a real viewer/concept or
  Blender URL exists. This avoids the old disabled `等待预览` / `等待工程` button
  clutter.
- When a viewer URL exists, the preview panel now shows `正在载入 3D 场景` until
  the iframe load event fires, instead of briefly looking like an empty scene.
- `dev-only`/`开发详情` remains available only under `?dev=1`; public mode keeps
  the right rail to `阶段进度`, `资产清单`, and `交付`.
- Added a stronger `ui10` CSS layer for the product workspace: higher contrast,
  clearer three-column hierarchy, muted grey viewer canvas, compact stage cards,
  and asset-chain status rows.
- A read-only UI sub-agent reviewed the current console and confirmed the same
  direction: hide raw runtime/path/node details in public mode, preserve the
  three-column creation layout, show five user-facing stages, and avoid a
  framework rewrite for this incremental pass.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
scripts/status_runtime_console.sh
curl -s http://127.0.0.1:8093/ | rg -n "20260630-ui10|Open GLB|Build Plan|Status|Phase|Workflow|Tools|阶段进度|资产清单|开发详情"
curl -s http://127.0.0.1:8093/app.js | rg -n "20260630-ui10|已筛选|正在载入 3D 场景|真实链路场景验收"
firefox --headless --window-size 1876,1310 --screenshot \
  /home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui10_public_initial_fixed.png \
  "http://127.0.0.1:8093/?v=ui10-fixed"
```

Results:

```text
node --check passed
html parser passed
17 passed in 0.39s
full current suite: 312 passed in 2.05s
runtime console running on http://10.2.16.106:8093/
served HTML references 20260630-ui10
served app.js references 20260630-ui10 and the new loading/run-title strings
default public-score selection:
  best_run=20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
  has_viewer_scene=True
  viewer_url_present=True
  phase=BLENDER_PREVIEW
  status=needs_user_action
screenshot artifact:
  /home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui10_public_initial_fixed.png
```

Boundary:

- Firefox CLI screenshots capture the initial static page before async run data
  fully renders, so the screenshot is useful for shell/layout and hidden-button
  checks, not as final proof of iframe rendering.
- No live generation, non-dry-run Blender edit, or new frontend framework was
  introduced in this pass.

## 2026-06-30 Runtime Console UI11 Public Review Fix

Goal: address the user's second frontend review screenshot. The public console
must not look like an English debug panel, must show the user-facing V1 stages,
and must reliably serve the current assets instead of stale browser resources.

Implementation:

- Bumped static assets to `20260630-ui11`.
- Renamed the surface to `image23D 创作台` and kept the page in a three-pane
  creator layout: left creation records, center 3D/concept preview plus
  chat/reference upload, right `阶段进度` / `资产清单` / `交付`.
- Added a stronger `ui11` CSS layer with higher contrast, clearer vertical
  stage cards, product-like panel spacing, and hidden public debug surfaces.
- Added base CSS guards so `[hidden]` and `.dev-only` remain hidden even if the
  polish skin is missing or stale.
- Updated default-run selection so a saved local selection is overridden when a
  clearly better viewer-ready run exists.
- Updated `tools/runtime_console_server.py` to send
  `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`,
  `Pragma: no-cache`, and `Expires: 0` for static/API responses.
- Restarted the runtime console on `8093` so the new cache headers and current
  assets are live.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
python -m py_compile tools/runtime_console_server.py
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
scripts/stop_runtime_console.sh
scripts/start_runtime_console.sh
scripts/status_runtime_console.sh
curl -s -D - "http://127.0.0.1:8093/?v=ui11-review" -o /tmp/runtime_console_ui11.html
curl -s -D - "http://127.0.0.1:8093/app.js?v=20260630-ui11" -o /tmp/runtime_console_ui11_app.js
firefox --headless --window-size 1876,1306 \
  --screenshot=/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui11_public.png \
  "http://127.0.0.1:8093/?v=ui11-review"
```

Results:

```text
node --check passed
html parser passed
py_compile passed
17 passed in 0.39s
runtime console running on http://10.2.16.106:8093/ pid=2664779
served HTML references 20260630-ui11
served app.js references UI_VERSION=20260630-ui11
served responses include no-store/no-cache/Pragma/Expires headers
top API run:
  20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
  has_viewer_scene=True
  has_scene_state=True
  phase=BLENDER_PREVIEW
  status=needs_user_action
  viewer_scene_url_present=True
screenshot artifact:
  /home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui11_public.png
```

Boundary:

- Firefox CLI still captures before async run data finishes rendering, so the
  screenshot proves shell/layout/debug hiding, while API evidence proves the
  default selected run has a live viewer URL.
- Public mode still uses the existing static HTML/CSS/JS runtime console rather
  than introducing a new framework. A framework migration remains a separate
  product decision.

## 2026-06-30 Runtime Loop Blender Edit Refresh Bridge

Goal: close the file/runtime control-plane gap after the `BLENDER_PREVIEW`
feedback gate. A user/requested Blender edit must be able to run through the
bounded runtime loop, refresh the viewer export and preview render, write
state/checkpoint/frontend status evidence, and stop at the next user preview
gate.

Implementation:

- `run_bounded_runtime_loop(...)` now accepts and forwards
  `blender_raw_tool_caller` and `blender_raw_caller_source` to
  `execute_next_runtime_job(...)`.
- Runtime console `/api/runs/<run>/loop` now forwards
  `blender_raw_caller_source` from the request payload, so the HTTP control
  layer can explicitly select `blender-lab-socket` for live approved runs.
- Runtime execution now routes `export_viewer_scene` and `render_preview`
  through the script-backed domain-tool dispatcher before the generic
  BLENDER_EDIT MCP dispatcher.
- Blender MCP scene sync now preserves the existing `blend_file_artifact_id`
  and `preview_image_id` when refreshing object summaries. Without this,
  a successful edit could drop the `.blend` artifact link and make the next
  `export_viewer_scene` fail with a missing input file.
- Added a loop-level regression test that starts from a pending
  `ReviewPatch.blender_edit_plan`, executes an injected raw Blender edit,
  runs fake script-backed `export_viewer_scene` and `render_preview`, writes
  viewer/preview artifacts, rebuilds the runtime plan, and stops at the
  `BLENDER_PREVIEW` user gate.

Verification:

```bash
python -m py_compile agent_runtime/domain_dispatcher.py agent_runtime/runtime_execution.py agent_runtime/runtime_loop.py tools/runtime_console_server.py tests/test_runtime_loop.py
pytest -q tests/test_runtime_loop.py::test_runtime_loop_live_blender_edit_refreshes_viewer_and_stops_at_preview_gate -p no:cacheprovider
pytest -q tests/test_runtime_execution.py tests/test_runtime_loop.py tests/test_runtime_jobs.py tests/test_controller.py tests/test_domain_dispatcher.py tests/test_workflow_runner.py::test_blender_edit_workflow_executes_injected_raw_caller_and_syncs_scene -p no:cacheprovider
```

Results:

```text
py_compile passed
loop edit-refresh test: 1 passed in 0.35s
targeted runtime/controller/domain suite: 62 passed in 0.59s
```

Boundary:

- The new test uses an injected raw Blender caller and fake script dispatcher;
  it proves the runtime/controller/state/file chain, not a live
  `blender-lab-socket` operation.
- A small approved live socket edit on a scratch/current run is still required
  before marking the real autonomous edit loop complete.

## 2026-06-30 Live Blender Socket Edit Refresh Scratch

Goal: run the newly wired edit-refresh control path against the real
`blender-lab-socket` bridge on a scratch run, without mutating the current live
preview run.

Scratch run:

```text
outputs/runs/20260630_blender_socket_edit_refresh_scratch_20260630T025222/
```

Implementation/evidence:

- Copied the current live visual run
  `20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live`
  into the scratch run and rewrote absolute JSON paths to the scratch location.
- Applied the runtime user action:
  `request_blender_changes("scratch 验证：把预览相机稍微拉近一点，保持主体和场景居中。")`.
- Loaded the scratch `compose/composed_scene.blend` into the running Blender
  Lab socket process.
- Ran `run_bounded_runtime_loop(..., dry_run=False,
  blender_raw_caller_source="blender-lab-socket")` with a fixture
  `BlenderEditRouter` response that planned `update_camera` for
  `Preview_Camera`.
- The loop executed:

```text
BlenderEditRouter
  -> update_camera via blender-lab-socket
  -> save scratch composed_scene.blend
  -> export_viewer_scene
  -> render_preview
  -> BLENDER_PREVIEW user gate
```

Key results:

```text
runtime_loop_summary.stop_reason = waiting_user
runtime_loop_summary.completed_iterations = 4
frontend_status.phase = BLENDER_PREVIEW
frontend_status.status = needs_user_action
runtime_plan.requires_user = true
delivery_handoff.ready = true
delivery_handoff.verified = false
viewer GLB HEAD via 8092 = HTTP 200, Content-Length 220281068
update_camera raw_caller_source = blender-lab-socket
update_camera raw_call_count = 3
update_camera saved_blend_path =
  outputs/runs/20260630_blender_socket_edit_refresh_scratch_20260630T025222/compose/composed_scene.blend
```

Generated files:

```text
compose/composed_scene.blend
viewer_export/viewer_scene.glb
viewer_export/scene_state.json
preview_render/preview.png
preview_render/preview.blend
runtime_user_action.jsonl
runtime_execution.jsonl
runtime_loop.jsonl
frontend_status.json
delivery_handoff.json
```

Verification commands:

```bash
scripts/status_blender51_lab_mcp_bridge.sh
python -m py_compile agent_runtime/domain_dispatcher.py agent_runtime/runtime_execution.py agent_runtime/runtime_loop.py tools/runtime_console_server.py tests/test_runtime_loop.py
pytest -q tests/test_domain_dispatcher.py tests/test_runtime_execution.py tests/test_runtime_loop.py tests/test_runtime_jobs.py tests/test_controller.py tests/test_workflow_runner.py::test_blender_edit_workflow_executes_injected_raw_caller_and_syncs_scene -p no:cacheprovider
curl -sI "http://10.2.16.106:8092/asset?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_blender_socket_edit_refresh_scratch_20260630T025222/viewer_export/viewer_scene.glb"
```

Results:

```text
Blender Lab MCP bridge socket: open on 127.0.0.1:9876
targeted runtime/controller/domain suite: 62 passed in 0.74s
full current suite: 315 passed in 2.47s
viewer GLB asset endpoint: 200 OK
```

Boundary:

- This is a real socket-backed Blender edit on a scratch copy, not the current
  user-facing parent run.
- The router response was fixture-backed through the same validated
  `BlenderEditRouter` parsing/apply path; a live Qwen/DeepSeek router call is
  still needed.
- The handoff is `ready=true` but `verified=false` because runtime script
  metadata currently writes URLs but does not yet persist viewer runtime/model
  check results into the new viewer artifact metadata.

## 2026-06-30 Runtime Console UI13 Public Review Fix

Goal: address the user's front-end review that the public runtime console still
looked like an English/debug panel and sometimes appeared blank before async run
data hydrated.

Implementation:

- Bumped static assets to `20260630-ui13`.
- Kept the existing static `web/runtime_console/` console and existing 8092
  GLB viewer; no parallel React/Ant/OpenWebUI app was introduced in this pass.
- Added a center workflow ribbon above the preview:
  `当前阶段 / 下一步 / 预览 / 资产`, all derived from the existing
  `frontend_status`, `runtime_plan`, and `file_manifest` state surfaces.
- Reworked the public empty/loading preview state so initial screenshots show a
  clear "正在读取创作" 3D card instead of a blank canvas.
- Added a viewer-loading fallback so a generated viewer URL does not leave an
  indefinite overlay if the iframe load event is delayed.
- Added public `composerNotice` feedback for missing edit instructions or
  confirmation errors, instead of writing those errors only into the hidden
  `?dev=1` job list.
- Changed public run-list filtering copy from "低价值记录" to "测试/历史记录",
  and added a public-name fallback so unknown debug-ish run ids containing
  `llm/qwen/deepseek/mcp/runtime/worker/smoke/audit/dryrun/handoff` show as
  `生成任务记录` outside `?dev=1`.
- Replaced remaining public "网页预览导出" wording with `3D 预览` / `生成 3D 预览`.
- Added a final tail CSS override layer because older ui skins remained later
  in `polish.css` and were overriding the first ui12 pass.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
pytest -q -p no:cacheprovider
curl -s "http://127.0.0.1:8093/?v=ui13-check" | rg -n "20260630-ui13|Open GLB|Build Plan|Step Dry|empty-stack"
curl -sI "http://127.0.0.1:8092/asset?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/blender_scene_live/viewer_export/viewer_scene.glb"
firefox --headless --window-size=1876,1306 --screenshot=/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui13_public_initial.png "http://127.0.0.1:8093/?v=ui13-check"
```

Results:

```text
node --check passed
html parser passed
targeted runtime-console/status suite: 17 passed in 0.38s
full current suite: 315 passed in 2.08s
served HTML/app/CSS use 20260630-ui13 and no ui12 resource version
served old visible strings Open GLB / Build Plan / Step Dry absent
public default run by UI score:
  20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
  has_viewer_scene=True
  phase=BLENDER_PREVIEW
  status=needs_user_action
  viewer_url_present=True
GLB viewer asset endpoint: 200 OK, Content-Length 220281068
runtime console: http://10.2.16.106:8093/
```

Visual evidence:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui13_public_initial.png
```

Boundary:

- Firefox CLI screenshots still capture the initial non-hydrated page, so the
  screenshot verifies shell/layout/empty-state behavior. Hydrated default-run
  and viewer availability were verified through the runtime API and 8092 HEAD
  checks.
- The UI is now a cleaner public review surface, but it is still the existing
  thin static console, not a full framework migration.

## 2026-06-30 Runtime Viewer Metadata For Refreshed Handoff

Goal: close the file/runtime verification gap discovered in the live
`blender-lab-socket` scratch edit-refresh run. The refreshed viewer GLB had
URLs and a complete file chain, but `delivery_handoff.verified=false` because
the runtime script export path wrote only viewer URLs, not viewer runtime/model
check metadata.

Implementation:

- Reused the existing `agent_runtime.viewer_runtime.ViewerRuntimeAdapter`.
- Updated `agent_runtime/runtime_execution.py` so script-backed
  `export_viewer_scene` artifact metadata now includes:
  - `runtime_status` from the existing 8092 viewer service;
  - `model_check` from the existing viewer asset/viewer HEAD checks;
  - a combined `model_check.ok` that requires both model and runtime checks.
- Left `delivery_handoff.py` semantics unchanged: it already treats
  `runtime_status.ok=true` and `model_check.ok=true` as the verification gate.
- Added a targeted runtime-execution test that monkeypatches the viewer adapter,
  proves the refreshed viewer GLB artifact carries the check metadata, and
  proves the resulting `delivery_handoff.json` has
  `verified=true`, `viewer_runtime_ok=true`, and `viewer_model_ok=true`.

Verification:

```bash
python -m py_compile agent_runtime/runtime_execution.py tests/test_runtime_execution.py
pytest -q tests/test_runtime_execution.py::test_runtime_execution_live_viewer_refresh_and_preview_rebuilds_plan tests/test_delivery_handoff.py tests/test_viewer_runtime.py -p no:cacheprovider
pytest -q tests/test_runtime_execution.py tests/test_runtime_loop.py tests/test_delivery_handoff.py tests/test_viewer_runtime.py tests/test_delivery_package.py -p no:cacheprovider
pytest -q -p no:cacheprovider
```

Results:

```text
targeted viewer/handoff metadata suite: 10 passed in 0.42s
runtime/delivery/viewer suite: 29 passed in 0.76s
full current suite: 315 passed in 2.51s
```

Live viewer check on the scratch run, without mutating the run files:

```text
run_dir = /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_blender_socket_edit_refresh_scratch_20260630T025222
viewer_artifact_id = runtime_exec_ce1b35ff8e0b_viewer_scene_glb
viewer_path = /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_blender_socket_edit_refresh_scratch_20260630T025222/viewer_export/viewer_scene.glb
runtime_ok = True
model_ok = True
asset_status = 200
asset_content_length = 220281068
viewer_status = 200
handoff_ready = True
handoff_verified = True
handoff_issues = []
```

Boundary:

- This fixes future runtime script-backed viewer refresh metadata. Existing
  already-written runs are not rewritten automatically.
- The live check above was in-memory evidence against the existing scratch GLB
  and 8092 viewer, not a new Blender generation.

## 2026-06-30 Runtime Console UI14 Public Workbench Pass

Goal: respond to the product-review issue that the public console still looked
like a debug/status dump, selected an empty run too easily, and exposed raw
English runtime wording in the right panel.

Implementation:

- Kept the existing dependency-free static console under
  `web/runtime_console/`; no new front-end framework or parallel API layer was
  introduced.
- Rebuilt `web/runtime_console/polish.css` as a single final public skin instead
  of many stacked historical override layers.
- Bumped the static version to `20260630-ui14` in `index.html` and `app.js` so
  browsers drop the stale UI cache.
- Updated public default-run selection: when a cached run has no scene preview
  but a viewer-ready run exists, public mode now selects the viewer-ready run.
- Added a right-side asset gallery fed from existing `state.artifacts`,
  `viewer_scene`, `.blend`, and subject-asset state. It shows public asset
  cards without exposing file paths.
- Kept raw status lists, runtime jobs, files, object internals, and debug action
  buttons behind `?dev=1`.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
pytest -q -p no:cacheprovider
scripts/status_runtime_console.sh
curl -s "http://127.0.0.1:8093/?v=ui14-check" | rg -n "20260630-ui14|Open GLB|Open Blend|Build Plan|Step Dry|STATUS|Phase|Workflow|Tools|资产|创作阶段"
curl -s "http://127.0.0.1:8093/polish.css?v=20260630-ui14" | rg -n "ui13|ui12|Open GLB|Build Plan|Step Dry|STATUS|Workflow|Tools"
```

Results:

```text
runtime console/status suite: 17 passed in 0.41s
full current suite: 315 passed in 2.22s
runtime console pid=3633300, URL=http://10.2.16.106:8093/
served HTML/app/css use ui14; old Open GLB/Open Blend/Build Plan/Step Dry public strings absent
served CSS line count=1392, old stacked ui12/ui13 tails absent
default public run by UI score:
  20260629_runtime_worker_codex_self_live_concept_20260629T115755Z
  has_viewer_scene=True
  is_stage=False
  frontend_status.phase=BLENDER_PREVIEW
  frontend_status.status=needs_user_action
```

Visual evidence:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui14_public.png
/home/team/zouzhiyuan/image23D_Agent/outputs/ui_checks/runtime_console_ui14_public_wait.png
```

Boundary:

- Firefox CLI screenshots still capture the non-hydrated shell too early, so
  the screenshots are only layout/initial-state evidence. Hydrated run
  selection and viewer availability were verified through the runtime API and
  served static checks.
- This is a public-console UI correction, not completion of the remaining live
  `BlenderEditRouter` provider call or object-level edit-sync work.

## 2026-06-30 BlenderEditRouter Feedback-To-Refresh Loop Coverage

Goal: close the test/evidence gap between two previously separate slices:
`request_blender_changes -> BLENDER_EDIT/BlenderEditRouter` and
`pre-existing blender_edit_plan -> edit/export/render -> BLENDER_PREVIEW`.
The product flow needs one loop that starts with natural-language preview
feedback and ends with a refreshed viewer gate.

Implementation:

- Extended `run_bounded_runtime_loop(...)` to pass optional `provider_configs`
  and `env` through to `execute_next_runtime_job(...)`. This keeps the direct
  path open for future Qwen/DeepSeek router calls while preserving the existing
  `response_text_by_node` fixture seam.
- Added
  `test_runtime_loop_routes_blender_feedback_into_edit_refresh` in
  `tests/test_runtime_loop.py`.
- The new test starts from `BLENDER_EDIT` with:
  - a latest user turn: `把机器人挪到画面中心，镜头保持不变。`;
  - a real `SceneSpec`;
  - a Blender scene containing object `Hero`;
  - no pre-existing `blender_edit_plan`.
- The loop then verifies:
  - controller first schedules `BlenderEditRouter`;
  - the router context contains the user edit text;
  - fixture router JSON is parsed through the real LLM-node/Pydantic path;
  - `ReviewPatch.structured_delta["blender_edit_plan"]` is written;
  - the rebuilt plan runs `move_subject -> export_viewer_scene -> render_preview`;
  - final state returns to `BLENDER_PREVIEW` with a user gate.

Verification:

```bash
python -m py_compile agent_runtime/runtime_loop.py tests/test_runtime_loop.py
pytest -q tests/test_runtime_loop.py::test_runtime_loop_routes_blender_feedback_into_edit_refresh -p no:cacheprovider
pytest -q tests/test_runtime_loop.py tests/test_runtime_state_apply.py tests/test_runtime_user_actions.py tests/test_runtime_execution.py -p no:cacheprovider
pytest -q -p no:cacheprovider
```

Results:

```text
new BlenderEditRouter feedback loop test: 1 passed in 0.46s
runtime loop/state/user-action/execution suite: 31 passed in 0.84s
full current suite: 316 passed in 2.36s
```

Boundary:

- This is still fixture LLM output, not a paid/live Qwen or DeepSeek call.
- The Blender edit call is an injected fake raw caller in test, not a new live
  Blender socket run.
- The remaining plan gap is now narrower: run the same loop with a live
  Qwen/DeepSeek `BlenderEditRouter` response and improve object-name sync for
  object-level edits in a live Blender scene.

## 2026-06-30 Runtime Console UI15 Product Workbench Correction

Goal: respond to the user review that the runtime console still looked like an
engineering/status surface rather than a creation workspace, with old cached
screens showing English buttons such as `Open GLB`, `Build Plan`, and right-side
debug fields.

Implementation:

- Kept the existing dependency-free `web/runtime_console/` UI and did not add a
  new framework or parallel state store.
- Bumped the served static version to `20260630-ui15`.
- Added a center `当前任务` brief so the public surface shows the natural
  language goal, reference-image binding state, current phase, asset progress,
  and next step before the 3D viewer.
- Tightened public run visibility/scoring so internal smoke/audit/worker/LLM
  runs are deprioritized or collapsed to public-safe names unless `?dev=1` is
  enabled.
- Improved preview loading behavior: iframe load now hides the loading state,
  while slow/blank preview load keeps an actionable Chinese hint instead of
  leaving an unexplained blank canvas.
- Added a final UI15 CSS override layer with stronger contrast, clearer
  phase/asset panels, more visible empty states, and product-workbench spacing.
  Raw runtime jobs, file paths, object internals, and debug controls remain
  behind `?dev=1`.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_frontend_status.py -p no:cacheprovider
pytest -q -p no:cacheprovider
curl -fsS "http://10.2.16.106:8093/?v=ui15-latest" | rg -n "ui15|当前任务|Open GLB|Build Plan|Step Dry"
firefox --headless --screenshot /tmp/image23d_ui15/runtime_console_ui15_latest.png --window-size 1600,1000 "http://10.2.16.106:8093/?v=ui15-latest"
```

Results:

```text
node --check: passed
html parser: passed
runtime console/frontend status suite: 8 passed in 0.33s
full current suite: 316 passed in 2.39s
served HTML uses ui15 and contains 当前任务
old Open GLB / Build Plan / Step Dry strings absent from served public HTML
runtime console pid=3633300, URL=http://10.2.16.106:8093/
```

Visual evidence:

```text
/tmp/image23d_ui15/runtime_console_ui15_latest.png
```

Boundary:

- Firefox CLI captures the initial shell before asynchronous `/api/runs`
  hydration completes, so the screenshot is visual evidence for the default
  public shell and loading state. Hydrated data paths were verified through
  HTTP API/static checks and the existing runtime-console tests.
- This is a public UI correction. It does not close the remaining live
  Qwen/DeepSeek agent decision, object-level Blender edit, or final autonomous
  acceptance-run gaps.

## 2026-06-30 Live Qwen BlenderEditRouter Alias-To-MCP Dry-Run Closure

Goal: close the immediate gap where a real LLM may output user-facing object
aliases (`object_id` / `subject_id`) instead of the internal
`blender_object_id`, making object-level Blender edits brittle.

Evidence inspected:

- Existing live run:
  `outputs/runs/20260630_live_qwen_blender_edit_router_smoke`.
- `runtime_execution_summary.json` records a non-dry-run `BlenderEditRouter`
  execution using provider `qwen`, model `qwen3.7-max`.
- The live parsed output planned:
  `move_subject({"object_id": "hero", "subject_id": "subject_robot",
  "location": [1.0, 2.0, 3.0]})`.
- `runtime_apply_summary.json` applied the candidate into
  `ReviewPatch.structured_delta["blender_edit_plan"]`.

Implementation:

- Extended `agent_runtime.blender_mcp._resolve_object_name(...)` so Blender
  edit tools resolve objects by:
  - `blender_object_id` / `object_id`;
  - exact Blender object name;
  - `subject_id` fallback.
- Added a conflict guard: if `object_id`/`blender_name` and `subject_id`
  resolve to different Blender objects, the operation plan is rejected instead
  of silently moving the wrong object.
- Added tests for live-LLM-style `object_id + subject_id` arguments, pure
  `subject_id` fallback, and conflict rejection.
- Fixed `agent_runtime.runtime_audit` so domain-tool dry-run outputs are
  audited as operation plans instead of being mistaken for LLM dry-runs without
  parsed candidates.

Non-destructive runtime proof:

```bash
python - <<'PY'
from pathlib import Path
from agent_runtime.runtime_execution import execute_next_runtime_job
run = Path("outputs/runs/20260630_live_qwen_blender_edit_router_smoke")
result = execute_next_runtime_job(run, dry_run=True)
print(result.ok, result.selected_job_id, result.record.status, result.record.output_json)
PY
```

Result:

```text
ok=True
selected_job_id=job_01_blender_edit_move_subject
status=dry_run
output_json=runtime_execution/exec_bf14f599e67b.json
```

The dry-run operation plan resolved the live Qwen aliases to Blender object
`Hero`:

```text
domain_tool_name=move_subject
raw_tool_name=execute_blender_code
arguments_summary={"blender_name": "Hero", "location": [1.0, 2.0, 3.0]}
safety_notes=[
  "object_resolved_from_blender_scene_state",
  "fixed_python_template",
  "view_layer_update_after_transform"
]
state.tool_call_log length remained 0
state.phase remained BLENDER_EDIT
```

Verification:

```bash
python -m py_compile agent_runtime/blender_mcp.py agent_runtime/runtime_audit.py tests/test_blender_mcp.py tests/test_domain_dispatcher.py tests/test_runtime_audit.py
pytest -q tests/test_blender_mcp.py::test_build_safe_blender_mcp_operation_plan_accepts_live_llm_object_aliases tests/test_blender_mcp.py::test_build_safe_blender_mcp_operation_plan_rejects_conflicting_object_and_subject tests/test_domain_dispatcher.py::test_blender_mcp_dispatcher_dry_run_accepts_live_llm_object_aliases -p no:cacheprovider
pytest -q tests/test_runtime_audit.py tests/test_blender_mcp.py tests/test_domain_dispatcher.py -p no:cacheprovider
python -m agent_runtime.runtime_audit outputs/runs/20260630_live_qwen_blender_edit_router_smoke --json
pytest -q -p no:cacheprovider
```

Results:

```text
alias target tests: 3 passed in 0.41s
audit/blender/domain-dispatcher suite: 48 passed in 0.42s
live Qwen run audit: ok=true, error_count=0, warning_count=0
full current suite: 320 passed in 2.35s
secret scan for long sk-* tokens in the live run: no matches
```

Boundary:

- This did not execute a live Blender object move. It proved that the live Qwen
  `BlenderEditRouter` output can be converted into a safe raw MCP operation
  plan for object `Hero`.
- Remaining Blender-edit gaps after the later DeepSeek replay closure:
  non-dry-run object-level Blender edit using a live-router payload, viewer
  export/render refresh after that live edit, and final user approval/delivery
  closure.

## 2026-06-30 Runtime Console UI16 Frontend Review Correction

Goal: respond to the user screenshot review that the runtime console still
looked like a debug/status page: pale visual contrast, right-side engineering
fields, unclear product-stage hierarchy, and old English/debug strings.

Implementation:

- Kept the existing lightweight runtime-console frontend and existing JSON/API
  chain; no new framework, state store, or run-directory layout was introduced.
- Bumped the public static version to `20260630-ui16`.
- Reworked the public right rail so the first visible block is `下一步`,
  followed by the five product stages, then assets and delivery files.
- Hid idle user-confirmation cards; approval buttons appear only at real
  concept-review or 3D-preview gates.
- Hid the duplicate current-stage hero in public mode; raw status/job/file
  details stay available only through `?dev=1`.
- Added a stronger final public skin in `web/runtime_console/polish.css`:
  clearer contrast, stable 4-column workbench layout, stronger center 3D
  preview area, clean upload/chat composer, and compact right-side cards.
- Preserved the product stage vocabulary:
  `需求绑定 -> 概念确认 -> 模型生成 -> 场景验收 -> 交付下载`.

Sub-agent audit:

- A read-only frontend sub-agent reviewed the current DOM/CSS/text flow and
  identified the remaining product-vs-debug issues:
  duplicate stage summaries, raw runtime wording behind `renderStatus()`, and
  the need to keep technical fields behind `?dev=1`.
- The UI16 pass integrated those recommendations without giving the sub-agent
  write ownership.

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_frontend_status.py -p no:cacheprovider
curl -fsS "http://127.0.0.1:8093/?v=ui16-check2" | rg -n "20260630-ui16|Open GLB|Open Blend|Build Plan|Step Dry|STATUS|Phase|Workflow|Tools|下一步|阶段进度|全部资产|交付文件"
firefox --headless --screenshot /tmp/image23d_ui16/runtime_console_ui16_reordered.png --window-size 1600,1000 "http://127.0.0.1:8093/?v=ui16-check2"
```

Results:

```text
node --check: passed
html parser: passed
runtime console/frontend status suite: 8 passed in 0.33s
served HTML uses ui16
old Open GLB / Open Blend / Build Plan / Step Dry / STATUS / Phase / Workflow / Tools strings absent from served public HTML
```

Runtime data check:

```text
default_run=20260630_blender_socket_edit_refresh_scratch_20260630T025222
has_viewer_scene=True
has_scene_state=True
phase=BLENDER_PREVIEW
status=needs_user_action
viewer_scene_url=http://10.2.16.106:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_blender_socket_edit_refresh_scratch_20260630T025222/viewer_export/viewer_scene.glb
objects=7
artifacts=10
```

Visual evidence:

```text
/tmp/image23d_ui16/runtime_console_ui16_reordered.png
```

Boundary:

- The available Firefox CLI screenshot captures the initial page shell before
  asynchronous `/api/runs` hydration. Hydrated run selection and viewer URLs
  were verified through the runtime-console API and bundle builder.
- This is a frontend review correction. It does not replace the remaining live
  agent-runtime gaps: non-dry-run object-level Blender edit, post-edit viewer
  refresh, and final approval/delivery closure.

## 2026-06-30 DeepSeek BlenderEditRouter Tool-Call-Only Replay Closure

Goal: close the live-provider compatibility gap where DeepSeek returned a
valid `BlenderEditRouter.domain_tool_calls` payload but no `ReviewPatch[]`,
while the runtime expected patches before it would schedule object-level
Blender edit jobs.

Evidence inspected:

- Existing live DeepSeek run:
  `outputs/runs/20260630_live_deepseek_blender_edit_router_smoke`.
- `runtime_execution_summary.json` records a non-dry-run `BlenderEditRouter`
  call using provider `deepseek`, model `deepseek-v4-flash`.
- The parsed output planned:
  `move_subject({"subject_id": "subject_robot", "location": [1, 2, 3]})`
  with `patches=[]`.
- The earlier apply result was technically `applied` but had
  `applied_fields=[]`, leaving no `ReviewPatch` and therefore no executable
  object-edit plan.

Implementation:

- `agent_runtime.runtime_state_apply._patches_with_blender_edit_plan(...)`
  now synthesizes a deterministic `ReviewPatch` when a `BlenderEditRouter`
  output contains domain tool calls but no patches.
- The synthesized patch stores the original
  `blender_edit_plan.domain_tool_calls`, maps common Blender edit tools to
  patch types, and preserves the target alias such as `subject_id`.
- Added test coverage for tool-call-only `move_subject` output:
  `apply_next_runtime_candidate(...)` now writes `review_patches`, rebuilds the
  runtime plan, and schedules `move_subject` before viewer export/render.

Non-API replay proof:

- Created a new replay run from the existing live DeepSeek output:
  `outputs/runs/20260630_live_deepseek_blender_edit_router_replay_toolcalls`.
- Rewrote copied absolute execution-output paths into the replay directory and
  removed prior apply logs so the live parsed output could be reapplied.
- Copied the referenced `.blend` artifact into the replay run's own
  `artifacts/` directory and rewrote `state.json`, `runtime_plan.json`, and
  checkpoint snapshots so the replay run is run-local and self-contained.

Replay result:

```text
apply_ok=True
apply_status=applied
applied_fields=["review_patches"]
patch_ids=["patch_blender_edit_0479e0079d83"]
state_phase=BLENDER_EDIT
patch=patch_blender_edit_0479e0079d83 move_object blender_object subject_robot
plan job 1=job_01_blender_edit_move_subject
dry-run operation plan target=Hero
raw_tool_name=execute_blender_code
state.tool_call_log length remained 0
```

Verification:

```bash
python -m py_compile agent_runtime/runtime_state_apply.py tests/test_runtime_state_apply.py
pytest -q tests/test_runtime_state_apply.py tests/test_runtime_loop.py tests/test_runtime_execution.py tests/test_runtime_audit.py -p no:cacheprovider
pytest -q tests/test_runtime_state_apply.py tests/test_runtime_loop.py tests/test_runtime_execution.py tests/test_runtime_audit.py tests/test_blender_mcp.py tests/test_domain_dispatcher.py -p no:cacheprovider
python -m agent_runtime.runtime_audit outputs/runs/20260630_live_deepseek_blender_edit_router_replay_toolcalls --json
rg -n 'sk-[A-Za-z0-9]{20,}|20260630_live_qwen_blender_edit_router_smoke' outputs/runs/20260630_live_deepseek_blender_edit_router_replay_toolcalls || true
pytest -q -p no:cacheprovider
```

Results:

```text
runtime state/loop/execution/audit suite: 29 passed in 0.81s
runtime/blender/domain-dispatcher suite: 74 passed in 0.92s
DeepSeek replay audit: ok=true, error_count=0, warning_count=0
secret/external-run path scan on replay run: no matches
full current suite: 321 passed in 2.32s
```

Boundary:

- This reused an existing live DeepSeek LLM output; it did not submit another
  paid/live API request.
- This replay slice still dry-ran the Blender domain tool. The immediate
  live-edit gap from this point is closed in the following
  `Live DeepSeek Router To Socket Blender Edit And Viewer Refresh` section.

## 2026-06-30 Live DeepSeek Router To Socket Blender Edit And Viewer Refresh

Goal: close the next gap after the DeepSeek replay by taking the same
live-provider `BlenderEditRouter` output through a real non-dry-run Blender
edit under the explicit `blender-lab-socket` raw-caller boundary, then refresh
the viewer GLB and preview render from the edited `.blend`.

Run:

```text
outputs/runs/20260630_live_deepseek_blender_edit_router_liveedit_socket
```

Live chain evidence:

- Reused the existing live DeepSeek `BlenderEditRouter` parsed output and the
  runtime patch synthesis path, without submitting a new provider call.
- Synced the current Blender socket scene and bound the Hunyuan mesh object
  back to `subject_robot` before editing.
- Executed `move_subject` through the explicit `blender-lab-socket` raw caller.
- Saved the edited run-local Blender file:
  `artifacts/blend_file_001.blend`.
- Executed the script-backed viewer refresh jobs:
  `export_viewer_scene` and `render_preview`.
- Final state is back at `BLENDER_PREVIEW` with `frontend_status.status` set to
  `needs_user_action`.

Execution ids:

```text
BlenderEditRouter live output: exec_d4470a2afe63
live move_subject socket edit: exec_1a74f5950f60
viewer GLB export: exec_a45340c602ff
preview render: exec_4543b776bc13
```

Output artifacts:

```text
viewer GLB:
outputs/runs/20260630_live_deepseek_blender_edit_router_liveedit_socket/viewer_export/viewer_scene.glb

preview PNG:
outputs/runs/20260630_live_deepseek_blender_edit_router_liveedit_socket/preview_render/preview.png

viewer URL:
http://10.2.16.106:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_live_deepseek_blender_edit_router_liveedit_socket/viewer_export/viewer_scene.glb
```

Implementation fixes landed while closing this run:

- `agent_runtime.domain_dispatcher` now preserves `subject_id`, `asset_id`,
  semantic role, and non-unknown object type when Blender MCP scene summaries
  return only raw object names. It also writes the planned transform back into
  `BlenderSceneState` after successful transform tools.
- `agent_runtime.runtime_execution` now merges Blender object metadata into
  regenerated `ViewerSceneState` objects so the viewer snapshot can keep
  subject bindings after export.
- `agent_runtime.runtime_audit` now validates both dry-run domain-tool payloads
  and completed non-dry-run domain-tool payloads. Live executions carry the
  `domain_tool_name` in `domain_tool_result`, while dry-runs carry it in the
  safe operation plan.

State checks:

```text
phase=BLENDER_PREVIEW
frontend_status=needs_user_action
tool_call_log length=3
handled_jobs=[
  job_01_blender_edit_BlenderEditRouter,
  job_01_blender_edit_move_subject,
  job_02_blender_edit_export_viewer_scene,
  job_03_blender_edit_render_preview
]
pending_jobs=[]
subject viewer object=Hunyuan3D_360a38c9-f8f9-44da-9a5c-ed19ece6a7a5_texturing.obj
subject_id=subject_robot
subject location=[1.0, 2.0, 3.0]
```

Verification:

```bash
python -m py_compile agent_runtime/runtime_audit.py tests/test_runtime_audit.py
pytest -q tests/test_runtime_audit.py -p no:cacheprovider
python -m agent_runtime.runtime_audit outputs/runs/20260630_live_deepseek_blender_edit_router_liveedit_socket --json
pytest -q tests/test_runtime_execution.py tests/test_runtime_audit.py tests/test_domain_dispatcher.py tests/test_runtime_loop.py -p no:cacheprovider
pytest -q -p no:cacheprovider
node --check web/runtime_console/app.js
python - <<'PY'
from html.parser import HTMLParser
from pathlib import Path
class P(HTMLParser): pass
P().feed(Path('web/runtime_console/index.html').read_text(encoding='utf-8'))
print('html parser ok')
PY
```

Results:

```text
runtime audit unit tests: 4 passed in 0.35s
liveedit runtime audit: ok=true, error_count=0, warning_count=0
target runtime/edit/audit suite: 55 passed in 0.83s
full current suite: 322 passed in 2.42s
frontend app syntax: ok
frontend HTML parse: ok
run-local secret scan: no matching files
```

Boundary:

- This closes the previous "live-router payload -> non-dry-run object edit ->
  viewer refresh" gap for one object-level move.
- This replay-derived live edit run is still a preview/edit proof, not a full
  delivery candidate: after tightening delivery preflight, it correctly reports
  `missing_subject_assets` and `missing_scene_assets` because its state only
  contains the edited `.blend`, viewer export, scene-state JSON, and preview
  render.
- Mature camera/layout reasoning and broad live-provider coverage across every
  LLM node remain future work.

## 2026-06-30 Delivery Preflight Tightening And Runtime Package Close-Out

Goal: close the gap between "viewer preview exists" and "delivery package is
actually complete". The previous `delivery_handoff.ready` check only proved
that a viewer URL/model check existed, which allowed an edit-only run to look
deliverable even though the package builder would reject it for missing
subject and scene assets.

Implementation:

- `agent_runtime.delivery_handoff.build_delivery_handoff(...)` now checks the
  same required artifact classes as the package builder:
  `.blend`, preview render, viewer GLB/GLTF, viewer state JSON, subject GLB,
  and scene/world GLB.
- It also checks that required artifact files exist, exposes
  `subject_asset_count` and `scene_asset_count`, and only reports
  `verified=true` when the handoff is both ready and the viewer runtime/model
  checks are true.
- Tests were updated so viewer-refresh-only fixtures remain valid preview
  proofs but no longer claim delivery readiness.

Corrected edit-run preflight:

```text
run=outputs/runs/20260630_live_deepseek_blender_edit_router_liveedit_socket
delivery_handoff.ready=false
delivery_handoff.verified=false
issues=["missing_subject_assets", "missing_scene_assets"]
subject_asset_count=0
scene_asset_count=0
```

Runtime delivery close-out run:

```text
outputs/runs/20260629_scene_spec_assembly_non_dryrun
```

This run already had the full package substrate:

```text
workflow_scene_glb          SCENE_3D_ASSET
workflow_subject_glb        SUBJECT_3D_ASSET
workflow_composed_preview_png BLENDER_PREVIEW_RENDER
workflow_composed_blend     BLENDER_FILE
workflow_viewer_scene_glb   VIEWER_SCENE_GLB
workflow_scene_state_json   VIEWER_SCENE_STATE_JSON
```

Runtime close-out actions:

```text
approve_blender_preview:
  action=approve_blender_preview
  checkpoint=ckpt_v1_local_e2e_workflow_local_workflow_20260629T222939Z_ff7b00cf80
  next phase=DELIVERY

execute_next_runtime_job:
  job=job_01_delivery_delivery
  execution=exec_8102097a7a63
  status=completed
```

Package result:

```text
package_id=delivery_v1_local_e2e_workflow_54dac92d
package_zip=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/delivery_package/package/delivery_v1_local_e2e_workflow_54dac92d.zip
zip_size=146769236
delivery_package_ok=true
delivery_package_issues=[]
delivery_handoff.ready=true
delivery_handoff.verified=true
subject_asset_count=1
scene_asset_count=1
```

Zip contents:

```text
files/blender/workflow_composed_blend.blend
files/preview/workflow_composed_preview_png.png
files/scene_assets/workflow_scene_glb.glb
files/subject_assets/workflow_subject_glb.glb
files/viewer_scene/workflow_viewer_scene_glb.glb
files/viewer_state/workflow_scene_state_json.json
metadata.json
version_manifest.json
```

Frontend/API evidence:

```text
GET http://127.0.0.1:8093/api/runs/20260629_scene_spec_assembly_non_dryrun
phase=DELIVERY
delivery_ready=true
delivery_verified=true
package_zip=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/delivery_package/package/delivery_v1_local_e2e_workflow_54dac92d.zip
```

Verification:

```bash
pytest -q tests/test_delivery_handoff.py tests/test_delivery_package.py tests/test_runtime_execution.py tests/test_runtime_loop.py tests/test_runtime_user_actions.py tests/test_runtime_audit.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
python -m agent_runtime.runtime_audit outputs/runs/20260629_scene_spec_assembly_non_dryrun --json
python -m agent_runtime.runtime_audit outputs/runs/20260630_live_deepseek_blender_edit_router_liveedit_socket --json
pytest -q -p no:cacheprovider
node --check web/runtime_console/app.js
```

Results:

```text
target handoff/package/runtime suite: 48 passed in 0.91s
SceneSpec delivery run audit: ok=true, error_count=0, warning_count=0
DeepSeek live edit run audit after preflight tightening: ok=true, error_count=0, warning_count=0
full current suite: 323 passed in 2.37s
frontend app syntax: ok
frontend HTML parse: ok
secret scan on updated runs/source/docs/tests/web: no matching files
```

Boundary:

- This closes runtime approval -> delivery package execution for one
  full-asset SceneSpec-driven run.
- It does not yet prove a single fully autonomous fresh run where live LLM
  SceneSpec/concept/edit decisions, live generation, full asset preservation,
  and delivery happen without manual stage stitching.

## 2026-06-30 Runtime Console UI17 Public Frontend Correction

Goal: respond to the latest frontend review that the console still looked like
an internal/debug surface, defaulted to live-router/debug runs, hid the formal
delivery run, and did not expose the file/JSON chain clearly enough.

Implementation:

- Bumped served static assets to `20260630-ui17`.
- Reworked public run selection:
  - `non_dryrun` is no longer misclassified as dry-run;
  - `live/deepseek/qwen/socket/scratch/router/worker/audit/smoke` runs are
    hidden in public mode unless `?dev=1` is used;
  - the formal `20260629_scene_spec_assembly_non_dryrun` delivery run is the
    top public default.
- Added public-safe task title/goal filtering so smoke/router/live/debug
  SceneSpec text does not appear as the user-facing current task.
- Added Blender preview-render image fallback in the main viewer area when
  the GLB viewer is absent, and added viewer embed query parameters for the
  iframe path.
- Kept a visible public status hero in the right panel; old UI16 CSS had hidden
  it in public mode.
- Delivery panel now exposes:
  - handoff ready/verified state plus translated issues;
  - `state.json`;
  - `viewer_export/scene_state.json`;
  - `delivery_handoff.json`;
  - the delivery zip URL from `file_manifest`.
- Upload/reference chips now merge `runtime_console/uploads.jsonl` with
  authoritative `state.input_images`, so inputs already present in state do not
  look missing.
- Reference images with missing purpose bindings are no longer counted as a
  fully ready asset.
- Added a final CSS override layer at the physical end of
  `web/runtime_console/polish.css` so stale UI16 rules cannot hide the public
  status block.

Service evidence:

```text
GET http://127.0.0.1:8093/?v=ui17-final-check
served assets: 20260630-ui17
old public strings Open GLB / Open Blend / Build Plan / Step Dry absent
```

Public run selection evidence:

```text
visible_count=4
top=20260629_scene_spec_assembly_non_dryrun
next=20260628_p0_real_demo
next=20260628_codex_self_robot_concept
next=runtime_console_20260629T071341Z0000
```

Formal delivery file-link evidence:

```text
delivery_ready=true
delivery_verified=true
state.url=/api/runs/.../file?path=state.json
scene_state.url=/api/runs/.../file?path=viewer_export/scene_state.json
delivery_handoff.url=/api/runs/.../file?path=delivery_handoff.json
delivery_package.url=/api/runs/.../file?path=delivery_package/package/delivery_v1_local_e2e_workflow_54dac92d.zip
```

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
firefox --headless --screenshot /tmp/image23d_ui17/runtime_console_ui17.png --window-size 1600,1000 "http://127.0.0.1:8093/?v=ui17-final2"
```

Results:

```text
frontend app syntax: ok
frontend HTML parse: ok
runtime console/status suite: 17 passed in 0.38s
headless screenshot: /tmp/image23d_ui17/runtime_console_ui17.png
```

Boundary:

- This is still the existing static runtime console, not a new React/Ant/TDesign
  migration.
- The embedded GLB viewer service itself can still expose its own English
  controls/path if it ignores `embed=1&public=1&lang=zh-CN`; a dedicated
  public viewer skin remains a separate follow-up.

## 2026-06-30 GLB Viewer Public Embed Mode

Goal: close the remaining frontend review gap where the runtime console shell
was Chinese/product-facing, but the embedded 8092 GLB viewer still showed
English controls and the absolute local model path.

Implementation:

- Reused the existing `tools/glb_viewer_server.py`; no second viewer service
  or parallel web runtime was introduced.
- Added `public=1` / `embed=1` query handling:
  - public mode uses Chinese controls;
  - embed mode hides the file path, download link, and model list link;
  - debug/default mode keeps the existing list/download/path surface for
    operator inspection.
- Updated the viewer asset URL in the generated viewer HTML to URL-encode the
  model path fully, so the public embed HTML no longer contains a bare
  `/home/team/...` path string.
- Kept the existing runtime-console `viewerEmbedUrl(...)` behavior that passes
  `embed=1&public=1&lang=zh-CN` into the iframe.
- Added `tests/test_glb_viewer_server.py` with a temporary HTTP server check
  for public/embed HTML.
- Restarted the live 8092 viewer service:

```text
Stopped GLB viewer pid=1603687
GLB viewer started: pid=1855599
URL: http://10.2.16.106:8092/
```

Live service check:

```text
GET /viewer?...&embed=1&public=1&lang=zh-CN
body class="embed public"
buttons: 暂停旋转 / 播放动画 / 重置视角
absent: >Download<, >List<, <div class="path">, bare /home/team/zouzhiyuan
```

Verification:

```bash
python -m py_compile tools/glb_viewer_server.py tests/test_glb_viewer_server.py
pytest -q tests/test_glb_viewer_server.py tests/test_viewer.py tests/test_viewer_runtime.py -p no:cacheprovider
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py tests/test_glb_viewer_server.py tests/test_viewer.py tests/test_viewer_runtime.py -p no:cacheprovider
```

Results:

```text
viewer tests: 10 passed in 0.87s
runtime-console/viewer combined tests: 27 passed in 0.94s
```

Boundary:

- Public embed mode improves the current acceptance viewer surface. It does
  not yet implement richer object picking, scene editing, or live websocket
  refresh inside the browser viewer.

## 2026-06-30 Hydrated Runtime Console Browser Smoke

Goal: close the long-standing gap where Firefox CLI screenshots captured the
initial shell before asynchronous `/api/runs` hydration finished. The new check
turns the hydrated runtime-console API state into a browser-rendered acceptance
report and verifies the public viewer iframe URL.

Implementation:

- Added `scripts/runtime_console_hydrated_smoke.py`.
- The script:
  - fetches the live 8093 index/app/static API;
  - applies the same public run selection policy as the UI;
  - verifies the selected public run is
    `20260629_scene_spec_assembly_non_dryrun`;
  - fetches the selected run bundle and checks `DELIVERY`,
    `delivery_handoff.ready=true`, and `delivery_handoff.verified=true`;
  - verifies public file links for `state.json`, `scene_state.json`,
    `delivery_handoff.json`, and the delivery package zip;
  - checks the 8092 viewer embed URL returns public Chinese controls without
    visible path/list/download debug UI;
  - writes `summary.json`, `hydrated_report.html`, and Firefox screenshots.

Live command:

```bash
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_hydrated_smoke \
  --expected-run-id 20260629_scene_spec_assembly_non_dryrun
```

Result summary:

```text
ok=true
selected_run_id=20260629_scene_spec_assembly_non_dryrun
visible_run_count=4
phase=DELIVERY
delivery_status=ready_verified
file links:
  state=http://127.0.0.1:8093/api/runs/.../file?path=state.json
  scene_state=http://127.0.0.1:8093/api/runs/.../file?path=viewer_export/scene_state.json
  delivery_handoff=http://127.0.0.1:8093/api/runs/.../file?path=delivery_handoff.json
  delivery_package=http://127.0.0.1:8093/api/runs/.../file?path=delivery_package/package/delivery_v1_local_e2e_workflow_54dac92d.zip
```

Checks:

```text
served_expected_assets=true
old_public_strings_absent=true
has_public_runs=true
expected_run_selected=true
delivery_ready=true
delivery_verified=true
delivery_phase=true
file_link_state=true
file_link_scene_state=true
file_link_delivery_handoff=true
file_link_delivery_package=true
viewer_embed_public=true
viewer_chinese_controls=true
viewer_debug_text_absent=true
viewer_bare_home_absent=true
```

Artifacts:

```text
/tmp/image23d_hydrated_smoke/summary.json
/tmp/image23d_hydrated_smoke/hydrated_report.html
/tmp/image23d_hydrated_smoke/hydrated_report.png
/tmp/image23d_hydrated_smoke/viewer_embed.png
```

Boundary:

- This is a browser-rendered hydrated acceptance report, not full WebDriver
  DOM automation of the runtime console app itself. It closes the previous
  early-screenshot problem for public run selection, delivery links, and
  embedded viewer acceptance, while richer object-level browser interactions
  remain future work.

## 2026-06-30 Runtime Console UI18 Public Review Fix

Goal: respond to the user's screenshot review that the console still looked
like a debug surface, had too much blank/white space, leaked English/internal
controls, and did not make the stage or file chain clear.

Implementation:

- Added `web/runtime_console/ui18_final.css` and loaded it after legacy
  `polish.css`, because `polish.css` contains many older UI layers whose later
  rules were overriding the intended public layout.
- Updated `tools/runtime_console_server.py` to serve `ui18_final.css`; restarted
  the live 8093 runtime console.
- Added a center `stageRoadmap` five-step strip and fixed the right-side
  `stageTimeline` to be a vertical Chinese progress list in public mode.
- Kept internal controls and runtime details behind `?dev=1`; public delivery
  now shows only user-facing entries: delivery status, open 3D preview,
  download 3D model, open Blender project, and download delivery package.
- Reworked public run/default selection so stale saved empty runs no longer
  override the formal viewer-ready run.
- Added a Blender render preview thumbnail inside the GLB loading state so a
  large 205MB viewer GLB does not present as an empty black area while WebGL is
  still loading.
- Corrected delivery-phase asset semantics: verified delivery runs show
  `6/6` ready, and upstream optional gaps display as "not used/not required" or
  "included in project" instead of looking like missing files.
- Used a read-only frontend sub-agent audit to identify the concrete issues:
  public JSON/debug leakage, weak phase visibility, confusing right rail, and
  run-name leakage.

Live service:

```text
Runtime console restarted: http://10.2.16.106:8093/ pid=2164593
GLB viewer unchanged/running: http://10.2.16.106:8092/ pid=1855599
```

Verification:

```bash
python -m py_compile tools/runtime_console_server.py scripts/runtime_console_hydrated_smoke.py
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py tests/test_glb_viewer_server.py tests/test_viewer.py tests/test_viewer_runtime.py -p no:cacheprovider
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_hydrated_smoke_ui18 \
  --expected-run-id 20260629_scene_spec_assembly_non_dryrun \
  --expected-ui-version 20260630-ui18
```

Results:

```text
targeted runtime-console suite: 17 passed in 0.39s
runtime-console/viewer combined suite: 27 passed in 0.95s
hydrated smoke: ok=true
selected_run_id=20260629_scene_spec_assembly_non_dryrun
phase=DELIVERY
delivery_status=ready_verified
public delivery entries=交付状态|打开 3D 预览|下载 3D 模型|打开工程文件|下载交付包
assets=6/6 个就绪
viewerHeight=579
taskHeight=90
hasPreviewImage=true
hasDebug=false
hasRuntimeName=false
```

Artifacts:

```text
/tmp/image23d_ui18/runtime_console_ui18_hydrated.png
/tmp/image23d_hydrated_smoke_ui18/summary.json
/tmp/image23d_hydrated_smoke_ui18/hydrated_report.html
/tmp/image23d_hydrated_smoke_ui18/hydrated_report.png
/tmp/image23d_hydrated_smoke_ui18/viewer_embed.png
```

Boundary:

- This fixes the review-facing public console shell and the file/status chain.
  It does not yet add object-level viewer picking, live scene refresh push, or a
  brand-new frontend framework. The implementation intentionally reuses the
  existing static runtime console and GLB viewer.

## 2026-06-30 Runtime Console Object-Focus Viewer Link

Goal: advance the remaining Web viewer gap from "scene preview exists" toward
object-level inspection without creating a second viewer.

Implementation:

- Reused the existing `scene_state.json` object list exposed by
  `agent_runtime.runtime_runs`.
- Added a public `场景对象` panel in `web/runtime_console/index.html`.
- Added `renderSceneObjectsPublic(...)` in `web/runtime_console/app.js`:
  - filters non-user-facing camera/light/empty objects;
  - shows object display name, object type, and bounds-derived size;
  - generates `聚焦查看` links using object bounds center and radius;
  - maps Hunyuan3D raw object names to public `主体模型`.
- Extended the existing `tools/glb_viewer_server.py` with public focus query
  support:
  - `target=x,y,z` -> model-viewer `camera-target`;
  - `radius=r` or `orbit=azimuth,elevation,radius` -> model-viewer
    `camera-orbit`;
  - `focus=<label>` -> public focus badge.
- Restarted the existing 8092 GLB viewer; no parallel viewer service was added.

Live service:

```text
GLB viewer restarted: http://10.2.16.106:8092/ pid=2262726
Runtime console was later restarted by the UI19 pass on
http://10.2.16.106:8093/ pid=2539659
```

Verification:

```bash
node --check web/runtime_console/app.js
python -m py_compile tools/glb_viewer_server.py tests/test_glb_viewer_server.py
pytest -q tests/test_glb_viewer_server.py tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py -p no:cacheprovider
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py tests/test_glb_viewer_server.py tests/test_viewer.py tests/test_viewer_runtime.py -p no:cacheprovider
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_hydrated_smoke_ui18_objects \
  --expected-run-id 20260629_scene_spec_assembly_non_dryrun \
  --expected-ui-version 20260630-ui18 \
  --skip-firefox
```

Results:

```text
object-focus targeted suite: 21 passed in 1.43s
runtime-console/viewer combined suite: 29 passed in 1.45s
hydrated smoke: ok=true
live focus viewer HTML:
  camera_target=true
  camera_orbit=true
  focus_badge=true
  public_embed=true
BiDi object panel:
  objectCount=3
  objectTexts=场景网格 1 ... 聚焦查看 | 场景网格 2 ... 聚焦查看 | 主体模型 ... 聚焦查看
  hasFocusParams=true
```

Artifacts:

```text
/tmp/image23d_ui18/runtime_console_ui18_objects_panel.png
/tmp/image23d_hydrated_smoke_ui18_objects/summary.json
```

Boundary:

- This adds object-level inspection entry points and focused viewer camera
  parameters. It does not yet implement in-canvas object picking, live push
  refresh, or object edit commands from the web UI.

## 2026-06-30 Runtime Console UI19 Product Shell

Goal: address the latest user review that the console still looked like a pale
runtime/debug dashboard with English/debug fragments and unclear phase/asset
organization.

Implementation:

- Stopped loading the legacy `polish.css` and `ui18_final.css` layers from the
  public runtime-console entrypoint. The public page now loads only
  `styles.css` plus the new `web/runtime_console/ui19_public.css`.
- Bumped runtime-console cache/version keys to `20260630-ui19`, so browsers
  drop stale UI18 local run selection.
- Reworked public copy and ordering:
  - left rail: `创作历史`;
  - center ribbon: `素材` instead of `链路资产`;
  - right rail: `素材库 -> 下一步/阶段进度 -> 场景内容 -> 验收与交付`;
  - public scene content hides raw dimensions/asset ids unless `?dev=1`.
- Kept existing runtime-console API, GLB viewer, run discovery, upload/chat,
  user-gate, delivery, and object-focus links. No new frontend framework or
  parallel viewer was introduced.
- Restarted the existing 8093 runtime console with `setsid -f` so it survives
  the command session.

Live service:

```text
Runtime console: http://10.2.16.106:8093/?v=ui19-final pid=2539659
GLB viewer: http://10.2.16.106:8092/ pid=2262726
```

Verification:

```bash
node --check web/runtime_console/app.js
python -m html.parser web/runtime_console/index.html
python -m py_compile tools/runtime_console_server.py scripts/runtime_console_hydrated_smoke.py
pytest -q tests/test_runtime_console.py tests/test_runtime_runs.py tests/test_frontend_status.py tests/test_glb_viewer_server.py tests/test_viewer.py tests/test_viewer_runtime.py -p no:cacheprovider
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_hydrated_smoke_ui19 \
  --expected-run-id 20260629_scene_spec_assembly_non_dryrun \
  --expected-ui-version 20260630-ui19
```

Results:

```text
runtime-console/viewer combined suite: 29 passed in 1.45s
hydrated smoke: ok=true
selected_run_id=20260629_scene_spec_assembly_non_dryrun
phase=DELIVERY
delivery_status=ready_verified
served_expected_assets=true
old_public_strings_absent=true
viewer_embed_public=true
viewer_chinese_controls=true
```

Artifacts:

```text
/tmp/image23d_ui19/runtime_console_ui19_fixed.png
/tmp/image23d_hydrated_smoke_ui19/summary.json
/tmp/image23d_hydrated_smoke_ui19/hydrated_report.html
/tmp/image23d_hydrated_smoke_ui19/hydrated_report.png
/tmp/image23d_hydrated_smoke_ui19/viewer_embed.png
```

Boundary:

- The visible public shell is cleaner and no longer depends on the old
  `polish.css` override stack. Remaining Step 9 gaps are still in-canvas
  picking, live push refresh, and direct object edit commands from the web UI.

## 2026-06-30 Full-Asset Live Router Edit Closure + UI20 Selection

Goal: close the gap where live Blender edit runs could work on the wrong open
Blender scene, then lose full-asset semantics in JSON/front-end status, and
remain hidden behind public-console internal-run filtering.

Implementation:

- `BlenderMCPDomainToolDispatcher` now has an explicit `ensure_blend_loaded`
  mode. When the raw caller source is `blender-lab-socket`, non-dry edit tools
  first open the run-local `.blend` artifact through Blender MCP, then execute
  the fixed edit template, sync objects, and save back to the same blend file.
- `sync_blender_scene_state_from_objects_summary(...)` now preserves the
  existing top-level `scene_asset_id`; the runtime state-apply viewer hydrate
  path also backfills `blender_scene.scene_asset_id` from the scene GLB artifact.
- `run_local_e2e_workflow(...)` now registers existing input GLBs into both
  `artifacts` and semantic `subject_assets` / `scene_asset` records, so future
  full-asset runs do not rely on file artifacts alone.
- `build_frontend_status(...)` now falls back to subject/scene GLB artifacts
  for legacy runs whose semantic asset records were missing.
- Runtime viewer export now writes the merged semantic viewer scene back into
  `viewer_export/scene_state.json` before artifact registration, so the linked
  JSON file itself carries `subject_id` / `asset_id` instead of only the
  in-memory `state.viewer_scene`.
- Runtime audit accepts failed prior-phase jobs that were later recovered by a
  successful execution of the same job id, instead of treating the old failed
  retry record as a current-plan inconsistency.
- Runtime console index items now expose `frontend_phase` and
  `frontend_status_value`; `ui20` sorting keeps inspectable
  `BLENDER_PREVIEW` edit/router runs visible and selected ahead of old
  showcase demos. The smoke script mirrors the same selection logic and accepts
  both delivery and preview-gate surfaces.

Live run advanced:

```text
run_dir=/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
subject_asset_ids=["workflow_subject_glb"]
scene_asset_id=workflow_scene_glb
viewer_scene_id=viewer_scene
current_stage=blender_preview_approval
```

Runtime executions:

```text
exec_313abe456b4c  move_subject       completed
  blend_load_raw_result=ok
  saved_blend_path=artifacts/blender_file/workflow_composed_blend.blend
  subject_plush location=[0.35, 0.95, -0.12]

exec_7ad61fc5a669  export_viewer_scene completed
  viewer_export/viewer_scene.glb
  viewer_export/scene_state.json

exec_c492db91ed82  render_preview      completed
  preview_render/preview.png
  preview_render/preview.blend
```

Generated artifacts:

```text
outputs/runs/20260630_full_asset_live_router_edit_dfce104f/viewer_export/viewer_scene.glb 214797360 bytes
outputs/runs/20260630_full_asset_live_router_edit_dfce104f/viewer_export/scene_state.json 6376 bytes
outputs/runs/20260630_full_asset_live_router_edit_dfce104f/preview_render/preview.png 1085316 bytes
outputs/runs/20260630_full_asset_live_router_edit_dfce104f/preview_render/preview.blend 91321439 bytes
```

Verification:

```bash
python -m py_compile \
  agent_runtime/blender_mcp.py \
  agent_runtime/domain_dispatcher.py \
  agent_runtime/runtime_state_apply.py \
  agent_runtime/workflow_runner.py \
  agent_runtime/frontend_status.py \
  agent_runtime/runtime_audit.py \
  agent_runtime/runtime_runs.py \
  scripts/runtime_console_hydrated_smoke.py

node --check web/runtime_console/app.js

pytest -q \
  tests/test_frontend_status.py \
  tests/test_runtime_runs.py \
  tests/test_blender_mcp.py \
  tests/test_domain_dispatcher.py \
  tests/test_runtime_execution.py \
  tests/test_runtime_state_apply.py \
  tests/test_runtime_audit.py \
  tests/test_workflow_runner.py::test_local_e2e_workflow_dry_run_uses_single_project_state \
  tests/test_workflow_runner.py::test_local_e2e_workflow_uses_scene_spec_for_compose_plan \
  tests/test_workflow_runner.py::test_blender_edit_workflow_executes_socket_raw_caller_source \
  -p no:cacheprovider

python -m agent_runtime.runtime_audit \
  outputs/runs/20260630_full_asset_live_router_edit_dfce104f --json

python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_ui20 \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f
```

Results:

```text
targeted suite: 91 passed in 0.71s
runtime audit: ok=true, error_count=0, warning_count=0
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
preview_gate=true
viewer_embed_public=true
viewer_chinese_controls=true
viewer_export/scene_state.json subject_id=subject_plush asset_id=workflow_subject_glb
```

Runtime console:

```text
http://10.2.16.106:8093/
pid=2860221
ui_version=20260630-ui21
```

Artifacts:

```text
/tmp/image23d_ui20/hydrated_report.png
/tmp/image23d_ui20/viewer_embed.png
/tmp/image23d_ui20/hydrated_report.html
```

Boundary:

- This closes the full-asset edit -> viewer export -> preview render ->
  Blender-preview gate file chain for one real run. The current run still
  awaits explicit user preview approval before the formal delivery package is
  built from parent state.
- The run's legacy `state.subject_assets` and `state.scene_asset` fields remain
  empty because it was created before the semantic full-asset registration fix;
  `frontend_status.json`, `viewer_scene.objects`, artifacts, and future
  full-asset runs now carry the corrected asset ids.

## 2026-06-30 UI21 Preview-Gate Visibility Fix

Goal: make the waiting-for-approval state visible and actionable in the actual
runtime console, not only in JSON/smoke output.

Implementation:

- The Blender-preview user gate now shows readiness chips for:
  - `3D 预览已就绪`;
  - `Blender 工程已就绪`;
  - scene object count.
- The primary preview approval button now says `确认并打包交付`, making the next
  action explicit.
- The console keeps the Blender render preview PNG as a non-blocking
  `preview-fallback` thumbnail over the 3D iframe. This prevents a blank-looking
  dark canvas while the large GLB/model-viewer component is still loading.
- Fixed a runtime TDZ bug in `renderSceneObjectsPublic`: `focusUrl` is now
  computed before it is used in the public scene-object metadata. This removes
  the `can't access lexical declaration...` subtitle error and lets the page
  finish rendering.
- Bumped the public console cache key to `20260630-ui21`.

Verification:

```bash
node --check web/runtime_console/app.js
python -m py_compile scripts/runtime_console_hydrated_smoke.py
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_ui21 \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f
```

Results:

```text
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
preview_gate=true
preview_gate_copy_present=true
preview_image_fallback_present=true
```

Actual console screenshot:

```text
/tmp/image23d_ui21/runtime_console_waited_tdzfix.png
```

## 2026-06-30 UI22 Public Review Workbench Pass

Goal: respond to the front-end review feedback by turning the runtime console
from a sparse/debug-looking page into a clearer public review workbench while
reusing the existing runtime/file/JSON chain.

Implementation:

- Bumped the public console cache key to `20260630-ui22`.
- Kept the existing three-column runtime shell but tightened the visual density:
  stronger contrast, clearer five-stage roadmap, and an initial right rail
  order of `下一步 -> 阶段进度 -> 素材库 -> 场景内容 -> 验收与交付`. This was
  later adjusted by the object-submit pass to surface `场景内容` earlier.
- Fixed the right-rail stage timeline by overriding the old horizontal
  `grid-auto-flow: column`; stages now render as a vertical list instead of
  compressed vertical text.
- Enlarged the Blender preview PNG fallback while the large `viewer_scene.glb`
  iframe/model-viewer is still loading, so the user can see the current scene
  and subject model before the full 3D canvas finishes.
- Added a safe object-level feedback affordance in `场景内容`: `写修改意见`
  fills the composer with a Chinese object-adjustment draft. It does not execute
  Blender directly; the user still has to submit through the existing preview
  gate / `request_blender_changes` path.
- Extended the hydrated smoke script to verify UI22 assets, Chinese public shell
  labels, old English debug-string absence, preview-gate copy, fallback preview,
  and object-feedback draft controls.

Verification:

```bash
node --check web/runtime_console/app.js
python -m py_compile scripts/runtime_console_hydrated_smoke.py
python -m pytest tests/test_frontend_status.py tests/test_runtime_audit.py \
  tests/test_runtime_execution.py tests/test_workflow_runner.py \
  tests/test_domain_dispatcher.py tests/test_blender_mcp.py \
  tests/test_runtime_state_apply.py -q
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_ui22d \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f \
  --skip-firefox
```

Results:

```text
targeted pytest: 129 passed in 0.82s
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
served_expected_assets=true
public_shell_chinese=true
old_public_strings_absent=true
object_feedback_draft_present=true
viewer_chinese_controls=true
```

Actual console screenshots:

```text
/tmp/image23d_ui22d/runtime_console_ui22_waited.png
/tmp/image23d_ui22d/hydrated_report.html
```

Boundary:

- This is a public review-surface improvement and a safe object-feedback draft
  bridge. It still stops at the required Blender-preview user gate.
- Direct in-canvas picking and automatic object-edit execution from the web UI
  remain future work; the authoritative edit execution remains the existing
  `request_blender_changes -> BlenderEditRouter -> Blender edit/export/render`
  runtime path.

## 2026-06-30 UI22 Object Quick-Submit Bridge

Goal: make right-rail scene objects actionable without adding another edit API
or bypassing the existing Blender-preview user gate.

Implementation:

- Reused the existing `POST /api/runs/<run_key>/user-action` path and
  `request_blender_changes` mutation boundary.
- Refactored the preview/concept feedback submitter into a shared
  `submitFeedbackActionRequest(...)` helper, so gate feedback and object-card
  feedback both write chat evidence, call the same user-action endpoint, reload
  state, and refresh chat.
- Added `场景内容` object actions:
  - `聚焦查看`: opens the public viewer focused on the object;
  - `写草稿`: fills the composer with a Chinese object-level adjustment request;
  - `提交修改`: explicitly submits that object-level request as
    `对象修改意见` through `request_blender_changes`.
- Moved `场景内容` above `素材库` in the right rail and constrained the stage
  timeline height so object controls appear in the first viewport.
- Extended the hydrated smoke script with
  `object_feedback_submit_present=true`.

Verification:

```bash
node --check web/runtime_console/app.js
python -m py_compile scripts/runtime_console_hydrated_smoke.py
python -m pytest tests/test_runtime_user_actions.py tests/test_frontend_status.py -q
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_ui22_object_submit_final \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f \
  --skip-firefox
```

Results:

```text
pytest: 11 passed in 0.36s
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
object_feedback_draft_present=true
object_feedback_submit_present=true
old_public_strings_absent=true
```

Actual console screenshot:

```text
/tmp/image23d_ui22_object_submit/runtime_console_object_submit_visible.png
```

Boundary:

- The UI does not auto-run the Blender edit/export/render loop on page load or
  on behalf of the user. Clicking `提交修改` records explicit user feedback and
  moves the runtime to the existing `BLENDER_EDIT` plan path.
- True in-canvas picking, push refresh, and direct manipulation handles are
  still future work.

## 2026-06-30 UI23 Object Refresh Command Boundary

Goal: close the gap between object-level feedback and the existing
edit/export/render runtime loop without hiding non-dry Blender work behind a
passive UI action.

Implementation:

- Bumped the runtime-console cache/version key to `20260630-ui23`.
- Added a third object-card action, `生成预览`, next to `聚焦查看`, `写草稿`,
  and `提交修改`.
- `生成预览` is the explicit command boundary:
  - it first records object feedback through the existing chat +
    `request_blender_changes` user-action path;
  - it then calls the existing `/api/runs/<run_key>/loop` endpoint with
    `dry_run=false`, `max_steps=6`, and
    `blender_raw_caller_source="blender-lab-socket"`;
  - it reloads the run bundle/chat and reports the loop stop reason in the
    composer notice.
- The dev-only loop button remains dry-run by default; this pass does not turn
  hidden debug controls into accidental live execution.
- No new state store, edit API, viewer runtime, or Blender service wrapper was
  introduced.

Verification:

```bash
node --check web/runtime_console/app.js
python -m py_compile scripts/runtime_console_hydrated_smoke.py
python -m pytest \
  tests/test_runtime_loop.py::test_runtime_loop_routes_blender_feedback_into_edit_refresh \
  tests/test_runtime_loop.py::test_runtime_loop_live_blender_edit_refreshes_viewer_and_stops_at_preview_gate \
  tests/test_runtime_user_actions.py::test_request_blender_changes_routes_to_blender_edit_plan \
  tests/test_frontend_status.py -q
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_ui23_object_refresh \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f \
  --skip-firefox
```

Results:

```text
pytest: 8 passed in 0.62s
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
object_feedback_draft_present=true
object_feedback_submit_present=true
object_feedback_refresh_present=true
old_public_strings_absent=true
```

Actual console screenshot:

```text
/tmp/image23d_ui23_object_refresh/runtime_console_object_refresh_visible.png
```

Boundary:

- The real full-asset run was not mutated during verification; the screenshot
  and smoke prove the UI/runtime command path is present, while backend loop
  tests prove the edit-refresh semantics.
- A live user-click proof on the current full-asset run, in-canvas picking,
  push refresh, and direct manipulation handles remain future work.

## 2026-06-30 UI24 Bounded Run Polling Refresh

Goal: make long-running explicit runtime actions visibly refresh the current
run without adding a second state store or a new push service.

Implementation:

- Bumped the runtime-console cache/version key to `20260630-ui24`.
- Added reusable frontend helpers:
  - `refreshCurrentRunBundle(...)`;
  - `startRunRefreshPoll(...)`;
  - `stopRunRefreshPoll(...)`.
- `生成预览` now starts a bounded polling refresh while the existing non-dry
  `/loop` request is running. The poll refreshes the current run bundle, updates
  the stage/ribbon/object/file panels, occasionally refreshes chat, and reports
  the current phase/next action in the composer notice.
- `确认并打包交付` now starts the same polling layer while formal delivery is
  built. It waits for `DELIVERY` plus a ready delivery handoff/package before
  declaring the delivery state refreshed.
- The polling layer is client-side only and uses the existing
  `GET /api/runs/<run_key>` and chat APIs. It does not create a websocket,
  background queue, or alternate runtime state path.

Verification:

```bash
node --check web/runtime_console/app.js
python -m py_compile scripts/runtime_console_hydrated_smoke.py
python -m pytest \
  tests/test_runtime_loop.py::test_runtime_loop_routes_blender_feedback_into_edit_refresh \
  tests/test_runtime_loop.py::test_runtime_loop_live_blender_edit_refreshes_viewer_and_stops_at_preview_gate \
  tests/test_runtime_user_actions.py::test_request_blender_changes_routes_to_blender_edit_plan \
  tests/test_runtime_execution.py::test_preview_approval_then_delivery_step_builds_formal_package \
  tests/test_frontend_status.py -q
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --output-dir /tmp/image23d_ui24_poll \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f \
  --skip-firefox
```

Results:

```text
pytest: 9 passed in 0.63s
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
object_feedback_refresh_present=true
run_refresh_poll_present=true
old_public_strings_absent=true
```

Actual console screenshot:

```text
/tmp/image23d_ui24_poll/runtime_console_ui24_poll_visible.png
```

Boundary:

- This closes a polling-based live refresh layer for explicit runtime actions.
- It is not a true websocket/push channel, and it does not prove a real
  user-click object refresh on the full-asset run.

## 2026-06-30 UI25 Creator Workbench Skin And Static Route Fix

Goal: replace the still-debug-looking public console with a cleaner
creator-workbench surface and make sure the browser actually receives the new
skin.

Implementation:

- Bumped the runtime-console cache/version key to `20260630-ui25`.
- Added `web/runtime_console/ui25_creator.css` as a product-facing skin inspired
  by mature chat/workbench shells: left creation history, central request and
  preview surface, and right-side stage/assets/delivery context.
- Moved the right rail emphasis from internal status dumps to `创作阶段`,
  `下一步`, `阶段进度`, `场景内容`, `素材库`, and `验收与交付`.
- Fixed preview-gate semantics so `needs_user_action` makes the active stage
  read `待你确认`; the next-action card now says `请验收当前 3D 场景` on
  preview-ready runs.
- Renamed the public preview action buttons to
  `确认当前预览并打包` and `输入修改意见再调整`.
- Fixed a real serving bug: the new CSS file must be whitelisted in
  `tools/runtime_console_server.py`; otherwise the browser keeps showing the
  older UI even though `index.html` references the new file.
- Restarted the runtime console so port `8093` serves the new static route.

Verification:

```bash
node --check web/runtime_console/app.js
python -m py_compile scripts/runtime_console_hydrated_smoke.py tools/runtime_console_server.py tools/glb_viewer_server.py
python -m pytest tests/test_frontend_status.py tests/test_runtime_console.py tests/test_glb_viewer_server.py -q
curl -s -o /tmp/ui25_creator.css.check -w '%{http_code} %{content_type}\n' \
  'http://127.0.0.1:8093/ui25_creator.css?v=ui25-check'
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f \
  --output-dir /tmp/image23d_ui25_creator_served
```

Results:

```text
pytest: 13 passed in 1.36s
static css: 200 text/css; charset=utf-8
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
served_expected_assets=true
ui25_creator_skin_present=true
preview_gate_copy_present=true
old_public_strings_absent=true
viewer_embed_public=true
viewer_chinese_controls=true
```

Evidence:

```text
/tmp/image23d_ui25_creator_served/summary.json
/tmp/image23d_ui25_creator_served/hydrated_report.png
/tmp/image23d_ui25_creator_served/viewer_embed.png
```

Boundary:

- This is a public UI/product-shell correction plus a static serving fix. It
  does not add a new frontend framework, state store, viewer runtime, or model
  generation path.
- In-canvas object picking, true server-push refresh, and live user-click proof
  for object refresh still remain.

## 2026-06-30 UI26 Viewer Object Selection Bridge

Goal: make the existing 8092 GLB viewer participate in object-level review
without replacing the viewer runtime or adding a parallel state store.

Implementation:

- Extended `tools/glb_viewer_server.py` to read an adjacent
  `scene_state.json` for public viewer pages and expose only a small path-free
  object summary:
  `viewer_object_id`, `blender_object_id`, `display_name`, type, subject/asset
  ids, and bounds.
- The embedded object summary is emitted as script-safe raw JSON, not
  HTML-entity JSON, so browser-side `JSON.parse(...)` can actually use it.
- Added viewer-side object chips and a best-effort canvas click picker:
  - chip clicks select a known object directly;
  - canvas clicks use `model-viewer.positionAndNormalFromPoint` when available
    and map the hit point to the nearest object bounds;
  - the selected object is focused with existing `camera-target` /
    `camera-orbit` semantics.
- Added a parent-window message bridge:
  `image23d.viewer.objectSelected`.
- Extended `web/runtime_console/app.js` so the 8093 console receives the viewer
  message, matches it against `scene_state.objects`, highlights the right-side
  scene object card, and fills the composer with the existing
  `objectFeedbackDraft(...)` text when the composer is empty.
- Added selected-object styling in both `ui19_public.css` and
  `ui25_creator.css`.
- Bumped the runtime-console cache/version key to `20260630-ui26` so browsers
  fetch the updated message bridge.
- Restarted the 8092 GLB viewer service after updating its server code.

Verification:

```bash
node --check web/runtime_console/app.js
python -m py_compile tools/glb_viewer_server.py scripts/runtime_console_hydrated_smoke.py tools/runtime_console_server.py
python -m pytest tests/test_glb_viewer_server.py tests/test_frontend_status.py tests/test_runtime_console.py -q
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f \
  --output-dir /tmp/image23d_ui26_object_pick_final \
  --skip-firefox
```

Results:

```text
pytest: 15 passed in 1.88s
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
viewer_object_selection_bridge_present=true
viewer_embed_public=true
viewer_debug_text_absent=true
viewer_bare_home_absent=true
direct viewer HTML check: sceneObjectsJson=true, objectSelected=true,
objectPicker=true, html_entity_quotes=false, bare_home=false
```

Evidence:

```text
/tmp/image23d_ui26_object_pick_final/summary.json
http://10.2.16.106:8092/viewer?... contains sceneObjectsJson, objectPicker,
and image23d.viewer.objectSelected without embedding the raw source_blend_path.
```

Boundary:

- This closes the first object-selection bridge between the existing viewer
  and runtime console.
- The canvas selection is bounds-based and best-effort, not guaranteed exact
  mesh-name picking.
- True websocket/server-push refresh and a live user-click object edit/preview
  generation proof on the full-asset run still remain.

## 2026-06-30 UI27 Server-Push Refresh

Goal: replace the review surface's passive-only refresh behavior with a real
server-push channel while keeping the existing polling path as a fallback for
explicit long-running actions.

Implementation:

- Added `GET /api/runs/<run_key>/events` to `tools/runtime_console_server.py`.
- The endpoint serves Server-Sent Events with:
  - `event: ready` when the stream opens;
  - `event: refresh` when watched run artifacts change;
  - `event: heartbeat` for long-lived connections.
- The event signature watches mtime/size for run-local control and preview
  files such as `state.json`, `frontend_status.json`, `summary.json`,
  runtime JSON/JSONL evidence, `delivery_handoff.json`, `viewer_export/*`,
  `preview_render/*`, and delivery zips. It does not read model or preview
  file contents.
- `web/runtime_console/app.js` now opens an `EventSource` for the selected run,
  refreshes the current run bundle/chat on `refresh`, and closes/reopens the
  stream when the selected run changes.
- Existing bounded polling for `生成预览` and `确认当前预览并打包` remains in
  place as an explicit-action fallback.
- Bumped the runtime-console cache/version key to `20260630-ui27`.
- Restarted the 8093 runtime console service after updating server code.

Verification:

```bash
python -m py_compile tools/runtime_console_server.py scripts/runtime_console_hydrated_smoke.py
node --check web/runtime_console/app.js
python -m pytest tests/test_runtime_console_server.py tests/test_runtime_console.py tests/test_frontend_status.py -q
python scripts/runtime_console_hydrated_smoke.py \
  --console-url http://127.0.0.1:8093 \
  --expected-run-id 20260630_full_asset_live_router_edit_dfce104f \
  --output-dir /tmp/image23d_ui27_sse \
  --skip-firefox
python -m pytest -q
```

Results:

```text
targeted pytest: 11 passed in 0.87s
full pytest: 336 passed in 4.48s
hydrated smoke: ok=true
selected_run_id=20260630_full_asset_live_router_edit_dfce104f
phase=BLENDER_PREVIEW
run_event_stream_present=true
direct /events check: content-type=text/event-stream; event_ready=true
```

Evidence:

```text
/tmp/image23d_ui27_sse/summary.json
http://127.0.0.1:8093/api/runs/<run_key>/events?max_seconds=0.2&interval=0.2
```

Boundary:

- This closes the server-push refresh layer for the runtime console using SSE.
- It is not a bidirectional WebSocket channel.
- Exact mesh-level picking and live user-click object edit/preview generation
  proof on the full-asset run still remain.

## 2026-06-30 UI28 Assembly Plan Camera Target

Goal: move the SceneSpec-driven Blender assembly plan one step past smoke-level
placement without creating a second Blender composition pipeline.

Implementation:

- Extended `ComposeScenePlan` with `camera_target_normalized`.
- `build_compose_scene_plan(...)` now combines horizontal and depth placement
  hints before selecting a region, so requests like `right side foreground`
  become a true `front_right` plan with a foreground Y offset.
- Camera target offset now follows the planned subject region with different
  strengths for close/portrait, default, and wide/full-scene framing.
- Render resolution now responds to `square` / `vertical portrait` / `wide
  landscape` SceneSpec camera hints while preserving the default 1400x900
  preview when no aspect hint exists.
- `tools/compose_blender_scene.py` consumes the optional
  `camera_target_normalized` field and aims the orthographic preview camera at
  the shifted target. Old assembly plans without the field still run with the
  previous center target.
- Updated `docs/blender_asset_pipeline_contract.md` to document the new
  optional field and its backward-compatible behavior.

Verification:

```bash
python -m py_compile agent_runtime/blender_assembly_planner.py tools/compose_blender_scene.py
python -m pytest tests/test_blender_assembly_planner.py \
  tests/test_workflow_runner.py::test_local_e2e_workflow_uses_scene_spec_for_compose_plan -q
python -m pytest tests/test_blender_assembly_planner.py tests/test_workflow_runner.py tests/test_script_adapters.py -q
python -m pytest -q
python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_full_asset_live_router_edit_dfce104f/artifacts/scene_3d_asset/workflow_scene_glb.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_full_asset_live_router_edit_dfce104f/artifacts/subject_3d_asset/workflow_subject_glb.glb \
  --scene-spec-json /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_blender_socket_edit_refresh_scratch_20260630T025222/scene_spec.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui28_assembly_plan_dryrun \
  --blender-path /home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender \
  --dry-run \
  --stages compose
```

Results:

```text
5 passed in 0.50s
59 passed in 0.55s
338 passed in 4.81s
dry-run workflow: ok=true, executed_stages=["compose"],
assembly_plan_json=outputs/runs/20260630_ui28_assembly_plan_dryrun/compose/assembly_plan.json,
camera_target_normalized=[-0.072, 0.072]
```

Evidence:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui28_assembly_plan_dryrun/summary.json
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui28_assembly_plan_dryrun/compose/assembly_plan.json
```

Boundary:

- This is still deterministic SceneSpec-to-compose planning, not a full
  LLM/MCP assembly planner.
- It improves layout/camera semantics for the existing compose/export path and
  keeps Blender execution behind the same script/domain-tool boundary.

## 2026-06-30 UI29 Runtime Assembly Planner Apply Bridge

Goal: close the runtime gap where `BlenderAssemblyPlanner` had a prompt/schema
and context, but a completed candidate could not yet become executable Blender
assembly work.

Implementation:

- Added `AgentProjectState.blender_assembly_plan` as the authoritative stored
  `BlenderAssemblyPlan` candidate.
- Added `BlenderAssemblyPlanner` as the mutation owner for that field.
- `runtime_state_apply.apply_next_runtime_candidate(...)` now supports
  completed `BlenderAssemblyPlanner` records, validates them with Pydantic,
  writes `state.blender_assembly_plan`, advances to
  `BLENDER_ASSEMBLY_EXECUTION`, checkpoints, refreshes `frontend_status.json`,
  and rebuilds `runtime_plan.json`.
- `controller.build_controller_plan(...)` now schedules `BlenderAssemblyPlanner`
  only when no assembly plan exists. Once a plan exists, it schedules the
  existing script-backed `import_scene_asset` domain tool with artifact/plan ids.
- `runtime_execution.execute_next_runtime_job(...)` now treats
  `import_scene_asset` as a runtime script-backed domain tool, resolves scene
  and subject GLBs from state/artifacts, writes a run-local
  `compose/runtime_assembly_plan.json`, and calls the existing
  `ScriptDomainToolDispatcher`.
- Added a bridge from `BlenderAssemblyPlan` to `ComposeScenePlan` so LLM output
  is normalized into the compose-script contract instead of being passed to
  Blender directly.
- Non-dry-run `import_scene_asset` can now register the produced `.blend` and
  preview PNG as artifacts and update `BlenderSceneState` through the existing
  state mutation guard.

Verification:

```bash
python -m py_compile agent_runtime/state.py agent_runtime/state_views.py \
  agent_runtime/blender_assembly_planner.py agent_runtime/controller.py \
  agent_runtime/runtime_state_apply.py agent_runtime/runtime_execution.py \
  agent_runtime/runtime_jobs.py
python -m pytest \
  tests/test_controller.py::test_controller_executes_existing_blender_assembly_plan_with_import_scene_asset \
  tests/test_runtime_state_apply.py::test_runtime_state_apply_blender_assembly_planner_records_plan_and_schedules_import \
  tests/test_runtime_execution.py::test_runtime_execution_dry_runs_import_scene_asset_from_assembly_plan \
  tests/test_runtime_execution.py::test_runtime_execution_live_import_scene_asset_registers_blender_scene \
  tests/test_blender_assembly_planner.py -q
python -m pytest tests/test_state.py tests/test_state_views.py tests/test_controller.py \
  tests/test_runtime_jobs.py tests/test_runtime_state_apply.py \
  tests/test_runtime_execution.py tests/test_runtime_loop.py \
  tests/test_blender_assembly_planner.py -q
python -m pytest -q
```

Results:

```text
8 passed in 0.44s
63 passed in 0.94s
342 passed in 4.95s
```

Boundary:

- This closes the candidate-apply and script-job bridge for assembly planning.
- It does not claim mature visual layout intelligence or a fresh non-dry-run
  full-asset preview using a live provider plan.

## 2026-06-30 UI30 Compose Subject Orientation Contract

Goal: reduce the assembly-planner semantic loss between natural-language/LLM
placement instructions and the existing Blender compose script. Before this
slice, the richer compose plan carried placement, scale, camera target, and
render aspect, but did not carry subject-facing/orientation.

Implementation:

- Extended `ComposeScenePlan` with `subject_yaw_degrees` and
  `orientation_reason`.
- The deterministic SceneSpec planner now infers yaw from explicit orientation
  hints such as facing the camera, back-to-camera, left/right profile, and
  facing the scene center.
- The `BlenderAssemblyPlan` bridge now preserves explicit
  `PlacementPlan.transform_hint.rotation_euler.z` as the strongest yaw signal,
  then falls back to placement/relation/composition text.
- `tools/compose_blender_scene.py` now consumes optional
  `subject_yaw_degrees` and applies a Z-axis rotation around the imported
  subject asset center before scale normalization and placement.
- The runtime assembly dry-run test now proves `subject_yaw_degrees` survives
  `BlenderAssemblyPlan -> compose/runtime_assembly_plan.json`.
- Updated `docs/blender_asset_pipeline_contract.md` with the optional yaw
  field and backward-compatible behavior.

Verification:

```bash
python -m py_compile agent_runtime/blender_assembly_planner.py tools/compose_blender_scene.py
python -m pytest tests/test_blender_assembly_planner.py -q
python -m pytest tests/test_script_adapters.py tests/test_domain_dispatcher.py \
  tests/test_workflow_runner.py::test_local_e2e_workflow_uses_scene_spec_for_compose_plan \
  tests/test_runtime_execution.py::test_runtime_execution_dry_runs_import_scene_asset_from_assembly_plan -q
python -m pytest tests/test_runtime_execution.py::test_runtime_execution_dry_runs_import_scene_asset_from_assembly_plan \
  tests/test_runtime_execution.py::test_runtime_execution_live_import_scene_asset_registers_blender_scene -q
python -m pytest -q
```

Results:

```text
6 passed in 0.32s
40 passed in 0.40s
2 passed in 0.55s
344 passed in 4.54s
```

Boundary:

- This improves placement/orientation semantics in the existing script-backed
  Blender path.
- It does not yet provide mesh-aware collision placement, a live-provider
  `BlenderAssemblyPlanner` call, or the new non-dry-run full-asset preview.

## 2026-06-30 UI31 Full-Asset Yaw Non-Dry-Run Preview

Goal: close the Step 8 evidence gap for a new non-dry-run full-asset preview
using the richer compose plan, including subject orientation.

Implementation and findings:

- Reused the full-asset scene/subject GLBs from
  `outputs/runs/20260630_full_asset_live_router_edit_dfce104f/artifacts/`.
- Generated a run-local SceneSpec copy that asks for the subject in the right
  foreground facing the scene center.
- Refreshed infrastructure inventory before execution:
  `ok=true`, required `20/20` present.
- First non-dry-run surfaced a real semantic bug: `face/toward scene center`
  let the placement parser read `center` as a placement request, producing
  `target_region=center` and `subject_yaw_degrees=0`.
- Fixed `_placement_from_text(...)` ordering so composite foreground/background
  plus left/right placement wins before generic center placement, while
  `center foreground` remains centered.
- Added a regression test for right-foreground placement with orientation
  mentioning scene center.

Non-dry-run command:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m agent_runtime.workflow_runner local-e2e \
  --root /home/team/zouzhiyuan/image23D_Agent \
  --scene-glb /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_full_asset_live_router_edit_dfce104f/artifacts/scene_3d_asset/workflow_scene_glb.glb \
  --asset-glb /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_full_asset_live_router_edit_dfce104f/artifacts/subject_3d_asset/workflow_subject_glb.glb \
  --scene-spec-json /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui31_full_asset_yaw_nondryrun_fixed/scene_spec_yaw.json \
  --output-dir /home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui31_full_asset_yaw_nondryrun_fixed \
  --blender-path /home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender \
  --viewer-base-url http://127.0.0.1:8092 \
  --compose-timeout 420 \
  --export-timeout 240 \
  --viewer-timeout 10 \
  --stages compose,export_viewer,viewer_check \
  --no-reset-metadata
```

Result:

```text
summary.ok=true
dry_run=false
executed_stages=["compose", "export_viewer", "viewer_check"]
phase=BLENDER_PREVIEW
target_region=front_right
target_region_normalized=[0.24, -0.24]
subject_yaw_degrees=90.0
camera_target_normalized=[0.132, -0.132]
viewer_check.ok=true
delivery_handoff.ready=true
delivery_handoff.verified=true
viewer_scene_object_count=7
preview_png=1400x900, nonblank
```

Evidence:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui31_full_asset_yaw_nondryrun_fixed/summary.json
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui31_full_asset_yaw_nondryrun_fixed/compose/assembly_plan.json
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui31_full_asset_yaw_nondryrun_fixed/compose/composed_preview.png
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui31_full_asset_yaw_nondryrun_fixed/compose/composed_scene.blend
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui31_full_asset_yaw_nondryrun_fixed/viewer_export/viewer_scene.glb
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui31_full_asset_yaw_nondryrun_fixed/viewer_export/scene_state.json
```

Verification:

```bash
python -m py_compile agent_runtime/blender_assembly_planner.py tools/compose_blender_scene.py
python -m pytest tests/test_blender_assembly_planner.py -q
python -m pytest tests/test_blender_assembly_planner.py \
  tests/test_workflow_runner.py::test_local_e2e_workflow_uses_scene_spec_for_compose_plan \
  tests/test_runtime_execution.py::test_runtime_execution_dry_runs_import_scene_asset_from_assembly_plan -q
python -m pytest -q
```

Results:

```text
7 passed in 0.42s
9 passed in 0.45s
345 passed in 4.59s
```

Boundary:

- This proves the richer deterministic compose plan can drive a real
  full-asset Blender compose/export/viewer-check run.
- Visual quality is still not final: mesh/collision-aware layout and stronger
  scene/asset quality tuning remain open.
- This is still deterministic SceneSpec planning evidence, not a live-provider
  `BlenderAssemblyPlanner` call.

## 2026-06-30 UI32 User-Provided Scenario And Review Branch Fixtures

Goal: add the user's three concrete scenario prompts to the runtime fixture
matrix and simulate both acceptance and rejection at review gates.

Implementation:

- Stored the uploaded Little Gwen reference image in the repo fixture area:
  `tests/fixtures/images/little_gwen_reference.png` (`1080x810`, RGB PNG).
- Added three natural-language cases to
  `tests/fixtures/natural_language_scene_cases.json`:
  - `scenario_zh_wuthering_chibi_beach_duo`: chibi Phoebe/Fronono-inspired
    beach duo with beach chair and sand castle props.
  - `scenario_zh_little_gwen_chessboard_ref`: image-1-bound chibi Little
    Gwen-inspired subject on a chessboard with many chess pieces.
  - `scenario_zh_explorer_rover_moon_regolith`: explorer robot rover on the
    moon beside pitted lunar regolith.
- Added fixture coverage assertions proving the new case ids, subject ids, and
  Little Gwen image binding are present.
- Added a runtime user-action simulation test covering:
  - concept approval for the beach duo sample;
  - concept rejection/feedback patch for the Little Gwen image-reference sample;
  - Blender preview approval for the lunar rover sample;
  - Blender preview rejection/edit feedback for the beach layout sample.

Verification:

```bash
python -m pytest \
  tests/test_natural_language_scene_fixtures.py::test_natural_language_fixture_matrix_includes_user_requested_samples \
  tests/test_natural_language_scene_fixtures.py::test_natural_language_scene_cases_run_to_delegated_generation -q
python -m pytest tests/test_runtime_user_actions.py::test_user_requested_samples_cover_accept_and_reject_review_branches -q
python -m pytest tests/test_natural_language_scene_fixtures.py tests/test_runtime_user_actions.py \
  tests/test_blender_assembly_planner.py -q
python -m py_compile agent_runtime/blender_assembly_planner.py tools/compose_blender_scene.py \
  agent_runtime/scenario_fixtures.py agent_runtime/runtime_user_actions.py
python -m pytest -q
```

Results:

```text
10 passed in 0.76s
1 passed in 0.36s
26 passed in 0.77s
350 passed in 4.76s
```

Boundary:

- These are structured runtime fixtures and review-action simulations, not live
  image generation or live 3D generation.
- They keep the existing runtime loop as the execution surface and make the
  prompt/schema/user-gate behavior inspectable for the user's concrete cases.
