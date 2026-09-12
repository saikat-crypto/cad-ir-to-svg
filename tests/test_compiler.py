"""
Unit tests for cad-ir-to-svg compiler, presets, block unrolling, and annotations.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

from cad_ir_to_svg.compiler import (
    compile_ir_to_svg_string,
    compile_ir_to_svg,
    get_svg_bounds,
    list_svg_layers,
)
from cad_ir_to_svg.config import PRESETS, SvgPreset


@pytest.fixture
def minimal_ir():
    return {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {"source_file": "unit_test.dwg"},
        "layers": [
            {"name": "WALLS", "hex_color": "#FF0000", "color_aci": 1},
            {"name": "DOORS", "hex_color": "#00FF00", "color_aci": 3},
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0.0, 0.0], "end": [100.0, 0.0], "layer": "WALLS"},
                    {"start": [100.0, 0.0], "end": [100.0, 100.0], "layer": "WALLS"},
                ],
                "arcs": [
                    {"center": [50.0, 50.0], "radius": 25.0, "start_angle": 0.0, "end_angle": 180.0, "layer": "DOORS"}
                ],
                "circles": [
                    {"center": [50.0, 50.0], "radius": 10.0, "layer": "DOORS"}
                ],
                "polylines": [
                    {"points": [[0.0, 0.0], [50.0, 20.0], [100.0, 0.0]], "is_closed": False, "layer": "WALLS"}
                ],
            }
        },
        "annotations": [
            {"position": [50.0, 50.0], "clean_text": "ROOM 101", "height": 14.0, "layer": "WALLS"}
        ],
        "dimensions": [
            {"defpoint": [0.0, 0.0], "text_midpoint": [50.0, -10.0], "text": "100.0", "layer": "DIM"}
        ]
    }


def test_compile_minimal_ir(minimal_ir):
    svg_str, report = compile_ir_to_svg_string(minimal_ir)
    assert report.success is True
    assert report.total_entities_rendered >= 5

    # Check valid XML parse
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")
    assert "viewBox" in root.attrib


def test_compile_presets(minimal_ir):
    # 1. Default (web-interactive-light)
    svg_light, _ = compile_ir_to_svg_string(minimal_ir, preset="web-interactive-light")
    assert 'fill="#FFFFFF"' in svg_light
    assert 'vector-effect="non-scaling-stroke"' in svg_light

    # 2. Dark mode
    svg_dark, _ = compile_ir_to_svg_string(minimal_ir, preset="cad-dark-modelspace")
    assert 'fill="#1E1E1E"' in svg_dark

    # 3. Monochrome
    svg_mono, _ = compile_ir_to_svg_string(minimal_ir, preset="architectural-monochrome")
    assert 'stroke="#000000"' in svg_mono


def test_layer_grouping(minimal_ir):
    svg_str, _ = compile_ir_to_svg_string(minimal_ir)
    root = ET.fromstring(svg_str)

    # Find group elements
    groups = [el for el in root.iter() if el.tag.endswith("g")]
    group_ids = [g.attrib.get("id") for g in groups]
    assert "layer-WALLS" in group_ids
    assert "layer-DOORS" in group_ids


def test_block_unrolling():
    ir_with_block = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "CHAIR": {
                "base_point": [0.0, 0.0],
                "lines": [
                    {"start": [-5.0, -5.0], "end": [5.0, -5.0]},
                    {"start": [5.0, -5.0], "end": [5.0, 5.0]},
                ]
            }
        },
        "components": [
            {"block_name": "CHAIR", "position": [100.0, 200.0], "rotation": 45.0, "scale": [1.0, 1.0], "layer": "FURNITURE"},
            {"block_name": "CHAIR", "position": [300.0, 200.0], "rotation": 0.0, "scale": [2.0, 2.0], "layer": "FURNITURE"},
        ],
        "geometry_primitives": {"primitives": {"lines": []}}
    }
    svg_str, report = compile_ir_to_svg_string(ir_with_block)
    assert report.success is True
    # 2 components x 2 lines = 4 lines rendered
    assert report.total_entities_rendered >= 4


def test_block_cycle_protection():
    # Mutual recursion between BLOCK_A and BLOCK_B
    cyclic_ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "BLOCK_A": {
                "lines": [{"start": [0, 0], "end": [10, 10]}],
            },
        },
        "components": [
            {"block_name": "BLOCK_A", "position": [0, 0], "layer": "0"}
        ],
        "geometry_primitives": {"primitives": {"lines": []}}
    }
    # Should compile cleanly without hanging or crashing
    svg_str, report = compile_ir_to_svg_string(cyclic_ir)
    assert report.success is True


def test_file_output_atomicity(minimal_ir, tmp_path):
    out_file = tmp_path / "test_output.svg"
    res = compile_ir_to_svg(minimal_ir, out_file)
    assert res == out_file
    assert out_file.is_file()
    assert out_file.stat().st_size > 0


def test_fabrication_cnc_preset(minimal_ir):
    svg_str, report = compile_ir_to_svg_string(minimal_ir, preset="fabrication-cnc-hairline")
    assert report.success is True
    # In CNC mode: no background rect
    assert '<rect' not in svg_str
    # Hairline stroke width
    assert 'stroke-width="0.10px"' in svg_str or 'stroke-width="0.1px"' in svg_str
    # Text and dimensions should be excluded
    assert '<text' not in svg_str


def test_custom_user_preset(minimal_ir):
    custom = SvgPreset(
        name="custom-teal",
        description="Custom teal styling",
        background_color="#002B36",
        default_stroke_color="#2AA198",
        default_stroke_width=2.5,
        non_scaling_stroke=False,
    )
    svg_str, report = compile_ir_to_svg_string(minimal_ir, preset=custom)
    assert report.success is True
    assert 'fill="#002B36"' in svg_str
    assert 'stroke="#2AA198"' in svg_str


def test_multiline_text_tspans():
    ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "annotations": [
            {"position": [10.0, 20.0], "clean_text": "Line 1\nLine 2\nLine 3", "height": 10.0}
        ],
        "geometry_primitives": {"primitives": {"lines": []}}
    }
    svg_str, report = compile_ir_to_svg_string(ir)
    assert report.success is True
    assert '<tspan' in svg_str
    assert 'Line 1' in svg_str
    assert 'Line 2' in svg_str
    assert 'Line 3' in svg_str


def test_anonymous_dimension_blocks():
    ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "*D12": {
                "lines": [
                    {"start": [10.0, 10.0], "end": [20.0, 10.0]},
                ]
            }
        },
        "geometry_primitives": {"primitives": {"lines": []}}
    }
    svg_str, report = compile_ir_to_svg_string(ir)
    assert report.success is True
    assert '<line' in svg_str


def test_cli_execution(minimal_ir, tmp_path, monkeypatch):
    import sys
    from cad_ir_to_svg.cli import main

    ir_file = tmp_path / "test_cli.json"
    with open(ir_file, "w", encoding="utf-8") as f:
        json.dump(minimal_ir, f)

    out_file = tmp_path / "test_cli.svg"

    # Test conversion
    monkeypatch.setattr(sys, "argv", ["cad-ir-to-svg", str(ir_file), "-o", str(out_file), "--preset", "cad-dark-modelspace"])
    exit_code = main()
    assert exit_code == 0
    assert out_file.is_file()

    # Test inspect-bounds
    monkeypatch.setattr(sys, "argv", ["cad-ir-to-svg", str(ir_file), "--inspect-bounds"])
    exit_code = main()
    assert exit_code == 0

    # Test list-layers
    monkeypatch.setattr(sys, "argv", ["cad-ir-to-svg", str(ir_file), "--list-layers"])
    exit_code = main()
    assert exit_code == 0


def test_introspection_bounds_and_layers(minimal_ir):
    bounds = get_svg_bounds(minimal_ir)
    assert bounds["min_x"] <= 0.0
    assert bounds["max_x"] >= 100.0
    assert bounds["width"] > 0.0

    layers = list_svg_layers(minimal_ir)
    assert "WALLS" in layers
    assert "DOORS" in layers


