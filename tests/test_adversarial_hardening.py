"""
Adversarial hardening, corruption resilience, and boundary condition tests for cad-ir-to-svg.
"""

import xml.etree.ElementTree as ET
import pytest

from cad_ir_to_svg.compiler import compile_ir_to_svg_string
from cad_ir_to_svg.telemetry import HardeningWarning


def test_adversarial_empty_payload():
    # Empty dictionary must compile to a valid blank SVG without crashing
    svg_str, report = compile_ir_to_svg_string({})
    assert report.success is True
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")
    assert "viewBox" in root.attrib


def test_adversarial_null_sections():
    # Malformed payload with null primary keys
    corrupt_ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": None,
        "layers": None,
        "geometry_primitives": None,
        "components": None,
        "annotations": None,
        "dimensions": None,
        "block_definitions": None,
    }
    svg_str, report = compile_ir_to_svg_string(corrupt_ir)
    assert report.success is True
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")


def test_adversarial_nan_and_inf_coordinates():
    # Payload with NaN, Inf, and invalid point formats
    corrupt_ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [float("nan"), 10.0], "end": [20.0, 30.0]},
                    {"start": [10.0, 20.0], "end": [float("inf"), 30.0]},
                    {"start": "invalid", "end": [10, 20]},
                    {"start": [0, 0], "end": [100, 100]},  # valid line
                ],
                "circles": [
                    {"center": [float("nan"), 0.0], "radius": 10.0},
                    {"center": [0.0, 0.0], "radius": float("inf")},
                    {"center": [0.0, 0.0], "radius": -5.0},  # negative radius
                    {"center": [50.0, 50.0], "radius": 10.0},  # valid circle
                ],
                "arcs": [
                    {"center": [0, 0], "radius": 0.0, "start_angle": 0, "end_angle": 90},  # zero radius
                    {"center": [10, 10], "radius": 5.0, "start_angle": 45, "end_angle": 45},  # 0 sweep
                ]
            }
        }
    }

    warnings = []
    svg_str, report = compile_ir_to_svg_string(corrupt_ir, warning_collector=warnings)
    assert report.success is True
    assert report.total_entities_rendered >= 2  # 1 valid line + 1 valid circle
    assert report.total_entities_dropped >= 3

    # Ensure output XML is valid and contains zero NaNs
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")


def test_adversarial_singular_block_transforms():
    # Component with zero scale (singular matrix)
    singular_ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "TEST": {
                "lines": [{"start": [0, 0], "end": [10, 10]}]
            }
        },
        "components": [
            {"block_name": "TEST", "position": [10, 20], "scale": [0.0, 1.0]},  # det = 0
            {"block_name": "TEST", "position": [10, 20], "scale": [float("nan"), 1.0]},  # nan scale
        ],
        "geometry_primitives": {"primitives": {"lines": []}}
    }
    warnings = []
    svg_str, report = compile_ir_to_svg_string(singular_ir, warning_collector=warnings)
    assert report.success is True
    # Singular components must be safely dropped without crashing
    assert report.total_entities_dropped >= 2


def test_zero_length_line_dropping():
    ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [10.0, 20.0], "end": [10.0, 20.0]},  # length 0
                    {"start": [0.0, 0.0], "end": [100.0, 100.0]},  # valid
                ]
            }
        }
    }
    svg_str, report = compile_ir_to_svg_string(ir)
    assert report.total_entities_rendered == 1
    assert report.total_entities_dropped == 1
