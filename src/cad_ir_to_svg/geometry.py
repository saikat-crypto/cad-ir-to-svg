"""
2D Geometry, Spatial Bounding Box, Affine Transforms, and Outlier Pruning for cad-ir-to-svg.
Implements the La Vinci geometric invariants: float finiteness, safe bounding boxes,
affine matrix singularity detection, and exact CAD-to-SVG arc decomposition.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Sequence, Any


def is_finite_number(val: Any) -> bool:
    """Checks if a value is a finite number (rejects None, NaN, Inf, bool, strings)."""
    if val is None or isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    return math.isfinite(float(val))


def is_valid_point(pt: Any) -> bool:
    """Checks if a point is a valid 2D sequence of finite floats [x, y]."""
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        return False
    return is_finite_number(pt[0]) and is_finite_number(pt[1])


@dataclass
class BoundingBox:
    """Represents a 2D axis-aligned bounding box with float-safe operations."""
    min_x: float = float("inf")
    min_y: float = float("inf")
    max_x: float = float("-inf")
    max_y: float = float("-inf")

    @property
    def is_valid(self) -> bool:
        return (
            math.isfinite(self.min_x)
            and math.isfinite(self.min_y)
            and math.isfinite(self.max_x)
            and math.isfinite(self.max_y)
            and self.min_x <= self.max_x
            and self.min_y <= self.max_y
        )

    @property
    def width(self) -> float:
        return max(0.0, self.max_x - self.min_x) if self.is_valid else 0.0

    @property
    def height(self) -> float:
        return max(0.0, self.max_y - self.min_y) if self.is_valid else 0.0

    @property
    def center(self) -> Tuple[float, float]:
        if not self.is_valid:
            return (0.0, 0.0)
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def expand(self, x: float, y: float) -> None:
        if is_finite_number(x) and is_finite_number(y):
            if x < self.min_x:
                self.min_x = float(x)
            if y < self.min_y:
                self.min_y = float(y)
            if x > self.max_x:
                self.max_x = float(x)
            if y > self.max_y:
                self.max_y = float(y)

    def expand_box(self, other: 'BoundingBox') -> None:
        if other.is_valid:
            self.expand(other.min_x, other.min_y)
            self.expand(other.max_x, other.max_y)

    def with_padding(self, ratio: float = 0.05, min_pad: float = 1.0) -> 'BoundingBox':
        """Returns a padded bounding box with a margin ratio (e.g. 5% padding)."""
        if not self.is_valid:
            return BoundingBox(0.0, 0.0, 100.0, 100.0)

        w = self.width
        h = self.height
        pad_x = max(w * ratio, min_pad if w == 0 else 0.0)
        pad_y = max(h * ratio, min_pad if h == 0 else 0.0)
        pad = max(pad_x, pad_y)

        return BoundingBox(
            min_x=self.min_x - pad,
            min_y=self.min_y - pad,
            max_x=self.max_x + pad,
            max_y=self.max_y + pad,
        )


def find_primary_cluster_1d(
    coords: Sequence[float],
    min_gap_ratio: float = 0.10,
    max_outlier_ratio: float = 0.02,
) -> Tuple[float, float]:
    """
    Identifies the primary cluster of coordinates along 1D axis using sorted gap analysis.
    Safely prunes isolated scratch geometry or distant elevation markers without clipping
    multi-view floorplans, schedules, or architectural elevations.
    """
    finite_coords = sorted(c for c in coords if is_finite_number(c))
    if not finite_coords:
        return (0.0, 0.0)
    if len(finite_coords) <= 10:
        return (finite_coords[0], finite_coords[-1])

    n = len(finite_coords)
    total_span = finite_coords[-1] - finite_coords[0]
    if total_span <= 1e-6:
        return (finite_coords[0], finite_coords[-1])

    best_start = 0
    best_end = n - 1

    # Check for large gaps from the left
    for i in range(n - 1):
        gap = finite_coords[i + 1] - finite_coords[i]
        left_count = i + 1
        if gap > total_span * min_gap_ratio and (left_count / n) <= max_outlier_ratio:
            best_start = i + 1
        elif (left_count / n) > max_outlier_ratio:
            break

    # Check for large gaps from the right
    for i in range(n - 1, 0, -1):
        gap = finite_coords[i] - finite_coords[i - 1]
        right_count = n - i
        if gap > total_span * min_gap_ratio and (right_count / n) <= max_outlier_ratio:
            best_end = i - 1
        elif (right_count / n) > max_outlier_ratio:
            break

    if best_start <= best_end:
        return (finite_coords[best_start], finite_coords[best_end])
    return (finite_coords[0], finite_coords[-1])


@dataclass(frozen=True)
class AffineMatrix2D:
    """
    2D Affine transformation matrix:
    [ a  c  tx ]
    [ b  d  ty ]
    [ 0  0  1  ]
    """
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    tx: float = 0.0
    ty: float = 0.0

    @classmethod
    def identity(cls) -> 'AffineMatrix2D':
        return cls(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    @classmethod
    def translation(cls, dx: float, dy: float) -> 'AffineMatrix2D':
        return cls(1.0, 0.0, 0.0, 1.0, float(dx), float(dy))

    @classmethod
    def rotation(cls, angle_deg: float) -> 'AffineMatrix2D':
        rad = math.radians(float(angle_deg))
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        return cls(cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)

    @classmethod
    def scale(cls, sx: float, sy: float) -> 'AffineMatrix2D':
        return cls(float(sx), 0.0, 0.0, float(sy), 0.0, 0.0)

    @property
    def determinant(self) -> float:
        det = self.a * self.d - self.b * self.c
        return det if math.isfinite(det) else 0.0

    @property
    def is_singular(self) -> bool:
        det = self.determinant
        return not math.isfinite(det) or abs(det) < 1e-12

    def multiply(self, other: 'AffineMatrix2D') -> 'AffineMatrix2D':
        """Multiplies self * other."""
        return AffineMatrix2D(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            tx=self.a * other.tx + self.c * other.ty + self.tx,
            ty=self.b * other.tx + self.d * other.ty + self.ty,
        )

    def transform_point(self, x: float, y: float) -> Tuple[float, float]:
        """Applies transformation to 2D coordinate point."""
        if not is_finite_number(x) or not is_finite_number(y):
            return (0.0, 0.0)
        px = self.a * x + self.c * y + self.tx
        py = self.b * x + self.d * y + self.ty
        return (px, py)

    @classmethod
    def from_cad_insert(
        cls,
        pos: Sequence[float],
        rotation_deg: float = 0.0,
        scale: Optional[Sequence[float]] = None,
        base_point: Optional[Sequence[float]] = None,
    ) -> 'AffineMatrix2D':
        """
        Constructs composite affine matrix for AutoCAD INSERT component instance:
        M = Translation(pos) * Rotation(rot) * Scale(s) * Translation(-base_point)
        """
        # Guard against non-finite scale or position
        if scale is not None:
            if not all(is_finite_number(s) for s in scale):
                return cls(a=0.0, b=0.0, c=0.0, d=0.0, tx=0.0, ty=0.0)

        if pos is not None:
            if not all(is_finite_number(p) for p in pos):
                return cls(a=0.0, b=0.0, c=0.0, d=0.0, tx=0.0, ty=0.0)

        sx = float(scale[0]) if scale and len(scale) >= 1 else 1.0
        sy = float(scale[1]) if scale and len(scale) >= 2 else sx
        px = float(pos[0]) if pos and len(pos) >= 1 else 0.0
        py = float(pos[1]) if pos and len(pos) >= 2 else 0.0
        rot = float(rotation_deg) if is_finite_number(rotation_deg) else 0.0

        bx = float(base_point[0]) if base_point and len(base_point) >= 1 and is_finite_number(base_point[0]) else 0.0
        by = float(base_point[1]) if base_point and len(base_point) >= 2 and is_finite_number(base_point[1]) else 0.0

        # Translation(-base_point)
        m = cls.translation(-bx, -by)
        # Scale(sx, sy)
        m = cls.scale(sx, sy).multiply(m)
        # Rotation(rot)
        if abs(rot) > 1e-6:
            m = cls.rotation(rot).multiply(m)
        # Translation(pos)
        m = cls.translation(px, py).multiply(m)
        return m


def calculate_arc_endpoints_and_sweep(
    cx: float,
    cy: float,
    r: float,
    start_deg: float,
    end_deg: float,
) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """
    Computes start point, end point, and sweep angle (in degrees) for a CAD arc.
    Sweep is always positive (counter-clockwise in CAD world space).
    """
    start_rad = math.radians(start_deg)
    end_rad = math.radians(end_deg)

    p1 = (cx + r * math.cos(start_rad), cy + r * math.sin(start_rad))
    p2 = (cx + r * math.cos(end_rad), cy + r * math.sin(end_rad))

    sweep = (end_deg - start_deg) % 360.0
    if abs(sweep) < 1e-9 and abs(end_deg - start_deg) > 1e-6:
        sweep = 360.0

    return (p1, p2, sweep)


def cad_arc_to_svg_path(
    cx: float,
    cy: float,
    r: float,
    start_deg: float,
    end_deg: float,
    y_transform_fn,
) -> str:
    """
    Converts a CAD circular arc into an SVG path 'd' string using the native 'A' (elliptical arc) operator.
    Properly handles Y-inversion where CAD CCW sweep becomes SVG CW sweep.
    y_transform_fn: callable(x, y) -> (svg_x, svg_y)
    """
    if not is_finite_number(r) or r <= 0:
        return ""

    # Sweep angle in degrees
    sweep = (end_deg - start_deg) % 360.0
    if abs(sweep) < 1e-9 and abs(end_deg - start_deg) > 1e-6:
        sweep = 360.0

    if sweep < 1e-6:
        return ""

    # Full circle case: SVG arc command cannot render 360 degrees with a single 'A' command
    # because start and end points coincide. We split into two 180-degree arcs.
    if abs(sweep - 360.0) < 1e-4:
        p1 = (cx + r, cy)
        p2 = (cx - r, cy)
        sp1 = y_transform_fn(p1[0], p1[1])
        sp2 = y_transform_fn(p2[0], p2[1])
        # Two 180-degree semicircles
        return (
            f"M {sp1[0]:.3f} {sp1[1]:.3f} "
            f"A {r:.3f} {r:.3f} 0 0 0 {sp2[0]:.3f} {sp2[1]:.3f} "
            f"A {r:.3f} {r:.3f} 0 0 0 {sp1[0]:.3f} {sp1[1]:.3f}"
        )

    # Standard partial arc
    p1, p2, _ = calculate_arc_endpoints_and_sweep(cx, cy, r, start_deg, end_deg)
    sp1 = y_transform_fn(p1[0], p1[1])
    sp2 = y_transform_fn(p2[0], p2[1])

    large_arc_flag = 1 if sweep > 180.0 else 0

    # Inverted Y (CAD +Y up to SVG +Y down):
    # Rotating from +X to +Y_cad (CCW) rotates from +X to -Y_svg (CCW in screen space).
    # In SVG path syntax: sweep-flag=0 is CCW, sweep-flag=1 is CW.
    sweep_flag = 0

    return (
        f"M {sp1[0]:.3f} {sp1[1]:.3f} "
        f"A {r:.3f} {r:.3f} 0 {large_arc_flag} {sweep_flag} {sp2[0]:.3f} {sp2[1]:.3f}"
    )
