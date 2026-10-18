# Bluespeaker Mini

Revision 0.3 · 2026-10-11 · Model: `cad/bluespeaker_mini.py`

The Mini is a smaller Bluetooth speaker with the hardware from `../bluedeck`.
It has the same Braun-style box as the large version. All printed parts use
three filaments: grey, orange, and a small amount of white. It has no LCD and no ESP32: the ZK-502C
board has its own Bluetooth receiver and volume control.

| Item | Value |
|---|---|
| Outside size | 166 W × 108 H × 94 D mm |
| Drivers | 2× Dayton Audio PC68-4 (2.5 in, 4 Ω), on 3 mm spacer frames |
| Amplifier | ZK-502C Bluetooth amplifier board, 12–24 V DC |
| Controls | Volume knob (on the ZK-502C volume control), AUX in |
| Power | DC adapter, 12–24 V, into the socket on the rear panel |
| Enclosure | Sealed, about 1.1 L shared by both drivers |
| Colours | Grey shell and grille, orange baffle (shows through the grille), white strip, orange knob with a white mark |

## Documents and files

| File | Content |
|---|---|
| `docs/Bluespeaker-Mini-Engineering-Report.pdf` | Report for a manufacturer: parts, print settings, fits, fasteners, snaps, post-processing, assembly, inspection, and the A3 drawing sheets |
| `docs/Bluespeaker-Mini-Drawings.pdf` | The 12 A3 drawing sheets alone (BSM-00 to BSM-11) |
| `docs/Bluespeaker-Mini-Specs.pdf` | Short spec sheet |
| `cad/step-mini/*.step` | One STEP file for each part, in its assembly position |
| `cad/bluespeaker_mini.FCStd` | FreeCAD document: all parts, and a TechDraw page for each printed part |

To make them again:

1. `uv run cad/mini_report.py --step` writes the STEP files. The parts come
   from a cache in `cad/.cache-mini/` while the model source is unchanged.
2. `uv run cad/mini_drawings.py` writes the drawing sheets (about 30 s).
3. `freecadcmd cad/mini_freecad.py` writes the FreeCAD document.
4. `uv run cad/mini_report.py`, then `uv run --with pillow cad/mini_report.py --render`,
   writes the render sets and renders only the views that changed.
5. `uv run --with pymupdf cad/mini_report.py --pdf` writes the report.

The FreeCAD document computes its drawing views when you open a page and
select Recompute. The released sheets come from `cad/mini_drawings.py`: it
uses the same hidden-line algorithm as TechDraw, and it adds the dimensions
and the sections.

## Layout

- The two drivers sit side by side in the upper part, 74 mm apart.
- The ZK-502C lies flat in the bottom bay on a printed tray. The board front
  edge touches the back of the baffle. The volume control and the AUX socket
  come through the baffle and the orange strip.
- The nut on the volume control holds the board against the baffle, as in
  bluedeck.
- The volume control body (10 × 11.45 mm) stands 2 mm in front of the board
  edge. It sits in a 1.5 mm pocket in the baffle back, so the board edge
  stops 0.5 mm behind the baffle. The nut recess in the baffle front is
  1.5 mm deep, with 1 mm of wall between the two. The nut stands 0.5 mm in
  front of the baffle, in a 0.7 mm recess in the back of the control strip.
- The volume control hole sets the board height at the front. The tray rails
  stop 0.5 mm below the PCB (`rail_drop`), so they cannot push the front edge
  up against the hole.
- Two small self-tapping screws hold the rear edge of the board. Each screw
  goes through a rear mounting hole into a post on the tray. The posts set
  the board height at the rear. The tray screws to the back of the baffle, so the front module
  slides out in one piece.
- The DC socket on the rear edge of the board aligns with a hole in the rear
  panel.

## Sound

The PC68-4 has Fs 117 Hz, Qts 0.65, and Vas 0.7 L. In about 0.55 L per
driver, the sealed box gives a Qtc near 1.0 and an F3 near 150 Hz. The Mini
is a desk speaker with clear mids and little deep bass. A larger box or a
passive radiator would give more bass, but the box would not be "mini".

