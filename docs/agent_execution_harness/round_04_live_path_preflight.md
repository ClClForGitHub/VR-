# Round04 Live Path Preflight

This preflight prepares the 12 live user samples before any additional live
generation run. It records where inputs come from, where runtime uploads will
land, and where generated concept images must be written.

No live generation was executed for this preflight.

## Roots

```text
raw user samples and source references:
/home/team/zouzhiyuan/image23D_Agent/docs/test/测试样例

runner fixtures:
/home/team/zouzhiyuan/image23D_Agent/tests/fixtures/live_user_samples/round04

live run output root:
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples

local generated preflight manifests:
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples_path_preflight/round04_path_manifest.md
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples_path_preflight/round04_path_manifest.json
```

`outputs/` is git-ignored; the two preflight manifest files above are local
evidence pointers, not tracked repository artifacts.

## Runner Commands

All cases:

```bash
python scripts/run_round04_live_user_samples.py --fixtures-root /home/team/zouzhiyuan/image23D_Agent/tests/fixtures/live_user_samples/round04 --output-root /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples --all --live --overwrite --max-concept-regens 1
```

Single case:

```bash
python scripts/run_round04_live_user_samples.py --fixtures-root /home/team/zouzhiyuan/image23D_Agent/tests/fixtures/live_user_samples/round04 --output-root /home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples --case <case_id> --live --overwrite --max-concept-regens 1
```

## Per-Case Output Pattern

For every `<case_id>`:

```text
run_dir:
/home/team/zouzhiyuan/image23D_Agent/outputs/runs/round04_live_user_samples/<case_id>

runtime uploads:
<run_dir>/runtime_console/uploads/upload_*_<fixture_image_name>

concept generation calls:
<run_dir>/live_generation_calls.jsonl

generated concept images:
<run_dir>/runtime_worker/live_image/<index>_<safe_requirement_id>.png

child-Codex reference view copies:
<run_dir>/runtime_worker/live_image/reference_views/<safe_requirement_id>/

state and frontend evidence:
<run_dir>/state.json
<run_dir>/summary.json
<run_dir>/frontend_status.json
<run_dir>/runtime_handoff_apply_summary.json
<run_dir>/case_live_report.json
<run_dir>/case_report.md
```

Runtime upload filenames contain a generated `upload_<uuid>` prefix, so the
preflight records glob patterns instead of inventing fixed upload IDs.

## Case IDs

```text
case_01_tft_little_gwen
case_02_wuthering_beach
case_03_lunar_rover
case_04_hsr_train
case_05_xianxia_original
case_06_cyberpunk_alley
case_07_miniature_japanese_garden
case_08_industrial_quadruped
case_09_frieren_magic_bedroom
case_10_helltaker_cafe
case_11_stellar_blade_eve_tachy
case_12_stellar_blade_raven_adam_xion
```

The local JSON manifest contains the full requirement-level matrix for all 12
cases, including each expected output image path and target-render source path.

## Case 10 Binding Fix

`case_10_helltaker_cafe` now matches the user-confirmed test intent:

```text
Q版路西法.png
  fixture: tests/fixtures/live_user_samples/round04/case_10_helltaker_cafe/reference_images/image_001.png
  raw docs/test source: docs/test/测试样例/测试样例10/Q版路西法.png
  upload_stage: initial_request
  target: subject_lucifer_chibi
  usage: subject_reference

恶魔咖啡馆.png
  fixture: tests/fixtures/live_user_samples/round04/case_10_helltaker_cafe/reference_images/image_002.png
  raw docs/test source: docs/test/测试样例/测试样例10/恶魔咖啡馆.png
  upload_stage: concept_feedback_1
  target: scene_demon_cafe_office
  usage: scene_reference
```

The first concept-feedback action for case 10 uploads only the scene reference.
Lucifer remains bound to the first-round uploaded subject reference.

Expected case 10 concept outputs:

```text
01_subject_concept_subject_lucifer_chibi.png
02_subject_concept_subject_justice_chibi.png
03_subject_concept_subject_cerberus_chibi.png
04_scene_concept_1.png
05_target_render_final_preview.png
```

## Reference View Conversion Risks

The preflight found reference files whose suffix is not a reliable visual-tool
format signal. The image2 adapter now validates file content with Pillow before
accepting PNG/JPEG/WEBP as natively viewable, and otherwise writes a PNG
`view_path`.

Known references that will get PNG view copies:

```text
case_01_tft_little_gwen/image_001.png: content format WEBP
case_03_lunar_rover/image_001.avif: content format AVIF
case_04_hsr_train/image_001.png: content format WEBP
case_04_hsr_train/image_003.png: content format WEBP
case_04_hsr_train/image_005.jpg: content format WEBP
```

The original fixture/upload path remains the source of truth in
`input_image_paths` and `attachment_manifest.path`; `attachment_manifest.view_path`
is only the child Codex visual input copy.

## Verification

```bash
python -m py_compile agent_runtime/image2_reference_adapter.py scripts/run_round04_live_user_samples.py agent_runtime/round04_live_samples.py
python -m pytest tests/test_round04_live_sample_manifest.py tests/test_image2_reference_attachment_live_contract.py -q
```

Result:

```text
py_compile: passed
path/manifest tests: 8 passed
preflight manifest generation: case_count=12, issues=[]
```

