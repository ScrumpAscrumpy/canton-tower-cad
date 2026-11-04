# 渲染层协议实施说明 — 后端选择与真实质感分级

> 公网浏览：<https://scrumpascrumpy.github.io/canton-tower-cad/>  
> 源码：`web/app.js`、`web/shell.html`、`web/style.css`、`assets/`、`tools/shot.mjs`  
> 验证：`reports/render_validation.md`

## 1. 后端选择与自动回退

### 1.1 能力检测

`web/app.js` 启动时检测：

```js
const caps = {
  webgpu: !!navigator.gpu,
  webgl2: !!document.createElement('canvas').getContext('webgl2'),
  cores: navigator.hardwareConcurrency || null,
  memoryGB: navigator.deviceMemory || null,
  mobile: matchMedia('(pointer: coarse)').matches,
};
```

### 1.2 初始化策略

1. `navigator.gpu` 存在 → 创建 `THREE.WebGPURenderer`，尝试 WebGPU 后端。
2. `navigator.gpu` 不存在 → 直接创建 `THREE.WebGPURenderer({ forceWebGL: true })`，走 WebGL2 后端。
3. WebGPU 适配器为空、设备请求失败或上下文初始化异常 → Three.js `WebGPURenderer` 自动调用 `getFallback()` 创建 WebGL2 后端；应用层同时捕获初始化异常并重试 `{ forceWebGL: true }`。
4. 两者都失败 → 显示 render error，提示浏览器/WebGL2 要求。

**架构选择说明**：本项目采用 Three.js 的统一 `WebGPURenderer`，其 WebGL2 路径是 `WebGLBackend`（WebGLRenderer 的 WebGL2 渲染路径），而不是另起一套 legacy `WebGLRenderer`。这样 L1/L2 的 TSL 后处理在两种后端上使用同一套节点代码；如果切换为 legacy WebGLRenderer，需要复制一套 EffectComposer/ShaderPass 管线，反而增加两套画面不一致的风险。实际后端仍由运行时检测决定，而不是写死。

### 1.3 运行时后端标识

- 顶栏徽标：`WEBGPU` 或 `WEBGL2`
- 右侧 RENDER 面板：`backend-name`、`backend-tag = GPU / FALLBACK`
- 底部状态条：`__RENDER__.backend`
- 调试 API：

```js
__RENDER__.backend          // 'WEBGPU' | 'WEBGL2'
__RENDER__.level            // 'L0' | 'L1' | 'L2'
__RENDER__.config           // {ibl, shadows, post, ssr}
__RENDER__.state            // backendReason, fps, autoDowngrades, ...
```

### 1.4 上下文丢失

- WebGL：监听 `webglcontextlost`，`preventDefault()` 后重建 WebGL2 renderer，保留 scene/model，重新构建后处理。
- WebGPU：监听 `renderer.backend.device.lost`，自动回退 WebGL2。
- 重建后重新绑定 OrbitControls、重建 PostProcessing、继续渲染；第二次 WebGL2 丢失时给出刷新提示。

### 1.5 后端无关性

- 场景、相机、GLTF 加载、材质参数、灯光、OrbitControls、尺寸计算均不依赖后端。
- 没有使用 WebGPU 专属 TSL/NodeMaterial 才能运行的特性；L1/L2 的 AO/Bloom/DoF/FXAA 均通过 `three/tsl` 的跨后端节点实现。
- 没有 compute shader 或 WebGPU-only 后处理；因此 WebGL2 回退不需要“功能禁用”才能渲染。SSR 明确未启用（见 §3）。

---

## 2. 真实质感分级

默认 **L1**。