## Front grille: two styles

The model has a `grille_style` setting.

### Lattice (default, for FDM)

The grille is a solid border with two layers of ribs. Each rib is one
extrusion line wide (0.5 mm for the 0.5 mm nozzle of the TAZ Workhorse SE),
at a 3.0 mm pitch. The 2.5 mm openings let the orange baffle show through.

- Print the grille front face down on a smooth or textured bed.
- Layer 1 holds horizontal ribs. This is the visible face, so the face is
  even and has no seams.
- Layer 2 holds vertical ribs. They bridge the 2.5 mm gaps.
- The slicer makes each rib one straight line. There are no small loops, no
  seams, and almost no retractions. The print takes minutes, not hours.
- The open area is about 69 %. Sound goes through freely. Set `rib_pitch`
  to 3.5 for about 73 %, or to 2.0 for a finer mesh (56 %).
- Use the Cura profile "Bluespeaker Mini - PLA Grille 0.25" (see below).
  For a different nozzle, set `rib_w` to your line width and export again.

### Holes (for resin)

The round-hole grid of the large version: 2.5 mm holes at a 3.8 mm pitch.
The export writes it as `cad/stl-mini/grille_holes.stl`. Use it for resin
prints. On FDM, each hole is a small loop on each layer, which is slow and
leaves seams.

### Slicer infill (Cura)

The slicer can also make the mesh. Then the infill settings in Cura control
the mesh, and Cura slices again when you change them.

The export writes three Cura files to `cad/stl-mini/`. Each file has a
solid plate (border, head ports, snap catches) and a window in the same position:

- `grille_infill.3mf`: the full grille.
- `grille_infill_coupon.3mf`: one corner of the grille (60 × 40 mm), for a
  short test print.
- `grille_infill_presets.3mf`: six corner coupons, each with a fixed preset
  from the table below. Print them together to compare the presets.

The window is a modifier mesh ("Modify settings for overlaps") with no walls
and no top or bottom layers, so only the infill prints. The plate always
prints solid. The files contain these settings.

The window also prints its infill at 20 mm/s with 110 % flow ("Infill Speed"
and "Infill Flow"). The window lines touch the bed with no wall or bottom
layer below them, so fast lines pull loose. The plate keeps the profile
speed. To change the window values, click the window and open "Per Model
Settings". The print settings cannot change the window speed alone, because
the plate is also infill.

To use the files:

1. Open `grille_infill.3mf` or `grille_infill_coupon.3mf` in Cura.
2. Select the profile "Bluespeaker Mini - PLA Grille Infill 0.25". It starts
   with the 3 mm lattice: Lines, 16.67 %, directions `[90,90,90,0,0,0]`.
3. Change "Infill Density", "Infill Pattern", or "Infill Line Directions" in
   the print settings. The window changes, and the plate stays solid.

| Preset | Infill Pattern | Infill Density | Infill Line Directions | Rib spacing |
|---|---|---|---|---|
| Lattice 3.0 | Lines | 16.67 % | `[90,90,90,0,0,0]` | 3.0 mm, as the lattice grille |
| Lattice 2.0 | Lines | 25 % | `[90,90,90,0,0,0]` | 2.0 mm |
| Diamond 3.0 | Lines | 16.67 % | `[45,45,45,135,135,135]` | 3.0 mm |
| Grid 3.0 | Grid | 33.33 % | `[]` | 3.0 mm |
| Triangles 4.0 | Triangles | 37.5 % | `[]` | 4.0 mm |
| Trihexagon 4.0 | Trihexagon | 37.5 % | `[]` | 4.0 mm |

Notes:

- The rib spacing is 0.5 mm × 100 / density. For Grid it is 2 times that,
  and for Triangles and Trihexagon 3 times that.
- "Infill Line Directions" has one angle for each layer, and then the list
  repeats. The grille has 6 layers. 90° gives horizontal ribs on the face.
- Each rib is one 0.5 mm line.
- The coupons in `grille_infill_presets.3mf` have their own settings, so the
  print settings do not change them.

