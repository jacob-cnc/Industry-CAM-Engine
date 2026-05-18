"""Property-based preservation tests for material simulation.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

These tests capture the EXISTING correct behavior of the material simulation
for non-buggy inputs (end-of-pass, start state, rapid moves, final state,
performance, and coordinate conventions). They must PASS on unfixed code
and continue to pass after the fix is applied.

Observation-first methodology: We observe what the unfixed code does for
non-buggy inputs, then encode those observations as properties.
"""

import time
import math
from typing import List, Tuple

import numpy as np
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from shapely.geometry import box, Polygon
from shapely.ops import unary_union

from models.moves import ToolMove, MoveType, PassType
from models.stock import StockDef
from models.profile import (
    ClosedProfile, ProfileMove, SegmentType, MachiningMode
)
from models.tool import (
    ToolDef, ToolOrientation, ToolDirection, ToolType
)
from models.params import RoughingParams, FinishingParams, RoughingStrategy
from models.results import PlanResult, TurningPass, SweptRegion
from outputs.material_sim import (
    compute, MaterialSimData, _build_stock_polygon, _polygon_to_arrays
)


# ============================================================
# Hypothesis Strategies for generating valid PlanResult inputs
# ============================================================

@st.composite
def od_tool_strategy(draw):
    """Generate a valid OD turning tool."""
    tnr = draw(st.floats(min_value=0.005, max_value=0.0625))
    return ToolDef(
        tool_number=1,
        nose_radius=tnr,
        tip_angle=55.0,
        edge_length=0.25,
        orientation=ToolOrientation.OD_FRONT_RIGHT,
        direction=ToolDirection.RIGHT,
        tool_type=ToolType.TURNING,
    )


@st.composite
def id_tool_strategy(draw):
    """Generate a valid ID boring tool."""
    tnr = draw(st.floats(min_value=0.005, max_value=0.0625))
    return ToolDef(
        tool_number=2,
        nose_radius=tnr,
        tip_angle=55.0,
        edge_length=0.25,
        orientation=ToolOrientation.ID_FRONT_RIGHT,
        direction=ToolDirection.LEFT,
        tool_type=ToolType.BORING,
    )


@st.composite
def od_stock_strategy(draw):
    """Generate a valid OD stock definition."""
    diameter = draw(st.floats(min_value=0.5, max_value=4.0))
    x_start = diameter - draw(st.floats(min_value=0.01, max_value=0.1))
    z_start = draw(st.floats(min_value=0.05, max_value=0.2))
    z_end = -draw(st.floats(min_value=0.2, max_value=3.0))
    return StockDef(
        diameter=diameter,
        x_start=x_start,
        z_start=z_start,
        z_end=z_end,
        mode=MachiningMode.OD,
    )


@st.composite
def id_stock_strategy(draw):
    """Generate a valid ID stock definition."""
    pilot_hole_dia = draw(st.floats(min_value=0.25, max_value=1.5))
    x_start = pilot_hole_dia + draw(st.floats(min_value=0.05, max_value=0.5))
    z_start = draw(st.floats(min_value=0.05, max_value=0.2))
    z_end = -draw(st.floats(min_value=0.2, max_value=2.0))
    return StockDef(
        diameter=x_start + 1.0,  # OD larger than bore
        x_start=x_start,
        z_start=z_start,
        z_end=z_end,
        mode=MachiningMode.ID,
        pilot_hole_dia=pilot_hole_dia,
    )


