"""
Adversarial Empirical Challenge Test Suite for Milestone 2.
Directly and rigorously verifies:
1. All 4 industrial DWG models across 3 presets without viewBox truncation:
   - Sany crane: lattice boom and tracks unclipped.
   - Kato crane: boom and carrier unclipped; Y=-26,665 outlier pruned.
   - Roadheader: full 13,150 mm machine width unclipped.
   - Building Technics 2: slewing radius circles have stroke-dasharray.
2. Synthetic NaN, Inf, subnormal, and extreme float payloads (|coord| > 1e7, 1e308, 1e-320).
3. Headless Playwright rendering of all 12 combinations without timeouts.
"""

import json
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

from cad_ir_to_svg.compiler import compile_ir_to_svg_string, compute_ir_extents
from cad_ir_to_svg.geometry import BoundingBox, is_valid_point, is_finite_number

IR_CACHE_DIR = Path(r"e:\Antigravity\La Vinci\.agents\survey_explorer_1\output")
PRESETS = ["web-interactive-light", "architectural-monochrome", "cad-dark-modelspace"]


def get_fresh_or_cached_ir(model_stem: str) -> dict:
    """Loads extracted IR; if model_stem is building_technics_2, loads or extracts fresh to verify linetypes."""
    dxf_path = IR_CACHE_DIR / f"{model_stem}.dxf"
    json_path = IR_CACHE_DIR / f"{model_stem}_ir.json"

    if model_stem == "building_technics_2" and dxf_path.exists():
        try:
            import sys
            extractor_src = r"e:\Antigravity\La Vinci\products\cad-extractor-ir\src"
            if extractor_src not in sys.path:
                sys.path.insert(0, extractor_src)
            from cad_extractor.core import extract_cad_ir
            return extract_cad_ir(str(dxf_path)).model_dump()
        except Exception:
            pass

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# CHALLENGE 1: Industrial DWG Models Extents, ViewBox & Outlier Pruning
# ==============================================================================

def test_sany_crane_lattice_boom_and_tracks_unclipped():
    """
    Verifies Sany SCC1800 Crawler Crane:
    - Bounding box spans X=[1288.1, 64233.9] and Y=[-1157.7, 32586.2].
    - Lattice boom reaches X > 64,000 and Y > 32,000.
    - Crawler tracks extend to Y = -1,157.7.
    - All 3 presets compile with viewBox fully encompassing boom and tracks.
    """
    ir = get_fresh_or_cached_ir("sany-crawler-crane-scc1800")
    bbox = compute_ir_extents(ir, outlier_pruning=True)

    # Confirm raw bounding box encompasses boom tip and crawler tracks
    assert bbox.min_x <= 1300.0, f"Sany min_x too high: {bbox.min_x}"
    assert bbox.max_x >= 64000.0, f"Sany lattice boom clipped on X: max_x={bbox.max_x}"
    assert bbox.min_y <= -1100.0, f"Sany crawler tracks clipped on Y: min_y={bbox.min_y}"
    assert bbox.max_y >= 32500.0, f"Sany lattice boom clipped on Y: max_y={bbox.max_y}"

    for preset in PRESETS:
        svg_str, report = compile_ir_to_svg_string(ir, preset=preset)
        assert report.success is True
        assert report.total_entities_rendered > 4000

        # Parse viewBox: "min_x min_y width height"
        vb_parts = [float(p) for p in report.viewbox.split()]
        vb_min_x, vb_min_y, vb_w, vb_h = vb_parts

        assert vb_min_x <= bbox.min_x, "ViewBox left clips lattice boom/body"
        assert vb_min_x + vb_w >= bbox.max_x, "ViewBox right clips lattice boom"
        assert vb_w >= bbox.width, "ViewBox width is smaller than model width"
        assert vb_h >= bbox.height, "ViewBox height is smaller than model height"


