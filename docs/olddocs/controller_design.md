# Controller Design

Updated: 2026-06-28

## Purpose

The controller turns `AgentProjectState` into the next safe workflow action. It
is deterministic and state-driven. It does not replace LangGraph; it defines the
gate logic that a later graph should preserve.

## Governing Flow

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
  -> DELIVERY
```

## Gate Rules

- Missing image bindings block at intake with `ask_user_clarification`.
- `SceneSpec.open_questions` block before concept generation.
- Concept images block at `CONCEPT_REVIEW` until the user approves or gives
  feedback.
- Pending `ReviewPatch[]` route to concept regeneration.
- Subject assets proceed only after concept approval.
- Failed or uncertain subject assets surface a user/operator action instead of
  silently continuing.
- Blender/viewer output blocks at `BLENDER_PREVIEW` until user approval.
- Delivery requires assembled Blender/viewer artifacts.

## Runtime Model

Implemented in `agent_runtime.controller`:

- `ControllerAction`
- `ControllerPlan`
- `build_controller_plan(state)`

The plan is intentionally small. It names the node/tool to run next, the reason,
whether user input is required, and which domain tools are allowed for that
phase.

