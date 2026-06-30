# Agent Runtime Contract

## Runtime Role

The runtime is responsible for state, scheduling, profiles, handoff surfaces,
and verification boundaries. It should not spend the main agent loop waiting on
long model jobs when those jobs can be delegated to a background worker or
sub-agent.

Existing services and viewers remain authoritative:

- Hunyuan3D FastAPI service: `http://127.0.0.1:8091`
- HY-World/WorldMirror: `http://127.0.0.1:8081`
- GLB viewer: `http://127.0.0.1:8092`
- Blender Web Docker, when running: `http://127.0.0.1:8300` and
  `https://127.0.0.1:8301`
- Blender Lab MCP bridge: `127.0.0.1:9876`

## Runtime Job Plan

`agent_runtime.runtime_jobs.build_agent_runtime_plan(...)` converts
`build_controller_plan(state)` into `RuntimeJobSpec` records.

Each job states:

- phase and reason;
- job kind: LLM node, domain tool, user gate, delivery, or stop;
- executor: main runtime, background worker, sub-agent, user, or external
  service;
- whether it is long-running and blocks the next runtime transition;
- profile id and tool arguments when a service generation profile applies;
- command hint only as an operator/debug aid, not as the source of truth.

Long-running generation jobs should normally use a sub-agent or background
worker:

- `generate_concept_images`
- `regenerate_concept_images`
- `build_subject_asset`
- `build_scene_asset`

The main runtime should focus on planning, state mutation, checkpoints, and
front-end handoff.

## Hunyuan3D Profiles

`agent_runtime.runtime_profiles` defines named presets for the existing
Hunyuan3D service. The current service is started with texture resolution `768`
and max view count `8`; per-request generation still controls octree
resolution, steps, chunks, face count, texture enablement, and seed behavior.

Profiles:

- `hq_textured_1m_768`: default high-quality textured run,
  `texture=true`, `octree_resolution=768`, `num_inference_steps=50`,
  `face_count=1000000`.
- `hq_shape_1m_768`: high-quality shape-only run with the same geometry scale.
- `fast_shape_50k_768`: smoke profile,
  `texture=false`, `num_inference_steps=30`, `face_count=50000`.
- `draft_shape_100k_512`: draft profile for faster iteration.

`workflow_runner subject-asset` accepts:

```text
--hunyuan-profile
--octree-resolution
--num-chunks
--remove-background/--no-remove-background
--texture/--no-texture
--face-count
--num-inference-steps
--guidance-scale
--seed
--randomize-seed/--no-randomize-seed
```

Explicit CLI values override profile defaults.

## Front-End Handoff

`agent_runtime.runtime_runs` provides read-only helpers for existing run
directories:

- discover `outputs/runs/<run_id>/`;
- read `state.json`, `summary.json`, `frontend_status.json`,
  `delivery_handoff.json`, and `scene_state.json`;
- rewrite local service URLs such as `127.0.0.1:8092` to public browser URLs;
- build `RuntimeWebSurface` that points to existing GLB viewer and Blender Web
  surfaces.

This is not a new UI state store. The source of truth remains:

- `AgentProjectState` in `state.json`;
- checkpoint snapshots and event/index JSONL files;
- workflow summaries;
- artifact records.

## Runtime Console MVP

The first browser runtime console is a thin control/read surface, not a second
workflow runtime:

- server: `tools/runtime_console_server.py`
- static UI: `web/runtime_console/`
- lifecycle scripts:
  - `scripts/start_runtime_console.sh`
  - `scripts/status_runtime_console.sh`
  - `scripts/stop_runtime_console.sh`
- default local/public URL: `http://127.0.0.1:8093/` /
  `http://10.2.16.106:8093/`

The console currently supports:

- listing existing `outputs/runs/<run_id>/` directories and visual child stages
  such as `outputs/runs/<run_id>/blender_viewer/`;
- creating an intake-only runtime run with `state.json`, `summary.json`, and
  `frontend_status.json`;
- appending chat messages to `runtime_console/chat.jsonl`;
- mirroring user messages into `AgentProjectState.user_turns`;
- uploading reference images to `runtime_console/uploads/`;
- registering uploaded images as `INPUT_IMAGE` artifacts and
  `AgentProjectState.input_images`;
- embedding the existing GLB viewer URL for `viewer_scene.glb`;
- exposing delivery links, object lists, and status derived from
  `state.json`, `frontend_status.json`, `delivery_handoff.json`, and
  `scene_state.json`.
