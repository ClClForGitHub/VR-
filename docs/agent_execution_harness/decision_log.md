# Agent Execution Harness Decision Log

## DEC-20260701-core-harness: Use small task packets instead of one large plan

Decision:
- Future coding-agent work will be split into small task packets with explicit file scope, tests, acceptance criteria, and final reports.

Reason:
- Large plans are easy for agents to skim and hard to enforce.
- The project needs visible state, artifacts, frontend status, and verification for every meaningful slice.

Alternatives considered:
- One comprehensive master plan for all remaining work.
- Unstructured chat instructions for each coding session.

Consequences:
- More rounds, but each round has a clearer closure boundary.
- Each task can be reviewed for actual user-flow progress.

## DEC-20260701-active-docs-reuse-first: Treat active docs as current and olddocs as reference

Decision:
- Current active project documentation lives directly under `docs/`.
- `docs/olddocs/` is a historical/reference archive, not the governing plan.
- Non-trivial work must reuse the existing Hunyuan3D, HY-World/WorldMirror,
  Blender compose/export, GLB viewer, artifact store, state/checkpoint, and
  review-patch paths before adding new infrastructure.

Reason:
- The old broad docs were reclassified, so agents need a short current entrypoint
  instead of falling back to stale archived material.
- The repository already has substantial runtime and service infrastructure; a
  parallel wrapper or state path would make future runs harder to verify.

Alternatives considered:
- Continue using `docs/olddocs/` as the normal read path.
- Restore old docs as-is into the active docs root.
- Let each future task rediscover reuse boundaries from code.

Consequences:
- Future task packets should cite current active docs and this harness first.
- Archived docs may still be used for historical comparison, but only with that
  boundary stated explicitly.
- New service or state abstractions need a documented reuse decision before they
  are added.

## DEC-20260701-runtime-asset-library-state: Store asset library in AgentProjectState

Decision:
- Use `AgentProjectState.asset_library` and
  `AgentProjectState.active_assembly_selection` as the backend fact source for
  thread asset review and selection.
- Keep `ArtifactRecord` as the artifact/storage record and use asset-library
  rows as review, lineage, and selection metadata over those artifacts.

Reason:
- The existing state/checkpoint/runtime-plan path already drives controller,
  frontend status, handoff apply, and audit behavior.
- A separate asset database or frontend-only cache would violate reuse-first and
  make selection invisible to workers and Blender assembly.

Alternatives considered:
- Store a standalone asset-library JSON file outside `state.json`.
- Store selection only in runtime-console frontend state.
- Infer selected assets every time from artifact order.

Consequences:
- Controlled writer allowlists must include the new fields.
- Runtime asset actions must write JSONL, summaries, checkpoints,
  `frontend_status.json`, and rebuilt plans.
- Rejected assets remain in the library and can be selected unless explicitly
  archived or superseded by future policy.

## DEC-20260701-core-pipeline-semantics: Make semantic requirements explicit before live generation

Decision:
- Treat `ConceptImageRequirement[]`, `asset_library`, delegated handoff JSON,
  controller payloads, and derived `frontend_status.json` as the local contract
  for the core pipeline before any live model/service execution.
- Require scene references, subject references, target-render dependencies, and
  named identity evidence to be represented as typed fields, not only in prompt
  prose.

Reason:
- Round04 live calls will be expensive and harder to debug if subject/scene
  scope, selected assets, or upload inputs are ambiguous.
- The existing state/checkpoint/handoff paths are already sufficient; adding a
  second queue/state/service wrapper would violate reuse-first and hide facts
  from tests.

Alternatives considered:
- Let the live image worker infer source images from natural-language prompt
  text such as "use image 1".
- Store frontend action state separately from `AgentProjectState`.
- Delay concept/selection/handoff contract tests until after live generation.

Consequences:
- Planner output can be rejected locally before image generation when scene
  refs, subject refs, target dependencies, or identity evidence are missing.
- Delegated workers receive explicit input files, resolved image paths, source
  requirement ids, upload rules, selected concepts, selected scene/target refs,
  and apply-result schemas.
- `frontend_status.json` may show backend action payload examples, but it
  remains a derived view and not a writable state source.

