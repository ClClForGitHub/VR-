# V1 Delivery Roadmap

Updated: 2026-06-30

## Honest Current Status

We have now run live Qwen `ConceptPromptPlanner`, codex-self/MCP image
generation with project ingestion, live Hunyuan3D shape-only subject
generation, and a high-quality textured Hunyuan3D subject generation from the
freshly generated codex-self concept image. The current live run has concept
PNG -> subject GLB -> WorldMirror/HY-World scene asset -> Blender/viewer
preview, and that fresh live run is still stopped at the documented Blender
preview user gate. The post-approval runtime delivery execution path is now
implemented, tested, and proven on the complete SceneSpec-driven non-dry-run
assembly run. A live DeepSeek `BlenderEditRouter` output now
exists and has been replayed through runtime state-apply/domain-tool dry-run,
then advanced through a true `blender-lab-socket` object edit, refreshed viewer
GLB export, preview render, and clean runtime audit. We have not yet run a
first-class Qwen image provider.

What has been run:

- local unit/workflow tests;
- dry-runs;
- fake-service tests;
- existing sample GLB/image smoke paths;
- one live Qwen prompt-planning smoke;
- one live Qwen `BlenderEditRouter` smoke and one live DeepSeek
  `BlenderEditRouter` output replay through runtime patch synthesis and safe
  Blender domain-tool dry-run;
- one live DeepSeek `BlenderEditRouter` output advanced through non-dry-run
  `move_subject` over `blender-lab-socket`, saved run-local `.blend`, refreshed
  `viewer_scene.glb`, rendered `preview.png`, and returned to the
  `BLENDER_PREVIEW` user gate:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_live_deepseek_blender_edit_router_liveedit_socket/`;
- one codex-self generated concept image extracted into a project artifact;
- live Hunyuan3D shape-only generation;
- live Hunyuan3D textured high-quality generation from the fresh codex-self
  concept image: job `360a38c9-f8f9-44da-9a5c-ed19ece6a7a5`, profile
  `hq_textured_1m_768`, GLB saved, QAed, and handoff-applied to the parent run;
- live WorldMirror/HY-World upload -> reconstruct -> save/adapt for the current
  run's scene asset, with event ids recorded in scene-asset metadata;
- Blender/viewer flow for the current live run;
- state/checkpoint/frontend-status output generation.
- runtime console MVP with chat/upload/run list/embedded GLB viewer.
- runtime console run/file linkage repair for visual child-stage discovery,
  `effective_run_dir`, and structured file manifests; ordinary workflow child
  directories such as `subject_asset_handoff_*` no longer hijack the parent
  run's current state.
- runtime console plan generation from chat/upload state to `runtime_plan.json`.
- runtime console execution-step logging to `runtime_execution.jsonl` and
  `runtime_execution_summary.json`.
- runtime controlled state apply logging to `runtime_apply.jsonl`,
  `runtime_apply_summary.json`, checkpoints, and rebuilt runtime plans.
- runtime bounded loop logging to `runtime_loop.jsonl` and
  `runtime_loop_summary.json`, with retries fixed so dry-run/user-gate/delegated
  records do not hide current jobs.
- runtime delegated handoff planning to `runtime_handoff.jsonl`,
  `runtime_handoff_summary.json`, and `runtime_handoff/<handoff_id>.json`.
- runtime worker/sub-agent execution attempts to `runtime_worker.jsonl`,
  `runtime_worker_summary.json`, and `runtime_worker/<worker_id>.json`, with a
  dry-run fixture adapter, guarded codex-self adapter, completed codex-self
  JSONL image-log ingestion, and confirmed apply path through existing
  handoff-result ingestion.
- runtime concept-review and Blender-preview user actions to `runtime_user_action.jsonl`,
  `runtime_user_action_summary.json`, checkpoints, `frontend_status.json`, and
  rebuilt runtime plans for approve-vs-regenerate/edit decisions.
- runtime handoff-result ingestion for concept images and subject GLBs to
  `runtime_handoff_apply.jsonl`, `runtime_handoff_apply_summary.json`,
  state/checkpoints/frontend status, and rebuilt runtime plans.
- runtime handoff-result ingestion for scene/world output directories to
  `Scene3DRecord`, state/checkpoints/frontend status, and rebuilt runtime plans.
- runtime worker-result ingestion for Blender/viewer outputs to
  `BlenderSceneState`, `ViewerSceneState`, `BLENDER_PREVIEW`, and the preview
  approval gate.
- runtime console concept-image preview before GLB export: concept-review and
  concept-approved runs can show the registered PNG through the existing
  `/api/runs/<run_key>/file` path instead of a blank 3D panel.
- codex-self sub-agent channel status/plan evidence plus one confirmed
  non-dry-run text execution smoke:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_codex_self_execute_text_smoke/`.
