"""
High-Performance W3C-Compliant SVG Writer for cad-ir-to-svg.
Generates clean, responsive SVG DOM with layer grouping, non-scaling stroke vectors,
proper XML character escaping, and multi-line CAD text formatting.
"""

import html
import re
from typing import List, Dict, Optional, Tuple, Any
from .config import SvgPreset
from .geometry import BoundingBox


def sanitize_cad_text(text: str) -> str:
    r"""
    Strips raw AutoCAD MTEXT formatting tags (\f..., \P, \C..., \H..., %%u, %%d, etc.)
    and replaces CAD special character escape codes.
    """
    if not text:
        return ""

    # Replace known CAD escape codes
    text = text.replace("%%d", "°").replace("%%D", "°")
    text = text.replace("%%p", "±").replace("%%P", "±")
    text = text.replace("%%c", "Ø").replace("%%C", "Ø")
    text = text.replace("%%u", "").replace("%%U", "")
    text = text.replace("%%o", "").replace("%%O", "")

    # Strip MTEXT formatting tags (\f...; \H...; \C...; \A...; \W...; \Q...; \T...; \S...;)
    text = re.sub(r"\\[HhFfCcAaWwQqTtSs][^;]*;", "", text)
    # Strip style mode toggles (\L, \l, \O, \o, \K, \k)
    text = re.sub(r"\\[LloOkK]", "", text)
    # Replace paragraph breaks \P with newline
    text = re.sub(r"\\[Pp]", "\n", text)
    # Replace non-breaking space \~ with regular space
    text = re.sub(r"\\~", " ", text)
    # Remove curly braces grouping
    text = re.sub(r"[{}]", "", text)

    # Sanitize any unpaired UTF-16 surrogates
    try:
        text = text.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
    except Exception:
        text = "".join(c for c in text if not (0xD800 <= ord(c) <= 0xDFFF))

    return text.strip()


def sanitize_id(name: str) -> str:
    """Sanitizes layer or block names into valid XML/HTML ID attributes."""
    if not name:
        return "unnamed"
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    if clean and clean[0].isdigit():
        clean = "id_" + clean
    return clean or "layer"


