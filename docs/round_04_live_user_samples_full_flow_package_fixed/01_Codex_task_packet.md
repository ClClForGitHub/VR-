# Round 04 执行包：真实用户样例全流程执行与代码补齐

## 0. 分支和前置条件

从 Round 03 分支继续：

```bash
git fetch origin
git checkout round03-core-pipeline-semantics
git pull --ff-only

git checkout -b round04-live-user-samples-full-flow
```

先确认 Round 03 状态和测试：

```bash
git status --short
python -m pytest tests/test_core_pipeline_semantics.py tests/test_concept_prompt_requirements.py tests/test_runtime_rework_flow.py tests/test_model_generation_selection_contract.py tests/test_runtime_context_and_file_contract.py tests/test_frontend_status_core_pipeline.py -q
```

## 1. 本轮目标

把当前后端从“语义链路和 dry-run/delegated 测试通过”推进到“用户样例可以真实走完整业务流”。

必须覆盖：

```text
用户 Markdown 样例 + 参考图
  -> runtime run 创建
  -> 聊天 turn / 上传图 / 显式绑定
  -> 自然语言理解 / identity research evidence
  -> SceneSpec
  -> ConceptPromptPack
  -> subject_concept / scene_concept / target_render requirements
  -> 真实 image generation MCP/tool 调用，必须真实 attach 参考图和 source concept 图
  -> 概念图入 asset_library
  -> 按样例脚本模拟用户同意/不同意/新增主体/返修
  -> 用户选择概念图进入模型生成
  -> 真实 Hunyuan3D subject GLB 生成
  -> 真实 HY-World/WorldMirror scene asset 生成或经批准的真实注册路径
  -> 模型/场景验收或返修
  -> active_assembly_selection
  -> Blender 组装 / viewer export / preview render
  -> frontend_status.json + runtime API 可展示全过程
  -> 每个样例生成清点报告
```

## 2. 必须先读

```text
AGENTS.md
docs/README.md
docs/agent_execution_harness/README.md
docs/agent_execution_harness/runtime_flow_rules.md
docs/agent_execution_harness/live_test_policy.md
docs/agent_execution_harness/round_03_core_pipeline_semantics.md
docs/agent_execution_harness/core_pipeline_test_matrix.md
docs/agent_execution_harness/live_test_readiness_matrix.md
agent_runtime/state.py
agent_runtime/controller.py
agent_runtime/runtime_jobs.py
agent_runtime/runtime_loop.py
agent_runtime/runtime_delegation.py
agent_runtime/runtime_handoff_apply.py
agent_runtime/runtime_asset_actions.py
agent_runtime/runtime_user_actions.py
agent_runtime/frontend_status.py
tools/runtime_console_server.py
```

再读本包中的：

```text
04_样例与参考图入库规范.md
05_真实调用执行契约.md
06_前端可观测性验收清单.md
repo_files_to_copy/docs/agent_execution_harness/round_04_live_full_flow_user_samples.md
repo_files_to_copy/tests/fixtures/live_user_samples/round04_samples_manifest.json
```

## 3. 允许修改

```text
agent_runtime/
tools/runtime_console_server.py
scripts/
tests/
docs/agent_execution_harness/
docs/README.md
web/runtime_console/  # 只允许必要的状态展示/API wiring，不做视觉重构
```

## 4. 禁止事项

```text
不要绕过 runtime/controller/user-action/handoff-apply 直接手写 state.json。
不要把 fixture/dry-run/fake image/fake GLB 当成最终 live acceptance。
不要只在 prompt 里写“参考图1”而不把图片实际 attach/upload 到 image generation。
不要把 delegated/running 当 completed。
不要创建第二套 artifact store、第二套 queue、第二套 viewer、第二套 runtime state。
不要把 outputs/runs、run_logs、模型权重、服务 repo、大型生成资产 commit。
不要为了测试通过降低业务约束。
```

## 5. 任务 A：样例与参考图入库

实现或补齐一个受控样例入库流程。

建议路径：

