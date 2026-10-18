#!/usr/bin/env python3
"""Make OrcaSlicer profiles for the LulzBot TAZ Workhorse SE 0.5 mm (Klipper).

The process profiles are translations of the Cura 5.13 profiles in
~/.local/share/cura/5.13/quality_changes. A setting that a Cura profile
does not set takes the value from the Cura Workhorse definition.

Usage:
    python3 orca/make_profiles.py            # write the profiles to orca/profiles/
    python3 orca/make_profiles.py --install  # also copy them into OrcaSlicer (close Orca first)

The OctoPrint API key is read from the Cura config only at install time. The
files in orca/profiles/ do not contain it.
"""

import argparse
import base64
import configparser
import glob
import json
import math
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "profiles"
ORCA_RES = Path("/opt/orca-slicer/resources/profiles")
ORCA_USER = Path.home() / ".config/OrcaSlicer/user/default"
CURA = Path.home() / ".local/share/cura/5.13"
VERSION = "2.4.2.0"

PRINTER = "LulzBot TAZ Workhorse SE 0.5 (Klipper)"
BASE_PRINTER = "MyKlipper 0.4 nozzle"
# Orca's command line checks a profile against the printer's system parent, so list both names.
COMPATIBLE = [PRINTER, BASE_PRINTER]
LINE = 0.5  # nozzle and line width

# Cura Workhorse definition defaults (lulzbot_taz_workhorse_se.def.json and fdmprinter)
CURA_DEFAULTS = dict(
    layer_height="0.2", layer_height_0="0.425", wall_thickness="1.0", top_bottom_thickness="1.0",
    infill_sparse_density="20", infill_pattern="grid", speed_print="40", speed_infill="40", speed_wall_0="30",
    speed_wall_x="30", speed_topbottom="30", speed_layer_0="15", speed_travel="175", speed_support="40",
    speed_slowdown_layers="2", adhesion_type="skirt", brim_line_count="10", skirt_line_count="2", skirt_gap="3",
    support_enable="False", support_angle="60", z_seam_type="shortest", material_print_temperature="215",
    material_print_temperature_layer_0="215",
)

# Profiles to translate: Cura profile name -> (Orca name, filament, note)
PROFILES = {
    "Bluedeck - PLA 0.25": ("Bluedeck - PLA 0.25", "230", "Bluedeck parts"),
    "Bluespeaker Mini - PLA Shell 0.25": ("Bluespeaker Mini - Shell 0.25", "230s", "sleeve.stl, supports under the front posts"),
    "Bluespeaker Mini - PLA Parts 0.25": ("Bluespeaker Mini - Parts 0.25", "230",
                                          "baffle, rear panel, tray, strip, knob, feet. No supports: drill the pilot holes"),
    "Bluespeaker Mini - PLA Grille 0.25": ("Bluespeaker Mini - Grille 0.25", "230", "lattice grille, one line per rib"),
    "Speakerdeck - Base PLA 0.3": ("Speakerdeck - Base 0.3", "220", ""),
    "Speakerdeck - Body PLA 0.4": ("Speakerdeck - Body 0.4", "230", ""),
    "Speakerdeck - Display Panel PLA 0.3": ("Speakerdeck - Display Panel 0.3", "220", ""),
    "Speakerdeck - Lid PLA 0.3": ("Speakerdeck - Lid 0.3", "220", ""),
    "Speakerdeck - Lower Panel PLA 0.3": ("Speakerdeck - Lower Panel 0.3", "220", ""),
    "Workhorse SE - Fine 0.1": ("Workhorse SE - Fine 0.10", "230", ""),
    "Workhorse SE - Standard 0.2": ("Workhorse SE - Standard 0.20", "230", ""),
    "Workhorse SE - High Speed 0.3": ("Workhorse SE - High Speed 0.30", "230", ""),
    "Workhorse SE - Shell": ("Workhorse SE - Shell 0.30", "230", ""),
}

FILAMENTS = {
    "230": ("Workhorse PLA 2.85 - 230", "230", "220"),
    # large solid shells: less fan, so the first layers do not shrink and lift the corners
    "230s": ("Workhorse PLA 2.85 - 230 Shell", "230", "220"),
    "220": ("Workhorse PLA 2.85 - 220", "220", "215"),
}

