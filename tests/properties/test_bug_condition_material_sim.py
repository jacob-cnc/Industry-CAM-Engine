"""Bug Condition Exploration Test — Property 1.

Per-Move Material State Not Rendered During Intra-Pass Playback.

This test is EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.
DO NOT attempt to fix the test or the code when it fails.

Validates: Requirements 1.1, 1.2, 1.3, 1.4

Sub-conditions tested:
  1. Snap: move_states exist but _update_material_state ignores them
  2. Face Z-slice: face pass partial regions use Z-clip instead of X-tracking
  3. Arc instant removal: arc pass uses full_swept for all cutting moves
  4. Index misalignment: SimMove index != tool_moves index when G-code has non-move lines
"""

import sys
import os
import math
import numpy as np
import pytest
from hypothesis import given, settings, assume, note
from hypothesis import strategies as st
from shapely.geometry import box, Polygon

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.moves import ToolMove, MoveType, PassType
from models.results import PlanResult, TurningPass, SweptRegion
from models.stock import StockDef
from models.profile import MachiningMode, ClosedProfile, ProfileMove, SegmentType
from models.tool import ToolDef, ToolOrientation, ToolDirection
from models.params import RoughingParams, FinishingParams, RoughingStrategy
from outputs.material_sim import (
    compute,
    _compute_per_move_states,
    _build_stock_polygon,
    _compute_arc_swept_band,
    _build_rectangular_swept_polygon,
)
from outputs.graph_adapter import convert, GraphData
from gui.components.sim_viewer import parse_gcode_for_sim, SimMove


# ---------------------------------------------------------------------------
# Test Fixtures / Helpers
# ---------------------------------------------------------------------------

def _make_stock(diameter=2.0, x_start=1.8, z_start=0.1, z_end=-1.0):
    """Create a standard OD stock definition."""
    return StockDef(
        diameter=diameter,
        x_start=x_start,
        z_start=z_start,
        z_end=z_end,
        mode=MachiningMode.OD,
    )


def _make_tool(tnr=0.032):
    """Create a standard turning tool."""
    return ToolDef(
        tool_number=1,
        nose_radius=tnr,
        tip_angle=55.0,
        edge_length=0.25,
        orientation=ToolOrientation.OD_FRONT_RIGHT,
        direction=ToolDirection.RIGHT,
    )


def _make_roughing_params():
    """Create standard roughing parameters."""
    return RoughingParams(
        doc_dia=0.050,
        feed=0.008,
        strategy=RoughingStrategy.STAIRCASE,
        fin_allowance=0.005,
    )


def _make_finishing_params():
    """Create standard finishing parameters."""
    return FinishingParams(passes=1, doc_dia=0.002, feed=0.003)


def _make_profile():
    """Create a simple straight profile for OD turning."""
    return ClosedProfile(
        segments=[
            ProfileMove(SegmentType.LINE, x=1.5, z=0.0),
            ProfileMove(SegmentType.LINE, x=1.5, z=-0.8),
        ],
        corner_breaks=[None],
        mode=MachiningMode.OD,
        z_start=0.0,
        z_end=-0.8,
    )


