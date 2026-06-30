# V1 Overall Status

Updated: 2026-06-30

## Overall Target

Build an agent workflow for image/text to Blender-ready 3D scene:

1. understand user request and reference images;
2. produce structured scene/subject specs;
3. generate or ingest 2D concept images;
4. generate subject 3D assets with Hunyuan3D;
5. generate or adapt scene/world assets with HY-World/WorldMirror;
6. assemble/edit in Blender through safe domain tools/MCP;
7. export viewer artifacts and delivery package;
8. keep state, checkpoints, review patches, and front-end status inspectable.

## Current Position

Current stage: first real local artifact-chain demo completed; still not a polished autonomous agent.

Done enough to rely on:

- Core state models: `AgentProjectState`, `SceneSpec`, `ConceptBundle`, `ReviewPatch`, assets, Blender/viewer state, pending actions, tool logs.
- Artifact store: large binaries stay outside state; state keeps ids, paths, hashes, metadata.
- Checkpoints: workflow stages write JSON snapshots and JSONL index/event logs.
- Front-end status: every workflow can write `frontend_status.json`.
- Local workflow runner: existing GLB -> Blender compose/export/viewer checks are wired through existing scripts.
- Hunyuan3D boundary: submit/status/save wrappers, dry-run/fake-service tests, subject-asset QA, repair decisions, and repair execution guard.
- HY-World/WorldMirror boundary: runtime status, call planning, queued upload/reconstruct primitives, fake/dry-run tests, and existing-output registration.
- Feedback loop state path: failed/uncertain asset -> pending action -> user feedback -> `ReviewPatch` -> concept-regeneration plan or registered generated image.
- Reference-image intake contract: explicit bindings are validated before
  SceneSpec/high-cost generation, and missing purposes become clarification
  actions rather than guesses.
- LLM prompt contract: key nodes have JSON-only Pydantic-backed prompt
  contracts and raw MCP/tool execution is excluded from LLM nodes.
- Prompt review surface: `docs/agent_prompt_catalog.md` is generated from live
  node specs and exposes every current node prompt, sample context, allowed
  tools, and output schema for user review.
- Natural-language regression fixtures: `tests/fixtures/natural_language_scene_cases.json`
  covers Chinese/English, text-only, explicit subject/scene/style/texture/layout
  bindings, multi-subject scenes, and missing-binding clarification. The
  runtime fixture test materializes these as run directories and drives the
  bounded loop rather than only checking prompt strings.
- LLM node execution boundary: `ConceptPromptPlanner` can now run through the
  existing Qwen provider adapter and validate JSON with Pydantic.
- Concept planning bridge: validated `ConceptPromptPlanner` output can be
  applied to state as a `ConceptPromptPack` without LLM-owned state mutation.
- Generated concept ingestion: `codex-self-mcp` image-generation logs can be
  decoded into a project image file and registered through `concept-seed` or
  the runtime worker/handoff-apply path.
- State-driven controller contract: `build_controller_plan(state)` now encodes
  the V1 gates from intake through delivery without creating a second state
  source.
- Runtime job planning: `build_agent_runtime_plan(state)` converts controller
  actions into explicit jobs for main runtime, background worker, sub-agent, or
  user gate execution.
- Hunyuan3D profile layer: high-quality and smoke profiles centralize
  texture/octree/steps/chunks/face-count defaults, and the subject-asset CLI can
  now select or override them.
- Runtime run reader: existing run outputs can be discovered/read with public
  GLB viewer and Blender Web URL adaptation without creating a new UI state
  source.
- Runtime console MVP: port `8093` browser console lists existing runs, creates
  intake runs, records chat, uploads reference images, embeds the existing GLB
  viewer, shows registered concept images before GLB export exists, and shows
  status/objects/delivery links from run files.
- Runtime console run/file linkage: parent runs and visual child stages are
  both discoverable, `effective_run_dir` resolves real visual/delivery stage
  JSON/model files, ordinary workflow child directories no longer hijack parent
  run state, and `file_manifest` exposes existing/missing file paths to the UI.
- Runtime console planning: chat/upload state can now produce a saved
  `runtime_plan.json` containing controller actions and runtime jobs without
  executing long-running model work.
- Runtime execution step: the console/API can execute one safe planned step,
  record user gates as `waiting_user`, dry-run main-runtime LLM nodes, and
  delegate long/background/sub-agent jobs with durable execution logs.
- Runtime semantic audit: real run directories can be checked for
  state/chat/plan/execution/output-file consistency instead of relying only on
  module self-tests.
