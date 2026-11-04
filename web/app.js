import * as THREE from 'three/webgpu';
import {
  pass, mrt, output, transformedNormalView, ao, bloom, fxaa, dof, uniform,
} from 'three/tsl';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

// ---------------------------------------------------------------------------
// Runtime configuration / capability detection
// ---------------------------------------------------------------------------
const q = new URLSearchParams(location.search);
const caps = {
  webgpu: typeof navigator !== 'undefined' && !!navigator.gpu,
  webgl2: (() => {
    try {
      const c = document.createElement('canvas');
      return !!c.getContext('webgl2');
    } catch { return false; }
  })(),
  cores: navigator.hardwareConcurrency || null,
  memoryGB: navigator.deviceMemory || null,
  mobile: matchMedia('(pointer: coarse)').matches,
};
const FORCE_WEBGL = q.get('backend') === 'webgl' || !!window.__FORCE_WEBGL__;
const ASSET_BASE = window.__ASSET_BASE__ || './assets/';
const HDR_URL = window.__HDR_DATA__ || (ASSET_BASE + 'env/night_sky_1k.hdr');
const TEX_METAL_URL = window.__TEX_METAL_DATA__ || (ASSET_BASE + 'tex/metal_orm.png');
const TEX_CONCRETE_URL = window.__TEX_CONCRETE_DATA__ || (ASSET_BASE + 'tex/concrete_orm.png');
const GLB_URL = window.__GLB_URL__ || (ASSET_BASE + 'canton_tower_web.glb');

const LEVELS = {
  L0: { label: '基础', ibl: false, shadows: false, post: false, ssr: false, dof: false,
        exposure: 1.00, pixelCap: 1.00, shadowSize: 0, passes: 0, bloom: [0, 0, 1] },
  L1: { label: '增强', ibl: true, shadows: true, post: true, ssr: false, dof: false,
        exposure: 0.80, pixelCap: 1.50, shadowSize: 1024, passes: 3, bloom: [0.36, 0.40, 0.82] },
  L2: { label: '电影', ibl: true, shadows: true, post: true, ssr: false, dof: true,
        exposure: 0.76, pixelCap: 1.75, shadowSize: 2048, passes: 4, bloom: [0.50, 0.48, 0.72] },
};

const requestedLevel = (q.get('level') || 'L1').toUpperCase();
const state = {
  phase: 'boot',
  ready: false,
  backend: 'detecting',
  backendReason: '检测 navigator.gpu → WebGPU → WebGL2',
  backendForced: FORCE_WEBGL,
  level: LEVELS[requestedLevel] ? requestedLevel : 'L1',
  custom: false,
  config: { ibl: true, shadows: true, post: true, ssr: false },
  autoQuality: q.get('auto') !== '0',
  autoDowngrades: 0,
  lowSeconds: 0,
  fps: 0,
  pixelScale: 1,
  readyAt: 0,
  envReady: false,
  envFailed: false,
  texturesReady: false,
  modelLoaded: false,
  postOK: false,
  postPasses: 0,
  recovering: false,
  contextLossCount: 0,
  l2Fallback: false,
  autoRotate: true,
  section: false,
  sectionValue: 0,
  visible: { lattice: true, core: true, floors: true, crown: true, antenna: true, podium: true },
  frames: 0,
  qualityEpoch: 0,
  lastBudgetAt: 0,
};

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x040a10);
scene.environmentIntensity = 1.0;

function skyGradientTexture() {
  const c = document.createElement('canvas');
  c.width = 1024; c.height = 512;
  const g = c.getContext('2d');
  const grad = g.createLinearGradient(0, 0, 0, 512);
  grad.addColorStop(0.00, '#02060c');
  grad.addColorStop(0.42, '#0a2231');
  grad.addColorStop(0.58, '#2a5568');
  grad.addColorStop(0.66, '#1b3e50');
  grad.addColorStop(0.78, '#0a1a22');
  grad.addColorStop(1.00, '#020509');
  g.fillStyle = grad; g.fillRect(0, 0, 1024, 512);
  const warm = g.createRadialGradient(340, 300, 0, 340, 300, 380);
  warm.addColorStop(0, 'rgba(150,95,50,0.22)');
  warm.addColorStop(0.45, 'rgba(70,55,42,0.08)');
  warm.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = warm; g.fillRect(0, 0, 1024, 512);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.mapping = THREE.EquirectangularReflectionMapping;
  return tex;
}
const skyDome = new THREE.Mesh(
  new THREE.SphereGeometry(3000, 48, 24),
  new THREE.MeshBasicMaterial({ map: skyGradientTexture(), side: THREE.BackSide, depthWrite: false })
);
skyDome.renderOrder = -1000;
skyDome.frustumCulled = false;
scene.add(skyDome);

const camera = new THREE.PerspectiveCamera(36, innerWidth / innerHeight, 0.5, 5200);
camera.position.set(650, 340, 820);

const canvasHost = $('#stage');
const clock = new THREE.Clock();

let renderer = null;
let controls = null;
let model = null;
let envTexture = null;
let texMetal = null;
let texConcrete = null;
let post = null;
let scenePass = null;
let postFocus = null;
let tween = null;
let lastFpsAt = performance.now();
let fpsFrames = 0;
let lastAutoAt = 0;
let toastTimer = null;
const clipMaterials = [];
const modelMaterials = [];

