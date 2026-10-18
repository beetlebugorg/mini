// Bluespeaker Mini: line-art images for the spec sheet, the drawings, and the docs page, in the
// style of the beetlebug.org explode viewer. Uses three.js in headless Chromium.
// Run from the repo root: node docs/lineart/render.mjs [shot ...]
// Output: docs/lineart/raw/<shot>-light.png and <shot>-dark.png, with a transparent background.
// build.sh trims them into docs/lineart/img/.

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const DOCS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(DOCS, "lineart", "raw");

// Z-up, millimetres, the front faces -Y. Labels, fills, and explode offsets are the same as on the site.
const PARTS = {
  sleeve: ["Sleeve", "print", [0, 0, 140]],
  feet: ["Feet", "print", [0, 0, -45]],
  inserts_front: ["Inserts", "buy", [0, 0, 140]],
  inserts_rear: ["Inserts", "buy", [0, 0, 140]],
  baffle: ["Front baffle", "print", [0, -60, 0]],
  speaker_l: ["PC68-4 left", "dark", [0, 40, 0]],
  speaker_r: ["PC68-4 right", "dark", [0, 40, 0]],
  inserts_speaker: ["Inserts", "buy", [0, 20, 0]],
  screws_speaker: ["M3 × 5", "dark", [0, 70, 0]],
  tray: ["Amp tray", "print", [0, 30, -40]],
  inserts_tray: ["Inserts", "buy", [0, 30, -40]],
  screws_tray: ["M3 × 8", "dark", [0, -60, 0]],
  amp_board: ["ZK-502C", "dark", [0, 50, 30]],
  amp_parts: ["ZK-502C", "buy", [0, 50, 30]],
  screws_board: ["Self-tappers", "dark", [0, 50, 55]],
  rear_panel: ["Rear panel", "print", [0, 80, 0]],
  screws_rear: ["M3 × 6", "dark", [0, 110, 0]],
  screws_front: ["M3 × 8", "dark", [0, -60, 0]],
  pot_nut: ["Pot nut", "buy", [0, -40, 0]],
  control_strip: ["Control strip", "print", [0, -80, -35]],
  grille: ["Grille", "print", [0, -80, 40]],
  knob: ["Knob", "print", [0, -150, -35]],
  knob_mark: ["Knob", "print", [0, -150, -35]],
};

const shell = ["sleeve", "feet", "inserts_front", "inserts_rear"];
const front = ["baffle", "speaker_l", "speaker_r", "inserts_speaker", "screws_speaker"];
const amp = ["tray", "inserts_tray", "screws_tray", "amp_board", "amp_parts", "screws_board"];
const rear = ["rear_panel", "screws_rear"];
const covers = ["pot_nut", "control_strip", "grille", "knob", "knob_mark"];
const all = [...shell, ...front, ...amp, "screws_front", ...rear, ...covers];

const CAMERA = [1.1, -1.9, 0.9];       // front right, the same as the site
const REAR = [1.3, 1.6, 0.8];
const each = (ids, v) => Object.fromEntries(ids.map((id) => [id, v]));

// name: { show, focus, explode {id: offset}, camera, frame }. A focus part with no explode
// entry uses its default offset. The steps are the same as on the site.
const SHOTS = {
  hero: { show: all, focus: [], camera: CAMERA },
  front: { show: all, focus: [], camera: [0, -1, 0] },
  rear: { show: all, focus: [], camera: REAR },
  exploded: {
    show: all, focus: [], camera: [1.6, -1.2, 0.9],
    explode: {
      sleeve: [0, 0, 0], feet: [0, 0, -40], inserts_front: [0, 0, 0], inserts_rear: [0, 0, 0],
      ...each([...front, ...amp, "pot_nut"], [0, -110, 0]), screws_front: [0, -150, 0],
      rear_panel: [0, 90, 0], screws_rear: [0, 120, 0],
      control_strip: [0, -190, 0], grille: [0, -210, 0], knob: [0, -240, 0], knob_mark: [0, -240, 0],
    },
  },
  step1: {
    show: shell, focus: ["feet", "inserts_front", "inserts_rear"], camera: CAMERA,
    explode: { inserts_front: [0, -40, 0], inserts_rear: [0, 40, 0] },
  },
  step2: { show: front, focus: ["speaker_l", "speaker_r", "inserts_speaker", "screws_speaker"], camera: REAR },
  step3: {
    show: [...front, ...amp, "pot_nut"],
    focus: ["tray", "inserts_tray", "screws_tray", "amp_board", "amp_parts", "screws_board", "pot_nut"],
    camera: [1.4, 1.4, 1.1],
  },
  step4: {
    show: [...shell, ...front, ...amp, "pot_nut", "screws_front"],
    focus: [...front, ...amp, "pot_nut", "screws_front"], camera: CAMERA,
    explode: { ...each([...front, ...amp, "pot_nut"], [0, -140, 0]), screws_front: [0, -200, 0] },
    labels: each([...front, ...amp, "pot_nut"], "Front module"),
  },
  step5: { show: [...shell, ...front, ...amp, "pot_nut", "screws_front", ...rear], focus: rear, camera: [1.2, 1.8, 0.9] },
  step6: { show: all, focus: ["control_strip", "grille", "knob", "knob_mark"], camera: CAMERA },
  // Details for the design page. The frames are in mm: the corner screw head in its grille port,
  // a snap catch on the grille back, and a pocket in the baffle front.
  corner: { show: all, focus: [], camera: [0.35, -1, 0.3], frame: { center: [-72, -47, 98], size: 34 } },
  snap: { show: ["grille"], focus: [], camera: [-0.6, 1, 0.5], frame: { center: [-63.75, -43, 99], size: 30 } },
  pocket: { show: ["baffle"], focus: [], camera: [0.4, -1, 0.6], frame: { center: [-63.75, -46, 99], size: 30 } },
};

const SIZE = 1600;
const LABEL_PX = 34;

function job(spec) {
  const parts = spec.show.map((id) => {
    const [label, finish, explode] = PARTS[id];
    const focus = spec.focus.includes(id);
    return {
      url: `/models-mini/${id}.glb`, finish, focus,
      label: spec.labels?.[id] ?? label,
      offset: spec.explode?.[id] ?? (focus ? explode : undefined),
    };
  });
  return { parts, camera: spec.camera, frame: spec.frame };
}

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".glb": "model/gltf-binary" };

function serve() {
  const server = http.createServer((req, res) => {
    const file = path.join(DOCS, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!file.startsWith(DOCS) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function main() {
  const only = process.argv.slice(2);
  fs.mkdirSync(OUT, { recursive: true });
  const server = await serve();
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROMIUM ?? "/usr/bin/chromium",
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: SIZE, height: SIZE, deviceScaleFactor: 1 });
    page.on("pageerror", (e) => console.error("page error:", e.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/lineart/page.html`);
    await page.waitForFunction("window.pageReady === true");
    for (const [name, spec] of Object.entries(SHOTS)) {
      if (only.length && !only.includes(name)) continue;
      for (const theme of ["light", "dark"]) {
        await page.evaluate((s, t) => window.renderShot(s, t), { ...job(spec), size: SIZE, labelPx: LABEL_PX }, theme);
        const file = path.join(OUT, `${name}-${theme}.png`);
        await (await page.$("#view")).screenshot({ path: file, omitBackground: true });
        console.log("wrote", path.relative(DOCS, file));
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
