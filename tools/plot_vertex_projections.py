#!/usr/bin/env python3
"""Plot front, side, and top vertex projections from a dumped GLB vertex file."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def draw_projection(
    points: np.ndarray,
    axes: tuple[int, int],
    out_path: Path,
    title: str,
    size: tuple[int, int] = (900, 900),
) -> None:
    coords = points[:, axes]
    mn = coords.min(axis=0)
    mx = coords.max(axis=0)
    extent = np.maximum(mx - mn, 1e-6)
    pad = 60
    canvas = np.array(size, dtype=np.float32)
    usable = canvas - pad * 2
    scale = float(np.min(usable / extent))
    xy = (coords - mn) * scale + pad
    xy[:, 1] = size[1] - xy[:, 1]

    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([pad, pad, size[0] - pad, size[1] - pad], outline=(220, 220, 220))
    # Draw a deterministic subsample if the mesh is very dense.
    if len(xy) > 180_000:
        rng = np.random.default_rng(1234)
        xy = xy[rng.choice(len(xy), 180_000, replace=False)]
    for x, y in xy.astype(np.int32):
        if 0 <= x < size[0] and 0 <= y < size[1]:
            draw.point((int(x), int(y)), fill=(24, 24, 24))
    draw.text((16, 16), title, fill=(0, 0, 0))
    image.save(out_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vertices", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    data = np.load(args.vertices)
    points = data["vertices"]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    draw_projection(points, (0, 2), out_dir / "projection_front_xz.png", "front: X/Z")
    draw_projection(points, (1, 2), out_dir / "projection_side_yz.png", "side: Y/Z")
    draw_projection(points, (0, 1), out_dir / "projection_top_xy.png", "top: X/Y")

    report = {
        "vertices": int(points.shape[0]),
        "bounds_min": points.min(axis=0).tolist(),
        "bounds_max": points.max(axis=0).tolist(),
        "extent": (points.max(axis=0) - points.min(axis=0)).tolist(),
    }
    print(report)


if __name__ == "__main__":
    main()