// ---------------------------------------------------------------------------
// Scene / light rig / ground context
// ---------------------------------------------------------------------------
const hemi = new THREE.HemisphereLight(0x9dc9ff, 0x060a0e, 0.40);
scene.add(hemi);

const key = new THREE.DirectionalLight(0xf5f9ff, 1.95);
key.position.set(-430, 620, 360);
key.target.position.set(0, 260, 0);
key.castShadow = true;
key.shadow.mapSize.set(1024, 1024);
key.shadow.camera.left = -520;
key.shadow.camera.right = 520;
key.shadow.camera.top = 520;
key.shadow.camera.bottom = -520;
key.shadow.camera.near = 1;
key.shadow.camera.far = 3000;
key.shadow.camera.updateProjectionMatrix();
key.shadow.bias = -0.0007;
key.shadow.normalBias = 0.9;
scene.add(key, key.target);

const fill = new THREE.DirectionalLight(0x4f8fd8, 0.55);
fill.position.set(470, 230, 300);
scene.add(fill);

const rim = new THREE.DirectionalLight(0xffc58a, 1.35);
rim.position.set(20, 360, -520);
scene.add(rim);

const under = new THREE.PointLight(0x2f86c8, 55, 420, 2.0);
under.position.set(0, 30, 0);
scene.add(under);

const ground = new THREE.Mesh(
  new THREE.CircleGeometry(920, 128),
  new THREE.MeshStandardMaterial({ color: 0x08141d, roughness: 0.9, metalness: 0.12 })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.02;
ground.receiveShadow = true;
scene.add(ground);

function baseGroundTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const g = c.getContext('2d');
  const r = g.createRadialGradient(256, 256, 4, 256, 256, 256);
  r.addColorStop(0.00, 'rgba(0,0,0,0.66)');
  r.addColorStop(0.30, 'rgba(0,0,0,0.48)');
  r.addColorStop(0.47, 'rgba(0,0,0,0.12)');
  r.addColorStop(0.54, 'rgba(0,0,0,0.00)');
  r.addColorStop(0.64, 'rgba(55,155,215,0.08)');
  r.addColorStop(0.80, 'rgba(35,105,160,0.06)');
  r.addColorStop(1.00, 'rgba(0,0,0,0.00)');
  g.fillStyle = r;
  g.fillRect(0, 0, 512, 512);
  return new THREE.CanvasTexture(c);
}
// One plane only: contact shadow + cool ground glow.  Two overlapping
// transparent planes caused depth-quantisation bow-ties at architectural scale.
const basePlane = new THREE.Mesh(
  new THREE.PlaneGeometry(245, 300),
  new THREE.MeshBasicMaterial({
    map: baseGroundTexture(), transparent: true, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
  })
);
basePlane.rotation.x = -Math.PI / 2;
basePlane.position.y = 0.25;
basePlane.renderOrder = 2;
scene.add(basePlane);

const grid = new THREE.Group();
const gridMat = new THREE.LineBasicMaterial({ color: 0x1a4560, transparent: true, opacity: 0.52 });
const gridMat2 = new THREE.LineBasicMaterial({ color: 0x2e7198, transparent: true, opacity: 0.30 });
for (let i = 1; i <= 14; i++) {
  const r = i * 58;
  const pts = [];
  for (let j = 0; j <= 180; j++) {
    const a = j / 180 * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * r, 0, Math.sin(a) * r));
  }
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), i === 7 ? gridMat2 : gridMat);
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

// Aviation beacon
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
beaconGlow.scale.setScalar(11);
beaconGlow.position.set(0, 600.2, 0);
scene.add(beaconGlow);
const beaconLight = new THREE.PointLight(0xff3b2e, 45, 42, 2);
beaconLight.position.set(0, 600.2, 0);
scene.add(beaconLight);

// ---------------------------------------------------------------------------
// Renderer creation + automatic WebGPU → WebGL2 fallback
// ---------------------------------------------------------------------------
const stageSize = () => ({
  w: canvasHost.clientWidth || innerWidth,
  h: canvasHost.clientHeight || innerHeight,
});

function pixelRatioForLevel() {
  const level = LEVELS[state.level] || LEVELS.L1;
  const deviceCap = state.mobile ? Math.min(devicePixelRatio || 1, level.pixelCap * 0.8) : Math.min(devicePixelRatio || 1, level.pixelCap);
  return Math.max(0.65, deviceCap * state.pixelScale);
}

async function createRenderer(forceWebGL) {
  const r = new THREE.WebGPURenderer({
    antialias: true,
    alpha: false,
    powerPreference: 'high-performance',
    forceWebGL,
  });
  const { w, h } = stageSize();
  r.setPixelRatio(pixelRatioForLevel());
  r.setSize(w, h);
  r.toneMapping = THREE.ACESFilmicToneMapping;
  r.toneMappingExposure = (LEVELS[state.level] || LEVELS.L1).exposure;
  r.outputColorSpace = THREE.SRGBColorSpace;
  r.shadowMap.enabled = state.config.shadows;
  r.shadowMap.type = THREE.PCFSoftShadowMap;
  r.setClearColor(0x040a10, 1);
  await r.init();
  return r;
}