```text
tests/fixtures/live_user_samples/round04/<case_id>/
  user_script.md
  case_manifest.json
  reference_images/
    image_001.<ext>
    image_002.<ext>
```

如果用户提供的图片较大或不适合进 git，则放入：

```text
local_inputs/round04_live_user_samples/<case_id>/reference_images/
```

并在 `case_manifest.json` 中记录绝对/相对路径。`local_inputs/` 和生成输出不得 commit。

必须实现一个 loader 或脚本，能把样例 Markdown + reference image slots 解析成 runtime 输入：

```text
initial_user_request
concept_feedback_rounds
model_feedback_rounds
reference_image_bindings
expected_subjects
expected_scene
expected_actions
expected_minimum_counts
```

## 6. 任务 B：补齐真实用户流程 runner

新增一个 Round 04 live runner，名称可自行决定，例如：

```text
scripts/run_round04_live_user_samples.py
```

或者复用现有 runtime console API，但必须保留脚本化入口。

runner 必须：

```text
1. 为每个 case 创建独立 run_dir。
2. 通过正式 runtime/chat/upload/user-action/asset-action/handoff-apply 路径推进状态。
3. 按样例脚本模拟用户概念图同意/拒绝、模型同意/拒绝、新增主体、选择组合。
4. 不允许直接编辑 state.json。
5. 每个阶段写入 run-local evidence。
6. 每个 case 输出 case_live_report.json 和 human-readable case_report.md。
```

输出位置：

```text
outputs/runs/round04_live_user_samples/<case_id>/
  state.json
  summary.json
  frontend_status.json
  runtime_plan.json
  runtime_console/
  runtime_execution.jsonl
  runtime_loop.jsonl
  runtime_worker/
  runtime_handoff/
  runtime_handoff_apply.jsonl
  runtime_user_action.jsonl
  runtime_asset_action.jsonl
  live_generation_calls.jsonl
  identity_research.jsonl
  artifacts/
  blender_viewer/ or viewer_export/
  case_live_report.json
  case_report.md
```

## 7. 任务 C：模型验收 / 返修逻辑

当前代码如果没有明确的“模型阶段同意/不同意”后端路径，必须补齐。

允许的实现方式：

```text
方案 1：新增受控 user/action，例如 request_model_changes / approve_model_assets。
方案 2：复用 runtime_asset_actions + ReviewPatch，但必须有明确 phase/status/frontend_status 表示。
方案 3：新增 WorkflowPhase.ASSET_REVIEW 或 MODEL_REVIEW，但必须同步 controller/runtime/frontend/tests。
```

无论选哪种，都必须满足：

```text
用户模型反馈“同意”后，才能进入最终 assembly selection / Blender 组合。
用户模型反馈“不同意，重新生成概念图”后，必须产生 ReviewPatch，并回到 concept regeneration，不得重开 intake。
用户新增主体后，SceneSpec / ConceptPromptPack / asset_library / selection 必须更新 lineage。
```

## 8. 任务 D：真实 image generation 调用

必须对每个 concept requirement 真实调用 image generation 工具或 MCP。

要求：

```text
subject_concept：主体干净图，适合 Hunyuan3D。
scene_concept：场景/环境图，不混入主体 identity。
target_render：必须使用已经生成的 subject_concept + scene_concept 作为 visual inputs。
image_guided：必须实际 attach/upload input_reference_image_ids 对应文件。
multi_image_composite：必须实际 attach/upload source_requirement_ids 对应生成图。
```

必须写：

```text
live_generation_calls.jsonl
```

每条记录至少包括：

```json
{
  "case_id": "case_01_tft_little_gwen",
  "requirement_id": "subject_concept:subject_little_gwen",
  "generation_mode": "image_guided",
  "prompt": "...",
  "input_image_paths": ["..."],
  "source_requirement_ids": [],
  "source_image_paths": [],
  "output_image_path": "...",
  "backend": "...",
  "ok": true,
  "issues": []
}
```

如果 backend 不能 attach required images，必须 blocked，不能降级成 text-only。

