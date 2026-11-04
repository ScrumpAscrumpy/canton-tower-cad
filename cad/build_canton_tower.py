#!/usr/bin/env python3
"""
Canton Tower — exact B-Rep build, STEP export, mesh-to-GLB export and metrics.

Run:
    cd canton-tower-cad
    source ../.venv-cad/bin/activate
    python cad/build_canton_tower.py

The script intentionally keeps every structural member as a closed B-Rep solid
inside a named assembly component instead of fusing 600+ members.  This is the
normal exchange representation for a member-level structural model and avoids
fragile, order-dependent global booleans at the joints.  All geometry that is
booleaned (core cavity, floor holes, antenna shells/access holes) is booleaned
in OCCT before export.
"""
from __future__ import annotations

import json
import math
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

import numpy as np
import cadquery as cq
from cadquery import Color, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cad"))
import params as P  # noqa: E402

OUT = ROOT / "out"
REPORTS = ROOT / "reports"
OUT.mkdir(exist_ok=True)
REPORTS.mkdir(exist_ok=True)

FAILURES: list[dict] = []
NOTES: list[dict] = []
LOG: list[str] = []


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.append(line)


def fail(step: str, exc: BaseException) -> None:
    FAILURES.append({
        "step": step,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(limit=4),
    })
    log(f"FAILED {step}: {type(exc).__name__}: {exc}")


def wire_ellipse(z: float, a: float, b: float, rot_deg: float,
                 tx: float = 0.0, ty: float = 0.0) -> cq.Wire:
    w = cq.Workplane("XY").workplane(offset=z).ellipse(a, b).val()
    if rot_deg:
        w = w.rotate(Vector(0, 0, 0), Vector(0, 0, 1), rot_deg)
    if tx or ty:
        w = w.translate(Vector(tx, ty, 0))
    return w


def solid_ellipse(z: float, h: float, a: float, b: float, rot_deg: float,
                  tx: float = 0.0, ty: float = 0.0) -> cq.Solid:
    s = cq.Workplane("XY").workplane(offset=z).ellipse(a, b).extrude(h).val()
    if rot_deg:
        s = s.rotate(Vector(0, 0, 0), Vector(0, 0, 1), rot_deg)
    if tx or ty:
        s = s.translate(Vector(tx, ty, 0))
    return s


def loft_wires(wires: list[cq.Wire], ruled: bool = True) -> cq.Solid:
    return cq.Workplane().add(wires).toPending().loft(ruled=ruled).val()


# ---------------------------------------------------------------------------
# 1. Core — elliptical concrete tube, wall 1000 -> 400 mm, boolean cavity
# ---------------------------------------------------------------------------
def build_core() -> cq.Solid:
    log("core: outer loft / inner cavity cut")
    outer = solid_ellipse(P.BASE_Z, P.MAIN_HEIGHT, P.CORE_A, P.CORE_B,
                          P.CORE_ROT_DEG, P.CORE_OFFSET_X, P.CORE_OFFSET_Y)
    z0 = P.BASE_Z + P.CORE_WALL_BASE          # keep a 1 m bottom cap
    z1 = P.MAIN_HEIGHT - P.CORE_WALL_TOP      # keep a 0.4 m top cap
    w0 = wire_ellipse(z0, P.CORE_A - P.CORE_WALL_BASE, P.CORE_B - P.CORE_WALL_BASE,
                      P.CORE_ROT_DEG, P.CORE_OFFSET_X, P.CORE_OFFSET_Y)
    w1 = wire_ellipse(z1, P.CORE_A - P.CORE_WALL_TOP, P.CORE_B - P.CORE_WALL_TOP,
                      P.CORE_ROT_DEG, P.CORE_OFFSET_X, P.CORE_OFFSET_Y)
    cavity = loft_wires([w0, w1], ruled=True)
    core = outer.cut(cavity)
    if not core.isValid():
        raise RuntimeError("core boolean produced invalid shape")
    return core


