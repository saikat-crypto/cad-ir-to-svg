# cad-ir-to-svg: Scalable Vector Graphics Compiler & Web Optimization Engine

> **Product**: `cad-ir-to-svg`  
> **Package Version**: `1.0.0`  
> **Source Directory**: `products/cad-ir-to-svg/`  
> **Role in Ecosystem**: Vector SVG Egress Compiler (`LAVINCI_CAD_IR_V3` $\to$ Scalable Vector Graphics)  

---

## 1. Executive Summary & Core Capabilities

The **`cad-ir-to-svg`** compiler transforms canonical **`LAVINCI_CAD_IR_V3`** JSON representations into standards-compliant, highly optimized, and interactive Scalable Vector Graphics (SVG 1.1 / SVG 2.0).

Unlike traditional CAD-to-SVG exporters that produce static or unstructured XML blobs with broken scales, `cad-ir-to-svg` is engineered specifically for **modern interactive web applications, CAD viewers, digital twins, and browser-based technical drafting**:
* **Semantic Layer Hierarchy**: Groups geometric elements inside `<g id="layer-{name}" class="cad-layer">` tags, enabling client-side JavaScript to toggle layer visibility, inspect metadata, or apply dynamic CSS hover/selection effects.
* **Coordinate Handedness Resolution**: Seamlessly maps AutoCAD's mathematical $+Y$ upwards coordinate system to the SVG screen $+Y$ downwards specification.
* **Empirically Calibrated Arc Mathematics**: Solves the planar reflection chirality inversion problem to ensure curved paths sweep along their intended trajectory.
* **Dynamic ViewBox & Proportional Stroke Scaling**: Employs adaptive diagonal-ratio stroke algorithms to guarantee that floorplans of any physical scale render with readable, aesthetic linework.

```
 ┌──────────────────────────────┐
 │   LAVINCI_CAD_IR_V3 (JSON)   │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │     Extents & Outliers       │
 │   - Primary Cluster Filter   │
 │   - Text Entity BBox Guard   │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │     Y-Axis Inversion &       │
 │   Chirality Transformation   │
 │   - Y_svg = Y_max - Y_cad    │
 │   - sweep_flag = 1 (CW)      │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │   Dynamic Stroke Scaling     │
 │   - default_stroke_width =   │
 │     max(0.1, 0.001*diagonal) │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │     SVG XML Serializer       │
 │   - Semantic <g> Layers      │
 │   - Non-scaling Stroke Flag  │
 │   - CSS Stylesheet Block     │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │    Optimized SVG Payload     │
 └──────────────────────────────┘
```

---

## 2. Mathematical Architecture & Coordinate Inversion

AutoCAD uses a Cartesian coordinate frame where $+Y$ points **up**. The W3C SVG specification defines screen space where $(0, 0)$ resides at the top-left and $+Y$ points **down**.

$$\vec{P}_{\text{cad}} = \begin{bmatrix} x \\ y \end{bmatrix} \implies \vec{P}_{\text{svg}} = \begin{bmatrix} x \\ Y_{\max} + Y_{\min} - y \end{bmatrix}$$

### 2.1 The Arc Chirality Inversion Problem & The Sweep Flag Fix
In CAD modelspace, circular arcs are defined mathematically with a counter-clockwise (CCW) sweep direction from start angle $\theta_s$ to end angle $\theta_e$.

When geometry undergoes a vertical reflection across the horizontal axis ($Y \mapsto -Y$), **the visual chirality of rotation inverts**:
$$\text{Counter-Clockwise (CCW)} \xrightarrow{\text{Y-Inversion}} \text{Clockwise (CW)}$$

An SVG elliptical arc command uses the syntax:
```xml
A rx ry x-axis-rotation large-arc-flag sweep-flag x y
```
* **`large-arc-flag`**: `1` if the angular span $\Delta\theta > 180^\circ$, else `0`.
* **`sweep-flag`**: `1` for clockwise (CW) arc sweep; `0` for counter-clockwise (CCW) sweep.

Prior to our audit, SVG compilers hardcoded `sweep_flag = 0` (CCW), assuming direct angle inheritance. Under SVG's inverted Y-axis, this caused arcs to swing "the long way around," flying outwards and ballooning outside the viewBox.

`cad-ir-to-svg` enforces the mathematically correct mapping:
```python
# Y-inversion turns a CAD CCW arc into a visual SVG CW arc
sweep_flag = 1
large_arc_flag = 1 if sweep_angle > 180.0 else 0

path_d = f"M {start_x:.3f},{start_y:.3f} A {r:.3f},{r:.3f} 0 {large_arc_flag} {sweep_flag} {end_x:.3f},{end_y:.3f}"
```

---

## 3. Dynamic Stroke Width Scaling Algorithm

In SVG rendering, if a drawing specifies an absolute stroke width in viewBox user units (e.g. `stroke-width="1"`):
* On small drawings (e.g. an aircraft part measuring $12\text{ mm}$ across), a 1-unit stroke is $1/12\text{th}$ of the entire drawing, creating massive black ink-bleeds.
* On large drawings (e.g. an airport masterplan measuring $45,000\text{ meters}$ across), a 1-unit stroke is $1/45,000\text{th}$ of the canvas, rendering the linework completely invisible.

### The Diagonal Scaling Equation
`cad-ir-to-svg` computes the spatial diagonal of the bounding box extents and dynamically scales the default stroke width:

$$\text{width} = X_{\max} - X_{\min}$$
$$\text{height} = Y_{\max} - Y_{\min}$$
$$\text{diagonal} = \sqrt{\text{width}^2 + \text{height}^2}$$
$$\text{default\_stroke\_width} = \max\left(0.1, \; 0.001 \times \text{diagonal}\right) \times \text{stroke\_scale}$$

Where `stroke_scale` is an optional multiplier provided by preset configurations or user overrides.

### Vector-Effect (`non-scaling-stroke`)
For interactive web viewers where users pan and zoom dynamically, `cad-ir-to-svg` can inject:
```xml
vector-effect="non-scaling-stroke"
```
This instructs browser SVG rasterization engines to render lines at a fixed screen-pixel thickness regardless of zoom depth.

---

## 4. Bounding Box & Outlier Pruning Architecture

Drafters frequently leave stray notes, scratch lines, or origin points at $(0, 0)$ hundreds of kilometers away from the actual building model. Simply taking the mathematical minimum and maximum coordinates results in massive letterboxing where the actual drawing shrinks to a tiny spec.

### 4.1 1D Coordinate Clustering (`find_primary_cluster_1d`)
`cad-ir-to-svg` analyzes the coordinate distribution along both axes. If a coordinate gap exceeds $5\times$ the median inter-entity distance, the isolated outlier is flagged for exclusion.

### 4.2 Strict Text Bounding Box Protection
During our audit, we discovered that standard clustering algorithms mistakenly classified legal notes and title blocks as outliers, clipping off crucial text in the generated SVG.

`cad-ir-to-svg` implements an **unconditional text preservation guard**:
* All `TEXT` and `MTEXT` insertion points and character bounding boxes are collected in a protected queue.
* After primary geometric clustering, the bounding box envelope is explicitly expanded to encompass all text entities:
  ```python
  for tx, ty in text_coords:
      box.expand(tx, ty)
  ```
  This guarantees that title blocks, drawing stamps, and dimensions are strictly protected from clipping.

---

## 5. Preset & Customization Architecture

### 5.1 Named SvgPreset Catalog

| Preset Name | Background | Default Stroke | Non-Scaling | Description & Best Use Case |
| :--- | :---: | :---: | :---: | :--- |
| **`web-interactive-light`** *(Default)* | `#FFFFFF` | `#1A1A1A` | `True` | Light background, dynamic strokes, semantic layer groups for interactive web viewers. |
| **`architectural-monochrome`** | `#FFFFFF` | `#000000` | `False` | Uniform black strokes with fixed scale widths for architectural web publication. |
| **`cad-dark-modelspace`** | `#1E1E1E` | `#FFFFFF` | `True` | Authentic AutoCAD dark theme with vibrant layer colors preserved. |
| **`fabrication-cnc-hairline`** | `None` (Transparent) | `#FF0000` | `False` | Ultra-fine $0.05\text{px}$ vector paths optimized for laser cutting and CNC plotters. |
| **`thumbnail-preview`** | `#F8F9FA` | `#2D3748` | `False` | Compact, lightweight SVG with low coordinate decimal precision for fast previews. |

---

### 5.2 Granular Customization Schema (`SvgOptions`)

```python
@dataclass
class SvgOptions:
    background_color: Optional[str] = None       # Hex color or None for transparent
    default_stroke_color: Optional[str] = None   # Fallback stroke hex
    default_stroke_width: Optional[float] = None # Base stroke weight
    non_scaling_stroke: Optional[bool] = None    # Inject vector-effect attribute
    group_by_layer: Optional[bool] = None        # Emit semantic <g> layer tags
    invert_y: Optional[bool] = None              # Perform Y-axis reflection (default True)
    padding_ratio: Optional[float] = None        # ViewBox margin fraction (e.g. 0.05 = 5%)
    target_space: Optional[str] = None           # 'Model' or specific paper layout
    include_dimensions: Optional[bool] = None    # Render dimension strings
    include_annotations: Optional[bool] = None   # Render TEXT/MTEXT labels
    color_mode: Optional[str] = None             # 'layer', 'monochrome', or 'entity'
    outlier_pruning: Optional[bool] = None       # Enable/disable outlier filtering
```

---

## 6. Public API & Usage Reference

### 6.1 Python SDK

```python
from cad_ir_to_svg import compile_ir_to_svg_string
from cad_ir_to_svg.config import SvgOptions

# 1. Compile with default preset (returns SVG XML string and telemetry report)
svg_xml, report = compile_ir_to_svg_string(
    ir_source="ir_data.json",
    preset="web-interactive-light"
)

# 2. Compile with custom overrides (Dark Cyberpunk Theme)
custom_options = SvgOptions(
    background_color="#121212",
    default_stroke_color="#00FFCC",
    padding_ratio=0.08,
    non_scaling_stroke=False
)

svg_cyberpunk, report = compile_ir_to_svg_string(
    ir_source=ir_dict,
    preset="web-interactive-light",
    options=custom_options
)

with open("output.svg", "w", encoding="utf-8") as f:
    f.write(svg_cyberpunk)
```

---

### 6.2 Command Line Interface (CLI)

```bash
# Compile to SVG file
python -m cad_ir_to_svg.cli input_ir.json -o output.svg

# Compile with dark modelspace preset
python -m cad_ir_to_svg.cli input_ir.json -o dark_model.svg --preset cad-dark-modelspace

# Custom stroke and transparent background
python -m cad_ir_to_svg.cli input_ir.json -o transparent.svg \
       --preset web-interactive-light \
       --background-color none \
       --default-stroke-color "#336699"
```
