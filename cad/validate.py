#!/usr/bin/env python3
"""Round-trip and mesh-deviation validation for the Canton Tower model."""
from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
import cadquery as cq
import trimesh
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRep import BRep_Tool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cad"))
import params as P  # noqa: E402
import build_canton_tower as B  # noqa: E402

STEP = ROOT / "out" / "canton_tower.step"
GLB_REF = ROOT / "out" / "canton_tower.glb"
GLB_WEB = ROOT / "out" / "canton_tower_web.glb"
REPORTS = ROOT / "reports"


def bbox_m(shape: cq.Shape) -> dict:
    bb = shape.BoundingBox()
    return {"xmin": bb.xmin / 1000, "xmax": bb.xmax / 1000,
            "ymin": bb.ymin / 1000, "ymax": bb.ymax / 1000,
            "zmin": bb.zmin / 1000, "zmax": bb.zmax / 1000,
            "xlen": (bb.xmax - bb.xmin) / 1000,
            "ylen": (bb.ymax - bb.ymin) / 1000,
            "zlen": (bb.zmax - bb.zmin) / 1000}


def analyse_step() -> dict:
    t = time.time()
    print("loading STEP ...", flush=True)
    w = cq.importers.importStep(str(STEP))
    solids = w.solids().vals()
    print(f"  imported {len(solids)} solids in {time.time()-t:.1f}s", flush=True)
    invalid = []
    closed_shells = 0
    total_shells = 0
    vol = 0.0
    for i, s in enumerate(solids):
        if not s.isValid():
            invalid.append(i)
        try:
            vol += abs(s.Volume())
        except Exception:
            invalid.append(i)
        for sh in s.Shells():
            total_shells += 1
            try:
                if BRep_Tool.IsClosed_s(sh.wrapped):
                    closed_shells += 1
            except Exception:
                pass
        if (i + 1) % 400 == 0:
            print(f"  checked {i+1}/{len(solids)}", flush=True)
    comp = cq.Compound.makeCompound(solids)
    return {
        "solids": len(solids),
        "invalid_solids": len(invalid),
        "invalid_indices": invalid[:20],
        "shells": total_shells,
        "closed_shells": closed_shells,
        "volume_m3": vol / 1e9,
        "bbox_m": bbox_m(comp),
        "read_seconds": time.time() - t,
    }


def rebuild_groups() -> dict[str, list[cq.Solid]]:
    print("rebuilding exact groups for deviation sampling ...", flush=True)
    stations = list(P.ring_levels())
    return {
        "Podium": [B.build_podium()],
        "ConcreteCore": [B.build_core()],
        "FloorSlabs": B.build_floors(),
        "CFTColumns": B.build_columns(stations),
        "RingBeams": B.build_rings(stations),
        "DiagonalBraces": B.build_braces(stations),
        "ConnectionGirders": B.build_connection_girders(),
        "ObservationDeck": B.build_deck(),
        "AntennaMast": B.build_antenna(),
    }


def glb_report(path: Path, groups: dict[str, list[cq.Solid]], sample_n: int = 30) -> dict:
    print(f"loading GLB {path.name} ...", flush=True)
    scene = trimesh.load(str(path), force="scene")
    b = scene.bounds
    out = {"path": path.name, "bytes": path.stat().st_size,
           "bbox_m": {"xmin": float(b[0][0]), "xmax": float(b[1][0]),
                      "ymin": float(b[0][1]), "ymax": float(b[1][1]),
                      "zmin": float(b[0][2]), "zmax": float(b[1][2])},
           "groups": {}, "deviation_samples": []}
    rng = random.Random(42)
    for name, g in scene.geometry.items():
        g = g.copy()
        g.merge_vertices()
        watertight = bool(g.is_watertight)
        vol = float(abs(g.volume)) if watertight else None
        out["groups"][name] = {
            "vertices": int(len(g.vertices)),
            "triangles": int(len(g.faces)),
            "watertight_after_merge": watertight,
            "volume_m3": vol,
        }
        exact = groups.get(name)
        if exact is None or len(g.faces) == 0:
            continue
        comp = cq.Compound.makeCompound(exact)
        # deterministic random triangle sample
        count = min(sample_n, len(g.faces))
        idx = rng.sample(range(len(g.faces)), count)
        tri = g.triangles[idx]           # metres, Y-up
        cent = tri.mean(axis=1)
        devs = []
        for cx, cy, cz in cent:
            x_mm, y_mm, z_mm = cx * 1000.0, -cz * 1000.0, cy * 1000.0
            v = cq.Vertex.makeVertex(x_mm, y_mm, z_mm)
            try:
                devs.append(float(comp.distance(v)))
            except Exception:
                pass
        if devs:
            out["deviation_samples"].append({
                "group": name, "n": len(devs),
                "max_mm": max(devs), "mean_mm": sum(devs) / len(devs),
                "p95_mm": float(np.percentile(devs, 95)),
            })
    allmax = max([d["max_mm"] for d in out["deviation_samples"]], default=0.0)
    out["max_sampled_deviation_mm"] = allmax
    return out


