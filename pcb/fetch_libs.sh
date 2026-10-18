#!/usr/bin/env bash
# Download the KiCad footprints and 3D models that the main PCB uses into pcb/lib/.
# The project does not need the system KiCad libraries.
set -euo pipefail
cd "$(dirname "$0")"
FP="https://gitlab.com/kicad/libraries/kicad-footprints/-/raw/master"
M3D="https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/master"

PARTS=(
  "RF_Module ESP32-S3-WROOM-1"
  "Package_SO HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm"
  "Package_SO TSSOP-16_4.4x5mm_P0.65mm"
  "Package_DFN_QFN Texas_RQM0029A_VQFN-29_4x4mm_P0.4mm"
  "Package_TO_SOT_SMD SOT-583-8"
  "Inductor_SMD L_Coilcraft_XAL6030-XXX"
  "Inductor_SMD L_Coilcraft_XAL4030-XXX"
  "Inductor_SMD L_1206_3216Metric"
  "Capacitor_SMD C_0603_1608Metric"
  "Capacitor_SMD C_0805_2012Metric"
  "Capacitor_SMD C_1206_3216Metric"
  "Capacitor_SMD CP_Elec_6.3x7.7"
  "Resistor_SMD R_0603_1608Metric"
  "Button_Switch_THT SW_PUSH_6mm_H5mm"
  "Button_Switch_SMD SW_SPST_TL3342"
  "Rotary_Encoder RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm"
  "Connector_JST JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal"
  "Connector_JST JST_PH_S6B-PH-K_1x06_P2.00mm_Horizontal"
  "Connector_JST JST_XH_S3B-XH-A_1x03_P2.50mm_Horizontal"
  "Connector_JST JST_PH_S5B-PH-K_1x05_P2.00mm_Horizontal"
  "Connector_JST JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical"
  "Connector_JST JST_PH_B5B-PH-K_1x05_P2.00mm_Vertical"
  "Connector_JST JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical"
  "Connector_JST JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"
  "Package_SO TSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.7mm_Mask3.1x4.05mm_ThermalVias"
  "Connector_FFC-FPC Hirose_FH12-12S-0.5SH_1x12-1MP_P0.50mm_Horizontal"
  "MountingHole MountingHole_3.2mm_M3_Pad"
)

for entry in "${PARTS[@]}"; do
  read -r lib name <<<"$entry"
  mkdir -p "lib/$lib.pretty" "lib/3d/$lib.3dshapes"
  f="lib/$lib.pretty/$name.kicad_mod"
  [ -s "$f" ] || curl -fsSL -o "$f" "$FP/$lib.pretty/$name.kicad_mod" || { echo "MISSING footprint $lib:$name"; rm -f "$f"; }
  s="lib/3d/$lib.3dshapes/$name.step"
  if [ ! -s "$s" ]; then
    if curl -fsSL -o "$s" "$M3D/$lib.3dshapes/$name.step" && head -c 20 "$s" | grep -q ISO-10303; then :; else
      echo "no 3D model for $lib:$name"; rm -f "$s"; fi
  fi
done
echo "done"