function canvasLabel(backend) {
  return backend === 'WEBGPU' ? 'WebGPU' : 'WebGL2';
}

function backendMetaText() {
  if (state.backend === 'WEBGPU') return 'WebGPU adapter active · TSL/Node postprocessing';
  if (state.backendForced && FORCE_WEBGL) return '验收参数 backend=webgl 强制 WebGL2';
  if (!caps.webgpu) return 'navigator.gpu 不可用 → WebGL2 自动回退';
  return 'WebGPU 适配器/上下文不可用 → WebGL2 自动回退';
}

async function initRenderer() {
  let created = null;
  let reason = '';
  try {
    created = await createRenderer(FORCE_WEBGL || !caps.webgpu);
  } catch (e) {
    console.warn('WebGPURenderer init failed, retrying with WebGL2', e);
    reason = 'WebGPU 初始化失败，正在回退 WebGL2';
    try {
      created = await createRenderer(true);
    } catch (e2) {
      throw new Error('WebGPU 与 WebGL2 初始化均失败：' + (e2?.message || e2));
    }
  }
  renderer = created;
  state.backend = renderer.backend?.isWebGPUBackend ? 'WEBGPU' : 'WEBGL2';
  state.backendForced = state.backend === 'WEBGL2';
  state.backendReason = reason || backendMetaText();
  renderer.domElement.setAttribute('aria-label', '广州塔三维模型');
  renderer.domElement.style.touchAction = 'none';
  canvasHost.appendChild(renderer.domElement);
  bindControls();
  installContextHandlers();
  updateBackendUI();
}

function bindControls() {
  if (!renderer) return;
  if (controls) controls.dispose();
  controls = new OrbitControls(camera, renderer.domElement);
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
  controls.autoRotate = state.autoRotate;
  controls.autoRotateSpeed = 0.38;
  controls.update();
}

function installContextHandlers() {
  const canvas = renderer.domElement;
  canvas.addEventListener('webglcontextlost', (e) => {
    e.preventDefault();
    recoverRenderer('WebGL context lost');
  }, false);
  const device = renderer.backend?.device;
  if (device?.lost) {
    device.lost.then((info) => {
      if (state.backend === 'WEBGPU' && !state.recovering) {
        recoverRenderer('WebGPU device lost: ' + (info?.reason || 'unknown'));
      }
    });
  }
}

async function recoverRenderer(reason) {
  if (state.recovering) return;
  state.recovering = true;
  state.contextLossCount++;
  showToast('渲染后端丢失，正在自动回退 WebGL2…', true);
  try {
    if (renderer) {
      renderer.setAnimationLoop(null);
      if (post && post.dispose) post.dispose();
      post = null;
      scenePass = null;
      if (controls) controls.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    }
    renderer = await createRenderer(true);
    state.backend = 'WEBGL2';
    state.backendForced = true;
    state.backendReason = '运行时上下文丢失 → 自动回退 WebGL2：' + reason;
    renderer.domElement.setAttribute('aria-label', '广州塔三维模型');
    canvasHost.appendChild(renderer.domElement);
    bindControls();
    installContextHandlers();
    updateBackendUI();
    applyRealism();
    window.__LOAD_STAGE__ = 'post-ready';
    setLoadDetail('Post pipeline built · first frame');
    startLoop();
    state.recovering = false;
    if (state.contextLossCount > 1) {
      showToast('WebGL2 上下文再次丢失；请刷新页面。', true);
    } else {
      showToast('已自动切换到 WebGL2，场景继续显示。', true);
    }
  } catch (e) {
    state.recovering = false;
    fatal('渲染后端恢复失败：' + (e?.message || e));
  }
}

// ---------------------------------------------------------------------------
// Assets: generated HDR environment, ORM textures, GLB
// ---------------------------------------------------------------------------
function loadTexture(url) {
  return new Promise((resolve, reject) => {
    new THREE.TextureLoader().load(url, resolve, undefined, reject);
  });
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

function loadGLB() {
  const loader = new GLTFLoader();
  const tag = document.getElementById('glb-b64');
  if (tag && tag.textContent.trim().length > 100) {
    return new Promise((resolve, reject) => {
      try {
        loader.parse(decodeBase64(tag.textContent.trim()), '', resolve, reject);
      } catch (e) { reject(e); }
    });
  }
  return new Promise((resolve, reject) => {
    loader.load(GLB_URL, resolve, (ev) => {
      if (ev.total) {
        const pct = Math.min(99, Math.round(ev.loaded / ev.total * 100));
        setLoadDetail(`加载 GLB ${pct}% · Web LOD 30 mm`);
      }
    }, reject);
  });
}

function addUVs(geom) {
  if (!geom || !geom.attributes || !geom.attributes.position) return;
  if (geom.attributes.uv) return;
  const pos = geom.attributes.position;
  const uv = new Float32Array(pos.count * 2);
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
    uv[i * 2] = (x + z * 0.35) * 0.034;
    uv[i * 2 + 1] = (y + x * 0.18) * 0.034;
  }
  geom.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
}

