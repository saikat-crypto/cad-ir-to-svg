"""
Configuration presets and styling models for cad-ir-to-svg.
Follows the La Vinci Cloud API Invariant: fully parameterized, customizable, and serializable.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class SvgPreset:
    """
    Structured configuration preset for SVG compilation.
    Fully parameterized to support interactive web viewers, CAD dark mode,
    architectural monochrome, CNC fabrication, or user-defined custom styling.
    """
    name: str
    description: str
    background_color: Optional[str] = "#FFFFFF"      # None for transparent background
    default_stroke_color: str = "#1A1A1A"           # Fallback stroke color
    default_stroke_width: float = 1.0               # Base stroke width
    non_scaling_stroke: bool = True                 # Injects vector-effect="non-scaling-stroke"
    group_by_layer: bool = True                     # Emits <g id="layer-..." class="cad-layer">
    invert_y: bool = True                           # Maps CAD (+Y up) to SVG (+Y down)
    padding_ratio: float = 0.05                     # Margin padding fraction (0.05 = 5%)
    target_space: str = "Model"                     # "Model" or specific paper space layout
    include_dimensions: bool = True                 # Render linear and aligned dimensions
    include_annotations: bool = True                # Render TEXT and MTEXT annotations
    color_mode: str = "layer"                       # "layer" (layer hex/ACI), "monochrome", or "entity"
    outlier_pruning: bool = True                    # Gap-based coordinate clustering for scratch geometry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "background_color": self.background_color,
            "default_stroke_color": self.default_stroke_color,
            "default_stroke_width": self.default_stroke_width,
            "non_scaling_stroke": self.non_scaling_stroke,
            "group_by_layer": self.group_by_layer,
            "invert_y": self.invert_y,
            "padding_ratio": self.padding_ratio,
            "target_space": self.target_space,
            "include_dimensions": self.include_dimensions,
            "include_annotations": self.include_annotations,
            "color_mode": self.color_mode,
            "outlier_pruning": self.outlier_pruning,
        }


# Canonical Presets Registry
PRESETS: Dict[str, SvgPreset] = {
    "web-interactive-light": SvgPreset(
        name="web-interactive-light",
        description="Responsive light canvas with layer grouping, high-contrast linework, and non-scaling strokes for web viewers.",
        background_color="#FFFFFF",
        default_stroke_color="#1A1A1A",
        default_stroke_width=1.0,
        non_scaling_stroke=True,
        group_by_layer=True,
        invert_y=True,
        padding_ratio=0.05,
        color_mode="layer",
    ),
    "cad-dark-modelspace": SvgPreset(
        name="cad-dark-modelspace",
        description="Classic AutoCAD dark modelspace background (#1E1E1E) with vibrant ACI layer colors.",
        background_color="#1E1E1E",
        default_stroke_color="#E0E0E0",
        default_stroke_width=1.0,
        non_scaling_stroke=True,
        group_by_layer=True,
        invert_y=True,
        padding_ratio=0.05,
        color_mode="layer",
    ),
    "architectural-monochrome": SvgPreset(
        name="architectural-monochrome",
        description="Strict black-on-white architectural line weights for publication, documentation, and printing.",
        background_color="#FFFFFF",
        default_stroke_color="#000000",
        default_stroke_width=0.75,
        non_scaling_stroke=False,
        group_by_layer=True,
        invert_y=True,
        padding_ratio=0.05,
        color_mode="monochrome",
    ),
    "fabrication-cnc-hairline": SvgPreset(
        name="fabrication-cnc-hairline",
        description="Ultra-fine hairline geometry paths (no background, no text/dimensions) for laser cutters, plotters, and CNCs.",
        background_color=None,
        default_stroke_color="#FF0000",
        default_stroke_width=0.1,
        non_scaling_stroke=False,
        group_by_layer=False,
        invert_y=True,
        padding_ratio=0.02,
        include_dimensions=False,
        include_annotations=False,
        color_mode="monochrome",
    ),
}

DEFAULT_PRESET = PRESETS["web-interactive-light"]