START_GCODE = (
    "; Klipper start: wipe, washer probe, and prime line run in the PRINT_START macro\n"
    "PRINT_START BED=[bed_temperature_initial_layer_single] EXTRUDER=[nozzle_temperature_initial_layer] "
    "WIPE=160 LAYER=[initial_layer_print_height] SPEED=[initial_layer_speed]\n"
    "M117 [input_filename_base]\n"
)
END_GCODE = "; Klipper end\nPRINT_END\n"


# ------------------------------------------------------------------------ helpers


def cura_profiles():
    """Merge each Cura quality_changes pair (global + extruder) into one dict per profile name."""
    prof = {}
    for f in sorted(glob.glob(str(CURA / "quality_changes" / "*.inst.cfg"))):
        c = configparser.ConfigParser(interpolation=None)
        c.read(f)
        prof.setdefault(c["general"]["name"], {}).update(dict(c["values"]))
    return prof


def num(v):
    return float(str(v).strip().strip("'\""))


def f2(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")


def orca_keys():
    keys = set()
    for f in ORCA_RES.rglob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        if isinstance(d, dict):
            keys |= set(d)
    return keys


# ------------------------------------------------------------------- translations


def machine_preset():
    return {
        "type": "machine", "name": PRINTER, "printer_settings_id": PRINTER, "from": "User",
        "inherits": BASE_PRINTER, "version": VERSION, "printer_variant": "0.5",
        "nozzle_diameter": ["0.5"], "printable_area": ["0x0", "280x0", "280x280", "0x280"], "printable_height": "285",
        "gcode_flavor": "klipper", "use_relative_e_distances": "1", "use_firmware_retraction": "0",
        "machine_start_gcode": START_GCODE, "machine_end_gcode": END_GCODE, "machine_pause_gcode": "PAUSE",
        # [printer] in printer.cfg: max_velocity 300, max_accel 3000, max_z_velocity 25, max_z_accel 100
        "machine_max_speed_x": ["300", "300"], "machine_max_speed_y": ["300", "300"],
        "machine_max_speed_z": ["25", "25"], "machine_max_speed_e": ["40", "40"],
        "machine_max_acceleration_x": ["3000", "3000"], "machine_max_acceleration_y": ["3000", "3000"],
        "machine_max_acceleration_z": ["100", "100"], "machine_max_acceleration_e": ["1000", "1000"],
        "machine_max_acceleration_extruding": ["3000", "3000"], "machine_max_acceleration_retracting": ["1000", "1000"],
        "machine_max_acceleration_travel": ["3000", "3000"],
        # Orca uses the jerk only for its time estimate. Klipper corners at square_corner_velocity 5.
        "machine_max_jerk_x": ["5", "5"], "machine_max_jerk_y": ["5", "5"],
        "max_layer_height": ["0.4"], "min_layer_height": ["0.08"],
        # retraction from the Cura profiles (most of them): 1.5 mm at 15 mm/s, at layer change, 3 mm min travel
        "retraction_length": ["1.5"], "retraction_speed": ["15"], "deretraction_speed": ["15"],
        "retract_when_changing_layer": ["1"], "retraction_minimum_travel": ["3"], "z_hop": ["0"], "wipe": ["0"],
        "default_filament_profile": [FILAMENTS["230"][0]], "default_print_profile": "Workhorse SE - Standard 0.20",
        "host_type": "octoprint", "print_host": "http://192.168.76.110", "printhost_apikey": "",
    }


def filament_preset(key):
    name, temp, temp0 = FILAMENTS[key]
    bed = "60"
    p = {
        "type": "filament", "name": name, "filament_settings_id": [name], "from": "User",
        "inherits": "Generic PLA @System", "version": VERSION, "compatible_printers": COMPATIBLE,
        "filament_diameter": ["2.85"],
        "nozzle_temperature": [temp], "nozzle_temperature_initial_layer": [temp0],
        "hot_plate_temp": [bed], "hot_plate_temp_initial_layer": [bed],
        "textured_plate_temp": [bed], "textured_plate_temp_initial_layer": [bed],
        "cool_plate_temp": [bed], "cool_plate_temp_initial_layer": [bed],
        "eng_plate_temp": [bed], "eng_plate_temp_initial_layer": [bed],
        # printer.cfg: the measured melt rate limit is 15 mm3/s
        "filament_max_volumetric_speed": ["15"],
        "fan_min_speed": ["100"], "fan_max_speed": ["100"], "close_fan_the_first_x_layers": ["1"],
        "slow_down_layer_time": ["12"],
        # Cura material_shrinkage_percentage_xy = 100.3
        "filament_shrink": ["100.3%"],
    }
    if key.endswith("s"):
        # Full fan on a 3 mm solid wall cools each layer fast. The layers then shrink and pull the
        # corners of the first layers up. No fan for 4 layers, then 40 %. Overhangs still get 100 %.
        p.update({"close_fan_the_first_x_layers": ["4"], "fan_min_speed": ["30"], "fan_max_speed": ["40"],
                  "enable_overhang_bridge_fan": ["1"], "overhang_fan_speed": ["100"], "overhang_fan_threshold": ["25%"]})
    return p


def process_preset(cura_name, c):
    name, fil, note = PROFILES[cura_name]
    v = {**CURA_DEFAULTS, **c}
    lh = num(v["layer_height"])
    walls = max(1, round(num(v["wall_thickness"]) / LINE))
    if "wall_line_count" in v:
        walls = int(num(v["wall_line_count"]))
    tb = num(v["top_bottom_thickness"])
    shells = 0 if tb == 0 else max(1, math.ceil(tb / lh - 1e-6))
    density = num(v["infill_sparse_density"])
    pattern = {"grid": "grid", "gyroid": "gyroid", "lines": "line", "zigzag": "zig-zag", "triangles": "triangles",
               "cubic": "cubic"}.get(v["infill_pattern"].strip("'\""), "grid")
    sp_print = num(v["speed_print"])
    p = {
        "type": "process", "name": name, "print_settings_id": name, "from": "User",
        "inherits": "0.20mm Standard @MyKlipper", "version": VERSION,
        "compatible_printers": COMPATIBLE, "compatible_printers_condition": "",
        "layer_height": f2(lh), "initial_layer_print_height": f2(num(v["layer_height_0"])),
        "line_width": f2(LINE), "outer_wall_line_width": f2(LINE), "inner_wall_line_width": f2(LINE),
        "sparse_infill_line_width": f2(LINE), "internal_solid_infill_line_width": f2(LINE),
        "top_surface_line_width": f2(LINE), "support_line_width": f2(LINE),
        "initial_layer_line_width": f2(LINE * num(v.get("initial_layer_line_width_factor", "100")) / 100),
        "wall_loops": str(walls), "top_shell_layers": str(shells), "bottom_shell_layers": str(shells),
        "top_shell_thickness": f2(tb), "bottom_shell_thickness": f2(tb),
        "sparse_infill_density": f"{density:g}%", "sparse_infill_pattern": pattern,
        "outer_wall_speed": f2(num(v.get("speed_wall_0", sp_print))),
        "inner_wall_speed": f2(num(v.get("speed_wall_x", sp_print))),
        "sparse_infill_speed": f2(num(v.get("speed_infill", sp_print))),
        "internal_solid_infill_speed": f2(num(v.get("speed_infill", sp_print))),
        "top_surface_speed": f2(num(v.get("speed_topbottom", sp_print))),
        "gap_infill_speed": f2(num(v.get("speed_wall_x", sp_print))),
        "initial_layer_speed": f2(num(v["speed_layer_0"])), "initial_layer_infill_speed": f2(num(v["speed_layer_0"])),
        "travel_speed": f2(num(v["speed_travel"])),
        "support_speed": f2(num(v.get("speed_support", sp_print))),
        "support_interface_speed": f2(num(v.get("speed_support_interface", v.get("speed_support", sp_print)))),
        "bridge_speed": f2(num(v.get("bridge_wall_speed", "25"))),
        "slow_down_layers": str(int(num(v["speed_slowdown_layers"]))),
        "wall_generator": "arachne", "detect_thin_wall": "1", "exclude_object": "1", "gcode_label_objects": "1",
        "enable_arc_fitting": "1",
        # Cura sent no acceleration commands, so Klipper used max_accel (3000) everywhere.
        # Keep 3000, but slow the outer walls, the top surface, and the first layer a little.
        "default_acceleration": "3000", "travel_acceleration": "3000", "inner_wall_acceleration": "3000",
        "outer_wall_acceleration": "2000", "top_surface_acceleration": "2000", "initial_layer_acceleration": "1000",
        # Klipper replaces ACCEL_TO_DECEL with minimum_cruise_ratio; do not send it
        "accel_to_decel_enable": "0",
    }
    # adhesion
    adh = v["adhesion_type"].strip("'\"")
    if adh == "brim":
        p["brim_type"] = "inner_only" if v.get("brim_location") == "inside" else "outer_only"
        p["brim_width"] = f2(num(v["brim_line_count"]) * LINE)
        p["skirt_loops"] = "0"
    else:
        p["brim_type"] = "no_brim"
        p["skirt_loops"] = str(int(num(v["skirt_line_count"])))
        p["skirt_distance"] = f2(num(v["skirt_gap"]))
    # supports: Cura support_angle is from vertical; Orca's threshold is from horizontal. Use organic trees.
    if v["support_enable"] == "True":
        p.update({"enable_support": "1", "support_type": "tree(auto)", "support_style": "organic",
                  "support_threshold_angle": str(int(90 - num(v["support_angle"]))),
                  "support_on_build_plate_only": "1" if v.get("support_type") == "buildplate" else "0",
                  "support_top_z_distance": f2(num(v.get("support_z_distance", "0.25"))),
                  "support_object_xy_distance": f2(num(v.get("support_xy_distance", "0.8")))})
    else:
        p["enable_support"] = "0"
    # seam
    seam = v["z_seam_type"].strip("'\"")
    p["seam_position"] = {"back": "back", "sharpest_corner": "aligned", "shortest": "nearest",
                          "random": "random"}.get(seam, "aligned")
    # first layer
    if "xy_offset_layer_0" in v:
        p["elefant_foot_compensation"] = f2(-num(v["xy_offset_layer_0"]))
    if "small_feature_speed_factor" in v:
        p["small_perimeter_speed"] = f"{num(v['small_feature_speed_factor']):g}%"
    # sleeves print front opening down: compensate the elephant foot of the first layers
    if name.endswith(("Shell 0.25", "Shell 0.30")):
        p["elefant_foot_compensation"] = "0.15"
    # the Mini sleeve: a brim on both sides of the 3 mm front rim holds the corners down
    if name == "Bluespeaker Mini - Shell 0.25":
        p.update({"brim_type": "outer_and_inner", "brim_width": "6", "brim_object_gap": "0", "skirt_loops": "0"})
    # lattice grille: one line per rib, no wall wipe, plain bridges
    if "Grille" in name:
        p.update({"thick_bridges": "0", "min_bead_width": "60%", "min_feature_size": "20%",
                  "reduce_crossing_wall": "0", "only_one_wall_first_layer": "0"})
    p["notes"] = f"From Cura profile '{cura_name}'. Use filament '{FILAMENTS[fil][0]}'. {note}".strip()
    return p


# ------------------------------------------------------------------------- output


def info_text():
    return f"sync_info = \nuser_id = \nsetting_id = \nbase_id = \nupdated_time = {int(time.time())}\n"


def safe(name):
    return re.sub(r"[/\\]", "-", name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()

    presets = {"machine": [machine_preset()], "filament": [filament_preset(k) for k in FILAMENTS], "process": []}
    cura = cura_profiles()
    for cura_name in PROFILES:
        if cura_name not in cura:
            print(f"WARNING: Cura profile '{cura_name}' not found")
            continue
        presets["process"].append(process_preset(cura_name, cura[cura_name]))

    # validate the keys against the keys that Orca's own profiles use
    known = orca_keys() | {"notes", "compatible_printers_condition", "printhost_apikey", "print_host", "host_type",
                           "accel_to_decel_enable"}
    bad = sorted({k for group in presets.values() for pr in group for k in pr if k not in known})
    if bad:
        print("WARNING: keys not found in Orca's profiles:", ", ".join(bad))

    for kind, group in presets.items():
        (OUT / kind).mkdir(parents=True, exist_ok=True)
        for pr in group:
            (OUT / kind / f"{safe(pr['name'])}.json").write_text(json.dumps(pr, indent=4) + "\n")
    print(f"wrote {sum(len(g) for g in presets.values())} profiles to {OUT}")

    if args.install:
        key = ""
        for f in glob.glob(str(CURA / "machine_instances" / "*.global.cfg")):
            m = re.search(r"^octoprint_api_key\s*=\s*(\S+)", Path(f).read_text(), re.M)
            if m:
                # the Cura OctoPrint plugin (3.x) keeps the key base64-encoded
                key = base64.b64decode(m.group(1)).decode()
        for kind, group in presets.items():
            d = ORCA_USER / kind
            d.mkdir(parents=True, exist_ok=True)
            for pr in group:
                pr = dict(pr)
                if kind == "machine" and key:
                    pr["printhost_apikey"] = key
                (d / f"{safe(pr['name'])}.json").write_text(json.dumps(pr, indent=4) + "\n")
                (d / f"{safe(pr['name'])}.info").write_text(info_text())
        print(f"installed into {ORCA_USER} (OctoPrint key {'found' if key else 'NOT found'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