## Cura profiles (PLA)

The folder `cura/` has four PLA profiles for the LulzBot TAZ Workhorse SE
with the 0.5 mm tool head. They are installed in Cura 5.13. They use the
calibrated values of the profile "Workhorse SE - Standard 0.2 - workhorse-pla":

| Setting | Value | Profiles |
|---|---|---|
| Scaling Factor Shrinkage Compensation XY | 100.21 % | All |
| Scaling Factor Shrinkage Compensation Z | 100 % | All |
| Printing Temperature | 220 °C | All |
| Horizontal Expansion | 0.095 mm | Shell, Parts |
| Hole Horizontal Expansion | 0.17 mm | Shell, Parts |

The Grille profiles have no horizontal expansion. An expansion would make
each 0.5 mm rib wider or narrower than one line. The model therefore adds
the net expansion to the grille snap catches (0.095 mm) and to the grille
head ports (0.075 mm). The values are `grille_xy_comp` and `grille_hole_comp`.

| Profile | Files | Main settings |
|---|---|---|
| Bluespeaker Mini - PLA Shell 0.25 | `sleeve.stl` | Solid 3 mm walls, supports from the build plate only (for the four front posts), 6 mm brim inside and outside, 40 % fan (none on layer 1) |
| Bluespeaker Mini - PLA Parts 0.25 | `baffle`, `rear_panel`, `tray`, `control_strip`, `knob`, `knob_mark`, `feet` | 0.25 mm first layer, 4 walls, 40 % gyroid for stiff panels, brim, no supports, bridge settings for the membranes |
| Bluespeaker Mini - PLA Grille Infill 0.25 | `grille_infill*.3mf` | The Grille profile, with 16.67 % Lines infill for the window (see "Slicer infill") |
| Bluespeaker Mini - PLA Grille 0.25 | `grille.stl` | 0.25 mm first layer (each rib layer is exactly 3 layers), one 0.5 mm line per rib, bridge settings, no wipe, skirt, 30 mm/s. 220 °C, 2.0 mm retraction at 30 mm/s, and 250 mm/s travel stop strings between the snap catches |

To use a profile:

1. Close Cura. To install the profiles again, copy the eight files from
   `cura/` to `~/.local/share/cura/5.13/quality_changes/`.
2. Start Cura. Select the printer "LulzBot TAZ Workhorse | SE | 0.5 mm".
3. Open the STL file. In the print settings, select the profile under
   "Custom profiles".
4. Select the material and the colour for each part (see the table below).

### Even first layer

The first layer is the visible face of the baffle, the grille, the strip,
and the sleeve rim. All four profiles have these settings for an even face:

- **Extra Skin Wall Count 0** (`skin_outline_count`). Cura then draws no
  extra loop around each bottom-skin area and each hole. The fill lines run
  straight to the walls.
- **Top/Bottom Line Directions `[45]`** (`skin_angles`). All skin lines run
  in one direction, so the face has one even sheen.
- **Monotonic Top/Bottom Order on.** Each line goes next to its neighbour in
  one direction, so the patches between holes have no ridges where they meet.
- **Combing "Not on Outer Surface".** Travel moves do not drag the nozzle
  across the finished face.

A CuraEngine slice of the baffle shows 7 extra skin loops on the first layer
with the old settings, and 0 with the new settings.

### Layer and line alignment

The model uses the layers and the lines of these profiles:

- Grille, strip, and baffle print at 0.25 mm layers with a 0.25 mm first
  layer. Each height on these parts is a multiple of 0.25 mm: the 1.5 mm
  covers (6 layers), the 4.0 mm baffle, the 1.5 mm and 2.25 mm counterbores,
  the 0.25 mm membranes, and the 2.5 mm snap catches (10 layers).
- The sleeve keeps a 0.425 mm first layer for a strong hold on the bed.
- Widths use the 0.5 mm line: the snap beam is one line, the ring around each
  head port is 3 lines (1.5 mm), and the clearances are half a line (0.25 mm).

Slice the grille, then look at the layer view. Layers 1 to 3 must show one
straight line for each horizontal rib, and layers 4 to 6 one line for each
vertical rib.

