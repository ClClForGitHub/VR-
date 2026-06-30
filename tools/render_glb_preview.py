import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main():
    try:
        sep = sys.argv.index("--")
    except ValueError as exc:
        raise SystemExit("Usage: blender -b --python render_glb_preview.py -- input.glb output.png output.blend") from exc

    glb_path = Path(sys.argv[sep + 1])
    output_png = Path(sys.argv[sep + 2])
    output_blend = Path(sys.argv[sep + 3])

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not mesh_objects:
        raise SystemExit(f"No mesh objects imported from {glb_path}")

    vertex_color_mat = bpy.data.materials.new("Preview_Vertex_Color")
    vertex_color_mat.use_nodes = True
    nodes = vertex_color_mat.node_tree.nodes
    links = vertex_color_mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Color"
    if bsdf is not None:
        links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.75

    palette = [
        (0.70, 0.64, 0.52, 1.0),
        (0.46, 0.54, 0.64, 1.0),
        (0.58, 0.44, 0.36, 1.0),
        (0.36, 0.42, 0.38, 1.0),
    ]
    for idx, obj in enumerate(mesh_objects):
        if obj.data.materials:
            continue
        if obj.data.color_attributes.get("Color") is not None:
            obj.data.materials.append(vertex_color_mat)
            continue
        mat = bpy.data.materials.new(f"Preview_Material_{idx:02d}")
        mat.diffuse_color = palette[idx % len(palette)]
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = mat.diffuse_color
            bsdf.inputs["Roughness"].default_value = 0.7
        obj.data.materials.append(mat)

    mins = Vector((float("inf"), float("inf"), float("inf")))
    maxs = Vector((float("-inf"), float("-inf"), float("-inf")))
    for obj in mesh_objects:
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, point.x)
            mins.y = min(mins.y, point.y)
            mins.z = min(mins.z, point.z)
            maxs.x = max(maxs.x, point.x)
            maxs.y = max(maxs.y, point.y)
            maxs.z = max(maxs.z, point.z)

    center = (mins + maxs) * 0.5
    size = maxs - mins
    max_dim = max(size.x, size.y, size.z, 1e-3)

    bpy.ops.object.light_add(type="AREA", location=(center.x, center.y - max_dim * 1.2, center.z + max_dim * 1.7))
    light = bpy.context.object
    light.name = "Preview_Area_Light"
    light.data.energy = 260
    light.data.size = max_dim * 1.5

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "Preview_Camera"
    direction = Vector((1.25, -1.55, 0.8)).normalized()
    camera.location = center + direction * max_dim * 2.8
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max_dim * 1.55
    camera.data.clip_end = max_dim * 20
    look_at(camera, center)

    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.world.color = (0.50, 0.50, 0.50)
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 900
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1

    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output_png)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.render.render(write_still=True)

    print(f"Imported GLB: {glb_path}")
    print(f"Mesh objects: {len(mesh_objects)}")
    print(f"Bounds min: {tuple(round(v, 4) for v in mins)}")
    print(f"Bounds max: {tuple(round(v, 4) for v in maxs)}")
    print(f"Saved preview: {output_png}")
    print(f"Saved blend: {output_blend}")


if __name__ == "__main__":
    main()
