import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const isSmall = matchMedia('(max-width: 860px)').matches;

// ---------------------------------------------------------------------------
// Renderer / scene
// ---------------------------------------------------------------------------
const canvasHost = $('#stage');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.88;
renderer.localClippingEnabled = true;
renderer.domElement.setAttribute('aria-label', '广州塔三维模型');
canvasHost.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(36, innerWidth / innerHeight, 0.5, 5200);
camera.position.set(650, 340, 820);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 300, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.065;
controls.rotateSpeed = 0.55;
controls.zoomSpeed = 0.85;
controls.panSpeed = 0.7;
controls.minDistance = 24;
controls.maxDistance = 2200;
controls.maxPolarAngle = Math.PI * 0.495;
controls.minPolarAngle = 0.08;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.38;

const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

// ---------------------------------------------------------------------------
// Light rig — cool night key, warm rim, low ambient
// ---------------------------------------------------------------------------
const hemi = new THREE.HemisphereLight(0x9dc9ff, 0x060a0e, 0.28);
scene.add(hemi);

const key = new THREE.DirectionalLight(0xf5f9ff, 2.5);
key.position.set(-560, 620, 320);
scene.add(key);

const fill = new THREE.DirectionalLight(0x4f8fd8, 0.42);
fill.position.set(470, 230, 300);
scene.add(fill);

const rim = new THREE.DirectionalLight(0xffd4a0, 1.7);
rim.position.set(20, 360, -520);
scene.add(rim);

const under = new THREE.PointLight(0x2f86c8, 55, 420, 2.0);
under.position.set(0, 30, 0);
scene.add(under);

// ---------------------------------------------------------------------------
// Ground — this is context only, not part of the precision model
// ---------------------------------------------------------------------------
const ground = new THREE.Mesh(
  new THREE.CircleGeometry(920, 128),
  new THREE.MeshStandardMaterial({ color: 0x07111a, roughness: 0.92, metalness: 0.12 })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.02;
scene.add(ground);

// Soft cyan pool of light under the tower
function radialTexture(inner = 'rgba(70,170,230,0.26)', outer = 'rgba(0,0,0,0)') {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, inner);
  grad.addColorStop(0.55, inner.replace('0.26', '0.10'));
  grad.addColorStop(1, outer);
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}
const pool = new THREE.Mesh(
  new THREE.PlaneGeometry(290, 360),
  new THREE.MeshBasicMaterial({ map: radialTexture(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })
);
pool.rotation.x = -Math.PI / 2;
pool.position.y = 0.03;
scene.add(pool);

// Radial survey grid: rings + spokes
const grid = new THREE.Group();
const gridMat = new THREE.LineBasicMaterial({ color: 0x1a4560, transparent: true, opacity: 0.52 });
const gridMat2 = new THREE.LineBasicMaterial({ color: 0x2e7198, transparent: true, opacity: 0.30 });
for (let i = 1; i <= 14; i++) {
  const r = i * 58;
  const pts = [];
  const seg = 180;
  for (let j = 0; j <= seg; j++) {
    const a = j / seg * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * r, 0, Math.sin(a) * r));
  }
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const line = new THREE.Line(geo, i === 7 ? gridMat2 : gridMat);
  line.position.y = 0.01;
  grid.add(line);
}
for (let i = 0; i < 36; i++) {
  const a = i / 36 * Math.PI * 2;
  const pts = [new THREE.Vector3(Math.cos(a) * 70, 0.01, Math.sin(a) * 70),
               new THREE.Vector3(Math.cos(a) * 812, 0.01, Math.sin(a) * 812)];
  grid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), i % 3 === 0 ? gridMat2 : gridMat));
}
scene.add(grid);

// ---------------------------------------------------------------------------
// Loader
// ---------------------------------------------------------------------------
const loader = new GLTFLoader();
let model = null;
const layerGroups = {
  lattice: ['CFTColumns', 'RingBeams', 'DiagonalBraces', 'ConnectionGirders'],
  core: ['ConcreteCore'],
  floors: ['FloorSlabs'],
  crown: ['ObservationDeck'],
  antenna: ['AntennaMast'],
  podium: ['Podium'],
};
const state = {
  autoRotate: true,
  section: false,
  sectionValue: 0,
  visible: { lattice: true, core: true, floors: true, crown: true, antenna: true, podium: true },
};
const sectionPlane = new THREE.Plane(new THREE.Vector3(1, 0, 0), 0);
const clipMaterials = [];