- Runtime state apply: completed parsed candidates can now be explicitly
  applied to `state.json`, checkpointed, surfaced in `frontend_status.json`,
  and used to rebuild the next runtime plan.
- Runtime bounded loop: the console/API can run `step -> apply -> rebuild
  plan` until user gate, delegated long job, blocked/failed job, dry-run
  boundary, no remaining jobs, or step budget. Runtime selection now treats
  only `completed` as handled, so dry-run/user-gate/delegated records do not
  hide still-current jobs on retry.
- Runtime delegated handoff: delegated jobs can now be turned into run-local
  handoff packages with input files, expected outputs, command hints, and task
  prompts for worker/sub-agent execution. Subject-asset handoff prompts include
  approved concept artifact URIs, Hunyuan profile evidence, and the boundary to
  use existing `workflow_runner`/Hunyuan3D paths rather than direct state/log
  mutation.
- Runtime worker execution bridge: planned handoffs can now be dry-run,
  fixture-applied, executed through a guarded codex-self adapter, or ingested
  from a completed codex-self MCP JSONL image log. All attempts write
  `runtime_worker*` evidence and reuse existing handoff-apply paths for actual
  state mutation. A real non-dry-run `backend=codex_self_mcp` concept-image
  worker has now generated an MCP image event, extracted a PNG, and applied it
  into `ConceptBundle`.
- Runtime handoff result apply: worker-provided concept images and subject GLB
  assets can be registered back into state through `FileArtifactStore`,
  checkpointed, surfaced in `frontend_status.json`, and used to rebuild the
  next plan.
- Runtime handoff result apply now also supports scene/world output directories,
  registering them through the existing WorldMirror adapter into
  `Scene3DRecord` and rebuilding the plan toward Blender assembly.
- Runtime worker result apply now supports Blender/viewer outputs, registering
  `.blend`, `viewer_scene.glb`, optional `scene_state.json`, and optional
  preview renders into state, then moving the run to `BLENDER_PREVIEW` for user
  approval.
- Formal delivery runtime execution: after `approve_blender_preview` creates a
  `DELIVERY` plan, `/step` can now execute the `kind=delivery` job, build the
  package through the existing delivery packager, write back parent
  `state/frontend_status/delivery_handoff/summary/checkpoint/runtime_plan`, and
  stop creating further delivery jobs once a valid `EXPORT_PACKAGE` zip exists.
- Blender compose planning: `SceneSpec`/fallback state now produces a run-local
  `compose/assembly_plan.json` with target region, target height ratio, camera
  direction, camera distance, and orthographic framing. The existing compose
  script consumes this plan without replacing the Blender pipeline.
- SceneSpec-driven non-dry-run assembly: the local-e2e workflow can now load a
  saved `scene_spec.json`, produce `compose/assembly_plan.json`, execute
  Blender compose/export/viewer-check, and hand off to deterministic delivery
  packaging.
- codex-self-mcp boundary: status, plan handoff, guarded execution path,
  confirmed non-dry-run text execution smoke, completed-log image extraction
  into concept handoff apply, and one freshly submitted runtime-worker concept
  image generation/apply run.