function materialBaseFor(name) {
  if (name === 'ConcreteCore') return { color: 0x77705f, metalness: 0.04, roughness: 0.86, map: 'concrete' };
  if (name === 'FloorSlabs') return { color: 0x2b4c5e, metalness: 0.18, roughness: 0.56, map: 'concrete' };
  if (name === 'ObservationDeck') return { color: 0x447f93, metalness: 0.22, roughness: 0.48, map: 'concrete' };
  if (name === 'Podium') return { color: 0x42484d, metalness: 0.12, roughness: 0.82, map: 'concrete' };
  if (name === 'AntennaMast') return { color: 0xdfe8ee, metalness: 0.55, roughness: 0.30, map: 'metal' };
  return { color: 0x8497a5, metalness: 0.52, roughness: 0.32, map: 'metal' };
}

function applyMaterialMaps() {
  const high = state.level !== 'L0';
  for (const entry of modelMaterials) {
    const { material, base, kind } = entry;
    const map = kind === 'concrete' ? texConcrete : texMetal;
    const enabled = high && !!map;
    material.roughnessMap = enabled ? map : null;
    material.metalnessMap = enabled ? map : null;
    material.roughness = enabled ? 1.0 : base.roughness;
    material.metalness = enabled ? 1.0 : base.metalness;
    material.envMapIntensity = enabled ? 0.82 : 0.18;
    material.needsUpdate = true;
  }
}

function prepareModel(root) {
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = true;
    o.receiveShadow = true;
    o.frustumCulled = true;
    addUVs(o.geometry);
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    for (const m of mats) {
      const baseSpec = materialBaseFor(o.name);
      m.color.setHex(baseSpec.color);
      m.metalness = baseSpec.metalness;
      m.roughness = baseSpec.roughness;
      m.envMapIntensity = 0.82;
      m.needsUpdate = true;
      modelMaterials.push({ material: m, base: { metalness: baseSpec.metalness, roughness: baseSpec.roughness }, kind: baseSpec.map });
      clipMaterials.push(m);
    }
  });
  model = root;
  scene.add(root);

  // entrance
  const t0 = performance.now();
  const ent = () => {
    const t = Math.min(1, (performance.now() - t0) / 1200);
    const e = 1 - Math.pow(1 - t, 3);
    root.position.y = -8 * (1 - e);
    root.scale.setScalar(0.995 + 0.005 * e);
    if (t < 1) requestAnimationFrame(ent);
  };
  ent();

  state.modelLoaded = true;
  applyMaterialMaps();
  setLoadDetail('GLB parsed · applying PBR materials');
  window.__LOAD_STAGE__ = 'model-ready';
}

async function loadAssets() {
  setLoadDetail('加载生成式 HDR IBL · 2.0 MB');
  const envPromise = new RGBELoader().loadAsync(HDR_URL).then((t) => {
    t.mapping = THREE.EquirectangularReflectionMapping;
    envTexture = t;
    state.envReady = true;
    return t;
  }).catch((e) => {
    state.envFailed = true;
    console.warn('HDR IBL load failed', e);
    return null;
  });

  const texPromise = Promise.allSettled([
    loadTexture(TEX_METAL_URL),
    loadTexture(TEX_CONCRETE_URL),
  ]).then(([a, b]) => {
    if (a.status === 'fulfilled') {
      texMetal = a.value;
      texMetal.colorSpace = THREE.NoColorSpace;
      texMetal.wrapS = texMetal.wrapT = THREE.RepeatWrapping;
      texMetal.anisotropy = 4;
    }
    if (b.status === 'fulfilled') {
      texConcrete = b.value;
      texConcrete.colorSpace = THREE.NoColorSpace;
      texConcrete.wrapS = texConcrete.wrapT = THREE.RepeatWrapping;
      texConcrete.anisotropy = 4;
    }
    state.texturesReady = !!(texMetal && texConcrete);
  });

  setLoadDetail('加载 GLB · Web LOD 30 mm · 约 380 k triangles');
  const glbPromise = loadGLB().then((gltf) => {
    prepareModel(gltf.scene);
    return gltf;
  });

  envPromise.then(() => { if (state.envReady) setLoadDetail('HDR IBL ready · waiting for model'); });
  texPromise.then(() => { if (state.texturesReady) setLoadDetail('ORM maps ready · waiting for model'); });
  glbPromise.then(() => { setLoadDetail('GLB parsed · waiting for environment'); });
  await Promise.all([envPromise, texPromise, glbPromise]);
  window.__LOAD_STAGE__ = 'assets-ready';
  setLoadDetail('Assets ready · building post pipeline');
  if (state.envFailed) {
    state.config.ibl = false;
    showToast('HDR IBL 加载失败：L1 材质仍可用，已自动关闭 IBL。', true);
  }
  if (!state.texturesReady) {
    showToast('ORM 贴图不可用：已回退到参数化 PBR 材质。', true);
  }
}

// ---------------------------------------------------------------------------
// Realism / postprocessing
// ---------------------------------------------------------------------------
function applyIBL() {
  const use = state.config.ibl && !!envTexture;
  scene.environment = use ? envTexture : null;
  scene.environmentIntensity = use ? 1.0 : 0.0;
  // Keep the authored night-sky dome as the visible background; the HDR is
  // used for image-based lighting only.  This keeps the UI palette stable and
  // avoids washing the model in a bright equirect background.
  scene.background = null;
  skyDome.visible = true;
  applyMaterialMaps();
}

