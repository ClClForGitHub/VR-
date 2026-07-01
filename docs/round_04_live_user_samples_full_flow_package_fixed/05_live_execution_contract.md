# Round 04 真实调用执行契约

## 1. Preflight

先运行只读检查：

```bash
scripts/status_a40_services.sh
scripts/status_glb_viewer.sh
scripts/status_runtime_console.sh
scripts/status_blender51_lab_mcp_bridge.sh
```

如果服务不可用，不要伪造结果。记录 blocked。

## 2. 允许先 dry-run，不允许把 dry-run 当最终验收

允许用 dry-run/fixture 检查代码路径：

```text
sample parsing
runtime state transitions
frontend_status fields
handoff payload schema
```

最终 acceptance 必须使用真实调用：

```text
LLM / identity research
image generation
Hunyuan3D
HY-World/WorldMirror or explicitly approved real scene-asset path
Blender non-dry-run
```

## 3. 真实 image generation

每个 requirement 一条真实生成记录。

- `subject_concept`：主体干净图。
- `scene_concept`：场景图。
- `target_render`：最终构图图，必须 attach 前面生成的主体图和场景图。
- `image_guided`：必须 attach 用户参考图。

记录：

```text
live_generation_calls.jsonl
```

## 4. 真实模型服务

Hunyuan3D：

```text
input = selected subject_concept artifact file
output = subject GLB
```

WorldMirror/HY-World：

```text
input = selected scene concept / target render / reference image set
output = scene/world asset directory and scene GLB or adapter output
```

Blender：

```text
input = active_assembly_selection
output = .blend + preview render + viewer_scene.glb + scene_state.json
```

## 5. 返修循环

按样例文本模拟用户反馈。

- 概念图拒绝：`request_concept_changes` / ReviewPatch / regeneration。
- 模型拒绝：必须进入受控 model review/rework path，不得手写状态。
- 新增主体：必须更新 SceneSpec 和 requirements。
- 最终组合：必须通过 asset action / active_assembly_selection。

## 6. 失败处理

失败可以接受，伪成功不接受。

失败时必须记录：

```text
失败阶段
命令/API
日志路径
是否可重试
下一步建议
```

