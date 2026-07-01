# Concept Image Executor Design Contract

The executor is the missing link between `ConceptImageRequirement[]` and real generated PNG artifacts.

Input source of truth:

```text
runtime_handoff/<handoff_id>.json -> concept_generation.requirements[]
```

Output source of truth:

```text
runtime_worker/<worker_id>.json
live_generation_calls.jsonl
artifacts/subject_concept_image/*
artifacts/scene_concept_image/*
artifacts/final_preview_image/*
state.json
frontend_status.json
```

Execution order:

1. Generate all subject_concept requirements.
2. Generate all scene_concept requirements.
3. Generate target_render requirements only after their source_requirement_ids are available.

Never treat prompt text like "use image 1" as image input. The backend call must receive local file paths for required image inputs.
