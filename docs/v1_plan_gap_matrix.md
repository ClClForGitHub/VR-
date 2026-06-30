# V1 Plan Gap Matrix

Updated: 2026-06-30

Source plan:
`blender_scene_agent_docs_v1_zh_v0_3/blender_scene_agent_docs_v1_zh_v0_3/DOC-003_Agent_Workflow_Design_v0.2_zh.md`

This matrix tracks the uploaded plan's V1 minimum implementation order against
the current repository evidence. It is intentionally conservative: a row is
not marked done unless a code path and verification evidence exist.

| Step | Plan item | Current status | Evidence | Remaining work |
| --- | --- | --- | --- | --- |
| 0 | Existing infrastructure inventory and reuse decision | Done for current slices | `agent_runtime/infra_inventory.py`; latest inventory `ok=true`, required `20/20` present | Keep running before each new implementation slice |
| 1 | State schema + artifact store | Mostly done | `agent_runtime/state.py`, `agent_runtime/artifacts.py`, checkpoint/persistence tests | Keep schema aligned as runtime execution adds new state mutations |
| 2 | Hunyuan3D client + single subject GLB test | Mostly done | `Hunyuan3DServiceAdapter`, subject-asset workflow, live shape-only GLB demos, and live high-quality textured submit/save/QA/apply from the fresh codex-self concept image | Retry loop evidence and stronger visual QA still needed |
| 3 | Blender MCP wrapper + import/export/render/save test | Partial to mostly done | `BlenderMCPAdapter`, safe raw call boundary, existing compose/render/export scripts, live Blender/viewer demos | Mature MCP-backed assembly/edit loop still missing |
| 4 | SceneSpec generation | Partial to mostly done | prompt/schema/controller contracts exist; `docs/agent_prompt_catalog.md` exposes generated prompts for review; natural-language fixture matrix runs Chinese/English text/reference cases through `ReferenceBindingValidator -> SceneInterpreter -> SceneSpecCompiler`, applies `scene_spec`, advances phase, checkpoints, rebuilds plan, and audits cleanly | Live provider/sub-agent SceneSpec candidate and richer clarification UI |
| 5 | 2D concept generation loop | Mostly done for V1 runtime path | `ConceptPromptPlanner` live Qwen smoke, `concept-seed`, codex-self image ingestion, concept regeneration registration, bounded loop applies prompt pack then stops at delegated `generate_concept_images`; runtime handoff writes worker/sub-agent JSON packages; `runtime_worker` can dry-run/fixture-apply a planned concept handoff into `ConceptBundle`; guarded `codex_self_mcp` worker path is tested with confirmed fake-adapter image extraction/apply; `codex_self_log` ingests completed MCP JSONL image logs through the same apply path; a fresh non-dry-run `backend=codex_self_mcp` run generated and extracted a 1024x1536 PNG, registered it under `artifacts/subject_concept_image/`, and moved state to `CONCEPT_REVIEW`; runtime console can now approve a concept or turn feedback into pending `ReviewPatch` and regeneration plan; fixture matrix covers multiple prompt categories | First-class direct image provider adapter and richer visual review/QA UI |
| 6 | Subject asset pipeline | Partial to mostly done | Hunyuan3D submit/status/save, GLB QA, repair decision, live shape-only output, delegated `build_subject_asset` handoff, runtime GLB result ingestion into `subject_assets`, improved subject-asset handoff prompt with concept artifact URI/profile, and live textured output applied to parent runtime state | User-approved retry loop, stronger visual QA, and cleaner live worker close-out evidence |
| 7 | SceneGenerationService adapter stub | Partial to mostly done | HY-World/WorldMirror status, call planning, upload/reconstruct primitives, existing-output registration, runtime `scene_asset_results` handoff-apply into `Scene3DRecord`, and one live WorldMirror/HY-World scene asset registered with upload/reconstruct event ids | Cleaner repeatable scene-generation preset and quality tuning |
| 8 | Blender assembly pipeline | Partial to mostly done | Existing-script compose/export/render path, live demo `.blend`, `viewer_scene.glb`, package, runtime `blender_results` handoff-apply into `BlenderSceneState`/`ViewerSceneState`, interactive `BLENDER_PREVIEW` approve-vs-edit user actions, a SceneSpec-driven non-dry-run compose/export/viewer-check run under `outputs/runs/20260629_scene_spec_assembly_non_dryrun/`, UI28 deterministic assembly planning with composite front/back/left/right placement, `camera_target_normalized`, aspect-aware render resolution, compose-script camera target consumption, targeted tests proving the SceneSpec workflow writes the richer plan, and UI29 runtime bridge applying completed `BlenderAssemblyPlanner` candidates into `state.blender_assembly_plan`, rebuilding `runtime_plan.json` to `import_scene_asset`, normalizing the LLM plan into `compose/runtime_assembly_plan.json`, and dry-running that existing script-backed domain tool | Stronger asset-aware layout/camera reasoning, live-provider assembly-planner evidence, and a new non-dry-run full-asset preview using the richer plan |
| 9 | Web 3D viewer snapshot sync | Mostly done for V1 review surface | GLB viewer reuse, runtime console embed, concept-PNG preview before GLB export, `scene_state.json`, file manifest, visual-only child-stage routing so workflow output dirs do not hijack parent run state, `ui27` public console serving with no-cache headers, `ui19_public.css` plus the product-facing `ui25_creator.css` creator-workbench skin, fixed 8093 static whitelist for the new CSS route, product-workbench layout, public `当前任务` brief, center five-stage roadmap, right rail focused on `创作阶段 -> 场景内容 -> 素材库 -> 验收与交付`, `needs_user_action` preview state shown as `请验收当前 3D 场景` / `待你确认`, artifact-backed asset gallery, internal-run collapse with inspectable `BLENDER_PREVIEW` edit/router runs kept visible, hidden debug details behind `?dev=1`, enlarged Blender preview image kept as a non-blocking fallback while large GLB/model-viewer content loads, delivery-aware asset semantics, public delivery entries limited to user-facing preview/model/project/package actions, public `场景内容` panel from `scene_state.objects` with product labels, `聚焦查看` links, safe `写草稿`, explicit `提交修改`, and explicit `生成预览` object-feedback refresh buttons while raw dimensions/asset ids stay in dev mode, client-side bounded polling refresh for `生成预览` and `确认当前预览并打包` via existing run/chat APIs, server-push SSE refresh through `GET /api/runs/<run_key>/events` and frontend `EventSource`, embedded 8092 GLB viewer `public=1/embed=1` Chinese controls plus `target`/`radius`/`orbit`/`focus` camera parameters without visible path/list/download debug UI, viewer-side path-free `scene_state.json` object summaries, object chips, best-effort bounds-based canvas selection, and `image23d.viewer.objectSelected` postMessage bridge into the 8093 object-card highlighter/draft filler, preview-gate readiness chips, TDZ fix for `renderSceneObjectsPublic`, `scripts/runtime_console_hydrated_smoke.py` proving hydrated selection of `20260630_full_asset_live_router_edit_dfce104f`, `BLENDER_PREVIEW`, file links, Chinese public shell, absence of old English debug strings, object-feedback draft/submit/refresh controls, polling refresh helper, SSE event-stream helper, UI25/UI26/UI27 skin/selection/push refresh, public viewer controls, and evidence under `/tmp/image23d_ui27_sse/`, earlier UI26/UI25/UI24/UI23/UI22/UI21/UI20/UI19/UI18 screenshots, live edit run `20260630_live_deepseek_blender_edit_router_liveedit_socket`, and 8093 API showing the delivered SceneSpec run with package zip path | Exact mesh-level picking, optional bidirectional websocket control if needed, live user-click proof for object refresh on the full-asset run, and more visual polish |
| 10 | Blender edit loop | Mostly done for explicit raw-caller file/runtime control plane | `BlenderEditRouterOutput.domain_tool_calls`, state-apply storage under `ReviewPatch.structured_delta["blender_edit_plan"]`, controller scheduling of planned edit tools before viewer refresh, safe Blender MCP dry-run execution plan, explicit raw-caller non-dry-run runtime execution with state/checkpoint/status writeback, runtime loop forwarding of Blender raw caller/source and now `provider_configs/env`, script-backed `export_viewer_scene`/`render_preview` execution from BLENDER_EDIT, run-local `.blend` preload before socket edits, preserved and saved `.blend` artifact after scene sync, generated prompt catalog, targeted loop tests proving both pre-existing edit plan -> viewer refresh and natural-language feedback -> `BlenderEditRouter` fixture JSON -> `move_subject` -> viewer export -> preview render -> `BLENDER_PREVIEW` gate, UI23 object `生成预览` button explicitly calling `request_blender_changes` then `/loop` with `dry_run=false`, `max_steps=6`, and `blender_raw_caller_source="blender-lab-socket"`, scratch live `blender-lab-socket` edit-refresh run `20260630_blender_socket_edit_refresh_scratch_20260630T025222`, live Qwen router dry-run evidence, DeepSeek replay/live socket-edit evidence, full-asset live-router edit run `20260630_full_asset_live_router_edit_dfce104f` executing `move_subject` via `exec_313abe456b4c`, exporting `viewer_export/viewer_scene.glb` via `exec_7ad61fc5a669`, rendering `preview_render/preview.png` via `exec_c492db91ed82`, surfacing `subject_asset_ids=["workflow_subject_glb"]` and `scene_asset_id=workflow_scene_glb` in `frontend_status.json`, and auditing cleanly with `error_count=0` | Mature layout/camera reasoning, broader live-provider node coverage, live user-click evidence on the full-asset run, and formal delivery after user approval of the full-asset edit preview |
| 11 | Delivery package | Mostly done | deterministic package builder, demo packages, delivery handoff, verified `scene_spec_assembly_20260629.zip`, tightened delivery preflight aligned with package requirements, and runtime approval/delivery execution for `20260629_scene_spec_assembly_non_dryrun` producing `delivery_v1_local_e2e_workflow_54dac92d.zip` with `.blend`, preview PNG, viewer GLB, scene state, subject GLB, scene GLB, metadata, and version manifest | Release-level packaging/signing/upload, final acceptance report format, and one fresh fully autonomous acceptance run |

