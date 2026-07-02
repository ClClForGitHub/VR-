import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def bounds_of(objects):
    mins = Vector((float("inf"), float("inf"), float("inf")))
    maxs = Vector((float("-inf"), float("-inf"), float("-inf")))
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, point.x)
            mins.y = min(mins.y, point.y)
            mins.z = min(mins.z, point.z)
            maxs.x = max(maxs.x, point.x)
            maxs.y = max(maxs.y, point.y)
            maxs.z = max(maxs.z, point.z)
    return mins, maxs


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_vertex_color_material():
    mat = bpy.data.materials.new("WorldMirror_Vertex_Color")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Color"
    if bsdf is not None:
        links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.75
    return mat


def load_assembly_plan(path):
    if path is None:
        return {}
    plan_path = Path(path)
    if not plan_path.is_file():
        raise SystemExit(f"Assembly plan JSON does not exist: {plan_path}")
    with plan_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("scene_glb")
    parser.add_argument("asset_glb")
    parser.add_argument("preview_png")
    parser.add_argument("output_blend")
    parser.add_argument("assembly_plan_json", nargs="?")
    parser.add_argument("--asset-glbs-json")
    return parser.parse_args(argv)


def load_asset_specs(primary_asset_glb, assembly_plan, asset_glbs_json):
    plan_specs = assembly_plan.get("subject_assets") if isinstance(assembly_plan.get("subject_assets"), list) else []
    path_items = []
    if asset_glbs_json:
        decoded = json.loads(asset_glbs_json)
        if not isinstance(decoded, list):
            raise SystemExit("--asset-glbs-json must decode to a list")
        path_items = decoded
    elif plan_specs:
        path_items = [
            item.get("asset_glb") or item.get("glb_path") or item.get("path")
            for item in plan_specs
            if isinstance(item, dict) and (item.get("asset_glb") or item.get("glb_path") or item.get("path"))
        ]
    if not path_items:
        path_items = [str(primary_asset_glb)]

    specs = []
    for index, item in enumerate(path_items):
        spec = dict(plan_specs[index]) if index < len(plan_specs) and isinstance(plan_specs[index], dict) else {}
        if isinstance(item, dict):
            spec.update(item)
            asset_path = item.get("asset_glb") or item.get("glb_path") or item.get("path")
        else:
            asset_path = item
        if not asset_path:
            raise SystemExit(f"Missing asset path for subject asset index {index}")
        spec["asset_glb"] = str(asset_path)
        spec.setdefault("asset_index", index)
        specs.append(spec)
    return specs


def default_target_region(index, total, fallback):
    presets = {
        1: [fallback],
        2: [(-0.24, -0.18), (0.24, -0.18)],
        3: [(-0.30, -0.20), (0.0, -0.10), (0.30, -0.20)],
        4: [(-0.30, -0.24), (0.30, -0.24), (-0.18, 0.08), (0.18, 0.08)],
        5: [(-0.34, -0.24), (0.0, -0.24), (0.34, -0.24), (-0.18, 0.10), (0.18, 0.10)],
        6: [(-0.34, -0.25), (0.0, -0.25), (0.34, -0.25), (-0.34, 0.10), (0.0, 0.10), (0.34, 0.10)],
        7: [(-0.36, -0.26), (-0.12, -0.26), (0.12, -0.26), (0.36, -0.26), (-0.24, 0.10), (0.0, 0.10), (0.24, 0.10)],
    }
    row = presets.get(total)
    if row is not None and index < len(row):
        return row[index]
    columns = min(4, max(1, total))
    col = index % columns
    row_index = index // columns
    x = -0.36 + 0.72 * (col / max(columns - 1, 1))
    y = -0.26 + 0.34 * row_index
    return x, max(-0.35, min(0.35, y))


def asset_plan_value(asset_spec, assembly_plan, key, default=None):
    if key in asset_spec:
        return asset_spec[key]
    return assembly_plan.get(key, default)


