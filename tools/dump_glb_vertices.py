#!/usr/bin/env python3
"""Dump mesh vertex coordinates from a GLB inside Blender Python."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)

    src = Path(args.input)
    dst = Path(args.output)
    dst.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    bpy.ops.import_scene.gltf(filepath=str(src))

    vertices = []
    faces = 0
    mesh_names = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        mesh_names.append(obj.name)
        faces += len(obj.data.polygons)
        matrix = obj.matrix_world
        vertices.extend(tuple(matrix @ vertex.co) for vertex in obj.data.vertices)

    arr = np.asarray(vertices, dtype=np.float32)
    np.savez_compressed(dst, vertices=arr, faces=np.asarray([faces], dtype=np.int64))
    print(f"saved={dst} vertices={arr.shape[0]} faces={faces} meshes={mesh_names}")


if __name__ == "__main__":
    main()
