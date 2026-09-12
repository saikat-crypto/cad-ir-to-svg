"""
Core Vector Compiler for cad-ir-to-svg.
Orchestrates IR ingestion, layer styles, block unrolling, coordinate Y-inversion,
outlier pruning, dimension rendering, and SVG XML emission.
Adheres strictly to the La Vinci Engineering & Reliability Contract.
"""

import json
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple

from .config import SvgPreset, DEFAULT_PRESET, PRESETS
from .geometry import (
    BoundingBox,
    AffineMatrix2D,
    find_primary_cluster_1d,
    is_valid_point,
    is_finite_number,
    cad_arc_to_svg_path,
)
from .svg_writer import SvgWriter, sanitize_cad_text
from .telemetry import (
    HardeningWarning,
    HardeningCategory,
    ActionTaken,
    CompilationReport,
)

MAX_BLOCK_DEPTH = 16
MAX_TOTAL_EXPANDED_ENTITIES = 500_000


def _load_ir_dict(ir_source: Union[str, Path, Dict[str, Any], Any]) -> Dict[str, Any]:
    """Defensively converts input source into a standard Python dictionary."""
    if isinstance(ir_source, dict):
        return ir_source
    if hasattr(ir_source, "model_dump"):
        return ir_source.model_dump()
    if hasattr(ir_source, "dict") and callable(ir_source.dict):
        return ir_source.dict()

    # Path or raw JSON string
    if isinstance(ir_source, (str, Path)):
        s = str(ir_source).strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                return json.loads(s)
            except Exception:
                pass
        p = Path(ir_source)
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)

    raise ValueError(f"Unable to parse CAD IR payload from source of type {type(ir_source)}")


def compute_ir_extents(
    ir: Dict[str, Any],
    outlier_pruning: bool = True,
    target_space: str = "Model",
) -> BoundingBox:
    """
    Computes spatial bounding box across all active primitives and block components.
    Applies gap-based coordinate clustering if outlier_pruning is enabled to reject
    distant scratch geometry while strictly preserving multi-view drawings.
    """
    box = BoundingBox()
    x_coords: List[float] = []
    y_coords: List[float] = []

    def _feed_point(x: float, y: float):
        if is_finite_number(x) and is_finite_number(y):
            # Guard against astronomical outliers (> 1e9)
            if abs(x) < 1e9 and abs(y) < 1e9:
                x_coords.append(float(x))
                y_coords.append(float(y))
                box.expand(float(x), float(y))

    geom = ir.get("geometry_primitives")
    prims = geom.get("primitives", {}) if isinstance(geom, dict) else {}

    # 1. Lines
    lines = prims.get("lines", [])
    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, dict):
                start = line.get("start")
                end = line.get("end")
                if is_valid_point(start) and is_valid_point(end):
                    _feed_point(start[0], start[1])
                    _feed_point(end[0], end[1])

    # 2. Arcs & Circles
    arcs = prims.get("arcs", [])
    if isinstance(arcs, list):
        for arc in arcs:
            if isinstance(arc, dict):
                c = arc.get("center")
                r = arc.get("radius")
                if is_valid_point(c) and is_finite_number(r) and r > 0:
                    _feed_point(c[0] - r, c[1] - r)
                    _feed_point(c[0] + r, c[1] + r)

    circles = prims.get("circles", [])
    if isinstance(circles, list):
        for cir in circles:
            if isinstance(cir, dict):
                c = cir.get("center")
                r = cir.get("radius")
                if is_valid_point(c) and is_finite_number(r) and r > 0:
                    _feed_point(c[0] - r, c[1] - r)
                    _feed_point(c[0] + r, c[1] + r)

    # 3. Polylines
    polys = prims.get("polylines", [])
    if isinstance(polys, list):
        for poly in polys:
            if isinstance(poly, dict):
                pts = poly.get("points", [])
                if isinstance(pts, list):
                    for pt in pts:
                        if is_valid_point(pt):
                            _feed_point(pt[0], pt[1])

    # 4. Component instances
    comps = ir.get("components", [])
    if isinstance(comps, list):
        for comp in comps:
            if isinstance(comp, dict):
                pos = comp.get("position")
                if is_valid_point(pos):
                    _feed_point(pos[0], pos[1])

    # 5. Annotations
    annots = ir.get("annotations", [])
    if isinstance(annots, list):
        for annot in annots:
            if isinstance(annot, dict):
                pos = annot.get("position")
                if is_valid_point(pos):
                    _feed_point(pos[0], pos[1])

    # 6. Dimensions
    dims = ir.get("dimensions", [])
    if isinstance(dims, list):
        for dim in dims:
            if isinstance(dim, dict):
                dp = dim.get("defpoint")
                if is_valid_point(dp):
                    _feed_point(dp[0], dp[1])
                dp2 = dim.get("defpoint2")
                if is_valid_point(dp2):
                    _feed_point(dp2[0], dp2[1])

    if not box.is_valid:
        # Default fallback box for empty drawings
        return BoundingBox(0.0, 0.0, 100.0, 100.0)

    # Apply 1D gap-based clustering outlier pruning if requested
    if outlier_pruning and len(x_coords) > 20:
        px_min, px_max = find_primary_cluster_1d(x_coords)
        py_min, py_max = find_primary_cluster_1d(y_coords)
        pruned_box = BoundingBox(px_min, py_min, px_max, py_max)
        if pruned_box.is_valid and pruned_box.width > 0 and pruned_box.height > 0:
            return pruned_box

    return box