def _make_roughing_pass(pass_index=0, n_moves=5, x_level=1.9, z_start=0.1, z_end=-0.8):
    """Create a roughing pass with n_moves linear feed moves in -Z direction.

    Simulates a standard OD roughing pass at a fixed X level moving from
    z_start toward z_end in equal increments.
    """
    moves = []
    # First move: rapid to start position
    moves.append(ToolMove(
        move_type=MoveType.RAPID,
        x=x_level,
        z=z_start,
        pass_type=PassType.ROUGH,
        pass_index=pass_index,
    ))
    # Cutting moves: feed from z_start toward z_end
    z_step = (z_end - z_start) / n_moves
    for i in range(1, n_moves + 1):
        z_pos = z_start + z_step * i
        moves.append(ToolMove(
            move_type=MoveType.FEED,
            x=x_level,
            z=z_pos,
            feed=0.008,
            pass_type=PassType.ROUGH,
            pass_index=pass_index,
        ))

    swept = SweptRegion(
        x_min=x_level - 0.050,
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


def _make_face_pass(pass_index=0, x_start=2.0, x_end=1.5, z_level=0.01):
    """Create a face pass moving in X from x_start toward x_end at fixed Z.

    Face passes move primarily in X (from stock OD toward centerline).
    """
    moves = []
    # Rapid to start
    moves.append(ToolMove(
        move_type=MoveType.RAPID,
        x=x_start,
        z=z_level + 0.05,
        pass_type=PassType.FACE,
        pass_index=pass_index,
    ))
    # Feed to face Z level
    moves.append(ToolMove(
        move_type=MoveType.FEED,
        x=x_start,
        z=z_level,
        feed=0.005,
        pass_type=PassType.FACE,
        pass_index=pass_index,
    ))
    # Face cuts: 4 moves from x_start toward x_end
    n_cuts = 4
    x_step = (x_end - x_start) / n_cuts
    for i in range(1, n_cuts + 1):
        x_pos = x_start + x_step * i
        moves.append(ToolMove(
            move_type=MoveType.FEED,
            x=x_pos,
            z=z_level,
            feed=0.005,
            pass_type=PassType.FACE,
            pass_index=pass_index,
        ))

    swept = SweptRegion(
        x_min=x_end,
        x_max=x_start,
        z_start=z_level + 0.05,
        z_end=z_level,
    )

    return TurningPass(
        x_level=x_start,
        z_start=z_level + 0.05,
        z_end=z_level,
        pass_index=pass_index,
        pass_type=PassType.FACE,
        moves=moves,
        swept_region=swept,
    )


def _make_arc_finish_pass(pass_index=0, arc_radius=0.5, x_start=1.5, z_start=0.0):
    """Create a finish pass with arc moves (G02/G03).

    Simulates a finish pass that traces an arc contour.
    """
    moves = []
    # Rapid to start
    moves.append(ToolMove(
        move_type=MoveType.RAPID,
        x=x_start,
        z=z_start + 0.05,
        pass_type=PassType.FINISH,
        pass_index=pass_index,
    ))
    # Feed to start of arc
    moves.append(ToolMove(
        move_type=MoveType.FEED,
        x=x_start,
        z=z_start,
        feed=0.003,
        pass_type=PassType.FINISH,
        pass_index=pass_index,
    ))

    # Create 3 arc moves (G02 clockwise) tracing a quarter circle
    # Arc center is at (x_start + arc_radius, z_start) in diameter coords
    # We split the quarter circle into 3 segments
    center_x_dia = x_start  # center_i is incremental offset in diameter
    n_arcs = 3
    for i in range(1, n_arcs + 1):
        angle = (math.pi / 2.0) * (i / n_arcs)  # 0 to pi/2
        # End point of this arc segment
        end_x = x_start + arc_radius * 2.0 * (1.0 - math.cos(angle))
        end_z = z_start - arc_radius * math.sin(angle)
        # center_i/center_k are incremental from the START of this segment
        if i == 1:
            ci = arc_radius * 2.0  # diameter offset to center
            ck = 0.0
        else:
            prev_angle = (math.pi / 2.0) * ((i - 1) / n_arcs)
            prev_x = x_start + arc_radius * 2.0 * (1.0 - math.cos(prev_angle))
            prev_z = z_start - arc_radius * math.sin(prev_angle)
            # Center is always at (x_start + arc_radius*2, z_start) in diameter
            center_x_abs = x_start + arc_radius * 2.0
            center_z_abs = z_start
            ci = center_x_abs - prev_x  # incremental from prev endpoint
            ck = center_z_abs - prev_z

        moves.append(ToolMove(
            move_type=MoveType.ARC_CW,
            x=end_x,
            z=end_z,
            feed=0.003,
            radius=arc_radius,
            center_i=ci,
            center_k=ck,
            pass_type=PassType.FINISH,
            pass_index=pass_index,
        ))

    # Swept region bounds (approximate bounding box of the arc)
    swept = SweptRegion(
        x_min=x_start,
        x_max=x_start + arc_radius * 2.0,
        z_start=z_start,
        z_end=z_start - arc_radius,
    )

    return TurningPass(
        x_level=x_start,
        z_start=z_start,
        z_end=z_start - arc_radius,
        pass_index=pass_index,
        pass_type=PassType.FINISH,
        moves=moves,
        swept_region=swept,
    )


# ---------------------------------------------------------------------------
# Sub-condition 1: Snap Behavior — move_states not rendered
# ---------------------------------------------------------------------------

class TestSubCondition1_SnapBehavior:
    """Test that _update_material_state renders move_states for intermediate moves.

    Bug: set_partial_material() shows previous pass state for intermediate
    progress values, ignoring the pre-computed move_states dictionary.

    Expected behavior: move_states[move_index] polygon is rendered directly.
    """

    @given(move_offset=st.integers(min_value=1, max_value=4))
    @settings(max_examples=10)
    def test_set_partial_material_shows_previous_pass_not_move_state(self, move_offset):
        """**Validates: Requirements 1.1**

        For a 5-move roughing pass, set_partial_material at intermediate
        progress shows the PREVIOUS pass state (stock for first pass),
        NOT the pre-computed move_states[move_index] polygon.

        This test asserts the EXPECTED behavior (that the viewer SHOULD
        render move_states), which FAILS on unfixed code because
        set_partial_material falls through to showing previous pass state.
        """
        stock = _make_stock()
        tool = _make_tool()
        roughing_pass = _make_roughing_pass(pass_index=0, n_moves=5)

        # Build a minimal PlanResult
        all_moves = roughing_pass.moves
        plan_result = PlanResult(
            profile=_make_profile(),
            stock=stock,
            tool=tool,
            roughing_params=_make_roughing_params(),
            finishing_params=_make_finishing_params(),
            mode=MachiningMode.OD,
            face_passes=[],
            roughing_passes=[roughing_pass],
            cleanup_passes=[],
            finish_passes=[],
            tool_moves=all_moves,
            finished_part_boundary=[],
            finish_allowance_boundary=[],
            material_to_rough_boundary=[],
            stock_boundary=[],
            profile_boundary=[],
            validations=[],
        )

        # Compute material simulation
        sim_data = compute(plan_result)

        # The move_states dict should have entries for cutting moves
        # (move indices 1-5, since index 0 is the rapid)
        target_move_idx = move_offset  # 1-based (skip rapid at index 0)
        note(f"Checking move_states for move_idx={target_move_idx}")
        note(f"move_states keys: {list(sim_data.move_states.keys())}")

        # Assert: move_states has an entry for this intermediate cutting move
        assert target_move_idx in sim_data.move_states, (
            f"move_states should contain entry for cutting move {target_move_idx}, "
            f"but keys are: {list(sim_data.move_states.keys())}"
        )

        # Convert to GraphData (what the viewer uses)
        graph_data = convert(plan_result, sim_data)
        assert graph_data.material_states is not None

        # Simulate what _update_material_state does:
        # It finds the pass, computes progress, and calls set_partial_material
        ps = graph_data.material_states.pass_states[0]
        move_range = ps.move_end - ps.move_start
        if move_range > 0:
            progress = (target_move_idx - ps.move_start) / float(move_range)
        else:
            progress = 1.0

        note(f"Progress for move {target_move_idx}: {progress}")
        assert 0.0 < progress < 1.0, "Should be intermediate progress"

        # THE BUG: set_partial_material for intermediate progress (0 < p < 1)
        # shows the PREVIOUS pass state (pass_index - 1), which for the first
        # pass is the stock polygon. It does NOT look up move_states[move_idx].
        #
        # We test this by checking what set_partial_material WOULD display:
        # For pass_index=0 and 0 < progress < 1, it calls
        # set_material_state(pass_index - 1) which shows stock.
        #
        # Expected behavior: it should show move_states[target_move_idx]
        # which has LESS material than stock.

        # Get what move_states says should be displayed
        move_state_polys = sim_data.move_states[target_move_idx]
        ms_x, ms_z = move_state_polys[0]
        expected_poly = Polygon(list(zip(ms_x, ms_z)))

        # Get what set_partial_material ACTUALLY displays (stock for first pass)
        stock_x, stock_z = sim_data.stock_polygon
        stock_poly = Polygon(list(zip(stock_x, stock_z)))

        # The actual displayed polygon (from set_partial_material) is stock
        # because for pass_index=0 and intermediate progress, it shows
        # set_material_state(pass_index - 1) = set_material_to_stock()
        #
        # Assert EXPECTED behavior: displayed polygon should equal move_states
        # This FAILS on unfixed code because displayed == stock != move_states
        assert expected_poly.area < stock_poly.area, (
            f"move_states[{target_move_idx}] should have less material than stock"
        )

        # THE KEY ASSERTION: verify that _update_material_state does NOT
        # look up move_states — it uses set_partial_material which for
        # intermediate progress shows previous pass state (stock).
        # On unfixed code, there's no code path that reads move_states
        # during playback. We verify this by checking the code path:
        # _update_material_state -> set_partial_material(ps_idx, progress)
        # -> for 0 < progress < 1: set_material_state(pass_index - 1)
        # This means the viewer shows STOCK, not move_states[idx].

        # Import and inspect the actual set_partial_material behavior
        from gui.components.graph_widget import MachiningGraphWidget
        import inspect

        # Also verify _update_material_state doesn't look up move_states
        from gui.components.sim_viewer import SimViewerWidget
        update_source = inspect.getsource(SimViewerWidget._update_material_state)

        # EXPECTED BEHAVIOR: _update_material_state SHOULD access move_states
        # to render per-move polygon data for intermediate cutting moves.
        # This assertion FAILS on unfixed code because it uses set_partial_material
        # which shows previous pass state instead of looking up move_states.
        assert "move_states" in update_source and (
            "move_states[" in update_source or "move_states.get" in update_source
        ), (
            "_update_material_state SHOULD look up move_states for intermediate "
            "cutting moves. Bug: it computes progress and calls set_partial_material "
            "which shows previous pass state for 0 < progress < 1, ignoring "
            "the pre-computed move_states dictionary entirely."
        )


# ---------------------------------------------------------------------------
# Sub-condition 2: Face Pass Z-Slice — partial region uses Z-clip not X-tracking
# ---------------------------------------------------------------------------

class TestSubCondition2_FaceZSlice:
    """Test that face pass move_states track X position, not Z extent.

    Bug: _compute_per_move_states clips face pass partial regions using Z bounds
    (box(x_min, partial_z_min, x_max, partial_z_max)) when face passes move
    primarily in X.

    Expected behavior: partial swept region tracks tool's actual X position.
    """

    @given(cut_index=st.integers(min_value=1, max_value=3))
    @settings(max_examples=10)
    def test_face_pass_partial_region_tracks_x_not_z(self, cut_index):
        """**Validates: Requirements 1.2**

        For a face pass moving X from 2.0 to 1.5 at Z=0.01, the move_states
        at intermediate X positions should show material removed tracking X,
        not Z-sliced across the full X range.

        On unfixed code: the partial_swept box clips by Z extent, which for
        a face pass (constant Z) produces either no removal or full removal
        depending on the Z bounds — NOT progressive X-tracking.
        """
        stock = _make_stock(diameter=2.0, x_start=1.0, z_start=0.1, z_end=-1.0)
        tool = _make_tool()
        face_pass = _make_face_pass(pass_index=0, x_start=2.0, x_end=1.5, z_level=0.01)

        all_moves = face_pass.moves
        plan_result = PlanResult(
            profile=_make_profile(),
            stock=stock,
            tool=tool,
            roughing_params=_make_roughing_params(),
            finishing_params=_make_finishing_params(),
            mode=MachiningMode.OD,
            face_passes=[face_pass],
            roughing_passes=[],
            cleanup_passes=[],
            finish_passes=[],
            tool_moves=all_moves,
            finished_part_boundary=[],
            finish_allowance_boundary=[],
            material_to_rough_boundary=[],
            stock_boundary=[],
            profile_boundary=[],
            validations=[],
        )

        sim_data = compute(plan_result)

        # The face pass has moves at indices:
        # 0: rapid to start
        # 1: feed to Z level (x=2.0, z=0.01)
        # 2-5: face cuts moving X from 2.0 toward 1.5
        # cut_index 1-3 maps to move indices 2-4 (the X-moving cuts)
        target_move_idx = cut_index + 1  # +1 to skip the Z-plunge feed

        note(f"Face pass cut_index={cut_index}, target_move_idx={target_move_idx}")
        note(f"move_states keys: {list(sim_data.move_states.keys())}")

        # Check if move_states has entries for face pass cutting moves
        if target_move_idx not in sim_data.move_states:
            # If no entry exists, the face pass Z-clip produced degenerate geometry
            # This itself demonstrates the bug (Z-clip at constant Z = no removal)
            pytest.fail(
                f"move_states has no entry for face pass move {target_move_idx}. "
                f"This indicates the Z-clip produced degenerate geometry for a "
                f"face pass at constant Z. Keys: {list(sim_data.move_states.keys())}"
            )

        # Get the move_state polygon for this intermediate face cut
        move_state_polys = sim_data.move_states[target_move_idx]
        assert len(move_state_polys) > 0

        # The face pass moves in X from 2.0 (dia) toward 1.5 (dia)
        # At cut_index=1 (first X cut), tool is at X = 2.0 + (1.5-2.0)/4 * 1 = 1.875 dia
        # Expected: material removed from X=2.0 down to X=1.875 (in diameter)
        # Bug: material removed in a Z-slice across full X range

        # Verify the partial removal tracks X position:
        # The move_state polygon should still have material at X values
        # BELOW the current tool X position (in radius coords)
        current_move = all_moves[target_move_idx]
        current_x_r = current_move.x / 2.0  # current tool X in radius

        ms_x, ms_z = move_state_polys[0]
        move_poly = Polygon(list(zip(ms_x, ms_z)))

        # The stock polygon
        stock_poly = Polygon(list(zip(*sim_data.stock_polygon)))

        # Expected behavior: material removed from stock OD (x=1.0r) down to
        # current_x_r, but ONLY in the Z range of the face pass.
        # The remaining material polygon should have its max X at approximately
        # current_x_r in the face zone (z near 0.01).

        # Bug behavior: Z-clip at constant Z produces either:
        # - No removal (if partial_z_min >= partial_z_max for constant Z)
        # - Full X-range removal in a thin Z slice
        # Either way, the polygon area relationship is wrong.

        # Assert progressive removal: each successive cut should remove MORE
        # material than the previous one. With Z-clip bug, all cuts either
        # remove nothing or the same amount.
        if cut_index > 1:
            prev_move_idx = cut_index  # previous cut
            if prev_move_idx in sim_data.move_states:
                prev_polys = sim_data.move_states[prev_move_idx]
                prev_poly = Polygon(list(zip(*prev_polys[0])))
                # Current cut should have LESS material than previous cut
                # (more material removed as X progresses)
                assert move_poly.area < prev_poly.area, (
                    f"Face pass cut {cut_index}: polygon area ({move_poly.area:.6f}) "
                    f"should be less than previous cut area ({prev_poly.area:.6f}). "
                    f"Z-clip bug causes all cuts to show same state."
                )


# ---------------------------------------------------------------------------
# Sub-condition 3: Arc Instant Removal — full_swept used for all arc moves
# ---------------------------------------------------------------------------

class TestSubCondition3_ArcInstantRemoval:
    """Test that arc pass move_states grow incrementally, not instant full removal.

    Bug: _compute_per_move_states uses partial_swept = full_swept for arc passes,
    removing the entire arc band at the first cutting move.

    Expected behavior: cumulative swept region grows incrementally with each
    arc cutting move.
    """

    @given(arc_move_index=st.integers(min_value=0, max_value=1))
    @settings(max_examples=10)
    def test_arc_pass_progressive_removal(self, arc_move_index):
        """**Validates: Requirements 1.3**

        For a finish pass with 3 arc moves, the move_states for the first
        arc cutting move should show LESS removal than the last arc move.

        On unfixed code: partial_swept = full_swept for ALL arc moves,
        so move_states entries are identical (full removal at first move).
        """
        stock = _make_stock()
        tool = _make_tool(tnr=0.032)
        arc_pass = _make_arc_finish_pass(pass_index=0, arc_radius=0.25)

        all_moves = arc_pass.moves
        plan_result = PlanResult(
            profile=_make_profile(),
            stock=stock,
            tool=tool,
            roughing_params=_make_roughing_params(),
            finishing_params=_make_finishing_params(),
            mode=MachiningMode.OD,
            face_passes=[],
            roughing_passes=[],
            cleanup_passes=[],
            finish_passes=[arc_pass],
            tool_moves=all_moves,
            finished_part_boundary=[],
            finish_allowance_boundary=[],
            material_to_rough_boundary=[],
            stock_boundary=[],
            profile_boundary=[],
            validations=[],
        )

        sim_data = compute(plan_result)

        # Arc pass moves:
        # 0: rapid
        # 1: feed to start
        # 2, 3, 4: arc cutting moves (ARC_CW)
        # arc_move_index 0 = first arc (move_idx 2), 1 = second arc (move_idx 3)
        first_arc_idx = 2
        last_arc_idx = 4
        target_arc_idx = first_arc_idx + arc_move_index

        note(f"Arc move_index={arc_move_index}, target_arc_idx={target_arc_idx}")
        note(f"move_states keys: {list(sim_data.move_states.keys())}")

        # Both the first and last arc moves should have move_states entries
        assert first_arc_idx in sim_data.move_states or last_arc_idx in sim_data.move_states, (
            f"Arc pass should have move_states entries for arc cutting moves. "
            f"Keys: {list(sim_data.move_states.keys())}"
        )

        if first_arc_idx not in sim_data.move_states or last_arc_idx not in sim_data.move_states:
            pytest.skip("Arc move_states entries missing — cannot test progressive removal")

        # Get polygons for first and last arc moves
        first_polys = sim_data.move_states[first_arc_idx]
        last_polys = sim_data.move_states[last_arc_idx]

        first_poly = Polygon(list(zip(*first_polys[0])))
        last_poly = Polygon(list(zip(*last_polys[0])))

        # Expected behavior: first arc move removes LESS material than last arc move
        # So first_poly.area > last_poly.area (more material remaining at first move)
        #
        # Bug behavior: partial_swept = full_swept for ALL arc moves
        # So first_poly.area == last_poly.area (same removal at every move)
        assert first_poly.area > last_poly.area, (
            f"First arc move (idx {first_arc_idx}) should have MORE remaining material "
            f"({first_poly.area:.8f}) than last arc move (idx {last_arc_idx}) "
            f"({last_poly.area:.8f}). "
            f"Bug: partial_swept = full_swept causes identical removal at all arc moves."
        )


# ---------------------------------------------------------------------------
# Sub-condition 4: Index Misalignment — SimMove index != tool_moves index
# ---------------------------------------------------------------------------

class TestSubCondition4_IndexMisalignment:
    """Test that SimMove indices correctly map to tool_moves indices.

    Bug: _update_material_state passes the SimMove index directly to
    toolpath_segments[move_idx], but toolpath_segments is built from
    PlanResult.tool_moves which may have different count/ordering.

    Expected behavior: a verified mapping between SimMove indices and
    PlanResult.tool_moves indices exists and is used.
    """

    @given(n_comments=st.integers(min_value=2, max_value=5))
    @settings(max_examples=10)
    def test_gcode_with_non_move_lines_causes_index_mismatch(self, n_comments):
        """**Validates: Requirements 1.4**

        When G-code has extra non-move lines (comments, M-codes), the
        SimMove count differs from tool_moves count. The SimMove index
        for a given physical move will NOT match the tool_moves index.

        On unfixed code: no sim_to_toolmoves mapping exists, so
        _update_material_state uses the SimMove index directly as
        toolpath_segments index, causing misalignment.
        """
        # Create G-code with interleaved comments and M-codes
        gcode_lines = [
            "(Program start)",
            "G21 (metric mode - but we use inches, just for non-move line)",
        ]

        # Add n_comments before the first move
        for i in range(n_comments):
            gcode_lines.append(f"(Comment {i} - non-move line)")

        # Add actual moves that correspond to a roughing pass
        gcode_lines.append("G00 X2.0 Z0.1")  # Rapid to start
        gcode_lines.append("(Mid-program comment)")
        gcode_lines.append("G01 X1.9 Z0.0 F0.008")  # Feed move 1
        gcode_lines.append("M08 (coolant on - non-move)")
        gcode_lines.append("G01 X1.9 Z-0.2 F0.008")  # Feed move 2
        gcode_lines.append("(Another comment)")
        gcode_lines.append("G01 X1.9 Z-0.4 F0.008")  # Feed move 3
        gcode_lines.append("G01 X1.9 Z-0.6 F0.008")  # Feed move 4
        gcode_lines.append("G01 X1.9 Z-0.8 F0.008")  # Feed move 5
        gcode_lines.append("G00 X2.0 Z0.1")  # Rapid retract

        gcode_text = "\n".join(gcode_lines)

        # Parse SimMoves from G-code
        sim_moves = parse_gcode_for_sim(gcode_text)

        # Create corresponding tool_moves (what the planner would produce)
        # These are the ACTUAL physical moves without comments/M-codes
        tool_moves = [
            ToolMove(MoveType.RAPID, x=2.0, z=0.1, pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=1.9, z=0.0, feed=0.008, pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=1.9, z=-0.2, feed=0.008, pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=1.9, z=-0.4, feed=0.008, pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=1.9, z=-0.6, feed=0.008, pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.FEED, x=1.9, z=-0.8, feed=0.008, pass_type=PassType.ROUGH, pass_index=0),
            ToolMove(MoveType.RAPID, x=2.0, z=0.1, pass_type=PassType.ROUGH, pass_index=0),
        ]

        note(f"SimMove count: {len(sim_moves)}")
        note(f"tool_moves count: {len(tool_moves)}")

        # The bug manifests in _update_material_state which uses the SimMove
        # index (from the interpolated path) directly as an index into
        # toolpath_segments[]. The toolpath_segments list is built from
        # PlanResult.tool_moves. If there's any discrepancy between the
        # SimMove path and tool_moves, the wrong segment is looked up.

        # Verify the core issue: _update_material_state has NO mapping
        # between SimMove indices and tool_moves indices.
        # It directly uses move_idx from self._path[self._sim_step] as
        # an index into graph_data.toolpath_segments[move_idx].

        # Check the source code of _update_material_state to confirm
        # it does NOT have any sim_to_toolmoves mapping logic
        from gui.components.sim_viewer import SimViewerWidget
        import inspect
        source = inspect.getsource(SimViewerWidget._update_material_state)

        # EXPECTED BEHAVIOR: _update_material_state SHOULD use a
        # sim_to_toolmoves mapping to convert SimMove indices to tool_moves indices.
        # This assertion FAILS on unfixed code because the mapping doesn't exist.
        assert "_sim_to_toolmoves" in source, (
            "_update_material_state SHOULD use _sim_to_toolmoves mapping "
            "to convert SimMove indices to tool_moves indices. "
            "Bug: it uses move_idx directly without any mapping, causing "
            "index misalignment when SimMove count differs from tool_moves count."
        )

        # Verify the line_idx values in SimMoves account for non-move lines
        # The first actual move (G00 X2.0 Z0.1) is at a line_idx > 0
        # because of the preceding comments
        first_move_line = sim_moves[0].line_idx
        note(f"First SimMove line_idx: {first_move_line}")
        note(f"n_comments: {n_comments}")
        assert first_move_line >= n_comments + 2, (
            f"First SimMove line_idx ({first_move_line}) should be >= "
            f"{n_comments + 2} (accounting for {n_comments} comments + 2 header lines). "
            f"This confirms non-move lines shift line indices."
        )