- generated prompt catalog plus executable natural-language scene fixture
  matrix for Chinese/English prompt/runtime regression checks.
- runtime semantic audits for text-intake and uploaded-reference user-gate run
  directories.
- SceneSpec-driven non-dry-run Blender compose/export/viewer-check run:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/`.
- delivery package for that SceneSpec-driven run:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/delivery_package/package/scene_spec_assembly_20260629.zip`.
- runtime preview approval and delivery execution for that same complete
  SceneSpec-driven run:
  `approve_blender_preview` wrote checkpoint
  `ckpt_v1_local_e2e_workflow_local_workflow_20260629T222939Z_ff7b00cf80`,
  `/step` executed `job_01_delivery_delivery` as `exec_8102097a7a63`, and the
  runtime package
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/delivery_package/package/delivery_v1_local_e2e_workflow_54dac92d.zip`
  contains `.blend`, preview PNG, scene GLB, subject GLB, viewer GLB,
  scene-state JSON, metadata, and version manifest.
- delivery handoff preflight now matches package completeness: preview-only or
  edit-only runs without subject/scene assets report explicit missing assets
  instead of incorrectly claiming `ready=true`.
- latest targeted checks for the UI/runtime surface:
  `29 passed in 1.45s` for runtime console/run/frontend status, GLB viewer
  public embed/focus, viewer URL, and viewer runtime tests. Hydrated browser smoke
  passed with `ok=true`, selecting
  `20260629_scene_spec_assembly_non_dryrun`, verifying `DELIVERY`,
  delivery file links, public Chinese viewer controls, and `20260630-ui19`
  served assets. The UI19 public shell no longer loads `polish.css` or
  `ui18_final.css`, and the browser screenshot at
  `/tmp/image23d_ui19/runtime_console_ui19_fixed.png` shows the product-shell
  layout with `素材库`, `创作历史`, and `场景内容`. Earlier hydrated BiDi evidence at
  `/tmp/image23d_ui18/runtime_console_ui18_hydrated.png` showed
  `viewerHeight=579`, `taskHeight=90`, `assets=6/6`, `hasDebug=false`, and
  `hasRuntimeName=false`. Object-panel evidence at
  `/tmp/image23d_ui18/runtime_console_ui18_objects_panel.png` shows
  `objectCount=3`, Chinese object labels, and focus viewer URLs with
  `target`/`radius` parameters.
- latest targeted checks for prompt/runtime Blender edit planning:
  `45 passed in 0.57s` for prompt catalog, BlenderEditRouter state apply,
  controller, runtime execution, runtime jobs, and Blender MCP tests.
- latest targeted checks for explicit raw-caller Blender edit execution:
  `56 passed in 0.55s` for runtime execution, domain dispatcher,
  injected-caller workflow runner, runtime jobs, and controller tests.
- latest live-router/edit/audit targeted checks:
  `55 passed in 0.83s` for runtime execution, runtime audit, domain dispatcher,
  and runtime loop, plus `runtime_audit` on the live edit run with
  `ok=true, error_count=0, warning_count=0`.
- latest delivery-preflight/runtime close-out targeted checks:
  `48 passed in 0.91s`, plus `runtime_audit` on the SceneSpec delivery run and
  the DeepSeek live edit run with `ok=true, error_count=0, warning_count=0`.
- latest full current test suite: `323 passed in 2.37s`.

This means the workflow spine is being built, but the full real image-to-3D-scene product is not complete yet.

## Definition Of Done

The overall V1 is only done when one small demo can run end to end:

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

Required evidence for that demo:

- exact command sequence;
- real generated concept image artifact;
- real subject 3D asset artifact;
- real or intentionally mocked scene/world asset artifact;
- `.blend` file;
- `viewer_scene.glb` and `scene_state.json`;
- `state.json`, `summary.json`, `tool_call_log.json`, `frontend_status.json`;
- checkpoint snapshots;
- final package zip;
- short human-readable report with paths and known issues.

## Phase Plan

### P0 - Project Control

Status: mostly done, still needs first reviewed commit.

Deliverables:

- git initialized;
- `.gitignore` protects keys, models, outputs, service repos, caches;
- docs index and directory rules;
- first reviewed commit after confirming tracked files.

### P1 - Minimal Visible Concept

Status: mostly done for the minimal demo; a codex-self MCP image-generation
worker now produced and registered a fresh concept image through the runtime
worker path. A first-class direct provider adapter is still future work.

Goal:

- produce one real visible concept image for a tiny demo scene.

Preferred path:

- use an available image-generation path only after explicit approval;
- if ChatGPT image generation/MCP is available, use it for a single small concept image;
- otherwise use the configured Qwen/image provider path only after provider availability is checked;
- record the generated image as a `SUBJECT_CONCEPT_IMAGE` artifact.

2026-06-28 result:

- `concept-seed` now registers an existing/generated image file into `ConceptBundle`, artifact store, state, checkpoints, and frontend status.
- A ChatGPT/session image generation call was made, but the tool did not expose a local file path for project ingestion.
- The first reproducible P1 run used the existing local sample image `Hunyuan3D-2.1/assets/example_images/example_000.png`.
- `agent_runtime.reference_intake`, `agent_runtime.agent_prompts`, and
  `agent_runtime.controller` now define the explicit reference-image binding,
  JSON prompt, and state-driven gate contracts needed before a real provider
  call becomes an autonomous agent step.
- `agent_runtime.llm_nodes` now runs controlled LLM nodes through the existing
  provider adapter. A live Qwen `ConceptPromptPlanner` smoke succeeded and
  produced Pydantic-valid prompt JSON.
- `agent_runtime.concept_planning` applies the validated prompt output into
  `AgentProjectState.concept_bundle`.
- `codex-self-mcp` produced a real concept image that was extracted from JSONL
  output and registered through `concept-seed`.
- Generated concept artifact:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/concept_seed/artifacts/subject_concept_image/codex_self_robot_concept_001.png`.
- A fresh delegated runtime worker run now executes `backend=codex_self_mcp`
  non-dry-run, extracts an MCP `image_generation` result, registers the
  concept image through handoff-apply, and moves state to `CONCEPT_REVIEW`.
