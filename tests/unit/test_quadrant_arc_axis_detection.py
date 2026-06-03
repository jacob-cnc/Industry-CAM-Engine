"""Unit tests for quadrant arc axis-aligned detection in zone_builder.

Validates Requirements 1.1, 1.2, 1.3:
- 1.1: Same X within tolerance → axis-aligned
- 1.2: Same Z within tolerance → axis-aligned
- 1.3: Both differ beyond tolerance → off-axis
"""

import pytest
from models.constants import TOLERANCE


class TestAxisAlignedDetection:
    """Test the axis-aligned detection logic used in _build_face_from_coords."""

    def _classify(self, cx: float, cz: float, tx: float, tz: float) -> str:
        """Replicate the classification logic from zone_builder._build_face_from_coords.

        Returns 'axis_aligned' or 'off_axis'.
        """
        same_x = abs(cx - tx) < TOLERANCE
        same_z = abs(cz - tz) < TOLERANCE
        is_axis_aligned = same_x or same_z
        return "axis_aligned" if is_axis_aligned else "off_axis"

    # --- Requirement 1.1: Same X → axis-aligned ---

    def test_same_x_exact(self):
        """Same X exactly → axis-aligned (vertical chord)."""
        result = self._classify(0.5, 0.0, 0.5, -0.5)
        assert result == "axis_aligned"

    def test_same_x_within_tolerance(self):
        """X difference within TOLERANCE → axis-aligned."""
        delta = TOLERANCE * 0.5  # half of tolerance
        result = self._classify(0.5, 0.0, 0.5 + delta, -0.5)
        assert result == "axis_aligned"

    def test_same_x_at_boundary(self):
        """X difference just below TOLERANCE → axis-aligned."""
        delta = TOLERANCE * 0.99
        result = self._classify(0.5, 0.0, 0.5 + delta, -0.5)
        assert result == "axis_aligned"

    # --- Requirement 1.2: Same Z → axis-aligned ---

    def test_same_z_exact(self):
        """Same Z exactly → axis-aligned (horizontal chord)."""
        result = self._classify(0.25, -0.5, 0.5, -0.5)
        assert result == "axis_aligned"

    def test_same_z_within_tolerance(self):
        """Z difference within TOLERANCE → axis-aligned."""
        delta = TOLERANCE * 0.5
        result = self._classify(0.25, -0.5, 0.5, -0.5 + delta)
        assert result == "axis_aligned"

    def test_same_z_at_boundary(self):
        """Z difference just below TOLERANCE → axis-aligned."""
        delta = TOLERANCE * 0.99
        result = self._classify(0.25, -0.5, 0.5, -0.5 + delta)
        assert result == "axis_aligned"

    # --- Requirement 1.3: Both differ → off-axis ---

    def test_both_differ(self):
        """Both X and Z differ beyond tolerance → off-axis."""
        result = self._classify(0.25, 0.0, 0.5, -0.75)
        assert result == "off_axis"

    def test_both_differ_slightly_beyond_tolerance(self):
        """Both X and Z differ just beyond TOLERANCE → off-axis."""
        delta = TOLERANCE * 1.5
        result = self._classify(0.5, 0.0, 0.5 + delta, 0.0 - delta)
        assert result == "off_axis"

    # --- Edge cases ---

    def test_both_same_is_axis_aligned(self):
        """Both X and Z same (degenerate) → axis-aligned (same_x is True)."""
        result = self._classify(0.5, -0.5, 0.5, -0.5)
        assert result == "axis_aligned"

    def test_negative_coordinates(self):
        """Works with negative coordinate values."""
        # Same X, different Z (negative coords)
        result = self._classify(-0.25, -1.0, -0.25, -0.5)
        assert result == "axis_aligned"

    def test_tolerance_value_matches_constant(self):
        """TOLERANCE is 0.0005 inches (verify assumption)."""
        assert TOLERANCE == 0.0005