| 等级 | 包含效果 | 默认 | 性能影响 | 不支持/失败时 |
|---|---|---|---|---|
| **L0 基础** | PBR 基础参数；单方向光 + 半球环境光；关闭阴影；关闭 IBL；关闭后处理；ACES tone mapping + sRGB；默认 MSAA | 可选 | 低 | 不依赖 HDR/ORM；若 GLB 失败则整体报错 |
| **L1 增强** | PBR + 金属度/粗糙度 ORM 贴图；HDR equirect IBL；PCFSoft 阴影 + 接触阴影；GTAO + Bloom + FXAA；ACES + sRGB；像素比上限 1.5 | **默认** | 中 | HDR 失败 → 关闭 IBL 并提示；ORM 失败 → 参数材质；后处理失败 → 直接渲染 |
| **L2 电影** | L1 + DoF、2048² 阴影、24-sample AO、略强 Bloom、像素比上限 1.75 | 可选 | 高 | DoF/后处理失败 → L1 并提示；SSR/体积光未启用，不崩溃；WebGL2 后端可运行同一 TSL 管线 |

### L2 的范围说明

本版本 L2 选择 **DoF + 高质量 AO + 更高阴影贴图**，没有启用 SSR、折射、体积光或运动模糊。原因：

- r169 的跨后端 TSL 后处理提供 DoF/Bloom/AO/FXAA，但没有 SSR 节点；WebGL2 下启用 SSR 需要额外屏幕空间管线和深度重建，风险高。
- UI 中 SSR 开关显式禁用，点击会提示“本版以 DoF 替代”；不会出现“点了 L2 就崩溃”。
- 这符合“L2 效果按需选择，不得全开导致不可用”的约束。

---

## 3. 真实质感配置表

| 配置项 | 默认 | 性能影响 | 不支持/失败时 | 运行时切换 |
|---|---|---|---|---|
| `realismLevel` | `L1` | L0<L1<L2 | 自动降级 | 安全；重建 PostProcessing（毫秒–数百毫秒） |
| `enableIBL` | `true` | 中（HDR 采样/PMREM） | HDR 失败自动关闭 | 安全；切换 `scene.environment`，材质重编译约 0.1–0.3 s |
| `enableShadows` | `true` | 高（额外深度 pass） | 阴影编译失败/低端自动关闭 | 安全；更新 `shadowMap.enabled`、`castShadow`，重建 shadow map |
| `enablePostProcessing` | `true` | 高（AO+Bloom+FXAA，L2 再加 DoF） | 后处理失败 → 直接渲染 | 安全；只重建后处理，不重建模型/材质 |
| `enableSSR` | `false` | 不可用 | 显式禁用并提示；L2 用 DoF 替代 | 不提供启用；避免 WebGL2 崩溃 |
| `enableAutoQuality` | `true` | 无额外 pass | 无 | 安全；关闭后停止 FPS 降级 |

> 运行时切换 IBL/shadows/post 可能触发异步 shader 编译；切换期间画面可能短暂停顿。几何、STEP、GLB 缓冲区不被修改。

---

## 4. 性能预算与自动降级

| 预算项 | 规则 |
|---|---|
| 目标帧率 | **50 FPS** |
| 降级阈值 | **连续 3 s < 30 FPS**，每 1 s 采样一次，8 s 冷却 |
| 阴影贴图 | L0 `OFF`；L1 `1024²`；L2 `2048²` |
| 后处理 pass 上限 | L0 `0`；L1 `3`（AO + Bloom + FXAA）；L2 `4`（+ DoF） |
| 像素比上限 | L0 `1.0×`；L1 `1.5×`；L2 `1.75×`；移动端再乘 `0.8`；`devicePixelRatio` 取小 |
| 自动降级序列 | L2 → L1 → L0；L0 仍低时 `pixelScale 1.0 → 0.85 → 0.70`；如自定义 post 仍开则关闭 |
| 低端提示 | `hardwareConcurrency ≤ 4` / 低内存时显示警告，不自动升 L2 |
| 手动控制 | RENDER 面板“自动降级”开关；URL `?auto=0` |

实现：`evaluateBudget()` 每 1 s 检查一次，`state.readyAt + 6 s` 后才开始统计；`setLevel(...,{auto:true})` 会写入 `autoDowngrades` 并弹出提示。

---

## 5. 渲染资产清单

资产清单机器可读版本：[`assets/render_assets.json`](../assets/render_assets.json)。

