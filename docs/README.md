# Project Docs Index

Use these docs as the current source of truth for V1 landing work.

- `v1_delivery_roadmap.md`: short execution roadmap from current scaffold to real end-to-end demo.
- `v1_real_demo_20260628_report.md`: first real local artifact-chain demo report.
- `agent_prompt_contract.md`: LLM node prompt, JSON output, and tool-boundary contract.
- `agent_prompt_catalog.md`: generated, user-reviewable prompt catalog with every current node prompt, sample context, and output schema.
- `reference_image_schema.md`: natural-language plus reference-image intake and binding schema.
- `controller_design.md`: state-driven controller gates and next-action rules.
- `agent_runtime_contract.md`: runtime job/profile/web-surface contract for
  dispatching work to main runtime, background workers, sub-agents, or user
  gates, plus the runtime console MVP boundary.
- `repo_layout.md`: directory ownership, git tracking rules, and output placement rules.
- `v1_overall_status.md`: current overall status and remaining gaps.
- `v1_plan_gap_matrix.md`: DOC-003 minimum-plan completion matrix and conservative remaining-work estimate.
- `v1_landing_progress.md`: detailed implementation/progress log and smoke evidence.
- `runtime_environment_plan.md`: local runtime/service environment plan.
- `blender_asset_pipeline_contract.md`: Blender/asset pipeline contract.
- `agent_llm_provider_notes.md`: agent LLM provider notes with key suffixes only.
- `../tests/fixtures/natural_language_scene_cases.json`: executable natural-language fixture matrix used by runtime tests.

Current truth boundary:

- Passing tests and dry-runs mean infrastructure is healthy.
- They do not mean the full image-to-3D-scene agent is complete.
- A feature counts as landed only when its real output artifact, state file, summary, and verification command are recorded.
