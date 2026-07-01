# Asset And Review Flow Audit

Updated: 2026-07-01

Scope: concept-image artifacts, JSON state handoff, runtime-console chat/upload
records, and frontend concept-review display for the three user samples.

## Verdict

Partially compliant after the 2026-07-01 fixes.

The repository has the right base pieces:

- `docs/repo_layout.md` says generated outputs belong under `outputs/runs/`
  and must not be committed.
- `FileArtifactStore` records artifact uri, size, sha256, mime type, semantic
  role, and metadata.
- runtime console uploads register `INPUT_IMAGE` artifacts and `InputImage`
  state records.
- `ConceptPromptPack.image_requirements` can now describe subject, scene, and
  target-render review images.
- `frontend_status.json` now exposes generation mode, input reference image ids,
  source requirement ids, and whether image inputs are mandatory.
- the runtime console concept-review cards now show whether a requirement is
  text-to-image, image-guided, or multi-image composite, plus reference/dependency
  counts.

## Fixed In This Slice

1. Concept-image result typing.

Previous behavior flattened delegated concept-image results into
`SUBJECT_CONCEPT_IMAGE`. That was wrong for scene concept images and final target
render images.

Current behavior:

- `output_type=subject_concept` -> `SUBJECT_CONCEPT_IMAGE` and
  `ConceptBundle.subject_concept_images`;
- `output_type=scene_concept` -> `SCENE_CONCEPT_IMAGE` and
  `ConceptBundle.scene_concept_image_ids`;
- `output_type=target_render` -> `FINAL_PREVIEW_IMAGE` and
  `ConceptBundle.final_preview_image_id`.

2. Frontend evidence visibility.

`frontend_status.concept_requirements[]` now includes:

- `generation_mode`;
- `input_reference_image_ids`;
- `source_requirement_ids`;
- `must_use_image_inputs`;
- `quality_bar`.

The browser card UI now surfaces the mode and counts for required image inputs
and source dependencies.

3. Prompt and MCP handoff docs.

`docs/concept_image_prompts_user_samples.md` records the full prompt set for:

- the agent planning rules;
- image MCP handoff rules;
- beach character subject/scene/target prompts;
- Little Gwen subject/scene/target prompts;
- rover subject/scene/target prompts.

The document explicitly requires web identity research for named IP/characters
and actual upload/attachment of reference images for image-guided and
multi-image-composite requirements.

4. Concept-generation handoff package.

`runtime_delegation` now writes a structured `concept_generation` payload into
each `generate_concept_images`/`regenerate_concept_images` handoff JSON. It
includes:

- the ordered `ConceptImageRequirement` list;
- prompt text per requirement;
- `input_reference_image_ids` plus resolved input image paths;
- `source_requirement_ids` for target renders;
- blocker notes for missing required input files;
- the expected handoff-apply `image_results` schema.

The task prompt now requires workers/sub-agents to execute requirements in
order and to mark a requirement blocked when the MCP/image tool cannot attach
mandatory images. The old "exactly one image" prompt is no longer the runtime
contract.

5. Guarded codex-self concept execution.

The existing `codex_self_mcp` worker backend can still plan a call and can still
support legacy single-image log extraction, but it does not expose a verified
multi-image upload interface. Confirmed non-dry-run execution is now blocked
for structured multi-requirement concept handoffs, mandatory input images, and
target-render source dependencies. This prevents the runtime from mistaking
"last generated image extracted from a log" for a full `GenerateConceptImages`
implementation.

## Still Not Fully Compliant

1. Historical live image folder is not a canonical runtime run.

`outputs/runs/20260630_live_review_images_codex_self/` is useful evidence, but
it is a flat manual image bundle. It does not have the canonical runtime shape:

```text
state.json
summary.json
frontend_status.json
artifacts/
checkpoints/
runtime_worker/
```

It should not be treated as accepted product evidence.

2. The old user-sample dry-run states predate the new requirement schema.

The run directories under:

```text
outputs/runs/20260630_actual_nl_first_step_check/
```

were produced before `generation_mode`, `input_reference_image_ids`, and
`source_requirement_ids` were added. They should be regenerated or superseded by
a new runtime run before frontend review.

3. True reference upload into image MCP is not yet proven in this run.

The contract now requires actual image attachments for:

- Little Gwen subject generation;
- target renders that depend on subject and scene concepts.

The next live generation run must record the actual input image paths sent to
the image backend in `generation_calls.jsonl` or runtime worker JSON. Text that
says "use image 1" is not sufficient.

## Required Shape For The Next Accepted Run

The next accepted concept-review run should use:

```text
outputs/runs/<date>_live_review_images_contract_v2/
  state.json
  summary.json
  frontend_status.json
  artifacts/
    input_image/
    subject_concept_image/
    scene_concept_image/
    final_preview_image/
  checkpoints/
  runtime_console/
    chat.jsonl
    uploads.jsonl
  runtime_worker/
    generation_calls.jsonl
    worker JSON or MCP logs
```

At minimum it must preserve:

- identity research evidence with URLs and confidence;
- `ConceptPromptPack` and `image_requirements`;
- actual image input paths passed to MCP;
- output artifact records with sha256;
- `frontend_status.json` showing all concept requirements ready;
- a screenshot or frontend smoke artifact for the review page.

## Verification In This Slice

```text
pytest -q tests/test_runtime_delegation.py tests/test_runtime_worker.py tests/test_concept_planning.py tests/test_frontend_status.py
32 passed in 1.13s

node --check web/runtime_console/app.js
pytest -q tests/test_frontend_status.py tests/test_runtime_delegation.py tests/test_runtime_worker.py tests/test_natural_language_scene_fixtures.py
35 passed in 1.56s

pytest -q tests/test_state_views.py tests/test_frontend_status.py tests/test_runtime_execution.py tests/test_runtime_loop.py tests/test_runtime_worker.py tests/test_runtime_delegation.py tests/test_runtime_user_actions.py tests/test_agent_prompts.py tests/test_concept_planning.py tests/test_natural_language_scene_fixtures.py
82 passed in 2.20s
```
