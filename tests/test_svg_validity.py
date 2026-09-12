"""
W3C SVG syntax and structural validity verification tests.
"""

import xml.etree.ElementTree as ET
import re
import pytest

from cad_ir_to_svg.compiler import compile_ir_to_svg_string


def test_w3c_xml_syntax_validity():
    ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "layers": [{"name": "0", "hex_color": "#000000"}],
        "geometry_primitives": {
            "primitives": {
                "lines": [{"start": [10.5, 20.3], "end": [30.2, 40.1], "layer": "0"}],
                "arcs": [{"center": [50.0, 50.0], "radius": 15.0, "start_angle": 30.0, "end_angle": 150.0}],
                "circles": [{"center": [100.0, 100.0], "radius": 25.0}],
                "polylines": [{"points": [[0, 0], [10, 0], [10, 10], [0, 10]], "is_closed": True}],
            }
        },
        "annotations": [
            {"position": [50.0, 60.0], "clean_text": "Room & Board <Special> \"Quotes\"", "height": 12.0}
        ],
    }

    svg_str, report = compile_ir_to_svg_string(ir)
    assert report.success is True

    # 1. Strict XML Parse
    root = ET.fromstring(svg_str)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg_str
    assert root.attrib.get("version") == "1.1"

    # 2. ViewBox validity
    vb = root.attrib.get("viewBox")
    assert vb is not None
    parts = [float(p) for p in vb.split()]
    assert len(parts) == 4
    # width and height must be strictly positive
    assert parts[2] > 0.0
    assert parts[3] > 0.0

    # 3. No NaN / Inf tokens in entire XML stream
    assert not re.search(r"\b(nan|inf|-inf)\b", svg_str, re.IGNORECASE)

    # 4. XML Character Escaping Verification
    assert "&amp;" in svg_str or "Room &amp; Board" in svg_str
    assert "&lt;Special&gt;" in svg_str


def test_cyrillic_and_unicode_text_preservation():
    ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "annotations": [
            {
                "position": [0.0, 0.0],
                "clean_text": "Экспликация помещений: Санузел №1 (Площадь: 12.5 м²)",
                "height": 14.0,
            }
        ],
        "geometry_primitives": {"primitives": {"lines": []}}
    }

    svg_str, _ = compile_ir_to_svg_string(ir)
    root = ET.fromstring(svg_str)
    # Check Cyrillic preserved in XML
    assert "Экспликация помещений" in svg_str
    assert "Санузел" in svg_str
    assert "м²" in svg_str
