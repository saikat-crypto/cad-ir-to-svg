"""
cad-ir-to-svg: High-Fidelity Vector CAD to SVG Compiler.
Part of the La Vinci CAD/BIM processing ecosystem.
"""

__version__ = "1.0.0"
__author__ = "Saikat Dutta Chowdhury"

from .config import SvgPreset, PRESETS, DEFAULT_PRESET
from .compiler import (
    compile_ir_to_svg,
    compile_ir_to_svg_string,
    get_svg_bounds,
    list_svg_layers,
    compute_ir_extents,
)
from .geometry import BoundingBox, AffineMatrix2D
from .telemetry import (
    CompilationReport,
    HardeningWarning,
    HardeningCategory,
    ActionTaken,
)

__all__ = [
    "compile_ir_to_svg",
    "compile_ir_to_svg_string",
    "get_svg_bounds",
    "list_svg_layers",
    "compute_ir_extents",
    "SvgPreset",
    "PRESETS",
    "DEFAULT_PRESET",
    "CompilationReport",
    "HardeningWarning",
    "HardeningCategory",
    "ActionTaken",
    "BoundingBox",
    "AffineMatrix2D",
]