def compile_ir_to_svg_string(
    ir_source: Union[str, Path, Dict[str, Any], Any],
    preset: Optional[Union[SvgPreset, str]] = None,
    warning_collector: Optional[List[HardeningWarning]] = None,
) -> Tuple[str, CompilationReport]:
    """
    Compiles a LAVINCI_CAD_IR_V3 source into a valid W3C SVG XML string.
    Returns (svg_string, compilation_report).
    Stateless, in-memory stream compatible for AWS Lambda, FastAPI, or MCP tools.
    """
    report = CompilationReport()
    warnings: List[HardeningWarning] = []

    def _warn(cat: HardeningCategory, act: ActionTaken, etype: str, reason: str, **kwargs):
        w = HardeningWarning(
            category=cat,
            action=act,
            entity_type=etype,
            reason=reason,
            layer=kwargs.get("layer"),
            original_value=kwargs.get("original_value"),
            sanitized_value=kwargs.get("sanitized_value"),
        )
        warnings.append(w)
        if warning_collector is not None:
            warning_collector.append(w)

    # 1. Resolve Preset
    active_preset: SvgPreset
    if preset is None:
        active_preset = DEFAULT_PRESET
    elif isinstance(preset, str):
        if preset in PRESETS:
            active_preset = PRESETS[preset]
        else:
            _warn(
                HardeningCategory.METADATA_MALFORMED,
                ActionTaken.FALLBACK_APPLIED,
                "preset",
                f"Unknown preset '{preset}', falling back to default.",
            )
            active_preset = DEFAULT_PRESET
    elif isinstance(preset, SvgPreset):
        active_preset = preset
    else:
        active_preset = DEFAULT_PRESET

    # 2. Parse IR Payload
    ir = _load_ir_dict(ir_source)

    # 3. Compute Bounding Box & Viewport
    raw_bbox = compute_ir_extents(
        ir,
        outlier_pruning=active_preset.outlier_pruning,
        target_space=active_preset.target_space,
    )
    padded_bbox = raw_bbox.with_padding(active_preset.padding_ratio)

    # 4. Y-Inversion Transform Function
    # In CAD, +Y goes UP. In SVG, +Y goes DOWN.
    # Reflecting across the horizontal midline: svg_y = (min_y + max_y) - cad_y
    # Bounds remain identically [min_y, max_y] with CAD top (max_y) mapping to SVG top (min_y).
    y_sum = padded_bbox.min_y + padded_bbox.max_y

    def cad_to_svg(cx: float, cy: float) -> Tuple[float, float]:
        if not is_finite_number(cx) or not is_finite_number(cy):
            return (0.0, 0.0)
        if active_preset.invert_y:
            return (float(cx), y_sum - float(cy))
        return (float(cx), float(cy))

    # 5. Initialize SVG Writer
    writer = SvgWriter(padded_bbox, active_preset)

    # Register Layers
    layers_data = ir.get("layers", [])
    if isinstance(layers_data, list):
        for l in layers_data:
            if isinstance(l, dict):
                lname = str(l.get("name", "0"))
                lcolor = l.get("hex_color")
                writer.register_layer(lname, color=lcolor)

    # 6. Extract Primitives & Blocks
    geom_data = ir.get("geometry_primitives", {})
    prims = geom_data.get("primitives", {}) if isinstance(geom_data, dict) else {}
    block_defs = ir.get("block_definitions", {}) if isinstance(ir.get("block_definitions"), dict) else {}

    entities_read = 0
    entities_rendered = 0
    entities_dropped = 0

    # Helper to emit a single line
    def emit_line(start, end, layer="0", color=None, width=None):
        nonlocal entities_rendered, entities_dropped
        if not is_valid_point(start) or not is_valid_point(end):
            entities_dropped += 1
            _warn(HardeningCategory.COORDINATE_SINGULARITY, ActionTaken.DROPPED, "line", "Invalid point coordinates")
            return
        # Check zero-length line
        if abs(start[0] - end[0]) < 1e-6 and abs(start[1] - end[1]) < 1e-6:
            entities_dropped += 1
            return
        sp1 = cad_to_svg(start[0], start[1])
        sp2 = cad_to_svg(end[0], end[1])
        writer.add_line(sp1[0], sp1[1], sp2[0], sp2[1], layer=layer, color=color, stroke_width=width)
        entities_rendered += 1

    # Helper to emit a circular arc
    def emit_arc(center, radius, start_angle, end_angle, layer="0", color=None):
        nonlocal entities_rendered, entities_dropped
        if not is_valid_point(center) or not is_finite_number(radius) or radius <= 0:
            entities_dropped += 1
            return
        d_path = cad_arc_to_svg_path(
            center[0], center[1], radius,
            start_angle, end_angle,
            cad_to_svg
        )
        if d_path:
            writer.add_path(d_path, layer=layer, color=color)
            entities_rendered += 1
        else:
            entities_dropped += 1

    # Helper to emit a circle
    def emit_circle(center, radius, layer="0", color=None):
        nonlocal entities_rendered, entities_dropped
        if not is_valid_point(center) or not is_finite_number(radius) or radius <= 0:
            entities_dropped += 1
            return
        sc = cad_to_svg(center[0], center[1])
        writer.add_circle(sc[0], sc[1], radius, layer=layer, color=color)
        entities_rendered += 1

    # Helper to emit a polyline
    def emit_polyline(points, is_closed=False, layer="0", color=None):
        nonlocal entities_rendered, entities_dropped
        if not points or len(points) < 2:
            entities_dropped += 1
            return
        valid_pts = [cad_to_svg(p[0], p[1]) for p in points if is_valid_point(p)]
        if len(valid_pts) < 2:
            entities_dropped += 1
            return
        writer.add_polyline(valid_pts, is_closed=is_closed, layer=layer, color=color)
        entities_rendered += 1

    # 7. Render Model Space Root Primitives
    # Lines
    raw_lines = prims.get("lines", [])
    if isinstance(raw_lines, list):
        for line in raw_lines:
            entities_read += 1
            if isinstance(line, dict):
                emit_line(line.get("start"), line.get("end"), layer=line.get("layer", "0"), color=line.get("color"))

    # Arcs
    raw_arcs = prims.get("arcs", [])
    if isinstance(raw_arcs, list):
        for arc in raw_arcs:
            entities_read += 1
            if isinstance(arc, dict):
                emit_arc(
                    arc.get("center"), arc.get("radius"),
                    arc.get("start_angle", 0.0), arc.get("end_angle", 360.0),
                    layer=arc.get("layer", "0"), color=arc.get("color")
                )

    # Circles
    raw_circles = prims.get("circles", [])
    if isinstance(raw_circles, list):
        for cir in raw_circles:
            entities_read += 1
            if isinstance(cir, dict):
                emit_circle(cir.get("center"), cir.get("radius"), layer=cir.get("layer", "0"), color=cir.get("color"))

    # Polylines
    raw_polys = prims.get("polylines", [])
    if isinstance(raw_polys, list):
        for poly in raw_polys:
            entities_read += 1
            if isinstance(poly, dict):
                emit_polyline(
                    poly.get("points", []),
                    is_closed=bool(poly.get("is_closed", False)),
                    layer=poly.get("layer", "0"),
                    color=poly.get("color")
                )

    # 8. Render Hierarchical Block Instances (components)
    def render_block_recursive(block_name: str, matrix: AffineMatrix2D, parent_layer: str, depth: int, visited: set):
        nonlocal entities_rendered, entities_dropped
        if depth > MAX_BLOCK_DEPTH:
            _warn(HardeningCategory.TRANSFORM_ABUSE, ActionTaken.DROPPED, "block", f"Exceeded max block depth {MAX_BLOCK_DEPTH}")
            return
        if block_name in visited:
            _warn(HardeningCategory.TRANSFORM_ABUSE, ActionTaken.DROPPED, "block", f"Cycle detected in block reference '{block_name}'")
            return
        if entities_rendered > MAX_TOTAL_EXPANDED_ENTITIES:
            _warn(HardeningCategory.TRANSFORM_ABUSE, ActionTaken.DROPPED, "block", "Quota reached for expanded entities")
            return

        bdef = block_defs.get(block_name)
        if not bdef or not isinstance(bdef, dict):
            return

        visited.add(block_name)

        # Lines inside block
        for bline in bdef.get("lines", []):
            if isinstance(bline, dict):
                p1 = bline.get("start")
                p2 = bline.get("end")
                if is_valid_point(p1) and is_valid_point(p2):
                    tp1 = matrix.transform_point(p1[0], p1[1])
                    tp2 = matrix.transform_point(p2[0], p2[1])
                    layer = bline.get("layer") or parent_layer
                    emit_line(tp1, tp2, layer=layer, color=bline.get("color"))

        # Circles inside block
        for bcir in bdef.get("circles", []):
            if isinstance(bcir, dict):
                c = bcir.get("center")
                r = bcir.get("radius")
                if is_valid_point(c) and is_finite_number(r) and r > 0:
                    tc = matrix.transform_point(c[0], c[1])
                    # Effective isotropic scale
                    scale_factor = math.sqrt(abs(matrix.determinant)) if abs(matrix.determinant) > 1e-12 else 1.0
                    layer = bcir.get("layer") or parent_layer
                    emit_circle(tc, r * scale_factor, layer=layer, color=bcir.get("color"))

        # Arcs inside block
        for barc in bdef.get("arcs", []):
            if isinstance(barc, dict):
                c = barc.get("center")
                r = barc.get("radius")
                if is_valid_point(c) and is_finite_number(r) and r > 0:
                    tc = matrix.transform_point(c[0], c[1])
                    scale_factor = math.sqrt(abs(matrix.determinant)) if abs(matrix.determinant) > 1e-12 else 1.0
                    rot_deg = math.degrees(math.atan2(matrix.b, matrix.a))
                    sa = (barc.get("start_angle", 0.0) + rot_deg) % 360.0
                    ea = (barc.get("end_angle", 360.0) + rot_deg) % 360.0
                    layer = barc.get("layer") or parent_layer
                    emit_arc(tc, r * scale_factor, sa, ea, layer=layer, color=barc.get("color"))

        # Polylines inside block
        for bpoly in bdef.get("polylines", []):
            if isinstance(bpoly, dict):
                pts = bpoly.get("points", [])
                if isinstance(pts, list) and len(pts) >= 2:
                    tpts = [matrix.transform_point(p[0], p[1]) for p in pts if is_valid_point(p)]
                    layer = bpoly.get("layer") or parent_layer
                    emit_polyline(tpts, is_closed=bool(bpoly.get("is_closed")), layer=layer, color=bpoly.get("color"))

        visited.remove(block_name)

    raw_comps = ir.get("components", [])
    if isinstance(raw_comps, list):
        for comp in raw_comps:
            entities_read += 1
            if not isinstance(comp, dict):
                continue
            bname = comp.get("block_name")
            if not bname or bname not in block_defs:
                continue

            pos = comp.get("position", [0.0, 0.0])
            rot = comp.get("rotation", 0.0)
            scl = comp.get("scale", [1.0, 1.0, 1.0])
            bdef = block_defs.get(bname, {})
            bpt = bdef.get("base_point", [0.0, 0.0, 0.0]) if isinstance(bdef, dict) else [0.0, 0.0, 0.0]

            mat = AffineMatrix2D.from_cad_insert(pos, rot, scl, bpt)
            if mat.is_singular:
                entities_dropped += 1
                _warn(HardeningCategory.TRANSFORM_ABUSE, ActionTaken.DROPPED, "component", f"Singular matrix in component '{bname}'")
                continue

            clayer = comp.get("layer", "0")
            render_block_recursive(bname, mat, clayer, depth=0, visited=set())

    # 9. Anonymous Dimension Blocks (*D...)
    # AutoCAD dimension lines, ticks, and extension lines are stored in *D... block definitions
    for bname, bdef in block_defs.items():
        if bname.startswith("*D") and isinstance(bdef, dict):
            # Dimension blocks reside in world coordinates (identity transform)
            render_block_recursive(bname, AffineMatrix2D.identity(), "DIMENSION", depth=0, visited=set())

    # 10. Text & Annotations
    if active_preset.include_annotations:
        raw_annots = ir.get("annotations", [])
        if isinstance(raw_annots, list):
            for annot in raw_annots:
                entities_read += 1
                if not isinstance(annot, dict):
                    continue
                pos = annot.get("position")
                raw_txt = annot.get("clean_text") or annot.get("raw_text") or annot.get("text") or annot.get("value")
                if is_valid_point(pos) and raw_txt:
                    sp = cad_to_svg(pos[0], pos[1])
                    h = annot.get("height", 12.0)
                    alayer = annot.get("layer", "0")
                    rot = annot.get("rotation", 0.0)
                    writer.add_text(
                        sp[0], sp[1], str(raw_txt),
                        height=float(h) if is_finite_number(h) else 12.0,
                        layer=alayer,
                        color=annot.get("color"),
                        rotation=float(rot) if is_finite_number(rot) else 0.0,
                    )
                    entities_rendered += 1

    # 11. Dimensions Text Labels
    if active_preset.include_dimensions:
        raw_dims = ir.get("dimensions", [])
        if isinstance(raw_dims, list):
            for dim in raw_dims:
                entities_read += 1
                if not isinstance(dim, dict):
                    continue
                dim_txt = dim.get("text")
                if not dim_txt and dim.get("measurement") is not None:
                    meas = dim.get("measurement")
                    if is_finite_number(meas):
                        dim_txt = f"{meas:.1f}" if abs(meas - round(meas)) > 0.05 else f"{int(round(meas))}"

                # Prefer explicitly positioned text midpoint anchor if available
                dpos = dim.get("text_midpoint") or dim.get("defpoint")
                if is_valid_point(dpos) and dim_txt:
                    sp = cad_to_svg(dpos[0], dpos[1])
                    dh = dim.get("text_height", 10.0)
                    dlayer = dim.get("layer", "DIMENSION")
                    drot = dim.get("text_rotation", 0.0)
                    writer.add_text(
                        sp[0], sp[1], str(dim_txt),
                        height=float(dh) if is_finite_number(dh) and float(dh) > 0 else 10.0,
                        layer=dlayer,
                        color=dim.get("color"),
                        rotation=float(drot) if is_finite_number(drot) else 0.0,
                    )
                    entities_rendered += 1

    # 12. Build SVG
    svg_content = writer.build_svg()

    # Populate Report
    report.success = True
    report.total_entities_read = entities_read
    report.total_entities_rendered = entities_rendered
    report.total_entities_dropped = entities_dropped
    report.viewbox = f"{padded_bbox.min_x:.3f} {padded_bbox.min_y:.3f} {padded_bbox.width:.3f} {padded_bbox.height:.3f}"
    report.width = padded_bbox.width
    report.height = padded_bbox.height
    report.layers_rendered = list(writer.layer_elements.keys())
    report.warnings = warnings

    return svg_content, report