# ---------------------------------------------------------------------------
# 2. Outer CFT columns — ruled loft along 46 ring stations, hollow 50 mm
# ---------------------------------------------------------------------------
def build_one_column(j: int, stations: list[float]) -> cq.Solid:
    pts = [Vector(*P.column_point(j, z)) for z in stations]
    normals = []
    for i, p in enumerate(pts):
        if i == 0 or i == len(pts) - 1:
            n = Vector(0, 0, 1)
        else:
            n = (pts[i + 1] - pts[i - 1]).normalized()
        normals.append(n)

    outer_wires = [cq.Wire.makeCircle(P.column_radius(z), p, n)
                   for z, p, n in zip(stations, pts, normals)]

    inner_pts = [Vector(p.x, p.y, p.z + (P.COL_WALL if i == 0 else
                                         -P.COL_WALL if i == len(pts) - 1 else 0))
                 for i, p in enumerate(pts)]
    inner_wires = [cq.Wire.makeCircle(P.column_radius(z) - P.COL_WALL, p, n)
                   for z, p, n in zip(stations, inner_pts, normals)]
    outer = loft_wires(outer_wires, ruled=True)
    inner = loft_wires(inner_wires, ruled=True)
    col = outer.cut(inner)
    if not col.isValid():
        raise RuntimeError(f"column {j} boolean invalid")
    return col


def build_columns(stations: list[float]) -> list[cq.Solid]:
    log(f"columns: 24 hollow CFT ruled lofts, {len(stations)} stations each")
    cols = []
    for j in range(P.N_COLUMNS):
        t = time.time()
        cols.append(build_one_column(j, stations))
        if j % 6 == 5:
            log(f"  columns {j + 1}/24  ({time.time() - t:.2f}s last)")
    return cols


# ---------------------------------------------------------------------------
# 3. Rings — closed periodic B-spline hoops through all 24 column nodes
# ---------------------------------------------------------------------------
def build_rings(stations: list[float]) -> list[cq.Solid]:
    """46 ring levels; each level is 24 straight tubular beams between columns.

    The published structure uses straight steel ring beams connecting the CFT
    joints.  A faceted 24-sided hoop is therefore both closer to the real
    member topology and dramatically lighter to tessellate than a smooth spline
    hoop.  Beam ends finish inside the CFT columns, so the node is concealed.
    """
    log(f"rings: {len(stations)} levels x 24 straight beam segments")
    rings = []
    for k, z in enumerate(stations):
        pts = [Vector(*P.column_point(j, z)) for j in range(P.N_COLUMNS)]
        for j in range(P.N_COLUMNS):
            p0 = pts[j]
            p1 = pts[(j + 1) % P.N_COLUMNS]
            v = p1 - p0
            h = v.Length
            if h < 2 * P.RING_R:
                continue
            ring = cq.Solid.makeCylinder(P.RING_R, h, p0, v.normalized())
            if not ring.isValid():
                raise RuntimeError(f"ring segment z={z}, j={j} invalid")
            rings.append(ring)
    log(f"  ring segments built: {len(rings)}")
    return rings


# ---------------------------------------------------------------------------
# 4. Diagonal braces — 552 straight hollow? solid tubes, alternating panels
# ---------------------------------------------------------------------------
def build_braces(stations: list[float]) -> list[cq.Solid]:
    log("braces: alternating diagonal tubes")
    nodes = [[Vector(*P.column_point(j, z)) for j in range(P.N_COLUMNS)]
             for z in stations]
    braces = []
    for i in range(len(stations) - 1):
        for j in range(P.N_COLUMNS):
            if (i + j) % 2 != 0:
                continue
            p0 = nodes[i][j]
            p1 = nodes[i + 1][(j + 1) % P.N_COLUMNS]
            v = p1 - p0
            h = v.Length
            if h < 2 * P.BRACE_R:
                continue
            braces.append(cq.Solid.makeCylinder(
                P.BRACE_R, h, p0, v.normalized()))
    log(f"  braces built: {len(braces)}")
    return braces


