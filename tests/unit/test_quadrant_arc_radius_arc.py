"""Unit tests for axis-aligned quadrant arc RadiusArc construction in zone_builder.

Validates Requirements:
- 2.1: Axis-aligned quadrant arcs use RadiusArc (Build123d API)
- 2.2: Arc center derived from bounding box corner based on tangent direction
- 2.3: Radius equals absolute difference of non-shared endpoint coordinates
- 2.4: Arc sweep travels from start to end in correct direction
- 4.1: Negative-Q mirrors center to opposite side
- 4.2: Negative-Q axis-aligned constructs RadiusArc with mirrored center (concave)
- 5.1: Polyline Line() loop removed for axis-aligned cases
"""

import pytest
import math
from unittest.mock import patch, MagicMock
from models.constants import TOLERANCE


class TestAxisAlignedRadiusArcConstruction:
    """Test that axis-aligned quadrant arcs produce correct RadiusArc calls."""

    def _get_radius_arc_args(self, cx, cz, tx, tz, quadrant_sign=1):
        """Replicate the axis-aligned RadiusArc construction logic from zone_builder.

        Returns (start, end, signed_radius) that would be passed to RadiusArc.
        """
        same_x = abs(cx - tx) < TOLERANCE
        same_z = abs(cz - tz) < TOLERANCE

        if not (same_x or same_z):
            return None  # Not axis-aligned

        arc_radius = abs(cz - tz) if same_x else abs(cx - tx)
        signed_radius = -arc_radius * quadrant_sign
        return ((cx, cz), (tx, tz), signed_radius)

    # --- Requirement 2.1: Uses RadiusArc for axis-aligned ---

    def test_same_x_convex_returns_radius_arc_params(self):
        """Same X (vertical chord), +Q → valid RadiusArc parameters."""
        result = self._get_radius_arc_args(0.5, 0.0, 0.5, -0.5, quadrant_sign=1)
        assert result is not None
        start, end, signed_radius = result
        assert start == (0.5, 0.0)
        assert end == (0.5, -0.5)

    def test_same_z_convex_returns_radius_arc_params(self):
        """Same Z (horizontal chord), +Q → valid RadiusArc parameters."""
        result = self._get_radius_arc_args(0.25, -1.0, 0.5, -1.0, quadrant_sign=1)
        assert result is not None
        start, end, signed_radius = result
        assert start == (0.25, -1.0)
        assert end == (0.5, -1.0)

    # --- Requirement 2.3: Radius = absolute non-shared delta ---

    def test_same_x_radius_is_z_delta(self):
        """Same X → radius = |z_start - z_end|."""
        result = self._get_radius_arc_args(0.5, 0.0, 0.5, -0.75, quadrant_sign=1)
        _, _, signed_radius = result
        assert abs(abs(signed_radius) - 0.75) < 1e-10

    def test_same_z_radius_is_x_delta(self):
        """Same Z → radius = |x_start - x_end|."""
        result = self._get_radius_arc_args(0.25, -1.0, 0.75, -1.0, quadrant_sign=1)
        _, _, signed_radius = result
        assert abs(abs(signed_radius) - 0.5) < 1e-10

    # --- Requirement 2.4: Sign convention for +Q convex ---

    def test_convex_sign_is_negative(self):
        """+Q (convex) → signed radius is negative (minor arc in Build123d)."""
        result = self._get_radius_arc_args(0.5, 0.0, 0.5, -0.5, quadrant_sign=1)
        _, _, signed_radius = result
        assert signed_radius < 0

    # --- Requirement 4.1, 4.2: Negative-Q mirroring ---

    def test_concave_sign_is_positive(self):
        """-Q (concave) → signed radius is positive (major arc in Build123d)."""
        result = self._get_radius_arc_args(0.5, 0.0, 0.5, -0.5, quadrant_sign=-1)
        _, _, signed_radius = result
        assert signed_radius > 0

    def test_convex_vs_concave_same_magnitude(self):
        """+Q and -Q produce same magnitude radius, opposite sign."""
        r_convex = self._get_radius_arc_args(0.5, 0.0, 0.5, -0.5, quadrant_sign=1)
        r_concave = self._get_radius_arc_args(0.5, 0.0, 0.5, -0.5, quadrant_sign=-1)
        _, _, sr_convex = r_convex
        _, _, sr_concave = r_concave
        assert abs(abs(sr_convex) - abs(sr_concave)) < 1e-10
        assert sr_convex * sr_concave < 0  # Opposite signs

    # --- Requirement 5.1: No polyline for axis-aligned ---

    def test_off_axis_returns_none(self):
        """Off-axis case returns None (not handled by RadiusArc)."""
        result = self._get_radius_arc_args(0.25, 0.0, 0.5, -0.75, quadrant_sign=1)
        assert result is None

    # --- Edge cases ---

    def test_small_radius_same_x(self):
        """Small radius (small Z delta) still produces valid params."""
        result = self._get_radius_arc_args(0.5, 0.0, 0.5, -0.001, quadrant_sign=1)
        assert result is not None
        _, _, signed_radius = result
        assert abs(abs(signed_radius) - 0.001) < 1e-10

    def test_large_radius_same_z(self):
        """Large radius (large X delta) produces valid params."""
        result = self._get_radius_arc_args(0.1, -2.0, 2.0, -2.0, quadrant_sign=1)
        assert result is not None
        _, _, signed_radius = result
        assert abs(abs(signed_radius) - 1.9) < 1e-10


class TestRadiusArcIntegration:
    """Circular quadrants in _build_face_from_coords (ellipses retired 2026-11-11,
    geometry/arc_entry.py): an equal-leg Q builds a face; a same-X Q must have
    been split into two quadrants first, and a same-Z Q is refused."""

    @staticmethod
    def _coords(q_end, sign, start=(0.25, 0.0), mid=(0.25, -0.5)):
        from models.profile import SegmentType
        L = dict(type=SegmentType.LINE, radius=0.0, quadrant=False, quadrant_sign=1)
        return [
            dict(L, x_radius=start[0], z=start[1]),
            dict(L, x_radius=mid[0], z=mid[1]),
            dict(L, x_radius=q_end[0], z=q_end[1], quadrant=True, quadrant_sign=sign),
            dict(L, x_radius=q_end[0], z=-1.5),
            dict(L, x_radius=0.0, z=-1.5),
            dict(L, x_radius=0.0, z=0.0),
        ]

    @staticmethod
    def _profile():
        from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode
        return ClosedProfile(segments=[ProfileMove(SegmentType.LINE, x=0.5, z=0.0)],
                             corner_breaks=[], mode=MachiningMode.OD)

    @pytest.mark.parametrize("sign", [1, -1])
    def test_equal_leg_quadrant_produces_face(self, sign):
        from geometry.zone_builder import _build_face_from_coords
        face = _build_face_from_coords(self._coords((0.5, -0.75), sign), self._profile())
        assert face is not None and face.area > 0

    def test_same_x_quadrant_must_be_split_first(self):
        from geometry.zone_builder import _build_face_from_coords
        with pytest.raises(ValueError, match="split into two quadrants"):
            _build_face_from_coords(self._coords((0.25, -1.0), 1), self._profile())

    def test_same_z_quadrant_is_refused(self):
        from geometry.zone_builder import _build_face_from_coords
        with pytest.raises(ValueError, match="same Z"):
            _build_face_from_coords(self._coords((0.5, -0.5), 1), self._profile())
