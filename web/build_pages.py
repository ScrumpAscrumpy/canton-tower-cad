#!/usr/bin/env python3
"""Build the dev page and the fully self-contained interactive HTML."""
from __future__ import annotations
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SHELL = (WEB / "shell.html").read_text(encoding="utf-8")
CSS = (WEB / "style.css").read_text(encoding="utf-8")
BUNDLE = (WEB / "bundle.js").read_text(encoding="utf-8")
GLB = (ROOT / "out" / "canton_tower_web.glb").read_bytes()

# Dev page: external bundle + external GLB (app falls back to ../out/...).
dev = (SHELL.replace("__CSS__", CSS)
            .replace("__BUNDLE__", "/* dev: see bundle.js */")
            .replace("__GLB_BASE64__", "")
            .replace("__REPORT_LINK__", "reports/validation_report.md"))
dev = dev.replace('<script id="glb-b64" type="text/plain"></script>', '')
dev = dev.replace("</body>", '<script src="bundle.js"></script>\n</body>')
(WEB / "index.html").write_text(dev, encoding="utf-8")

# Standalone page: inline CSS, JS, and base64 GLB.
b64 = base64.b64encode(GLB).decode("ascii")
standalone = (SHELL.replace("__CSS__", CSS)
                   .replace("__BUNDLE__", BUNDLE)
                   .replace("__GLB_BASE64__", b64)
                   .replace("__REPORT_LINK__", "canton-tower-cad/reports/validation_report.md"))
out_root = ROOT.parent / "canton-tower.html"
out_root.write_text(standalone, encoding="utf-8")
(ROOT / "canton-tower.html").write_text(
    standalone.replace('href="canton-tower-cad/reports/validation_report.md"',
                       'href="reports/validation_report.md"'), encoding="utf-8")
print("dev page:", WEB / "index.html", (WEB / "index.html").stat().st_size)
print("standalone:", out_root, out_root.stat().st_size)
print("glb base64 chars:", len(b64))
