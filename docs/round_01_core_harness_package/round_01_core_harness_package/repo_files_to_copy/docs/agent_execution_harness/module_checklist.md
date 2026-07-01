# Module Checklist

Use this checklist to keep implementation slices tied to product workflow modules.

## 1. Intake and reference binding

Entry:
- user chat text;
- optional uploaded images.

Required behavior:
- uploaded images must have explicit binding before high-cost generation;
- missing binding becomes a user clarification, not a guess.

Evidence:
- user turn recorded;
- input image artifacts registered;
- reference bindings or open questions recorded;
- frontend can show missing binding or ready state.

## 2. SceneSpec and natural-language understanding

Entry:
- valid intake or text-only request.

Required behavior:
- produce structured SceneSpec;
- preserve subject IDs, reference IDs, environment, camera, lighting, style, and constraints;
- named IP/character identity requires explicit research evidence before final image prompts.

Evidence:
- validated node output;
- controlled state apply;
- updated runtime plan;
- tests for Chinese/English and user samples.

## 3. Concept prompt and image requirements

Entry:
- SceneSpec ready.

Required behavior:
- create subject concept requirements for real subjects;
- create scene concept requirements for environment/layout;
- create target render requirement that depends on generated subject/scene concepts;
- image-guided requirements must carry actual input reference image IDs.

Evidence:
- ConceptPromptPack;
- ConceptImageRequirement[];
- frontend_status concept requirements;
- generation handoff with execution order.

## 4. Concept generation and review

Entry:
- concept image handoff ready.

Required behavior:
- generate or apply concept images through controlled worker/handoff-apply path;
- record actual image input paths when required;
- user approval or feedback is handled by runtime user-action.

Evidence:
- generated image artifacts;
- state concept bundle;
- frontend_status review state;
- runtime_worker / runtime_handoff_apply logs;
- user-action logs.

## 5. Chat asset library and selection

Entry:
- any generated or uploaded visible asset.

Required behavior:
- every concept image, subject model, scene asset, preview, and package becomes inspectable in the chat-thread asset library;
- rejected assets are not deleted by default;
- concept-to-model and concept-to-scene lineage is preserved;
- Blender assembly uses explicit user selection rather than the first available asset.

Evidence:
- asset library records;
- review/selection status;
- lineage fields;
- frontend_status asset library and active selection.

## 6. Subject model generation

Entry:
- selected and approved subject concept image.

Required behavior:
- generate subject GLB through existing Hunyuan3D path;
- use selected concept image as source;
- record profile, service evidence, output GLB, and QA.

Evidence:
- subject asset artifact;
- Asset3DRecord;
- QA result;
- handoff/apply logs;
- frontend status.

## 7. Scene/world asset generation

Entry:
- selected scene concept or approved scene plan.

Required behavior:
- generate or adapt scene/world asset through existing HY-World/WorldMirror path;
- preserve event IDs, output directory, scene GLB, and adapter summary.

Evidence:
- Scene3DRecord;
- scene GLB or output dir;
- event IDs when live;
- frontend status.

## 8. Blender assembly and preview

Entry:
- explicit assembly selection with subject model(s) and scene asset.

Required behavior:
- create Blender assembly plan;
- import selected assets;
- export viewer scene;
- render preview;
- stop at user preview gate.

Evidence:
- `.blend`;
- `viewer_scene.glb`;
- `scene_state.json`;
- preview PNG;
- frontend_status BLENDER_PREVIEW;
- user-action gate.

## 9. Preview edit and delivery

Entry:
- BLENDER_PREVIEW.

Required behavior:
- user changes become structured edit/selection updates;
- viewer is refreshed through controlled domain tools;
- approval advances to delivery;
- delivery package includes expected artifacts or explicit missing-item report.

Evidence:
- ReviewPatch or selection update;
- refreshed viewer/export/render artifacts;
- delivery package;
- metadata/version manifest;
- final frontend status.