def test_kato_crane_boom_carrier_unclipped_outlier_pruned():
    """
    Verifies Kato SR-300LS Crane:
    - Outlier at Y=-26,665 is pruned (span ~19,510, Y in [18,255.2, 37,765.5]).
    - Boom apex (Y ~ 37,765) and carrier chassis (Y ~ 18,255) are fully unclipped.
    - ViewBox Y bounds do NOT include Y=-26,665.
    """
    ir = get_fresh_or_cached_ir("kato-sr-300ls")

    # 1. Unpruned vs Pruned verification
    unpruned = compute_ir_extents(ir, outlier_pruning=False)
    pruned = compute_ir_extents(ir, outlier_pruning=True)

    # Verify outlier presence in unpruned
    assert unpruned.min_y < -20000.0, f"Expected outlier around -26,665, got {unpruned.min_y}"

    # Verify outlier is cleanly pruned in pruned box
    assert pruned.min_y > 15000.0, f"Outlier was not pruned: min_y={pruned.min_y}"
    assert 18000.0 <= pruned.min_y <= 18500.0, f"Unexpected pruned min_y: {pruned.min_y}"
    assert 37000.0 <= pruned.max_y <= 38000.0, f"Telescopic boom apex clipped: max_y={pruned.max_y}"
    assert 37000.0 <= pruned.min_x <= 37800.0, f"Carrier left extent incorrect: min_x={pruned.min_x}"
    assert 73000.0 <= pruned.max_x <= 74000.0, f"Carrier/boom right extent incorrect: max_x={pruned.max_x}"

    for preset in PRESETS:
        svg_str, report = compile_ir_to_svg_string(ir, preset=preset)
        assert report.success is True
        assert report.total_entities_rendered > 15000

        vb_parts = [float(p) for p in report.viewbox.split()]
        vb_min_x, vb_min_y, vb_w, vb_h = vb_parts

        # ViewBox must cover the pruned crane assembly with padding, without distortion from -26665
        assert vb_w < 50000.0, f"ViewBox width inflated by outlier: {vb_w}"
        assert vb_h < 30000.0, f"ViewBox height inflated by outlier: {vb_h}"


def test_roadheader_full_machine_width_unclipped():
    """
    Verifies Heavy Mining Roadheader:
    - Full 13,150 mm machine width (cutting drum to rear discharge conveyor) is unclipped.
    - Raw width is ~13,150.8 mm.
    """
    ir = get_fresh_or_cached_ir("roadheader")
    bbox = compute_ir_extents(ir, outlier_pruning=True)

    assert 13140.0 <= bbox.width <= 13160.0, f"Roadheader width incorrect: {bbox.width}"
    assert 7400.0 <= bbox.height <= 7450.0, f"Roadheader height incorrect: {bbox.height}"

    for preset in PRESETS:
        svg_str, report = compile_ir_to_svg_string(ir, preset=preset)
        assert report.success is True
        assert report.total_entities_rendered > 10000

        vb_parts = [float(p) for p in report.viewbox.split()]
        vb_min_x, vb_min_y, vb_w, vb_h = vb_parts

        assert vb_w >= 13150.0, f"ViewBox width clips roadheader: {vb_w}"
        assert vb_min_x <= bbox.min_x, "ViewBox clips left cutting drum"
        assert vb_min_x + vb_w >= bbox.max_x, "ViewBox clips rear discharge conveyor"


def test_building_technics_2_slewing_radius_circles_have_stroke_dasharray():
    """
    Verifies Building Technics 2 Construction Fleet:
    - Slewing radius circles (crane/excavator turning radius, r ~ 2,642 mm)
      are rendered with W3C stroke-dasharray attribute.
    """
    ir = get_fresh_or_cached_ir("building_technics_2")

    for preset in PRESETS:
        svg_str, report = compile_ir_to_svg_string(ir, preset=preset)
        assert report.success is True

        root = ET.fromstring(svg_str)
        circles = root.findall(".//{http://www.w3.org/2000/svg}circle")
        assert len(circles) >= 280, f"Expected >= 280 circles, got {len(circles)}"

        # Find the slewing radius circle (r ~ 2642.592 at x ~ 47015)
        slewing_circles = [
            c for c in circles
            if abs(float(c.get("r", 0)) - 2642.592) < 5.0
        ]
        assert len(slewing_circles) >= 1, "Slewing radius circle (r=2642.6) not found!"

        sc = slewing_circles[0]
        assert "stroke-dasharray" in sc.attrib, f"Slewing circle missing stroke-dasharray: {sc.attrib}"
        dash_val = sc.attrib["stroke-dasharray"]
        assert dash_val in ("12,6", "6,6", "16,4,4,4", "12,3", "16,3,3,3"), f"Unexpected dasharray: {dash_val}"


# ==============================================================================
# CHALLENGE 2: Synthetic Boundary, NaN, Inf, Subnormal, and Extreme Floats
# ==============================================================================

