import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


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


def main():
    try:
        sep = sys.argv.index("--")
    except ValueError as exc:
        raise SystemExit(
            "Usage: blender -b --python compose_blender_scene.py -- scene.glb asset.glb preview.png output.blend"
        ) from exc

    scene_glb = Path(sys.argv[sep + 1])
    asset_glb = Path(sys.argv[sep + 2])
    preview_png = Path(sys.argv[sep + 3])
    output_blend = Path(sys.argv[sep + 4])
    assembly_plan = load_assembly_plan(sys.argv[sep + 5] if len(sys.argv) > sep + 5 else None)

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
    scene_max_dim = max(scene_size.x, scene_size.y, scene_size.z, 1e-3)

    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(asset_glb))
    asset_objects = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]
    if not asset_objects:
        raise SystemExit(f"No asset mesh objects imported from {asset_glb}")

    asset_mat = bpy.data.materials.new("Hunyuan3D_Asset_Material")
    asset_mat.diffuse_color = (0.72, 0.58, 0.48, 1.0)
    asset_mat.use_nodes = True
    bsdf = asset_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = asset_mat.diffuse_color
        bsdf.inputs["Roughness"].default_value = 0.65
    ensure_material(asset_objects, asset_mat)

    asset_min, asset_max = bounds_of(asset_objects)
    asset_center = (asset_min + asset_max) * 0.5
    asset_size = asset_max - asset_min
    asset_height = max(asset_size.z, 1e-3)
    target_height_ratio = numeric_value(assembly_plan.get("target_height_ratio"), 0.42, minimum=0.05, maximum=1.5)
    target_height = scene_height * target_height_ratio
    scale = target_height / asset_height

    region_x, region_y = numeric_pair(assembly_plan.get("target_region_normalized"), (-0.18, 0.18))
    target = Vector((
        scene_center.x + scene_size.x * region_x,
        scene_center.y + scene_size.y * region_y,
        scene_min.z,
    ))
    for obj in asset_objects:
        obj.location = (obj.location - asset_center) * scale + target + Vector((0, 0, target_height * 0.5))
        obj.scale *= scale
        obj.name = "Hunyuan3D_" + obj.name

    all_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    all_min, all_max = bounds_of(all_meshes)
    all_center = (all_min + all_max) * 0.5
    all_size = all_max - all_min
    max_dim = max(all_size.x, all_size.y, all_size.z, 1e-3)

    bpy.ops.object.light_add(type="AREA", location=(all_center.x, all_center.y - max_dim * 1.2, all_center.z + max_dim * 1.8))
    light = bpy.context.object
    light.name = "Preview_Area_Light"
    light.data.energy = 320
    light.data.size = max_dim * 1.4

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
        all_center.x + all_size.x * camera_target_x,
        all_center.y + all_size.y * camera_target_y,
        all_center.z,
    ))
    camera.data.ortho_scale = max_dim * ortho_scale_factor
    camera.location = camera_target + camera_direction.normalized() * max_dim * camera_distance_multiplier
    camera.data.clip_end = max_dim * 30
    look_at(camera, camera_target)

    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.world.color = (0.50, 0.50, 0.50)
    resolution_x, resolution_y = numeric_pair(assembly_plan.get("render_resolution"), (1400, 900))
    scene.render.resolution_x = int(max(320, min(resolution_x, 4096)))
    scene.render.resolution_y = int(max(240, min(resolution_y, 4096)))
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"

    preview_png.parent.mkdir(parents=True, exist_ok=True)
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(preview_png)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.render.render(write_still=True)

    print(f"Imported scene: {scene_glb}")
    print(f"Scene mesh objects: {len(scene_objects)}")
    print(f"Imported asset: {asset_glb}")
    print(f"Asset mesh objects: {len(asset_objects)}")
    if assembly_plan:
        print(f"Assembly plan: {assembly_plan.get('plan_id', 'unnamed')}")
    print(f"Asset scale: {scale:.6f}")
    print(f"Asset target: {tuple(round(v, 4) for v in target)}")
    print(f"Camera direction: {tuple(round(v, 4) for v in camera_direction)}")
    print(f"Camera target: {tuple(round(v, 4) for v in camera_target)}")
    print(f"Camera ortho scale factor: {ortho_scale_factor:.6f}")
    print(f"Saved preview: {preview_png}")
    print(f"Saved blend: {output_blend}")


if __name__ == "__main__":
    main()