class SvgWriter:
    """
    Stateful SVG builder assembling XML elements into a structured document.
    """
    def __init__(self, bbox: BoundingBox, preset: SvgPreset):
        self.bbox = bbox
        self.preset = preset
        self.layer_elements: Dict[str, List[str]] = {}
        self.layer_attributes: Dict[str, Dict[str, str]] = {}
        self.root_elements: List[str] = []

    def register_layer(self, layer_name: str, color: Optional[str] = None) -> None:
        """Registers a layer with its default color styling."""
        if layer_name not in self.layer_elements:
            self.layer_elements[layer_name] = []

        stroke_color = self.preset.default_stroke_color
        if self.preset.color_mode != "monochrome" and color and color.startswith("#"):
            stroke_color = color

        self.layer_attributes[layer_name] = {
            "stroke": stroke_color,
            "stroke-width": f"{self.preset.default_stroke_width}px",
        }

    def _get_target_layer_list(self, layer: Optional[str]) -> List[str]:
        target_layer = layer or "0"
        if target_layer not in self.layer_elements:
            self.register_layer(target_layer)
        return self.layer_elements[target_layer]

    def add_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        layer: Optional[str] = None,
        color: Optional[str] = None,
        stroke_width: Optional[float] = None,
    ) -> None:
        """Appends an SVG <line> element."""
        target = self._get_target_layer_list(layer)
        attrs = [
            f'x1="{x1:.3f}"',
            f'y1="{y1:.3f}"',
            f'x2="{x2:.3f}"',
            f'y2="{y2:.3f}"',
        ]

        if color and self.preset.color_mode != "monochrome":
            attrs.append(f'stroke="{color}"')
        if stroke_width is not None and abs(stroke_width - self.preset.default_stroke_width) > 1e-4:
            attrs.append(f'stroke-width="{stroke_width:.2f}px"')
        if self.preset.non_scaling_stroke:
            attrs.append('vector-effect="non-scaling-stroke"')

        target.append(f'  <line {" ".join(attrs)} />')

    def add_circle(
        self,
        cx: float,
        cy: float,
        r: float,
        layer: Optional[str] = None,
        color: Optional[str] = None,
        fill: Optional[str] = None,
    ) -> None:
        """Appends an SVG <circle> element."""
        target = self._get_target_layer_list(layer)
        attrs = [
            f'cx="{cx:.3f}"',
            f'cy="{cy:.3f}"',
            f'r="{r:.3f}"',
            f'fill="{fill or "none"}"',
        ]

        if color and self.preset.color_mode != "monochrome":
            attrs.append(f'stroke="{color}"')
        if self.preset.non_scaling_stroke:
            attrs.append('vector-effect="non-scaling-stroke"')

        target.append(f'  <circle {" ".join(attrs)} />')

    def add_path(
        self,
        d: str,
        layer: Optional[str] = None,
        color: Optional[str] = None,
        fill: Optional[str] = None,
        stroke_width: Optional[float] = None,
    ) -> None:
        """Appends an SVG <path> element (for arcs, polylines, and complex contours)."""
        if not d:
            return
        target = self._get_target_layer_list(layer)
        attrs = [
            f'd="{d}"',
            f'fill="{fill or "none"}"',
        ]

        if color and self.preset.color_mode != "monochrome":
            attrs.append(f'stroke="{color}"')
        if stroke_width is not None and abs(stroke_width - self.preset.default_stroke_width) > 1e-4:
            attrs.append(f'stroke-width="{stroke_width:.2f}px"')
        if self.preset.non_scaling_stroke:
            attrs.append('vector-effect="non-scaling-stroke"')

        target.append(f'  <path {" ".join(attrs)} />')

    def add_polyline(
        self,
        points: List[Tuple[float, float]],
        is_closed: bool = False,
        layer: Optional[str] = None,
        color: Optional[str] = None,
        fill: Optional[str] = None,
    ) -> None:
        """Appends an SVG <polyline> or <polygon> element."""
        if not points or len(points) < 2:
            return

        tag = "polygon" if is_closed else "polyline"
        pts_str = " ".join(f"{px:.3f},{py:.3f}" for px, py in points)
        target = self._get_target_layer_list(layer)

        attrs = [
            f'points="{pts_str}"',
            f'fill="{fill or "none"}"',
        ]

        if color and self.preset.color_mode != "monochrome":
            attrs.append(f'stroke="{color}"')
        if self.preset.non_scaling_stroke:
            attrs.append('vector-effect="non-scaling-stroke"')

        target.append(f'  <{tag} {" ".join(attrs)} />')

    def add_text(
        self,
        x: float,
        y: float,
        text: str,
        height: float = 12.0,
        layer: Optional[str] = None,
        color: Optional[str] = None,
        rotation: float = 0.0,
    ) -> None:
        """Appends an SVG <text> element with proper XML escaping and multi-line support."""
        clean = sanitize_cad_text(text)
        if not clean:
            return

        target = self._get_target_layer_list(layer)
        fill_color = self.preset.default_stroke_color
        if color and self.preset.color_mode != "monochrome":
            fill_color = color

        lines = clean.split("\n")
        safe_h = max(1.0, height)

        transform_attr = ""
        if abs(rotation) > 1e-4:
            # Note: in SVG (+Y down), standard CAD counter-clockwise rotation becomes -rotation
            transform_attr = f' transform="rotate({-rotation:.2f} {x:.3f} {y:.3f})"'

        attrs = [
            f'x="{x:.3f}"',
            f'y="{y:.3f}"',
            f'font-size="{safe_h:.2f}px"',
            f'fill="{fill_color}"',
            'stroke="none"',
            'class="cad-text"',
        ]
        if transform_attr:
            attrs.append(transform_attr.strip())

        if len(lines) == 1:
            escaped = html.escape(lines[0])
            target.append(f'  <text {" ".join(attrs)}>{escaped}</text>')
        else:
            tspan_elements = []
            for idx, line in enumerate(lines):
                escaped = html.escape(line)
                dy = f'{safe_h * 1.2:.2f}px' if idx > 0 else '0'
                tspan_elements.append(f'    <tspan x="{x:.3f}" dy="{dy}">{escaped}</tspan>')
            target.append(f'  <text {" ".join(attrs)}>\n' + "\n".join(tspan_elements) + '\n  </text>')

    def build_svg(self) -> str:
        """Assembles the complete W3C SVG XML document."""
        w = self.bbox.width
        h = self.bbox.height
        min_x = self.bbox.min_x
        min_y = self.bbox.min_y

        out = []
        out.append('<?xml version="1.0" encoding="UTF-8"?>')
        out.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{min_x:.3f} {min_y:.3f} {w:.3f} {h:.3f}" '
            f'width="100%" height="100%" '
            f'version="1.1">'
        )

        # Embedded Stylesheet
        out.append('  <style>')
        out.append('    .cad-layer { fill: none; stroke-linecap: round; stroke-linejoin: round; }')
        out.append('    .cad-text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; dominant-baseline: auto; }')
        out.append('  </style>')

        # Background Rect (if configured)
        if self.preset.background_color:
            out.append(
                f'  <rect x="{min_x:.3f}" y="{min_y:.3f}" width="{w:.3f}" height="{h:.3f}" '
                f'fill="{self.preset.background_color}" stroke="none" />'
            )

        # Render Layer Groups or Root Container
        if not self.preset.group_by_layer:
            root_attrs = [
                'class="cad-root"',
                f'stroke="{self.preset.default_stroke_color}"',
                f'stroke-width="{self.preset.default_stroke_width}px"',
            ]
            if self.preset.non_scaling_stroke:
                root_attrs.append('vector-effect="non-scaling-stroke"')
            out.append(f'  <g {" ".join(root_attrs)}>')
            for layer_name, elements in self.layer_elements.items():
                out.extend(elements)
            out.append('  </g>')
        else:
            for layer_name, elements in self.layer_elements.items():
                if not elements:
                    continue

                sanitized_id = sanitize_id(layer_name)
                layer_meta = self.layer_attributes.get(layer_name, {})
                stroke = layer_meta.get("stroke", self.preset.default_stroke_color)
                stroke_w = layer_meta.get("stroke-width", f"{self.preset.default_stroke_width}px")

                group_attrs = [
                    f'id="layer-{sanitized_id}"',
                    'class="cad-layer"',
                    f'data-layer-name="{html.escape(layer_name)}"',
                    f'stroke="{stroke}"',
                    f'stroke-width="{stroke_w}"',
                ]
                if self.preset.non_scaling_stroke:
                    group_attrs.append('vector-effect="non-scaling-stroke"')

                out.append(f'  <g {" ".join(group_attrs)}>')
                out.extend(elements)
                out.append('  </g>')

        out.append('</svg>\n')
        return "\n".join(out)
