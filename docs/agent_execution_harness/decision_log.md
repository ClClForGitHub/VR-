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