- building a non-executing controller/runtime job plan with
  `POST /api/runs/<run_key>/plan`, saved as `runtime_plan.json`.
- executing one safe runtime step with `POST /api/runs/<run_key>/step`, saved
  as `runtime_execution.jsonl`, `runtime_execution_summary.json`, and
  per-step JSON under `runtime_execution/`.
- applying the next validated LLM candidate with
  `POST /api/runs/<run_key>/apply`, saved as `runtime_apply.jsonl`,
  `runtime_apply_summary.json`, checkpoint snapshots, refreshed
  `frontend_status.json`, and a rebuilt `runtime_plan.json`.
- running a conservative bounded dispatcher loop with
  `POST /api/runs/<run_key>/loop`, saved as `runtime_loop.jsonl` and
  `runtime_loop_summary.json`. The loop repeats `step -> apply -> rebuild
  plan` until it reaches a user gate, delegated long job, blocked/failed job,
  dry-run-without-live-output boundary, no remaining jobs, or the caller's
  step budget.
- planning a delegated worker/sub-agent handoff with
  `POST /api/runs/<run_key>/handoff`, saved as `runtime_handoff.jsonl`,
  `runtime_handoff_summary.json`, and individual JSON packages under
  `runtime_handoff/`. This records inputs, expected outputs, command hints,
  and task prompts for long jobs without executing those jobs in the console
  request.
- executing or dry-running the next planned worker/sub-agent handoff with
  `POST /api/runs/<run_key>/worker`, saved as `runtime_worker.jsonl`,
  `runtime_worker_summary.json`, and per-attempt JSON under
  `runtime_worker/`. The default console action uses a dry-run fixture adapter,
  so it records the selected handoff without mutating state. Confirmed worker
  execution still sends outputs through the existing `handoff-apply` functions;
  this is execution evidence, not a second queue or state source.
  Supported worker backends are:
  - `fixture`: deterministic local payload adapter for tests and explicit
    result registration;
  - `codex_self_mcp`: guarded live codex-self call planning/execution, with
    non-dry-run execution requiring `confirm_execute=true`;
  - `codex_self_log`: completed codex-self MCP JSONL image-log ingestion. The
    caller passes `fixture_payload.log_path`; the runtime decodes the last
    image-generation result, writes the extracted image under `runtime_worker/`
    by default, and applies it through the concept-image handoff path.
- applying explicit concept-review user gates with
  `POST /api/runs/<run_key>/user-action`, saved as
  `runtime_user_action.jsonl`, `runtime_user_action_summary.json`, checkpoints,
  refreshed `frontend_status.json`, and a rebuilt `runtime_plan.json`.
  Supported actions are:
  - `approve_concept`: requires `CONCEPT_REVIEW` plus at least one concept
    image, marks the current `ConceptBundle` approved, advances the run to
    `CONCEPT_APPROVED`, and rebuilds the plan toward `build_subject_asset`;
  - `request_concept_changes`: requires explicit feedback text, writes a
    pending `ReviewPatch` with lineage to the user turn/action, keeps the run
    in `CONCEPT_REVIEW`, and rebuilds the plan toward concept regeneration.
- the same user-action route handles `BLENDER_PREVIEW` gates:
  - `approve_blender_preview`: requires `BLENDER_PREVIEW`, `blender_scene`,
    and `viewer_scene`, advances the run to `DELIVERY`, checkpoints, refreshes
    status, and rebuilds the plan to the delivery action;
  - `request_blender_changes`: requires explicit feedback text, writes a
    pending `ReviewPatch` with Blender/viewer lineage, moves the run to
    `BLENDER_EDIT`, and rebuilds the plan toward
    `BlenderEditRouter -> export_viewer_scene -> render_preview`.
- applying a completed `BlenderEditRouter` candidate can now store concrete
  planned Blender domain-tool calls in
  `ReviewPatch.structured_delta["blender_edit_plan"]`. The controller reuses
  those calls on the next `BLENDER_EDIT` plan, scheduling safe edit tools such
  as `move_subject` before `export_viewer_scene` and `render_preview`. The
  main runtime dry-run path maps these planned edit tools through
  `agent_runtime.blender_mcp.build_safe_blender_mcp_operation_plan(...)`,
  recording the constrained raw MCP operation plan without executing live
  Blender edits.
