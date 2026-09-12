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


def clean_hex(val: Any) -> Optional[str]:
    """Validates and normalizes hex strings into standard #RRGGBB format."""
    if not isinstance(val, str):
        return None
    s = val.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3 and re.fullmatch(r"[0-9a-fA-F]{3}", s):
        s = "".join(c * 2 for c in s)
    elif len(s) == 8 and re.fullmatch(r"[0-9a-fA-F]{8}", s):
        s = s[:6]
    if len(s) == 6 and re.fullmatch(r"[0-9a-fA-F]{6}", s):
        return "#" + s.upper()
    return None


def hex_luminance(hex_str: Optional[str]) -> float:
    """Computes standard Rec. 709 relative luminance for a normalized #RRGGBB hex color."""
    if not hex_str or not hex_str.startswith("#") or len(hex_str) != 7:
        return 0.0
    try:
        r = int(hex_str[1:3], 16) / 255.0
        g = int(hex_str[3:5], 16) / 255.0
        b = int(hex_str[5:7], 16) / 255.0
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except Exception:
        return 0.0


def resolve_contrast_color(
    color: Optional[str],
    bg_color: Optional[str],
    default_color: str = "#1A1A1A",
) -> str:
    """
    Ensures foreground stroke or text color remains clearly visible against the canvas background.
    - If background is light (or default white / transparent on light page, bg_lum >= 0.8):
      pure white (#FFFFFF) or near-white/light colors (lum > 0.85) are remapped to default_color (#1A1A1A).
    - If background is dark (bg_lum < 0.2):
      pure black (#000000) or near-black colors (lum < 0.1) are remapped to #FFFFFF.
    """
    clean_target = clean_hex(color)
    clean_default = clean_hex(default_color) or "#1A1A1A"

    if not clean_target:
        return clean_default

    clean_bg = clean_hex(bg_color)
    bg_lum = hex_luminance(clean_bg) if clean_bg else 1.0
    target_lum = hex_luminance(clean_target)

    if bg_lum >= 0.8:
        # Light canvas: prevent invisible white or low-contrast yellow/light strokes on white bg
        if clean_target in ("#FFFFFF", "#FFF") or target_lum > 0.85:
            return clean_default
    elif bg_lum < 0.2:
        # Dark canvas: prevent invisible dark strokes on dark bg
        if clean_target in ("#000000", "#000") or target_lum < 0.1:
            return "#FFFFFF"

    return clean_target


