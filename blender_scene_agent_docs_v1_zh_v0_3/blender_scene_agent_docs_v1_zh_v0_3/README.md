# Blender 场景 Agent V1 中文文档集（v0.3 修订版）

本目录包含文本+图像到 Blender 场景 Agent 的 9 份中文工程文档。

本轮 v0.3 / v0.2 修订重点：

```text
1. V1 前端必须有 Web 端实时 3D 预览，不再只依赖 Blender 渲染图片。
2. Blender 在 Linux 服务器上作为权威场景与最终渲染环境。
3. 前端通过 viewer_scene.glb / viewer_scene.gltf + scene_state.json 实现 orbit / zoom / pan 查看。
4. 新增 ScenePreviewExporter、ViewerSyncService、Web3DPreviewRuntime 等模块。
5. Hunyuan3D 主体资产在 V1 中按静态 mesh/GLB 处理，不假设有骨架或动画。
6. 自动上骨架、角色动作、retargeting、复杂动画全部推迟到后续独立动画管线。
```

## 文档列表

1. `DOC-001_V1_Scope_and_Decisions_v0.3_zh.md`
   - V1 范围、决策、非目标、成功标准。

2. `DOC-002_Product_Workflow_Spec_v0.2_zh.md`
   - 产品流程与前端交互规范。新增 Web 端实时 3D Viewer 需求。

3. `DOC-003_Agent_Workflow_Design_v0.2_zh.md`
   - Agent / LangGraph 工作流设计。新增实时预览导出与同步节点。

4. `DOC-004_State_and_JSON_Schema_Spec_v0.2_zh.md`
   - 状态与 JSON Schema。新增 ViewerSceneState。

5. `DOC-005_Artifact_and_Versioning_Spec_v0.2_zh.md`
   - 产物与版本管理。新增 viewer_scene / scene_state 产物类型。

6. `DOC-006_Tool_and_MCP_Integration_Spec_v0.2_zh.md`
   - 工具与 MCP 接入。新增 export_viewer_scene；动画工具标记为暂缓。

7. `DOC-007_Hunyuan3D_and_Hunyuan_Mirror_Pipeline_Spec_v0.2_zh.md`
   - Hunyuan3D / Hunyuan Mirror 管线。明确 Hunyuan3D 输出默认静态资产，不承诺骨架。

8. `DOC-008_LLM_Node_and_Prompt_Spec_v0.2_zh.md`
   - LLM 节点与 Prompt 规范。新增动画请求的 V1 边界处理。

9. `DOC-009_QA_and_Evaluation_Spec_v0.2_zh.md`
   - QA 与评估规范。新增 Web 端实时 3D 预览质量门禁。