- Runtime worker concept artifact:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/artifacts/subject_concept_image/job_01_concept_generation_generate_concept_images_worker_a6cacea6151b.png`.

Acceptance:

- image file exists under `outputs/runs/<run_id>/artifacts/`;
- registered in `state.json`;
- appears in `summary.json`;
- no plaintext API key in docs/logs.

### P2 - Subject 3D Asset

Status: live shape-only runs completed; the current high-quality textured run
has also completed and been applied to parent state.

Goal:

- send the concept image to Hunyuan3D and get one subject GLB.

Acceptance:

- live submit/status/save command recorded;
- GLB exists and passes deterministic QA;
- optional preview render produced;
- subject asset recorded in state and artifact store.

2026-06-28 result:

- Live Hunyuan3D job `f72e91e2-e600-40a2-8f37-4f44f817f87f` completed with status `completed_shape_only`.
- Output GLB: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/subject_asset_live_save/subject_assets/demo_robot_asset_001.glb`.
- Deterministic QA passed with score `1.0`.
- Live Hunyuan3D job `9c8c6a2a-b637-4180-a27b-2ebfcde9e974` completed with status `completed_shape_only`.
- Output GLB: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/subject_asset_status_save/subject_assets/codex_self_robot_asset_001.glb`.
- Deterministic QA passed with score `1.0`.

2026-06-29 result:

- Fresh codex-self concept run was advanced through the runtime approval gate:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z`.
- Latest subject-asset handoff:
  `runtime_handoff/handoff_4016b4726e01.json`.