function prepareModel(root) {
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.frustumCulled = true;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    const name = o.name || '';
    for (const m of mats) {
      m.envMapIntensity = 0.30;
      m.metalness = Math.min(m.metalness ?? 0.4, 0.48);
      m.roughness = Math.max(m.roughness ?? 0.4, 0.34);
      if (name === 'ConcreteCore') {
        m.color.setHex(0x5e5a50); m.metalness = 0.04; m.roughness = 0.86;
      } else if (name === 'FloorSlabs') {
        m.color.setHex(0x2b4c5e); m.metalness = 0.18; m.roughness = 0.56;
      } else if (name === 'ObservationDeck') {
        m.color.setHex(0x447f93); m.metalness = 0.22; m.roughness = 0.48;
      } else if (name === 'Podium') {
        m.color.setHex(0x42484d); m.metalness = 0.12; m.roughness = 0.82;
      } else if (name === 'AntennaMast') {
        m.color.setHex(0xdfe8ee); m.metalness = 0.55; m.roughness = 0.30;
      } else {
        m.color.setHex(0x8fa2b0); m.metalness = 0.52; m.roughness = 0.32;
      }
      m.needsUpdate = true;
      clipMaterials.push(m);
    }
  });
  scene.add(root);

  // gentle entrance
  root.position.y = -8;
  root.scale.setScalar(0.995);
  const t0 = performance.now();
  const ent = () => {
    const t = Math.min(1, (performance.now() - t0) / 1500);
    const e = 1 - Math.pow(1 - t, 3);
    root.position.y = -8 * (1 - e);
    root.scale.setScalar(0.995 + 0.005 * e);
    if (t < 1) requestAnimationFrame(ent);
  };
  ent();

  const box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3();
  box.getSize(size);
  $('#loading').classList.add('is-done');
  setTimeout(() => $('#loading').remove(), 900);
  window.__TOWER_READY__ = true;

  // Deep links: ?view=waist&section=1 — also useful for automated screenshots.
  const q = new URLSearchParams(location.search);
  const v = q.get('view');
  if (v && presets[v]) {
    flyTo(v, true);
    $$('[data-view]').forEach((x) => x.classList.remove('is-active'));
    const active = document.querySelector(`[data-view="${v}"]`);
    if (active) active.classList.add('is-active');
  }
  if (q.get('section') === '1') {
    state.section = true;
    state.sectionValue = Number(q.get('x') || 0);
    $('#section-range').value = String(state.sectionValue);
    $('#section-value').textContent = (state.sectionValue >= 0 ? '+' : '') + state.sectionValue + ' m · X normal';
    applySection();
  }
}

function fail(err) {
  console.error(err);
  const msg = (err && (err.stack || err.message)) ? String(err.stack || err.message) : String(err);
  $('#loading').innerHTML = '<div class="load-card"><div class="load-kicker">MODEL ERROR</div><div class="load-title">模型加载失败</div><p style="white-space:pre-wrap;text-align:left;max-height:40vh;overflow:auto">' + msg.replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])) + '</p></div>';
  window.__TOWER_ERROR__ = msg;
}

function decodeBase64(b64) {
  const bin = atob(b64);
  const len = bin.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i += 4096) {
    const end = Math.min(len, i + 4096);
    for (let j = i; j < end; j++) bytes[j] = bin.charCodeAt(j);
  }
  return bytes.buffer;
}

function loadModel() {
  const tag = document.getElementById('glb-b64');
  if (tag && tag.textContent.trim().length > 100) {
    try {
      const buf = decodeBase64(tag.textContent.trim());
      loader.parse(buf, '', (gltf) => prepareModel(gltf.scene), fail);
    } catch (e) { fail(e); }
  } else {
    const external = window.__GLB_URL__ || '../out/canton_tower_web.glb';
    loader.load(external, (gltf) => prepareModel(gltf.scene), undefined, fail);
  }
}
requestAnimationFrame(() => setTimeout(loadModel, 60));

// ---------------------------------------------------------------------------
// Layers
// ---------------------------------------------------------------------------
function setLayer(key, on) {
  state.visible[key] = on;
  for (const name of layerGroups[key]) {
    const obj = model && model.getObjectByName(name);
    if (obj) obj.visible = on;
  }
  $$(`[data-layer="${key}"]`).forEach((el) => {
    el.classList.toggle('is-off', !on);
    el.setAttribute('aria-pressed', String(on));
    const st = el.querySelector('.state');
    if (st) st.textContent = on ? 'ON' : 'OFF';
  });
}
$$('[data-layer]').forEach((btn) => {
  btn.addEventListener('click', () => setLayer(btn.dataset.layer, !state.visible[btn.dataset.layer]));
});

