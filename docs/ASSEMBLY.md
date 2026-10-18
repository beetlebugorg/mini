# Bluespeaker — assembly instructions

Revision 0.1 · 2026-10-07 · Model: `cad/bluespeaker.py`

Each step has a "Show in 3D" button on the design site. The 3D viewer then
shows the parts for that step and moves the new parts into position.

## Safety

> **WARNING:** The battery pack holds about 50 Wh. A short circuit can cause
> a fire. Keep metal tools away from the pack terminals. Do not puncture,
> crush, or bend the cells. Connect the battery lead only in step 5.

> **CAUTION:** A heat-set insert tool is at about 245 °C. Do not touch the tip.
> Use the tool in an area with a flow of air.

## Tools

- Soldering iron with an M3 heat-set insert tip
- Hex keys or drivers for M3 and M2.5 screws (countersunk and pan head)
- Flush cutters and a deburring tool
- Two-part epoxy (5 minute), CA glue, and 0.2 mm double-sided tape
- Isopropyl alcohol and lint-free cloth

## Hardware

| Item | Qty | Where |
|---|---|---|
| M3 heat-set insert, 5.7 mm long (for a 4.0 mm hole) | 34 | Sleeve 11, baffle 12, bay wall 3, rear panel 8 |
| M3 × 10 countersunk screw | 14 | Baffle to sleeve 5, baffle to bay wall 3, rear panel 6 |
| M3 × 6 pan head screw | 20 | Drivers 8, radiators 8, main PCB 4 |
| M2.5 × 6 pan head thread-forming screw | 8 | LCD carrier 4, encoder board 2, USB-C port board 2 |
| Magnet, 6 × 2 mm, N52 | 8 | Baffle front |
| Magnet, 6 × 1 mm, N52 | 8 | Grille 4, control strip 4 |
| Closed-cell foam tape, 3 × 6 mm | 1.5 m | Driver and radiator flanges |
| Hook-and-loop strap, 10 mm wide | 2 | Battery |
| Acoustic felt, 10 mm | 0.15 m² | Inner walls of the sleeve |
| Polyester fill | 30 g | Behind the drivers |

## Bought parts

| Item | Qty |
|---|---|
| Dayton Audio ND90-4 full-range driver | 2 |
| Dayton Audio ND90-PR passive radiator (with weights) | 2 |
| 3S1P 21700 stick pack with protection board, NTC, and lead | 1 |
| 2.4 in IPS LCD module, 320 × 240, with capacitive touch | 1 |
| Main PCB, assembled, with tact switches (`pcb/bluespeaker.kicad_pcb`) | 1 |
| Encoder board, 22 × 22 mm, with an EC11E encoder (20 mm D-shaft) | 1 |
| Encoder lead, 5 wires, 120 mm, with a JST-PH plug | 1 |
| USB-C port board, assembled | 1 |
| Speaker leads, 2 × 0.5 mm², with JST-PH plugs, 120 mm | 2 |
| USB-C cable lead, 6 wires, 180 mm, with plugs | 1 |
| Smoked acrylic window, 61.6 × 43.6 × 1.5 mm | 1 |

The battery lead must carry 3 A. Use a JST-XH or a larger connector for
the battery. JST-PH is rated for 2 A.

## Printed parts

The export writes these files to `cad/stl/`. Each file is already in its
print orientation, centred, and on the bed (Z = 0). Do not turn the parts in
the slicer. To write only the STL files, run `uv run cad/bluespeaker.py --stl`.

| File | Qty | Process | Orientation and notes |
|---|---|---|---|
| `sleeve.stl` | 1 | FDM, PETG or ASA | Front opening down. Add supports below the five front posts only. 6 walls. |
| `baffle.stl` | 1 | FDM or resin | Front face down. No supports. 100 % infill. |
| `rear_panel.stl` | 1 | FDM or resin | Outer face down. No supports. 100 % infill. |
| `bay_wall.stl` | 1 | FDM, PETG | Rear face of the wall down. No supports. |
| `brace.stl` | 1 | FDM | Flat. |
| `grille.stl` | 1 | Resin preferred | Front face down. FDM: 0.4 mm nozzle, 0.15 mm layers. |
| `control_strip.stl` | 1 | FDM or resin | Front face down. |
| `key_prev.stl`, `key_next.stl` | 1 each | Resin | Cap up. Grey. |
| `key_play.stl` | 1 | Resin | Cap up. Orange. |
| `knob.stl` | 1 | Resin preferred | Front face up. |
| `knob_mark.stl` | 1 | Resin | Orange. |
| `feet.stl` | 1 set (4) | FDM, TPU | Flat. |

Before you start, do these steps on all printed parts:

1. Remove the supports and the brim.
2. Sand the visible faces to 320 grit.
3. Apply filler primer, then matt off-white paint. Paint the control strip silver.
4. Do not paint the insert holes or the magnet pockets.

## Step 1 — Prepare the sleeve

1. Remove the supports below the five front posts.
2. Install the 11 inserts in the sleeve posts: 5 at the front, 6 at the rear.
   1. Set the iron to 245 °C for PETG or 255 °C for ASA.
   2. Put the insert on the hole and push it straight down with the hot tip.
   3. Stop when the insert is flush with the post face.
3. Apply epoxy in the two brace pockets. Put the brace in the pockets. Hold
   it for 10 minutes.