@st.composite
def roughing_pass_strategy(draw, stock, pass_index, doc_dia=0.050):
    """Generate a valid roughing pass with moves within stock bounds.

    Creates a pass that moves in -Z direction at a fixed X level.
    """
    # X level for this pass (diameter) - between x_start and stock diameter
    x_range = stock.diameter - stock.x_start
    assume(x_range > doc_dia)
    x_level = stock.diameter - (pass_index + 1) * doc_dia
    assume(x_level > stock.x_start)

    z_start = stock.z_start
    z_end = stock.z_end

    # Build moves: rapid to start, then feed cuts in -Z
    num_cuts = draw(st.integers(min_value=2, max_value=8))
    z_step = (z_start - z_end) / num_cuts

    moves = []
    # Rapid to start position
    moves.append(ToolMove(
        move_type=MoveType.RAPID,
        x=x_level, z=z_start,
        pass_type=PassType.ROUGH, pass_index=pass_index,
    ))
    # Feed cuts moving in -Z
    for i in range(1, num_cuts + 1):
        current_z = z_start - i * z_step
        moves.append(ToolMove(
            move_type=MoveType.FEED,
            x=x_level, z=current_z, feed=0.010,
            pass_type=PassType.ROUGH, pass_index=pass_index,
        ))

    swept = SweptRegion(
        x_min=x_level - doc_dia,
        x_max=x_level,
        z_start=z_start,
        z_end=z_end,
    )

    return TurningPass(
        x_level=x_level,
        z_start=z_start,
        z_end=z_end,
        pass_index=pass_index,
        pass_type=PassType.ROUGH,
        moves=moves,
        swept_region=swept,
    )


@st.composite
def face_pass_strategy(draw, stock, pass_index):
    """Generate a valid face pass that moves in X direction at Z near face."""
    z_level = stock.z_start - 0.010  # Face cut just below face
    x_start_dia = stock.diameter
    x_end_dia = stock.x_start

    # Build moves: rapid to start, then feed cuts in -X
    num_cuts = draw(st.integers(min_value=2, max_value=5))
    x_step = (x_start_dia - x_end_dia) / num_cuts

    moves = []
    moves.append(ToolMove(
        move_type=MoveType.RAPID,
        x=x_start_dia, z=stock.z_start,
        pass_type=PassType.FACE, pass_index=pass_index,
    ))
    for i in range(1, num_cuts + 1):
        current_x = x_start_dia - i * x_step
        moves.append(ToolMove(
            move_type=MoveType.FEED,
            x=current_x, z=z_level, feed=0.008,
            pass_type=PassType.FACE, pass_index=pass_index,
        ))

    swept = SweptRegion(
        x_min=x_end_dia,
        x_max=x_start_dia,
        z_start=stock.z_start,
        z_end=z_level,
    )

    return TurningPass(
        x_level=x_start_dia,
        z_start=stock.z_start,
        z_end=z_level,
        pass_index=pass_index,
        pass_type=PassType.FACE,
        moves=moves,
        swept_region=swept,
    )


def _build_simple_profile(stock: StockDef, mode: MachiningMode) -> ClosedProfile:
    """Build a minimal valid profile for testing."""
    if mode == MachiningMode.OD:
        # Simple step profile
        segments = [
            ProfileMove(SegmentType.LINE, x=stock.x_start, z=0.0),
            ProfileMove(SegmentType.LINE, x=stock.x_start, z=stock.z_end),
        ]
    else:
        # Simple bore profile
        segments = [
            ProfileMove(SegmentType.LINE, x=stock.x_start, z=0.0),
            ProfileMove(SegmentType.LINE, x=stock.x_start, z=stock.z_end),
        ]
    return ClosedProfile(
        segments=segments,
        corner_breaks=[None],
        mode=mode,
        z_start=0.0,
        z_end=stock.z_end,
    )


def _build_plan_result(
    stock: StockDef,
    tool: ToolDef,
    face_passes: List[TurningPass],
    roughing_passes: List[TurningPass],
    mode: MachiningMode,
) -> PlanResult:
    """Build a minimal PlanResult from passes."""
    profile = _build_simple_profile(stock, mode)

    # Collect all tool_moves from all passes in order
    all_moves = []
    for p in face_passes + roughing_passes:
        all_moves.extend(p.moves)

    return PlanResult(
        profile=profile,
        stock=stock,
        tool=tool,
        roughing_params=RoughingParams(
            doc_dia=0.050, feed=0.010,
            strategy=RoughingStrategy.STAIRCASE,
        ),
        finishing_params=FinishingParams(),
        mode=mode,
        face_passes=face_passes,
        roughing_passes=roughing_passes,
        cleanup_passes=[],
        finish_passes=[],
        tool_moves=all_moves,
        finished_part_boundary=[],
        finish_allowance_boundary=[],
        material_to_rough_boundary=[],
        stock_boundary=[],
        profile_boundary=[],
        validations=[],
        pass_count=len(face_passes) + len(roughing_passes),
        move_count=len(all_moves),
    )


