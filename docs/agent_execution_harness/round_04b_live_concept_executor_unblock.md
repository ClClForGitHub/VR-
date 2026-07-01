# Round04B Live Concept Executor Unblock

Round04 exposed a real product blocker: the runtime could plan concept
requirements and apply concept artifacts, but no reusable backend executed
multi-requirement concept generation with actual reference-image attachments
and target-render composition.

## Implemented Boundary

- Added `agent_runtime/concept_image_execution.py` as the structured executor
  between `runtime_handoff/<handoff_id>.json` and
  `runtime_handoff_apply.apply_concept_handoff_result`.
- Added `RuntimeWorkerBackend="live_image"` in `runtime_worker.py`.
- Kept the existing `codex_self_mcp` guard path intact.
- Added `scripts/probe_live_image_backend.py` for read-only capability reports.
- Updated `scripts/run_round04_live_user_samples.py --live` so the canary uses:
  `execute_next_runtime_job` -> `plan_next_delegated_handoff` ->
  `execute_next_runtime_worker(..., backend="live_image")`.

## Execution Contract

The executor reads `concept_generation.requirements[]` and
`concept_generation.execution_order` from the existing handoff JSON.

Per requirement it records:

- `requirement_id`
- `output_type`
- `generation_mode`
- `prompt`
- `input_reference_image_ids`
- `input_image_paths`
- `source_requirement_ids`
- `source_image_paths`
- `backend`
- `started_at`
- `finished_at`
- `output_image_path`
- `ok`
- `issues`

The log path is:

```text
<run_dir>/live_generation_calls.jsonl
```

## Dependency Rules

- `text_to_image` may run without file inputs only when the selected backend
  declares `text_to_image=true`.
- `image_guided` resolves every `resolved_input_images[].uri` to an existing
  local file path and requires backend image-input support.
- `multi_image_composite` resolves `source_requirement_ids` to previous
  generated output paths and requires backend multi-image composition support.
- A mixed structured handoff that requires image-guided or multi-image support
  preflights backend capability before starting partial text-only generation.
- If required attachments are unsupported or missing, the requirement is blocked
  with explicit issues. There is no text-only downgrade for live acceptance.

## Backend Probe Result

Command:

```bash
python scripts/probe_live_image_backend.py --write-report outputs/runs/round04b_probe/live_image_backend_probe.json
```

Result:

```text
backend: codex_self_mcp
text_to_image: true
image_guided_single_reference: false
multi_image_composite: false
output_extraction: true
structured_file_attachments: false
live_acceptance_ready: false
probe_report_path: outputs/runs/round04b_probe/live_image_backend_probe.json
```

Conclusion:

The default codex-self helper can extract a prompt-only generated image, but it
does not expose proven local-file attachment or multi-image composition
arguments. It is therefore not accepted as the Round04B live backend for
image-guided canaries.

## Canary Result

Command:

```bash
python scripts/run_round04_live_user_samples.py --case case_03_lunar_rover --live --overwrite --max-concept-regens 1
```

Result:

```text
exit_code: 1
case_id: case_03_lunar_rover
status: blocked
run_dir: outputs/runs/round04_live_user_samples/case_03_lunar_rover
worker_backend: live_image
worker_status: failed
call_count: 3
successful_call_count: 0
```

Blocking issues:

```text
backend_missing_required_image_guided_support:codex_self_mcp
backend_missing_required_multi_image_composite_support:codex_self_mcp
backend_missing_structured_file_attachment_support:codex_self_mcp
```

Evidence:

```text
outputs/runs/round04_live_user_samples/case_03_lunar_rover/live_generation_calls.jsonl
outputs/runs/round04_live_user_samples/case_03_lunar_rover/runtime_worker_summary.json
outputs/runs/round04_live_user_samples/case_03_lunar_rover/summary.json
```

The canary uploaded the real lunar-rover reference image and recorded its
resolved input path. It did not start partial prompt-only generation after the
preflight found missing structured attachment support.

## Verification

```bash
python -m py_compile agent_runtime/concept_image_execution.py agent_runtime/runtime_worker.py scripts/probe_live_image_backend.py scripts/run_round04_live_user_samples.py tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py
pytest -q tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py
pytest -q tests/test_concept_image_execution_contract.py tests/test_runtime_worker_live_image_backend.py tests/test_round04_live_canary_execution.py tests/test_runtime_worker.py tests/test_round04_live_runner_contract.py
pytest -q
```

Results:

```text
py_compile: passed
new Round04B tests: 5 passed
targeted related tests: 15 passed
full pytest: 405 passed
```

## Remaining Blocker

A real provider backend still needs to be wired or proven with:

- actual local reference-image attachments for `image_guided`;
- actual multi-image source attachment for `target_render`;
- generated image files under the run directory;
- handoff-apply evidence through the existing artifact/state/checkpoint path.
