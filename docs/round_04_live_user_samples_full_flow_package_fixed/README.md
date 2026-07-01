# Round 04 使用说明

这份包用于交给 Codex 执行 **Round 04：真实样例全流程执行与代码补齐**。

本轮不是前端 UI 美化，也不是继续新增抽象结构；目标是把 Round 03 已经补齐的核心语义链路推进到“能用用户样例真实跑完”的阶段。

## 你给 Codex 的方式

1. 把整个 ZIP 交给 Codex。
2. 让它先读 `01_给_Codex_执行包.md`。
3. 把你之后提供的 Markdown 样例和参考图一起交给它。
4. 要求它按 `04_样例与参考图入库规范.md` 放置样例和参考图。
5. 它完成后必须填写 `02_Codex_完成汇报模板.md`，并 commit + push。

## 本轮核心目标

- 用真实用户样例驱动完整业务流程。
- 补齐全流程执行所缺的后端代码、runtime action、目录管理、状态输出和测试。
- 真实调用 LLM / image generation / Hunyuan3D / HY-World or WorldMirror / Blender，不能用玩具 fixture 冒充最终结果。
- 前端必须能通过 `frontend_status.json` 和 runtime API 看到每个样例的阶段、资产库、可选资产、返修状态、最终预览和产物计数。

## 重要边界

- 可以先跑 dry-run/fixture 作为代码 preflight，但最终 Round 04 acceptance 必须是真实调用。
- 如果某个真实服务不可用，必须记录 blocked 证据，不能伪造成功。
- 生成输出放在 `outputs/runs/round04_live_user_samples/<case_id>/`，不要 commit。
- 用户提供的样例和参考图按规范放入输入目录；生成结果和大模型产物不进 git。

