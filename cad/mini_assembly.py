"""Writes the models of the Mini in their places for the Parts tab of Printdeck: one STL file for each
part in cad/assembly-mini/, Z up, in millimetres, the front toward -Y. They come from the glTF files of
the design page (docs/models-mini/, Y up, in metres), which bluespeaker_mini.py writes.

Run: uv run --no-project --with trimesh --with numpy python cad/mini_assembly.py
Then make the large files smaller with the tool of the beetlebug.org repo, which keeps the shape
within 0.2 % of its size: node ../beetlebugorg/tools/simplify.mjs cad/assembly-mini
"""

from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "models-mini"
OUT = ROOT / "cad" / "assembly-mini"

# glTF Y up in metres to Z up in millimetres: turn +90 degrees about X, then scale.
FIX = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
FIX[:3, :3] *= 1000.0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for glb in sorted(SRC.glob("*.glb")):
        mesh = trimesh.load(glb, force="mesh")
        mesh.apply_transform(FIX)
        out = OUT / (glb.stem + ".stl")
        mesh.export(out)
        lo, hi = mesh.bounds
        print(f"{out.relative_to(ROOT)}: {hi[0] - lo[0]:.0f} x {hi[1] - lo[1]:.0f} x {hi[2] - lo[2]:.0f} mm, {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