// ---------------------------------------------------------------------------
// Section clipping
// ---------------------------------------------------------------------------
function applySection() {
  sectionPlane.constant = -state.sectionValue;
  for (const m of clipMaterials) {
    m.clippingPlanes = state.section ? [sectionPlane] : [];
    m.clipShadows = false;
    m.needsUpdate = true;
  }
  $('#section-range').disabled = !state.section;
  $('#section-wrap').classList.toggle('is-active', state.section);
  $('#section-toggle').classList.toggle('on', state.section);
  $('#section-toggle').setAttribute('aria-pressed', String(state.section));
}
$('#section-toggle').addEventListener('click', () => {
  state.section = !state.section;
  applySection();
});
$('#section-range').addEventListener('input', (e) => {
  state.sectionValue = Number(e.target.value);
  $('#section-value').textContent = (state.sectionValue >= 0 ? '+' : '') + state.sectionValue.toFixed(0) + ' m';
  applySection();
});
applySection();

// ---------------------------------------------------------------------------
// Camera presets / auto rotate
// ---------------------------------------------------------------------------
const presets = {
  full:   { pos: [650, 340, 820], target: [0, 300, 0] },
  waist:  { pos: [180, 300, 250], target: [0, 280, 0] },
  crown:  { pos: [190, 455, 260], target: [0, 435, 0] },
  antenna:{ pos: [58, 560, 84],   target: [0, 532, 0] },
  base:   { pos: [230, 76, 300],  target: [0, 38, 0] },
};
let tween = null;
function flyTo(name, instant = false) {
  const p = presets[name];
  if (!p) return;
  if (instant) {
    camera.position.set(...p.pos);
    controls.target.set(...p.target);
    controls.update();
    return;
  }
  tween = {
    t0: performance.now(), dur: 1250,
    p0: camera.position.clone(), p1: new THREE.Vector3(...p.pos),
    q0: controls.target.clone(), q1: new THREE.Vector3(...p.target),
  };
}
$$('[data-view]').forEach((b) => b.addEventListener('click', () => {
  $$('[data-view]').forEach((x) => x.classList.remove('is-active'));
  b.classList.add('is-active');
  flyTo(b.dataset.view);
}));

$('#autorotate').addEventListener('click', () => {
  state.autoRotate = !state.autoRotate;
  controls.autoRotate = state.autoRotate;
  $('#autorotate').setAttribute('aria-pressed', String(state.autoRotate));
  $('#autorotate .switch').classList.toggle('on', state.autoRotate);
});

// reset
$('#reset').addEventListener('click', () => {
  $$('[data-view]').forEach((x) => x.classList.remove('is-active'));
  $('[data-view="full"]').classList.add('is-active');
  flyTo('full');
});

// ---------------------------------------------------------------------------
// Beacon and animation
// ---------------------------------------------------------------------------
const beacon = new THREE.Mesh(
  new THREE.SphereGeometry(0.95, 16, 12),
  new THREE.MeshBasicMaterial({ color: 0xff5a48, transparent: true })
);
beacon.position.set(0, 600.2, 0);
scene.add(beacon);
const beaconGlow = new THREE.Sprite(new THREE.SpriteMaterial({
  map: (() => {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d');
    const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, 'rgba(255,120,95,1)');
    gr.addColorStop(0.18, 'rgba(255,80,60,0.6)');
    gr.addColorStop(1, 'rgba(255,40,30,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  })(),
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
}));
beaconGlow.scale.setScalar(18);
beaconGlow.position.set(0, 600.2, 0);
scene.add(beaconGlow);
const beaconLight = new THREE.PointLight(0xff3b2e, 60, 42, 2);
beaconLight.position.set(0, 600.2, 0);
scene.add(beaconLight);

const clock = new THREE.Clock();
function animate() {
  const t = clock.getElapsedTime();
  controls.update();

  if (tween) {
    const k = Math.min(1, (performance.now() - tween.t0) / tween.dur);
    const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
    camera.position.lerpVectors(tween.p0, tween.p1, e);
    controls.target.lerpVectors(tween.q0, tween.q1, e);
    if (k >= 1) tween = null;
  }

  const pulse = 0.6 + 0.4 * Math.sin(t * 2.4);
  beacon.material.opacity = 0.45 + 0.55 * pulse;
  beacon.scale.setScalar(0.8 + 0.5 * pulse);
  beaconGlow.material.opacity = 0.35 + 0.55 * pulse;
  beaconLight.intensity = 25 + 70 * pulse;

  renderer.render(scene, camera);
}
renderer.setAnimationLoop(animate);

// ---------------------------------------------------------------------------
// Resize / keyboard
// ---------------------------------------------------------------------------
function resize() {
  const w = canvasHost.clientWidth || innerWidth;
  const h = canvasHost.clientHeight || innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}
addEventListener('resize', resize);
new ResizeObserver(resize).observe(canvasHost);

addEventListener('keydown', (e) => {
  if (e.key === 'r' || e.key === 'R') $('#reset').click();
  if (e.key === 'x' || e.key === 'X') $('#section-toggle').click();
  if (e.code === 'Space') { e.preventDefault(); $('#autorotate').click(); }
});

// Expose for headless checks
window.__TOWER = { scene, camera, controls, state, flyTo, applySection };