## Printed parts

The export writes these files to `cad/stl-mini/`. Each file is already in
its print orientation, centred, and on the bed (Z = 0), so it opens in Cura
ready to slice. To write only the STL files, run
`uv run cad/bluespeaker_mini.py --stl`.

| File | Process | Orientation and notes |
|---|---|---|
| `sleeve.stl` | FDM, grey | Front opening down. Supports below the four front posts only. Use the Orca profile "Bluespeaker Mini - Shell 0.25" and the filament "Workhorse PLA 2.85 - 230 Shell" (see "Warped front corners"). |
| `baffle.stl` | FDM, orange | Front face down. Turn supports off. The front face shows through the grille. |
| `rear_panel.stl` | FDM, grey | Outer face down. |
| `tray.stl` | FDM, grey | Flat. |
| `grille.stl` | FDM, grey | Front face down. See "Lattice" above. |
| `grille_holes.stl` | Resin | Alternative grille. |
| `control_strip.stl` | FDM, white (about 9 g) | Front face down. |
| `knob.stl` | FDM, orange | Front face up. |
| `knob_mark.stl` | FDM, white | Glue into the groove on the knob. |
| `feet.stl` | FDM, grey | Flat. Or use stick-on rubber feet: PLA feet can slide. |

The colours come from the filament, so no part needs paint. The design page
has a colour switcher with five grey and orange schemes and a choice of
strip colour (white, grey, or orange).

## Drilled holes

Small holes that open to the bed fill with support material. Horizontal
holes sag. The model therefore prints these holes as 1.6 mm pilot holes with
a 45° tip. The slicer adds no support in a pilot hole, and its walls make a
solid ring around each pilot. Drill each hole to its full size after the
print. The pilot holds the drill on the correct position.

| Part | Holes | Drill | Depth |
|---|---|---|---|
| Sleeve | 4 front post holes (inserts) | 4.0 mm | 7 mm |
| Tray | 2 tab holes (inserts) | 4.0 mm | Through the tab (9 mm) |
| Tray | 2 post tap holes | Do not drill | Printed 1.5 mm, the screw cuts its thread |

The baffle also has one-layer membranes. Each membrane is the floor of a
recess that opens to the bed, so the slicer prints it as a straight bridge:

- Six screw counterbores: drill the membrane with a 3.4 mm drill from the
  back of the baffle. The printed hole guides the drill.
- The volume control hole and the AUX hole: cut the membrane out with a
  knife from the back.

Print the baffle with supports off. It has no part that needs support.

## Screws: socket head cap screws

All M3 screws are socket head cap screws (ISO 4762, 5.5 mm head, 3 mm high).

- **Front corners:** The four baffle screws are part of the front design.
  Each head sits in a 1.5 mm counterbore in the baffle and goes through a
  round port in the grille (upper corners) or the strip (lower corners). The
  head top is flush with the cover face.
  - The ports and the counterbores are 6.0 mm across: 0.25 mm around the
    5.5 mm head. A thin orange ring of the baffle shows around each head.
  - Each port has a 0.5 mm × 45° chamfer at the face. The covers print face
    down, so the chamfer needs no support.
  - A solid ring of 1.5 mm (3 lines) surrounds each port in the grille. The
    lattice or the infill stops at the ring.
  - The ports also locate the covers on the heads.
- **Tray:** The two tray screws sit in 2.25 mm counterbores. Pockets on the
  back of the strip cover their heads.
- **Rear:** The four rear panel screws have no counterbore. The heads sit on
  the rear panel.

## Warped front corners

The sleeve prints front opening down. The front rim is the first layer, so
a lifted corner shows at the front. The Shell profiles reduce this:

- The profile has a 6 mm brim on the outside and on the inside of the rim.
- The fan is off for the first layer and goes up to 40 % at layer 5. Full fan
  on a 3 mm solid wall makes each layer shrink fast, and the shrink lifts the
  corners. Bridges still get 100 % fan.