- The handoff prompt now includes the approved concept PNG URI, Hunyuan profile
  evidence, and the boundary to use existing `workflow_runner`/Hunyuan3D paths
  instead of editing runtime state directly.
- Live textured Hunyuan3D submit succeeded:
  `job_id=360a38c9-f8f9-44da-9a5c-ed19ece6a7a5`.
- Output directory:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/subject_asset_handoff_8fdfad06d643`.
- Close-out status: completed, GLB saved under the handoff output directory,
  deterministic QA passed, and artifact `subject_plush_asset_hq_001` is now
  registered in the parent run.

### P3 - Scene/World Asset

Status: HY-World call planning, existing-output registration, and runtime
scene-asset handoff-result ingestion exist. The current live run has one
WorldMirror/HY-World scene asset registered in parent state; the saved
scene-asset workflow evidence should be read together with the parent artifact
metadata because part of the chain was resumed across explicit upload,
reconstruct, inspect, save, and apply commands.

Goal:

- run one small HY-World/WorldMirror scene generation or intentionally choose an existing scene asset for the first demo.

Acceptance:

- if live: upload event id, reconstruct event id, poll completion evidence, output dir;
- if existing: exact provenance path and adapter summary;
- scene asset recorded in state.

### P4 - Blender Assembly

Status: local Blender/viewer demos completed with existing scene asset plus
live subject GLB; runtime Blender/viewer worker-result ingestion can now move a
run to `BLENDER_PREVIEW`. Compose now also has a deterministic
`assembly_plan.json` input contract for placement scale and camera framing.

Goal:

- import subject asset plus scene asset into Blender and export viewer scene.

Acceptance:

- `.blend` exists;
- preview PNG exists;
- `viewer_scene.glb` exists;
- `scene_state.json` exists;
- viewer model check passes or records exact failure.

2026-06-28 result:

- `.blend`, preview PNG, `viewer_scene.glb`, `scene_state.json`, viewer URLs, and delivery handoff were created under `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/blender_viewer/`.
- Viewer runtime and model checks passed.
- A generated-concept variant also passed under
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/blender_viewer/`.
- Known quality boundary: placement/scale/camera are still smoke-level and need
  mature SceneSpec/Blender planning.

2026-06-29 result:

- Added `agent_runtime.blender_assembly_planner.build_compose_scene_plan(...)`
  to map `SceneSpec` subject placement, priority/scale hints, and camera hints
  into a run-local compose plan.
- `tools/compose_blender_scene.py` keeps the old four-argument mode but can now
  consume optional `assembly_plan.json` for target region, target height ratio,
  camera direction, camera distance, orthographic scale, and render resolution.
- `workflow_runner local-e2e` writes `compose/assembly_plan.json`, passes it
  through `ScriptDomainToolDispatcher`, and records the plan id/path in summary,
  tool-call arguments, and compose-stage checkpoint metadata.
- Dry-run evidence:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_blender_assembly_plan_smoke/`.
- Non-dry-run SceneSpec evidence:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/`.
- The non-dry-run run completed compose, export, and viewer check with
  `.blend`, preview PNG, `viewer_scene.glb`, `scene_state.json`,
  `frontend_status.json`, `delivery_handoff.json`, and `summary.json`.
- The compose plan used `plan_id=compose_plan_subject_plush_v1`,
  `target_region=front_right`, `target_height_ratio=0.5`, and produced a
  viewer scene with `7` objects.

2026-06-30 result:

- Extended the deterministic `ComposeScenePlan` contract with
  `camera_target_normalized` while keeping old plans compatible.
- SceneSpec placement planning now combines horizontal and depth hints, so
  `right side foreground` becomes a real foreground-right placement instead of
  only a side placement.
