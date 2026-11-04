#!/usr/bin/env python3
"""Build the dev page, the GitHub Pages entry page, and standalone HTML files."""
from __future__ import annotations
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ASSETS = ROOT / "assets"
SHELL = (WEB / "shell.html").read_text(encoding="utf-8")
CSS = (WEB / "style.css").read_text(encoding="utf-8")
BUNDLE = (WEB / "bundle.js").read_text(encoding="utf-8")
GLB = (ASSETS / "canton_tower_web.glb").read_bytes()
HDR = (ASSETS / "env" / "night_sky_1k.hdr").read_bytes()
TEX_METAL = (ASSETS / "tex" / "metal_orm.png").read_bytes()
TEX_CONCRETE = (ASSETS / "tex" / "concrete_orm.png").read_bytes()


def build_page(*, asset_base: str, bundle_tag: str, report_link: str,
               bootstrap: str, glb_b64: str = "", standalone: bool = False) -> str:
    s = (SHELL.replace("__CSS__", CSS)
              .replace("__REPORT_LINK__", report_link)
              .replace("__BOOTSTRAP__", bootstrap)
              .replace("__BUNDLE_TAG__", bundle_tag))
    if standalone:
        s = s.replace("__GLB_BASE64__", glb_b64)
    else:
        # Remove the embedded base64 tag entirely on network-served pages.
        s = s.replace('<script id="glb-b64" type="text/plain">__GLB_BASE64__</script>\n', '')
    return s


# 1) Dev page, served from /web/ during development.
dev = build_page(
    asset_base="../assets/",
    bundle_tag='<script src="bundle.js"></script>',
    report_link="reports/validation_report.md",
    bootstrap="window.__ASSET_BASE__='../assets/';",
)
(WEB / "index.html").write_text(dev, encoding="utf-8")

# 2) GitHub Pages root entry, external assets for fast first paint.
deploy = build_page(
    asset_base="assets/",
    bundle_tag='<script src="web/bundle.js"></script>',
    report_link="reports/validation_report.md",
    bootstrap="window.__ASSET_BASE__='assets/';window.__GLB_URL__='assets/canton_tower_web.glb';",
)
(ROOT / "index.html").write_text(deploy, encoding="utf-8")

# 3) Standalone offline HTML: all render assets as data URIs + GLB base64.
b64 = base64.b64encode(GLB).decode("ascii")
hdr_data = "data:application/octet-stream;base64," + base64.b64encode(HDR).decode("ascii")
metal_data = "data:image/png;base64," + base64.b64encode(TEX_METAL).decode("ascii")
concrete_data = "data:image/png;base64," + base64.b64encode(TEX_CONCRETE).decode("ascii")
bootstrap = (
    "window.__ASSET_BASE__='assets/';"
    "window.__HDR_DATA__=" + repr(hdr_data) + ";"
    "window.__TEX_METAL_DATA__=" + repr(metal_data) + ";"
    "window.__TEX_CONCRETE_DATA__=" + repr(concrete_data) + ";"
)
standalone = build_page(
    asset_base="assets/",
    bundle_tag="<script>" + BUNDLE + "</script>",
    report_link="reports/validation_report.md",
    bootstrap=bootstrap,
    glb_b64=b64,
    standalone=True,
)
out_root = ROOT.parent / "canton-tower.html"
out_root.write_text(standalone, encoding="utf-8")
(ROOT / "canton-tower.html").write_text(standalone, encoding="utf-8")

print("dev:", WEB / "index.html", (WEB / "index.html").stat().st_size)
print("deploy:", ROOT / "index.html", (ROOT / "index.html").stat().st_size)
print("standalone:", out_root, out_root.stat().st_size)
print("glb base64 chars:", len(b64), "hdr data chars:", len(hdr_data))