- non-dry-run Blender edit runtime execution is also wired, but it requires an
  explicit raw-caller boundary. `execute_next_runtime_job(..., dry_run=False)`
  stays blocked unless the caller injects `blender_raw_tool_caller` or passes
  `blender_raw_caller_source="blender-lab-socket"`. When enabled, the runtime
  reuses `BlenderMCPDomainToolDispatcher`, writes updated `state.json`,
  checkpoint, `summary.json`, `frontend_status.json`, execution output JSON,
  and leaves the current `runtime_plan.json` in place so the already-planned
  viewer refresh jobs continue after the completed edit job.
- applying a completed concept-image handoff result with
  `POST /api/runs/<run_key>/handoff-apply`, saved as
  `runtime_handoff_apply.jsonl` and
  `runtime_handoff_apply_summary.json`. This registers worker-provided concept
  image files through `FileArtifactStore`, updates `ConceptBundle`, writes a
  checkpoint/front-end status snapshot, and rebuilds the next plan.
- the same `handoff-apply` route can apply completed subject-asset handoff
  results when the request contains `asset_results`. This registers
  worker-provided GLB files as `SUBJECT_3D_ASSET`, updates
  `AgentProjectState.subject_assets`, writes a checkpoint/front-end status
  snapshot, and rebuilds the next plan.
- the same `handoff-apply` route can apply completed scene/world handoff
  results when the request contains `scene_asset_results`. This registers a
  worker-provided WorldMirror/HY-World output directory through the existing
  scene-asset adapter, updates `AgentProjectState.scene_asset`, moves the run
  to `SCENE_ASSET_ADAPTATION`, writes checkpoint/front-end status, and rebuilds
  the next plan toward Blender assembly.
- the same `handoff-apply` route can apply Blender/viewer worker outputs when
  the request contains `blender_results`. This registers `.blend`,
  `viewer_scene.glb`, optional `scene_state.json`, and optional preview render
  artifacts, updates `AgentProjectState.blender_scene` and `viewer_scene`, moves
  the run to `BLENDER_PREVIEW`, and rebuilds the next plan as a user approval
  gate.

Runtime execution step contract:

- user gates are recorded as `waiting_user` and do not mutate state;
- ordinary `main_runtime` LLM jobs can be dry-run by default through
  `agent_runtime.llm_nodes`, producing a prompt/context/result JSON artifact;
- long-running, background-worker, and sub-agent jobs are recorded as
  `delegated` with command/profile hints instead of being hidden inside the
  request thread;
- unsupported main-runtime jobs are recorded as `blocked`;
- `state.json` remains the fact source. LLM dry-run/live outputs are candidate
  artifacts until a controlled state mutation path applies them.
- only `completed` execution records count as handled for current job
  selection. `dry_run`, `waiting_user`, `delegated`, and `blocked` records are
  durable evidence, but they do not hide the same still-current job on a later
  retry.
- `SceneSpecCompiler` may consume a prior `SceneInterpreter` candidate only
  when that candidate was completed successfully and its recorded context
  matches the current latest user turn. Stale interpretation output from an
  older turn must not silently feed a new scene spec.

Worker result apply payload examples:

```json
{
  "scene_asset_results": [
    {
      "output_dir": "/path/to/worldmirror_output",
      "scene_asset_id": "scene_asset_001",
      "source_scene_concept_image_ids": ["scene_concept_001"],
      "source_prompt": "simple clean studio scene"
    }
  ]
}
```

```json
{
  "blender_results": [
    {
      "blend_path": "/path/to/scene.blend",
      "viewer_scene_path": "/path/to/viewer_scene.glb",
      "scene_state_json_path": "/path/to/scene_state.json",
      "preview_image_path": "/path/to/preview.png",
      "blender_scene_id": "blender_scene_001",
      "viewer_scene_id": "viewer_scene_001"
    }
  ]
}
```

Runtime state-apply contract:

- only completed execution records with parsed JSON can be applied;
- dry-run results, user gates, delegated long jobs, and missing outputs are not
  written into state;
- currently supported apply nodes include `ReferenceBindingValidator`,
  `SceneSpecCompiler`, `ConceptPromptPlanner`, `FeedbackPatchParser`,
  `RegenerationRouter`, `BlenderAssemblyPlanner`, and `BlenderEditRouter`;
- `BlenderAssemblyPlanner` candidates write `state.blender_assembly_plan`,
  move the run to `BLENDER_ASSEMBLY_EXECUTION`, and rebuild
  `runtime_plan.json` toward the existing script-backed
  `import_scene_asset` domain tool. The runtime normalizes that plan into the
  compose-script `assembly_plan.json` contract, including optional subject
  yaw/orientation, before Blender execution;
