# cad-ir-to-svg: Scalable Vector Graphics Compiler & Digital Twin Engine

<div align="center">

[![Python: 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Format: W3C SVG 1.1/2.0](https://img.shields.io/badge/Format-W3C%20SVG%20Vector-FF9F43.svg?style=for-the-badge)](#)
[![Domain: Web CAD / Digital Twins](https://img.shields.io/badge/Domain-Web%20CAD%20%7C%20Digital%20Twins-10AC84.svg?style=for-the-badge)](#)
[![Validation Suite](https://img.shields.io/badge/Test%20Suite-100%25%20Passing-2ED573.svg?style=for-the-badge)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**A high-precision vector compiler translating canonical `LAVINCI_CAD_IR_V3` JSON models into interactive, semantic Scalable Vector Graphics (SVG), featuring planar reflection arc chirality correction and dynamic diagonal stroke width scaling.**

*Part of the **La Vinci** engineering initiative by **Saikat Dutta Chowdhury** (Mechanical Engineering).*

</div>

---

## 💡 The Web CAD Problem & Engineering Scope

Embedding complex engineering CAD drawings into modern web applications (interactive dashboards, digital twins, IoT factory maps) has historically been an uphill battle:
1. **Coordinate Reflection Inversion**: AutoCAD's $+Y$ up coordinates invert when mapped to SVG's $+Y$ down screen space, causing circular arcs to invert their rotational sweep direction and explode outside the canvas.
2. **Fixed Stroke-Width Distortion**: A fixed $1\text{px}$ line thickness bloats into solid black blobs on a small mechanical bolt ($10\text{mm}$) and renders completely invisible on a civil facility layout ($100\text{m}$).
3. **Loss of Semantic Hierarchy**: Generic converters flatten layers into unstructured path soups, making browser DOM selection and layer toggling impossible.

**`cad-ir-to-svg`** transforms raw CAD intermediate representations into clean, web-native vector documents:
* Mathematical **planar arc chirality correction** enforcing exact circular curvature.
* **Diagonal-proportional stroke scaling** ensuring aesthetic line weights across any drawing size.
* **Semantic layer grouping** (`<g id="layer-{name}">`) enabling direct JavaScript DOM interaction.
* Injects **`vector-effect="non-scaling-stroke"`** for crisp linework during browser zoom and pan.

```
[ Input: LAVINCI_CAD_IR_V3 JSON ]
               │
               ▼
┌──────────────────────────────────────────────┐
│           cad-ir-to-svg Compiler             │
│                                              │
│  1. Extents & Outlier Isolation              │
│     • Primary cluster isolation              │
│     • Unconditional text bbox protection     │
│                                              │
│  2. Coordinate Inversion & Chirality Pass    │
│     • Y_svg = Y_max + Y_min - Y_cad          │
│     • Rotational chirality: CCW -> CW        │
│     • sweep_flag = 1 (enforces true curves)  │
│                                              │
│  3. Adaptive Diagonal Stroke Scaling         │
│     • default_stroke = max(0.1, 0.001*diag)  │
│                                              │
│  4. Semantic SVG Emission                    │
│     • <g id="layer-..." class="cad-layer">   │
│     • vector-effect="non-scaling-stroke"     │
└──────────────────────────────────────────────┘
               │
               ▼
[ Output: interactive_cad.svg ]
```

---

## 🔬 Mathematical Invariants & Chirality Resolution

### 1. Planar Arc Chirality Inversion under Vertical Reflection
In CAD space, analytic arcs sweep counter-clockwise (CCW). SVG coordinates invert the vertical axis:
$$Y_{\text{svg}} = Y_{\text{extent\_max}} + Y_{\text{extent\_min}} - Y_{\text{cad}}$$
Because the Jacobian determinant of a vertical reflection matrix is negative:
$$\det \begin{bmatrix} 1 & 0 \\ 0 & -1 \end{bmatrix} = -1$$
The orientation of rotational paths inverts: **$\text{CCW} \mapsto \text{CW}$**. Naive converters keeping `sweep_flag = 0` (CCW) cause arcs to sweep inside-out. `cad-ir-to-svg` mathematically enforces:
```python
sweep_flag = 1  # Clockwise sweep required in Y-down SVG coordinate space
path_d = f"M {start_x:.3f},{start_y:.3f} A {r:.3f},{r:.3f} 0 {large_arc_flag} {sweep_flag} {end_x:.3f},{end_y:.3f}"
```

### 2. Extents Diagonal Proportional Stroke Scaling
Computes the spatial diagonal of the geometry envelope to ensure scale-invariant stroke thickness:
$$\text{diagonal} = \sqrt{(X_{\max}-X_{\min})^2 + (Y_{\max}-Y_{\min})^2}$$
$$\text{default\_stroke\_width} = \max\left(0.1, \; 0.001 \times \text{diagonal}\right) \times \text{stroke\_scale}$$

### 3. Semantic DOM Layer Selection
Layers are wrapped in distinct groups, allowing frontend developers to control architectural visibility via standard JavaScript:
```javascript
// Toggle HVAC ductwork in browser DOM
document.querySelector('g[data-layer-name="M-HVAC"]').style.display = 'none';
```

---

## ⚡ Quick Start

### Installation
```bash
pip install -e products/cad-ir-to-svg
```

### Python SDK
```python
from cad_ir_to_svg import compile_ir_to_svg_string
from cad_ir_to_svg.config import SvgOptions

# 1. Compile with standard interactive web preset
svg_xml, telemetry = compile_ir_to_svg_string(
    ir_source="piping_network_ir.json",
    preset="web-interactive-light"
)

with open("piping_network.svg", "w", encoding="utf-8") as f:
    f.write(svg_xml)

# 2. Compile authentic dark modelspace theme
svg_dark, _ = compile_ir_to_svg_string(
    ir_source="piping_network_ir.json",
    preset="cad-dark-modelspace"
)
```

### Command Line Interface (CLI)
```bash
# Convert to standard web SVG
python -m cad_ir_to_svg.cli drawing_ir.json -o drawing.svg

# Convert with authentic dark modelspace theme
python -m cad_ir_to_svg.cli drawing_ir.json -o dark.svg --preset cad-dark-modelspace
```

---

## 📄 License

Licensed under the [MIT License](LICENSE).