- Fresh textured Hunyuan evidence:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/subject_asset_handoff_8fdfad06d643/`
  submitted job `360a38c9-f8f9-44da-9a5c-ed19ece6a7a5` with
  `hq_textured_1m_768`; the GLB was later saved, QAed, and handoff-applied to
  the parent runtime run as `subject_plush_asset_hq_001`.
- Blender Lab MCP boundary: safe selected read/edit operations through injected/socket raw caller; dry-run and selected non-dry-run smoke paths exist.
- Delivery packaging: deterministic local zip/package from existing state
  artifacts, now verified through runtime approval and delivery execution for
  the SceneSpec-driven non-dry-run assembly run.
- Local verification: current full suite passes; infrastructure inventory required
  items are present; tracked docs/source secret scan found no plaintext
  `sk-...` keys.
- First real demo evidence: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/`.
- Generated-concept demo evidence:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/`.
- Fresh runtime-worker concept evidence:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/`.
- SceneSpec-driven non-dry-run assembly/runtime-delivery evidence:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/`.
- Live Hunyuan3D shape-only subject generation completed and passed deterministic GLB QA.
- Blender compose, viewer export/check, preview approval, runtime delivery
  execution, and delivery package completed for that demo using an existing
  HY-World scene GLB.

## Not Yet Complete

These are the main gaps before the overall system is truly complete:

1. Full LangGraph graph
   - Current workflows are explicit runner entrypoints, not one full LangGraph node graph.
   - `langgraph` is not installed in the current Python environment.

2. Real agent LLM loop
   - Qwen/DeepSeek provider configs and dry-run scaffolding exist.
   - `ConceptPromptPlanner` has one successful live Qwen JSON smoke.
   - `BlenderEditRouter` now has live-provider evidence from both Qwen and
     DeepSeek: Qwen returned a patchable object edit with live-style aliases;
     DeepSeek returned tool calls without patches and the runtime now
     normalizes that shape into a `ReviewPatch.blender_edit_plan`.
   - The successful prompt-pack result can be applied to state.
   - codex-self has one confirmed non-dry-run text execution smoke through the
     local MCP helper.
   - SceneSpec generation, feedback parsing, and Blender routing nodes have
     schema/state-apply/controller coverage, but they still need live provider
     call evidence beyond the current dry-run/fixture paths.

3. Real concept image generation
   - `concept-seed` and `concept-regeneration` can register real local image files.
   - `codex-self-mcp` has produced a real concept image that was extracted from
     JSONL output and registered as a project artifact.
   - A freshly submitted delegated runtime worker has now used
     `backend=codex_self_mcp` to generate one concept image, extract it to
     `runtime_worker/<worker_id>_concept.png`, register it under
     `artifacts/subject_concept_image/`, and move state to `CONCEPT_REVIEW`.
   - A first-class project-native Qwen/image-generation provider/export path is
     still missing.

4. Live Hunyuan3D subject generation
   - Live shape-only generation completed.
   - The current live high-quality textured generation from the fresh
     codex-self concept image completed, was saved, QAed, and handoff-applied
     back into parent runtime state.
   - Retry loops still need a focused run.

5. Live HY-World scene generation
   - Upload/reconstruct call boundaries exist.
   - The current run has a WorldMirror/HY-World scene asset registered with
     upload/reconstruct event ids and saved scene GLB/PLY/NPZ/camera outputs.
   - Scene quality tuning and a cleaner repeatable generation preset are still
     needed.

6. Full Blender assembly intelligence
   - Existing-script compose/export and selected MCP edit paths work.
   - Fixed smoke placement has been upgraded to a deterministic
     `assembly_plan.json` contract that can be produced from `SceneSpec` hints
     and consumed by the existing compose script.
   - One saved SceneSpec has now driven a non-dry-run compose/export/viewer
     check and delivery package for the `20260629_scene_spec_assembly_non_dryrun`
     run.
   - Blender preview feedback can now be routed into concrete planned edit
     domain-tool calls, stored in `ReviewPatch.structured_delta`, scheduled by
     the controller before viewer refresh, dry-run through the safe Blender
     MCP operation planner, and executed through the main runtime when an
     explicit raw caller is injected or `blender-lab-socket` is explicitly
     selected.
   - The bounded runtime loop now forwards an explicit Blender raw caller/source
     and LLM `provider_configs/env`, and has tested file-level sequences for
     both `ReviewPatch.blender_edit_plan -> move_subject -> export_viewer_scene
     -> render_preview -> BLENDER_PREVIEW user gate` and natural-language
     feedback -> `BlenderEditRouter` fixture JSON -> `ReviewPatch.blender_edit_plan`
     -> `move_subject` -> viewer refresh -> preview gate. Script-backed viewer
     refresh jobs are no longer misrouted into the generic Blender edit MCP
     dispatcher, and Blender scene sync preserves the `.blend` artifact link
     needed for post-edit export.
   - A scratch run has now executed a real `blender-lab-socket` edit refresh:
     `BlenderEditRouter` fixture -> `update_camera` through the socket -> save
     scratch `.blend` -> export viewer GLB -> render preview -> return to the
     `BLENDER_PREVIEW` user gate. The viewer GLB is served by the existing 8092
     viewer, and the scratch run is visible through the 8093 runtime console.
   - Runtime script-backed `export_viewer_scene` now writes viewer
     `runtime_status` and `model_check` into the viewer GLB artifact metadata,
     allowing refreshed `delivery_handoff.verified` to become true when 8092
     checks pass.
   - A live Qwen `BlenderEditRouter` run now exists:
     `20260630_live_qwen_blender_edit_router_smoke` executed
     `qwen3.7-max`, parsed a `move_subject` plan with live-style
     `object_id + subject_id` arguments, applied it into
     `ReviewPatch.blender_edit_plan`, and dry-ran the next runtime step into a
     safe `execute_blender_code` MCP operation plan targeting Blender object
     `Hero`. The run audits cleanly after the audit layer learned to distinguish
     domain-tool dry-run operation plans from LLM dry-runs.
   - A live DeepSeek `BlenderEditRouter` output has been replayed through the
     current runtime:
     `20260630_live_deepseek_blender_edit_router_replay_toolcalls` reuses the
     existing live `deepseek-v4-flash` parsed output, synthesizes
     `patch_blender_edit_0479e0079d83` from tool calls without patches,
     schedules `move_subject`, dry-runs a safe MCP operation plan targeting
     Blender object `Hero`, and audits with `error_count=0, warning_count=0`.
   - The same live DeepSeek router output has now been advanced through a
     true non-dry-run object edit and viewer refresh:
     `20260630_live_deepseek_blender_edit_router_liveedit_socket` executes
     `move_subject` through the explicit `blender-lab-socket` raw caller,
     saves a run-local `.blend`, exports `viewer_export/viewer_scene.glb`,
     renders `preview_render/preview.png`, returns to the `BLENDER_PREVIEW`
     user gate, and audits with `error_count=0, warning_count=0`.
   - Delivery handoff preflight now matches the package builder: edit-only or
     preview-only runs without subject/scene package assets report
     `missing_subject_assets` / `missing_scene_assets` instead of claiming
     delivery readiness.
   - A complete SceneSpec-driven run has now gone through runtime
     `approve_blender_preview` and delivery execution:
     `20260629_scene_spec_assembly_non_dryrun` reached `DELIVERY`, generated
     `delivery_v1_local_e2e_workflow_54dac92d.zip`, exposes the package through
     the 8093 runtime API, and audits with `error_count=0, warning_count=0`.
   - Final layout/scale/camera intelligence is still basic and not a mature
     LLM/vision planner; the next edit proof should preserve a full
     asset-bearing package substrate while applying live-router edits.

7. Front-end UI/runtime surface
   - Runtime console MVP exists on `8093` with a creator-workbench layout:
     narrow product nav, left run list, center concept/3D preview plus
     chat/reference upload, and a right-side Chinese phase/asset/delivery
     panel.
   - The latest `ui16` pass makes the default surface a clearer public creation
     workspace instead of a debug dashboard: five visible stages
     (`需求绑定 -> 概念确认 -> 模型生成 -> 场景验收 -> 交付下载`), a right rail
     ordered as `下一步 -> 阶段进度 -> 全部资产 -> 交付文件`, a center
     `当前阶段 / 下一步 / 预览 / 资产` summary ribbon, a public `当前任务`
     brief for the natural-language goal/reference binding/asset progress,
     user confirmation actions when relevant, a reference/asset chain,
     delivery links, no default `Open GLB / Build Plan
     / Status / Phase / Node` debug block, and no default child-stage/smoke/audit
     run inventory. It also prioritizes viewer-ready runs, hides unavailable
     preview/engineering buttons until real URLs exist, shows a visible
     non-blank 3D preview empty/loading state while the viewer hydrates, keeps
     a Chinese actionable hint if the iframe is slow or blank,
     surfaces missing edit-feedback errors in the public composer, and serves
     static/API responses with explicit no-cache headers.
   - The UI14/UI15/UI16 correction keeps the historical stacked CSS behind a
     final public skin, adds an asset gallery backed by existing
     artifacts/state, overrides stale cached empty runs with viewer-ready runs
     in public mode, and deprioritizes or collapses internal
     smoke/audit/worker/LLM runs unless `?dev=1` is enabled.
   - The UI17 correction tightens public run selection again: `non_dryrun` is
     no longer hidden as dry-run, live/debug provider runs are not public
     defaults, the formal `20260629_scene_spec_assembly_non_dryrun` run becomes
     the top public entry, public task text filters smoke/router/debug wording,
     the right-side status hero remains visible, and the delivery panel exposes
     state/scene/handoff JSON plus the delivery zip URL from `file_manifest`.
   - The embedded 8092 GLB viewer now supports `public=1` / `embed=1`: runtime
     console iframes get Chinese controls, no visible absolute path row, and no
     list/download debug buttons, while the default viewer still keeps operator
     debug access.
   - `scripts/runtime_console_hydrated_smoke.py` now produces a browser-rendered
     hydrated acceptance report from the live 8093 API and embedded 8092 viewer.
     The latest run selects `20260629_scene_spec_assembly_non_dryrun`, verifies
     `DELIVERY`, verified delivery handoff, state/scene/handoff/package file
     links, and public Chinese viewer controls, then writes summary/report HTML
     and screenshots under `/tmp/image23d_hydrated_smoke/`.
   - The UI18 public review fix adds a final `ui18_final.css` layer served by
     the existing 8093 runtime console, a center five-stage roadmap, vertical
     right-side stage progress, public-only delivery entries, delivery-aware
     asset semantics (`6/6` ready on verified delivery), and a Blender preview
     thumbnail inside the 3D viewer loading state for large GLB files. The
     hydrated BiDi check wrote
     `/tmp/image23d_ui18/runtime_console_ui18_hydrated.png` with
     `viewerHeight=579`, `taskHeight=90`, `hasDebug=false`, and
     `hasRuntimeName=false`.
   - Public object inspection now reuses `scene_state.json`: the 8093 console
     shows a `场景对象` panel with bounds-derived sizes and `聚焦查看` links, and
     the existing 8092 viewer accepts `target`, `radius`/`orbit`, and `focus`
     query parameters to set model-viewer camera target/orbit plus a public
     focus badge. Live BiDi evidence showed `objectCount=3`, Chinese object
     labels including `主体模型`, and `hasFocusParams=true`.
   - The UI19 product-shell pass removed the public dependency on legacy
     `polish.css`/`ui18_final.css`, adds `ui19_public.css`, renames the right
     rail at that time to `素材库 -> 下一步/阶段进度 -> 场景内容 -> 验收与交付`, hides raw scene
     dimensions/asset ids outside `?dev=1`, and restarts 8093 at
     `http://10.2.16.106:8093/?v=ui19-final` with pid `2539659`.
   - The UI20/UI21 passes keep inspectable `BLENDER_PREVIEW` edit/router runs visible
     instead of hiding them by internal-looking names, add preview-gate readiness
     chips plus the `确认并打包交付` action, and keep a Blender render thumbnail
     visible while the large 3D viewer loads. The hydrated smoke now
     selects `20260630_full_asset_live_router_edit_dfce104f`, verifies public
     viewer embedding and Chinese controls, and writes screenshots under
     `/tmp/image23d_ui21/`.
   - The UI22 pass tightens the public review workbench after user review:
     stronger contrast/density, public right-rail grouping, vertical stage
     progress instead of compressed
     horizontal text, larger Blender-preview fallback while the large GLB loads,
     and safe `写修改意见` object buttons that fill the composer without bypassing
     the `request_blender_changes` user gate. Hydrated smoke selects
     `20260630_full_asset_live_router_edit_dfce104f` at `BLENDER_PREVIEW`,
     confirms `public_shell_chinese=true`, `old_public_strings_absent=true`,
     `object_feedback_draft_present=true`, and writes screenshots under
     `/tmp/image23d_ui22d/`.
   - The UI22 object-submit pass makes object actions visible in the first
     review viewport by ordering the right rail as `下一步/阶段进度 -> 场景内容 ->
     素材库 -> 验收与交付`, constraining the stage list height, and adding
     `提交修改` buttons that write chat evidence and call the existing
     `request_blender_changes` user-action path. Smoke now confirms
     `object_feedback_submit_present=true`; the object-submit screenshot is
     under `/tmp/image23d_ui22_object_submit/`.
   - The UI23 object-refresh pass adds an explicit `生成预览` command boundary
     on scene-object cards. It records object feedback through chat and
     `request_blender_changes`, then calls the existing bounded `/loop` endpoint
     with `dry_run=false`, `max_steps=6`, and
     `blender_raw_caller_source="blender-lab-socket"`. Smoke confirms
     `object_feedback_refresh_present=true`; the screenshot is under
     `/tmp/image23d_ui23_object_refresh/`. Backend loop tests prove the
     feedback -> edit -> viewer export -> preview render -> preview gate path.
   - The UI24 polling pass adds a client-side bounded refresh layer for
     explicit long actions. `生成预览` and `确认并打包交付` now start polling
     `GET /api/runs/<run_key>` while the existing runtime request is running,
     update panels/chat, and surface phase/next-action progress in the composer
     notice. Hydrated smoke confirms `run_refresh_poll_present=true`; screenshot
     evidence is under `/tmp/image23d_ui24_poll/`.
   - The UI25 creator-workbench pass adds a cleaner product-facing skin in
     `web/runtime_console/ui25_creator.css`, fixes the 8093 static whitelist so
     the new CSS is actually served, makes the preview-ready state read
     `请验收当前 3D 场景` / `待你确认`, and keeps the right rail focused on
     Chinese stage/assets/delivery context instead of internal status dumps.
     Hydrated smoke confirms `ui25_creator_skin_present=true`,
     `preview_gate_copy_present=true`, `old_public_strings_absent=true`, and
     the static CSS route returns `200 text/css`; evidence is under
     `/tmp/image23d_ui25_creator_served/`.
   - The UI26 viewer-selection pass reuses the existing 8092 viewer and
     adjacent `scene_state.json`: public viewer pages now expose a path-free
     object summary, object chips, best-effort bounds-based canvas selection,
     and `image23d.viewer.objectSelected` postMessage events. The 8093 console
     receives the event, highlights the matching `场景内容` card, and fills the
     existing object-feedback draft when the composer is empty. Hydrated smoke
     confirms `viewer_object_selection_bridge_present=true`; evidence is under
     `/tmp/image23d_ui26_object_pick_final/`.
   - It can build a runtime plan, run a bounded dispatcher loop, apply
     supported candidates, create delegated job handoff packages, dry-run a
     worker/sub-agent execution attempt, ingest
     concept-image/subject-asset/scene-asset/Blender-viewer handoff results,
     apply concept-review and Blender-preview user actions, and surface
     loop/handoff/worker/user action/file evidence.
   - The latest UI pass hides technical ids, URLs, paths, status snapshots, and
     raw runtime logs behind `?dev=1`, while the first screen shows only current
     phase, next action, asset readiness, delivery links, chat, clean reference
     upload, and concept/3D preview state. Upload chips and the asset panel now
     expose whether reference images have explicit V1 purpose bindings. Unknown
     debug-like run ids are collapsed to public-safe names unless `?dev=1` is
     enabled.
   - It is not yet a full background worker runtime with exact mesh-level
     picking, true websocket/push refresh, or live user-click evidence for
     object refresh on the full-asset run.

