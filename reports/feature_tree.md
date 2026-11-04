# 广州塔特征树 / Feature Tree

单位 mm；Z 向上；草图/基准均由 `cad/params.py` 驱动。

```
基准
├─ Ground datum: Z = 0, plan centre (0,0), X east / Y north
├─ Twist schedule: φ(z) = -45°·(z - 0)/(454 000)
├─ Envelope: 3 control stations (base 60×80, waist 20.65×27.5 @280 m, crown 40.5×54 @454 m)
│  └─ C1 smoothstep interpolation, 46 ring stations
├─ Core datum: 17×14 m ellipse, long axis 108° from +X (=18° west of north), offset (1.2, -0.8) m (B)
└─ Antenna octagon: 7 stations, R 6 500 → 500 mm

草图 / Sketch
├─ Outer envelope ellipse family (parametric, rotated by φ(z))
├─ Core outer ellipse (constant 17×14 m)
├─ Core inner ellipse (wall 1 000 → 400 mm)
├─ 24 CFT circular profiles, R 1 200 → 800 → 700 mm
├─ Ring beam circular profile R 320 mm
├─ Brace circular profile R 240 mm
├─ Floor outer ellipse (0.955 × envelope) with core clearance hole
├─ Deck annulus outer 22×29 m / inner 18.5×24 m
├─ Octagonal antenna sections
└─ Podium ellipse 66×86 m

特征 / Features
├─ F01 Podium: ellipse extrude 1 000 mm → top edge fillet 250 mm
├─ F02 Core: outer ellipse extrude 454 000 mm
│  └─ Boolean cut: inner ruled loft (wall 1 000 → 400 mm), closed ends
├─ F03 24 CFT columns: 46-section ruled loft, hollow
│  └─ Boolean cut: inner 46-section loft, 50 mm wall
├─ F04 46 ring levels × 24 straight tubular beams = 1 104 solids
├─ F05 540 alternating diagonal braces (cylindrical solids)
├─ F06 37 floor slabs: envelope ellipse extrude 200 mm
│  └─ Boolean cut: core-shaped clearance hole
├─ F07 32 connection girders: 4 levels × 8 radial box beams
├─ F08 Observation deck: annulus extrude 900 mm + closed railing sweep
├─ F09 Antenna:
│  ├─ Octagonal ruled loft 454 → 592 m
│  ├─ Shell + external frame hybrid (real structure is an open spatial frame)
│  ├─ Shell attempt failed → exact inner-loft boolean cut (wall 120 mm)
│  ├─ 12 octagonal flange bands (annulus extrude)
│  ├─ 4 access-hole cuts Ø700 mm at 470/500/540/570 m, -Y side
│  ├─ 8 corner chords + 96 face diagonals (spatial frame)
│  └─ Revolved cone tip 592 → 600 m
└─ F10 Assembly: 9 named components, colour-preserving STEP AP214

阵列 / Arrays
├─ Columns: polar 24× at equal-sector-area parameters
├─ Ring beams: 46 z-levels × 24 circumferential segments
├─ Braces: alternating (i+j) parity, 540 of 1 104 possible panels
├─ Floors: 37 levels in 5 programmatic zones
└─ Antenna frame: 8 corners × 6 segments + 2 diagonals per face/segment

网格 / Mesh
├─ Reference: BRepMesh_IncrementalMesh, absolute linear 5 mm, angular 0.2 rad
└─ Web: absolute linear 30 mm, angular 0.45 rad; Y-up, metres

依赖关系
params → envelope/stations → columns/rings/braces/core/floors/deck/antenna
       → 9 group compounds → STEP assembly
       → tessellation (absolute deflection) → GLB
       → validation (STEP re-read, GLB deviation)
```

## 内核操作与失败记录

| 操作 | 结果 |
|---|---|
| Extrude（基座、核心筒外壁、楼板） | OK |
| Ruled loft（24 根 CFT 柱、核心筒内腔、天线八边形） | OK |
| Boolean cut（核心筒内腔、柱内腔、楼板孔、天线孔、天线内腔回退） | OK |
| Sweep（观景环栏杆，闭合椭圆路径） | OK |
| Fillet（基座顶边 250 mm） | OK |
| Shell（天线锥形八边形，−120 mm） | **失败**：`ValueError: Null TopoDS_Shape`；已用精确布尔差回退并记录 |
| 45° 扭转 / 24 柱阵列 / 46 环 / 540 斜撑 | 参数化循环生成 |
