"""Cutting allowance schedule and independent spring pass, through G-code."""
from dataclasses import replace
import pytest

from models.params import FinishingParams
from models.moves import MoveType
from outputs.gcode_parser import parse
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute
from tests.integration.test_operation_depth import bore_fields

def _without_comp_entries(gcode: str) -> str:
    """Drop the in-air cutter-comp entry/lead-out moves (added 2026-11-08)
    so tests compare only the planned contour moves."""
    return "\n".join(l for l in gcode.splitlines()
                     if "Comp entry" not in l and "Comp lead-out" not in l
                     and "Contour approach" not in l)


def _split_links(gcode: str):
    """(contour text, planned-link text): finish retract/approach links and the
    diagonal retract are planned links; since 2026-11-11 a link into a finish or
    spring pass ends with a .020 dia FEED-in, so links are no longer all rapids."""
    lines = _without_comp_entries(gcode).splitlines()
    is_link = lambda l: "retract/approach" in l or "Diagonal retract" in l
    return ("\n".join(l for l in lines if not is_link(l)),
            "\n".join(l for l in lines if is_link(l)))



def shape(moves):
    return [(m.move_type, m.x, m.z, m.feed, m.center_i, m.center_k, m.radius) for m in moves]


@pytest.mark.parametrize("mode", ["id", "od"])
@pytest.mark.parametrize("strategy", ["staircase", "offset_contour"])
@pytest.mark.parametrize("spring", [False, True])
def test_cutting_passes_remove_allowance_and_spring_repeats_final(mode, strategy, spring):
    fields = bore_fields(mode=mode, strategy=strategy, finish_passes=3,
                         fin_allowance=.006, finish_doc_dia=.099,
                         finish_spring_pass=spring)
    profile, stock, roughing, finishing = build_from_fields(**fields)
    # Caller-provided legacy DOC never controls the schedule.
    assert finishing.doc_dia == pytest.approx(.002)
    result = execute(profile, stock, fields["tool_def"], roughing,
                     replace(finishing, doc_dia=.5))
    assert result.plan_result is not None, result.validations
    plan = result.plan_result
    assert plan.finishing_params.doc_dia == pytest.approx(.002)
    cuts = [p for p in plan.finish_passes if not p.is_spring_pass]
    springs = [p for p in plan.finish_passes if p.is_spring_pass]
    assert len(cuts) == 3
    assert len(springs) == int(spring)
    expected_x = [3.113, 3.115, 3.117] if mode == "id" else [3.121, 3.119, 3.117]
    for p, x in zip(cuts, expected_x):
        assert [m.x for m in p.moves] == pytest.approx([x, x])
        assert [m.z for m in p.moves] == pytest.approx([0, -.568])
    if spring:
        assert shape(springs[0].moves) == shape(cuts[-1].moves)
        assert springs[0].pass_index != cuts[-1].pass_index
    code = GCodeWriter().write(plan)
    section = code.split("; === FINISH PASS")[1].split("; === PROGRAM END")[0]
    cut_text, link_text = _split_links(section)
    emitted_cuts = [m for m in parse(cut_text) if m.move_type == MoveType.FEED]
    expected_moves = [m for p in plan.finish_passes for m in p.moves]
    assert [m.x for m in emitted_cuts] == pytest.approx([m.x for m in expected_moves])
    assert [m.z for m in emitted_cuts] == pytest.approx([m.z for m in expected_moves])
    # All finish-to-finish links in output are the links already validated by pipeline,
    # move type included (each ends with the .020 dia feed-in).
    links = [m for p in plan.finish_passes[1:] for m in p.approach_moves]
    links += list(plan.finish_passes[-1].retract_moves)
    # Writer approach to the first pass (rise/traverse at clearance) is filtered
    # out above as 'Contour approach'; the rest are the validated links.
    emitted_links = parse(link_text)
    assert [m.move_type for m in emitted_links] == [m.move_type for m in links]
    assert [m.x for m in emitted_links] == pytest.approx([m.x for m in links])
    assert [m.z for m in emitted_links] == pytest.approx([m.z for m in links])
    assert "; Finish Passes: 3" in code
    assert f"; Spring Pass: {int(spring)}" in code


@pytest.mark.parametrize("spring", [False, True])
def test_one_finish_cut_preserves_existing_final_contour(spring):
    fields = bore_fields(finish_spring_pass=spring)
    profile, stock, roughing, finishing = build_from_fields(**fields)
    plan = execute(profile, stock, fields["tool_def"], roughing, finishing).plan_result
    assert plan is not None
    assert [(m.x, m.z) for m in plan.finish_passes[0].moves] == [(3.117, 0), (3.117, -.568)]
    assert len(plan.finish_passes) == 1 + int(spring)
    GCodeWriter().write(plan)


@pytest.mark.parametrize("passes", [0, -1, 1.5, True])
def test_invalid_cutting_counts_are_rejected(passes):
    with pytest.raises(ValueError, match="positive integer"):
        FinishingParams(passes=passes)


def test_zero_allowance_does_not_invent_multiple_cutting_passes():
    with pytest.raises(ValueError, match="positive finish allowance"):
        build_from_fields(**bore_fields(fin_allowance=0, finish_passes=3))


