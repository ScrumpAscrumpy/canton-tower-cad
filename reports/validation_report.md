# Canton Tower — Validation report

Generated: 2026-11-04T22:07:42+0800

## 1. Acceptance checks

| Check | Result | Detail |
|---|---|---|
| STEP re-read | PASS | 1899 / 1899 solids |
| STEP topology | PASS | 0 invalid solids |
| Closed shells | PASS | 1924 / 1924 shells closed |
| Volume > 0 | PASS | 36764.5 m3 |
| STEP volume round-trip < 0.1% | PASS | 0.000000% |
| Reference GLB deviation <= 5 mm | PASS | 4.000 mm (sampled) |
| Web GLB deviation <= 30 mm | PASS | 20.793 mm (sampled) |
| GLB group count | PASS | 9 / 9 / 9 |
| GLB triangle count > 0 | PASS | 1487644 ref / 379748 web |

## 2. STEP round trip

- Solids written / re-read: **1899 / 1899**
- Invalid solids: **0**
- Shells closed: **1924 / 1924**
- Volume (original): **36764.454 m³**
- Volume (STEP re-read): **36764.454 m³**
- Volume delta: **0.000000 %**
- BBox STEP (m): **{'xmin': -33.0000000001, 'xmax': 33.0000000001, 'ymin': -43.000000000100016, 'ymax': 43.00000000010002, 'zmin': -9.999999999999999e-11, 'zmax': 600.0, 'xlen': 66.0000000002, 'ylen': 86.00000000020003, 'zlen': 600.0000000001}**

## 3. GLB meshes

| Mesh | Vertices | Triangles | Size | Max sampled deviation |
|---|---:|---:|---:|---:|
| reference (5 mm / 0.2 rad) | 747042 | 1487644 | 31.74 MB | 4.000 mm |
| web (30 mm / 0.45 rad) | 191126 | 379748 | 9.14 MB | 20.793 mm |

- Reference GLB bbox (m): **{'xmin': -32.999996185302734, 'xmax': 32.999916076660156, 'ymin': 0.0, 'ymax': 600.0, 'zmin': -43.0, 'zmax': 42.9998893737793}**
- Web GLB bbox (m): **{'xmin': -33.0, 'xmax': 32.99077606201172, 'ymin': 0.0, 'ymax': 600.0, 'zmin': -43.0, 'zmax': 42.99374008178711}**

## 4. Key dimensions

- `total_height_mm` = 600000.0
- `main_body_top_mm` = 454000.0
- `antenna_length_mm` = 146000.0
- `base_centerline_oval_mm` = [60000.0, 80000.0]
- `waist_centerline_oval_mm` = [20650.0, 27500.0]
- `waist_outer_oval_mm` = [22250.0, 29100.0]
- `top_centerline_oval_mm` = [40500.0, 54000.0]
- `top_outer_oval_mm` = [41900.0, 55400.0]
- `twist_deg` = -45.0
- `core_outer_mm` = [17000.0, 14000.0]
- `core_wall_mm` = [1000.0, 400.0]
- `min_wall_mm_modelled` = 50.0
- `antenna_access_holes` = [{'z_mm': 470000.0, 'side': '-Y', 'diameter_mm': 700.0}, {'z_mm': 500000.0, 'side': '-Y', 'diameter_mm': 700.0}, {'z_mm': 540000.0, 'side': '-Y', 'diameter_mm': 700.0}, {'z_mm': 570000.0, 'side': '-Y', 'diameter_mm': 700.0}]
- `ring_inclination_documented_deg` = 15.5
- `ring_inclination_applied` = False

## 5. Per-group meshes (web LOD)

| Group | Vertices | Triangles | Watertight | Volume m³ |
|---|---:|---:|---|---:|
| Podium | 938 | 1872 | True | 4451.898593337838 |
| ConcreteCore | 208 | 408 | True | 14895.804939576852 |
| FloorSlabs | 10488 | 20976 | True | 10349.091036727 |
| CFTColumns | 61928 | 123664 | True | 2992.824691745029 |
| RingBeams | 59616 | 119232 | False | None |
| DiagonalBraces | 30240 | 58320 | True | 1098.1634845497886 |
| ConnectionGirders | 256 | 384 | True | 230.22199227790634 |
| ObservationDeck | 18482 | 36964 | True | 552.0816025955017 |
| AntennaMast | 8970 | 17928 | False | None |

> Note: a group mesh can be non-manifold after vertex welding where individual members interpenetrate at joints. This is expected for a member-level structural assembly. The STEP check confirms every one of the 1,899 B-Rep solids is valid and every shell is closed.

## 6. Deviation samples

| Group | n | max mm | mean mm | p95 mm |
|---|---:|---:|---:|---:|
| Podium | 25 | 20.793 | 13.113 | 19.220 |
| ConcreteCore | 25 | 13.335 | 5.680 | 12.819 |
| FloorSlabs | 25 | 13.264 | 5.800 | 13.229 |
| CFTColumns | 25 | 6.511 | 4.975 | 6.223 |
| RingBeams | 25 | 1.792 | 0.644 | 1.789 |
| DiagonalBraces | 25 | 1.341 | 0.699 | 1.341 |
| ConnectionGirders | 25 | 0.012 | 0.003 | 0.012 |
| ObservationDeck | 25 | 13.244 | 4.002 | 11.613 |
| AntennaMast | 25 | 6.705 | 0.454 | 0.615 |