function applyLights() {
  const level = state.level;
  if (level === 'L0') {
    hemi.intensity = 0.50;
    key.intensity = 2.30;
    fill.intensity = 0.0;
    rim.intensity = 0.0;
    under.intensity = 0.0;
    beaconLight.visible = false;
  } else {
    hemi.intensity = 0.42;
    key.intensity = 1.95;
    fill.intensity = 0.45;
    rim.intensity = level === 'L2' ? 1.55 : 1.45;
    under.intensity = 55;
    beaconLight.visible = true;
  }
}

function shadowSizeForLevel() {
  return LEVELS[state.level]?.shadowSize ?? 1024;
}

function applyShadows() {
  const enabled = state.config.shadows;
  renderer.shadowMap.enabled = enabled;
  key.castShadow = enabled;
  if (enabled) {
    const size = shadowSizeForLevel();
    if (key.shadow.mapSize.x !== size) {
      key.shadow.mapSize.set(size, size);
      if (key.shadow.map) {
        key.shadow.map.dispose();
        key.shadow.map = null;
      }
    }
    key.shadow.camera.updateProjectionMatrix();
    key.shadow.needsUpdate = true;
    renderer.shadowMap.needsUpdate = true;
    if (model) model.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  } else {
    if (model) model.traverse((o) => { if (o.isMesh) o.castShadow = false; });
  }
}

function applyPixelRatio() {
  if (!renderer) return;
  const pr = pixelRatioForLevel();
  renderer.setPixelRatio(pr);
  const { w, h } = stageSize();
  renderer.setSize(w, h, false);
}

function disposePost() {
  if (post && post.dispose) {
    try { post.dispose(); } catch {}
  }
  if (scenePass && scenePass.dispose) {
    try { scenePass.dispose(); } catch {}
  }
  post = null;
  scenePass = null;
  state.postOK = false;
}

function rebuildPost() {
  disposePost();
  postFocus = null;
  if (!state.config.post) {
    state.postPasses = 0;
    updateRenderUI();
    return;
  }
  try {
    post = new THREE.PostProcessing(renderer);
    scenePass = pass(scene, camera);
    scenePass.setMRT(mrt({ output, normal: transformedNormalView }));
    const color = scenePass.getTextureNode('output');
    const depth = scenePass.getTextureNode('depth');
    const normal = scenePass.getTextureNode('normal');
    const aoPass = ao(depth, normal, camera);
    if (aoPass.SAMPLES) aoPass.SAMPLES.value = state.level === 'L2' ? 24 : 16;
    let out = color.mul(aoPass.getTextureNode());

    const [bs, br, bt] = LEVELS[state.level].bloom;
    const bloomPass = bloom(out, bs * 0.9, br, bt);
    out = out.add(bloomPass);

    if (state.level === 'L2') {
      postFocus = uniform(900);
      const aperture = uniform(0.0000012);
      const maxblur = uniform(0.0035);
      out = dof(out, scenePass.getViewZNode(), postFocus, aperture, maxblur);
    }

    post.outputNode = fxaa(out);
    post.needsUpdate = true;
    state.postOK = true;
    state.postPasses = state.level === 'L2' ? 4 : 3;
    updateRenderUI();
  } catch (e) {
    console.warn('Postprocessing unavailable', e);
    state.postOK = false;
    state.postPasses = 0;
    post = null;
    updateRenderUI();
    if (state.level === 'L2' && !state.l2Fallback) {
      state.l2Fallback = true;
      showToast('L2 DoF/后处理初始化失败，已自动降级到 L1。', true);
      setLevel('L1', { auto: true, silent: true });
    } else {
      showToast('后处理不可用，已回退到直接渲染。', true);
      state.config.post = false;
      updateRenderUI();
    }
  }
}

function applyRealism() {
  if (!renderer) return;
  const level = LEVELS[state.level] || LEVELS.L1;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMappingExposure = level.exposure;
  applyPixelRatio();
  applyLights();
  applyIBL();
  applyShadows();
  rebuildPost();
  updateRenderUI();
}

function setLevel(level, opts = {}) {
  if (!LEVELS[level]) return;
  state.qualityEpoch++;
  state.level = level;
  state.l2Fallback = false;
  state.levelSetAt = performance.now();
  state.custom = false;
  const p = LEVELS[level];
  state.config = { ibl: p.ibl, shadows: p.shadows, post: p.post, ssr: false };
  state.pixelScale = 1;
  state.lowSeconds = 0;
  state.lastBudgetAt = performance.now();
  state.autoDowngrades = opts.auto ? state.autoDowngrades + 1 : state.autoDowngrades;
  if (opts.auto) {
    showToast(`FPS 低于预算，已自动降级到 ${level}。`, true);
  }
  if (opts.silent !== true) updateRenderUI();
  applyRealism();
}

function setConfig(keyName, value) {
  if (keyName === 'ssr') return;
  state.qualityEpoch++;
  state.config[keyName] = value;
  state.custom = true;
  state.lowSeconds = 0;
  if (keyName === 'post') {
    rebuildPost();
  } else if (keyName === 'ibl') {
    applyIBL();
  } else if (keyName === 'shadows') {
    applyShadows();
  }
  updateRenderUI();
}