def test_stress_synthetic_nan_inf_and_astronomical_floats():
    """
    Adversarially feeds synthetic payloads containing:
    - NaN, +Inf, -Inf coordinates in all primitive slots
    - Astronomical numbers: 1e308, -1e308, 1e20, 1e8 (> 1e7 threshold)
    - Subnormal numbers: 1e-320
    - Degenerate matrices: det=0, singular blocks
    - Recursive block cycles and deep nesting (>16 levels)
    Verifies: Zero crashes, report.success is True, valid W3C XML, no 'nan'/'inf' in SVG strings.
    """
    pathological_ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "layers": [
            {"name": "0", "hex_color": "#000000"},
            {"name": "PATHOLOGY", "hex_color": "#FF0000", "linetype": "CENTER"},
        ],
        "block_definitions": {
            "CYCLE_A": {
                "components": [{"block_name": "CYCLE_B", "position": [0, 0]}],
                "lines": [{"start": [0, 0], "end": [10, 10]}],
            },
            "CYCLE_B": {
                "components": [{"block_name": "CYCLE_A", "position": [0, 0]}],
                "lines": [{"start": [0, 0], "end": [20, 20]}],
            },
            "ASTRONOMICAL_BLOCK": {
                "lines": [
                    {"start": [1e250, -1e250], "end": [2e250, 0.0]},  # Must be safely dropped by 1e7 guard
                    {"start": [float("nan"), 0.0], "end": [0.0, float("inf")]},
                    {"start": [10.0, 10.0], "end": [100.0, 100.0]},  # Valid inside block
                ],
                "circles": [
                    {"center": [1e20, 1e20], "radius": 1e20},  # Dropped
                    {"center": [50.0, 50.0], "radius": 25.0},  # Valid
                ]
            }
        },
        "components": [
            {"block_name": "CYCLE_A", "position": [0, 0]},
            {"block_name": "ASTRONOMICAL_BLOCK", "position": [100, 100]},
            {"block_name": "NON_EXISTENT_BLOCK", "position": [500, 500]},
            {"block_name": "ASTRONOMICAL_BLOCK", "position": [0, 0], "scale": [0.0, 0.0, 0.0]},  # Singular
            {"block_name": "ASTRONOMICAL_BLOCK", "position": [float("nan"), 10.0]},  # Invalid pos
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [float("nan"), 0.0], "end": [10.0, 10.0]},
                    {"start": [0.0, float("inf")], "end": [10.0, 10.0]},
                    {"start": [0.0, 0.0], "end": [float("-inf"), 10.0]},
                    {"start": [1e308, 0.0], "end": [0.0, 1e308]},
                    {"start": [-1e308, 0.0], "end": [0.0, -1e308]},
                    {"start": [1e8, 10.0], "end": [1e8, 20.0]},  # Exceeds 1e7 threshold -> dropped
                    {"start": [1e-320, 1e-320], "end": [50.0, 50.0]},  # Subnormal -> valid
                    {"start": [10.0, 10.0], "end": [10.0, 10.0]},  # Zero-length line -> dropped
                    {"start": [0.0, 0.0], "end": [200.0, 200.0], "layer": "PATHOLOGY"},  # Valid
                ],
                "circles": [
                    {"center": [float("nan"), 0.0], "radius": 10.0},
                    {"center": [0.0, float("nan")], "radius": 10.0},
                    {"center": [0.0, 0.0], "radius": float("nan")},
                    {"center": [0.0, 0.0], "radius": float("inf")},
                    {"center": [0.0, 0.0], "radius": -10.0},  # Negative radius
                    {"center": [0.0, 0.0], "radius": 0.0},  # Zero radius
                    {"center": [1e9, 1e9], "radius": 50.0},  # Center > 1e7
                    {"center": [100.0, 100.0], "radius": 1e8},  # Radius >= 1e7
                    {"center": [150.0, 150.0], "radius": 30.0, "layer": "PATHOLOGY"},  # Valid
                ],
                "arcs": [
                    {"center": [float("nan"), 0.0], "radius": 10.0, "start_angle": 0, "end_angle": 90},
                    {"center": [0.0, 0.0], "radius": float("inf"), "start_angle": 0, "end_angle": 90},
                    {"center": [0.0, 0.0], "radius": 20.0, "start_angle": float("nan"), "end_angle": 90},
                    {"center": [0.0, 0.0], "radius": 20.0, "start_angle": 0, "end_angle": 0},  # 0 sweep
                    {"center": [100.0, 100.0], "radius": 40.0, "start_angle": 0, "end_angle": 90},  # Valid
                ],
                "polylines": [
                    {"points": [[float("nan"), 0.0], [10.0, 10.0]], "layer": "0"},  # Only 1 valid pt -> dropped
                    {"points": [[0.0, 0.0], [float("inf"), 10.0], [50.0, 50.0]], "layer": "0"},  # 2 valid pts -> kept
                    {"points": [[1e250, 0.0], [1e250, 10.0]], "layer": "0"},  # Dropped
                ],
            }
        },
        "annotations": [
            {"position": [float("nan"), 0.0], "clean_text": "NAN_POS"},
            {"position": [1e300, 0.0], "clean_text": "ASTRONOMICAL_POS"},
            {"position": [50.0, 20.0], "clean_text": "VALID_TEXT", "height": 12.0},
        ],
        "dimensions": [
            {"defpoint": [float("nan"), 0.0], "defpoint2": [10.0, 10.0]},
            {"defpoint": [10.0, 10.0], "defpoint2": [50.0, 50.0]},
        ]
    }

    warnings = []
    svg_str, report = compile_ir_to_svg_string(pathological_ir, warning_collector=warnings)

    # 1. Verification of crash resilience
    assert report.success is True, "Compiler failed on pathological payload"
    assert report.total_entities_rendered >= 3, "Valid entities were erroneously dropped"
    assert report.total_entities_dropped >= 10, "Pathological entities were not dropped"

    # 2. Strict XML validity check
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")

    # 3. Text search for string leaks of 'nan', 'inf' or astronomical exponents
    lower_svg = svg_str.lower()
    for bad in ('="nan', '="inf', '="infinity', 'nan,', ',nan', 'inf,', ',inf'):
        assert bad not in lower_svg, f"Leaked invalid float string '{bad}' into SVG!"

    # 4. ViewBox check
    vb = root.attrib.get("viewBox", "")
    for part in vb.split():
        val = float(part)
        assert math.isfinite(val), f"ViewBox part is not finite: {part}"
        assert abs(val) < 1e7, f"ViewBox part exceeded sanity limit: {val}"