def compile_ir_to_svg(
    ir_source: Union[str, Path, Dict[str, Any], Any],
    output_path: Union[str, Path],
    preset: Optional[Union[SvgPreset, str]] = None,
    warning_collector: Optional[List[HardeningWarning]] = None,
) -> Path:
    """
    Compiles a LAVINCI_CAD_IR_V3 source and saves the W3C SVG file to disk atomically.
    Returns the Path to the compiled SVG.
    """
    svg_str, report = compile_ir_to_svg_string(ir_source, preset=preset, warning_collector=warning_collector)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg_str)
    report.output_target = str(out)
    return out


# Introspection Primitives for AI Agents & MCP Tools
def get_svg_bounds(ir_source: Union[str, Path, Dict[str, Any], Any]) -> Dict[str, float]:
    """Inspects and returns the isotropic spatial bounding box of a CAD drawing."""
    ir = _load_ir_dict(ir_source)
    box = compute_ir_extents(ir, outlier_pruning=True)
    return {
        "min_x": box.min_x,
        "min_y": box.min_y,
        "max_x": box.max_x,
        "max_y": box.max_y,
        "width": box.width,
        "height": box.height,
        "center_x": box.center[0],
        "center_y": box.center[1],
    }


def list_svg_layers(ir_source: Union[str, Path, Dict[str, Any], Any]) -> List[str]:
    """Inspects and lists all layer names defined in the drawing."""
    ir = _load_ir_dict(ir_source)
    layers = ir.get("layers", [])
    if isinstance(layers, list):
        return [str(l.get("name", "0")) for l in layers if isinstance(l, dict)]
    return ["0"]