function updateFocus() {
  if (postFocus) {
    postFocus.value = camera.position.distanceTo(controls?.target || new THREE.Vector3(0, 300, 0));
  }
}

// ---------------------------------------------------------------------------
// Render loop / quality budget
// ---------------------------------------------------------------------------
function renderFrame() {
  if (!renderer) return;
  const t = clock.getElapsedTime();
  controls.update();
  updateFocus();

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

  if (state.postOK && post) post.render();
  else renderer.render(scene, camera);

  state.frames++;
  updateFPS();
  if (state.ready && state.autoQuality) evaluateBudget();
  if (state.modelLoaded && state.frames > 2 && !state.ready) {
    state.ready = true;
    state.phase = 'ready';
    state.readyAt = performance.now();
    $('#loading').classList.add('is-done');
    setTimeout(() => { const el = $('#loading'); if (el) el.remove(); }, 900);
    window.__TOWER_READY__ = true;
    window.__RENDER_READY__ = true;
  }
}

function startLoop() {
  if (!renderer) return;
  renderer.setAnimationLoop(renderFrame);
}

function updateFPS() {
  const now = performance.now();
  fpsFrames++;
  if (now - lastFpsAt >= 1000) {
    state.fps = Math.round(fpsFrames * 1000 / (now - lastFpsAt));
    fpsFrames = 0;
    lastFpsAt = now;
    $('#perf-fps').textContent = state.fps || '–';
    $('#fps-badge').textContent = state.fps ? `${state.fps} FPS` : '-- FPS';
    $('#chip-fps').textContent = state.fps || '–';
  }
}

function evaluateBudget() {
  const now = performance.now();
  if (now - state.readyAt < 6000) return;
  if (now - state.lastBudgetAt < 1000) return;
  state.lastBudgetAt = now;
  if (state.fps > 0 && state.fps < 30) {
    state.lowSeconds++;
  } else {
    state.lowSeconds = 0;
  }
  if (state.lowSeconds < 3) return;
  if (performance.now() - lastAutoAt < 8000) return;
  lastAutoAt = performance.now();
  state.lowSeconds = 0;
  if (state.level === 'L2') {
    setLevel('L1', { auto: true });
  } else if (state.level === 'L1') {
    setLevel('L0', { auto: true });
  } else {
    if (state.pixelScale > 0.7) {
      state.pixelScale = Math.max(0.7, state.pixelScale - 0.15);
      applyPixelRatio();
      showToast(`L0 仍低于 30 FPS：像素比降至 ${pixelRatioForLevel().toFixed(2)}×。`, true);
    } else if (state.config.post) {
      state.config.post = false;
      rebuildPost();
      showToast('L0 仍低于 30 FPS：已关闭后处理。', true);
    }
  }
  updateRenderUI();
}

// ---------------------------------------------------------------------------
// UI / backend / realism
// ---------------------------------------------------------------------------
function updateBackendUI() {
  const isGPU = state.backend === 'WEBGPU';
  const isGL = state.backend === 'WEBGL2';
  const label = isGPU ? 'WEBGPU' : isGL ? 'WEBGL2' : 'DETECTING';
  $('#backend-badge-label').textContent = label;
  $('#backend-name').textContent = label === 'DETECTING' ? '检测中…' : label;
  $('#backend-tag').textContent = isGPU ? 'GPU' : isGL ? 'FALLBACK' : 'INIT';
  $('#backend-meta').textContent = state.backendReason || backendMetaText();
  $('#backend-dot').className = 'backend-dot';
  $('#backend-led').className = 'backend-led';
  const b = $('#backend-badge');
  b.classList.toggle('is-gpu', isGPU);
  b.classList.toggle('is-gl', isGL);
  b.classList.toggle('is-fail', state.backend === 'FAIL');
  if (isGPU) { $('#backend-dot').classList.add('is-gpu'); $('#backend-led').classList.add('is-gpu'); }
  if (isGL) { $('#backend-dot').classList.add('is-gl'); $('#backend-led').classList.add('is-gl'); }
  if (state.backend === 'FAIL') { $('#backend-dot').classList.add('is-fail'); $('#backend-led').classList.add('is-fail'); }
  $('#chip-backend').textContent = label;
  $('#chip-level').textContent = state.level;
}

function levelCopy() {
  if (state.custom) return `${state.level} 自定义组合`;
  if (state.level === 'L0') return 'L0 基础：PBR 参数 · 单方向光 · 阴影/后处理关闭';
  if (state.level === 'L1') return 'L1 增强：HDR IBL · PCF 软阴影 · GTAO + Bloom · FXAA · ACES';
  return 'L2 电影：L1 + DoF · 2048² 阴影 · 24-sample AO · 轻量颗粒';
}