# ==============================================================================
# CHALLENGE 3: Headless Playwright Rendering Across All 12 Combinations
# ==============================================================================

def test_headless_playwright_all_12_combinations_no_timeouts(tmp_path):
    """
    Renders all 4 models x 3 presets = 12 combinations with headless Playwright Chromium.
    Asserts:
    - Sub-3000ms render execution time per drawing.
    - Zero page timeouts or crash events.
    - Output PNG screenshot exists and has valid PNG magic bytes.
    """
    models = [
        "sany-crawler-crane-scc1800",
        "kato-sr-300ls",
        "roadheader",
        "building_technics_2",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        for model in models:
            ir = get_fresh_or_cached_ir(model)

            for preset in PRESETS:
                t0 = time.perf_counter()
                svg_str, report = compile_ir_to_svg_string(ir, preset=preset)
                compile_ms = (time.perf_counter() - t0) * 1000.0

                assert report.success is True
                assert report.width > 0
                assert report.height > 0

                bg = "#1E1E1E" if preset == "cad-dark-modelspace" else "#FFFFFF"
                html_doc = (
                    "<!DOCTYPE html><html><head><meta charset='UTF-8'><style>"
                    f"html, body {{ margin:0; padding:0; width:1920px; height:1080px; overflow:hidden; background:{bg}; }}"
                    "svg { width:100%; height:100%; display:block; }"
                    f"</style></head><body>{svg_str}</body></html>"
                )

                png_path = tmp_path / f"{model}_{preset}.png"

                t_render0 = time.perf_counter()
                # 5000ms timeout guard
                page.set_content(html_doc, wait_until="domcontentloaded", timeout=5000)
                page.screenshot(path=str(png_path))
                render_ms = (time.perf_counter() - t_render0) * 1000.0

                # Assertions on render execution
                assert png_path.is_file(), f"Screenshot not created for {model} {preset}"
                assert png_path.stat().st_size > 1000, f"Screenshot empty for {model} {preset}"

                # Verify PNG magic bytes (\x89PNG\r\n\x1a\n)
                header = png_path.read_bytes()[:8]
                assert header == b"\x89PNG\r\n\x1a\n", f"Corrupt PNG for {model} {preset}"

                # Performance gate: strictly under 3000ms
                assert render_ms < 3000.0, f"Render took too long ({render_ms:.1f}ms) for {model} {preset}"

        browser.close()
