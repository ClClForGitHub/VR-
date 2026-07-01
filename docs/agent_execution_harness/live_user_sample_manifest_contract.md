# Live User Sample Manifest Contract

Each Round 04 case has a `case_manifest.json` with this shape:

```json
{
  "case_id": "case_03_lunar_rover",
  "title": "月球车月壤探测",
  "category": "realistic_single_mechanical_subject",
  "initial_user_request": "...",
  "reference_images": [
    {
      "slot": "@图片1",
      "image_id": "image_001",
      "path": "reference_images/image_001.avif",
      "declared_target_type": "subject",
      "declared_target_id": "subject_lunar_rover",
      "usage": "subject_reference",
      "required_for_generation": true
    }
  ],
  "scripted_user_actions": [
    {
      "gate": "concept_review",
      "action": "approve_concept",
      "text": "同意。"
    },
    {
      "gate": "model_review",
      "action": "approve_model_assets",
      "text": "同意。"
    }
  ],
  "expected_minimum_counts": {
    "concept_rounds": 1,
    "subject_concept_images": 1,
    "scene_concept_images": 1,
    "target_render_images": 1,
    "subject_glbs": 1,
    "scene_assets": 1,
    "preview_renders": 1,
    "viewer_glbs": 1
  }
}
```

The manifest is a test contract. If the implementation cannot parse or satisfy it, update the code or record an explicit blocker. Do not silently drop subjects, references, or scripted feedback.

