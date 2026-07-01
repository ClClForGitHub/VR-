# Runtime Flow Rules

This file defines how implementation slices should respect the runtime workflow. It does not replace code; it constrains how agents work on the code.

## Runtime facts

- `AgentProjectState` in `state.json` is the fact source.
- `frontend_status.json` is derived for frontend display.
- `runtime_plan.json` is a plan, not execution evidence.
- `runtime_execution.jsonl` records attempted execution.
- `runtime_loop.jsonl` records bounded loop progress.
- `runtime_handoff/` records delegated long-job packages.
- `runtime_worker/` records worker attempts and outputs.
- `runtime_handoff_apply.jsonl` records controlled application of worker results.
- `runtime_user_action.jsonl` records user approval or feedback gates.

## Phase progression

```text
INTAKE
  -> SCENE_SPEC_DRAFT / SCENE_SPEC_READY
  -> CONCEPT_GENERATION
  -> CONCEPT_REVIEW
  -> CONCEPT_APPROVED
  -> SUBJECT_ASSET_GENERATION / SUBJECT_ASSET_QA
  -> SCENE_ASSET_GENERATION / SCENE_ASSET_ADAPTATION
  -> BLENDER_ASSEMBLY_PLANNING / BLENDER_ASSEMBLY_EXECUTION
  -> BLENDER_PREVIEW
  -> BLENDER_EDIT when user asks for changes
  -> DELIVERY after user approves preview
```

## User gates

Concept review and Blender preview are user gates.

Concept review:

- Approve through the runtime user-action path.
- Reject or request changes through the runtime user-action path.
- Feedback becomes a `ReviewPatch` or equivalent structured change request.
- The concept bundle remains inspectable; rejected images should remain available for the future asset library.

Blender preview:

- Approve through the runtime user-action path.
- Request changes through the runtime user-action path.
- Editing must route to Blender edit planning and controlled domain tools.
- Preview approval is required before delivery packaging.

## Long jobs

Long jobs include concept image generation, subject asset generation, scene asset generation, and similar model-service tasks.

A long job may be:

- planned;
- delegated;
- running, if a worker records actual progress;
- completed, only after real output is returned and applied;
- blocked or failed, with issues recorded.

`delegated` is not `completed`.

## Image-generation rule

For `image_guided` requirements, downstream execution must attach or upload the actual referenced files. The execution record must include `input_image_paths` or equivalent evidence.

For `multi_image_composite` requirements, downstream execution must resolve `source_requirement_ids` to generated images and attach those images as visual references.

If required image inputs cannot be attached, the requirement is blocked. It must not silently degrade into a text-only request.

## Frontend status rule

Every workflow-changing slice must state what the frontend can display. At minimum, the frontend needs:

- current phase;
- current user action, if any;
- visible stage label;
- ready/pending/blocked job status;
- relevant artifact IDs;
- concept requirement readiness;
- selected or pending assets when selection is involved.

Frontend code should not infer hidden workflow state from filenames when backend state can expose it.

## Completion rule

A slice is complete only when the task packet's acceptance criteria are satisfied and the final report contains test evidence. Passing tests alone are not enough if the business artifact or state transition required by the task is missing.