- In Cura, the profile "Bluespeaker Mini - PLA Shell 0.25" has these
  settings. In Orca, use the process "Bluespeaker Mini - Shell 0.25" and the
  filament "Workhorse PLA 2.85 - 230 Shell". Overhangs get 100 % fan in Orca.
- Keep the bed at 60 °C. A colder bed holds the first layer with less force,
  so the corners lift more.
- Clean the bed with isopropyl alcohol before the print. Keep drafts away
  from the printer.

To install the Cura profiles, close Cura and copy the eight files from `cura/`
to `~/.local/share/cura/5.13/quality_changes/`. To install the Orca profiles,
close Orca and run `python3 orca/make_profiles.py --install`. Each install
replaces your own changes to the Bluespeaker profiles.

## Snap catches (grille and strip)

The grille and the strip both snap onto the baffle. Their faces are flush
with the sleeve rim and with the four screw heads. You can remove them and
fit them again many times. They need no magnets, pins, or glue.

Each cover has four catches. Each catch is a beam between two posts on the
cover back. The grille catches are near the corners of its top and bottom
bands. The strip catches are clear of the volume control, the AUX socket,
and the tray screw heads.

- The beam is one 0.5 mm line, 10 mm long, and 2.0 mm high. It bridges
  0.5 mm above the grille back, so the slicer prints it as straight lines
  along its length.
- The beam flexes in the plane of the grille. The bending load goes along
  the printed lines, not across the layers. An upright pin or hook would
  bend across the layers and crack.
- A 0.4 mm bump on the beam clicks behind a lip at the mouth of a 3 mm
  pocket in the baffle. The lip face is at 45°. When you pull the grille,
  the lip pushes the bump back and releases the grille. The catch does not
  break.
- The bump presses 0.05 mm on the lip. This preload pulls the grille flat
  against the baffle.
- The posts fit their pockets with 0.15 mm clearance. They locate the cover.
- The strip prints with the Parts profile, which has 0.095 mm horizontal
  expansion. Its beam is therefore modelled 0.31 mm wide, so it prints as
  one 0.5 mm line.
- The pocket is narrow at the mouth and wider inside. The baffle prints
  front face down, so the pocket walls only step back and need no support.
  The pocket floor is a 3.3 mm bridge.

Before you print the baffle and the covers, print the three test parts:
`fit_test_snap_baffle.stl` (Parts profile, two pockets),
`fit_test_snap_grille.stl` (Grille profile), and `fit_test_snap_strip.stl`
(Parts profile). Press each catch into a pocket, then pull it out:

- Too tight, or the beam cracks: set `snap_bump` smaller (for example 0.3).
- Too loose: set `snap_bump` larger (for example 0.5) or `snap_preload`
  larger (for example 0.1).

To remove the grille, put a flat blade in the slot at the top edge of the
strip, below the grille centre. Lift the bottom edge of the grille, then pull
the grille off.

## Fit of the front module

- The sleeve has a 0.6 mm lead-in chamfer inside the front opening. It takes
  the elephant foot of the first layers. The Orca Shell profile also has
  0.15 mm elephant foot compensation.
- The panels have 0.3 mm clearance on each side in the sleeve opening.
- The front posts sit 0.4 mm deeper than the baffle needs. Raised plastic
  around the heat-set inserts and support marks on the post faces then
  cannot push the baffle forward. The insert holes also have a relief
  chamfer for that plastic. The grille sits up to 0.4 mm below the rim.
- If the baffle still stops early on a sleeve that you printed before:
  scrape the inside of the front rim, shave the plastic rings around the
  inserts flat, and remove support marks from the four front post faces.

## Hardware

