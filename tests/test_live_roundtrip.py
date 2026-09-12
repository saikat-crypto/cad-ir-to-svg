"""
Live end-to-end integration tests for cad-ir-to-svg compiling real-world CAD drawings.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

from cad_ir_to_svg.compiler import compile_ir_to_svg, compile_ir_to_svg_string

WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent.parent


def get_real_ir_fixtures():
    candidates = [
        WORKSPACE_DIR / "experiments" / "sample_ir.json",
        WORKSPACE_DIR / "products" / "cad-extractor-ir" / "examples" / "blueprint_sample_ir.json",
        WORKSPACE_DIR / "experiments" / "e2e_demo" / "toyota_c_hr_2017_ir.json",
        WORKSPACE_DIR / "experiments" / "e2e_demo" / "citroen_ir.json",
        WORKSPACE_DIR / "experiments" / "e2e_demo" / "mercedes_ir.json",
    ]
    return [p for p in candidates if p.is_file()]


def test_live_real_world_blueprint_compilation(tmp_path):
    fixtures = get_real_ir_fixtures()
    assert len(fixtures) >= 1, "At least one real-world CAD IR fixture must exist in the workspace"

    for fixture in fixtures:
        out_svg = tmp_path / f"{fixture.stem}.svg"
        result_path = compile_ir_to_svg(fixture, out_svg, preset="web-interactive-light")
        assert result_path.is_file()
        assert result_path.stat().st_size > 500  # Non-trivial size

        # Validate W3C XML parse
        tree = ET.parse(result_path)
        root = tree.getroot()
        assert root.tag.endswith("svg")
        assert "viewBox" in root.attrib
        vb = [float(x) for x in root.attrib["viewBox"].split()]
        assert len(vb) == 4
        assert vb[2] > 0.0  # width > 0
        assert vb[3] > 0.0  # height > 0

        # Verify layer groups exist
        groups = [e for e in root.iter() if e.tag.endswith("g") and "id" in e.attrib]
        assert len(groups) >= 1


def test_live_dark_and_monochrome_presets(tmp_path):
    sample = WORKSPACE_DIR / "experiments" / "sample_ir.json"
    if not sample.is_file():
        sample = WORKSPACE_DIR / "products" / "cad-extractor-ir" / "examples" / "blueprint_sample_ir.json"

    if sample.is_file():
        # Dark mode compilation
        dark_svg = tmp_path / "dark.svg"
        compile_ir_to_svg(sample, dark_svg, preset="cad-dark-modelspace")
        content_dark = dark_svg.read_text(encoding="utf-8")
        assert 'fill="#1E1E1E"' in content_dark

        # Monochrome compilation
        mono_svg = tmp_path / "mono.svg"
        compile_ir_to_svg(sample, mono_svg, preset="architectural-monochrome")
        content_mono = mono_svg.read_text(encoding="utf-8")
        assert 'stroke="#000000"' in content_mono