# ---------------------------------------------------------------------------
# 5. Floors — 37 annular composite slabs with a core clearance hole
# ---------------------------------------------------------------------------
def build_floors() -> list[cq.Solid]:
    log(f"floors: {len(P.floor_levels())} annular slabs")
    floors = []
    for z in P.floor_levels():
        e = P.envelope(z)
        a = e.a * P.FLOOR_OUTER_FACTOR
        b = e.b * P.FLOOR_OUTER_FACTOR
        slab = solid_ellipse(z, P.FLOOR_THICK, a, b, math.degrees(e.phi))
        hole = solid_ellipse(
            z - P.FLOOR_HOLE_OVERSHOOT, P.FLOOR_THICK + 2 * P.FLOOR_HOLE_OVERSHOOT,
            P.CORE_A + P.FLOOR_HOLE_CLEARANCE,
            P.CORE_B + P.FLOOR_HOLE_CLEARANCE,
            P.CORE_ROT_DEG, P.CORE_OFFSET_X, P.CORE_OFFSET_Y)
        slab = slab.cut(hole)
        if not slab.isValid():
            raise RuntimeError(f"floor at z={z} invalid")
        floors.append(slab)
    return floors


# ---------------------------------------------------------------------------
# 6. Connection girders at 204/230/272/303 m
# ---------------------------------------------------------------------------
def build_connection_girders() -> list[cq.Solid]:
    log("connection girders: 4 levels x 8 radial box girders")
    beams = []
    for z in P.CONNECTION_LEVELS:
        for j in range(P.CONNECTION_BEAMS):
            col_j = int(round(j * P.N_COLUMNS / P.CONNECTION_BEAMS)) % P.N_COLUMNS
            ex, ey, _ = P.column_point(col_j, z)
            cx, cy = P.CORE_OFFSET_X, P.CORE_OFFSET_Y
            dx, dy = ex - cx, ey - cy
            length = math.hypot(dx, dy) - 500.0
            ang = math.degrees(math.atan2(dy, dx))
            beam = (cq.Workplane("XY").box(length, P.CONNECTION_BEAM_W,
                                           P.CONNECTION_BEAM_H)
                    .translate((length / 2.0, 0, 0))
                    .rotate((0, 0, 0), (0, 0, 1), ang)
                    .translate((cx, cy, z)).val())
            if not beam.isValid():
                raise RuntimeError(f"girder at z={z}, j={j} invalid")
            beams.append(beam)
    return beams


# ---------------------------------------------------------------------------
# 7. Observation deck at 449 m + railing
# ---------------------------------------------------------------------------
def build_deck() -> list[cq.Solid]:
    log("observation deck: annular slab and railing")
    slab = (cq.Workplane("XY").workplane(offset=P.DECK_Z)
            .ellipse(P.DECK_OUTER_A, P.DECK_OUTER_B)
            .ellipse(P.DECK_INNER_A, P.DECK_INNER_B)
            .extrude(P.DECK_THICK).val())
    # railing hoop at deck top, just inside the outer edge
    z = P.DECK_Z + P.DECK_THICK
    a = P.DECK_OUTER_A - P.DECK_RAIL_INSET
    b = P.DECK_OUTER_B - P.DECK_RAIL_INSET
    path = cq.Workplane("XY").workplane(offset=z).ellipse(a, b).val()
    prof = cq.Wire.makeCircle(P.DECK_RAIL_R, Vector(a, 0, z), Vector(0, 1, 0))
    rail = cq.Workplane().add(prof).toPending().sweep(
        path, isFrenet=True, makeSolid=True).val()
    if not (slab.isValid() and rail.isValid()):
        raise RuntimeError("deck boolean/sweep invalid")
    return [slab, rail]