- `tools/compose_blender_scene.py` now aims the preview camera at the optional
  normalized camera target, and the planner chooses square/vertical/wide render
  resolution from SceneSpec camera hints.
- Verification:
  `python -m pytest tests/test_blender_assembly_planner.py tests/test_workflow_runner.py::test_local_e2e_workflow_uses_scene_spec_for_compose_plan -q`
  -> `5 passed in 0.50s`.
- Dry-run evidence:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260630_ui28_assembly_plan_dryrun/compose/assembly_plan.json`
  with `camera_target_normalized=[-0.072, 0.072]`.
- Runtime bridge:
  completed `BlenderAssemblyPlanner` candidates now apply into
  `state.blender_assembly_plan`, rebuild `runtime_plan.json` to the existing
  `import_scene_asset` domain tool, normalize the candidate into the
  compose-script `runtime_assembly_plan.json` contract, and can dry-run the
  script-backed assembly job. Targeted verification: `7 passed in 0.34s`;
  related runtime/controller suite: `62 passed in 0.84s`.

### P5 - Review Loop

Status: state loop and runtime console MVP exist; one-step runtime execution
and controlled apply/checkpoint logging exist. Runtime can now dry-run or
execute a planned delegated handoff through a worker adapter, then reuse
handoff-apply for state/checkpoint/frontend updates. The console has
first-class approval/retry controls for concept review and Blender preview,
with technical runtime details folded behind `开发详情`; the default right panel
now shows product-facing Chinese phase, next-action, preview, asset, and
delivery state instead of raw runtime/file/path details. The codex-self channel
now has both a confirmed non-dry-run text smoke and a freshly submitted
concept-image worker that applied a real generated image into runtime state.

Goal:

- let failed/uncertain output create `PendingAction`;
- convert user feedback to `ReviewPatch`;
- regenerate or register a revised concept image;
- retry subject asset generation if approved.

Acceptance:

- pending action shown in `frontend_status.json`;
- console surfaces the run, current status, chat context, uploaded references,
  and viewer/delivery links;
- patch recorded;
- regenerated image artifact recorded;
- patch marked applied only after actual artifact is registered.

### P6 - Package And Report

Status: packages completed for the first demos and the SceneSpec-driven
non-dry-run assembly run. Runtime delivery execution is now connected for
post-preview-approval parent runs, but the current live run is still waiting at
the preview approval gate.

Goal:

- create final handoff package.

Acceptance:

- zip package exists;
- metadata and version manifest exist;
- package contains the expected artifacts or explicit missing-item report.

2026-06-28 result:

- Package zip: `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_p0_real_demo/delivery_package/package/delivery_20260628_p0_real_demo.zip`.
- Package checks passed.
- Generated-concept package zip:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260628_codex_self_robot_concept/delivery_package/package/codex_self_robot_demo_20260628.zip`.
- Package checks passed.

2026-06-29 result:

