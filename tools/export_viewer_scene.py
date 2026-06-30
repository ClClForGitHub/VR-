import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


def bounds_of_object(obj):
    if not hasattr(obj, "bound_box"):
        return None
    mins = Vector((float("inf"), float("inf"), float("inf")))
    maxs = Vector((float("-inf"), float("-inf"), float("-inf")))
    for corner in obj.bound_box:
        point = obj.matrix_world @ Vector(corner)
        mins.x = min(mins.x, point.x)
        mins.y = min(mins.y, point.y)
        mins.z = min(mins.z, point.z)
        maxs.x = max(maxs.x, point.x)
        maxs.y = max(maxs.y, point.y)
        maxs.z = max(maxs.z, point.z)
    if mins.x == float("inf"):
        return None
    return {
        "min": [round(mins.x, 6), round(mins.y, 6), round(mins.z, 6)],
        "max": [round(maxs.x, 6), round(maxs.y, 6), round(maxs.z, 6)],
    }


def transform_of(obj):
    return {
        "location": [round(value, 6) for value in obj.location],
        "rotation_euler": [round(value, 6) for value in obj.rotation_euler],
        "scale": [round(value, 6) for value in obj.scale],
    }


def camera_state(camera):
    if camera is None:
        return None
    return {
        "name": camera.name,
        "type": camera.data.type,
        "transform": transform_of(camera),
        "focal_length": getattr(camera.data, "lens", None),
        "ortho_scale": getattr(camera.data, "ortho_scale", None),
        "clip_start": getattr(camera.data, "clip_start", None),
        "clip_end": getattr(camera.data, "clip_end", None),
    }


def object_record(obj):
    record = {
        "viewer_object_id": obj.name,
        "subject_id": None,
        "blender_object_id": obj.name,
        "asset_id": None,
        "display_name": obj.name,
        "selectable": obj.type == "MESH",
        "highlighted": False,
        "object_type": obj.type,
        "transform": transform_of(obj),
    }
    bounds = bounds_of_object(obj)
    if bounds is not None:
        record["bounds"] = bounds
    return record


def main():
    try:
        sep = sys.argv.index("--")
    except ValueError as exc:
        raise SystemExit(
            "Usage: blender -b --python export_viewer_scene.py -- input.blend viewer_scene.glb scene_state.json"
        ) from exc

    blend_path = Path(sys.argv[sep + 1])
    viewer_glb = Path(sys.argv[sep + 2])
    scene_state_json = Path(sys.argv[sep + 3])

    bpy.ops.wm.open_mainfile(filepath=str(blend_path))

    viewer_glb.parent.mkdir(parents=True, exist_ok=True)
    scene_state_json.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(viewer_glb),
        export_format="GLB",
        export_animations=False,
    )

    scene = bpy.context.scene
    state = {
        "viewer_scene_id": viewer_glb.stem,
        "source_blend_version_id": blend_path.stem,
        "viewer_scene_artifact_id": None,
        "viewer_state_artifact_id": None,
        "objects": [
            object_record(obj)
            for obj in scene.objects
            if obj.type in {"MESH", "EMPTY", "CAMERA", "LIGHT"}
        ],
        "camera": camera_state(scene.camera),
        "active_object_id": bpy.context.view_layer.objects.active.name
        if bpy.context.view_layer.objects.active is not None
        else None,
        "version": 1,
        "last_exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_blend_path": str(blend_path),
        "viewer_scene_path": str(viewer_glb),
    }
    scene_state_json.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Opened blend: {blend_path}")
    print(f"Exported viewer GLB: {viewer_glb}")
    print(f"Wrote scene state: {scene_state_json}")
    print(f"Objects exported in state: {len(state['objects'])}")


if __name__ == "__main__":
    main()
