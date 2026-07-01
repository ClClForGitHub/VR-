# Round04B Acceptance Checklist

- [ ] Branch starts from `round04-live-user-samples-full-flow`.
- [ ] New concept image executor consumes existing handoff payloads.
- [ ] The executor supports or explicitly blocks text_to_image, image_guided, and multi_image_composite separately.
- [ ] Required image references are attached as actual file inputs; no text-only downgrade.
- [ ] target_render source_requirement_ids resolve to generated source image files.
- [ ] `live_generation_calls.jsonl` records every call and output path.
- [ ] Successful concept generation applies through `runtime_handoff_apply`.
- [ ] `state.json` contains real generated concept artifacts.
- [ ] `frontend_status.json` exposes the generated concept artifacts and asset library entries.
- [ ] `case_03_lunar_rover` no longer blocks at the concept-generation executor boundary when backend succeeds.
- [ ] If downstream stages block, report the first real downstream blocker.
- [ ] Full pytest passes.
- [ ] Completion report is committed and pushed.