- successful apply writes `state.json`, `summary.json`,
  `frontend_status.json`, `runtime_apply.jsonl`,
  `runtime_apply_summary.json`, and a checkpoint snapshot under
  `checkpoints/`;
- after a successful apply, `runtime_plan.json` is rebuilt from the updated
  state.

UI layout contract:

- narrow left nav: creator/generation/asset/scene navigation affordances;
- left column: run navigation and run creation/refresh controls;
- center column: embedded 3D preview plus chat/reference-image composer;
- right column: Chinese phase hero/timeline, next action, asset readiness, and
  delivery links;
- developer details: raw status, runtime plan/jobs, objects, file manifest
  paths, and other technical evidence stay behind the default-closed
  `开发详情` panel.

Run/file routing contract:

- API routes use `run_key`, a URL-safe encoded relative run path, so child
  stages can be selected without unsafe slashes in the route.
- `RuntimeRunBundle.run_dir` is the selected parent/stage directory.
- `RuntimeRunBundle.effective_run_dir` is the directory actually used for
  `state.json`, `summary.json`, `frontend_status.json`,
  `delivery_handoff.json`, `scene_state.json`, and viewer lookup.
- Passing a parent run to `build_runtime_run_bundle(...)` may resolve
  `effective_run_dir` to its best visual child stage, currently prioritizing
  directories with `viewer_scene.glb`, `scene_state.json`, and
  `delivery_handoff.json`.
- `file_manifest.files` returns structured file records with `label`,
  `exists`, `path`, `relative_path`, `size_bytes`, and `url`.
- JSON files are exposed through the console's safe run-local
  `/api/runs/<run_key>/file?path=...` endpoint; GLB/glTF files point to the
  existing GLB viewer.
- `runtime_plan.json` contains `controller` and `runtime_plan` blocks. It is a
  planning artifact only.
- `runtime_execution.jsonl` and `runtime_execution_summary.json` contain the
  durable step history. They do not replace checkpoints or `state.json`.
- `runtime_apply.jsonl` and `runtime_apply_summary.json` contain the explicit
  mutation history for candidate outputs that were actually applied.
- `runtime_loop.jsonl` and `runtime_loop_summary.json` contain bounded loop
  iterations and stop reasons. They summarize orchestration evidence only and
  do not replace execution/apply logs or checkpoints.
- `runtime_handoff.jsonl`, `runtime_handoff_summary.json`, and
  `runtime_handoff/<handoff_id>.json` contain delegated job handoff evidence.
  They are plans for worker/sub-agent execution, not proof that the long job
  completed.
- `runtime_worker.jsonl`, `runtime_worker_summary.json`, and
  `runtime_worker/<worker_id>.json` contain worker/sub-agent execution attempt
  evidence. Dry-run records do not prove an output was produced; `applied`
  records point to the existing handoff-apply state mutation.
- `runtime_handoff_apply.jsonl` and
  `runtime_handoff_apply_summary.json` contain controlled handoff-result
  ingestion history. They do not replace worker logs; they only prove the
  runtime accepted and registered output files.

Current console limits:

- chat/upload can build a runtime plan, run a bounded dry/live/fixture loop,
  stop cleanly at user gates or delegated long jobs, write a delegated job
  handoff package, ingest concept-image handoff results supplied by a
  worker/sub-agent, and let the user approve or request changes for concept
  images. It is still not a full background worker system and does not itself
  run external generation jobs inside the HTTP request;
- uploads are intake artifacts, not automatic reference-binding decisions;
- concept approval/retry actions are interactive and logged; Blender preview
  approval/retry is still status metadata rather than a full interactive action
  queue;
- GLB preview is delegated to the existing GLB viewer; `.blend` access is
  delegated to Blender Web when that service is running.

## Do Not Duplicate

- Do not create another GLB viewer; use `tools/glb_viewer_server.py`.
- Do not put `.blend` into the GLB viewer; use Blender Web or local Blender for
  `.blend`, and exported `viewer_scene.glb` for browser preview.
- Do not create another runtime console state store; console chat/upload files
  are run-local evidence, while `state.json` and checkpoints remain
  authoritative.
- Do not let LLM nodes call raw MCP tools directly.
- Do not let front-end files become a second workflow state source.
- Do not hide long-running service calls inside tests or synchronous status
  checks.
