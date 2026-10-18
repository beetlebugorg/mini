#!/usr/bin/env bash
# Build the main PCB from netlist.py, check it, and export STEP files and renders.
#   pcb/export.sh
# Outputs in pcb/out/:
#   board.step       board body only (origin at the board centre)
#   parts.step       component 3D models only
#   bluespeaker.step board and components
#   erc.json, drc.json, top.png, bottom.png, iso.png
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
python3 build.py 2>&1 | grep -v "assert"
kicad-cli sch erc --format json -o out/erc.json bluespeaker.kicad_sch >/dev/null
kicad-cli pcb drc --schematic-parity --format json -o out/drc.json bluespeaker.kicad_pcb >/dev/null
python3 - <<'PY'
import json
e = json.load(open("out/erc.json")); d = json.load(open("out/drc.json"))
erc = sum(len(s["violations"]) for s in e["sheets"])
err = sum(v["severity"] == "error" for v in d["violations"])
print(f"ERC violations: {erc}   DRC errors: {err}   DRC warnings: {len(d['violations']) - err}   "
      f"unrouted: {len(d['unconnected_items'])}   schematic parity: {len(d['schematic_parity'])}")
PY
O="--user-origin 212x123mm --subst-models --force"
kicad-cli pcb export step $O --board-only -o out/board.step bluespeaker.kicad_pcb 2>&1 | grep -v assert | tail -1
kicad-cli pcb export step $O --no-board-body -o out/parts.step bluespeaker.kicad_pcb 2>&1 | grep -v assert | tail -1
kicad-cli pcb export step $O -o out/bluespeaker.step bluespeaker.kicad_pcb 2>&1 | grep -v assert | tail -1
R="--quality high --background opaque"
kicad-cli pcb render --side top --width 2400 --height 560 --zoom 3.6 $R -o out/top.png bluespeaker.kicad_pcb 2>&1 | grep -v assert | tail -1
kicad-cli pcb render --side bottom --width 2400 --height 560 --zoom 3.6 $R -o out/bottom.png bluespeaker.kicad_pcb 2>&1 | grep -v assert | tail -1
kicad-cli pcb render --side top --rotate "-50,0,25" --perspective --width 1800 --height 900 --zoom 2.2 $R -o out/iso.png bluespeaker.kicad_pcb 2>&1 | grep -v assert | tail -1
