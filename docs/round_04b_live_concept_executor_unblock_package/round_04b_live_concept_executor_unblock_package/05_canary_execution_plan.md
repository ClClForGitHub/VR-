# Canary Execution Plan

Start with case_03_lunar_rover because it is the smallest real sample with one subject reference and a stable scientific scene.

Expected concept requirements:

```text
subject_concept: lunar rover image-guided from uploaded rover reference
scene_concept: lunar surface scene concept
 target_render: multi-image composite from subject_concept + scene_concept
```

Acceptance target for canary:

```text
subject_concept_images >= 1
scene_concept_images >= 1
target_render_images >= 1
live_generation_calls.jsonl output_image_path non-null for all successful requirements
frontend_status shows generated concept artifacts
```

Only after this passes should the runner proceed to Hunyuan3D, scene generation, Blender assembly, and then the rest of the 12 cases.
