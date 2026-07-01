# Round 04 前端可观测性验收清单

本轮不要求做前端 UI 美化，但必须让前端能看见真实业务状态。

## 1. runtime API

每个样例 run 必须能通过 runtime API 获取：

```text
phase
status
progress_label
concept_requirements
asset_library
active_assembly_selection
available_actions
file_manifest
viewer URLs
preview image paths
case report paths
```

## 2. frontend_status.json

必须展示：

```text
概念图生成中 / 待确认 / 返修中
模型生成中 / 模型待确认 / 模型返修中
场景生成中
Blender 组装中
最终预览待确认
完成/失败/阻塞
```

如果现有字段不足，扩展派生字段，不要让前端自己推断业务状态。

## 3. 资产库展示要求

每个 asset_library item 至少支持前端展示：

```text
asset_kind
artifact_id
subject_id / scene_id
review_status
selection_status
source_artifact_ids
derived_artifact_ids
thumbnail/file URL
created_at / updated_at
```

## 4. 用户 action payload 示例

必须提供并测试：

```text
approve_concept
request_concept_changes
approve_model_assets 或等价 action
request_model_changes 或等价 action
select_concept_for_subject_generation
select_asset_for_assembly
approve_blender_preview
request_blender_changes
```

## 5. 证据

每个 case 保存：

```text
frontend_status.json
runtime_api_bundle_snapshot.json
screenshot_if_browser_available.png
```