function updateRenderUI() {
  $('#level-badge').textContent = state.level;
  $('#chip-level').textContent = state.level;
  for (const btn of $$('#level-seg button')) {
    const active = btn.dataset.level === state.level && !state.custom;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-pressed', String(active));
  }
  $('#level-note').textContent = levelCopy();
  for (const [id, on] of [['sw-ibl', state.config.ibl], ['sw-shadows', state.config.shadows], ['sw-post', state.config.post], ['sw-auto', state.autoQuality]]) {
    const el = $('#' + id);
    if (!el) continue;
    el.classList.toggle('on', !!on);
    el.setAttribute('aria-pressed', String(!!on));
  }
  $('#sw-ssr').classList.remove('on');
  const pr = pixelRatioForLevel();
  $('#perf-dpr').textContent = pr.toFixed(2) + '×';
  const sz = state.config.shadows ? shadowSizeForLevel() : 0;
  $('#perf-shadow').textContent = sz ? `${sz}²` : 'OFF';
  $('#perf-passes').textContent = state.postPasses || (state.config.post ? 0 : 0);
  $('#render-note').textContent = state.backend === 'WEBGPU'
    ? 'WebGPU 是渲染后端，不是真实感开关。L1/L2 的差异来自 IBL、阴影、AO、Bloom、DoF 与色彩管理。'
    : 'WebGL2 自动回退仍使用同一套 TSL 后处理。WebGPU / WebGL 只是后端，真实感由开关决定。';
  updateQualityWarning();
}

function updateQualityWarning() {
  const el = $('#quality-warning');
  const notes = [];
  if (state.backend === 'WEBGL2') notes.push('WebGL2 回退模式；L2 可用，但受 GPU/驱动限制。');
  if (state.envFailed) notes.push('HDR IBL 加载失败，已关闭 IBL。');
  if (!state.texturesReady) notes.push('ORM 贴图不可用，已回退参数材质。');
  if (state.autoDowngrades > 0) notes.push(`质量预算保护已触发 ${state.autoDowngrades} 次。`);
  if (state.l2Fallback) notes.push('L2 后处理不可用，已降到 L1。');
  if (caps.cores && caps.cores <= 4) notes.push('低核心数设备：默认 L1，FPS <30 连续 3 秒会自动降级。');
  if (!notes.length) { el.hidden = true; el.textContent = ''; }
  else { el.hidden = false; el.textContent = notes.join(' '); }
}

function showToast(msg, warn = false) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle('is-warn', warn);
  el.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('is-visible'), 4200);
}

function setLoadDetail(msg) {
  const el = $('#load-detail');
  if (el) el.textContent = msg;
}

function fatal(msg) {
  console.error(msg);
  window.__TOWER_ERROR__ = msg;
  const loading = $('#loading');
  if (loading) {
    loading.innerHTML = `<div class="load-card"><div class="load-kicker">RENDER ERROR</div><div class="load-title">渲染初始化失败</div><p>${String(msg).replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</p><p>请使用支持 WebGL2 的浏览器，或通过 HTTP/HTTPS 打开页面。</p></div>`;
    loading.classList.remove('is-done');
  }
  state.phase = 'error';
}

// ---------------------------------------------------------------------------
// UI bindings
// ---------------------------------------------------------------------------
function setTab(name) {
  for (const btn of $$('.control-tab')) {
    const on = btn.dataset.tab === name;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', String(on));
  }
  $('#tab-render').classList.toggle('is-hidden', name !== 'render');
  $('#tab-view').classList.toggle('is-hidden', name !== 'view');
}
$$('.control-tab').forEach((b) => b.addEventListener('click', () => setTab(b.dataset.tab)));

for (const btn of $$('#level-seg button')) {
  btn.addEventListener('click', () => {
    state.l2Fallback = false;
    setLevel(btn.dataset.level);
  });
}
for (const id of ['sw-ibl', 'sw-shadows', 'sw-post']) {
  $('#' + id).addEventListener('click', () => {
    const keyName = id === 'sw-ibl' ? 'ibl' : id === 'sw-shadows' ? 'shadows' : 'post';
    setConfig(keyName, !state.config[keyName]);
  });
}
$('#sw-auto').addEventListener('click', () => {
  state.autoQuality = !state.autoQuality;
  updateRenderUI();
  showToast(state.autoQuality ? '自动性能降级已开启。' : '自动性能降级已关闭。');
});
$('#ssr-row').addEventListener('click', () => {
  showToast('SSR 在当前跨后端管线中未启用；L2 使用 DoF + 高质量 AO 作为替代。', true);
});

const presets = {
  full:   { pos: [650, 340, 820], target: [0, 300, 0] },
  waist:  { pos: [180, 300, 250], target: [0, 280, 0] },
  crown:  { pos: [190, 455, 260], target: [0, 435, 0] },
  antenna:{ pos: [58, 560, 84],   target: [0, 532, 0] },
  base:   { pos: [230, 76, 300],  target: [0, 38, 0] },
};
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
for (const b of $$('[data-view]')) {
  b.addEventListener('click', () => {
    for (const x of $$('[data-view]')) x.classList.remove('is-active');
    b.classList.add('is-active');
    flyTo(b.dataset.view);
  });
}
$('#reset').addEventListener('click', () => {
  for (const x of $$('[data-view]')) x.classList.remove('is-active');
  $('[data-view="full"]').classList.add('is-active');
  flyTo('full');
});
$('#autorotate').addEventListener('click', () => {
  state.autoRotate = !state.autoRotate;
  controls.autoRotate = state.autoRotate;
  $('#autorotate').classList.toggle('on', state.autoRotate);
  $('#autorotate').setAttribute('aria-pressed', String(state.autoRotate));
});