## 9. 任务 E：真实 LLM / identity research

对 IP、游戏、角色、皮肤、场景专名必须有 identity research evidence。

必须写：

```text
identity_research.jsonl
```

每条至少包括：

```json
{
  "case_id": "case_01_tft_little_gwen",
  "query": "小小格温 云顶之弈 斗魂觉醒 水晶玫瑰 咖啡甜心",
  "resolved_identity": "...",
  "aliases": ["..."],
  "source_urls": ["..."],
  "source_quality": "official | wiki | community | unknown",
  "confidence": 0.0,
  "notes": "..."
}
```

如果 Codex 当前环境没有 web/search 能力，必须把 case 标记 blocked_for_identity_research，不允许靠模型记忆伪造官方特征。

## 10. 任务 F：真实 Hunyuan3D / HY-World / Blender

按样例选择结果执行真实模型/场景/Blender 流程。

要求：

```text
Hunyuan3D：必须使用 selected concept artifact 作为 source image。
HY-World/WorldMirror：必须使用 selected scene concept / target render / reference inputs，或记录经用户批准的真实替代路径。
Blender：必须使用 active_assembly_selection 中的 subject assets、scene asset、target render、placement hints。
```

每个 case 最终至少要清点：

```text
concept_round_count
subject_concept_image_count
scene_concept_image_count
target_render_image_count
subject_glb_count
scene_asset_count
blender_file_exists
viewer_scene_glb_exists
preview_render_exists
frontend_status_visible
case_completed
```

## 11. 任务 G：前端可观测性

不要做 UI 美化，但前端/runtime API 必须能看到流程。

最低要求：

```text
GET /api/runs/<run_key> 返回 asset_library、active_assembly_selection、concept_requirements、available actions、file manifest。
frontend_status.json 显示当前 phase/status/progress_label。
样例执行过程中前端可看到概念图、模型资产、场景资产、最终 viewer/preview。
每个 case 保存一次 runtime console API snapshot。
如有浏览器可用，保存一张 runtime console screenshot。
```

## 12. 测试要求

先补自动化测试：

```bash
python -m pytest tests/test_core_pipeline_semantics.py tests/test_concept_prompt_requirements.py tests/test_runtime_rework_flow.py tests/test_model_generation_selection_contract.py tests/test_runtime_context_and_file_contract.py tests/test_frontend_status_core_pipeline.py -q
python -m pytest tests/test_runtime_asset_actions.py tests/test_runtime_handoff_apply.py tests/test_runtime_delegation.py tests/test_frontend_status.py tests/test_controller.py -q
```

必须新增 Round 04 测试，名称可调整：

```text
tests/test_round04_live_sample_manifest.py
tests/test_round04_live_runner_contract.py
tests/test_round04_model_review_flow.py
tests/test_round04_frontend_observability.py
```

然后运行全量：

```bash
python -m pytest -q
```

## 13. 真实执行要求

在 preflight 通过、服务 status 正常后，执行真实样例。

建议先跑 case 03 作为 canary：月球车单主体写实机械，最稳。

```bash
python scripts/run_round04_live_user_samples.py --case case_03_lunar_rover --live --max-concept-regens 2
```

canary 完成后跑全部：

```bash
python scripts/run_round04_live_user_samples.py --all --live --max-concept-regens 2
```

如果一个 case 因模型质量失败，需要按样例反馈走返修，不允许直接手工修 state。

## 14. 提交和推送

完成后：

```bash
git status --short
python -m pytest -q
```

确认没有 outputs/run_logs/models/大文件/解压包目录后：

```bash
git add agent_runtime tools scripts tests docs
# 不要 git add outputs/ run_logs/ models/ local_inputs/ 大型图片/生成资产
git commit -m "Run Round04 live user sample pipeline"
git push -u origin round04-live-user-samples-full-flow
```

最后填写 `02_Codex_完成汇报模板.md`，并把报告保存为：

```text
docs/agent_execution_harness/round_04_completion_report.md
```

报告也要 commit + push。