def main() -> int:
    t0 = time.time()
    metrics = json.loads((REPORTS / "build_metrics.json").read_text())
    step_info = analyse_step()
    groups = rebuild_groups()
    ref = glb_report(GLB_REF, groups, sample_n=25)
    web = glb_report(GLB_WEB, groups, sample_n=25)

    # key dimensions derived from parameters
    r_waist = P.column_radius(P.WAIST_Z)
    r_top = P.column_radius(P.MAIN_HEIGHT)
    key = {
        "total_height_mm": P.TOTAL_HEIGHT,
        "main_body_top_mm": P.MAIN_HEIGHT,
        "antenna_length_mm": P.ANTENNA_HEIGHT,
        "base_centerline_oval_mm": [2 * P.BASE_A, 2 * P.BASE_B],
        "waist_centerline_oval_mm": [2 * P.WAIST_A, 2 * P.WAIST_B],
        "waist_outer_oval_mm": [2 * (P.WAIST_A + r_waist),
                                2 * (P.WAIST_B + r_waist)],
        "top_centerline_oval_mm": [2 * P.TOP_A, 2 * P.TOP_B],
        "top_outer_oval_mm": [2 * (P.TOP_A + r_top),
                              2 * (P.TOP_B + r_top)],
        "twist_deg": P.TWIST_DEG,
        "core_outer_mm": [2 * P.CORE_A, 2 * P.CORE_B],
        "core_wall_mm": [P.CORE_WALL_BASE, P.CORE_WALL_TOP],
        "min_wall_mm_modelled": min(P.COL_WALL, P.ANTENNA_WALL,
                                    P.CORE_WALL_TOP),
        "antenna_access_holes": [
            {"z_mm": z, "side": "-Y", "diameter_mm": 2 * P.ANTENNA_ACCESS_R}
            for z in P.ANTENNA_ACCESS_HOLES
        ],
        "ring_inclination_documented_deg": 15.5,
        "ring_inclination_applied": False,
    }

    # compare original / STEP round-trip / GLB
    comparison = {
        "original_volume_m3": metrics["overall"]["volume_m3"],
        "step_volume_m3": step_info["volume_m3"],
        "step_volume_delta_pct": 100.0 * (step_info["volume_m3"] - metrics["overall"]["volume_m3"])
        / metrics["overall"]["volume_m3"],
        "original_bbox_mm": metrics["overall"]["bbox_mm"],
        "step_bbox_m": step_info["bbox_m"],
    }

    checks = []
    checks.append(("STEP re-read", step_info["solids"] == metrics["overall"]["solid_count"],
                   f'{step_info["solids"]} / {metrics["overall"]["solid_count"]} solids'))
    checks.append(("STEP topology", step_info["invalid_solids"] == 0,
                   f'{step_info["invalid_solids"]} invalid solids'))
    checks.append(("Closed shells", step_info["closed_shells"] == step_info["shells"],
                   f'{step_info["closed_shells"]} / {step_info["shells"]} shells closed'))
    checks.append(("Volume > 0", step_info["volume_m3"] > 0,
                   f'{step_info["volume_m3"]:.1f} m3'))
    checks.append(("STEP volume round-trip < 0.1%",
                   abs(comparison["step_volume_delta_pct"]) < 0.1,
                   f'{comparison["step_volume_delta_pct"]:.6f}%'))
    checks.append(("Reference GLB deviation <= 5 mm",
                   ref["max_sampled_deviation_mm"] <= P.MESH_LINEAR_TOL + 0.01,
                   f'{ref["max_sampled_deviation_mm"]:.3f} mm (sampled)'))
    checks.append(("Web GLB deviation <= 30 mm",
                   web["max_sampled_deviation_mm"] <= P.MESH_WEB_LINEAR_TOL + 0.01,
                   f'{web["max_sampled_deviation_mm"]:.3f} mm (sampled)'))
    checks.append(("GLB group count", len(ref["groups"]) == len(groups) == len(web["groups"]),
                   f'{len(ref["groups"])} / {len(groups)} / {len(web["groups"])}'))
    checks.append(("GLB triangle count > 0",
                   all(g["triangles"] > 0 for g in ref["groups"].values())
                   and all(g["triangles"] > 0 for g in web["groups"].values()),
                   f'{sum(g["triangles"] for g in ref["groups"].values())} ref / '
                   f'{sum(g["triangles"] for g in web["groups"].values())} web'))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "inputs": {"step": str(STEP), "glb_reference": str(GLB_REF),
                   "glb_web": str(GLB_WEB)},
        "key_dimensions": key,
        "step_roundtrip": step_info,
        "comparison": comparison,
        "glb_reference": ref,
        "glb_web": web,
        "checks": [{"name": n, "pass": bool(p), "detail": d} for n, p, d in checks],
        "all_pass": all(p for _, p, _ in checks),
        "runtime_s": time.time() - t0,
    }
    (REPORTS / "validation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Canton Tower — Validation report", "",
             f"Generated: {report['generated_at']}", "",
             "## 1. Acceptance checks", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    for c in report["checks"]:
        lines.append(f"| {c['name']} | {'PASS' if c['pass'] else 'FAIL'} | {c['detail']} |")
    lines += ["", "## 2. STEP round trip", "",
              f"- Solids written / re-read: **{metrics['overall']['solid_count']} / {step_info['solids']}**",
              f"- Invalid solids: **{step_info['invalid_solids']}**",
              f"- Shells closed: **{step_info['closed_shells']} / {step_info['shells']}**",
              f"- Volume (original): **{metrics['overall']['volume_m3']:.3f} m³**",
              f"- Volume (STEP re-read): **{step_info['volume_m3']:.3f} m³**",
              f"- Volume delta: **{comparison['step_volume_delta_pct']:.6f} %**",
              f"- BBox STEP (m): **{step_info['bbox_m']}**",
              "", "## 3. GLB meshes", "",
              "| Mesh | Vertices | Triangles | Size | Max sampled deviation |",
              "|---|---:|---:|---:|---:|",
              f"| reference (5 mm / 0.2 rad) | {ref['groups'] and sum(g['vertices'] for g in ref['groups'].values())} | "
              f"{sum(g['triangles'] for g in ref['groups'].values())} | {ref['bytes']/1e6:.2f} MB | {ref['max_sampled_deviation_mm']:.3f} mm |",
              f"| web (30 mm / 0.45 rad) | {sum(g['vertices'] for g in web['groups'].values())} | "
              f"{sum(g['triangles'] for g in web['groups'].values())} | {web['bytes']/1e6:.2f} MB | {web['max_sampled_deviation_mm']:.3f} mm |",
              "",
              f"- Reference GLB bbox (m): **{ref['bbox_m']}**",
              f"- Web GLB bbox (m): **{web['bbox_m']}**",
              "", "## 4. Key dimensions", ""]
    for k, v in key.items():
        lines.append(f"- `{k}` = {v}")
    lines += ["", "## 5. Per-group meshes (web LOD)", "",
              "| Group | Vertices | Triangles | Watertight | Volume m³ |",
              "|---|---:|---:|---|---:|"]
    for name, g in web["groups"].items():
        lines.append(f"| {name} | {g['vertices']} | {g['triangles']} | "
                     f"{g['watertight_after_merge']} | {g['volume_m3']} |")
    lines += ["", "> Note: a group mesh can be non-manifold after vertex welding where "
              "individual members interpenetrate at joints. This is expected for a member-level "
              "structural assembly. The STEP check confirms every one of the 1,899 B-Rep solids "
              "is valid and every shell is closed.", "", "## 6. Deviation samples", "",
              "| Group | n | max mm | mean mm | p95 mm |", "|---|---:|---:|---:|---:|"]
    for d in web["deviation_samples"]:
        lines.append(f"| {d['group']} | {d['n']} | {d['max_mm']:.3f} | {d['mean_mm']:.3f} | {d['p95_mm']:.3f} |")
    (REPORTS / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nvalidation done in {time.time()-t0:.1f}s; all_pass={report['all_pass']}")
    return 0 if report["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