def safe_name(value, fallback):
    raw = str(value or fallback)
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)


def numeric_pair(value, default):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return default
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return default


def clamped_pair(value, default, minimum=-0.8, maximum=0.8):
    first, second = numeric_pair(value, default)
    return (
        max(minimum, min(maximum, first)),
        max(minimum, min(maximum, second)),
    )


def numeric_triple(value, default):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return default
    try:
        return float(value[0]), float(value[1]), float(value[2])
    except (TypeError, ValueError):
        return default


def numeric_value(value, default, minimum=None, maximum=None):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(parsed, minimum)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def ensure_material(objects, material):
    for obj in objects:
        if obj.type == "MESH" and not obj.data.materials:
            obj.data.materials.append(material)


def clear_scene_occluders(objects, target, *, radius, min_height, ground_z):
    if radius <= 0:
        return []
    removed = []
    for obj in list(objects):
        obj_min, obj_max = bounds_of([obj])
        obj_size = obj_max - obj_min
        if obj_size.z < min_height:
            continue
        center = (obj_min + obj_max) * 0.5
        distance_xy = math.hypot(center.x - target.x, center.y - target.y)
        if distance_xy > radius:
            continue
        if obj_max.z <= ground_z + min_height:
            continue
        removed.append(obj.name)
        bpy.data.objects.remove(obj, do_unlink=True)
        if obj in objects:
            objects.remove(obj)
    return removed


