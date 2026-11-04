# 渲染层验证报告 — Backend / Realism / Graceful degradation

验证日期：2026-11-05 · 页面：`index.html` / `web/index.html`  
验证工具：`tools/shot.mjs`（Chrome DevTools Protocol，等待 `window.__TOWER_READY__` 后截图并读取 `window.__RENDER__`）

## 1. 验证环境

| 项目 | 值 |
|---|---|
| OS / CPU | macOS arm64（当前环境） |
| 浏览器 | Google Chrome 152 headless |
| GPU 路径 | SwiftShader（软件 WebGL2） |
| WebGPU 可用性 | **无可用 adapter**（headless 环境限制） |
| 页面后端（默认） | **WEBGL2 自动回退** |
| 几何 | 未修改的 `assets/canton_tower_web.glb`（30 mm LOD） |

> 软件渲染下 FPS 为 **1–6**，不能作为真实设备性能结论；此报告重点验证管线、开关、回退和状态，而非绝对帧率。

## 2. 测试矩阵与结果

| # | 场景 | 命令/操作 | 期望 | 实际结果 |
|---|---|---|---|---|
| 1 | WebGPU 不可用自动回退 | 打开无 `backend` 参数的页面 | 场景显示；后台显示 WEBGL2 | **PASS**：`backend=WEBGL2`，`backendReason="WebGPU 适配器/上下文不可用 → WebGL2 自动回退"`，`postOK=true` |
| 2 | L0 基础模式 | `?level=L0&auto=0&backend=webgl` | 无 IBL/阴影/后处理 | **PASS**：`config={ibl:false,shadows:false,post:false,ssr:false}`，`postOK=false`，`postPasses=0` |
| 3 | L1 默认模式 | `?level=L1&auto=0` | IBL+PCF 阴影+3 pass+ACES | **PASS**：`postOK=true`，`postPasses=3`，`shadow map=1024²`，`env=true`，ORM maps=true |
| 4 | L2 电影模式（WebGL2） | `?level=L2&auto=0&backend=webgl` | 4 pass；不得崩溃 | **PASS**：`postOK=true`，`postPasses=4`，`shadow map=2048²`，WebGL2 正常显示 |
| 5 | 运行时切换等级 | `__RENDER__.setLevel('L0')` | 从 L1 切到 L0 | **PASS**：`level=L0`，`config` 变为全关，`postOK=false` |
| 6 | 运行时关闭 IBL/阴影/后处理 | `__RENDER__.setConfig(...)` | 立即生效；不崩 | **PASS**：`config={ibl:false,shadows:false,post:false,ssr:false}`，`postOK=false`，`level=L1, custom=true` |
| 7 | 自动降级 | 默认 `auto=1`，L1，软件渲染 ~3 FPS，等待 15 s | L1 → L0，提示 | **PASS**：`level=L0`，`autoDowngrades=1`，`pixelScale=0.7` |
| 8 | 材质/阴影实际绑定 | CDP 检查 `CFTColumns` 材质 | ORM maps/IBL/shadow 已绑定 | **PASS**：`env=true`，`shadow=true`，`mapSize=[1024,1024]`，`roughnessMap=true`，`metalnessMap=true` |
| 9 | 自包含离线文件 | `file:///.../canton-tower.html?auto=0&level=L1` | 数据 URI 资产可加载 | **PASS**：GLB+HDR+两张 ORM 全部加载，`postOK=true` |
| 10 | WebGL context loss 自动恢复 | `WEBGL_lose_context.loseContext()` | 自动重建 WebGL2，场景继续显示 | **PASS**：`contextLossCount=1`，`backendReason` 含“运行时上下文丢失”，`postOK=true`，页面继续渲染 |
| 11 | WebGPU 正路径实际渲染 | 需要可用 WebGPU adapter | 顶栏 WEBGPU | **NOT VERIFIED IN THIS ENVIRONMENT**（headless 无 adapter）；代码路径保留并通过 WebGPURenderer 自动选择 |

截图：

- [L0 基础模式](render_validation_L0.png)
- [L1 增强模式](render_validation_L1.png)
- [L2 电影模式（WebGL2）](render_validation_L2.png)
- [自动回退 WebGL2](render_validation_fallback.png)
- [Context loss 自动恢复](render_validation_contextloss.png)

## 3. 运行时观测数据

### 3.1 自动回退（无 backend 参数）

```json
{
  "backend": "WEBGL2",
  "backendReason": "WebGPU 适配器/上下文不可用 → WebGL2 自动回退",
  "level": "L1",
  "config": {"ibl": true, "shadows": true, "post": true, "ssr": false},
  "postOK": true,
  "postPasses": 3,
  "fps": 2
}
```

### 3.2 L1 材质/阴影绑定

```json
{
  "env": true,
  "shadow": true,
  "mapSize": [1024, 1024],
  "mats": [{"name": "CFTColumns", "roughnessMap": true, "metalnessMap": true, "envMapIntensity": 0.82}]
}
```

### 3.3 L2 在 WebGL2

```json
{
  "backend": "WEBGL2",
  "level": "L2",
  "config": {"ibl": true, "shadows": true, "post": true, "ssr": false},
  "postOK": true,
  "postPasses": 4,
  "state": {"l2Fallback": false}
}
```

### 3.4 运行时切换到 L0

```json
{
  "level": "L0",
  "config": {"ibl": false, "shadows": false, "post": false, "ssr": false},
  "postOK": false,
  "qualityEpoch": 2
}
```

### 3.5 Context loss

```json
{
  "backend": "WEBGL2",
  "backendReason": "运行时上下文丢失 → 自动回退 WebGL2：WebGL context lost",
  "contextLossCount": 1,
  "postOK": true,
  "frames": 30
}
```

### 3.6 自动降级

```json
{
  "level": "L0",
  "autoQuality": true,
  "autoDowngrades": 1,
  "pixelScale": 0.7,
  "fps": 3
}
```

## 4. 验收判定

| 验收项 | 结果 |
|---|---|
| WebGPU 不可用时自动回退 WebGL 且场景正常显示 | **PASS**（WebGL2 回退，post 管线运行） |
| 真实质感可运行时切换 | **PASS**（level 与单开关均验证） |
| L2 在 WebGL2 不直接崩溃 | **PASS**（4 pass，WebGL2 下渲染） |
| 不使用“WebGPU = 真实”的错误实现 | **PASS**：UI/文档明确区分后端口与真实感；L0 在 WebGL2/WebGPU 都是基础效果 |
| 几何精度不随画质变化 | **PASS**：所有等级读取同一个 GLB；质量切换不改顶点/拓扑 |

## 5. 已知限制

1. **WebGPU 正路径未在本环境点亮验证**。需要支持 WebGPU 的非 headless 浏览器；若不可用，页面会显示 WEBGL2 和原因。
2. FPS 是 SwiftShader 软件渲染值（1–6），不能代表用户硬件。
3. SSR/折射/体积光/运动模糊未启用；L2 使用 DoF + 高质量 AO。UI 中 SSR 开关禁用并给出说明。
4. L2 的 DoF 会随焦点距离变化；相机推拉时可能短暂柔化塔顶/塔基，这是镜头效果，不是几何误差。
5. 渲染资产（HDR/ORM）为程序生成 CC0 文件；如果替换为真实 HDRI，需同步更新 `assets/render_assets.json` 的许可。