def test_invalid_kernel_contour_is_still_blocked_by_validation(monkeypatch):
    from geometry.zone_query import ZoneQueryAPI, EdgeData
    from models.validation import PipelineStatus
    original = ZoneQueryAPI.profile_offset_edges
    def invalid_finish(self, profile, allowance, **kwargs):
        if "z_min" in kwargs:
            return original(self, profile, allowance, **kwargs)
        return [EdgeData("LINE", (3.217, 0), (3.217, -.568))]
    monkeypatch.setattr(ZoneQueryAPI, "profile_offset_edges", invalid_finish)
    fields = bore_fields(finish_passes=3, fin_allowance=.006)
    p, s, r, f = build_from_fields(**fields)
    result = execute(p, s, fields["tool_def"], r, f)
    assert result.status == PipelineStatus.BLOCKED_BY_ERROR
    assert result.plan_result is None
    assert any("GOUGE" in v.message for v in result.validations)


def test_missing_finish_link_cannot_be_written_as_a_return_cut():
    fields = bore_fields(finish_spring_pass=True)
    p, s, r, f = build_from_fields(**fields)
    plan = execute(p, s, fields["tool_def"], r, f).plan_result
    broken = replace(plan, finish_passes=[plan.finish_passes[0],
                     replace(plan.finish_passes[1], approach_moves=())])
    with pytest.raises(ValueError, match="planned retract/approach"):
        GCodeWriter().write(broken)


def test_single_id_finish_uses_kernel_edges_without_hidden_coordinate_fallback(monkeypatch):
    from planners.finish_planner import FinishPlanner
    def no_fallback(*args):
        raise AssertionError("Unexpected coordinate fallback instead of kernel edges")
    monkeypatch.setattr(FinishPlanner, "_moves_from_segments", no_fallback)
    fields = bore_fields()
    p, s, r, f = build_from_fields(**fields)
    assert execute(p, s, fields["tool_def"], r, f).plan_result is not None


def test_single_cut_and_spring_have_identical_contour_entry():
    fields = bore_fields(x_start=2.995, finish_spring_pass=True)
    p, s, r, f = build_from_fields(**fields)
    plan = execute(p, s, fields["tool_def"], r, f).plan_result
    cut, spring = plan.finish_passes
    assert cut.x_level == spring.approach_moves[-1].x
    assert cut.z_start == spring.approach_moves[-1].z
    assert shape(cut.moves) == shape(spring.moves)


def test_rounding_cannot_silently_turn_cutting_passes_into_spring_repeats():
    fields = bore_fields(finish_passes=10, fin_allowance=.0005)
    p, s, r, f = build_from_fields(**fields)
    plan = execute(p, s, fields["tool_def"], r, f).plan_result
    assert plan is not None
    with pytest.raises(ValueError, match="output precision"):
        GCodeWriter().write(plan, unit_mode="inch")


@pytest.mark.parametrize("mode,segments", [
    ("id", [dict(x=1.2, z=0), dict(x=1.2, z=-1), dict(x=.8, z=-1), dict(x=.8, z=-1.5)]),
    ("od", [dict(x=3, z=0), dict(type="arc", x=2, z=-.5, radius=.5), dict(x=2, z=-1)]),
    ("id", [dict(x=3, z=0), dict(type="arc", x=3.5, z=-.25, radius=-.25), dict(x=3.5, z=-1)]),
])
def test_kernel_offsets_preserve_steps_arcs_and_spring_geometry(mode, segments):
    fields = bore_fields(mode=mode, segments=segments, stock_back_z=-2,
        pilot_hole_dia=.5, x_start=segments[0]["x"], fin_allowance=.006,
        finish_passes=3, finish_spring_pass=True)
    profile, stock, roughing, finishing = build_from_fields(**fields)
    result = execute(profile, stock, fields["tool_def"], roughing, finishing)
    assert result.plan_result is not None, result.validations
    plan = result.plan_result
    assert shape(plan.finish_passes[-1].moves) == shape(plan.finish_passes[-2].moves)
    assert len(plan.finish_passes) == 4
    assert any(m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW)
               for m in plan.finish_passes[0].moves) == any(s.get("type") == "arc" for s in segments)
    # The final cutting pass still follows the user contour, not an offset/closure.
    assert [m.x for m in plan.finish_passes[-2].moves] == pytest.approx([s["x"] for s in segments])
    assert [m.z for m in plan.finish_passes[-2].moves] == pytest.approx([s["z"] for s in segments])
    code = GCodeWriter().write(plan)
    final_cut = code.split("; Finish cutting pass 3\n")[1].split("; Spring pass (repeat final contour)\n")[0]
    spring_cut = code.split("; Spring pass (repeat final contour)\n")[1].split("; === PROGRAM END")[0]
    cutting_types = (MoveType.FEED, MoveType.ARC_CW, MoveType.ARC_CCW)
    parsed_final = [m for m in parse(_split_links(final_cut)[0]) if m.move_type in cutting_types]
    parsed_spring = [m for m in parse(_split_links(spring_cut)[0]) if m.move_type in cutting_types]
    assert shape(parsed_final) == shape(parsed_spring)