function setLayer(keyName, on) {
  state.visible[keyName] = on;
  const groups = {
    lattice: ['CFTColumns', 'RingBeams', 'DiagonalBraces', 'ConnectionGirders'],
    core: ['ConcreteCore'], floors: ['FloorSlabs'], crown: ['ObservationDeck'],
    antenna: ['AntennaMast'], podium: ['Podium'],
  };
  for (const n of groups[keyName] || []) {
    const obj = model && model.getObjectByName(n);
    if (obj) obj.visible = on;
  }
  for (const el of $$(`[data-layer="${keyName}"]`)) {
    el.classList.toggle('is-off', !on);
    el.setAttribute('aria-pressed', String(on));
    const st = el.querySelector('.state');
    if (st) st.textContent = on ? 'ON' : 'OFF';
  }
}
for (const b of $$('[data-layer]')) {
  b.addEventListener('click', () => setLayer(b.dataset.layer, !state.visible[b.dataset.layer]));
}

const sectionPlane = new THREE.Plane(new THREE.Vector3(1, 0, 0), 0);
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
$('#section-toggle').addEventListener('click', () => { state.section = !state.section; applySection(); });
$('#section-range').addEventListener('input', (e) => {
  state.sectionValue = Number(e.target.value);
  $('#section-value').textContent = (state.sectionValue >= 0 ? '+' : '') + state.sectionValue.toFixed(0) + ' m';
  applySection();
});
applySection();

function resize() {
  if (!renderer) return;
  const { w, h } = stageSize();
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  applyPixelRatio();
  renderer.setSize(w, h, false);
}
addEventListener('resize', resize);
new ResizeObserver(resize).observe(canvasHost);

addEventListener('keydown', (e) => {
  if (e.key === 'r' || e.key === 'R') $('#reset').click();
  if (e.key === 'x' || e.key === 'X') $('#section-toggle').click();
  if (e.code === 'Space') { e.preventDefault(); $('#autorotate').click(); }
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function boot() {
  try {
    setTab('render');
    setLoadDetail('初始化渲染后端 · 检测 WebGPU / WebGL2');
    updateBackendUI();
    await initRenderer();
    setLoadDetail(`后端 ${canvasLabel(state.backend)} 就绪 · 加载 HDR / GLB`);
    await loadAssets();
    if (q.get('ibl') === '0') state.config.ibl = false;
    if (q.get('shadows') === '0') state.config.shadows = false;
    if (q.get('post') === '0') state.config.post = false;
    if (state.level === 'L0') state.config = { ibl: false, shadows: false, post: false, ssr: false };
    if (q.get('view') && presets[q.get('view')]) {
      flyTo(q.get('view'), true);
      for (const x of $$('[data-view]')) x.classList.remove('is-active');
      const active = document.querySelector(`[data-view="${q.get('view')}"]`);
      if (active) active.classList.add('is-active');
    }
    if (q.get('section') === '1') {
      state.section = true;
      state.sectionValue = Number(q.get('x') || 0);
      $('#section-range').value = String(state.sectionValue);
      $('#section-value').textContent = (state.sectionValue >= 0 ? '+' : '') + state.sectionValue + ' m · X normal';
      applySection();
    }
    // Progressive first paint: render with the L0 material/shadow/post budget
    // first, hide the loading overlay, then compile/activate the requested L1/L2
    // pipeline.  Slow software drivers otherwise look "hung" during shader compile.
    const targetLevel = state.level;
    state.level = 'L0';
    state.config = { ibl: false, shadows: false, post: false, ssr: false };
    applyPixelRatio();
    renderer.toneMappingExposure = LEVELS.L0.exposure;
    applyLights();
    applyIBL();
    applyMaterialMaps();
    applyShadows();
    state.postOK = false;
    state.postPasses = 0;
    window.__LOAD_STAGE__ = 'first-paint';
    setLoadDetail('First paint · L0 bootstrap');
    const bootEpoch = ++state.qualityEpoch;
    startLoop();
    const activateQuality = () => {
      if (bootEpoch !== state.qualityEpoch) return;
      if (!state.ready) { setTimeout(activateQuality, 180); return; }
      state.level = targetLevel;
      state.custom = false;
      const p = LEVELS[state.level] || LEVELS.L1;
      state.config = { ibl: p.ibl, shadows: p.shadows, post: p.post, ssr: false };
      updateRenderUI();
      applyRealism();
      window.__LOAD_STAGE__ = 'post-ready';
      setTimeout(() => {
        if (state.ready) showToast('渲染就绪：' + state.backend + ' · ' + state.level + (state.backend === 'WEBGL2' ? ' · WebGL2 回退' : ''), false);
      }, 1400);
    };
    setTimeout(activateQuality, 900);
    window.__RENDER__ = {
      get backend() { return state.backend; },
      get level() { return state.level; },
      get config() { return { ...state.config }; },
      get fps() { return state.fps; },
      get postOK() { return state.postOK; },
      get state() { return { ...state, config: { ...state.config } }; },
      get scene() { return scene; },
      get renderer() { return renderer; },
      get keyLight() { return key; },
      get model() { return model; },
      get envTexture() { return envTexture; },
      setLevel, setConfig, forceWebGL: () => recoverRenderer('manual acceptance'),
      caps,
    };
  } catch (e) {
    console.error(e);
    fatal(e?.stack || e?.message || e);
  }
}

boot();
