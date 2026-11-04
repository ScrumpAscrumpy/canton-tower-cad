"""
Canton Tower (广州塔) — authoritative parameter set for the parametric CAD model.

All lengths are in millimetres.  Coordinate system: X = east, Y = north, Z = up.
The public ground datum is Z = 0.  The tower main body rises to Z = 454 000 mm;
the antenna mast rises a further 146 000 mm to Z = 600 000 mm.

Sources and confidence classes are documented in reports/parameter_sources.csv.
Values marked (B) are engineering assumptions required to make a buildable
architectural representation; they are NOT survey data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

# ----------------------------------------------------------------------------
# A-class public / published geometry
# ----------------------------------------------------------------------------
TOTAL_HEIGHT = 600_000.0          # mm, official 600 m
MAIN_HEIGHT = 454_000.0           # mm, top of main tube
ANTENNA_HEIGHT = 146_000.0        # mm, thesis value (Wikipedia variant: 150 m / 604 m)
N_COLUMNS = 24                    # CFT columns
N_RINGS = 46                      # steel ring beams / levels
N_FUNCTIONAL_FLOORS = 37
RING_LOWER_COUNT = 27
RING_UPPER_COUNT = 20
RING_START_Z = 1_000.0
RING_END_Z = 453_500.0
TWIST_DEG = -45.0                 # clockwise looking down, top vs bottom

# Outer tube envelope, semi-axes of the reference ellipse (column centre-lines)
BASE_Z = 0.0
BASE_A = 30_000.0                 # 60 m across X
BASE_B = 40_000.0                 # 80 m across Y
WAIST_Z = 280_000.0
WAIST_A = 10_325.0                # 20.65 m
WAIST_B = 13_750.0                # 27.50 m
TOP_A = 20_250.0                  # 40.50 m
TOP_B = 27_000.0                  # 54.00 m

# Core: 17 m x 14 m, long axis 18 deg west of north, centroid offset (B)
CORE_A = 8_500.0                  # semi-axis along its local long axis (17 m)
CORE_B = 7_000.0                  # semi-axis across (14 m)
CORE_ROT_DEG = 108.0              # long axis 18 deg west of +Y north
CORE_OFFSET_X = 1_200.0           # (B) undocumented eccentricity, conservative
CORE_OFFSET_Y = -800.0            # (B)
CORE_WALL_BASE = 1_000.0          # published 1.0 m at base
CORE_WALL_TOP = 400.0             # published 0.4 m at top

# ----------------------------------------------------------------------------
# B-class dimensions: architectural interpretation / not published
# ----------------------------------------------------------------------------
COL_R_BASE = 1_200.0              # CFT outer radius (2.4 m dia)
COL_R_WAIST = 800.0               # 1.6 m dia
COL_R_TOP = 700.0                 # 1.4 m dia
COL_WALL = 50.0                   # 50 mm CFT wall
RING_R = 320.0                    # 0.64 m dia ring tube
BRACE_R = 240.0                   # 0.48 m dia diagonal brace
FLOOR_THICK = 200.0
FLOOR_OUTER_FACTOR = 0.955        # floor edge just inside the CFT centre-line
FLOOR_HOLE_CLEARANCE = 25.0
FLOOR_HOLE_OVERSHOOT = 100.0
PODIUM_A = 33_000.0
PODIUM_B = 43_000.0
PODIUM_H = 1_000.0
PODIUM_FILLET = 250.0
DECK_Z = 449_000.0
DECK_OUTER_A = 22_000.0
DECK_OUTER_B = 29_000.0
DECK_INNER_A = 18_500.0
DECK_INNER_B = 24_000.0
DECK_THICK = 900.0
DECK_RAIL_R = 90.0
DECK_RAIL_INSET = 250.0
ANTENNA_R_BASE = 6_500.0          # octagonal circumradius, 13 m max diagonal
ANTENNA_WALL = 120.0
ANTENNA_TIP_Z = 592_000.0
ANTENNA_TIP_R = 500.0
ANTENNA_TOP_R = 40.0
ANTENNA_FLANGE_COUNT = 12
ANTENNA_FLANGE_Z0 = 460_000.0
ANTENNA_FLANGE_Z1 = 585_000.0
ANTENNA_FLANGE_H = 300.0
ANTENNA_FLANGE_OUT = 180.0
ANTENNA_FLANGE_IN = 40.0
ANTENNA_ACCESS_HOLES = (470_000.0, 500_000.0, 540_000.0, 570_000.0)
ANTENNA_ACCESS_R = 350.0
ANTENNA_CORNER_R = 110.0
ANTENNA_DIAGONAL_R = 70.0
CONNECTION_LEVELS = (204_000.0, 230_000.0, 272_000.0, 303_000.0)
CONNECTION_BEAMS = 8
CONNECTION_BEAM_W = 600.0
CONNECTION_BEAM_H = 900.0

# Mesh / export parameters
MESH_LINEAR_TOL = 5.0             # mm — architectural LOD (see report for 0.05 mm rationale)
MESH_ANGULAR_TOL = 0.2            # rad
MESH_WEB_LINEAR_TOL = 30.0        # mm — web LOD (3 cm at 600 m scale)
MESH_WEB_ANGULAR_TOL = 0.45       # rad

# Materials (A-class generic values)
RHO_STEEL = 7_850.0               # kg/m3
RHO_CONCRETE = 2_500.0            # kg/m3
RHO_GLASS = 2_500.0

# Ring levels are generated from 27 lower + 20 upper stations (46 total),
# slightly denser near the waist.  This reproduces the documented non-uniform
# spacing without pretending to know the construction setting-out table.
def ring_levels() -> tuple[float, ...]:
    lower_n = RING_LOWER_COUNT
    upper_n = RING_UPPER_COUNT
    z0, zw, z1 = RING_START_Z, WAIST_Z, RING_END_Z
    lower = []
    for i in range(lower_n):
        u = i / (lower_n - 1)
        # derivative at waist = 0.85, at base = 1.15 -> tighter near waist
        f = 1.15 * u - 0.15 * u * u
        lower.append(z0 + (zw - z0) * f)
    upper = []
    for i in range(upper_n):
        u = i / (upper_n - 1)
        f = 0.85 * u + 0.15 * u * u
        upper.append(zw + (z1 - zw) * f)
    return tuple(lower + upper[1:])


def floor_levels() -> tuple[float, ...]:
    """37 functional floor levels, grouped in five programmatic zones (B)."""
    zones = ((30_000.0, 80_000.0, 8), (85_000.0, 170_000.0, 12),
             (180_000.0, 275_000.0, 6), (285_000.0, 375_000.0, 7),
             (385_000.0, 445_000.0, 4))
    out: list[float] = []
    for z0, z1, n in zones:
        for i in range(n):
            out.append(z0 + (z1 - z0) * i / (n - 1))
    assert len(out) == N_FUNCTIONAL_FLOORS
    return tuple(out)


# Antenna octagonal section schedule (z, circumradius) — B-class interpretation
ANTENNA_SECTIONS = (
    (454_000.0, 6_500.0),
    (470_000.0, 5_600.0),
    (490_000.0, 4_500.0),
    (520_000.0, 3_200.0),
    (550_000.0, 2_000.0),
    (575_000.0, 1_000.0),
    (ANTENNA_TIP_Z, 500.0),
)


@dataclass(frozen=True)
class Envelope:
    z: float
    a: float
    b: float
    phi: float  # radians, clockwise negative


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def envelope(z: float) -> Envelope:
    """Smooth C1 hourglass envelope through base/waist/top.

    The source gives 60x80 m at -10 m, 20.65x27.5 m at 280 m and
    40.5x54 m at 454 m.  For a ground-datum model the base ellipse is placed at
    z=0 (documented datum shift); the waist and crown heights are unchanged.
    """
    if z <= WAIST_Z:
        t = (z - WAIST_Z) / (BASE_Z - WAIST_Z)
        s = smoothstep(t)
        a = WAIST_A + (BASE_A - WAIST_A) * s
        b = WAIST_B + (BASE_B - WAIST_B) * s
    else:
        t = (z - WAIST_Z) / (MAIN_HEIGHT - WAIST_Z)
        s = smoothstep(t)
        a = WAIST_A + (TOP_A - WAIST_A) * s
        b = WAIST_B + (TOP_B - WAIST_B) * s
    phi = math.radians(TWIST_DEG) * (z - BASE_Z) / (MAIN_HEIGHT - BASE_Z)
    return Envelope(z, a, b, phi)


def column_point(j: int, z: float) -> tuple[float, float, float]:
    """Centre-line point of column j (0..23) at height z."""
    e = envelope(z)
    th = 2.0 * math.pi * j / N_COLUMNS
    ca, sa = math.cos(th), math.sin(th)
    cp, sp = math.cos(e.phi), math.sin(e.phi)
    x = e.a * ca * cp - e.b * sa * sp
    y = e.a * ca * sp + e.b * sa * cp
    return (x, y, z)


def column_radius(z: float) -> float:
    if z <= WAIST_Z:
        t = (z - BASE_Z) / (WAIST_Z - BASE_Z)
        return COL_R_BASE + (COL_R_WAIST - COL_R_BASE) * t
    t = (z - WAIST_Z) / (MAIN_HEIGHT - WAIST_Z)
    return COL_R_WAIST + (COL_R_TOP - COL_R_WAIST) * t


def core_outer_dimensions(z: float) -> tuple[float, float]:
    """Core exterior is constant 17 m x 14 m; returns (a,b) semi-axes."""
    return CORE_A, CORE_B


def core_wall(z: float) -> float:
    t = max(0.0, min(1.0, (z - BASE_Z) / (MAIN_HEIGHT - BASE_Z)))
    return CORE_WALL_BASE + (CORE_WALL_TOP - CORE_WALL_BASE) * t


def antenna_radius(z: float) -> float:
    secs = ANTENNA_SECTIONS
    if z <= secs[0][0]:
        return secs[0][1]
    for (z0, r0), (z1, r1) in zip(secs, secs[1:]):
        if z <= z1:
            t = (z - z0) / (z1 - z0)
            return r0 + (r1 - r0) * t
    return secs[-1][1]


# Named parameter records used to generate the CSV / Markdown table.
PARAMETER_RECORDS = [
    # name, value, unit, category, source_type, source_id, date, confidence, status
    ("total_height", "600000", "mm", "A", "standard/official", "https://en.wikipedia.org/wiki/Canton_Tower ; HKIE Cover Story 2012", "2026-11-04", "high", "已确认"),
    ("main_body_height", "454000", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, Ch.3; HKIE 2012", "2026-11-04", "high", "已确认"),
    ("antenna_length", "146000", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.32", "2026-11-04", "high", "已确认"),
    ("functional_floors", "37", "count", "A", "official/engineering", "HKIE Cover Story 2012", "2026-11-04", "high", "已确认"),
    ("cft_columns", "24", "count", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.34", "2026-11-04", "high", "已确认"),
    ("ring_levels", "46", "count", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.34", "2026-11-04", "high", "已确认"),
    ("base_oval", "60000 x 80000", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.34 (at -10 m)", "2026-11-04", "high", "已确认"),
    ("waist_oval", "20650 x 27500", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.34 (at 280 m)", "2026-11-04", "high", "已确认"),
    ("top_oval", "40500 x 54000", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.34 (at 454 m)", "2026-11-04", "high", "已确认"),
    ("twist", "-45", "deg", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.34", "2026-11-04", "high", "已确认"),
    ("core_outer", "17000 x 14000", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.31", "2026-11-04", "high", "已确认"),
    ("core_wall", "1000 -> 400", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.31", "2026-11-04", "high", "已确认"),
    ("core_long_axis", "18 deg west of north", "deg", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.31", "2026-11-04", "high", "已确认"),
    ("antenna_octagon", "13000 diagonal", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.32", "2026-11-04", "high", "已确认"),
    ("connection_girder_levels", "204000/230000/272000/303000", "mm", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.36", "2026-11-04", "high", "已确认"),
    ("total_mass", "100000", "t", "A", "encyclopedic", "Wikipedia Canton Tower (citing public data)", "2026-11-04", "medium", "已查证/非建模依据"),
    ("ring_inclination", "15.5", "deg", "A", "academic thesis", "Zhang 2015 PolyU thesis, p.34", "2026-11-04", "high", "已查证/未施加（缺节点放样表）"),
    ("ring_beam_idealisation", "46 levels x 24 horizontal straight tubes", "count", "B", "assumption", "thesis gives count; joint coordinates not published", "2026-11-04", "low", "待确认"),
    ("base_datum_shift", "-10 m -> 0 m", "m", "B", "assumption", "source base oval at -10 m; shifted to ground datum", "2026-11-04", "medium", "待确认"),
    ("step_schema", "AP214 / mm", "n/a", "A", "export choice", "OpenCASCADE STEPCAFControl_Writer", "2026-11-04", "high", "已确认"),
    ("steel_density", "7850", "kg/m3", "A", "material standard", "GB/T 700 / general steel", "2026-11-04", "high", "已确认"),
    ("concrete_density", "2500", "kg/m3", "A", "material standard", "GB 50010 normal-weight concrete", "2026-11-04", "high", "已确认"),
    ("column_diameter_schedule", "2400 -> 1600 -> 1400", "mm", "B", "assumption", "not published as a schedule", "2026-11-04", "low", "待确认"),
    ("column_wall", "50", "mm", "B", "assumption", "CFT wall thickness not published", "2026-11-04", "low", "待确认"),
    ("ring_tube_diameter", "640", "mm", "B", "assumption", "derived visually", "2026-11-04", "low", "待确认"),
    ("brace_diameter", "480", "mm", "B", "assumption", "derived visually", "2026-11-04", "low", "待确认"),
    ("floor_thickness", "200", "mm", "B", "assumption", "composite deck assumed", "2026-11-04", "low", "待确认"),
    ("floor_levels", "5 zones / 37 levels", "mm", "B", "assumption", "only counts and zone ranges published", "2026-11-04", "low", "待确认"),
    ("core_eccentricity", "1200, -800", "mm", "B", "assumption", "thesis states centroids differ, value not published", "2026-11-04", "low", "待确认"),
    ("podium", "66000 x 86000 x 1000", "mm", "B", "assumption", "architectural base terrace", "2026-11-04", "low", "待确认"),
    ("observation_deck", "44000 x 58000 x 900", "mm", "B", "assumption", "roof deck envelope", "2026-11-04", "low", "待确认"),
    ("antenna_radius_schedule", "6500 -> 500", "mm", "B", "assumption", "linear schedule between documented ends", "2026-11-04", "low", "待确认"),
    ("mesh_linear_tol", "5", "mm", "A", "meshing choice", "architectural LOD; 0.05 mm not tractable at 600 m", "2026-11-04", "high", "已确认"),
    ("mesh_angular_tol", "0.2", "rad", "A", "meshing choice", "OCCT BRepMesh", "2026-11-04", "high", "已确认"),
    ("mesh_web_linear_tol", "30", "mm", "A", "meshing choice", "web LOD; 3 cm at 600 m scale", "2026-11-04", "high", "已确认"),
    ("mesh_web_angular_tol", "0.45", "rad", "A", "meshing choice", "web LOD angular tolerance", "2026-11-04", "high", "已确认"),
    ("antenna_hybrid", "120 mm shell + 8 corner tubes + X bracing", "n/a", "B", "assumption", "thesis describes an octagonal spatial frame, not a plate shell", "2026-11-04", "low", "待确认"),
]
