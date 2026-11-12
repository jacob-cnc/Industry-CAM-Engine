"""Finish planner edges: lines and circular arcs only (2026-11-12).

Profiles are lines and circular arcs (ellipses retired 2026-11-11), and so are
their outlines and offsets: over the regression corpus the zone query made
1896 LINE and 443 ARC edges and no CURVE edge. The curve-fitting path that
approximated non-circular edges with fitted arcs (and the fallback that cut a
CURVE edge without kernel geometry as a straight line) was removed; such an
edge - or an ARC without a centre - is now refused instead of cut wrongly.
"""

import pytest

from planners.finish_planner import FinishPlanner
from models.moves import MoveType
from models.params import FinishingParams


@pytest.fixture
def planner():
    return FinishPlanner()


@pytest.fixture
def finishing_params():
    return FinishingParams(feed=0.005)


class TestFinishEdges:

    def test_line_and_arc_edges_unchanged(self, planner, finishing_params):
        """LINE and ARC edges should still work as before."""
        from geometry.zone_query import EdgeData

        edges = [
            EdgeData(
                edge_type="LINE",
                start=(2.0, 0.0),
                end=(2.0, -1.0),
            ),
            EdgeData(
                edge_type="ARC",
                start=(2.0, -1.0),
                end=(1.5, -1.5),
                center=(2.0, -1.5),
                radius=0.5,
            ),
        ]

        moves = planner._moves_from_edges(edges, finishing_params)

        # First move: feed to first start
        assert moves[0].move_type == MoveType.FEED
        assert moves[0].x == 2.0
        assert moves[0].z == 0.0
        # Second: line move
        assert moves[1].move_type == MoveType.FEED
        assert moves[1].x == 2.0
        assert moves[1].z == -1.0
        # Third: arc move
        assert moves[2].move_type in (MoveType.ARC_CW, MoveType.ARC_CCW)
        assert moves[2].x == 1.5
        assert moves[2].z == -1.5


    @pytest.mark.parametrize("ocp_edge", [None, object()])
    def test_curve_edge_is_refused(self, planner, finishing_params, ocp_edge):
        from geometry.zone_query import EdgeData
        edges = [EdgeData(edge_type="CURVE", start=(2.0, 0.0), end=(2.0, -1.0), ocp_edge=ocp_edge)]
        with pytest.raises(ValueError, match="not a line"):
            planner._moves_from_edges(edges, finishing_params)

    def test_arc_without_centre_is_refused(self, planner, finishing_params):
        from geometry.zone_query import EdgeData
        edges = [EdgeData(edge_type="ARC", start=(2.0, 0.0), end=(1.5, -0.5), center=None, radius=0.5)]
        with pytest.raises(ValueError, match="not a line"):
            planner._moves_from_edges(edges, finishing_params)


class TestEdgeDataCurveType:
    """Tests for zone_query EdgeData with CURVE edge_type."""

    def test_edge_data_curve_stores_ocp_edge(self):
        """CURVE EdgeData should store the ocp_edge reference."""
        from geometry.zone_query import EdgeData

        mock_edge = object()  # Placeholder
        ed = EdgeData(
            edge_type="CURVE",
            start=(2.0, 0.0),
            end=(1.0, -1.0),
            ocp_edge=mock_edge,
        )
        assert ed.edge_type == "CURVE"
        assert ed.ocp_edge is mock_edge
        assert ed.center is None
        assert ed.radius == 0.0

    def test_edge_data_backward_compatible(self):
        """Existing LINE/ARC EdgeData should work without ocp_edge."""
        from geometry.zone_query import EdgeData

        line = EdgeData(edge_type="LINE", start=(2.0, 0.0), end=(2.0, -1.0))
        assert line.ocp_edge is None

        arc = EdgeData(
            edge_type="ARC", start=(2.0, -1.0), end=(1.5, -1.5),
            center=(2.0, -1.5), radius=0.5
        )
        assert arc.ocp_edge is None
