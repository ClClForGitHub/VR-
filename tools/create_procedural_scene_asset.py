"""Create lightweight procedural scene GLBs for runtime smoke/demo assembly.

Run inside Blender:

    blender -b --python tools/create_procedural_scene_asset.py -- \
      --scene-type moon_surface --output /path/to/scene.glb
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def _mat(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    return material


def _terrain_height(x: float, y: float) -> float:
    z = 0.025 * math.sin(2.1 * x + 0.7) + 0.018 * math.cos(2.7 * y - 0.4)
    craters = [
        (-2.7, -1.4, 0.85, 0.18),
        (-1.0, 1.6, 0.55, 0.12),
        (1.35, -0.95, 0.72, 0.16),
        (2.5, 1.1, 0.48, 0.10),
        (0.15, 2.55, 0.62, 0.13),
    ]
    for cx, cy, radius, depth in craters:
        dist = math.hypot(x - cx, y - cy)
        if dist < radius:
            t = dist / radius
            bowl = (1.0 - t * t) * depth
            rim = 0.04 * math.exp(-((dist - radius * 0.92) ** 2) / (radius * 0.09))
            z -= bowl
            z += rim
    return z


def _create_moon_surface(output: Path) -> None:
    _clear_scene()
    terrain_mat = _mat("lunar_regolith_gray", (0.46, 0.45, 0.42, 1.0))
    rim_mat = _mat("raised_crater_rims", (0.58, 0.57, 0.53, 1.0))
    rock_mat = _mat("small_lunar_rocks", (0.34, 0.34, 0.32, 1.0))

    size = 8.0
    divisions = 88
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for iy in range(divisions + 1):
        y = -size / 2.0 + size * iy / divisions
        for ix in range(divisions + 1):
            x = -size / 2.0 + size * ix / divisions
            verts.append((x, y, _terrain_height(x, y)))
    row = divisions + 1
    for iy in range(divisions):
        for ix in range(divisions):
            a = iy * row + ix
            faces.append((a, a + 1, a + row + 1, a + row))

    mesh = bpy.data.meshes.new("moon_surface_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    terrain = bpy.data.objects.new("moon_surface_cratered_regolith", mesh)
    bpy.context.collection.objects.link(terrain)
    terrain.data.materials.append(terrain_mat)

    crater_specs = [
        (-2.7, -1.4, 0.85),
        (-1.0, 1.6, 0.55),
        (1.35, -0.95, 0.72),
        (2.5, 1.1, 0.48),
        (0.15, 2.55, 0.62),
    ]
    for idx, (x, y, radius) in enumerate(crater_specs):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=radius,
            minor_radius=0.018,
            major_segments=80,
            minor_segments=8,
            location=(x, y, _terrain_height(x, y) + 0.035),
        )
        rim = bpy.context.object
        rim.name = f"crater_rim_{idx:02d}"
        rim.data.materials.append(rim_mat)

    rock_positions = [
        (-3.2, 1.2, 0.13),
        (-2.0, 2.5, 0.09),
        (-0.55, -2.6, 0.12),
        (0.9, 2.0, 0.10),
        (2.8, -2.2, 0.15),
        (3.1, 0.35, 0.08),
    ]
    for idx, (x, y, scale) in enumerate(rock_positions):
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=2,
            radius=scale,
            location=(x, y, _terrain_height(x, y) + scale * 0.45),
        )
        rock = bpy.context.object
        rock.name = f"lunar_rock_{idx:02d}"
        rock.scale.x *= 1.35
        rock.scale.y *= 0.8
        rock.data.materials.append(rock_mat)

    bpy.ops.object.light_add(type="SUN", location=(0, -3, 5))
    sun = bpy.context.object
    sun.name = "low_hard_sun"
    sun.data.energy = 2.4
    sun.rotation_euler = (math.radians(48), 0.0, math.radians(26))

    bpy.ops.object.camera_add(location=(0.0, -6.0, 3.0), rotation=(math.radians(62), 0.0, 0.0))
    bpy.context.scene.camera = bpy.context.object
    bpy.context.scene.world.color = (0.02, 0.02, 0.025)

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-type", choices=["moon_surface"], required=True)
    parser.add_argument("--output", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)

    if args.scene_type == "moon_surface":
        _create_moon_surface(Path(args.output).expanduser().resolve())


if __name__ == "__main__":
    main()
