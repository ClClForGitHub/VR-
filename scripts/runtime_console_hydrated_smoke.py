#!/usr/bin/env python3
"""Hydrated browser-level smoke for the runtime console surface.

This is a lightweight acceptance probe for environments without Playwright or
WebDriver. It fetches the live runtime-console API, applies the public run
selection policy, verifies the selected run's delivery/viewer surfaces, writes a
static hydrated report, and optionally renders screenshots with headless
Firefox.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_CONSOLE_URL = "http://127.0.0.1:8093"
DEFAULT_OUT_DIR = "/tmp/image23d_hydrated_smoke"
OLD_PUBLIC_STRINGS = ["Open GLB", "Open Blend", "Build Plan", "Step Dry", "STATUS"]
PUBLIC_SHELL_STRINGS = ["下一步", "素材库", "场景内容", "验收与交付", "阶段进度"]


def fetch_text(url: str, *, timeout: float = 20) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str, *, timeout: float = 20) -> Any:
    return json.loads(fetch_text(url, timeout=timeout))


def norm_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def has_any(value: str, phrases: list[str]) -> bool:
    normalized = norm_name(value)
    return any(phrase in normalized for phrase in phrases)


def is_user_console_run_name(name: str) -> bool:
    return bool(re.search(r"^runtime_console_\d{8}", name, re.I) or re.search(r"console_user|runtime_console_user|用户|创作", name, re.I))


def is_public_showcase_run_name(name: str) -> bool:
    return bool(re.search(r"scene_spec_assembly_non_dryrun|p0_real_demo|real_demo|codex_self_robot_concept", name, re.I))


def is_dry_run_name(name: str) -> bool:
    if re.search(r"non[_-]?dryrun", name, re.I):
        return False
    return has_any(name, ["smoke", "audit", "dryrun", "dry run", "preflight", "http audit", "step smoke", "plan smoke"])


def is_internal_run_name(name: str) -> bool:
    if is_user_console_run_name(name) or is_public_showcase_run_name(name):
        return False
    return has_any(
        name,
        [
            "smoke",
            "audit",
            "dryrun",
            "dry run",
            "fixture",
            "handoff",
            "worker",
            "loop",
            "step smoke",
            "plan smoke",
            "http audit",
            "apply",
            "qwen",
            "deepseek",
            "llm node",
            "socket",
            "scratch",
            "router",
            "live router",
        ],
    ) or bool(re.search(r"^202\d{5}_runtime_", name, re.I))


def public_run_visible(run: dict[str, Any]) -> bool:
    if not run or run.get("is_stage"):
        return False
    name = str(run.get("display_name") or run.get("run_id") or "")
    if is_dry_run_name(name):
        return False
    if is_public_showcase_run_name(name):
        return bool(run.get("has_state") or run.get("has_summary") or run.get("has_frontend_status") or run.get("has_viewer_scene") or run.get("has_scene_state"))
    if is_user_console_run_name(name):
        return bool(run.get("has_state") or run.get("has_summary") or run.get("has_frontend_status"))
    if re.search(r"p0_real|real_demo|codex_self_robot", name, re.I):
        return bool(run.get("has_state") or run.get("has_summary") or run.get("has_frontend_status"))
    if has_inspectable_preview(run):
        return True
    if is_internal_run_name(name):
        return False
    return bool(run.get("has_viewer_scene") or run.get("has_scene_state"))


def has_inspectable_preview(run: dict[str, Any]) -> bool:
    return bool(run.get("has_viewer_scene") or run.get("has_scene_state"))


def run_selection_score(run: dict[str, Any]) -> float:
    name = str(run.get("display_name") or run.get("run_id") or "")
    inspectable_preview = has_inspectable_preview(run)
    frontend_phase = str(run.get("frontend_phase") or "")
    score = float(run.get("modified_at") or 0) / 10000000
    if run.get("has_viewer_scene"):
        score += 180
    if run.get("has_scene_state"):
        score += 90
    if run.get("has_frontend_status"):
        score += 32
    if run.get("has_state"):
        score += 24
    if run.get("has_summary"):
        score += 12
    if run.get("has_delivery_handoff"):
        score += 28
    if is_public_showcase_run_name(name):
        score += 45
    if re.search(r"scene_spec_assembly_non_dryrun", name, re.I):
        score += 25
    if is_user_console_run_name(name):
        score += 70
    if frontend_phase == "BLENDER_PREVIEW":
        score += 260
    if frontend_phase == "DELIVERY":
        score += 80
    if inspectable_preview and re.search(r"edit|router|live", name, re.I):
        score += 120
    if is_internal_run_name(name) and not inspectable_preview:
        score -= 160
    if re.search(r"live|real|用户|真实", name, re.I):
        score += 25
    if not run.get("has_viewer_scene") and run.get("has_frontend_status"):
        score += 8
    if is_dry_run_name(name):
        score -= 100
    if re.search(r"deepseek|qwen|socket|scratch|refresh|router", name, re.I) and not inspectable_preview:
        score -= 80
    if run.get("is_stage"):
        score -= 45
    return score


def viewer_embed_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["embed"] = ["1"]
    query["public"] = ["1"]
    query["lang"] = ["zh-CN"]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))


def manifest_file(bundle: dict[str, Any], label: str) -> dict[str, Any] | None:
    for record in bundle.get("file_manifest", {}).get("files", []) or []:
        if record.get("label") == label and record.get("exists") and record.get("url"):
            return record
    return None


def absolute_url(base_url: str, url: str) -> str:
    return urllib.parse.urljoin(f"{base_url.rstrip('/')}/", url)


def bool_check(checks: dict[str, bool], name: str, value: bool) -> None:
    checks[name] = bool(value)


def build_report_html(summary: dict[str, Any]) -> str:
    checks = summary["checks"]
    rows = "\n".join(
        f"<tr><td>{html.escape(key)}</td><td class=\"{'ok' if value else 'bad'}\">{'通过' if value else '失败'}</td></tr>"
        for key, value in checks.items()
    )
    file_rows = "\n".join(
        f"<li><strong>{html.escape(label)}</strong><a href=\"{html.escape(url)}\">打开</a></li>"
        for label, url in summary["file_links"].items()
    )
    iframe = ""
    if summary.get("viewer_embed_url"):
        iframe = f"<iframe title=\"3D viewer\" src=\"{html.escape(summary['viewer_embed_url'])}\"></iframe>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>image23D Hydrated Smoke</title>
  <style>
    body {{ margin: 0; font-family: Inter, system-ui, "Microsoft YaHei", sans-serif; background: #f4f6f8; color: #111827; }}
    main {{ display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 16px; min-height: 100vh; padding: 16px; box-sizing: border-box; }}
    section {{ border: 1px solid #d7dee8; border-radius: 8px; background: white; padding: 16px; }}
    h1 {{ margin: 0 0 8px; font-size: 22px; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; }}
    p {{ color: #475467; }}
    iframe {{ width: 100%; height: 640px; border: 0; border-radius: 8px; background: #161d27; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td {{ padding: 8px 0; border-bottom: 1px solid #edf1f5; font-size: 14px; }}
    .ok {{ color: #16803c; font-weight: 800; }}
    .bad {{ color: #b42318; font-weight: 800; }}
    ul {{ display: grid; gap: 8px; padding: 0; list-style: none; }}
    li {{ display: flex; justify-content: space-between; gap: 12px; border: 1px solid #e5eaf0; border-radius: 8px; padding: 10px; }}
    a {{ color: #0f766e; font-weight: 800; text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>{html.escape(summary['selected_run_name'])}</h1>
      <p>阶段：{html.escape(summary['phase'])} / 交付：{html.escape(summary['delivery_status'])}</p>
      {iframe}
    </section>
    <section>
      <h2>浏览器验收检查</h2>
      <table>{rows}</table>
      <h2 style="margin-top: 20px;">文件链路</h2>
      <ul>{file_rows}</ul>
    </section>
  </main>
</body>
</html>"""


