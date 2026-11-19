"""Error messages must carry the facts needed to act on them.

Every assertion here is about an error the owner reads at the machine: which
row of tool.tbl, which block of the saved program, which line of the G-code,
and what the numbers actually were. A message that only names the rule
("invalid tool table field") costs a debugging session, so these tests pin the
context into the text and fail if a later edit drops it.
"""
import pytest

from models.params import FinishingParams
from outputs.run_from_line import RunFromError, build_resume_program, describe_missing_n
from pipeline.model_builder import build_from_fields
from tools.tool_card_data import ToolCardData
from tools.tool_table_io import load_tool_table, save_tool_table, serialize_tool


def _tool(number=2, **kw):
    fields = dict(nose_radius=.016, front_angle=62.5, back_angle=117.5,
                  x_offset=.5, z_offset=-.25, x_wear=.001, z_wear=-.002)
    fields.update(kw)
    return ToolCardData(number, "Boring Bar", "DCMT", 5, "boring", **fields)


# --------------------------------------------------------------------------
# tool.tbl — the owner edits this file by hand and through the Tools tab
# --------------------------------------------------------------------------

def test_bad_tool_row_names_the_file_line_and_shows_the_row(tmp_path):
    path = tmp_path / "tool.tbl"
    path.write_text(
        "; a comment\n"
        "T1 P1 X0 Z0 D0.02 I60 J120 Q3 ;ice=2|xwear=0|zwear=0|desc=good\n"
        "\n"
        "T4 P4 X0 Z0 X1.5 D0.02 I60 J120 Q3 ;ice=2|xwear=0|zwear=0|desc=dup X\n"
    )
    with pytest.raises(ValueError) as err:
        load_tool_table(str(path))
    message = str(err.value)
    assert "line 4" in message, message          # not "line 2" (blank/comment skipped)
    assert "tool.tbl" in message
    assert "X appears twice" in message
    assert "T4 P4 X0 Z0 X1.5" in message         # the offending row, verbatim


def test_missing_orientation_names_the_tool_and_what_q_means(tmp_path):
    path = tmp_path / "tool.tbl"
    path.write_text("T7 P7 X0 Z0 D0.02 I60 J120 ;ice=2|xwear=0|zwear=0|desc=no Q\n")
    with pytest.raises(ValueError) as err:
        load_tool_table(str(path))
    message = str(err.value)
    assert "T7" in message
    assert "no Q word" in message
    assert "Q1" in message and "Q9" in message


def test_pocket_mismatch_names_both_numbers(tmp_path):
    path = tmp_path / "tool.tbl"
    path.write_text("T3 P5 X0 Z0 D0.02 I60 J120 Q3 ;ice=2|xwear=0|zwear=0|desc=x\n")
    with pytest.raises(ValueError) as err:
        load_tool_table(str(path))
    assert "P5" in str(err.value) and "T3" in str(err.value)


def test_duplicate_rows_name_the_tool(tmp_path):
    row = "T2 P2 X0 Z0 D0.02 I60 J120 Q3 ;ice=2|xwear=0|zwear=0|desc=x\n"
    path = tmp_path / "tool.tbl"
    path.write_text(row + row)
    with pytest.raises(ValueError) as err:
        load_tool_table(str(path))
    assert "T2" in str(err.value)
    assert "line 2" in str(err.value)


def test_saving_duplicate_numbers_names_them(tmp_path):
    with pytest.raises(ValueError) as err:
        save_tool_table([_tool(2), _tool(2), _tool(5)], str(tmp_path / "t.tbl"))
    message = str(err.value)
    assert "T2" in message
    assert "T5" not in message                   # only the duplicate is named


def test_oversized_row_says_how_much_to_cut():
    oversized = _tool(2)
    oversized.description = "x" * 95
    with pytest.raises(ValueError) as err:
        serialize_tool(oversized)
    message = str(err.value)
    assert "T2" in message
    assert "stores only 255" in message
    assert "1 character." in message             # singular, not "1 characters"


def test_invalid_q_on_save_reports_the_q_value():
    bad = _tool(2)
    bad.orientation = 0
    with pytest.raises(ValueError) as err:
        serialize_tool(bad)
    assert "Q0" in str(err.value) and "T2" in str(err.value)


