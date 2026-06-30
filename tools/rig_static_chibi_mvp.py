#!/usr/bin/env python3
"""Create a rough animated armature for a static chibi GLB.

This is a proof-of-pipeline tool, not production-quality auto-rigging.
It creates coarse vertex groups from spatial regions, adds a simple armature,
keys a short dance-like motion, and exports an animated GLB.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import bpy
from mathutils import Vector


MMD_BONE_NAMES = {
    "root": "全ての親",
    "center": "センター",
    "hips": "下半身",
    "spine": "上半身",
    "head": "頭",
    "upper_arm.L": "左腕",
    "forearm.L": "左ひじ",
    "upper_arm.R": "右腕",
    "forearm.R": "右ひじ",
    "thigh.L": "左足",
    "shin.L": "左ひざ",
    "thigh.R": "右足",
    "shin.R": "右ひざ",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--name", default="rigged_chibi_mvp")
    parser.add_argument("--vmd", default="")
    parser.add_argument("--camera-vmd", default="")
    parser.add_argument("--audio", default="")
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def bounds_for_meshes(mesh_objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    mn = Vector((float("inf"), float("inf"), float("inf")))
    mx = Vector((float("-inf"), float("-inf"), float("-inf")))
    for obj in mesh_objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            mn.x = min(mn.x, world.x)
            mn.y = min(mn.y, world.y)
            mn.z = min(mn.z, world.z)
            mx.x = max(mx.x, world.x)
            mx.y = max(mx.y, world.y)
            mx.z = max(mx.z, world.z)
    return mn, mx


def add_bone(edit_bones, name: str, head: tuple[float, float, float], tail: tuple[float, float, float], parent=None):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    bone.parent = parent
    return bone


def bone_name(name: str, use_mmd_names: bool) -> str:
    if use_mmd_names:
        return MMD_BONE_NAMES.get(name, name)
    return name


def create_armature(mn: Vector, mx: Vector, use_mmd_names: bool = False) -> bpy.types.Object:
    cx = (mn.x + mx.x) * 0.5
    cy = (mn.y + mx.y) * 0.5
    h = mx.z - mn.z
    z = lambda r: mn.z + h * r

    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    armature = bpy.context.object
    armature.name = "Chibi_MVP_Armature"
    armature.data.name = "Chibi_MVP_ArmatureData"
    armature.show_in_front = True

    edit_bones = armature.data.edit_bones
    edit_bones.remove(edit_bones[0])

    parent = None
    if use_mmd_names:
        root = add_bone(edit_bones, bone_name("root", True), (cx, cy, z(0.02)), (cx, cy, z(0.08)))
        parent = add_bone(edit_bones, bone_name("center", True), (cx, cy, z(0.12)), (cx, cy, z(0.34)), root)

    hips = add_bone(edit_bones, bone_name("hips", use_mmd_names), (cx, cy, z(0.34)), (cx, cy, z(0.45)), parent)
    spine = add_bone(edit_bones, bone_name("spine", use_mmd_names), (cx, cy, z(0.45)), (cx, cy, z(0.62)), hips)
    head = add_bone(edit_bones, bone_name("head", use_mmd_names), (cx, cy, z(0.62)), (cx, cy, z(0.92)), spine)

    shoulder_z = z(0.57)
    hand_z = z(0.35)
    left_x = mn.x + (mx.x - mn.x) * 0.20
    right_x = mn.x + (mx.x - mn.x) * 0.80
    mid_left_x = mn.x + (mx.x - mn.x) * 0.34
    mid_right_x = mn.x + (mx.x - mn.x) * 0.66
    far_left_x = mn.x + (mx.x - mn.x) * 0.06
    far_right_x = mn.x + (mx.x - mn.x) * 0.94

    upper_arm_l = add_bone(edit_bones, bone_name("upper_arm.L", use_mmd_names), (mid_left_x, cy, shoulder_z), (left_x, cy, z(0.48)), spine)
    add_bone(edit_bones, bone_name("forearm.L", use_mmd_names), (left_x, cy, z(0.48)), (far_left_x, cy, hand_z), upper_arm_l)
    upper_arm_r = add_bone(edit_bones, bone_name("upper_arm.R", use_mmd_names), (mid_right_x, cy, shoulder_z), (right_x, cy, z(0.48)), spine)
    add_bone(edit_bones, bone_name("forearm.R", use_mmd_names), (right_x, cy, z(0.48)), (far_right_x, cy, hand_z), upper_arm_r)

    hip_left_x = mn.x + (mx.x - mn.x) * 0.43
    hip_right_x = mn.x + (mx.x - mn.x) * 0.57
    foot_left_x = mn.x + (mx.x - mn.x) * 0.40
    foot_right_x = mn.x + (mx.x - mn.x) * 0.60
    thigh_l = add_bone(edit_bones, bone_name("thigh.L", use_mmd_names), (hip_left_x, cy, z(0.34)), (foot_left_x, cy, z(0.17)), hips)
    add_bone(edit_bones, bone_name("shin.L", use_mmd_names), (foot_left_x, cy, z(0.17)), (foot_left_x, cy, z(0.02)), thigh_l)
    thigh_r = add_bone(edit_bones, bone_name("thigh.R", use_mmd_names), (hip_right_x, cy, z(0.34)), (foot_right_x, cy, z(0.17)), hips)
    add_bone(edit_bones, bone_name("shin.R", use_mmd_names), (foot_right_x, cy, z(0.17)), (foot_right_x, cy, z(0.02)), thigh_r)

    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def assign_coarse_weights(mesh_obj: bpy.types.Object, mn: Vector, mx: Vector, use_mmd_names: bool = False) -> dict[str, int]:
    h = mx.z - mn.z
    w = mx.x - mn.x
    groups = {
        bone_name(name, use_mmd_names): mesh_obj.vertex_groups.new(name=bone_name(name, use_mmd_names))
        for name in [
            "hips",
            "spine",
            "head",
            "upper_arm.L",
            "forearm.L",
            "upper_arm.R",
            "forearm.R",
            "thigh.L",
            "shin.L",
            "thigh.R",
            "shin.R",
        ]
    }
    buckets: dict[str, list[int]] = defaultdict(list)

    for vertex in mesh_obj.data.vertices:
        world = mesh_obj.matrix_world @ vertex.co
        zn = (world.z - mn.z) / h
        xn = (world.x - mn.x) / w
        bone = "spine"

        if zn > 0.58:
            bone = "head"
        elif zn < 0.18:
            bone = "shin.L" if xn < 0.5 else "shin.R"
        elif zn < 0.34:
            bone = "thigh.L" if xn < 0.5 else "thigh.R"
        elif xn < 0.20 and 0.22 < zn < 0.62:
            bone = "forearm.L"
        elif xn < 0.38 and 0.28 < zn < 0.68:
            bone = "upper_arm.L"
        elif xn > 0.80 and 0.22 < zn < 0.62:
            bone = "forearm.R"
        elif xn > 0.62 and 0.28 < zn < 0.68:
            bone = "upper_arm.R"
        elif zn < 0.44:
            bone = "hips"

        buckets[bone_name(bone, use_mmd_names)].append(vertex.index)

    for bone, indices in buckets.items():
        group = groups[bone]
        for start in range(0, len(indices), 20000):
            group.add(indices[start : start + 20000], 1.0, "ADD")
    return {name: len(indices) for name, indices in buckets.items()}


def animate_armature(armature: bpy.types.Object) -> None:
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 96
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "XYZ"

    keyframes = [1, 13, 25, 37, 49, 61, 73, 85, 96]
    for frame in keyframes:
        phase = (frame - 1) / 12.0
        sway = math.sin(phase * math.pi)
        alt = math.sin(phase * math.pi + math.pi)
        bpy.context.scene.frame_set(frame)

        armature.location.x = 0.035 * sway
        armature.rotation_euler = (0.035 * alt, 0.0, 0.08 * sway)
        armature.keyframe_insert("location", frame=frame)
        armature.keyframe_insert("rotation_euler", frame=frame)

        rotations = {
            "hips": (0.06 * alt, 0.0, 0.08 * sway),
            "spine": (-0.06 * alt, 0.0, -0.10 * sway),
            "head": (0.04 * alt, 0.0, 0.12 * sway),
            "upper_arm.L": (0.0, 0.0, 0.55 * alt),
            "forearm.L": (0.0, 0.0, 0.32 * alt),
            "upper_arm.R": (0.0, 0.0, 0.55 * sway),
            "forearm.R": (0.0, 0.0, 0.32 * sway),
            "thigh.L": (0.18 * sway, 0.0, 0.08 * alt),
            "shin.L": (-0.12 * sway, 0.0, 0.0),
            "thigh.R": (0.18 * alt, 0.0, 0.08 * sway),
            "shin.R": (-0.12 * alt, 0.0, 0.0),
        }
        for name, rotation in rotations.items():
            pose_bone = armature.pose.bones.get(name)
            if pose_bone is None:
                continue
            pose_bone.rotation_euler = rotation
            pose_bone.keyframe_insert("rotation_euler", frame=frame)


def add_camera_and_light(mesh_objects: list[bpy.types.Object], mn: Vector, mx: Vector) -> bpy.types.Object:
    center = (mn + mx) * 0.5
    extent = mx - mn
    size = max(extent.x, extent.y, extent.z)
    bpy.ops.object.light_add(type="AREA", location=(center.x, center.y - size * 1.2, center.z + size * 0.9))
    light = bpy.context.object
    light.name = "Rig_MVP_Area_Key"
    light.data.energy = 550
    light.data.size = max(size * 0.7, 1.0)

    bpy.ops.object.camera_add(location=(center.x, center.y - size * 2.4, center.z + size * 0.15))
    camera = bpy.context.object
    camera.name = "Rig_MVP_Camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(extent.z * 1.2, extent.x * 1.15)
    direction = center - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera
    return camera


def add_audio_to_timeline(audio_path: Path) -> str:
    bpy.context.scene.sequence_editor_create()
    bpy.context.scene.sequence_editor.strips.new_sound(
        name=audio_path.stem,
        filepath=str(audio_path),
        channel=1,
        frame_start=1,
    )
    return str(audio_path)


def main() -> None:
    args = parse_args()
    src = Path(args.input)
    out_dir = Path(args.out_dir)
    vmd_path = Path(args.vmd) if args.vmd else None
    camera_vmd_path = Path(args.camera_vmd) if args.camera_vmd else None
    audio_path = Path(args.audio) if args.audio else None
    use_mmd_names = vmd_path is not None
    out_dir.mkdir(parents=True, exist_ok=True)
    blend_path = out_dir / f"{args.name}.blend"
    glb_path = out_dir / f"{args.name}_animated.glb"

    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    bpy.ops.import_scene.gltf(filepath=str(src))
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(mesh_objects) != 1:
        raise RuntimeError(f"Expected one mesh for this MVP, found {len(mesh_objects)}")

    mesh_obj = mesh_objects[0]
    mn, mx = bounds_for_meshes(mesh_objects)
    weight_counts = assign_coarse_weights(mesh_obj, mn, mx, use_mmd_names=use_mmd_names)
    armature = create_armature(mn, mx, use_mmd_names=use_mmd_names)

    modifier = mesh_obj.modifiers.new("Chibi_MVP_Armature", "ARMATURE")
    modifier.object = armature
    mesh_obj.parent = armature

    vmd_status = None
    if vmd_path is not None:
        bpy.ops.object.select_all(action="DESELECT")
        armature.select_set(True)
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = armature
        vmd_status = bpy.ops.mmd_tools.import_vmd(
            filepath=str(vmd_path),
            scale=0.08,
            update_scene_settings=True,
            bone_mapper="PMX",
            log_level="ERROR",
        )
    else:
        animate_armature(armature)
    camera = add_camera_and_light(mesh_objects, mn, mx)

    camera_vmd_status = None
    if camera_vmd_path is not None:
        bpy.ops.object.select_all(action="DESELECT")
        camera.select_set(True)
        bpy.context.view_layer.objects.active = camera
        camera_vmd_status = bpy.ops.mmd_tools.import_vmd(
            filepath=str(camera_vmd_path),
            scale=0.08,
            update_scene_settings=True,
            log_level="ERROR",
        )

    audio_added = None
    if audio_path is not None:
        audio_added = add_audio_to_timeline(audio_path)

    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.render.resolution_x = 900
    bpy.context.scene.render.resolution_y = 1200
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        export_animations=True,
        export_frame_range=True,
    )
    print(
        {
            "input": str(src),
            "blend": str(blend_path),
            "animated_glb": str(glb_path),
            "vmd": str(vmd_path) if vmd_path else None,
            "vmd_status": list(vmd_status) if vmd_status else None,
            "camera_vmd": str(camera_vmd_path) if camera_vmd_path else None,
            "camera_vmd_status": list(camera_vmd_status) if camera_vmd_status else None,
            "audio": audio_added,
            "actions": [(action.name, len(action.fcurves)) for action in bpy.data.actions],
            "weight_counts": weight_counts,
            "frame_start": bpy.context.scene.frame_start,
            "frame_end": bpy.context.scene.frame_end,
        }
    )


if __name__ == "__main__":
    main()
