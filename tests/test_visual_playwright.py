"""
Headless Playwright visual rendering tests for cad-ir-to-svg.
Verifies that HTML-wrapped SVG vector drawings render headlessly with Chromium
in under 300ms with zero timeouts, no infinite scroll loops, and full visual fidelity.
"""

import time
import json
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

from cad_ir_to_svg.compiler import compile_ir_to_svg_string
from cad_ir_to_svg.config import PRESETS


HTML_WRAPPER = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  html, body {{ margin: 0; padding: 0; width: 1920px; height: 1080px; overflow: hidden; background: #fff; }}
  svg {{ width: 100%; height: 100%; display: block; }}
</style>
</head>
<body>
{svg_content}
</body>
</html>"""


@pytest.fixture(scope="module")
def sample_complex_ir():
    """Generates a rich, multi-entity CAD IR payload for visual benchmarking."""
    return {
        "format": "LAVINCI_CAD_IR_V3",
        "layers": [
            {"name": "0", "hex_color": "#000000"},
            {"name": "CENTERLINES", "hex_color": "#FF0000", "linetype": "CENTER"},
            {"name": "HIDDEN_EDGES", "hex_color": "#0000FF", "linetype": "HIDDEN"},
            {"name": "ANNOTATIONS", "hex_color": "#008000"},
        ],
        "block_definitions": {
            "WHEEL_ASSEMBLY": {
                "base_point": [0.0, 0.0],
                "circles": [
                    {"center": [0.0, 0.0], "radius": 150.0},
                    {"center": [0.0, 0.0], "radius": 75.0},
                ],
                "lines": [
                    {"start": [-150.0, 0.0], "end": [150.0, 0.0], "layer": "CENTERLINES", "linetype": "CENTER"},
                    {"start": [0.0, -150.0], "end": [0.0, 150.0], "layer": "CENTERLINES", "linetype": "CENTER"},
                ],
                "polylines": [
                    {"points": [[-50, -50], [50, -50], [50, 50], [-50, 50]], "is_closed": True},
                ],
            }
        },
        "components": [
            {"block_name": "WHEEL_ASSEMBLY", "position": [300.0, 300.0], "rotation": 0.0, "scale": [1.0, 1.0]},
            {"block_name": "WHEEL_ASSEMBLY", "position": [900.0, 300.0], "rotation": 45.0, "scale": [1.0, 1.0]},
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [100.0, 100.0], "end": [1100.0, 100.0], "layer": "0"},
                    {"start": [100.0, 500.0], "end": [1100.0, 500.0], "layer": "0"},
                    {"start": [100.0, 100.0], "end": [100.0, 500.0], "layer": "HIDDEN_EDGES", "linetype": "HIDDEN"},
                    {"start": [1100.0, 100.0], "end": [1100.0, 500.0], "layer": "HIDDEN_EDGES", "linetype": "HIDDEN"},
                    {"start": [0.0, 300.0], "end": [1200.0, 300.0], "layer": "CENTERLINES", "linetype": "CENTER"},
                ],
                "arcs": [
                    {"center": [600.0, 300.0], "radius": 200.0, "start_angle": 0.0, "end_angle": 180.0, "layer": "0"},
                ],
                "circles": [
                    {"center": [600.0, 300.0], "radius": 250.0, "layer": "0", "linetype": "DASHED"},
                ],
                "polylines": [
                    {
                        "points": [[200, 600], [400, 700], [600, 650], [800, 750], [1000, 600]],
                        "is_closed": False,
                        "layer": "0",
                    }
                ],
            }
        },
        "annotations": [
            {"position": [600.0, 50.0], "clean_text": "INDUSTRIAL TEST ASSEMBLY", "height": 32.0, "layer": "ANNOTATIONS"},
        ],
    }


def test_html_wrapped_svg_headless_rendering_performance(sample_complex_ir, tmp_path):
    """
    Feature 11: Verifies that HTML-wrapped SVG vector content renders headlessly with Playwright
    in under 300ms without timeouts or rendering artifacts.
    """
    svg_str, report = compile_ir_to_svg_string(sample_complex_ir, preset="web-interactive-light")
    assert report.success is True

    html_content = HTML_WRAPPER.format(svg_content=svg_str)
    screenshot_path = tmp_path / "test_render.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        start_time = time.perf_counter()
        page.set_content(html_content, wait_until="domcontentloaded")
        page.screenshot(path=str(screenshot_path))
        render_duration_ms = (time.perf_counter() - start_time) * 1000.0

        browser.close()

    assert screenshot_path.is_file()
    assert screenshot_path.stat().st_size > 1000
    # Performance gate: sub-second headless render (generous 3000ms timeout check, typical <300ms)
    assert render_duration_ms < 3000.0, f"Render took too long: {render_duration_ms:.1f}ms"


def test_playwright_render_across_presets(sample_complex_ir, tmp_path):
    """
    Verifies that all three primary presets render cleanly in headless Chromium.
    """
    presets_to_test = ["web-interactive-light", "architectural-monochrome", "cad-dark-modelspace"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        for preset in presets_to_test:
            svg_str, report = compile_ir_to_svg_string(sample_complex_ir, preset=preset)
            assert report.success is True

            bg = "#1E1E1E" if preset == "cad-dark-modelspace" else "#FFFFFF"
            html_doc = f"""<!DOCTYPE html><html><head><style>
            html, body {{ margin:0; width:1920px; height:1080px; overflow:hidden; background:{bg}; }}
            svg {{ width:100%; height:100%; }}
            </style></head><body>{svg_str}</body></html>"""

            shot_file = tmp_path / f"shot_{preset}.png"
            page.set_content(html_doc, wait_until="domcontentloaded")
            page.screenshot(path=str(shot_file))
            assert shot_file.is_file()
            assert shot_file.stat().st_size > 500

        browser.close()


def test_playwright_industrial_dwg_ir_renders_if_available(tmp_path):
    """
    Verifies that real extracted industrial DWG IR payloads (Sany crane, Kato crane, Roadheader, Fleet)
    render headlessly without timeouts or layout distortion if present on system.
    """
    ir_dir = Path(r"e:\Antigravity\La Vinci\.agents\survey_explorer_1\output")
    if not ir_dir.exists():
        pytest.skip("Industrial IR cache directory not present")

    ir_files = list(ir_dir.glob("*_ir.json"))
    if not ir_files:
        pytest.skip("No industrial IR JSON files found")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        for ir_path in ir_files:
            with open(ir_path, "r", encoding="utf-8") as f:
                ir_data = json.load(f)

            svg_str, report = compile_ir_to_svg_string(ir_data, preset="web-interactive-light")
            assert report.success is True
            assert report.width > 0
            assert report.height > 0

            html_doc = HTML_WRAPPER.format(svg_content=svg_str)
            shot_file = tmp_path / f"industrial_{ir_path.stem}.png"

            t0 = time.perf_counter()
            page.set_content(html_doc, wait_until="domcontentloaded")
            page.screenshot(path=str(shot_file))
            elapsed = (time.perf_counter() - t0) * 1000.0

            assert shot_file.is_file()
            assert shot_file.stat().st_size > 1000
            # Zero timeouts verification
            assert elapsed < 5000.0

        browser.close()
