import importlib.util
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from http.server import ThreadingHTTPServer


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "glb_viewer_server.py"
SPEC = importlib.util.spec_from_file_location("glb_viewer_server_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
glb_viewer_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(glb_viewer_server)

ViewerHandler = glb_viewer_server.ViewerHandler
camera_orbit_from_query = glb_viewer_server.camera_orbit_from_query
camera_target_from_query = glb_viewer_server.camera_target_from_query
public_scene_objects_for_model = glb_viewer_server.public_scene_objects_for_model
query_flag = glb_viewer_server.query_flag


def test_query_flag_accepts_truthy_values() -> None:
    assert query_flag({"embed": ["1"]}, "embed") is True
    assert query_flag({"public": ["true"]}, "public") is True
    assert query_flag({"public": ["0"]}, "public") is False
    assert query_flag({}, "embed") is False


def test_camera_focus_query_builds_model_viewer_camera_values() -> None:
    assert camera_target_from_query({"target": ["1,2.5,-0.25"]}) == "1.0000m 2.5000m -0.2500m"
    assert camera_orbit_from_query({"radius": ["3.2"]}) == "35deg 72deg 3.2000m"
    assert camera_orbit_from_query({"orbit": ["15,65,2.75"]}) == "15.00deg 65.00deg 2.7500m"
    assert camera_target_from_query({"target": ["bad"]}) == "auto auto auto"
    assert camera_orbit_from_query({"radius": ["bad"]}) == "35deg 72deg auto"


def test_public_embed_viewer_hides_visual_path_and_uses_chinese_labels(tmp_path: Path) -> None:
    model = tmp_path / "viewer_scene.glb"
    model.write_bytes(b"glb")
    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    server.allowed_roots = [tmp_path.resolve()]
    server.vendor_js = tmp_path / "missing-model-viewer.min.js"
    server.list_limit = 10
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        encoded_path = urllib.parse.quote(str(model.resolve()), safe="")
        url = f"http://127.0.0.1:{server.server_port}/viewer?path={encoded_path}&embed=1&public=1&lang=zh-CN"
        body = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert 'body class="embed public"' in body
    assert "暂停旋转" in body
    assert "播放动画" in body
    assert "重置视角" in body
    assert ">Download<" not in body
    assert ">List<" not in body
    assert '<div class="path">' not in body
    assert str(model.resolve()) not in body


def test_public_embed_viewer_accepts_focus_camera_params(tmp_path: Path) -> None:
    model = tmp_path / "viewer_scene.glb"
    model.write_bytes(b"glb")
    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    server.allowed_roots = [tmp_path.resolve()]
    server.vendor_js = tmp_path / "missing-model-viewer.min.js"
    server.list_limit = 10
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        encoded_path = urllib.parse.quote(str(model.resolve()), safe="")
        url = (
            f"http://127.0.0.1:{server.server_port}/viewer?path={encoded_path}"
            "&embed=1&public=1&lang=zh-CN&target=0.1,0.2,-0.3&radius=1.7&focus=Hero"
        )
        body = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert 'camera-target="0.1000m 0.2000m -0.3000m"' in body
    assert 'camera-orbit="35deg 72deg 1.7000m"' in body
    assert "聚焦：Hero" in body


def test_public_scene_objects_are_loaded_without_paths(tmp_path: Path) -> None:
    model = tmp_path / "viewer_scene.glb"
    model.write_bytes(b"glb")
    (tmp_path / "scene_state.json").write_text(
        """
        {
          "source_blend_path": "/home/team/zouzhiyuan/secret.blend",
          "objects": [
            {
              "viewer_object_id": "HeroMesh",
              "blender_object_id": "HeroMesh.001",
              "display_name": "Hunyuan3D_geometry_0.001",
              "object_type": "MESH",
              "selectable": true,
              "subject_id": "subject_plush",
              "asset_id": "workflow_subject_glb",
              "bounds": {"min": [0.1, 0.2, -0.3], "max": [0.4, 0.8, 0.1]}
            },
            {
              "viewer_object_id": "Camera",
              "display_name": "Camera",
              "object_type": "CAMERA",
              "selectable": false,
              "bounds": {"min": [0, 0, 0], "max": [0, 0, 0]}
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    objects = public_scene_objects_for_model(model)

    assert len(objects) == 1
    assert objects[0]["viewer_object_id"] == "HeroMesh"
    assert "source_blend_path" not in objects[0]


def test_public_embed_viewer_exposes_object_selection_bridge(tmp_path: Path) -> None:
    model = tmp_path / "viewer_scene.glb"
    model.write_bytes(b"glb")
    (tmp_path / "scene_state.json").write_text(
        """
        {
          "source_blend_path": "/home/team/zouzhiyuan/secret.blend",
          "objects": [
            {
              "viewer_object_id": "HeroMesh",
              "blender_object_id": "HeroMesh.001",
              "display_name": "Hunyuan3D_geometry_0.001",
              "object_type": "MESH",
              "selectable": true,
              "subject_id": "subject_plush",
              "asset_id": "workflow_subject_glb",
              "bounds": {"min": [0.1, 0.2, -0.3], "max": [0.4, 0.8, 0.1]}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    server.allowed_roots = [tmp_path.resolve()]
    server.vendor_js = tmp_path / "missing-model-viewer.min.js"
    server.list_limit = 10
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        encoded_path = urllib.parse.quote(str(model.resolve()), safe="")
        url = f"http://127.0.0.1:{server.server_port}/viewer?path={encoded_path}&embed=1&public=1&lang=zh-CN"
        body = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "sceneObjectsJson" in body
    assert "image23d.viewer.objectSelected" in body
    assert "objectPicker" in body
    assert "HeroMesh" in body
    assert "&quot;" not in body
    assert "/home/team/zouzhiyuan/secret.blend" not in body