# ---------------------------------------------------------------------------
# 8. Antenna — octagonal tapered shell, flanges, access holes, tip
# ---------------------------------------------------------------------------
def build_antenna() -> list[cq.Solid]:
    log("antenna: octagonal loft, shell, flanges, holes, tip")
    wires = []
    for z, r in P.ANTENNA_SECTIONS:
        wires.append(cq.Workplane("XY").workplane(offset=z).polygon(8, r).val())
    outer = loft_wires(wires, ruled=True)
    try:
        body = cq.Workplane(obj=outer).shell(-P.ANTENNA_WALL).val()
        if not body.isValid():
            raise RuntimeError("shell result invalid")
        log("  antenna shell feature: OK")
    except Exception as exc:
        # Exact fallback: an offset inner octagonal loft cut.  This is still a
        # B-Rep boolean, not a mesh approximation.  The shell failure is recorded.
        msg = (f"OCCT shell(-{P.ANTENNA_WALL}) failed on the tapered octagonal "
               f"loft ({type(exc).__name__}: {exc}); exact inner-loft boolean "
               f"fallback used")
        NOTES.append({"feature": "antenna shell", "note": msg})
        log("  NOTE: " + msg)
        shrink = P.ANTENNA_WALL / math.cos(math.pi / 8.0)
        iw = []
        for i, (z, r) in enumerate(P.ANTENNA_SECTIONS):
            zi = z + (P.ANTENNA_WALL if i == 0 else
                      -P.ANTENNA_WALL if i == len(P.ANTENNA_SECTIONS) - 1 else 0.0)
            iw.append(cq.Workplane("XY").workplane(offset=zi)
                      .polygon(8, r - shrink).val())
        inner = loft_wires(iw, ruled=True)
        body = outer.cut(inner)
    if not body.isValid():
        raise RuntimeError("antenna shell/cut invalid")

    parts = [body]
    # 12 octagonal flange bands
    for i in range(P.ANTENNA_FLANGE_COUNT):
        z = P.ANTENNA_FLANGE_Z0 + i * (P.ANTENNA_FLANGE_Z1 - P.ANTENNA_FLANGE_Z0) / (P.ANTENNA_FLANGE_COUNT - 1)
        r = P.antenna_radius(z)
        band = (cq.Workplane("XY").workplane(offset=z - P.ANTENNA_FLANGE_H / 2)
                .polygon(8, r + P.ANTENNA_FLANGE_OUT)
                .polygon(8, r - P.ANTENNA_FLANGE_IN)
                .extrude(P.ANTENNA_FLANGE_H).val())
        if not band.isValid():
            raise RuntimeError(f"antenna flange at {z} invalid")
        parts.append(band)

    # 4 access holes through the -Y wall
    for z in P.ANTENNA_ACCESS_HOLES:
        r = P.antenna_radius(z)
        cutter = cq.Solid.makeCylinder(
            P.ANTENNA_ACCESS_R, r + 150.0, Vector(0, -r - 100.0, z), Vector(0, 1, 0))
        body = body.cut(cutter)
    parts[0] = body
    if not body.isValid():
        raise RuntimeError("antenna access holes invalid")

    # Octagonal spatial-frame expression: 8 corner chords + 2 diagonals per
    # face/segment.  This is the documented "steel spatial frame with octagonal
    # section" rather than a bare tube.
    def corners(z, r):
        return [Vector(r * math.cos(2 * math.pi * k / 8.0),
                       r * math.sin(2 * math.pi * k / 8.0), z)
                for k in range(8)]

    section_pts = [corners(z, r) for z, r in P.ANTENNA_SECTIONS]
    for i in range(len(P.ANTENNA_SECTIONS) - 1):
        for k in range(8):
            p0 = section_pts[i][k]
            p1 = section_pts[i + 1][k]
            v = p1 - p0
            parts.append(cq.Solid.makeCylinder(P.ANTENNA_CORNER_R, v.Length, p0, v.normalized()))
            a0 = section_pts[i][k]
            a1 = section_pts[i + 1][(k + 1) % 8]
            va = a1 - a0
            parts.append(cq.Solid.makeCylinder(P.ANTENNA_DIAGONAL_R, va.Length, a0, va.normalized()))
            b0 = section_pts[i][(k + 1) % 8]
            b1 = section_pts[i + 1][k]
            vb = b1 - b0
            parts.append(cq.Solid.makeCylinder(P.ANTENNA_DIAGONAL_R, vb.Length, b0, vb.normalized()))

    tip = cq.Solid.makeCone(
        P.ANTENNA_TIP_R, P.ANTENNA_TOP_R, P.TOTAL_HEIGHT - P.ANTENNA_TIP_Z,
        Vector(0, 0, P.ANTENNA_TIP_Z), Vector(0, 0, 1))
    parts.append(tip)
    return parts


