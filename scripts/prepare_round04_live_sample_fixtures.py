#!/usr/bin/env python3
"""Prepare Round04 live user sample fixtures from the user-provided docs/test folder."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = ROOT / "docs/test/测试样例"
DEFAULT_OUTPUT_ROOT = ROOT / "tests/fixtures/live_user_samples/round04"


CASE_DEFS: list[dict[str, Any]] = [
    {
        "number": 1,
        "case_id": "case_01_tft_little_gwen",
        "title": "TFT 小小格温多皮肤灵魂莲华棋盘",
        "category": "q_chibi_ip_multi_skin_scene",
        "expected_scene": "云顶棋盘灵魂莲华场景",
        "subjects": [
            ("subject_little_gwen_base", "小小格温", "character", ["image_001"]),
            ("subject_little_gwen_soul_fighter", "斗魂觉醒皮肤小小格温", "character", ["image_002"]),
            ("subject_little_gwen_crystal_rose", "水晶玫瑰皮肤小小格温", "character", ["image_003"]),
            ("subject_little_gwen_cafe_cuties", "咖啡甜心小小格温", "character", ["image_004"]),
        ],
        "references": [
            ("@图片1", "image_001", "测试样例1/小小格温.png", "subject", "subject_little_gwen_base", "subject_reference", "concept_feedback_1"),
            ("@图片2", "image_002", "测试样例1/斗魂觉醒 小小格温.jpg", "subject", "subject_little_gwen_soul_fighter", "subject_reference", "concept_feedback_1"),
            ("@图片3", "image_003", "测试样例1/水晶玫瑰 小小格温.jpg", "subject", "subject_little_gwen_crystal_rose", "subject_reference", "concept_feedback_1"),
            ("@图片4", "image_004", "测试样例1/咖啡甜心 小小格温.jpg", "subject", "subject_little_gwen_cafe_cuties", "subject_reference", "concept_feedback_1"),
            ("@图片5", "image_005", "测试样例1/灵魂莲华 棋盘.png", "scene", "scene_tft_spirit_blossom_board", "scene_reference", "concept_feedback_1"),
        ],
        "actions": [
            ("concept_review", "request_concept_changes", "拒绝。角色外观不符合要求，概念图不干净；新增咖啡甜心小小格温，并上传 5 张参考图重新生成。", ["image_001", "image_002", "image_003", "image_004", "image_005"], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "第二轮用户概念图反馈：同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "同意。选择组合所有主体格温 + 场景棋盘。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 4, "scene_concept_images": 1, "target_render_images": 1, "subject_glbs": 4},
    },
    {
        "number": 2,
        "case_id": "case_02_wuthering_beach",
        "title": "鸣潮 Q版多人沙滩新增终末地角色",
        "category": "q_chibi_anime_beach_multi_character",
        "expected_scene": "沙滩场景，含沙滩椅、螃蟹、沙堆城堡",
        "subjects": [
            ("subject_phoebe_chibi", "Q版菲比", "character", []),
            ("subject_florollo_chibi", "Q版弗洛洛", "character", []),
            ("subject_daniya_chibi", "Q版达妮娅", "character", []),
            ("subject_gugugaga_endfield_admin", "终末地女管理员二创角色咕咕嘎嘎", "character", []),
        ],
        "references": [],
        "actions": [
            ("concept_review", "approve_concept", "同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "request_model_changes", "不同意。角色模型失真严重，概念图要重新生成；新增终末地女管理员二创角色咕咕嘎嘎。", [], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "第二轮用户概念图反馈：同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "第二轮用户模型反馈：同意。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 4, "scene_concept_images": 1, "target_render_images": 1, "subject_glbs": 4},
    },
    {
        "number": 3,
        "case_id": "case_03_lunar_rover",
        "title": "月球车月壤探测",
        "category": "realistic_single_mechanical_subject",
        "expected_scene": "月球表面月壤探测场景",
        "subjects": [("subject_lunar_rover", "月球车", "vehicle", ["image_001"])],
        "references": [
            ("@图片1", "image_001", "测试样例3/月球车.avif", "subject", "subject_lunar_rover", "subject_reference", "initial_request"),
        ],
        "actions": [
            ("concept_review", "approve_concept", "同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "同意。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 1},
    },
    {
        "number": 4,
        "case_id": "case_04_hsr_train",
        "title": "星穹铁道 Q版列车车厢多人场景",
        "category": "q_chibi_scifi_indoor_ip_multi_character",
        "expected_scene": "星穹列车车厢，窗外宇宙和星球，桌面咖啡杯、黑胶唱片、全息投影",
        "subjects": [
            ("subject_kafka_chibi", "Q版卡芙卡", "character", ["image_001"]),
            ("subject_silver_wolf_chibi", "Q版银狼", "character", ["image_002"]),
            ("subject_blade_chibi", "Q版刃", "character", ["image_003"]),
            ("subject_pom_pom_chibi", "帕姆", "character", ["image_004"]),
        ],
        "references": [
            ("@图片1", "image_001", "测试样例4/卡芙卡.png", "subject", "subject_kafka_chibi", "subject_reference", "concept_feedback_1"),
            ("@图片2", "image_002", "测试样例4/银狼.jpg", "subject", "subject_silver_wolf_chibi", "subject_reference", "concept_feedback_1"),
            ("@图片3", "image_003", "测试样例4/刃.png", "subject", "subject_blade_chibi", "subject_reference", "concept_feedback_1"),
            ("@图片4", "image_004", "测试样例4/帕姆.jpg", "subject", "subject_pom_pom_chibi", "subject_reference", "concept_feedback_1"),
            ("@图片5", "image_005", "测试样例4/车厢.jpg", "scene", "scene_astral_express_carriage", "scene_reference", "concept_feedback_1"),
        ],
        "actions": [
            ("concept_review", "request_concept_changes", "拒绝。角色脸部和服装不够像，列车车厢氛围不对；上传 5 张参考图并新增帕姆。", ["image_001", "image_002", "image_003", "image_004", "image_005"], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "第二轮用户概念图反馈为空，按用户确认模拟为同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "同意。角色和场景都可以，进入最终模型组合。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 4, "subject_glbs": 4},
        "parse_notes": ["第二轮用户概念图反馈为空；用户在对话中确认应模拟为同意。"],
    },
    {
        "number": 5,
        "case_id": "case_05_xianxia_original",
        "title": "原创国风仙侠悬崖道观",
        "category": "original_xianxia_fantasy_scene",
        "expected_scene": "悬崖边道观，云海日出，松树山石符纸",
        "subjects": [
            ("subject_female_sword_cultivator", "年轻女性剑修", "character", []),
            ("subject_white_fox_spirit_pet", "白狐灵宠", "animal", []),
            ("subject_blue_luan_bird", "青鸾", "animal", []),
            ("subject_stone_lantern", "石灯笼", "prop", []),
        ],
        "references": [],
        "actions": [
            ("concept_review", "approve_concept", "同意。整体气质和构图我满意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "request_model_changes", "不同意。服装层次太复杂、发饰太碎、青鸾不稳定；简化设计并新增石灯笼。", [], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "第二轮用户概念图反馈：同意。现在更适合落地成 3D 模型了。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "第二轮用户模型反馈：同意。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 4, "subject_glbs": 4},
    },
    {
        "number": 6,
        "case_id": "case_06_cyberpunk_alley",
        "title": "赛博朋克雨夜霓虹小巷",
        "category": "realistic_cyberpunk_scene_with_subjects",
        "expected_scene": "雨夜霓虹小巷，积水反射、机车、全息广告牌、金属管道",
        "subjects": [
            ("subject_short_haired_female_hacker", "短发女黑客", "character", []),
            ("subject_hovering_drone", "悬浮无人机", "prop", []),
            ("subject_mechanical_cat", "机械猫", "animal", []),
            ("subject_vending_machine", "自动贩卖机", "prop", []),
        ],
        "references": [
            ("@图片1", "image_001", "测试样例6/场景参考图.png", "scene", "scene_cyberpunk_rainy_neon_alley", "scene_reference", "concept_feedback_1"),
        ],
        "actions": [
            ("concept_review", "request_concept_changes", "拒绝。主体摆放不清楚；上传一张场景参考图，不上传角色参考图，并新增自动贩卖机。", ["image_001"], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "第二轮用户概念图反馈：同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "同意。选择组合所有主体和雨夜霓虹小巷场景。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 4, "subject_glbs": 4},
    },
    {
        "number": 7,
        "case_id": "case_07_miniature_japanese_garden",
        "title": "微缩日式庭院场景",
        "category": "miniature_environment_scene",
        "expected_scene": "木质茶室、红枫树、石灯笼、鲤鱼池、竹篱笆、碎石小路、木桥",
        "subjects": [
            ("subject_wooden_teahouse", "木质茶室", "architecture_part", ["image_001"]),
            ("subject_red_maple_tree", "红枫树", "environment_asset", ["image_003"]),
            ("subject_stone_lantern", "石灯笼", "prop", []),
            ("subject_koi_pond", "鲤鱼池", "environment_asset", ["image_002"]),
            ("subject_bamboo_fence", "竹篱笆", "environment_asset", []),
            ("subject_gravel_path", "碎石小路", "environment_asset", []),
            ("subject_wooden_bridge", "木桥", "architecture_part", []),
        ],
        "references": [
            ("@图片1", "image_001", "测试样例7/茶室结构.png", "subject", "subject_wooden_teahouse", "subject_reference", "model_feedback_1"),
            ("@图片2", "image_002", "测试样例7/日式庭院布局.png", "layout", "scene_miniature_japanese_garden", "layout_reference", "model_feedback_1"),
            ("@图片3", "image_003", "测试样例7/红枫树.png", "subject", "subject_red_maple_tree", "subject_reference", "model_feedback_1"),
        ],
        "actions": [
            ("concept_review", "approve_concept", "同意。整体构图和元素布局我满意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "request_model_changes", "不同意。茶室复杂、红枫太散、比例不协调；上传三张参考图并新增木桥。", ["image_001", "image_002", "image_003"], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "第二轮用户概念图反馈：同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "第二轮用户模型反馈：同意。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 7, "subject_glbs": 7},
    },
    {
        "number": 8,
        "case_id": "case_08_industrial_quadruped",
        "title": "写实工业四足巡检机器人",
        "category": "realistic_mechanical_industrial_scene",
        "expected_scene": "室内工业厂房，工具箱、警示路障、管线、监控屏幕、金属平台、小型机械臂工作台",
        "subjects": [
            ("subject_quadruped_inspection_robot", "四足巡检机器人", "vehicle", []),
            ("subject_small_robotic_arm_workbench", "小型机械臂工作台", "prop", []),
            ("subject_toolbox", "工具箱", "prop", []),
            ("subject_warning_barricade", "警示路障", "prop", []),
            ("subject_industrial_pipelines", "工业管线", "environment_asset", []),
            ("subject_monitoring_screen", "监控屏幕", "prop", []),
            ("subject_metal_platform", "金属平台", "environment_asset", []),
        ],
        "references": [],
        "actions": [
            ("concept_review", "approve_concept", "同意。整体方向可以。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "request_model_changes", "不同意。机器人腿部关节和比例不合理，厂房关系不明确；不上传参考图，新增小型机械臂工作台。", [], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "第二轮用户概念图反馈：同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "第二轮用户模型反馈：同意。选择组合所有主体。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 7, "subject_glbs": 7},
    },
    {
        "number": 9,
        "case_id": "case_09_frieren_magic_bedroom",
        "title": "葬送的芙莉莲 Q版温馨魔法书房",
        "category": "anime_ip_magic_indoor_scene",
        "expected_scene": "温暖魔法书房，书架、魔法阵地毯、药水瓶、木桌、夜晚星空窗景",
        "subjects": [
            ("subject_frieren_chibi", "Q版芙莉莲", "character", []),
            ("subject_fern_chibi", "Q版菲伦", "character", []),
            ("subject_stark_chibi", "Q版修塔尔克", "character", []),
        ],
        "references": [
            ("@图片1", "image_001", "测试样例9/魔法卧室.png", "scene", "scene_warm_magic_study", "scene_reference", "model_feedback_1"),
        ],
        "actions": [
            ("concept_review", "approve_concept", "同意。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "request_model_changes", "不同意。角色模型失真，新增 Q版修塔尔克；只上传一张魔法书房场景参考图。", ["image_001"], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "用户概念图反馈：同意。这版角色和场景关系清楚。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "用户模型反馈：同意。选择组合所有主体。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 3, "subject_glbs": 3},
    },
    {
        "number": 10,
        "case_id": "case_10_helltaker_cafe",
        "title": "Helltaker Q版恶魔咖啡办公室",
        "category": "anime_game_ip_demon_cafe_office",
        "expected_scene": "恶魔主题复古咖啡馆兼办公室，咖啡杯、甜甜圈、文件、黑胶唱片",
        "subjects": [
            ("subject_lucifer_chibi", "Q版 Lucifer", "character", ["image_001"]),
            ("subject_justice_chibi", "Q版 Justice", "character", []),
            ("subject_cerberus_chibi", "Q版 Cerberus", "character", []),
        ],
        "references": [
            ("@图片L", "image_001", "测试样例10/Q版路西法.png", "subject", "subject_lucifer_chibi", "subject_reference", "concept_feedback_1"),
            ("@图片1", "image_002", "测试样例10/恶魔咖啡馆.png", "scene", "scene_demon_cafe_office", "scene_reference", "concept_feedback_1"),
        ],
        "actions": [
            ("concept_review", "request_concept_changes", "不同意。概念图不够干净；新增 Q版 Cerberus。用户确认第一轮同时上传 Q版路西法主体参考和恶魔咖啡馆场景参考。", ["image_001", "image_002"], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "用户概念图反馈：同意。这版角色站位、场景氛围和道具布局可以。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "用户模型反馈：同意。选择组合所有主体。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 3, "subject_glbs": 3},
        "parse_notes": ["用户确认 Q版路西法.png 也作为第一轮 Lucifer 主体参考图加入流程；原始样例文本只显式写了场景 @图片1。"],
    },
    {
        "number": 11,
        "case_id": "case_11_stellar_blade_eve_tachy",
        "title": "剑星 Eve 与 Tachy 末世登陆战场",
        "category": "aaa_game_full_body_ip_battlefield",
        "expected_scene": "破碎海岸、坠落舱残骸、湿润沙地、远处毁坏建筑",
        "subjects": [
            ("subject_eve_full_body", "Eve", "character", ["image_001"]),
            ("subject_tachy_full_body", "Tachy", "character", ["image_002"]),
        ],
        "references": [
            ("@图片1", "image_001", "测试样例11/eve.png", "subject", "subject_eve_full_body", "subject_reference", "concept_feedback_1"),
            ("@图片2", "image_002", "测试样例11/tachy.png", "subject", "subject_tachy_full_body", "subject_reference", "concept_feedback_1"),
            ("@图片3", "image_003", "测试样例11/场景图.png", "scene", "scene_post_apocalyptic_landing_battlefield", "scene_reference", "concept_feedback_1"),
        ],
        "actions": [
            ("concept_review", "request_concept_changes", "不同意。不够像《剑星》3A 游戏截图；上传 Eve、Tachy 主体参考和末世登陆战场场景参考。", ["image_001", "image_002", "image_003"], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "用户概念图反馈：同意。这版角色质感、全身结构和《剑星》画面风格都对了。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "用户模型反馈：同意。选择组合 Eve + Tachy + 场景。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 2, "subject_glbs": 2},
    },
    {
        "number": 12,
        "case_id": "case_12_stellar_blade_raven_adam_xion",
        "title": "剑星 Raven 与 Adam 的 Xion 被袭击城市中枢",
        "category": "aaa_game_full_body_ip_city_center",
        "expected_scene": "Xion 被袭击后的城市中枢/记忆广场附近，破损金属、红色警报、停电广告屏",
        "subjects": [
            ("subject_raven_full_body", "Raven", "character", ["image_001"]),
            ("subject_adam_full_body", "Adam", "character", ["image_002"]),
        ],
        "references": [
            ("@图片1", "image_001", "测试样例12/raven.png", "subject", "subject_raven_full_body", "subject_reference", "concept_feedback_1"),
            ("@图片2", "image_002", "测试样例12/adam.png", "subject", "subject_adam_full_body", "subject_reference", "concept_feedback_1"),
            ("@图片3", "image_003", "测试样例12/场景.png", "scene", "scene_xion_attacked_city_center", "scene_reference", "concept_feedback_1"),
        ],
        "actions": [
            ("concept_review", "request_concept_changes", "不同意。角色不够像；上传 Raven、Adam 主体参考和 Xion 城市中枢场景参考。", ["image_001", "image_002", "image_003"], "CONCEPT_GENERATION"),
            ("concept_review", "approve_concept", "用户概念图反馈：同意。这版角色更贴近《剑星》，场景也更像 Xion。", [], "SUBJECT_ASSET_GENERATION"),
            ("model_review", "approve_model_assets", "用户模型反馈：同意。选择组合 Raven + Adam + Xion 场景。", [], "SCENE_ASSET_GENERATION"),
        ],
        "minimum": {"concept_rounds": 2, "subject_concept_images": 2, "subject_glbs": 2},
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    markdown_path = source_root / "测试样例.md"
    if not markdown_path.is_file():
        raise FileNotFoundError(markdown_path)
    sections = split_sample_markdown(markdown_path.read_text(encoding="utf-8"))
    output_root.mkdir(parents=True, exist_ok=True)
    summary = []
    for case_def in CASE_DEFS:
        case_dir = output_root / case_def["case_id"]
        if case_dir.exists() and args.overwrite:
            shutil.rmtree(case_dir)
        case_dir.mkdir(parents=True, exist_ok=True)
        section = sections[case_def["number"]]
        (case_dir / "user_script.md").write_text(section.strip() + "\n", encoding="utf-8")
        ref_dir = case_dir / "reference_images"
        ref_dir.mkdir(exist_ok=True)
        manifest = build_manifest(case_def, section, source_root, ref_dir)
        (case_dir / "case_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        parse_notes = manifest.get("parse_notes") or []
        if parse_notes:
            (case_dir / "case_parse_notes.md").write_text("\n".join(f"- {note}" for note in parse_notes) + "\n", encoding="utf-8")
        summary.append({"case_id": case_def["case_id"], "reference_count": len(manifest["reference_images"])})
    (output_root / "round04_fixture_summary.json").write_text(
        json.dumps({"case_count": len(summary), "cases": summary}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "output_root": str(output_root), "case_count": len(summary)}, ensure_ascii=False))
    return 0


def split_sample_markdown(text: str) -> dict[int, str]:
    matches = list(re.finditer(r"(?m)^# 测试样例(\d+)\s*$", text))
    sections: dict[int, str] = {}
    for index, match in enumerate(matches):
        number = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[number] = text[match.start() : end].strip()
    missing = sorted(set(range(1, 13)) - set(sections))
    if missing:
        raise ValueError(f"missing sample sections: {missing}")
    return sections


def build_manifest(case_def: dict[str, Any], section: str, source_root: Path, ref_dir: Path) -> dict[str, Any]:
    references = []
    for slot, image_id, rel_source, target_type, target_id, usage, upload_stage in case_def["references"]:
        source = source_root / rel_source
        if not source.is_file():
            raise FileNotFoundError(source)
        suffix = source.suffix or ".bin"
        target = ref_dir / f"{image_id}{suffix}"
        shutil.copy2(source, target)
        references.append(
            {
                "slot": slot,
                "image_id": image_id,
                "path": f"reference_images/{target.name}",
                "declared_target_type": target_type,
                "declared_target_id": target_id,
                "usage": usage,
                "required_for_generation": True,
                "upload_stage": upload_stage,
                "source_text_span": slot,
            }
        )
    minimum = {
        "concept_rounds": 1,
        "subject_concept_images": 1,
        "scene_concept_images": 1,
        "target_render_images": 1,
        "subject_glbs": 1,
        "scene_assets": 1,
        "preview_renders": 1,
        "viewer_glbs": 1,
    }
    minimum.update(case_def.get("minimum") or {})
    return {
        "case_id": case_def["case_id"],
        "title": case_def["title"],
        "category": case_def["category"],
        "initial_user_request": extract_initial_request(section),
        "expected_subjects": [
            {
                "subject_id": subject_id,
                "display_name": display_name,
                "category": category,
                "needs_3d_asset": True,
                "reference_image_ids": reference_ids,
            }
            for subject_id, display_name, category, reference_ids in case_def["subjects"]
        ],
        "expected_scene": case_def["expected_scene"],
        "reference_images": references,
        "scripted_user_actions": [
            {
                "gate": gate,
                "action": action,
                "text": text,
                "reference_image_ids": reference_ids,
                "expected_next_phase": expected_next_phase,
            }
            for gate, action, text, reference_ids, expected_next_phase in case_def["actions"]
        ],
        "expected_minimum_counts": minimum,
        "raw_sample_source": str(source_root / "测试样例.md"),
        "parse_notes": case_def.get("parse_notes") or [],
    }


def extract_initial_request(section: str) -> str:
    marker = "**初始用户请求：**"
    start = section.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    end_candidates = [
        pos
        for token in ["**用户概念图反馈：**", "**用户模型反馈：**"]
        for pos in [section.find(token, start)]
        if pos >= 0
    ]
    end = min(end_candidates) if end_candidates else len(section)
    return section[start:end].strip()


if __name__ == "__main__":
    raise SystemExit(main())
