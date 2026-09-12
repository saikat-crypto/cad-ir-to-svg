"""
Unit tests for 2D geometry, bounding box, affine matrices, and SVG arc mapping.
"""

import math
import pytest
from cad_ir_to_svg.geometry import (
    BoundingBox,
    AffineMatrix2D,
    find_primary_cluster_1d,
    is_valid_point,
    is_finite_number,
    calculate_arc_endpoints_and_sweep,
    cad_arc_to_svg_path,
)


def test_is_valid_point_and_finite_number():
    assert is_finite_number(0.0) is True
    assert is_finite_number(-123.456) is True
    assert is_finite_number(1e9) is True
    assert is_finite_number(float("nan")) is False
    assert is_finite_number(float("inf")) is False
    assert is_finite_number(float("-inf")) is False
    assert is_finite_number("123") is False
    assert is_finite_number(True) is False
    assert is_finite_number(None) is False

    assert is_valid_point([10.0, 20.0]) is True
    assert is_valid_point((0, 0)) is True
    assert is_valid_point([10.0, float("nan")]) is False
    assert is_valid_point([float("inf"), 20.0]) is False
    assert is_valid_point([10.0]) is False
    assert is_valid_point([]) is False
    assert is_valid_point(None) is False


def test_bounding_box_operations():
    box = BoundingBox()
    assert box.is_valid is False
    assert box.width == 0.0
    assert box.height == 0.0
    assert box.center == (0.0, 0.0)

    box.expand(10.0, 20.0)
    box.expand(30.0, 40.0)
    assert box.is_valid is True
    assert box.min_x == 10.0
    assert box.min_y == 20.0
    assert box.max_x == 30.0
    assert box.max_y == 40.0
    assert box.width == 20.0
    assert box.height == 20.0
    assert box.center == (20.0, 30.0)

    # Padding
    padded = box.with_padding(0.1)  # 10% of 20 = 2.0 pad
    assert padded.min_x == 8.0
    assert padded.min_y == 18.0
    assert padded.max_x == 32.0
    assert padded.max_y == 42.0


def test_find_primary_cluster_pruning():
    # 100 points around [0, 100] and 2 distant outlier points at 10,000
    points = [float(i) for i in range(101)] + [10000.0, 10005.0]
    p_min, p_max = find_primary_cluster_1d(points)
    assert p_min == 0.0
    assert p_max == 100.0


def test_affine_matrix_operations():
    # Identity
    ident = AffineMatrix2D.identity()
    assert ident.determinant == 1.0
    assert ident.is_singular is False
    assert ident.transform_point(10.0, 20.0) == (10.0, 20.0)

    # Translation
    t = AffineMatrix2D.translation(5.0, -3.0)
    assert t.transform_point(10.0, 20.0) == (15.0, 17.0)

    # Rotation 90 degrees
    r = AffineMatrix2D.rotation(90.0)
    px, py = r.transform_point(1.0, 0.0)
    assert abs(px - 0.0) < 1e-6
    assert abs(py - 1.0) < 1e-6

    # Scale
    s = AffineMatrix2D.scale(2.0, 3.0)
    assert s.transform_point(4.0, 5.0) == (8.0, 15.0)
    assert s.determinant == 6.0

    # Singularity
    singular = AffineMatrix2D.scale(0.0, 1.0)
    assert singular.is_singular is True

    # CAD INSERT composition
    m = AffineMatrix2D.from_cad_insert(pos=[100.0, 200.0], rotation_deg=0.0, scale=[2.0, 2.0], base_point=[10.0, 10.0])
    # Point at (10, 10) should translate to base (0, 0), scale to (0, 0), and translate to pos (100, 200)
    assert m.transform_point(10.0, 10.0) == (100.0, 200.0)


def test_cad_to_svg_arc_math():
    # Arc from 0 to 90 degrees, radius 10, center (0, 0)
    def identity_transform(x, y):
        return (x, y)

    path_d = cad_arc_to_svg_path(0.0, 0.0, 10.0, 0.0, 90.0, identity_transform)
    assert path_d.startswith("M 10.000 0.000 A 10.000 10.000 0 0 0 0.000 10.000")

    # Arc with sweep > 180 (e.g. 0 to 270) -> large_arc_flag should be 1
    path_large = cad_arc_to_svg_path(0.0, 0.0, 10.0, 0.0, 270.0, identity_transform)
    assert "A 10.000 10.000 0 1 0" in path_large

    # Full 360 degree sweep circle
    path_circle = cad_arc_to_svg_path(0.0, 0.0, 10.0, 0.0, 360.0, identity_transform)
    assert path_circle.count("A 10.000 10.000") == 2  # Two semicircles