# ---------------------------------------------------------------------------
# 9. Podium
# ---------------------------------------------------------------------------
def build_podium() -> cq.Solid:
    log("podium: elliptical terrace")
    p = (cq.Workplane("XY").workplane(offset=0.0)
         .ellipse(P.PODIUM_A, P.PODIUM_B).extrude(P.PODIUM_H))
    try:
        p = p.edges(">Z").fillet(P.PODIUM_FILLET)
    except Exception as exc:
        fail("podium top fillet", exc)
        raise
    s = p.val()
    if not s.isValid():
        raise RuntimeError("podium invalid")
    return s


# ---------------------------------------------------------------------------
# Metrics / export
# ---------------------------------------------------------------------------
def bbox_mm(shape: cq.Shape) -> dict:
    bb = shape.BoundingBox()
    return {"xmin": bb.xmin, "xmax": bb.xmax, "ymin": bb.ymin,
            "ymax": bb.ymax, "zmin": bb.zmin, "zmax": bb.zmax,
            "xlen": bb.xmax - bb.xmin, "ylen": bb.ymax - bb.ymin,
            "zlen": bb.zmax - bb.zmin}


def group_metrics(name: str, shapes: list[cq.Solid], density: float,
                  color: list[int]) -> dict:
    vol_mm3 = 0.0
    invalid = 0
    solids = 0
    for s in shapes:
        try:
            if s.isValid():
                solids += 1
            else:
                invalid += 1
            vol_mm3 += abs(s.Volume())
        except Exception:
            invalid += 1
    compound = cq.Compound.makeCompound(shapes)
    vol_m3 = vol_mm3 / 1e9
    mass_t = vol_m3 * density / 1000.0
    return {
        "name": name,
        "solid_count": solids,
        "invalid_solids": invalid,
        "volume_m3": vol_m3,
        "mass_t": mass_t,
        "density_kg_m3": density,
        "color_rgb": color,
        "bbox_mm": bbox_mm(compound),
    }


def mesh_absolute(shape: cq.Shape, tol: float, ang: float) -> tuple[np.ndarray, np.ndarray]:
    """Absolute-deflection OCCT meshing.

    CadQuery's Shape.tessellate() calls BRepMesh_IncrementalMesh with
    isRelative=True, so its "tolerance" is not a millimetre value on a 600 m
    object.  This helper passes isRelative=False and extracts the triangulation
    directly, guaranteeing the stated linear deflection in model units (mm).
    """
    from OCP.BRepTools import BRepTools
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopAbs import TopAbs_Orientation

    BRepTools.Clean_s(shape.wrapped)
    BRepMesh_IncrementalMesh(shape.wrapped, tol, False, ang, True)
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for f in shape.Faces():
        loc = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(f.wrapped, loc)
        if poly is None:
            continue
        trsf = loc.Transformation()
        reverse = f.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
        base = len(verts)
        verts.extend((v.X(), v.Y(), v.Z()) for v in
                     (poly.Node(i).Transformed(trsf) for i in range(1, poly.NbNodes() + 1)))
        if reverse:
            faces.extend((base + t.Value(1) - 1, base + t.Value(3) - 1,
                          base + t.Value(2) - 1) for t in poly.Triangles())
        else:
            faces.extend((base + t.Value(1) - 1, base + t.Value(2) - 1,
                          base + t.Value(3) - 1) for t in poly.Triangles())
    return np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def tessellate_group(shapes: list[cq.Solid], tol: float, ang: float) -> tuple[np.ndarray, np.ndarray]:
    verts: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    off = 0
    for s in shapes:
        v, f = mesh_absolute(s, tol, ang)
        if len(v) == 0:
            continue
        verts.append(v)
        faces.append(f + off)
        off += len(v)
    if not verts:
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int64)
    return np.vstack(verts), np.vstack(faces)



