#!/usr/bin/env python3
"""Generate the render-only IBL and ORM assets.

HDR: 1024x512 Radiance RGBE equirectangular night sky, generated procedurally.
     Deterministic. Released CC0 by this project.
ORM: 512x512 tileable metalness/roughness maps (green=roughness, blue=metalness).
     Generated procedurally. Released CC0 by this project.
The CAD geometry, STEP and GLB are not modified by this script.
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
ENV = ROOT / "env" / "night_sky_1k.hdr"
METAL = ROOT / "tex" / "metal_orm.png"
CONCRETE = ROOT / "tex" / "concrete_orm.png"
ENV.parent.mkdir(parents=True, exist_ok=True)
METAL.parent.mkdir(parents=True, exist_ok=True)

W, H = 1024, 512
x = (np.arange(W) + 0.5) / W * 2.0 * math.pi - math.pi
y = (np.arange(H) + 0.5) / H * math.pi
az, el = np.meshgrid(x, y)  # az -pi..pi, el 0 top .. pi bottom
elev = math.pi / 2 - el
# equirect direction (Y up; +Z is front)
dx = np.cos(elev) * np.sin(az)
dy = np.sin(elev)
dz = np.cos(elev) * np.cos(az)

# --- night sky base ---
sky = np.zeros((H, W, 3), dtype=np.float64)
sky[..., 0] = 0.006 + 0.010 * np.cos(np.clip(elev, 0, None))
sky[..., 1] = 0.010 + 0.020 * np.cos(np.clip(elev, 0, None))
sky[..., 2] = 0.020 + 0.045 * np.cos(np.clip(elev, 0, None))
# warm horizon band
horizon = np.exp(-np.abs(elev) / 0.10)[..., None]
sky += horizon * np.array([0.13, 0.075, 0.035])
# subtle city glow lobes
for a0, amp in [(-2.2, 0.25), (-0.7, 0.12), (1.5, 0.09)]:
    lob = np.exp(-((np.angle(np.exp(1j * (az - a0)))) ** 2) / 0.22) * np.exp(-np.abs(elev) / 0.10)
    sky += lob[..., None] * np.array([amp, amp * 0.55, amp * 0.25])
# deep ground below horizon (not visible in reflections much)
ground = elev < -0.02
sky[ground] *= 0.25

# --- warm sun low over the city ---
sun_dir = np.array([0.42, 0.10, 0.90]); sun_dir = sun_dir / np.linalg.norm(sun_dir)
d = np.clip(dx * sun_dir[0] + dy * sun_dir[1] + dz * sun_dir[2], -1, 1)
sun = np.exp((d - 1.0) / 0.00075) * 7.0
sky += sun[..., None] * np.array([1.0, 0.52, 0.20])
# moon / cool fill
moon_dir = np.array([-0.35, 0.52, -0.78]); moon_dir = moon_dir / np.linalg.norm(moon_dir)
d2 = np.clip(dx * moon_dir[0] + dy * moon_dir[1] + dz * moon_dir[2], -1, 1)
moon = np.exp((d2 - 1.0) / 0.00035) * 2.2
sky += moon[..., None] * np.array([0.55, 0.68, 1.0])

# gentle broken clouds / haze to break up the gradient
yy, xx = np.mgrid[0:H, 0:W]
noise = (np.sin(xx * 0.013 + np.sin(yy * 0.021) * 2.0) * 0.5 + 0.5)
noise *= (np.sin(yy * 0.037 + 1.3) * 0.5 + 0.5)
cloud = (np.exp(-np.abs(elev) / 0.18) * noise)[..., None] * 0.035
sky += cloud

# posterise nothing; keep HDR values. Encode RGBE (shared exponent).
rgb = np.clip(sky, 0, None)
maxc = rgb.max(axis=2)
mant, exp = np.frexp(maxc)
scale = np.where(maxc > 1e-12, 255.0 * mant / np.maximum(maxc, 1e-12), 0.0)
rgbe = np.empty((H, W, 4), dtype=np.uint8)
rgbe[..., 0] = np.clip(rgb[..., 0] * scale, 0, 255).astype(np.uint8)
rgbe[..., 1] = np.clip(rgb[..., 1] * scale, 0, 255).astype(np.uint8)
rgbe[..., 2] = np.clip(rgb[..., 2] * scale, 0, 255).astype(np.uint8)
rgbe[..., 3] = np.clip(exp + 128, 0, 255).astype(np.uint8)

header = b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y %d +X %d\n" % (H, W)
ENV.write_bytes(header + rgbe.tobytes())
print("wrote", ENV, ENV.stat().st_size)


def save_orm(path: Path, metalness: bool):
    rng = np.random.default_rng(20261104 if metalness else 20261105)
    size = 512
    yy, xx = np.mgrid[0:size, 0:size]
    # low-frequency mottling + fine grain
    field = (np.sin(xx * 0.045 + np.sin(yy * 0.071) * 1.8)
             + np.cos(yy * 0.039 + np.sin(xx * 0.053) * 1.4)) * 0.5
    grain = rng.normal(0, 1, (size, size))
    grain = (grain + np.roll(grain, 1, 0) + np.roll(grain, 1, 1)) / 3.0
    if metalness:
        # brushed metal: vertical streak structure + oxidation
        streaks = (np.sin(xx * 0.9 + np.sin(yy * 0.02) * 3.0) * 0.5 + 0.5)
        rough = 0.30 + 0.22 * (1 - streaks) + 0.06 * field + 0.025 * grain
        metal = 0.48 + 0.20 * streaks + 0.05 * field
    else:
        # concrete: high roughness, almost no metalness
        rough = 0.72 + 0.10 * field + 0.025 * grain
        metal = 0.02 + 0.035 * (1 - field)
    rough = np.clip(rough, 0, 1)
    metal = np.clip(metal, 0, 1)
    out = np.zeros((size, size, 3), dtype=np.uint8)
    out[..., 0] = 0
    out[..., 1] = (rough * 255).astype(np.uint8)
    out[..., 2] = (metal * 255).astype(np.uint8)
    Image.fromarray(out, "RGB").save(path)
    print("wrote", path, path.stat().st_size)


save_orm(METAL, True)
save_orm(CONCRETE, False)
