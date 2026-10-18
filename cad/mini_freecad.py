# Bluespeaker Mini: a FreeCAD document with the STEP parts and TechDraw pages, to open and edit in FreeCAD.
#
#   uv run cad/mini_report.py --step          # write cad/step-mini/ first
#   freecadcmd cad/mini_freecad.py            # writes cad/bluespeaker_mini.FCStd
#
# The script only makes the objects. FreeCAD computes the drawing views when you open the file.
# The released drawings (with dimensions and sections) come from cad/mini_drawings.py.

import json
import os
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(os.environ.get("BLUESPEAKER_ROOT", Path.home() / "Projects" / "bluespeaker"))
STEP = ROOT / "cad" / "step-mini"
TEMPLATE = "/usr/share/freecad/Mod/TechDraw/Templates/ISO/A3_Landscape_ISO5457_advanced.svg"
V = App.Vector

meta = json.loads((STEP / "parts.json").read_text())
doc = App.newDocument("BluespeakerMini")
grp_printed = doc.addObject("App::DocumentObjectGroup", "Printed")
grp_bought = doc.addObject("App::DocumentObjectGroup", "Bought")
objs = {}
for x in meta:
    o = doc.addObject("Part::Feature", x["name"])
    o.Shape = Part.read(str(STEP / f"{x['name']}.step"))
    o.Label = x["label"]
    (grp_printed if x["printed"] else grp_bought).addObject(o)
    objs[x["name"]] = o
    if App.GuiUp:
        o.ViewObject.ShapeColor = tuple(int(x["color"][i:i + 2], 16) / 255 for i in (1, 3, 5))

import TechDraw  # noqa: E402,F401  (registers the TechDraw types)

n = 0
for x in meta:
    if not x["printed"]:
        continue
    n += 1
    page = doc.addObject("TechDraw::DrawPage", f"Sheet_{x['name']}")
    page.Label = f"BSM-{n:02d} {x['label']}"
    tpl = doc.addObject("TechDraw::DrawSVGTemplate", f"Template_{x['name']}")
    tpl.Template = TEMPLATE
    page.Template = tpl
    texts = dict(tpl.EditableTexts)
    texts.update({"title": "Bluespeaker Mini", "supplementary_title_1": x["label"], "drawing_number": f"BSM-{n:02d}",
                  "revision_index": "0.3", "date_of_issue": "2026-10-11", "scale": "1:1", "general_tolerances": "±0.2 mm",
                  "part_material": "PLA", "creator": "build123d model", "language_code": "en"})
    tpl.EditableTexts = texts
    page.KeepUpdated = False  # compute the views when you open the page and press Recompute
    group = doc.addObject("TechDraw::DrawProjGroup", f"Views_{x['name']}")
    page.addView(group)
    group.ProjectionType = "Third angle"
    group.Source = [objs[x["name"]]]
    group.X, group.Y = 140, 170
    group.ScaleType = "Custom"
    group.Scale = 1.0
    for proj in ("Front", "Top", "Right"):
        group.addProjection(proj)
    group.Anchor.Direction = V(0, -1, 0)
    group.Anchor.XDirection = V(1, 0, 0)

out = ROOT / "cad" / "bluespeaker_mini.FCStd"
doc.saveAs(str(out))
print("wrote", out)
os._exit(0)
