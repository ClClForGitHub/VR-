# Reference Image Schema

Updated: 2026-06-28

## Purpose

V1 must understand natural language together with uploaded images. The binding
between an image and its role is not optional: users must explicitly declare
what each image is for before high-cost generation proceeds.

## Intake Rule

The front end or controller assigns stable IDs such as:

```text
image_001
image_002
image_003
```

The user should bind them in text, for example:

```text
subject_hero reference: image_001
scene reference: image_002
style reference: image_003
```

If uploaded images are not bound, the controller must ask for clarification
instead of guessing. MLLM descriptions may help the user or future prompts, but
they do not replace explicit binding in V1.

For mixed natural-language/reference requests, the reference image controls only
the declared target. Example: "小小格温图片1在棋盘上" means image 1 binds to the
Little Gwen subject identity; the chessboard and chess pieces come from the
natural-language scene specification and must not be injected into the subject
reference/concept prompt.

## Runtime Models

Implemented in `agent_runtime.reference_intake`:

- `ReferenceImageInput`
- `ReferenceBindingPlan`
- `UserRequestIntake`
- `IntakeExtractionResult`

These models bridge UI/user text to existing `InputImage` and
`ReferenceBinding` state models.

## Supported Binding Targets

V1 supported target types:

- `subject`
- `scene`
- `style`
- `pose`
- `texture`
- `layout`

Supported usages mirror `ReferenceBinding.usage`:

- `subject_reference`
- `scene_reference`
- `style_reference`
- `pose_reference`
- `texture_reference`
- `layout_reference`

## Controller Outcome

Valid intake can proceed to SceneSpec compilation.

Invalid or incomplete intake produces:

- `requires_clarification=true`;
- open questions;
- a clarification prompt;
- no hidden image-purpose guess.
