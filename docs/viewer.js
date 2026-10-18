// Shared 3D viewer for index.html and mini.html. The manifest path is in #stage data-manifest.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const $ = id => document.getElementById(id);
const stage = $("stage"), statusEl = $("status"), pickEl = $("pick");

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
const sun = new THREE.DirectionalLight(0xffffff, 1.2);
sun.position.set(300, 500, 400);
scene.add(sun, new THREE.HemisphereLight(0xffffff, 0xd8d2c4, 0.6));

const camera = new THREE.PerspectiveCamera(35, 1, 1, 10000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
const HOME = { pos: new THREE.Vector3(470, 330, 720), target: new THREE.Vector3(0, 95, 0) };
let VIEW_SCALE = 1;
function resetView() {
  camera.position.copy(HOME.pos);
  controls.target.copy(HOME.target);
  controls.update();
}
resetView();

function resize() {
  const w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage);

// The model is Z-up in mm. The GLB files are Y-up in metres.
// Model (x, y, z) maps to three.js (x, z, -y).
const toThree = ([x, y, z]) => new THREE.Vector3(x, z, -y);

const METAL = new Set(["encoder", "usb_c", "lcd_backlight", "battery_nickel", "magnets"]);
const parts = [];
let explode = 0, selected = null;
let mode = "explode", stepN = 0, stepAnim = null, anim = null;

function setSelected(p) {
  selected = p;
  for (const q of parts) {
    q.mats.forEach(m => m.emissive.setHex(q === p ? 0x5a2410 : 0x000000));
    q.li.classList.toggle("sel", q === p);
  }
  if (!p) { pickEl.style.display = "none"; return; }
  const [sx, sy, sz] = p.info.size;
  const qty = p.info.qty > 1 ? ` · qty ${p.info.qty}` : "";
  pickEl.innerHTML = `<b>${p.info.label}</b><br>${sx} × ${sy} × ${sz} mm${qty}<br><span style="color:var(--muted)">${p.info.process} · step ${p.info.step}</span>`;
  pickEl.style.display = "block";
}

function updateVisibility() {
  const refs = $("refs").checked;
  for (const p of parts) {
    const inStep = mode !== "step" || p.inStep;
    p.holder.visible = p.on && (p.info.printed || refs) && inStep;
    p.li.classList.toggle("dim", !inStep);
    p.li.classList.toggle("cur", mode === "step" && p.info.step === stepN);
  }
}

function applyExplode() {
  for (const p of parts) p.holder.position.copy(p.dir).multiplyScalar(explode);
}

const clamp01 = t => Math.max(0, Math.min(1, t));
function applyStep(t) {
  const st = steps[stepN - 1], mv = st.move;
  const tm = mv ? clamp01(t / 0.55) : 1;
  const tc = mv ? clamp01((t - 0.45) / 0.55) : t;
  for (const p of parts) {
    const off = new THREE.Vector3();
    if (p.info.step === stepN) off.copy(p.dir).multiplyScalar(0.9 * (1 - ease(tc)));
    else if (mv && mv.groups.includes(p.info.group)) off.copy(toThree(mv.by)).multiplyScalar(1 - ease(tm));
    p.holder.position.copy(off);
  }
}

function showStep(n) {
  if (!steps.length) return;
  n = Math.max(1, Math.min(steps.length, n));
  mode = "step"; stepN = n; anim = null;
  const st = steps[n - 1];
  for (const p of parts) p.inStep = p.info.step <= n && st.groups.includes(p.info.group);
  $("sLbl").innerHTML = `<b>Step ${n} of ${steps.length}</b><br>${st.title}`;
  explode = 0; $("explode").value = 0;
  updateVisibility();
  stepAnim = { t0: performance.now() };
  applyStep(0);
}
function showAll() {
  mode = "explode"; stepN = 0; stepAnim = null;
  $("sLbl").innerHTML = "Assembly steps";
  updateVisibility();
  applyExplode();
}
window.bsShowStep = n => { showStep(n); stage.scrollIntoView({ behavior: "smooth", block: "center" }); };
// Recolour parts by name, for colour schemes: { partName: "#rrggbb", ... }
window.bsSetColors = map => {
  for (const p of parts) {
    const c = map[p.info.name];
    if (!c) continue;
    p.mats.forEach(m => m.color.set(c));
    p.li.querySelector(".sw").style.background = c;
  }
};

// ---- load
const loader = new GLTFLoader();
const manifest = await (await fetch(stage.dataset.manifest || "models/manifest.json", { cache: "no-store" })).json();
const steps = manifest.steps || [];
const infos = manifest.parts || manifest;
const list = $("parts");
let loaded = 0;
const bust = Date.now();

await Promise.all(infos.map(async info => {
  const gltf = await loader.loadAsync(info.file + "?v=" + bust);
  const root = gltf.scene;
  root.scale.setScalar(1000);
  const glass = info.name === "lcd_window" || info.name === "lcd_panel";
  const metal = METAL.has(info.name) || info.name.startsWith("screws_") || info.name.startsWith("inserts_");
  const mat = new THREE.MeshStandardMaterial({
    color: info.color,
    roughness: glass ? 0.06 : metal ? 0.32 : 0.72,
    metalness: metal ? 0.85 : info.name === "control_strip" ? 0.35 : 0.0,
    transparent: info.name === "lcd_window", opacity: info.name === "lcd_window" ? 0.82 : 1,
    side: THREE.DoubleSide,
  });
  const mats = [mat];
  const edgeLines = [];
  root.traverse(o => {
    if (!o.isMesh) return;
    o.material = mat;
    if (!info.printed || info.edges === false) return;  // edges only on the printed parts
    const e = new THREE.LineSegments(
      new THREE.EdgesGeometry(o.geometry, 35),
      new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.22 }));
    o.add(e);
    edgeLines.push(e);
  });
  const holder = new THREE.Group();
  holder.add(root);
  scene.add(holder);
  const li = document.createElement("li");
  const qty = info.qty > 1 ? ` ×${info.qty}` : "";
  li.innerHTML = `<span class="sw" style="background:${info.color}"></span><span class="lbl">${info.label}${qty}</span><span class="tag">${info.step}·${info.printed ? "print" : "buy"}</span>`;
  const p = { info, holder, root, mats, edgeLines, li, on: true, inStep: true, dir: toThree(info.explode) };
  li.querySelector(".sw").addEventListener("click", ev => {
    ev.stopPropagation();
    p.on = !p.on;
    li.style.opacity = p.on ? 1 : 0.4;
    updateVisibility();
  });
  li.addEventListener("click", () => setSelected(selected === p ? null : p));
  parts.push(p);
  statusEl.textContent = `Loading parts… ${++loaded}/${infos.length}`;
}));

