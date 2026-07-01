# Codex Patch Brief v0.5.2

目标：修正 `web/creator_app` 当前产品流转和 UI 实现。不要换视觉方向；保留高级深色电影感风格，但重做结构、信息架构和真实 GLB viewer。

## Patch 1: Navigation and Layout

- Remove reveal / feedback compare / asset memory from main navigation.
- Main nav should include only: input-binding, concept-select, model-review, composition, director, delivery.
- Asset memory stays as top/right button and drawer.
- Remove duplicated top large nav area. Keep compact app header and left process nav.
- Ensure 1440px width first screen shows primary action button without scrolling.

## Patch 2: Reference Tray

- Implement fixed slots: subject 1-5 and scene 1.
- Do not display browser filename as product name.
- Do not show "usage" dropdown.
- Card actions: replace image, remove.
- Composer buttons: @, upload, send. @ opens reference picker.

## Patch 3: GenerationStatusDock

- Add background generation dock with pseudo progress.
- Progress caps 95-99 until backend done.
- On backend done: close dock and show CinematicRevealOverlay.
- Reveal overlay is not a route.

## Patch 4: Concept Selection

- Rewrite ConceptReviewScreen as ConceptSelectionScreen.
- Support categories: overall, subject, scene.
- Support subject tabs: subject 1-5 existing only.
- Selecting entity and version updates central preview.
- Maintain approvedConceptSelection state.
- Right actions: feedback drawer, selected combination modal, accept combination and generate models.
- Remove direct feedback compare as main screen.

## Patch 5: Feedback Drawer

- Targeted feedback by: overall, subject_n, scene_1.
- Textarea per target or selected target.
- Include upload reference and @ picker.
- Submit produces FeedbackTarget[] payload.

## Patch 6: Model Review

- Left model list grouped by entity and versions.
- Selecting model updates central viewer.
- Use real GLB viewer if url exists, otherwise poster fallback with disabled controls.
- Remove "switch to other model" button.
- Concept/model compare opens modal, not bottom fixed panel.
- Feedback opens ModelFeedbackDrawer with upload and @ picker.

## Patch 7: Real GLB Viewer

- Replace current poster-only GlbViewerShell.
- Use model-viewer V1.
- Props: glbUrl, poster, title, cameraPresets, disabledReason.
- Buttons have real behavior: auto-rotate, reset camera, fullscreen, screenshot, download.
- If no GLB: show poster fallback and disabled controls.

## Patch 8: Composition and Director

- Composition uses entity->version mapping.
- Final director uses viewer_scene.glb and scene_state.json if present.
- Object list only shown when scene_state objects have semantic labels.
- Otherwise show "object semantics unavailable".

## Patch 9: RuntimeAdapter

- Normalize reference slots.
- Normalize entities.
- Normalize asset versions separately.
- Do not mix subject entity with version.
- Preserve finalScene.viewerSceneUrl.
- Preserve model asset glb URL.

## Acceptance

- Run `npm run build`.
- Add screenshot smoke for: intake, concept selection, model review, composition, final review.
- At 1440px no primary action hidden below fold on intake.
- Model review must show either `<model-viewer>` or clear "GLB not ready" fallback.
