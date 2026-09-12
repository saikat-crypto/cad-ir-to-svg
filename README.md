# cad-ir-to-svg

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://python.org)
[![Output: Scalable%20Vector%20Graphics](https://img.shields.io/badge/Output-W3C%20SVG-orange.svg)](#)
[![Ecosystem](https://img.shields.io/badge/Project-La%20Vinci-purple.svg)](#)

**High-Fidelity Vector CAD to SVG Compiler.**  
Converts a [`LAVINCI_CAD_IR_V3`](https://github.com/saikat-crypto/cad-extractor-ir) JSON payload into responsive, W3C-compliant Scalable Vector Graphics (SVG) with native vector paths, interactive layer grouping, and non-scaling strokes.

*Engineered by **Saikat Dutta Chowdhury** as part of the **La Vinci** engineering initiative.*

</div>

---

## 💡 Pipeline Position

This package is a core downstream spoke of the La Vinci Hub-and-Spoke CAD architecture:

```
AutoCAD DWG / DXF ──► cad-extractor-ir ──► LAVINCI_CAD_IR_V3 ──► cad-ir-to-svg ──► W3C Vector SVG
```

---

## ✨ Features

- **Pure W3C Scalable Vector Graphics**: 100% vector linework with clean `<svg>`, `<g>`, `<line>`, `<circle>`, `<path>`, and `<text>` elements. Infinite clarity at any zoom factor.
- **Interactive Layer Grouping**: Entities are neatly organized into DOM groups (`<g id="layer-WALLS" class="cad-layer" data-layer-name="WALLS">`), enabling frontend JavaScript/CSS to toggle layer visibility, attach event listeners, or style layers dynamically.
- **Crisp Pan & Zoom (`non-scaling-stroke`)**: Injects `vector-effect="non-scaling-stroke"` so lines remain crisp hairlines during browser pan and zoom operations rather than ballooning into thick bars.
- **Mathematical CAD-to-SVG Y-Inversion**: Automatically flips the CAD $+Y$ (up) axis to SVG $+Y$ (down) across the isotropic bounding box, ensuring drawings and text render right-side up with correct chirality.
- **Exact Elliptical & Circular Arc Mapping**: Translates CAD arc centers, radii, and sweep angles into native SVG path `A` (elliptical arc) commands without polygon chord degradation.
- **Hierarchical Block Unrolling**: Evaluates 2D affine transformation matrices ($T \cdot R \cdot S$) on nested CAD blocks (`INSERT`), handling translation, rotation, and non-uniform scaling with cycle detection.
- **Anonymous Dimension Block (`*D...`) Rendering**: Ingests AutoCAD dimension witness lines, tick marks, and measurement labels with proper clearance.
- **Zero External Heavy Dependencies**: Built with Python standard library—stateless, ultra-fast, and cloud-ready for AWS Lambda, FastAPI, or MCP tool servers.

---

## 📐 Active Default Preset: `web-interactive-light`

| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| **Canvas Background** | **`#FFFFFF`** | Clean presentation canvas. |
| **Default Stroke** | **`#1A1A1A`** | High-contrast charcoal with layer color overrides preserved. |
| **Stroke Width** | **`1.0 px`** | Balanced stroke weight. |
| **Non-Scaling Stroke** | **`True`** | Maintains uniform stroke width on browser pan/zoom (`vector-effect="non-scaling-stroke"`). |
| **Layer Grouping** | **`True`** | Wraps entities in `<g id="layer-..." class="cad-layer">`. |
| **Y-Inversion** | **`True`** | Mathematical projection from CAD (+Y up) to SVG (+Y down). |
| **Padding Margin** | **`5%`** | Isotropic boundary padding around drawing extents. |
| **Color Mode** | **`layer`** | Respects CAD layer and entity true colors. |

### Extensible Presets Available
- **`web-interactive-light`** *(Default)*: Responsive web viewer with interactive layer groups and non-scaling strokes.
- **`cad-dark-modelspace`**: Classic AutoCAD dark background (`#1E1E1E`) with vibrant ACI neon colors.
- **`architectural-monochrome`**: Strict black-and-white linework for documentation and printing.
- **`fabrication-cnc-hairline`**: Ultra-fine hairline paths (`0.1px`, transparent background, no text/dimensions) for laser cutters and CNCs.

---

## 🚀 Installation

```bash
git clone https://github.com/saikat-crypto/cad-ir-to-svg.git
cd cad-ir-to-svg
pip install -e .
```

---

## 💻 CLI Usage

### Basic Compilation
```bash
cad-ir-to-svg floor_plan.json -o floor_plan.svg
```

### Specifying Presets
```bash
cad-ir-to-svg blueprint.json -o blueprint_dark.svg --preset cad-dark-modelspace
cad-ir-to-svg blueprint.json -o blueprint_mono.svg --preset architectural-monochrome
```

### Introspection (For AI Agents & Automation)
```bash
# Query drawing bounds
cad-ir-to-svg blueprint.json --inspect-bounds

# List all CAD layers
cad-ir-to-svg blueprint.json --list-layers
```

---

## 🐍 Python API

```python
from cad_ir_to_svg import compile_ir_to_svg, compile_ir_to_svg_string, PRESETS, SvgPreset

# 1. Compile file to file
svg_path = compile_ir_to_svg("floor_plan.json", "output.svg")

# 2. In-memory string compilation (ideal for AWS Lambda or FastAPI)
with open("floor_plan.json", "r") as f:
    ir_data = json.load(f)

svg_xml_string, report = compile_ir_to_svg_string(ir_data, preset="web-interactive-light")
print(f"Rendered {report.total_entities_rendered} entities in viewBox {report.viewbox}")

# 3. Custom user-defined preset
custom_preset = SvgPreset(
    name="custom-brand",
    description="Custom styling with corporate brand colors",
    background_color="#F8F9FA",
    default_stroke_color="#003366",
    non_scaling_stroke=True,
    padding_ratio=0.08,
)
svg_path = compile_ir_to_svg("floor_plan.json", "branded.svg", preset=custom_preset)
```

---

## 🧪 Testing

```bash
pytest tests/ -v
```

---

## 📄 License

MIT License. Copyright (c) 2026 La Vinci.