## Current Completion Read

Infrastructure skeleton and file-based runtime control are about **89%** of the
uploaded V1 plan.

The real autonomous image-to-Blender-scene agent is now about **90%** complete
for the V1 file/runtime control plane:
the state/tool/service spine exists, generated prompts are reviewable, and a
bounded runtime loop advances intake through prompt-pack state in real run
directories. Delegated long jobs produce explicit handoff packages, a bounded
worker bridge now records dry-run/fixture execution attempts, and worker
results can be registered back into state/checkpoints for concept images,
subject GLBs, scene/world outputs, and Blender/viewer outputs up to the
`BLENDER_PREVIEW` user approval gate. Concept-review and Blender-preview
approval/retry are now interactive runtime actions, and the Blender edit
refresh loop can now execute natural-language preview feedback ->
`BlenderEditRouter` JSON -> `ReviewPatch.blender_edit_plan` -> edit -> viewer
export -> preview render -> next preview gate in tests, plus through real
`blender-lab-socket` runs for both scratch and full-asset edit/export paths.
Runtime viewer refresh now writes viewer runtime/model check metadata for handoff
verification. A live Qwen router candidate has been applied into a
`ReviewPatch.blender_edit_plan` and dry-run through the safe MCP operation
planner with live-style object aliases. A live DeepSeek router output has been
replayed through tool-call-only patch synthesis into the same safe Blender
dry-run path, then advanced through a real `blender-lab-socket` object edit,
viewer export, preview render, and clean runtime audit. Delivery preflight now
matches package requirements and blocks preview-only/edit-only runs that lack
subject or scene assets. A complete SceneSpec-driven run has now gone through
runtime preview approval and runtime delivery execution, producing
`delivery_v1_local_e2e_workflow_54dac92d.zip` and auditing cleanly. A full
asset-bearing live-router edit run now reaches `BLENDER_PREVIEW` with refreshed
viewer and preview artifacts. Live LLM candidate generation for every node,
retry-loop evidence, mature placement/camera planning, user-approved delivery
of the edited full-asset preview, and the final fully autonomous end-to-end
acceptance run are still incomplete.

## Near-Term Runtime Gap

The immediate runtime gap is no longer the bounded loop itself. The current
console/API can run a conservative `step -> apply -> rebuild plan` loop and
write all orchestration evidence:

```text
state.json
  -> controller/runtime_plan.json
  -> runtime_execution.jsonl
  -> LLM candidate JSON or delegated job record
  -> controlled state mutation/checkpoint
  -> next runtime_plan.json
```

The next implementation slice should continue from the full-asset live-router
edit proof and the SceneSpec runtime-delivery proof: get user approval on the
edited full-asset preview, produce the formal delivery package from parent
state, add richer viewer object actions/refresh behavior, and improve mature
layout/camera reasoning. Keep the same file chain and explicit command boundary; do not hide
Blender or model-service work inside the main HTTP request.