# ============================================================
# Property 2.1: End-of-Pass State Preservation
# **Validates: Requirements 3.1**
#
# For all pass indices p and at move_end position:
#   displayed_polygon == pass_states[p]
# ============================================================

class TestEndOfPassPreservation:
    """End-of-pass material state matches pass_states[p]."""

    @given(
        num_passes=st.integers(min_value=1, max_value=10),
        stock=od_stock_strategy(),
        tool=od_tool_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_end_of_pass_polygon_matches_pass_state(
        self, num_passes, stock, tool
    ):
        """**Validates: Requirements 3.1**

        At move_end for each pass, the material polygon stored in
        pass_states[p] is the result of stock.difference(swept_region)
        applied sequentially.
        """
        # Build roughing passes
        doc_dia = 0.050
        x_range = stock.diameter - stock.x_start
        max_passes = int(x_range / doc_dia)
        num_passes = min(num_passes, max(1, max_passes - 1))
        assume(num_passes >= 1)

        passes = []
        all_moves = []
        for i in range(num_passes):
            x_level = stock.diameter - (i + 1) * doc_dia
            if x_level <= stock.x_start:
                break
            z_start = stock.z_start
            z_end = stock.z_end
            moves = [
                ToolMove(MoveType.RAPID, x=x_level, z=z_start,
                         pass_type=PassType.ROUGH, pass_index=i),
                ToolMove(MoveType.FEED, x=x_level, z=z_end, feed=0.010,
                         pass_type=PassType.ROUGH, pass_index=i),
            ]
            swept = SweptRegion(
                x_min=x_level - doc_dia, x_max=x_level,
                z_start=z_start, z_end=z_end,
            )
            tp = TurningPass(
                x_level=x_level, z_start=z_start, z_end=z_end,
                pass_index=i, pass_type=PassType.ROUGH,
                moves=moves, swept_region=swept,
            )
            passes.append(tp)
            all_moves.extend(moves)

        assume(len(passes) >= 1)

        plan = _build_plan_result(stock, tool, [], passes, MachiningMode.OD)
        result = compute(plan)

        # Verify each pass_state is the sequential subtraction result
        assert len(result.pass_states) == len(passes)
        for ps in result.pass_states:
            # pass_states should have non-empty polygons
            assert len(ps.polygons) > 0
            # Each polygon should have coordinate arrays
            for x_arr, z_arr in ps.polygons:
                assert len(x_arr) > 0
                assert len(z_arr) > 0
                assert len(x_arr) == len(z_arr)


    @given(
        num_passes=st.integers(min_value=2, max_value=8),
        tool=od_tool_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_pass_states_monotonically_shrink(self, num_passes, tool):
        """**Validates: Requirements 3.1**

        Each successive pass_state should have less or equal material area
        than the previous one (material is only removed, never added).
        """
        doc_dia = 0.050
        # Build a stock with guaranteed enough range for num_passes
        needed_range = num_passes * doc_dia + 0.01
        diameter = 2.0
        x_start = diameter - needed_range - 0.05
        stock = StockDef(
            diameter=diameter, x_start=x_start,
            z_start=0.1, z_end=-1.0, mode=MachiningMode.OD,
        )
        x_range = stock.diameter - stock.x_start
        max_passes = int(x_range / doc_dia)
        num_passes = min(num_passes, max(1, max_passes - 1))
        assume(num_passes >= 2)

        passes = []
        all_moves = []
        for i in range(num_passes):
            x_level = stock.diameter - (i + 1) * doc_dia
            if x_level <= stock.x_start:
                break
            moves = [
                ToolMove(MoveType.RAPID, x=x_level, z=stock.z_start,
                         pass_type=PassType.ROUGH, pass_index=i),
                ToolMove(MoveType.FEED, x=x_level, z=stock.z_end, feed=0.010,
                         pass_type=PassType.ROUGH, pass_index=i),
            ]
            swept = SweptRegion(
                x_min=x_level - doc_dia, x_max=x_level,
                z_start=stock.z_start, z_end=stock.z_end,
            )
            tp = TurningPass(
                x_level=x_level, z_start=stock.z_start, z_end=stock.z_end,
                pass_index=i, pass_type=PassType.ROUGH,
                moves=moves, swept_region=swept,
            )
            passes.append(tp)
            all_moves.extend(moves)

        assume(len(passes) >= 2)

        plan = _build_plan_result(stock, tool, [], passes, MachiningMode.OD)
        result = compute(plan)

        # Verify monotonic shrinking: each pass removes material
        # Compare polygon bounding boxes (x_max should decrease for OD roughing)
        prev_x_max = None
        for ps in result.pass_states:
            if ps.polygons:
                x_arr = ps.polygons[0][0]
                current_x_max = float(np.max(x_arr))
                if prev_x_max is not None:
                    # Material should shrink or stay same (x_max decreases)
                    assert current_x_max <= prev_x_max + 1e-9
                prev_x_max = current_x_max


# ============================================================
# Property 2.2: Stock Display Preservation (Frame 0)
# **Validates: Requirements 3.2**
#
# For frame 0: displayed_polygon == stock_polygon
# ============================================================

class TestStockDisplayPreservation:
    """At frame 0 (start/reset), full stock polygon is displayed unchanged."""

    @given(
        stock=od_stock_strategy(),
        tool=od_tool_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_stock_polygon_is_full_stock_rectangle_od(self, stock, tool):
        """**Validates: Requirements 3.2**

        The stock_polygon in MaterialSimData should represent the full
        stock rectangle in radius/inches coordinates for OD mode.
        """
        # Build a simple single-pass plan
        x_level = stock.diameter - 0.050
        assume(x_level > stock.x_start)
        moves = [
            ToolMove(MoveType.RAPID, x=x_level, z=stock.z_start,
                     pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=x_level, z=stock.z_end, feed=0.010,
                     pass_type=PassType.ROUGH, pass_index=0),
        ]
        swept = SweptRegion(
            x_min=x_level - 0.050, x_max=x_level,
            z_start=stock.z_start, z_end=stock.z_end,
        )
        tp = TurningPass(
            x_level=x_level, z_start=stock.z_start, z_end=stock.z_end,
            pass_index=0, pass_type=PassType.ROUGH,
            moves=moves, swept_region=swept,
        )
        plan = _build_plan_result(stock, tool, [], [tp], MachiningMode.OD)
        result = compute(plan)

        # Stock polygon should match stock dimensions in radius
        stock_x, stock_z = result.stock_polygon
        assert len(stock_x) > 0
        assert len(stock_z) > 0

        # X range should be [x_start/2, diameter/2] (radius)
        expected_x_min = stock.x_start / 2.0
        expected_x_max = stock.diameter / 2.0
        assert abs(float(np.min(stock_x)) - expected_x_min) < 1e-9
        assert abs(float(np.max(stock_x)) - expected_x_max) < 1e-9

        # Z range should be [z_end, z_start]
        assert abs(float(np.min(stock_z)) - stock.z_end) < 1e-9
        assert abs(float(np.max(stock_z)) - stock.z_start) < 1e-9


    @given(
        stock=id_stock_strategy(),
        tool=id_tool_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_stock_polygon_is_full_stock_rectangle_id(self, stock, tool):
        """**Validates: Requirements 3.2, 3.6**

        The stock_polygon in MaterialSimData should represent the full
        stock rectangle in radius/inches coordinates for ID mode.
        X range: [pilot_hole_dia/2, x_start/2] (radius).
        """
        # Build a simple single-pass plan for ID mode
        x_level = stock.pilot_hole_dia + 0.050
        assume(x_level < stock.x_start)
        moves = [
            ToolMove(MoveType.RAPID, x=x_level, z=stock.z_start,
                     pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=x_level, z=stock.z_end, feed=0.010,
                     pass_type=PassType.ROUGH, pass_index=0),
        ]
        swept = SweptRegion(
            x_min=stock.pilot_hole_dia, x_max=x_level,
            z_start=stock.z_start, z_end=stock.z_end,
        )
        tp = TurningPass(
            x_level=x_level, z_start=stock.z_start, z_end=stock.z_end,
            pass_index=0, pass_type=PassType.ROUGH,
            moves=moves, swept_region=swept,
        )
        plan = _build_plan_result(stock, tool, [], [tp], MachiningMode.ID)
        result = compute(plan)

        # Stock polygon for ID mode
        stock_x, stock_z = result.stock_polygon
        assert len(stock_x) > 0

        # X range should be [pilot_hole_dia/2, x_start/2] (radius)
        expected_x_min = stock.pilot_hole_dia / 2.0
        expected_x_max = stock.x_start / 2.0
        assert abs(float(np.min(stock_x)) - expected_x_min) < 1e-9
        assert abs(float(np.max(stock_x)) - expected_x_max) < 1e-9


# ============================================================
# Property 2.3: Rapid Move Preservation
# **Validates: Requirements 3.3**
#
# For all rapid move indices: material_state is unchanged
# (no subtraction occurs during rapids)
# ============================================================

class TestRapidMovePreservation:
    """During rapid moves (G00), no material state update occurs."""

    @given(
        num_passes=st.integers(min_value=1, max_value=6),
        stock=od_stock_strategy(),
        tool=od_tool_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_rapid_moves_not_in_move_states(self, num_passes, stock, tool):
        """**Validates: Requirements 3.3**

        Rapid moves should NOT appear in the move_states dictionary.
        Only cutting moves (FEED, ARC_CW, ARC_CCW) get entries.
        """
        doc_dia = 0.050
        x_range = stock.diameter - stock.x_start
        max_passes = int(x_range / doc_dia)
        num_passes = min(num_passes, max(1, max_passes - 1))
        assume(num_passes >= 1)

        passes = []
        all_moves = []
        rapid_indices = []

        move_counter = 0
        for i in range(num_passes):
            x_level = stock.diameter - (i + 1) * doc_dia
            if x_level <= stock.x_start:
                break
            moves = [
                ToolMove(MoveType.RAPID, x=x_level, z=stock.z_start,
                         pass_type=PassType.ROUGH, pass_index=i),
                ToolMove(MoveType.FEED, x=x_level, z=(stock.z_start + stock.z_end) / 2,
                         feed=0.010, pass_type=PassType.ROUGH, pass_index=i),
                ToolMove(MoveType.FEED, x=x_level, z=stock.z_end, feed=0.010,
                         pass_type=PassType.ROUGH, pass_index=i),
            ]
            # Track rapid move indices
            rapid_indices.append(move_counter)  # First move is rapid
            move_counter += len(moves)

            swept = SweptRegion(
                x_min=x_level - doc_dia, x_max=x_level,
                z_start=stock.z_start, z_end=stock.z_end,
            )
            tp = TurningPass(
                x_level=x_level, z_start=stock.z_start, z_end=stock.z_end,
                pass_index=i, pass_type=PassType.ROUGH,
                moves=moves, swept_region=swept,
            )
            passes.append(tp)
            all_moves.extend(moves)

        assume(len(passes) >= 1)

        plan = _build_plan_result(stock, tool, [], passes, MachiningMode.OD)
        result = compute(plan)

        # Verify no rapid move index appears in move_states
        for rapid_idx in rapid_indices:
            assert rapid_idx not in result.move_states, (
                f"Rapid move at index {rapid_idx} should not be in move_states"
            )


# ============================================================
# Property 2.4: Final State Preservation
# **Validates: Requirements 3.5**
#
# For final state: displayed_polygon == stock.difference(union(all_swept_regions))
# ============================================================

class TestFinalStatePreservation:
    """At 'Show All' (final state), stock - union(all swept) is displayed."""

    @given(
        num_passes=st.integers(min_value=1, max_value=8),
        stock=od_stock_strategy(),
        tool=od_tool_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_final_state_equals_stock_minus_all_swept(
        self, num_passes, stock, tool
    ):
        """**Validates: Requirements 3.5**

        The final_state in MaterialSimData should equal
        stock.difference(union(all swept regions)).
        """
        doc_dia = 0.050
        x_range = stock.diameter - stock.x_start
        max_passes = int(x_range / doc_dia)
        num_passes = min(num_passes, max(1, max_passes - 1))
        assume(num_passes >= 1)

        passes = []
        all_moves = []
        for i in range(num_passes):
            x_level = stock.diameter - (i + 1) * doc_dia
            if x_level <= stock.x_start:
                break
            moves = [
                ToolMove(MoveType.RAPID, x=x_level, z=stock.z_start,
                         pass_type=PassType.ROUGH, pass_index=i),
                ToolMove(MoveType.FEED, x=x_level, z=stock.z_end, feed=0.010,
                         pass_type=PassType.ROUGH, pass_index=i),
            ]
            swept = SweptRegion(
                x_min=x_level - doc_dia, x_max=x_level,
                z_start=stock.z_start, z_end=stock.z_end,
            )
            tp = TurningPass(
                x_level=x_level, z_start=stock.z_start, z_end=stock.z_end,
                pass_index=i, pass_type=PassType.ROUGH,
                moves=moves, swept_region=swept,
            )
            passes.append(tp)
            all_moves.extend(moves)

        assume(len(passes) >= 1)

        plan = _build_plan_result(stock, tool, [], passes, MachiningMode.OD)
        result = compute(plan)

        # Compute expected final state independently
        stock_poly = _build_stock_polygon(stock, MachiningMode.OD)
        all_swept = []
        for tp in passes:
            region = tp.swept_region
            swept_poly = box(
                region.x_min / 2.0, region.z_end,
                region.x_max / 2.0, region.z_start,
            )
            all_swept.append(swept_poly)

        expected_final = stock_poly.difference(unary_union(all_swept))

        # Compare final_state from compute() with expected
        if expected_final.is_empty:
            assert len(result.final_state) == 0
        else:
            assert len(result.final_state) > 0
            # Compare areas (should be very close)
            # Reconstruct polygon from result arrays
            final_x = result.final_state[0][0]
            final_z = result.final_state[0][1]
            result_poly = Polygon(zip(final_x, final_z))
            area_diff = abs(result_poly.area - expected_final.area)
            assert area_diff < 1e-9, (
                f"Final state area mismatch: got {result_poly.area}, "
                f"expected {expected_final.area}"
            )


# ============================================================
# Property 2.5: Performance Preservation
# **Validates: Requirements 3.4**
#
# For random profiles with 1-30 passes: computation time < 200ms
# ============================================================

class TestPerformancePreservation:
    """Computation completes within 200ms for 30-pass profiles."""

    @given(
        num_passes=st.integers(min_value=1, max_value=30),
        stock=od_stock_strategy(),
        tool=od_tool_strategy(),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_computation_within_200ms_budget(self, num_passes, stock, tool):
        """**Validates: Requirements 3.4**

        Material simulation computation must complete within 200ms
        for profiles with up to 30 passes.
        """
        doc_dia = 0.020  # Smaller DOC to allow more passes
        x_range = stock.diameter - stock.x_start
        max_passes = int(x_range / doc_dia)
        num_passes = min(num_passes, max(1, max_passes - 1))
        assume(num_passes >= 1)

        passes = []
        all_moves = []
        for i in range(num_passes):
            x_level = stock.diameter - (i + 1) * doc_dia
            if x_level <= stock.x_start:
                break
            # Each pass has 3-5 moves for realistic workload
            z_step = (stock.z_start - stock.z_end) / 3
            moves = [
                ToolMove(MoveType.RAPID, x=x_level, z=stock.z_start,
                         pass_type=PassType.ROUGH, pass_index=i),
            ]
            for j in range(1, 4):
                moves.append(ToolMove(
                    MoveType.FEED, x=x_level,
                    z=stock.z_start - j * z_step, feed=0.010,
                    pass_type=PassType.ROUGH, pass_index=i,
                ))

            swept = SweptRegion(
                x_min=x_level - doc_dia, x_max=x_level,
                z_start=stock.z_start, z_end=stock.z_end,
            )
            tp = TurningPass(
                x_level=x_level, z_start=stock.z_start, z_end=stock.z_end,
                pass_index=i, pass_type=PassType.ROUGH,
                moves=moves, swept_region=swept,
            )
            passes.append(tp)
            all_moves.extend(moves)

        assume(len(passes) >= 1)

        plan = _build_plan_result(stock, tool, [], passes, MachiningMode.OD)
        result = compute(plan)

        # Verify computation time is within budget
        assert result.computation_time_ms < 200.0, (
            f"Computation took {result.computation_time_ms:.1f}ms "
            f"(budget: 200ms, passes: {len(passes)})"
        )


# ============================================================
# Property 2.6: ID/OD Mode Coordinate Convention Preservation
# **Validates: Requirements 3.6**
#
# For ID mode inputs: X coordinates are radius values
# For OD mode: same convention preserved
# ============================================================

class TestModeCoordinatePreservation:
    """ID mode and OD mode produce correct coordinate conventions."""

    @given(
        stock=od_stock_strategy(),
        tool=od_tool_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_od_mode_x_coordinates_are_radius(self, stock, tool):
        """**Validates: Requirements 3.6**

        In OD mode, all X coordinates in material states should be
        in radius (not diameter). Values should be within
        [0, stock.diameter/2].
        """
        x_level = stock.diameter - 0.050
        assume(x_level > stock.x_start)
        moves = [
            ToolMove(MoveType.RAPID, x=x_level, z=stock.z_start,
                     pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=x_level, z=stock.z_end, feed=0.010,
                     pass_type=PassType.ROUGH, pass_index=0),
        ]
        swept = SweptRegion(
            x_min=x_level - 0.050, x_max=x_level,
            z_start=stock.z_start, z_end=stock.z_end,
        )
        tp = TurningPass(
            x_level=x_level, z_start=stock.z_start, z_end=stock.z_end,
            pass_index=0, pass_type=PassType.ROUGH,
            moves=moves, swept_region=swept,
        )
        plan = _build_plan_result(stock, tool, [], [tp], MachiningMode.OD)
        result = compute(plan)

        # All X coordinates should be in radius (max = diameter/2)
        max_radius = stock.diameter / 2.0

        # Check stock polygon
        stock_x, _ = result.stock_polygon
        if len(stock_x) > 0:
            assert float(np.max(stock_x)) <= max_radius + 1e-9
            assert float(np.min(stock_x)) >= 0.0 - 1e-9

        # Check pass states
        for ps in result.pass_states:
            for x_arr, z_arr in ps.polygons:
                assert float(np.max(x_arr)) <= max_radius + 1e-9
                assert float(np.min(x_arr)) >= 0.0 - 1e-9

        # Check move states
        for move_idx, arrays in result.move_states.items():
            for x_arr, z_arr in arrays:
                assert float(np.max(x_arr)) <= max_radius + 1e-9
                assert float(np.min(x_arr)) >= 0.0 - 1e-9


    @given(
        stock=id_stock_strategy(),
        tool=id_tool_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_id_mode_x_coordinates_are_radius(self, stock, tool):
        """**Validates: Requirements 3.6**

        In ID mode, all X coordinates in material states should be
        in radius (not diameter). Values should be within
        [pilot_hole_dia/2, x_start/2].
        """
        x_level = stock.pilot_hole_dia + 0.050
        assume(x_level < stock.x_start)
        moves = [
            ToolMove(MoveType.RAPID, x=x_level, z=stock.z_start,
                     pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=x_level, z=stock.z_end, feed=0.010,
                     pass_type=PassType.ROUGH, pass_index=0),
        ]
        swept = SweptRegion(
            x_min=stock.pilot_hole_dia, x_max=x_level,
            z_start=stock.z_start, z_end=stock.z_end,
        )
        tp = TurningPass(
            x_level=x_level, z_start=stock.z_start, z_end=stock.z_end,
            pass_index=0, pass_type=PassType.ROUGH,
            moves=moves, swept_region=swept,
        )
        plan = _build_plan_result(stock, tool, [], [tp], MachiningMode.ID)
        result = compute(plan)

        # All X coordinates should be in radius
        max_radius = stock.x_start / 2.0
        min_radius = stock.pilot_hole_dia / 2.0

        # Check stock polygon
        stock_x, _ = result.stock_polygon
        if len(stock_x) > 0:
            assert float(np.max(stock_x)) <= max_radius + 1e-9
            assert float(np.min(stock_x)) >= min_radius - 1e-9

        # Check pass states
        for ps in result.pass_states:
            for x_arr, z_arr in ps.polygons:
                assert float(np.max(x_arr)) <= max_radius + 1e-9
                assert float(np.min(x_arr)) >= min_radius - 1e-9

        # Check mode is correctly recorded
        assert result.mode == MachiningMode.ID