| 资产 | 用途 | 大小 | 来源 | 授权 |
|---|---|---:|---|---|
| `assets/env/night_sky_1k.hdr` | L1/L2 equirectangular HDR IBL | 2.0 MB | 由 `assets/generate_render_assets.py` 生成 | CC0-1.0 |
| `assets/tex/metal_orm.png` | 钢构金属度/粗糙度 ORM（G=roughness, B=metalness） | 256 KB | 同上，程序生成 | CC0-1.0 |
| `assets/tex/concrete_orm.png` | 混凝土/楼板 ORM | 228 KB | 同上，程序生成 | CC0-1.0 |
| `assets/canton_tower_web.glb` | 几何 + 基础 PBR 参数 | 9.1 MB | 由 CAD 管线的 30 mm LOD 导出 | 项目生成 |
| 运行时 CanvasTexture | 天空穹顶、接触阴影、航空灯 glow | 0 | 浏览器运行时生成 | 项目生成 |

ORM 贴图通过运行时生成的 box-projected UV 应用于材质；只新增 `TEXCOORD_0`，**不修改顶点位置、拓扑或 GLB 几何精度**。

---

## 6. 验收说明

### 6.1 网页上

1. 打开 <https://scrumpascrumpy.github.io/canton-tower-cad/>。
2. 顶栏查看 `WEBGPU` 或 `WEBGL2`；切换 RENDER/VIEW 标签。
3. RENDER 面板确认 `L1` 默认、FPS、PIXEL RATIO、SHADOW、POST PASSES。
4. 点击 L0/L1/L2，观察开关与提示；L2 在 WebGL2 下仍应正常渲染（可能较低 FPS）。
5. 关闭“自动降级”可固定当前画质；FPS 低时观察自动降级 toast 和 `autoDowngrades`。

### 6.2 控制台

```js
__RENDER__.backend                 // 'WEBGL2' or 'WEBGPU'
__RENDER__.level                   // 'L0'/'L1'/'L2'
__RENDER__.config                  // current switches
__RENDER__.state.backendReason
__RENDER__.state.fps
__RENDER__.state.autoDowngrades
__RENDER__.setLevel('L2')          // runtime switch
__RENDER__.setConfig('post', false)
```

### 6.3 URL 参数

| URL | 用途 |
|---|---|
| `?level=L1` | 指定等级 |
| `?level=L0` / `?level=L2` | 低/高画质 |
| `?backend=webgl` | 强制 WebGL2，验证回退与场景显示 |
| `?auto=0` | 关闭自动降级，便于截图/验收 |
| `?ibl=0&shadows=0&post=0` | 单开关验收 |
| `?view=waist` / `?view=crown` | 视角 |
| `?section=1&x=0` | 剖切 |

### 6.4 回退验证（已执行）

在无可用 WebGPU 适配器的 headless Chrome 中，默认 URL 自动得到：

```json
{"backend":"WEBGL2","backendReason":"WebGPU 适配器/上下文不可用 → WebGL2 自动回退","postOK":true}
```

L0/L1/L2、运行时 L1→L0、单开关关闭和自动降级均已在 WebGL2 下验证；详见 [`render_validation.md`](render_validation.md)。

### 6.5 WebGPU 实际运行的说明

当前 headless Chrome 环境无法提供可用的 WebGPU adapter；因此 **WebGPU 后端本身未被本环境实际点亮验证**，不能声称“WebGPU 已在 CI 中通过”。代码路径、自动回退与 WebGL2 全部已验证。请在支持 WebGPU 的 Chrome/Edge/Safari（HTTPS、非无头模式）打开，顶栏应显示 `WEBGPU`；如仍显示 `WEBGL2`，`backend-meta` 会给出原因。

---

## 7. 与几何精度的关系

- 渲染层只读取 `assets/canton_tower_web.glb`，不在 Three.js 内细分、重构或改变拓扑。
- L0/L1/L2 切换只改材质参数、阴影、IBL、后处理；不改变 GLB 顶点。
- 需要更高几何精度时，回到 CAD：修改 `cad/params.py` 中的网格化偏差并重跑 `build_canton_tower.py`，而不是在渲染器里细分。
- 精确 STEP 与参考 GLB 仍通过 [GitHub Release v1.0.0](https://github.com/ScrumpAscrumpy/canton-tower-cad/releases/tag/v1.0.0) 分发。
