#!/usr/bin/env python3
import argparse
import html
import json
import mimetypes
import os
import posixpath
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


MODEL_EXTENSIONS = {".glb", ".gltf"}
TRUTHY_QUERY_VALUES = {"1", "true", "yes", "on"}
DEFAULT_CAMERA_ORBIT = "35deg 72deg auto"
DEFAULT_CAMERA_TARGET = "auto auto auto"


def human_size(num):
    units = ["B", "KB", "MB", "GB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{num} B"


def resolve_under(path_text, allowed_roots):
    if not path_text:
        raise ValueError("missing path")
    raw = unquote(path_text)
    path = Path(raw)
    if not path.is_absolute():
        path = allowed_roots[0] / path
    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise ValueError(f"path is outside allowed roots: {resolved}")


def query_flag(query, name):
    values = query.get(name, [])
    if not values:
        return False
    return any(str(value).strip().lower() in TRUTHY_QUERY_VALUES for value in values)


def _float_triplet(value):
    if not value:
        return None
    parts = [part.strip() for part in str(value).split(",")]
    if len(parts) != 3:
        return None
    try:
        return tuple(float(part) for part in parts)
    except ValueError:
        return None


def camera_target_from_query(query):
    values = query.get("target", [])
    if not values:
        return DEFAULT_CAMERA_TARGET
    triplet = _float_triplet(values[0])
    if triplet is None:
        return DEFAULT_CAMERA_TARGET
    return " ".join(f"{value:.4f}m" for value in triplet)


def camera_orbit_from_query(query):
    values = query.get("orbit", [])
    if values:
        triplet = _float_triplet(values[0])
        if triplet is not None:
            azimuth, elevation, radius = triplet
            radius = max(0.05, radius)
            return f"{azimuth:.2f}deg {elevation:.2f}deg {radius:.4f}m"
    radius_values = query.get("radius", [])
    if radius_values:
        try:
            radius = max(0.05, float(radius_values[0]))
        except ValueError:
            radius = None
        if radius is not None:
            return f"35deg 72deg {radius:.4f}m"
    return DEFAULT_CAMERA_ORBIT


def _bounds_triplet(values):
    if not isinstance(values, list) or len(values) != 3:
        return None
    try:
        return [round(float(value), 6) for value in values]
    except (TypeError, ValueError):
        return None


def public_scene_objects_for_model(model_path):
    """Return a small path-free object list from adjacent scene_state.json."""
    state_path = model_path.with_name("scene_state.json")
    if not state_path.exists():
        return []
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    objects = []
    for item in payload.get("objects", []):
        if not isinstance(item, dict):
            continue
        object_type = str(item.get("object_type") or "").upper()
        if object_type in {"CAMERA", "LIGHT", "EMPTY"}:
            continue
        if item.get("selectable") is False and object_type != "MESH":
            continue
        bounds = item.get("bounds") or {}
        min_values = _bounds_triplet(bounds.get("min"))
        max_values = _bounds_triplet(bounds.get("max"))
        if not min_values or not max_values or min_values == max_values:
            continue
        objects.append(
            {
                "viewer_object_id": str(item.get("viewer_object_id") or ""),
                "blender_object_id": str(item.get("blender_object_id") or ""),
                "display_name": str(item.get("display_name") or item.get("viewer_object_id") or item.get("blender_object_id") or "object"),
                "object_type": object_type or "OBJECT",
                "subject_id": str(item.get("subject_id") or ""),
                "asset_id": str(item.get("asset_id") or ""),
                "bounds": {"min": min_values, "max": max_values},
            }
        )
    return objects


def script_json(value):
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def recent_models(allowed_roots, limit):
    seen = set()
    files = []
    for root in allowed_roots:
        output_root = root / "outputs"
        search_root = output_root if output_root.exists() else root
        for ext in MODEL_EXTENSIONS:
            for path in search_root.rglob(f"*{ext}"):
                try:
                    resolved = path.resolve()
                except OSError:
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                try:
                    stat = resolved.stat()
                except OSError:
                    continue
                files.append((stat.st_mtime, stat.st_size, resolved))
    files.sort(reverse=True)
    return files[:limit]


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "GLBViewer/0.1"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    @property
    def allowed_roots(self):
        return self.server.allowed_roots

    @property
    def vendor_js(self):
        return self.server.vendor_js

    def send_bytes(self, body, content_type, status=HTTPStatus.OK, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_text(self, text, content_type="text/html; charset=utf-8", status=HTTPStatus.OK):
        self.send_bytes(text.encode("utf-8"), content_type, status=status)

    def send_error_text(self, status, message):
        self.send_text(
            f"<!doctype html><title>{status}</title><pre>{html.escape(message)}</pre>",
            status=status,
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        route = posixpath.normpath(parsed.path)
        if route == "/":
            return self.handle_index()
        if route == "/viewer":
            return self.handle_viewer(parse_qs(parsed.query))
        if route == "/asset":
            return self.handle_asset(parse_qs(parsed.query))
        if route == "/api/list":
            return self.handle_api_list(parse_qs(parsed.query))
        if route == "/vendor/model-viewer.min.js":
            return self.handle_vendor()
        self.send_error_text(HTTPStatus.NOT_FOUND, f"not found: {route}")

    def do_HEAD(self):
        self.do_GET()

    def handle_vendor(self):
        if not self.vendor_js.exists():
            self.send_error_text(
                HTTPStatus.NOT_FOUND,
                f"model-viewer bundle not installed: {self.vendor_js}",
            )
            return
        self.send_bytes(self.vendor_js.read_bytes(), "text/javascript; charset=utf-8")

    def handle_index(self):
        rows = []
        for _, size, path in recent_models(self.allowed_roots, self.server.list_limit):
            label = str(path)
            viewer = f"/viewer?path={quote(label)}"
            asset = f"/asset?path={quote(label)}"
            rows.append(
                "<tr>"
                f"<td><a href=\"{viewer}\">{html.escape(path.name)}</a></td>"
                f"<td>{html.escape(human_size(size))}</td>"
                f"<td class=\"path\">{html.escape(label)}</td>"
                f"<td><a href=\"{asset}\">download</a></td>"
                "</tr>"
            )
        body = "\n".join(rows) or "<tr><td colspan=\"4\">No GLB/GLTF files found under outputs/.</td></tr>"
        self.send_text(
            f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>image23D GLB Viewer</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, Arial, sans-serif; }}
    body {{ margin: 0; background: #f4f5f7; color: #171717; }}
    header {{ padding: 18px 24px; background: #20242b; color: white; }}
    h1 {{ margin: 0; font-size: 20px; font-weight: 680; }}
    main {{ padding: 20px 24px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dde1e7; }}
    th, td {{ padding: 11px 12px; border-bottom: 1px solid #e8ebef; text-align: left; font-size: 14px; }}
    th {{ background: #f9fafb; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #5d6675; }}
    a {{ color: #2458d6; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .path {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #535b68; font-size: 12px; }}
  </style>
</head>
<body>
  <header><h1>image23D GLB Viewer</h1></header>
  <main>
    <table>
      <thead><tr><th>Model</th><th>Size</th><th>Path</th><th>File</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
  </main>
</body>
</html>"""
        )

    def handle_api_list(self, query):
        limit = int(query.get("limit", [self.server.list_limit])[0])
        items = []
        for mtime, size, path in recent_models(self.allowed_roots, limit):
            text_path = str(path)
            items.append(
                {
                    "name": path.name,
                    "path": text_path,
                    "size": size,
                    "mtime": mtime,
                    "viewer_url": f"/viewer?path={quote(text_path)}",
                    "asset_url": f"/asset?path={quote(text_path)}",
                }
            )
        self.send_bytes(json.dumps(items, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")

    def handle_asset(self, query):
        path_text = query.get("path", query.get("file", [""]))[0]
        try:
            path = resolve_under(path_text, self.allowed_roots)
        except ValueError as exc:
            self.send_error_text(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path.suffix.lower() not in MODEL_EXTENSIONS:
            self.send_error_text(HTTPStatus.BAD_REQUEST, f"unsupported model type: {path.suffix}")
            return
        if not path.exists():
            self.send_error_text(HTTPStatus.NOT_FOUND, f"missing file: {path}")
            return
        mime = "model/gltf-binary" if path.suffix.lower() == ".glb" else "model/gltf+json"
        self.send_bytes(
            path.read_bytes(),
            mime,
            extra_headers={"Content-Disposition": f"inline; filename={path.name!r}"},
        )

    def handle_viewer(self, query):
        path_text = query.get("path", query.get("file", [""]))[0]
        try:
            path = resolve_under(path_text, self.allowed_roots)
        except ValueError as exc:
            self.send_error_text(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if not path.exists():
            self.send_error_text(HTTPStatus.NOT_FOUND, f"missing file: {path}")
            return
        if path.suffix.lower() not in MODEL_EXTENSIONS:
            self.send_error_text(HTTPStatus.BAD_REQUEST, f"unsupported model type: {path.suffix}")
            return
        asset = f"/asset?path={quote(str(path), safe='')}"
        download = asset
        embed_mode = query_flag(query, "embed")
        public_mode = embed_mode or query_flag(query, "public")
        title = html.escape("3D 场景预览" if public_mode else path.name)
        full_path = html.escape("" if public_mode else str(path))
        body_class = "embed public" if embed_mode else "public" if public_mode else "debug"
        path_row = "" if public_mode else f'<div class="path">{full_path}</div>'
        camera_target = camera_target_from_query(query)
        camera_orbit = camera_orbit_from_query(query)
        focus_label = html.escape(query.get("focus", [""])[0])
        focus_badge = f'<div class="focus-badge">聚焦：{focus_label}</div>' if public_mode and focus_label else ""
        scene_objects = public_scene_objects_for_model(path) if public_mode else []
        object_picker = '<div id="objectPicker" class="object-picker" hidden></div>' if scene_objects else ""
        selection_badge = '<div id="selectionBadge" class="selection-badge" hidden></div>' if scene_objects else ""
        extra_links = "" if embed_mode else (
            f'<a class="button" href="{download}">{"下载模型" if public_mode else "Download"}</a>'
            f'<a class="button" href="/">{"返回列表" if public_mode else "List"}</a>'
        )
        labels = {
            "rotate_on": "暂停旋转" if public_mode else "Pause",
            "rotate_off": "开启旋转" if public_mode else "Rotate",
            "anim_play": "播放动画" if public_mode else "Play Anim",
            "anim_pause": "暂停动画" if public_mode else "Pause Anim",
            "anim_none": "无动画" if public_mode else "No Anim",
            "reset": "重置视角" if public_mode else "Reset",
        }
        self.send_text(
            f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script type="module" src="/vendor/model-viewer.min.js"></script>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, Arial, sans-serif; }}
    html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: #161d27; }}
    model-viewer {{ width: 100vw; height: 100vh; background: radial-gradient(circle at 50% 40%, #5f6877 0, #27313e 48%, #141a22 100%); }}
    .bar {{
      position: fixed; left: 12px; right: 12px; top: 12px; z-index: 10;
      display: flex; align-items: center; gap: 10px; min-height: 36px;
      background: rgba(20, 22, 26, .78); color: #f4f6fb;
      border: 1px solid rgba(255,255,255,.12); backdrop-filter: blur(10px);
      padding: 8px 10px; box-sizing: border-box;
    }}
    .title {{ min-width: 0; flex: 1; }}
    .name {{ font-size: 14px; font-weight: 680; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .path {{ margin-top: 2px; color: #b8c0cd; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .focus-badge {{
      position: fixed; left: 16px; bottom: 16px; z-index: 9;
      max-width: min(380px, calc(100vw - 32px)); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      border: 1px solid rgba(20, 184, 166, .38); border-radius: 8px;
      background: rgba(15, 23, 42, .74); color: #dffcf7;
      padding: 8px 10px; font-size: 13px; font-weight: 760;
      backdrop-filter: blur(10px);
    }}
    .selection-badge {{
      position: fixed; left: 14px; bottom: 16px; z-index: 9;
      max-width: min(420px, calc(100vw - 28px)); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      border: 1px solid rgba(20, 184, 166, .52); border-radius: 8px;
      background: rgba(11, 92, 87, .82); color: #ecfffb;
      padding: 8px 10px; font-size: 13px; font-weight: 780;
      backdrop-filter: blur(10px);
    }}
    .object-picker {{
      position: fixed; left: 14px; right: 14px; bottom: 58px; z-index: 8;
      display: flex; flex-wrap: wrap; gap: 7px; pointer-events: none;
    }}
    .object-picker button {{
      pointer-events: auto; width: auto; min-width: 0; max-width: 180px;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      border-color: rgba(20, 184, 166, .38);
      background: rgba(15, 23, 42, .68); color: #e7fbf7;
      backdrop-filter: blur(10px);
    }}
    .object-picker button.selected {{
      border-color: rgba(20, 184, 166, .85);
      background: rgba(15, 118, 110, .88);
      color: #ffffff;
    }}
    button, a.button {{
      min-width: 72px; height: 30px; border: 1px solid rgba(255,255,255,.18); border-radius: 8px;
      background: rgba(255,255,255,.08); color: white; padding: 0 10px; font-size: 13px;
      text-decoration: none; cursor: pointer;
    }}
    button:hover, a.button:hover {{ background: rgba(255,255,255,.15); }}
    body.public .bar {{ left: 14px; right: 14px; top: 14px; border-radius: 8px; }}
    body.public .name {{ font-weight: 760; }}
    body.embed .bar {{
      left: auto; right: 14px; width: auto; min-height: 36px; padding: 7px;
      border-radius: 8px; background: rgba(17, 24, 39, .68);
    }}
    body.embed .title {{ display: none; }}
    body.embed button {{ min-width: 76px; }}
    body.embed a.button {{ display: none; }}
    body.public model-viewer {{ background: radial-gradient(circle at 50% 38%, #5b6472 0, #252f3c 48%, #111827 100%); }}
  </style>
</head>
<body class="{body_class}">
  <script id="sceneObjectsJson" type="application/json">{script_json(scene_objects)}</script>
  <div class="bar">
    <div class="title">
      <div class="name">{title}</div>
      {path_row}
    </div>
    <button id="toggleRotate">{labels["rotate_on"]}</button>
    <button id="toggleAnim">{labels["anim_play"]}</button>
    <button id="resetCamera">{labels["reset"]}</button>
    {extra_links}
  </div>
  {focus_badge}
  {selection_badge}
  {object_picker}
  <model-viewer id="viewer"
    src="{asset}"
    camera-controls
    autoplay
    animation-crossfade-duration="300"
    auto-rotate
    rotation-per-second="12deg"
    shadow-intensity="0.85"
    exposure="1"
    environment-image="neutral"
    camera-orbit="{html.escape(camera_orbit)}"
    camera-target="{html.escape(camera_target)}"
    interaction-prompt="auto">
  </model-viewer>
  <script>
    const viewer = document.getElementById('viewer');
    const animButton = document.getElementById('toggleAnim');
    const objectPicker = document.getElementById('objectPicker');
    const selectionBadge = document.getElementById('selectionBadge');
    const sceneObjects = JSON.parse(document.getElementById('sceneObjectsJson')?.textContent || '[]');
    let selectedObjectKey = '';

    const objectKey = (object) => object?.viewer_object_id || object?.blender_object_id || object?.display_name || '';
    const displayObjectName = (object) => {{
      const raw = String(object?.display_name || object?.viewer_object_id || object?.blender_object_id || '场景内容');
      if (/hunyuan3d/i.test(raw)) return '主体模型';
      const geometry = raw.match(/^geometry[_-]?(\\d+)$/i);
      if (geometry) return `场景网格 ${{Number(geometry[1]) + 1}}`;
      return raw.replace(/[_-]+/g, ' ') || '场景内容';
    }};
    const centerOf = (object) => {{
      const min = object?.bounds?.min || [];
      const max = object?.bounds?.max || [];
      if (min.length !== 3 || max.length !== 3) return null;
      return min.map((value, index) => (Number(value) + Number(max[index])) / 2);
    }};
    const focusForObject = (object) => {{
      const min = object?.bounds?.min || [];
      const max = object?.bounds?.max || [];
      if (min.length !== 3 || max.length !== 3) return null;
      const center = centerOf(object);
      const diagonal = Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
      return {{ target: center, radius: Math.max(0.35, diagonal * 2.6) }};
    }};
    const hitPositionFromEvent = (event) => {{
      if (typeof viewer.positionAndNormalFromPoint !== 'function') return null;
      try {{
        const hit = viewer.positionAndNormalFromPoint(event.clientX, event.clientY);
        const position = hit?.position;
        if (!position) return null;
        return [Number(position.x), Number(position.y), Number(position.z)];
      }} catch {{
        return null;
      }}
    }};
    const nearestObjectForPoint = (point) => {{
      if (!point || sceneObjects.length === 0) return null;
      let best = null;
      let bestScore = Infinity;
      for (const object of sceneObjects) {{
        const min = object?.bounds?.min || [];
        const max = object?.bounds?.max || [];
        const center = centerOf(object);
        if (!center) continue;
        let outsideDistance = 0;
        for (let index = 0; index < 3; index += 1) {{
          const pad = Math.max(0.025, Math.abs(max[index] - min[index]) * 0.08);
          const low = Number(min[index]) - pad;
          const high = Number(max[index]) + pad;
          const value = point[index];
          if (value < low) outsideDistance += (low - value) ** 2;
          if (value > high) outsideDistance += (value - high) ** 2;
        }}
        const centerDistance = Math.hypot(point[0] - center[0], point[1] - center[1], point[2] - center[2]);
        const score = Math.sqrt(outsideDistance) * 5 + centerDistance;
        if (score < bestScore) {{
          best = object;
          bestScore = score;
        }}
      }}
      return best;
    }};
    const postObjectSelection = (object, source) => {{
      if (window.parent === window || !object) return;
      window.parent.postMessage({{
        type: 'image23d.viewer.objectSelected',
        source,
        object: {{
          viewer_object_id: object.viewer_object_id || '',
          blender_object_id: object.blender_object_id || '',
          display_name: object.display_name || '',
          object_type: object.object_type || '',
          subject_id: object.subject_id || '',
          asset_id: object.asset_id || '',
        }},
      }}, '*');
    }};
    const selectObject = (object, source = 'viewer') => {{
      if (!object) return;
      selectedObjectKey = objectKey(object);
      const focus = focusForObject(object);
      if (focus) {{
        viewer.cameraTarget = `${{focus.target[0].toFixed(4)}}m ${{focus.target[1].toFixed(4)}}m ${{focus.target[2].toFixed(4)}}m`;
        viewer.cameraOrbit = `35deg 72deg ${{focus.radius.toFixed(4)}}m`;
        viewer.jumpCameraToGoal();
      }}
      if (selectionBadge) {{
        selectionBadge.hidden = false;
        selectionBadge.textContent = `已选择：${{displayObjectName(object)}}`;
      }}
      renderObjectPicker();
      postObjectSelection(object, source);
    }};
    function renderObjectPicker() {{
      if (!objectPicker || !sceneObjects.length) return;
      objectPicker.hidden = false;
      objectPicker.innerHTML = '';
      sceneObjects.slice(0, 8).forEach((object) => {{
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = displayObjectName(object);
        button.dataset.objectId = objectKey(object);
        button.className = objectKey(object) === selectedObjectKey ? 'selected' : '';
        button.addEventListener('click', () => selectObject(object, 'object-chip'));
        objectPicker.appendChild(button);
      }});
    }}
    renderObjectPicker();
    viewer.addEventListener('click', (event) => {{
      const target = event.target;
      if (target && target.closest && target.closest('button, a')) return;
      const object = nearestObjectForPoint(hitPositionFromEvent(event));
      if (object) selectObject(object, 'canvas-click');
    }});
    viewer.addEventListener('load', () => {{
      if (viewer.availableAnimations && viewer.availableAnimations.length > 0) {{
        viewer.animationName = viewer.availableAnimations[0];
        viewer.play();
        animButton.textContent = '{labels["anim_pause"]}';
      }} else {{
        animButton.disabled = true;
        animButton.textContent = '{labels["anim_none"]}';
      }}
    }});
    animButton.addEventListener('click', (event) => {{
      if (viewer.paused) {{
        viewer.play();
        event.target.textContent = '{labels["anim_pause"]}';
      }} else {{
        viewer.pause();
        event.target.textContent = '{labels["anim_play"]}';
      }}
    }});
    document.getElementById('toggleRotate').addEventListener('click', (event) => {{
      viewer.autoRotate = !viewer.autoRotate;
      event.target.textContent = viewer.autoRotate ? '{labels["rotate_on"]}' : '{labels["rotate_off"]}';
    }});
    document.getElementById('resetCamera').addEventListener('click', () => {{
      viewer.cameraOrbit = '{camera_orbit}';
      viewer.cameraTarget = '{camera_target}';
      viewer.jumpCameraToGoal();
    }});
  </script>
</body>
</html>"""
        )


def main():
    parser = argparse.ArgumentParser(description="Serve local GLB/GLTF files through a browser model-viewer UI.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--list-limit", type=int, default=80)
    args = parser.parse_args()

    roots = [Path(path).resolve() for path in (args.root or [Path.cwd()])]
    vendor = Path(__file__).resolve().parents[1] / "web" / "model_viewer" / "node_modules" / "@google" / "model-viewer" / "dist" / "model-viewer.min.js"

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    server.allowed_roots = roots
    server.vendor_js = vendor
    server.list_limit = args.list_limit
    print(f"Serving GLB viewer on http://{args.host}:{args.port}/", flush=True)
    for root in roots:
        print(f"Allowed root: {root}", flush=True)
    print(f"model-viewer bundle: {vendor}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