- SceneSpec-driven package zip:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_scene_spec_assembly_non_dryrun/delivery_package/package/scene_spec_assembly_20260629.zip`.
- Package checks passed with no issues:
  `has_blend_file=true`, `has_preview_render=true`,
  `has_viewer_scene=true`, `has_viewer_state=true`,
  `subject_asset_count=1`, `scene_asset_count=1`,
  `delivery_handoff_ready=true`, `delivery_handoff_verified=true`.
- Zip verification found `metadata.json`, `version_manifest.json`,
  `files/blender/workflow_composed_blend.blend`,
  `files/preview/workflow_composed_preview_png.png`,
  `files/viewer_scene/workflow_viewer_scene_glb.glb`,
  `files/viewer_state/workflow_scene_state_json.json`,
  `files/subject_assets/workflow_subject_glb.glb`, and
  `files/scene_assets/workflow_scene_glb.glb`.
- The packaged `state.json` and `frontend_status.json` are in `DELIVERY`.
- Current live-run preflight package:
  `/home/team/zouzhiyuan/image23D_Agent/outputs/runs/20260629_runtime_worker_codex_self_live_concept_20260629T115755Z/delivery_preflight/package/live_preview_delivery_preflight_20260629.zip`.
- This preflight package is file-complete and has
  `delivery_handoff_ready=true`, `delivery_handoff_verified=true`, but it does
  not mutate the parent run to `DELIVERY`; the parent remains
  `BLENDER_PREVIEW` until the Blender preview user gate is approved.
- Formal delivery execution is now implemented in the runtime: after
  `approve_blender_preview`, the `kind=delivery` job builds the package through
  the existing packager, writes parent `state.json`, `frontend_status.json`,
  `delivery_handoff.json`, summary/checkpoint/runtime-plan evidence, and stops
  creating repeated delivery jobs once a valid `EXPORT_PACKAGE` exists.

## Immediate Next Run

Run ID convention:

```text
outputs/runs/20260629_<short_goal>/
```

Suggested next demo:

- subject: one simple stylized object/character;
- scene: approved HY-World live run if the user wants real scene generation now,
  otherwise keep the existing lightweight scene GLB;
- focus: submit one fresh worker/provider job through the existing
  `runtime_worker`/handoff-apply file chain now proven for concept-image
  generation; the next close-out is to bridge this into the approved
  Hunyuan3D/HY-World/Blender path rather than using reused assets.
- remaining model-service close-out: poll/save/QA/apply the in-flight textured
  Hunyuan3D job, then run one approved live HY-World scene generation instead
  of using the existing scene GLB.

Operator approvals needed before true live execution:

- permission to poll/save the submitted live Hunyuan3D job if it is still
  running;
- permission to submit/poll a live HY-World job if we do not use an existing scene asset.

## What Was Built So Far

Useful, but not the final product:

- state schema;
- artifact store;
- checkpoints;
- workflow runner;
- dry-run service boundaries;
- QA and repair routing;
- ReviewPatch handoff;
- concept-regeneration registration path;
- Blender/viewer adapters;
- delivery package builder;
- runtime console MVP;
- runtime console `ui11` public/dev split with hidden internal records,
  no-cache static/API serving, no default disabled preview buttons,
  prioritized viewer-ready run selection, and a Chinese five-stage user
  surface;
- runtime loop Blender edit refresh bridge: explicit raw caller/source
  forwarding, preserved `.blend` artifact ids after scene sync, script-backed
  viewer export/render execution from `BLENDER_EDIT`, and tested
  edit -> viewer export -> preview render -> preview-gate file chain;
- full-asset live-router edit closure on
  `outputs/runs/20260630_full_asset_live_router_edit_dfce104f`: run-local
  `.blend` preload before socket edit, non-dry `move_subject`, refreshed
  `viewer_export/viewer_scene.glb`, refreshed `viewer_export/scene_state.json`,
  `preview_render/preview.png`, public console selection of this preview run,
  UI21 preview-gate controls/fallback thumbnail, UI22 public review workbench
  cleanup with Chinese shell checks, safe object-feedback draft controls, and
  object-card `提交修改` controls that reuse the existing
  `request_blender_changes` user-action path, UI23 object-card `生成预览`
  controls that explicitly call the existing non-dry bounded runtime loop with
  the Blender socket raw caller boundary, UI24 polling refresh for explicit
  object-preview and delivery-package actions, UI25 creator-workbench skin plus
  the 8093 static-route fix for `ui25_creator.css`, UI26 viewer-to-console
  object selection through adjacent `scene_state.json` and
  `image23d.viewer.objectSelected`, UI27 server-push refresh through
  `GET /api/runs/<run_key>/events` and frontend `EventSource`, and clean
  runtime audit;
- scratch live `blender-lab-socket` edit-refresh evidence on
  `20260630_blender_socket_edit_refresh_scratch_20260630T025222`, using
  `update_camera` to save the scratch `.blend`, export a refreshed viewer GLB,
  render a preview PNG, and return to the preview user gate;
- tests.

These are foundations. The next visible progress should connect the console to
real runtime dispatch and keep producing verifiable artifacts, not another
parallel UI or viewer.