def render_screenshot(firefox: str, target_url: str, output_path: Path, *, width: int = 1600, height: int = 1000) -> bool:
    command = [
        firefox,
        "--headless",
        "--screenshot",
        str(output_path),
        "--window-size",
        f"{width},{height}",
        target_url,
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45)
    return result.returncode == 0 and output_path.exists()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run hydrated browser-level smoke checks for the image23D runtime console.")
    parser.add_argument("--console-url", default=DEFAULT_CONSOLE_URL)
    parser.add_argument("--output-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--expected-run-id", default="20260629_scene_spec_assembly_non_dryrun")
    parser.add_argument("--expected-ui-version", default="20260630-ui27")
    parser.add_argument("--skip-firefox", action="store_true")
    args = parser.parse_args()

    console_url = args.console_url.rstrip("/")
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: dict[str, bool] = {}

    index_html = fetch_text(f"{console_url}/?v=hydrated-smoke-{int(time.time())}")
    app_js = fetch_text(f"{console_url}/app.js?v=hydrated-smoke-{int(time.time())}")
    runs = fetch_json(f"{console_url}/api/runs")
    visible_runs = sorted([run for run in runs if public_run_visible(run)], key=run_selection_score, reverse=True)
    selected_run = visible_runs[0] if visible_runs else None
    selected_key = selected_run.get("run_key") if selected_run else ""
    bundle = fetch_json(f"{console_url}/api/runs/{urllib.parse.quote(selected_key)}") if selected_key else {}

    handoff = bundle.get("delivery_handoff") or {}
    frontend_status = bundle.get("frontend_status") or {}
    web_surface = bundle.get("web_surface") or {}
    viewer_url = web_surface.get("viewer_scene_url") or handoff.get("viewer_url") or ""
    embed_url = viewer_embed_url(viewer_url) if viewer_url else ""
    viewer_html = fetch_text(embed_url) if embed_url else ""
    phase = frontend_status.get("phase") or bundle.get("state", {}).get("phase") or ""
    is_delivery = phase == "DELIVERY"
    is_preview = phase == "BLENDER_PREVIEW"
    file_links = {
        label: absolute_url(console_url, record["url"])
        for label in ["state", "scene_state", "delivery_handoff", "delivery_package"]
        if (record := manifest_file(bundle, label))
    }

    selected_name = str(selected_run.get("display_name") or selected_run.get("run_id") if selected_run else "")
    bool_check(checks, "served_expected_assets", args.expected_ui_version in index_html and args.expected_ui_version in app_js)
    bool_check(checks, "public_shell_chinese", all(token in index_html for token in PUBLIC_SHELL_STRINGS))
    bool_check(checks, "preview_gate_copy_present", all(token in app_js for token in ["确认当前预览并打包", "3D 预览已就绪", "Blender 工程已就绪"]))
    bool_check(checks, "preview_image_fallback_present", all(token in app_js for token in ["preview-fallback", "keepPreview"]))
    bool_check(checks, "object_feedback_draft_present", all(token in app_js for token in ["写草稿", "objectFeedbackDraft", "data-object-edit-draft"]))
    bool_check(checks, "object_feedback_submit_present", all(token in app_js for token in ["提交修改", "data-object-edit-submit", "source: 'scene_object_quick_action'"]))
    bool_check(checks, "object_feedback_refresh_present", all(token in app_js for token in ["生成预览", "data-object-edit-refresh", "source: 'scene_object_refresh_action'", "blender-lab-socket"]))
    bool_check(checks, "run_refresh_poll_present", all(token in app_js for token in ["startRunRefreshPoll", "stopRunRefreshPoll", "正在生成新版预览", "正在打包交付"]))
    bool_check(checks, "ui25_creator_skin_present", "ui25_creator.css" in index_html and "请验收当前 3D 场景" in app_js)
    bool_check(checks, "viewer_object_selection_bridge_present", all(token in viewer_html for token in ["sceneObjectsJson", "image23d.viewer.objectSelected", "objectPicker"]) and "handleViewerObjectSelectedMessage" in app_js)
    bool_check(checks, "run_event_stream_present", all(token in app_js for token in ["EventSource", "/events", "startRunEventStream", "refreshFromRunEventStream"]))
    bool_check(checks, "old_public_strings_absent", not any(token in index_html for token in OLD_PUBLIC_STRINGS))
    bool_check(checks, "has_public_runs", bool(visible_runs))
    bool_check(checks, "expected_run_selected", selected_run and selected_run.get("run_id") == args.expected_run_id)
    bool_check(checks, "reviewable_phase", is_delivery or is_preview)
    if is_delivery:
        bool_check(checks, "delivery_ready", bool(handoff.get("ready")))
        bool_check(checks, "delivery_verified", bool(handoff.get("verified")))
    else:
        bool_check(checks, "preview_gate", frontend_status.get("current_stage") == "blender_preview_approval")
    required_files = ["state", "scene_state", "delivery_handoff"] + (["delivery_package"] if is_delivery else [])
    for label in required_files:
        bool_check(checks, f"file_link_{label}", label in file_links)
    bool_check(checks, "viewer_embed_public", 'body class="embed public"' in viewer_html)
    bool_check(checks, "viewer_chinese_controls", all(token in viewer_html for token in ["暂停旋转", "播放动画", "重置视角"]))
    bool_check(checks, "viewer_debug_text_absent", ">Download<" not in viewer_html and ">List<" not in viewer_html and '<div class="path">' not in viewer_html)
    bool_check(checks, "viewer_bare_home_absent", "/home/team/zouzhiyuan" not in viewer_html)

    summary = {
        "ok": all(checks.values()),
        "console_url": console_url,
        "selected_run_key": selected_key,
        "selected_run_id": selected_run.get("run_id") if selected_run else None,
        "selected_run_name": selected_name,
        "visible_run_count": len(visible_runs),
        "phase": phase,
        "delivery_status": "ready_verified" if handoff.get("ready") and handoff.get("verified") else "not_ready",
        "viewer_embed_url": embed_url,
        "file_links": file_links,
        "checks": checks,
        "artifacts": {},
    }
    report_html = build_report_html(summary)
    report_path = output_dir / "hydrated_report.html"
    summary_path = output_dir / "summary.json"
    report_path.write_text(report_html, encoding="utf-8")
    firefox = shutil.which("firefox")
    if firefox and not args.skip_firefox:
        report_shot = output_dir / "hydrated_report.png"
        viewer_shot = output_dir / "viewer_embed.png"
        if render_screenshot(firefox, report_path.as_uri(), report_shot):
            summary["artifacts"]["hydrated_report_screenshot"] = str(report_shot)
        if embed_url and render_screenshot(firefox, embed_url, viewer_shot, width=1200, height=760):
            summary["artifacts"]["viewer_embed_screenshot"] = str(viewer_shot)
    summary["artifacts"]["hydrated_report_html"] = str(report_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
