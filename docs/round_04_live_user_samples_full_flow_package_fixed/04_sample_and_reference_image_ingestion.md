# Round 04 样例与参考图入库规范

## 1. 标准目录

用户提供的测试样例和参考图必须进入标准目录，不要散落在项目根目录。

推荐：

```text
tests/fixtures/live_user_samples/round04/<case_id>/
  user_script.md
  case_manifest.json
  reference_images/
    image_001.png
    image_002.jpg
    image_003.avif
```

如果参考图较大、不适合进 git，则使用：

```text
local_inputs/round04_live_user_samples/<case_id>/
  user_script.md
  case_manifest.json
  reference_images/
    image_001.png
```

并确保 `local_inputs/` 被 git ignore。生成输出必须放在：

```text
outputs/runs/round04_live_user_samples/<case_id>/
```

## 2. 图片槽位

用户文本中的 `@图片1`、`@图片2` 必须映射到 manifest 中的 stable id：

```json
{
  "slot": "@图片1",
  "image_id": "image_001",
  "path": "reference_images/image_001.png",
  "declared_target_type": "subject",
  "declared_target_id": "subject_little_gwen_base",
  "usage": "subject_reference"
}
```

不得只在 prompt 中写“参考图片1”。必须在 image-generation 调用记录中出现真实文件路径。

## 3. 样例脚本

每个 case 的 `case_manifest.json` 至少包含：

```json
{
  "case_id": "case_03_lunar_rover",
  "title": "月球车月壤探测",
  "initial_user_request": "...",
  "reference_images": [],
  "scripted_user_actions": [
    {"gate": "concept_review", "action": "approve_concept", "text": "同意。"},
    {"gate": "model_review", "action": "approve_model_assets", "text": "同意。"},
    {"gate": "assembly_selection", "action": "select_asset_for_assembly", "text": "选择组合..."}
  ],
  "expected_minimum_counts": {
    "subject_concept_images": 1,
    "scene_concept_images": 1,
    "target_render_images": 1,
    "subject_glbs": 1,
    "scene_assets": 1,
    "preview_renders": 1
  }
}
```

## 4. 原始样例保留

必须保留用户原始 Markdown，不要只保留抽取后的 JSON。

```text
user_script.md
case_manifest.json
```

如果解析不确定，记录在：

```text
case_parse_notes.md
```

## 5. 提交流程

小型文本 manifest 可以 commit。

参考图是否 commit 由用户决定。默认：

```text
- 用户明确要求作为测试 fixture 的小图可以 commit。
- 大图、生成图、模型输出、Blender 文件不 commit。
- 所有生成结果在 outputs/runs 下留证据。
```

