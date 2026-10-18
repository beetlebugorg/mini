"""Make the 3D models that the KiCad libraries do not have.

KiCad 3D model coordinates: X right, Y up (KiCad -Y), Z up from the top of the board.
Run with the uv environment:  uv run pcb/make_models.py
"""
from pathlib import Path

from build123d import Box, Cylinder, Pos, export_step, fillet, Axis, Align

OUT = Path(__file__).resolve().parent / "lib" / "3d" / "generated"
OUT.mkdir(parents=True, exist_ok=True)
MIN = (Align.CENTER, Align.CENTER, Align.MIN)

# Feasycom FSC-BT1026D: 13 x 26.9 mm PCB 0.8 mm, shield can on the lower 17 mm, antenna area at the top.
pcb = Box(13.0, 26.9, 0.8, align=MIN)
can = Pos(0, -4.4, 0.8) * Box(12.2, 17.0, 1.4, align=MIN)
can = fillet(can.edges().filter_by(Axis.Z), 0.6)
bt = pcb + can
export_step(bt, OUT / "Feasycom_FSC-BT1026D.step")

# TI RQM VQFN-29, 4 x 4 x 1.0 mm (BQ25792)
qfn = Box(4.0, 4.0, 0.9, align=MIN)
qfn = qfn - Pos(-1.4, 1.4, 0.88) * Cylinder(0.3, 0.1, align=MIN)  # pin 1 mark
export_step(qfn, OUT / "VQFN-29_4x4mm.step")
print("models ok")
