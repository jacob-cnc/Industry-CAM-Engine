"""Material removal by the true-scale insert (tool-graphic plan 2026-11-13, T5)."""
import pytest
from shapely.geometry import box

from validation.material_sweep import GRAZE, run_material, stock_box, sweep, outline_polygon
from geometry.tool_outline import tool_outline
from models.tool import InsertSpec
from outputs.program_header import stock_from_header

R = 1 / 64
CNMG = tool_outline(InsertSpec(2, R, 95.0, 175.0, "C", 0.5))       # RH OD, 95 deg holder


def test_turning_pass_leaves_the_surface_at_the_tip_line():
    """A Q2 tool fed along -Z at r .4: nothing is left above r .4 where it
    passed, nothing below r .4 is touched (the nose bottom IS the tip line)."""
    stock = stock_box(0.0, 0.5, -1.0, 0.0)
    run = run_material(stock, [("feed", CNMG, [(0.4, 0.1), (0.4, -0.5)])])
    left = run.after[-1]
    assert left.intersection(box(0.4 + 1e-6, -0.5 + R, 0.5, 0.0)).area < 1e-9
    assert left.intersection(box(0.0, -1.0, 0.4 - 1e-6, 0.0)).area == pytest.approx(0.4 * 1.0, abs=5e-6)   # .000005 deep over 1"
    assert run.warnings == []


def test_sweep_is_the_hull_of_the_two_placements():
    body = outline_polygon(CNMG)
    s = sweep(body, [(0.0, 0.0), (0.0, -0.5)])
    assert s.area == pytest.approx(body.area + 0.5 * (body.bounds[2] - body.bounds[0]), rel=1e-3)


def test_back_of_the_insert_into_stock_is_a_rub():
    """Feeding +Z into stock with a RH tool drives the insert body (not its
    cutting edges) into the material."""
    stock = stock_box(0.0, 0.5, 0.2, 0.6)
    run = run_material(stock, [("feed", CNMG, [(0.3, -0.5), (0.3, 0.1)])])
    assert [w[1] for w in run.warnings] == ["rub"]


def test_normal_facing_and_turning_do_not_rub():
    stock = stock_box(0.0, 0.5, -1.0, 0.05)
    moves = [("feed", CNMG, [(0.55, 0.0), (0.0, 0.0)]),            # face to centre
             ("rapid", CNMG, [(0.0, 0.0), (0.0, 0.1)]),
             ("rapid", CNMG, [(0.0, 0.1), (0.45, 0.1)]),
             ("feed", CNMG, [(0.45, 0.1), (0.45, -0.5)]),           # turn
             ("feed", CNMG, [(0.45, -0.5), (0.55, -0.5)])]          # out along the shoulder
    run = run_material(stock, moves)
    assert run.warnings == []
    assert run.after[-1].area < stock.area


def test_rapid_into_stock_is_reported_and_a_graze_is_not():
    stock = stock_box(0.0, 0.5, -1.0, 0.0)
    crash = run_material(stock, [("rapid", CNMG, [(0.45, 0.1), (0.45, -0.5)])])
    assert [w[1] for w in crash.warnings] == ["rapid"]
    graze = run_material(stock, [("rapid", CNMG, [(0.5 - GRAZE / 4, 0.1), (0.5 - GRAZE / 4, -0.5)])])
    assert graze.warnings == []


def test_move_without_a_tool_shape_sweeps_nothing():
    stock = stock_box(0.0, 0.5, -1.0, 0.0)
    run = run_material(stock, [("feed", None, [(0.4, 0.1), (0.4, -0.5)])])
    assert run.cuts == [None] and run.after[-1].equals(run.stock)


HEADER = """%
; Industry CAM Engine - Generated Program
; Units: {units}
; Mode: {mode}
;
; === STOCK ===
; Diameter: {dia}
; X Start: 0.0000
; Z Start: 0.1000
; Z End: -1.0000
{pilot}
; === TOOL ===
; Tool Number: T4
"""


def test_header_stock_od_id_metric_and_missing():
    od = stock_from_header(HEADER.format(units="inch", mode="OD", dia="2.0000", pilot=";"))
    assert od.rect() == pytest.approx((0.0, 1.0, -1.0, 0.1))
    bore = stock_from_header(HEADER.format(units="inch", mode="ID", dia="4.0000",
                                           pilot="; Pilot Hole Dia: 2.8700\n;"))
    assert bore.rect() == pytest.approx((1.435, 2.0, -1.0, 0.1))
    mm = stock_from_header(HEADER.format(units="metric (mm)", mode="OD", dia="50.800", pilot=";"))
    assert mm.diameter == pytest.approx(2.0)
    assert stock_from_header("G0 X1 Z1\nM2\n") is None
    assert stock_from_header(HEADER.format(units="inch", mode="ID", dia="4.0000", pilot=";")) is None


def test_header_stock_face_line_wins_over_z_start():
    text = HEADER.format(units="inch", mode="OD", dia="2.0000", pilot="; Stock Face Z: 0.0000\n;")
    st = stock_from_header(text)
    assert st.face_known and st.rect()[3] == 0.0
    assert not stock_from_header(HEADER.format(units="inch", mode="OD", dia="2.0000", pilot=";")).face_known