4. Glue the four feet into the recesses on the bottom with CA glue.
5. Line the top, the side walls, and the rear half of the floor with felt.
   Keep the first 15 mm at each end of the sleeve clear.

## Step 2 — Mount the drivers on the baffle

1. Install 8 inserts in the two spacer frames on the back of the baffle.
2. Install 4 inserts in the four tall bosses below the drivers. These hold
   the main PCB.
3. Apply foam tape to the front face of each driver flange. Keep the four
   holes clear.
4. Put each driver on its spacer frame from the back. Turn the terminals
   toward the centre of the baffle.
5. Install four M3 × 6 pan head screws in each driver. Tighten them in a
   diagonal order. Stop when the foam is compressed by half.

## Step 3 — Fit the keys, the LCD, and the encoder board

1. Push the three keys through the baffle from the back. The orange key goes
   in the centre hole.
2. Put the LCD module on the four short posts. The glass goes into the
   opening, and the flat cable is on the right.
3. Install four M2.5 × 6 thread-forming screws. Stop when the screw head
   touches the carrier PCB. More torque strips the posts.
4. Put the encoder body into the square pocket at the knob position. The
   encoder board lies flat on the back of the baffle.
5. Install two M2.5 × 6 thread-forming screws through the encoder board.

## Step 4 — Fit the main PCB

1. Connect the LCD flat cable to the connector on the front face of the
   main PCB.
2. Put the main PCB on the four tall bosses. The switches face the baffle.
3. Put the encoder lead over the top edge of the PCB. Connect it to J6 on
   the rear face.
4. Install four M3 × 6 pan head screws.
5. Push each key. Make sure that each switch clicks.

## Step 5 — Fit the bay wall and the battery

1. Install 3 inserts in the three tabs on top of the bay wall shelf.
2. Put the battery pack in the three saddles. The protection board goes to
   the left end (seen from the front), near the battery connector J3.
3. Put a strap through the slot in each outer saddle. Close each strap
   around the cells.
4. Put the two speaker leads up through the outer holes in the shelf. Put
   the USB-C lead up through the centre hole.
5. Put the bay wall on the back of the baffle. The tabs touch the baffle,
   and the shelf is above the main PCB.
6. Install three M3 × 10 countersunk screws from the front of the baffle
   into the tabs.
7. Connect the speaker leads to the driver terminals and to J4 (right) and
   J5 (left) on the main PCB.
8. Connect the battery lead to J3 on the main PCB.
9. Seal the three shelf holes around the leads with a small amount of
   neutral-cure silicone.

The speaker stays off until you push the knob.

## Step 6 — Build the rear panel

1. Install 8 inserts in the two spacer frames on the inside of the rear panel.
2. Install one 7.3 g weight on the rod of each radiator. Tighten the wing nut.
3. Apply foam tape to the front face of each radiator flange.
4. Put each radiator on its spacer frame from the inside. Install four
   M3 × 6 pan head screws in each radiator.
5. Put the USB-C port board on the small shelf. Push the receptacle into the
   slot. Install two M2.5 × 6 thread-forming screws.

## Step 7 — Install the front module

1. Hold the front module by the baffle. Hold the free end of the USB-C lead.
2. Push the module into the front of the sleeve. Pull the USB-C lead out
   through the rear opening.
3. Install five M3 × 10 countersunk screws through the baffle into the
   sleeve posts.

## Step 8 — Install the rear panel

1. Put the polyester fill loosely behind the two drivers. Keep it away from
   the radiator rods.
2. Connect the USB-C lead to the port board.
3. Push the rear panel into the sleeve. Do not pinch the lead.
4. Install six M3 × 10 countersunk screws.

## Step 9 — Fit the covers and the knob

1. Glue the eight 6 × 2 mm magnets into the baffle pockets with CA glue.
   Let the glue cure for 10 minutes.
2. Put one 6 × 1 mm magnet on each baffle magnet. Each magnet turns to the
   correct polarity.
3. Put a drop of CA glue in each magnet pocket on the back of the grille and
   the control strip.
4. Put the grille and the control strip on the baffle. Push for 30 seconds.
   Remove them, and let the glue cure for 10 minutes.
5. Attach the acrylic window to the back of the control strip with
   double-sided tape. Do not use CA glue on acrylic. It makes the acrylic white.
6. Glue the orange mark into the groove on the knob.
7. Put the control strip on the baffle. The keys go through their holes.
8. Push the knob onto the encoder shaft. Align the flat in the bore with
   the flat on the shaft.
9. Put the grille on the baffle.

## Step 10 — Test

1. Connect a USB-C PD charger. Make sure that the LCD shows the charge state.
2. Push the knob. Make sure that the LCD shows the start screen.
3. Pair a phone with Bluetooth. Play a sine sweep from 40 Hz to 200 Hz at
   medium volume. Listen for rattles.
4. If a part rattles, find it, and add foam or tighten the screws.
5. Connect the speaker to Wi-Fi. Log in to Spotify on the LCD.

## Disassembly

1. Pull off the grille and the control strip. The magnets hold them.
2. Pull the knob off the encoder shaft.
3. Remove the six rear panel screws. Disconnect the USB-C lead.
4. Remove the five front screws. Pull the front module out of the sleeve.

## Known gaps in revision 0.1

- The baffle and the rear panel have no gasket ledge. Seal the seam from
  the inside with a thin rope of putty until the model has a ledge.
- The resin split of the sleeve is not modelled.
- The lead lengths are estimates. Measure them on the first build.