8. End-to-end acceptance run
   - Artifact chains now exist for both a local sample concept and a
     codex-self generated concept:
     generated/registered concept -> live Hunyuan3D subject GLB -> existing
     scene GLB -> Blender/viewer -> package.
   - The current live run now reaches generated concept -> generated subject
     GLB -> generated/adapted scene asset -> Blender/viewer preview and stops
     at the required Blender-preview user gate.
   - A preflight package for the current live run is ready/verified without
     mutating parent state, and the formal post-approval runtime delivery
     execution path is now implemented/tested. A separate full-asset live-router
     edit run, `20260630_full_asset_live_router_edit_dfce104f`, now executes
     `move_subject` against the run-local `.blend`, exports a refreshed
     `viewer_scene.glb`, renders `preview.png`, audits cleanly, and stops at the
     required `BLENDER_PREVIEW` user gate. The edited preview still requires
     user approval before formal `DELIVERY`.
   - A complete autonomous request -> generated concept -> generated subject
     -> fresh scene -> polished Blender output -> approved delivery run is still
     not complete.

## Practical Completion Read

If the "whole thing" means infrastructure and safe local workflow skeleton:

- status: mostly built;
- remaining: LangGraph integration, richer planners, and a few guarded live-service checks.

If the "whole thing" means a real autonomous image-to-3D-scene agent:

- status: not complete yet;
- current work has built the reusable foundation and state/review/checkpoint spine;
- remaining work is mainly live model/service integration, mature planning, UI review surface, and full E2E acceptance.

## Immediate Next Steps

1. Keep git initialized and make a deliberate first commit only after the user approves the tracked file list.
2. Ask the user to inspect
   `outputs/runs/20260630_full_asset_live_router_edit_dfce104f` in the 8093
   console. If accepted, run the Blender-preview approval action and build the
   formal delivery package from parent state.
3. If not accepted, record the feedback as a Blender preview `ReviewPatch` and
   route through the now-tested Blender edit/export loop without restarting
   from concept generation.
4. Tune or repeat HY-World scene generation for cleaner scene geometry.
5. Add or install LangGraph only after deciding the environment policy.
6. Run live Qwen visual/reasoning checks in the close-out phase, with DeepSeek
   kept as a compatibility comparison path that already has router replay
   evidence.
7. Continue improving the review surface: exact mesh-level picking, true
   websocket or server-push refresh, and live user-click proof for object
   refresh on the full-asset run are still missing even though the file/runtime
   edit chain, explicit object-refresh command bridge, polling refresh layer,
   and viewer-to-console object-selection bridge are now proven.
