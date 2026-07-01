# Core Pipeline Test Matrix

Status: implemented for Round 03 dry-run/delegated semantics.

| Case ID | Purpose | Required assertions | Test file | Result |
| --- | --- | --- | --- | --- |
| `case_text_only_robot_display` | Pure text request creates subject, scene, and target render planning. | `subject_concept`, `scene_concept`, and `target_render` requirements exist; target render is `multi_image_composite`; target render depends on subject/scene requirement ids. | `tests/test_core_pipeline_semantics.py`, `tests/test_concept_prompt_requirements.py` | Passed in targeted suite. |
| `case_reference_bound_subject_and_scene` | Reference-bound subject and scene keep scopes separate. | Subject requirement is `image_guided` with subject ref only; scene requirement is `image_guided` with scene ref only; handoff resolves real input paths. | `tests/test_core_pipeline_semantics.py`, `tests/test_concept_prompt_requirements.py`, `tests/test_runtime_context_and_file_contract.py` | Passed in targeted suite. |
| `case_reject_then_reselect_old_concept` | User can reject a concept and later reselect it. | Concept feedback creates `ReviewPatch`; regeneration plan is created; rejected concept remains in `asset_library`; rejected concept can be selected for subject generation. | `tests/test_runtime_rework_flow.py`, `tests/test_model_generation_selection_contract.py` | Passed in targeted suite. |
| `case_multi_subject_selection_payload` | Multi-subject selections reach Blender assembly payload. | `active_assembly_selection.selected_subject_assets` carries per-subject asset ids; placement hints and selected scene/target refs are included in controller payload. | `tests/test_model_generation_selection_contract.py` | Passed in targeted suite. |
| `case_ip_identity_research_placeholder` | IP/character text cannot rely on hidden model memory. | Subject with `canonical_identity`, aliases, or identity confidence requires `identity_notes` evidence or clarification/blocking. | `tests/test_concept_prompt_requirements.py` | Passed in targeted suite. |
| `case_handoff_context_contract` | Delegated worker JSON contains enough context/schema. | Concept handoff includes SceneSpec, reference images, reference bindings, requirements, execution order, resolved images, source requirements, upload rules, and apply schema. Subject/scene asset handoffs include selected inputs and apply schemas. | `tests/test_runtime_context_and_file_contract.py`, `tests/test_runtime_delegation.py` | Passed in targeted and adjacent suites. |
| `case_frontend_status_core_pipeline` | Frontend gets enough backend state to render and submit next actions. | Derived status exposes phase/status, concept requirements with ready artifacts, asset library, active selection, available actions, and action payload examples. | `tests/test_frontend_status_core_pipeline.py`, `tests/test_frontend_status.py` | Passed in targeted and adjacent suites. |

Fixture source:

- `tests/fixtures/user_journeys/core_pipeline_semantic_cases.json`

Live evidence boundary:

- These tests prove local typed contracts, state transitions, runtime-plan payloads, and delegated handoff JSON.
- They do not prove live provider/model/service quality. Live evidence is tracked in `live_test_readiness_matrix.md` and is reserved for Round04 unless explicitly approved.