def export_glb(groups: list[dict], tol: float, ang: float, glb_path: Path,
               web: bool = False) -> dict:
    import trimesh
    from trimesh.visual.material import PBRMaterial

    scene = trimesh.Scene()
    scene.metadata["name"] = "Canton Tower — 广州塔"
    out_groups = []
    total_v = total_f = 0
    # Z-up mm -> Y-up m: (x,y,z) -> (x/1000, z/1000, -y/1000)
    T = np.array([[0.001, 0, 0, 0],
                  [0, 0, 0.001, 0],
                  [0, -0.001, 0, 0],
                  [0, 0, 0, 1]], dtype=np.float64)
    for g in groups:
        tv = time.time()
        verts, faces = tessellate_group(g["_shapes"], tol, ang)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        mesh.apply_transform(T)
        rgba = [float(c) for c in g["_mesh_color"]] + [1.0]
        mat = PBRMaterial(baseColorFactor=rgba,
                          metallicFactor=float(g["_metallic"]),
                          roughnessFactor=float(g["_roughness"]))
        mesh.visual = trimesh.visual.TextureVisuals(material=mat)
        scene.add_geometry(mesh, node_name=g["name"], geom_name=g["name"])
        out_groups.append({"name": g["name"], "vertices": int(len(verts)),
                           "triangles": int(len(faces))})
        total_v += len(verts)
        total_f += len(faces)
        log(f"  mesh {g['name']}: {len(verts)} verts, {len(faces)} tris "
            f"({time.time() - tv:.1f}s)")
    glb_path.write_bytes(scene.export(file_type="glb"))
    log(f"GLB written: {glb_path} ({glb_path.stat().st_size / 1e6:.1f} MB), "
        f"{total_v} verts / {total_f} tris")
    return {"path": glb_path.name, "linear_tol_mm": tol,
            "angular_tol_rad": ang, "vertices": int(total_v),
            "triangles": int(total_f), "bytes": glb_path.stat().st_size,
            "groups": out_groups, "web_lod": web}


