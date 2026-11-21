"""Write the flat X2D presets of the Mini from the BBL presets of an OrcaSlicer source tree.

Run: python profiles/bambu-x2d/make_profiles.py <OrcaSlicer>/resources/profiles/BBL
"""
import json
import sys
from pathlib import Path

MACHINE = "Bambu Lab X2D 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL X2D"
FILAMENT = "Bambu PLA Basic @BBL X2D 0.4 nozzle"
COLORS = (("filament_gray", "Mini X2D PLA Gray", "#8E9089"), ("filament_white", "Mini X2D PLA White", "#FFFFFF"))
PROCESS_CHANGES = dict(
    name="Mini X2D 0.20 Inlay", compatible_printers=[MACHINE], wall_loops="4", sparse_infill_density="40%",
    bottom_shell_layers="3", top_shell_layers="4", brim_type="outer_only", brim_width="3",
    enable_prime_tower="1", enable_support="0", wall_generator="arachne", min_bead_width="50%",
    min_feature_size="20%", detect_thin_wall="1", elefant_foot_compensation="0",
)


def index(src):
    out = {}
    for kind in ("machine", "process", "filament"):
        for path in (src / kind).rglob("*.json"):
            try:
                data = json.loads(path.read_text())
            except ValueError:
                continue
            if isinstance(data, dict) and "name" in data:
                out[kind, data["name"]] = data
    return out


def flat(presets, kind, name):
    data = presets[kind, name]
    base = flat(presets, kind, data["inherits"]) if data.get("inherits") else {}
    base.update(data)
    return base


def user_preset(data, **changes):
    out = {**data, **changes, "from": "User", "inherits": ""}
    out.pop("setting_id", None)
    out.pop("instantiation", None)
    return out


def main():
    presets = index(Path(sys.argv[1]))
    here = Path(__file__).parent
    files = {
        "machine": user_preset(flat(presets, "machine", MACHINE)),
        "process": user_preset(flat(presets, "process", PROCESS), **PROCESS_CHANGES),
    }
    base = flat(presets, "filament", FILAMENT)
    for stem, name, color in COLORS:
        files[stem] = user_preset(base, name=name, filament_colour=[color], default_filament_colour=[color],
                                  compatible_printers=[MACHINE])
    for stem, data in files.items():
        (here / f"{stem}.json").write_text(json.dumps(data, indent=1) + "\n")
        print(stem, len(data))


if __name__ == "__main__":
    main()