parts.sort((a, b) => infos.indexOf(a.info) - infos.indexOf(b.info));

// Fit the home view to the model size (the large and the mini model share this viewer)
{
  const box = new THREE.Box3();
  parts.forEach(p => box.expandByObject(p.holder));
  const c = box.getCenter(new THREE.Vector3()), r = box.getSize(new THREE.Vector3()).length() / 2;
  VIEW_SCALE = r / 175;
  HOME.target.copy(c);
  HOME.pos.copy(c).add(new THREE.Vector3(470, 235, 720).multiplyScalar(VIEW_SCALE));
  resetView();
}
parts.forEach(p => list.appendChild(p.li));
statusEl.textContent = `${parts.length} parts`;
window.dispatchEvent(new Event("bsready"));

// ---- controls
const slider = $("explode");
slider.addEventListener("input", () => {
  if (mode === "step") showAll();
  explode = +slider.value; anim = null; applyExplode();
});
$("anim").addEventListener("click", e => {
  if (mode === "step") showAll();
  const to = explode > 0.5 ? 0 : 1;
  anim = { from: explode, to, t0: performance.now() };
  e.target.textContent = to ? "Assemble" : "Explode";
});
$("reset").addEventListener("click", resetView);
$("refs").addEventListener("change", updateVisibility);
$("edges").addEventListener("change", e => {
  for (const p of parts) p.edgeLines.forEach(l => l.visible = e.target.checked);
});
$("ghost").addEventListener("change", e => {
  const s = parts.find(p => p.info.name === "sleeve");
  s.mats.forEach(m => { m.transparent = e.target.checked; m.opacity = e.target.checked ? 0.18 : 1; m.depthWrite = !e.target.checked; m.needsUpdate = true; });
});
$("sPrev").addEventListener("click", () => showStep(stepN ? stepN - 1 : 1));
$("sNext").addEventListener("click", () => showStep(stepN + 1));
$("sAll").addEventListener("click", showAll);

// URL options: ?view=front|rear|side|top|iso, ?explode=0..1, ?step=1..9
const qs = new URLSearchParams(location.search);
const VIEWS = { front: [0, 82, 600], rear: [0, 82, -600], side: [600, 82, 0], top: [0, 700, 1], bottom: [0, -540, 1], iso: [470, 330, 720], under: [380, -260, 520] };
if (VIEWS[qs.get("view")]) {
  camera.position.copy(HOME.target).add(new THREE.Vector3(...VIEWS[qs.get("view")]).sub(new THREE.Vector3(0, 82, 0)).multiplyScalar(VIEW_SCALE));
  controls.update();
}
if (qs.has("explode")) { explode = +qs.get("explode"); slider.value = explode; }
// ?only=name1,name2 shows only these parts
if (qs.has("only")) {
  const keep = new Set(qs.get("only").split(","));
  for (const p of parts) { p.on = keep.has(p.info.name); p.li.style.opacity = p.on ? 1 : 0.4; }
  updateVisibility();
}
applyExplode();
if (qs.has("step")) { showStep(+qs.get("step")); stepAnim = null; applyStep(1); }

// ---- picking
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
let down = null;
renderer.domElement.addEventListener("pointerdown", e => down = [e.clientX, e.clientY]);
renderer.domElement.addEventListener("pointerup", e => {
  if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const vis = parts.filter(p => p.holder.visible && !(p.info.name === "sleeve" && $("ghost").checked));
  const hit = ray.intersectObjects(vis.map(p => p.holder), true).find(h => h.object.isMesh);
  setSelected(hit ? parts.find(p => p.holder.getObjectById(hit.object.id)) : null);
});

function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
renderer.setAnimationLoop(now => {
  if (anim) {
    const t = Math.min(1, (now - anim.t0) / 1400);
    explode = anim.from + (anim.to - anim.from) * ease(t);
    slider.value = explode;
    applyExplode();
    if (t >= 1) anim = null;
  }
  if (stepAnim) {
    const t = Math.min(1, (now - stepAnim.t0) / 1800);
    applyStep(t);
    if (t >= 1) stepAnim = null;
  }
  controls.update();
  renderer.render(scene, camera);
});
