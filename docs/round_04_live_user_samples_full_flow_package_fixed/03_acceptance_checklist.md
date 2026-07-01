# Round 04 验收清单

## A. 代码链路

- [ ] 有受控样例入库/加载机制。
- [ ] 有真实用户样例 runner。
- [ ] runner 不直接编辑 state.json。
- [ ] 模型验收/返修路径存在并有测试。
- [ ] 新增主体后 SceneSpec / ConceptPromptPack / asset_library / selection 能更新。
- [ ] selected concept -> subject model handoff 使用用户选择。
- [ ] selected scene concept / target render -> scene asset handoff 使用用户选择。
- [ ] Blender payload 使用 active_assembly_selection。
- [ ] frontend_status/API 暴露全流程状态和资产。

## B. 真实调用

- [ ] 有 identity_research.jsonl。
- [ ] 有 live_generation_calls.jsonl。
- [ ] image_guided requirement 真实 attach/upload reference image。
- [ ] target_render 真实 attach/upload subject/scene concept images。
- [ ] Hunyuan3D 使用 selected concept artifact。
- [ ] HY-World/WorldMirror 使用 selected scene/target input 或记录真实替代路径。
- [ ] Blender non-dry-run 完成 preview / viewer export。

## C. 每个样例清点

- [ ] case_live_report.json 存在。
- [ ] case_report.md 存在。
- [ ] 记录概念轮数。
- [ ] 记录 subject_concept / scene_concept / target_render 数量。
- [ ] 记录 subject GLB 数量。
- [ ] 记录 scene asset 数量。
- [ ] 记录 Blender preview 是否存在。
- [ ] 记录 viewer GLB 是否存在。
- [ ] 记录 frontend_status 是否可见。
- [ ] 记录失败/阻塞原因。

## D. 前端联调准备

- [ ] runtime API 可以读取 case run。
- [ ] asset_library 可以展示。
- [ ] active_assembly_selection 可以展示。
- [ ] concept/model/scene/final preview 资产有 thumbnail 或文件链接。
- [ ] 用户同意/不同意/选择组合的 action payload 有示例。

## E. Git / 文档

- [ ] 全量测试通过。
- [ ] 输出目录和大文件未 commit。
- [ ] 完成报告已写入 docs/agent_execution_harness/round_04_completion_report.md。
- [ ] commit + push 完成。