## DEC-20260701-round04b-live-image-executor: Add a bounded concept-image executor before accepting live concept runs

Decision:
- Add `agent_runtime.concept_image_execution` as the structured executor between
  existing runtime handoff JSON and existing concept handoff-apply.
- Add `runtime_worker` backend `live_image` for this executor.
- Require backend capability proof for local reference-image attachment and
  multi-image composition before running a mixed structured concept handoff.

Reason:
- Round04 proved the control plane can produce `ConceptImageRequirement[]`, but
  no reusable worker executed image-guided and target-render requirements.
- Running a prompt-only scene image inside a mixed image-guided handoff would
  create misleading partial live evidence.
- The state, artifact, checkpoint, and handoff-apply paths already exist and
  should remain the only mutation boundary.

Alternatives considered:
- Extend the old `codex_self_mcp` worker directly and rely on prompt text to
  mention reference images.
- Generate partial text-only images when image-guided requirements are blocked.
- Add another artifact/result store dedicated to image generation.

Consequences:
- `live_generation_calls.jsonl` is now the per-requirement concept generation
  call record for Round04B live attempts.
- Default `codex_self_mcp` remains usable only for capabilities it actually
  exposes; currently it is blocked for Round04B image-guided/multi-image live
  acceptance.
- A future provider backend can be accepted by implementing the same
  `ConceptImageBackend` contract and proving real file attachments.

## DEC-20260701-round04c-agent-mediated-image2: Accept child-agent view_image as the image2 attachment boundary

Decision:
- Use `codex_self_mcp_image2` as the Round04C live concept backend.
- Treat child Codex `view_image` calls plus `input_image` payload evidence as
  the project-level proof that local reference files reached the visual context.
- Preserve original attachment paths in `input_image_paths` and
  `attachment_manifest.path`; use `attachment_manifest.view_path` for any
  converted PNG passed to the child visual tool.

Reason:
- The official codex MCP tool exposes a prompt string but no native `images[]`
  parameter.
- Local canary evidence proved a child Codex session can call `view_image` on
  local files and then generate images.
- AVIF uploads may not be directly processable by the visual tool, so the
  adapter must create a PNG view copy without changing the original user input
  record.

Alternatives considered:
- Mark backend capability as true without proving visual payloads.
- Put only `/path/to/image` inside the prompt and trust the model to infer it.
- Modify the external `codex-self-mcp` helper for an image argument.

Consequences:
- `view_image_tool_call` alone is insufficient; logs must contain
  `function_call_output` with an `input_image` payload.
- Target renders must attach generated concept outputs as visual references
  through the same manifest path.
- The boundary remains a wrapper over codex-self rather than a claim that the
  upstream MCP schema has native image parameters.

## DEC-20260702-creator-app-round04d-collection: Use an explicit real concept-case collection for the Creator App project center

Decision:
- The Creator App project center defaults to
  `GET /api/creator/projects?collection=round04d_concepts` on the 5173
  same-origin Creator App backend.
- `round04d_concepts` maps to
  `outputs/runs/round04d_live_12_samples/case_*` and should expose the 12 real
  Round04D concept sample projects.
- The legacy runtime-console/all-runs discovery list is not the Creator App
  project-center backend.

Reason:
- The old all-runs discovery endpoint prioritizes historical runs with viewer/scene
  artifacts and can return 50 older runtime entries before the current concept
  samples are visible.
- The user-facing Creator App must show the real 12 concept cases that were
  generated for Round04D, not old placeholder/mock choices.
- A backend collection keeps the frontend project selector tied to runtime
  `state.json`/artifact evidence instead of a hard-coded gallery list.

Alternatives considered:
- Increase the default all-runs limit and let the frontend search for cases.
- Hard-code 12 base64 run keys directly in the frontend.
- Replace the Creator App backend with the static HTML concept gallery.

Consequences:
- 5173 now has a stable same-origin collection query surface for demo data.
- Frontend direct `project_key`/`run_key` links still load even when the selected project is not
  present in the current collection.
- Future demo collections should be added as explicit backend collections
  rather than relying on global modified-time ordering or the old 8093 service.
