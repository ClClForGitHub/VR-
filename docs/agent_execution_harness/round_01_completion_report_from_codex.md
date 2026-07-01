# Codex Completion Report: Round 01 Core Harness

  ## 1. Summary

  - Completed:
    - Applied the Round 01 core harness package to `docs/agent_execution_harness/`.
    - Added `tests/test_agent_execution_harness_docs.py`.
    - Updated `AGENTS.md` so non-trivial work must read and follow the harness.
    - Updated `docs/README.md` so active `docs/` is the current documentation source and `docs/olddocs/` is historical reference only.
    - Recorded the active-docs and reuse-first decision in the harness decision/progress logs.
  - Not completed:
    - Did not implement the chat asset library, free-composition behavior, or frontend-status asset contract. That is the next product slice.
    - Did not modify runtime business code, frontend UI, or service code.
    - Did not run live Hunyuan3D, HY-World, image generation, or non-dry-run Blender MCP jobs.
  - Scope deviation: no.

  ## 2. Changed Files

  ```text
  AGENTS.md
  docs/README.md
  docs/agent_execution_harness/README.md
  docs/agent_execution_harness/task_packet_template.md
  docs/agent_execution_harness/runtime_flow_rules.md
  docs/agent_execution_harness/live_test_policy.md
  docs/agent_execution_harness/documentation_maintenance.md
  docs/agent_execution_harness/module_checklist.md
  docs/agent_execution_harness/progress_log.md
  docs/agent_execution_harness/decision_log.md
  docs/agent_execution_harness/design_notes.md
  docs/agent_execution_harness/round_01_completion_report.md
  tests/test_agent_execution_harness_docs.py
  ```

  ## 3. Diff Summary

  ```text
   AGENTS.md                                        |   41 +-
   docs/README.md                                   |   71 +-
   docs/agent_llm_provider_notes.md                 |   34 -
   docs/agent_prompt_catalog.md                     | 2834 --------
   docs/agent_prompt_contract.md                    |  176 -
   docs/agent_runtime_contract.md                   |  382 --
   docs/asset_and_review_flow_audit_20260701.md     |  185 -
   docs/blender_asset_pipeline_contract.md          |  310 -
   docs/concept_image_prompts_user_samples.md       |  372 -
   docs/controller_design.md                        |   50 -
   docs/glb_to_mmd_rigging_notes.md                 |  271 -
   docs/reference_image_schema.md                   |   80 -
   docs/repo_layout.md                              |  135 -
   docs/runtime_environment_plan.md                 |  226 -
   docs/v1_codex_self_robot_demo_20260628_report.md |  153 -
   docs/v1_delivery_roadmap.md                      |  545 --
   docs/v1_landing_progress.md                      | 7927 ----------------------
   docs/v1_overall_status.md                        |  485 --
   docs/v1_plan_gap_matrix.md                       |   83 -
   docs/v1_real_demo_20260628_report.md             |  163 -
   20 files changed, 76 insertions(+), 14447 deletions(-)
  ```

  Important note: the diff summary above reflects the existing old-doc archival state. New untracked harness files do not appear in `git diff --stat`.

  ## 4. Git Status

  ```text
   M AGENTS.md
   M docs/README.md
   D docs/agent_llm_provider_notes.md
   D docs/agent_prompt_catalog.md
   D docs/agent_prompt_contract.md
   D docs/agent_runtime_contract.md
   D docs/asset_and_review_flow_audit_20260701.md
   D docs/blender_asset_pipeline_contract.md
   D docs/concept_image_prompts_user_samples.md
   D docs/controller_design.md
   D docs/glb_to_mmd_rigging_notes.md
   D docs/reference_image_schema.md
   D docs/repo_layout.md
   D docs/runtime_environment_plan.md
   D docs/v1_codex_self_robot_demo_20260628_report.md
   D docs/v1_delivery_roadmap.md
   D docs/v1_landing_progress.md
   D docs/v1_overall_status.md
   D docs/v1_plan_gap_matrix.md
   D docs/v1_real_demo_20260628_report.md
  ?? docs/agent_execution_harness/
  ?? docs/olddocs/
  ?? docs/round_01_core_harness_package/
  ?? tests/test_agent_execution_harness_docs.py
  ```

  ## 5. Test Results

  ```bash
  python -m pytest tests/test_agent_execution_harness_docs.py -q
  ```

  ```text
  .....                                                                    [100%]
  5 passed in 0.02s
  ```

  ```bash
  python -m pytest -q
  ```

  ```text
  ........................................................................ [ 19%]
  ........................................................................ [ 39%]
  ........................................................................ [ 59%]
  ........................................................................ [ 78%]
  ........................................................................ [ 98%]
  ......                                                                   [100%]
  366 passed in 5.41s
  ```

  ## 6. Read-only Service Status Checks

  ```bash
  scripts/status_a40_services.sh || true
  scripts/status_glb_viewer.sh || true
  scripts/status_runtime_console.sh || true
  scripts/status_blender51_lab_mcp_bridge.sh || true
  ```

  ```text
  A40 status:
  available True
  count 1
  device0 NVIDIA A40
  free_total_gb (26.24, 44.34)
  nvidia-smi: Unable to determine the device handle ... Unknown Error
  ports listening: 8081, 8091

  GLB viewer:
  running pid=3713724
  URL: http://10.2.16.106:8092/

  Runtime console:
  running pid=368974
  URL: http://10.2.16.106:8093/

  Blender Lab MCP bridge:
  Blender 5.1.2
  running pid=1192219
  socket open on 127.0.0.1:9876
  ```

  ## 7. Live Call Declaration

  No live model service, image generation, HY-World, Hunyuan3D, or non-dry-run Blender MCP call was run.

  ## 8. Errors Or Blockers

  ```text
  No blockers.

  Notes:
  - `scripts/status_a40_services.sh` reported an NVML device-handle error from nvidia-smi, while torch still saw the A40 as available.
  - Blender bridge logs include historical SSBO binding-limit messages, but the bridge socket is open.
  - The worktree contains old-doc archival deletes and untracked `docs/olddocs/`; that state still needs user review before staging/commit.
  ```

  ## 9. Documentation Maintenance

  - Updated `docs/README.md`: yes.
  - Updated `AGENTS.md`: yes.
  - Added `docs/agent_execution_harness/progress_log.md` entry: yes.
  - Recorded design/decision: yes.

  ## 10. Next Round Suggestions

  1. Write a Round 02 task packet for the chat-thread asset library and user selection contract.
  2. Define asset library records for concept images, rejected images, subject GLBs, scene assets, previews, and packages.
  3. Define lineage from concept image to model/scene asset to Blender assembly to viewer/export/package.
  4. Extend `frontend_status.json` with derived asset-library and active-selection fields.
  5. Add state-transition tests proving rejected, archived, and selected assets stay inspectable and do not bypass user gates.