# --------------------------------------------------------------------------
# Run From — the path that ran the wrong file on 2026-11-18
# --------------------------------------------------------------------------

_PROGRAM = "\n".join([
    "N10 G7 G18 G21",
    "N20 T1 M6",
    "N30 G97 S500 M3",
    "N40 G0 X1.0 Z0.1",
    "N50 G1 X0.9 F0.004",
    "N60 G0 X2.0 Z2.0",
])


def test_line_one_is_not_reported_as_outside_the_program():
    with pytest.raises(RunFromError) as err:
        build_resume_program(_PROGRAM, 0)
    message = str(err.value)
    assert "Cycle Start" in message               # tells them what to press
    assert "outside the program" not in message


def test_past_the_end_gives_the_line_count():
    with pytest.raises(RunFromError) as err:
        build_resume_program(_PROGRAM, 99)
    message = str(err.value)
    assert "100" in message                       # the line they asked for
    assert "6 lines" in message                   # what the program actually has


def test_blank_start_line_names_the_line():
    text = _PROGRAM.replace("N50 G1 X0.9 F0.004", "   ")
    with pytest.raises(RunFromError) as err:
        build_resume_program(text, 4)
    assert "Line 5" in str(err.value)


def test_canned_cycle_refusal_names_the_cycle_and_where_it_started():
    text = "\n".join([
        "N10 G7 G18",
        "N20 G97 S500 M3",
        "N30 G81 X1.0 Z-0.5 R0.1 F0.004",
        "N40 X1.2",
    ])
    with pytest.raises(RunFromError) as err:
        build_resume_program(text, 3)
    message = str(err.value)
    assert "G81" in message
    assert "line 3" in message                   # where the cycle was commanded
    assert "G80" in message                      # and the way out


def test_unclosed_o_block_names_the_opening_line():
    # No modal words inside the block: those trip an earlier, different refusal.
    text = "\n".join([
        "N10 G7 G18",
        "o100 if [#5399 EQ 1]",
        "N30 X1.0",
        "N40 Z-1.0",
    ])
    with pytest.raises(RunFromError) as err:
        build_resume_program(text, 3)
    message = str(err.value)
    assert "o100" in message
    assert "line 2" in message


def test_missing_n_number_reports_the_range_and_neighbours():
    message = describe_missing_n(_PROGRAM, 45)
    assert "N45" in message
    assert "N10" in message and "N60" in message  # the range present
    assert "N40" in message and "N50" in message  # the nearest blocks


def test_missing_n_number_past_the_end_names_the_last_block():
    message = describe_missing_n(_PROGRAM, 900)
    assert "N900" in message
    assert "last block is N60" in message


def test_missing_n_number_without_any_n_words_says_so():
    assert "no N block numbers" in describe_missing_n("G0 X1\nG1 Z-1\n", 10)


# --------------------------------------------------------------------------
# Owner-entered numbers come back with the numbers in the message
# --------------------------------------------------------------------------

def _fields(**changes):
    """The bore job from tests/integration/test_operation_depth.py."""
    from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
    fields = dict(
        segments=[dict(type="line", x=3.117, z=0), dict(type="line", x=3.117, z=-0.568)],
        stock_dia=4, x_start=3.117, z_start=0.05, z_end=-99,
        stock_back_z=-1, mode="id", pilot_hole_dia=2.995,
        doc_dia=0.02, feed=0.003, strategy="staircase", fin_allowance=0.002,
        peck_enabled=False, peck_length=None, spindle_rpm=300,
        finish_passes=1, finish_doc_dia=0.002, finish_feed=0.002,
        tool_def=ToolDef(1, 0.008, 55, 0.25, ToolOrientation.ID_FRONT_RIGHT,
                         ToolDirection.RIGHT, ToolType.BORING),
    )
    fields.update(changes)
    return fields


def test_stock_back_face_error_shows_both_z_values():
    with pytest.raises(ValueError) as err:
        build_from_fields(**_fields(stock_back_z=-0.4))
    message = str(err.value)
    assert "-0.4000" in message                   # what they entered
    assert "-0.5680" in message                   # where the profile cuts to


def test_finish_pass_count_error_shows_what_was_given():
    with pytest.raises(ValueError) as err:
        FinishingParams(passes=0)
    assert "Got: 0" in str(err.value)