def main() -> int:
    t_start = time.time()
    log("Canton Tower build start")
    stations = list(P.ring_levels())
    log(f"ring stations: {len(stations)}  z=[{stations[0]:.0f}, {stations[-1]:.0f}] mm")

    groups: list[dict] = []

    def add_group(name, shapes, density, color, mesh_color, metallic=0.8, rough=0.35):
        if not shapes:
            return
        gm = group_metrics(name, shapes, density, color)
        gm["_mesh_color"] = mesh_color
        gm["_metallic"] = metallic
        gm["_roughness"] = rough
        gm["_shapes"] = shapes
        groups.append(gm)
        log(f"  group {name}: {gm['solid_count']} solids, "
            f"{gm['volume_m3']:.1f} m3, {gm['mass_t']:.0f} t")

    # Build in dependency order
    podium = build_podium()
    add_group("Podium", [podium], P.RHO_CONCRETE, [154, 160, 166],
              [0.58, 0.61, 0.64], 0.15, 0.85)

    core = build_core()
    add_group("ConcreteCore", [core], P.RHO_CONCRETE, [206, 203, 196],
              [0.80, 0.79, 0.75], 0.05, 0.9)

    floors = build_floors()
    add_group("FloorSlabs", floors, P.RHO_CONCRETE, [108, 133, 148],
              [0.38, 0.55, 0.66], 0.1, 0.65)

    columns = build_columns(stations)
    add_group("CFTColumns", columns, P.RHO_STEEL, [228, 231, 234],
              [0.88, 0.90, 0.92], 0.65, 0.32)

    rings = build_rings(stations)
    add_group("RingBeams", rings, P.RHO_STEEL, [214, 219, 224],
              [0.82, 0.85, 0.88], 0.7, 0.3)

    braces = build_braces(stations)
    add_group("DiagonalBraces", braces, P.RHO_STEEL, [197, 205, 212],
              [0.72, 0.77, 0.82], 0.7, 0.32)

    girders = build_connection_girders()
    add_group("ConnectionGirders", girders, P.RHO_STEEL, [164, 174, 184],
              [0.58, 0.64, 0.70], 0.65, 0.38)

    deck = build_deck()
    add_group("ObservationDeck", deck, P.RHO_CONCRETE, [120, 178, 198],
              [0.42, 0.68, 0.78], 0.25, 0.45)

    antenna = build_antenna()
    add_group("AntennaMast", antenna, P.RHO_STEEL, [242, 244, 246],
              [0.94, 0.95, 0.96], 0.75, 0.28)

    # Overall bbox and totals
    all_shapes = [s for g in groups for s in g["_shapes"]]
    all_compound = cq.Compound.makeCompound(all_shapes)
    total_vol = sum(g["volume_m3"] for g in groups)
    total_mass = sum(g["mass_t"] for g in groups)
    overall = {
        "solid_count": sum(g["solid_count"] for g in groups),
        "invalid_solids": sum(g["invalid_solids"] for g in groups),
        "volume_m3": total_vol,
        "mass_t": total_mass,
        "bbox_mm": bbox_mm(all_compound),
    }
    log(f"TOTAL: {overall['solid_count']} solids, {total_vol:.1f} m3, "
        f"{total_mass:.0f} t, bbox {overall['bbox_mm']}")

    # STEP assembly (names + colours retained)
    log("writing STEP assembly")
    assy = cq.Assembly(name="CantonTower")
    for g in groups:
        assy.add(cq.Compound.makeCompound(g["_shapes"]), name=g["name"],
                 color=Color(*[c / 255.0 for c in g["color_rgb"]]))
    step_path = OUT / "canton_tower.step"
    assy.export(str(step_path), exportType="STEP")
    log(f"STEP written: {step_path} ({step_path.stat().st_size / 1e6:.1f} MB)")

    # GLB — reference (5 mm) and web LOD (12 mm)
    log(f"meshing reference GLB: linear {P.MESH_LINEAR_TOL} mm, angular {P.MESH_ANGULAR_TOL} rad")
    ref_glb = export_glb(groups, P.MESH_LINEAR_TOL, P.MESH_ANGULAR_TOL,
                         OUT / "canton_tower.glb", web=False)
    log(f"meshing web GLB: linear {P.MESH_WEB_LINEAR_TOL} mm, angular {P.MESH_WEB_ANGULAR_TOL} rad")
    web_glb = export_glb(groups, P.MESH_WEB_LINEAR_TOL, P.MESH_WEB_ANGULAR_TOL,
                         OUT / "canton_tower_web.glb", web=True)

    # Clean internal keys before JSON
    for g in groups:
        g.pop("_shapes", None)
        g.pop("_mesh_color", None)
        g.pop("_metallic", None)
        g.pop("_roughness", None)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "units_step": "mm",
        "units_glb": "m (render-only derivative, Y-up)",
        "coordinate_system_step": "right-handed, X east, Y north, Z up; ground Z=0",
        "mesh_reference": ref_glb,
        "mesh_web": web_glb,
        "parameters": {k: v for k, v in vars(P).items()
                       if k.isupper() and isinstance(v, (int, float, str, tuple))},
        "envelope_design": [
            {"z_mm": P.BASE_Z, "center_width_mm": 2 * P.BASE_A,
             "center_depth_mm": 2 * P.BASE_B, "twist_deg": 0.0},
            {"z_mm": P.WAIST_Z, "center_width_mm": 2 * P.WAIST_A,
             "center_depth_mm": 2 * P.WAIST_B,
             "twist_deg": P.TWIST_DEG * (P.WAIST_Z - P.BASE_Z) / P.MAIN_HEIGHT},
            {"z_mm": P.MAIN_HEIGHT, "center_width_mm": 2 * P.TOP_A,
             "center_depth_mm": 2 * P.TOP_B, "twist_deg": P.TWIST_DEG},
        ],
        "overall": overall,
        "groups": groups,
        "failures": FAILURES,
        "kernel_notes": NOTES,
        "log": LOG,
        "runtime_s": time.time() - t_start,
    }
    (REPORTS / "build_metrics.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORTS / "build.log").write_text("\n".join(LOG), encoding="utf-8")
    log(f"build complete in {time.time() - t_start:.1f}s; failures={len(FAILURES)}")
    return 0 if not FAILURES else 2


if __name__ == "__main__":
    raise SystemExit(main())