def main():
    try:
        sep = sys.argv.index("--")
    except ValueError as exc:
        raise SystemExit(
            "Usage: blender -b --python compose_blender_scene.py -- scene.glb asset.glb preview.png output.blend [assembly_plan.json] [--asset-glbs-json JSON]"
        ) from exc

    args = parse_args(sys.argv[sep + 1 :])
    scene_glb = Path(args.scene_glb)
    asset_glb = Path(args.asset_glb)
    preview_png = Path(args.preview_png)
    output_blend = Path(args.output_blend)
    assembly_plan = load_assembly_plan(args.assembly_plan_json)
    asset_specs = load_asset_specs(asset_glb, assembly_plan, args.asset_glbs_json)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    bpy.ops.import_scene.gltf(filepath=str(scene_glb))
    scene_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not scene_objects:
        raise SystemExit(f"No scene mesh objects imported from {scene_glb}")

    vertex_color_material = make_vertex_color_material()
    ensure_material(scene_objects, vertex_color_material)
    scene_min, scene_max = bounds_of(scene_objects)
    scene_center = (scene_min + scene_max) * 0.5
    scene_size = scene_max - scene_min
    scene_height = max(scene_size.z, 1e-3)
    scene_horizontal = max(scene_size.x, scene_size.y, 1e-3)
    scene_reference_height = max(scene_height, scene_horizontal * 0.16)
    scene_max_dim = max(scene_size.x, scene_size.y, scene_size.z, 1e-3)

    asset_objects = []
    asset_summaries = []
    cleared_scene_objects = []
    total_assets = len(asset_specs)
    global_region = numeric_pair(assembly_plan.get("target_region_normalized"), (-0.18, 0.18))
    for asset_index, asset_spec in enumerate(asset_specs):
        current_asset_glb = Path(asset_spec["asset_glb"])
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=str(current_asset_glb))
        current_objects = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]
        if not current_objects:
            raise SystemExit(f"No asset mesh objects imported from {current_asset_glb}")

        asset_mat = bpy.data.materials.new(f"Hunyuan3D_Asset_Material_{asset_index + 1:02d}")
        asset_mat.diffuse_color = (0.72, 0.58, 0.48, 1.0)
        asset_mat.use_nodes = True
        bsdf = asset_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = asset_mat.diffuse_color
            bsdf.inputs["Roughness"].default_value = 0.65
        ensure_material(current_objects, asset_mat)

        asset_min, asset_max = bounds_of(current_objects)
        asset_center = (asset_min + asset_max) * 0.5
        asset_size = asset_max - asset_min
        asset_height = max(asset_size.z, 1e-3)
        default_height_ratio = 0.42 if total_assets == 1 else 0.26
        target_height_ratio = numeric_value(
            asset_plan_value(asset_spec, assembly_plan, "target_height_ratio", default_height_ratio),
            default_height_ratio,
            minimum=0.05,
            maximum=1.5,
        )
        target_height = scene_reference_height * target_height_ratio
        scale = target_height / asset_height
        subject_yaw_degrees = numeric_value(
            asset_plan_value(asset_spec, assembly_plan, "subject_yaw_degrees", 0.0),
            0.0,
            minimum=-180.0,
            maximum=180.0,
        )

        default_region = default_target_region(asset_index, total_assets, global_region)
        region_x, region_y = numeric_pair(
            asset_plan_value(asset_spec, assembly_plan, "target_region_normalized", default_region),
            default_region,
        )
        target = Vector((
            scene_center.x + scene_size.x * region_x,
            scene_center.y + scene_size.y * region_y,
            scene_min.z,
        ))
        clearance_radius_normalized = numeric_value(
            asset_plan_value(asset_spec, assembly_plan, "subject_clearance_radius_normalized", 0.0),
            0.0,
            minimum=0.0,
            maximum=0.5,
        )
        clearance_min_height_ratio = numeric_value(
            asset_plan_value(asset_spec, assembly_plan, "subject_clearance_min_height_ratio", 0.12),
            0.12,
            minimum=0.0,
            maximum=1.0,
        )
        cleared_scene_objects.extend(
            clear_scene_occluders(
                scene_objects,
                target,
                radius=max(scene_size.x, scene_size.y) * clearance_radius_normalized,
                min_height=scene_height * clearance_min_height_ratio,
                ground_z=scene_min.z,
            )
        )
        asset_transform = (
            Matrix.Translation(target + Vector((0, 0, target_height * 0.5)))
            @ Matrix.Rotation(math.radians(subject_yaw_degrees), 4, "Z")
            @ Matrix.Diagonal((scale, scale, scale, 1.0))
            @ Matrix.Translation(-asset_center)
        )
        name_prefix = "Hunyuan3D_" + safe_name(
            asset_spec.get("subject_id") or asset_spec.get("subject_asset_id"),
            f"subject_{asset_index + 1:02d}",
        )
        for obj in current_objects:
            obj.matrix_world = asset_transform @ obj.matrix_world
            obj.name = f"{name_prefix}_{obj.name}"
        asset_objects.extend(current_objects)
        asset_summaries.append(
            {
                "asset_glb": str(current_asset_glb),
                "mesh_objects": len(current_objects),
                "scale": scale,
                "target": target,
                "target_height_ratio": target_height_ratio,
                "subject_yaw_degrees": subject_yaw_degrees,
            }
        )
    bpy.context.view_layer.update()

    all_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    all_min, all_max = bounds_of(all_meshes)
    all_center = (all_min + all_max) * 0.5
    all_size = all_max - all_min
    max_dim = max(all_size.x, all_size.y, all_size.z, 1e-3)
    framed_min, framed_max = bounds_of(asset_objects)
    framed_center = (framed_min + framed_max) * 0.5
    framed_size = framed_max - framed_min
    camera_frame = str(assembly_plan.get("camera_frame") or "scene").lower()
    if camera_frame == "subject":
        camera_bounds_center = framed_center
        camera_bounds_size = framed_size
        camera_max_dim = max(
            framed_size.x * 1.25,
            framed_size.y * 1.25,
            framed_size.z * 1.55,
            scene_horizontal * 0.18,
            1e-3,
        )
    else:
        camera_bounds_center = all_center
        camera_bounds_size = all_size
        camera_max_dim = max_dim

    bpy.ops.object.light_add(type="AREA", location=(all_center.x, all_center.y - max_dim * 1.2, all_center.z + max_dim * 1.8))
    light = bpy.context.object
    light.name = "Preview_Area_Light"
    light.data.energy = numeric_value(assembly_plan.get("key_light_energy"), 780, minimum=50, maximum=5000)
    light.data.size = max_dim * 1.6

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "Preview_Camera"
    camera.data.type = "ORTHO"
    ortho_scale_factor = numeric_value(assembly_plan.get("camera_ortho_scale_factor"), 1.55, minimum=0.35, maximum=5.0)
    camera_distance_multiplier = numeric_value(assembly_plan.get("camera_distance_multiplier"), 2.8, minimum=0.8, maximum=8.0)
    camera_direction = Vector(numeric_triple(assembly_plan.get("camera_direction"), (1.25, -1.55, 0.85)))
    if camera_direction.length < 1e-6:
        camera_direction = Vector((1.25, -1.55, 0.85))
    camera_target_x, camera_target_y = clamped_pair(assembly_plan.get("camera_target_normalized"), (0.0, 0.0))
    camera_target = Vector((
        camera_bounds_center.x + camera_bounds_size.x * camera_target_x,
        camera_bounds_center.y + camera_bounds_size.y * camera_target_y,
        camera_bounds_center.z,
    ))
    camera.data.ortho_scale = camera_max_dim * ortho_scale_factor
    camera.location = camera_target + camera_direction.normalized() * camera_max_dim * camera_distance_multiplier
    camera.data.clip_end = max(max_dim, camera_max_dim) * 30
    look_at(camera, camera_target)

    bpy.ops.object.light_add(
        type="AREA",
        location=(
            camera.location.x,
            camera.location.y,
            camera.location.z + max_dim * 0.35,
        ),
    )
    fill = bpy.context.object
    fill.name = "Preview_Camera_Fill_Light"
    fill.data.energy = numeric_value(assembly_plan.get("fill_light_energy"), 260, minimum=0, maximum=3000)
    fill.data.size = max_dim * 2.2

    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.world.color = (0.68, 0.68, 0.68)
    resolution_x, resolution_y = numeric_pair(assembly_plan.get("render_resolution"), (1400, 900))
    scene.render.resolution_x = int(max(320, min(resolution_x, 4096)))
    scene.render.resolution_y = int(max(240, min(resolution_y, 4096)))
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = numeric_value(assembly_plan.get("exposure"), 0.25, minimum=-3.0, maximum=3.0)

    preview_png.parent.mkdir(parents=True, exist_ok=True)
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(preview_png)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.render.render(write_still=True)

    print(f"Imported scene: {scene_glb}")
    print(f"Scene mesh objects: {len(scene_objects)}")
    print(f"Imported assets: {[summary['asset_glb'] for summary in asset_summaries]}")
    print(f"Asset count: {len(asset_summaries)}")
    print(f"Asset mesh objects: {len(asset_objects)}")
    if assembly_plan:
        print(f"Assembly plan: {assembly_plan.get('plan_id', 'unnamed')}")
    print(f"Asset scales: {[round(summary['scale'], 6) for summary in asset_summaries]}")
    print(f"Scene reference height: {scene_reference_height:.6f}")
    print(f"Asset yaw degrees: {[round(summary['subject_yaw_degrees'], 3) for summary in asset_summaries]}")
    print(f"Asset targets: {[tuple(round(v, 4) for v in summary['target']) for summary in asset_summaries]}")
    print(f"Cleared scene occluders: {cleared_scene_objects}")
    print(f"Camera direction: {tuple(round(v, 4) for v in camera_direction)}")
    print(f"Camera frame: {camera_frame}")
    print(f"Camera target: {tuple(round(v, 4) for v in camera_target)}")
    print(f"Camera ortho scale factor: {ortho_scale_factor:.6f}")
    print(f"Saved preview: {preview_png}")
    print(f"Saved blend: {output_blend}")


if __name__ == "__main__":
    main()