| Item | Qty | Where |
|---|---|---|
| Dayton Audio PC68-4 | 2 | [Parts Express 295-150](https://www.parts-express.com/Dayton-Audio-PC68-4-2-1-2-Full-Range-Poly-Cone-Driver-295-150) |
| ZK-502C Bluetooth amplifier board | 1 | From your bluedeck parts |
| DC adapter, 12–24 V, 2 A or more | 1 | Check the plug size of the ZK-502C socket before you buy |
| M3 heat-set insert, short (3 mm long, 4.0 mm hole) | 18 | [CNC Kitchen M3 Short](https://www.3djake.com/cnc-kitchen/threaded-inserts-m3-short?sai=15446) |
| M3 × 8 socket head cap screw | 6 | Baffle 4, tray 2 |
| Self-tapping screw, 1.9 mm × 7 mm, 3.28 mm pan head | 2 | Board rear edge to the tray posts |
| M3 × 6 socket head cap screw | 4 | Rear panel |
| Drills: 3.4 mm and 4.0 mm | 1 each | Pilot holes (see "Drilled holes") |
| M3 × 5 pan head screw | 8 | Speakers |
| Speaker wire, 2 × 0.5 mm², 150 mm | 2 | Drivers to the ZK-502C terminals |
| Closed-cell foam tape, 3 × 6 mm | 0.6 m | Driver flanges, panel seams |

## Step 1 — Prepare the sleeve

1. Remove the supports below the four front posts.
2. Drill the four front post holes: 4.0 mm, 7 mm deep.
3. Install 8 short inserts in the sleeve posts: 4 at the front, 4 at the rear.
4. Glue the four feet into the recesses on the bottom.

## Step 2 — Mount the speakers on the baffle

1. Drill or cut the membranes in the baffle (see "Drilled holes").
2. Install 8 short inserts in the two spacer frames on the back of the baffle.
3. Apply foam tape to the front face of each driver frame.
4. Put each driver on its spacer frame from the back. The terminals point down.
5. Install four M3 × 5 pan head screws in each driver.

## Step 3 — Fit the tray and the amplifier

1. Drill the two tab holes of the tray: 4.0 mm, through the tab.
2. Install 2 short inserts in the tabs at the front of the tray.
   Each tab has at least 3 mm of plastic around the 4.0 mm hole, so the
   insert has material to grip. Push the insert in slowly and keep it
   straight.
3. Put the tray against the back of the baffle. Install two M3 × 8
   socket head cap screws from the front of the baffle into the tabs.
4. Remove the knob and the nut from the ZK-502C volume control.
5. Put the board on the tray rails. Push the volume control bushing and the
   AUX socket into their holes in the baffle. The volume control body goes
   into its pocket in the baffle back.
6. Install the nut on the bushing from the front. The nut sits in its recess
   and pulls the volume control body onto the pocket floor.
7. Install two self-tapping screws (1.9 mm thread, 7 mm long, 3.28 mm head)
   through the rear mounting holes into the tray posts. Stop when the head
   touches the board. The thread cuts into the 1.5 mm tap hole. Do not
   tighten more, or the thread strips the plastic.
8. Connect the speaker wires to the drivers and to the ZK-502C terminals.

## Step 4 — Install the front module

1. Push the front module into the front of the sleeve.
2. Install four M3 × 8 socket head cap screws through the baffle into the posts.

## Step 5 — Install the rear panel

1. Push the rear panel into the sleeve. The DC socket aligns with the hole.
2. Install four M3 × 6 socket head cap screws.

## Step 6 — Fit the covers and the knob

1. Align the white strip with the two lower screw heads and the volume
   control. Push it on until the four catches click.
2. Align the grille ports with the two upper screw heads. Push the grille
   on until the four catches click.
3. Push the knob onto the volume control shaft.

To remove the covers, pull off the knob. Put a flat blade in the pry slot at
the top edge of the strip. Lift the bottom edge of the grille, then pull the
grille off. Then lift the top edge of the strip and pull the strip off. Do
not lever a cover at the centre of the lattice: the lattice is thin.

## Test

1. Connect the DC adapter. Pair a phone with the ZK-502C.
2. Play a sweep from 80 Hz to 300 Hz at medium volume. Listen for rattles.
3. Test the AUX input with a 3.5 mm cable.

## Known gaps

- The ZK-502C component positions are estimates from photos (as in
  bluedeck). Measure your board and change `amp_parts()` and the port
  values in `MParams` before you print.
- The volume control shaft is drawn round. Check whether your ZK-502C has a
  knurled or a D-shaft, and change the knob bore to match.