def map_cad_linetype_to_dasharray(linetype: Optional[str]) -> Optional[str]:
    """
    Maps standard CAD linetypes to SVG stroke-dasharray values.
    Supports DASHED, HIDDEN, CENTER, DOT, DASHDOT, PHANTOM, and ACAD_ISO patterns.
    """
    if not linetype or not isinstance(linetype, str):
        return None
    lt = linetype.strip().upper()
    if lt in ("", "CONTINUOUS", "SOLID", "BYLAYER", "BYBLOCK", "NONE"):
        return None

    # Exact matches and standard pattern mappings
    if lt == "DASHED" or lt.startswith("DASHED"):
        if "2" in lt and "X" not in lt:
            return "6,3"
        elif "X2" in lt:
            return "24,12"
        return "12,6"

    if lt == "HIDDEN" or lt.startswith("HIDDEN"):
        if "2" in lt and "X" not in lt:
            return "3,3"
        elif "X2" in lt:
            return "12,12"
        return "6,6"

    if lt == "CENTER" or lt.startswith("CENTER"):
        if "2" in lt and "X" not in lt:
            return "8,2,2,2"
        elif "X2" in lt:
            return "32,8,8,8"
        return "16,4,4,4"

    if "ISO02W100" in lt:  # ACAD_ISO02W100: ISO dash
        return "12,3"

    if "ISO04W100" in lt:  # ACAD_ISO04W100: ISO long dash dot
        return "16,3,3,3"

    if "ISO03W100" in lt:  # ACAD_ISO03W100
        return "12,3,3,3"

    if "ISO05W100" in lt:  # ACAD_ISO05W100
        return "16,3,3,3,3,3"

    if lt.startswith("DOT"):
        return "2,4"

    if lt.startswith("DASHDOT"):
        return "12,4,2,4"

    if lt.startswith("PHANTOM"):
        return "16,4,4,4,4,4"

    if lt.startswith("DIVIDE"):
        return "16,4,2,4,2,4"

    if lt.startswith("BORDER"):
        return "16,4,16,4,4,4"

    return None



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

    def register_layer(self, layer_name: str, color: Optional[str] = None, linetype: Optional[str] = None) -> None:
        """Registers a layer with its default color styling, linetype, and background-aware contrast safety."""
        if layer_name not in self.layer_elements:
            self.layer_elements[layer_name] = []

        stroke_color = self.preset.default_stroke_color
        if self.preset.color_mode != "monochrome" and color:
            clean_c = clean_hex(color)
            if clean_c:
                stroke_color = resolve_contrast_color(clean_c, self.preset.background_color, self.preset.default_stroke_color)

        attrs = {
            "stroke": stroke_color,
            "stroke-width": f"{self.preset.default_stroke_width}px",
        }
        if linetype:
            dash = map_cad_linetype_to_dasharray(linetype)
            if dash:
                attrs["stroke-dasharray"] = dash
        self.layer_attributes[layer_name] = attrs

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
        linetype: Optional[str] = None,
        stroke_dasharray: Optional[str] = None,
    ) -> None:
        """Appends an SVG <line> element with contrast safety and linetype dasharray."""
        target = self._get_target_layer_list(layer)
        attrs = [
            f'x1="{x1:.3f}"',
            f'y1="{y1:.3f}"',
            f'x2="{x2:.3f}"',
            f'y2="{y2:.3f}"',
        ]

        if color and self.preset.color_mode != "monochrome":
            clean_c = clean_hex(color)
            if clean_c:
                safe_color = resolve_contrast_color(clean_c, self.preset.background_color, self.preset.default_stroke_color)
                attrs.append(f'stroke="{safe_color}"')
        if stroke_width is not None and abs(stroke_width - self.preset.default_stroke_width) > 1e-4:
            attrs.append(f'stroke-width="{stroke_width:.2f}px"')
        dash = stroke_dasharray or map_cad_linetype_to_dasharray(linetype)
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
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
        linetype: Optional[str] = None,
        stroke_dasharray: Optional[str] = None,
    ) -> None:
        """Appends an SVG <circle> element with contrast safety and linetype dasharray."""
        target = self._get_target_layer_list(layer)
        attrs = [
            f'cx="{cx:.3f}"',
            f'cy="{cy:.3f}"',
            f'r="{r:.3f}"',
            f'fill="{fill or "none"}"',
        ]

        if color and self.preset.color_mode != "monochrome":
            clean_c = clean_hex(color)
            if clean_c:
                safe_color = resolve_contrast_color(clean_c, self.preset.background_color, self.preset.default_stroke_color)
                attrs.append(f'stroke="{safe_color}"')
        dash = stroke_dasharray or map_cad_linetype_to_dasharray(linetype)
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
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
        linetype: Optional[str] = None,
        stroke_dasharray: Optional[str] = None,
    ) -> None:
        """Appends an SVG <path> element (for arcs, polylines, and complex contours) with contrast safety and linetype dasharray."""
        if not d:
            return
        target = self._get_target_layer_list(layer)
        attrs = [
            f'd="{d}"',
            f'fill="{fill or "none"}"',
        ]

        if color and self.preset.color_mode != "monochrome":
            clean_c = clean_hex(color)
            if clean_c:
                safe_color = resolve_contrast_color(clean_c, self.preset.background_color, self.preset.default_stroke_color)
                attrs.append(f'stroke="{safe_color}"')
        if stroke_width is not None and abs(stroke_width - self.preset.default_stroke_width) > 1e-4:
            attrs.append(f'stroke-width="{stroke_width:.2f}px"')
        dash = stroke_dasharray or map_cad_linetype_to_dasharray(linetype)
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
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
        linetype: Optional[str] = None,
        stroke_dasharray: Optional[str] = None,
    ) -> None:
        """Appends an SVG <polyline> or <polygon> element with contrast safety and linetype dasharray."""
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
            clean_c = clean_hex(color)
            if clean_c:
                safe_color = resolve_contrast_color(clean_c, self.preset.background_color, self.preset.default_stroke_color)
                attrs.append(f'stroke="{safe_color}"')
        dash = stroke_dasharray or map_cad_linetype_to_dasharray(linetype)
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
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
        """Appends an SVG <text> element with proper XML escaping, contrast safety, and unitless font sizing."""
        clean = sanitize_cad_text(text)
        if not clean:
            return

        target = self._get_target_layer_list(layer)
        fill_color = self.preset.default_stroke_color
        if color and self.preset.color_mode != "monochrome":
            clean_c = clean_hex(color)
            if clean_c:
                fill_color = resolve_contrast_color(clean_c, self.preset.background_color, self.preset.default_stroke_color)
        elif self.preset.color_mode != "monochrome" and layer:
            layer_meta = self.layer_attributes.get(layer, {})
            layer_stroke = layer_meta.get("stroke")
            if layer_stroke:
                fill_color = layer_stroke

        lines = clean.split("\n")
        safe_h = max(0.001, height)

        transform_attr = ""
        if abs(rotation) > 1e-4:
            # Note: in SVG (+Y down), standard CAD counter-clockwise rotation becomes -rotation
            transform_attr = f' transform="rotate({-rotation:.2f} {x:.3f} {y:.3f})"'

        attrs = [
            f'x="{x:.3f}"',
            f'y="{y:.3f}"',
            f'font-size="{safe_h:.2f}"',
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
                dy = f'{safe_h * 1.2:.2f}' if idx > 0 else '0'
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
                if "stroke-dasharray" in layer_meta:
                    group_attrs.append(f'stroke-dasharray="{layer_meta["stroke-dasharray"]}"')
                if self.preset.non_scaling_stroke:
                    group_attrs.append('vector-effect="non-scaling-stroke"')

                out.append(f'  <g {" ".join(group_attrs)}>')
                out.extend(elements)
                out.append('  </g>')

        out.append('</svg>\n')
        return "\n".join(out)
