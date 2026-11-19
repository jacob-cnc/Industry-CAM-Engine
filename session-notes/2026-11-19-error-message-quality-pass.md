# Error-message quality pass (2026-11-19)

Branch `claude/run-from-open-race`, on top of 1254c9b (the Run-From open/abort
race and Edit-tab crash hardening). Owner's request, after that debug session:
"search for error messages that could use improvement."

Message text and the context carried in it. No motion, geometry, offsets, HAL,
INI or tool-table semantics changed. The one behaviour change is deliberate and
narrow: two failures that were previously log-only now show on screen.

## The standard applied

`validation/pre_planning_validator.py` was already the house standard -- every
finding carries a `message` with the actual numbers and a `recommendation`
saying what to do. The rest of the codebase was not held to it. 102 of 231
`raise` sites outside tests used a static string with no value, no row, no line
number. Those are the ones that cost a session to diagnose, because the message
names the rule that was broken and nothing about the input that broke it.

## What changed, and why these

### `tools/tool_table_io.py` -- the largest and worst cluster

`load_tool_table` re-raised a row error with **no indication of which row**.
A hand-edited `tool.tbl` produced, in a QMessageBox, exactly:

    Duplicate or non-finite tool table field.

for a file of any length. Now:

    tool.tbl line 4 was not loaded: X appears twice in this row (X0 and X1);
    LinuxCNC would use only one of them.

      T4 P4 X0 Z0 X1.5 D0.02 I60 J120 Q3 ;ice=2|xwear=0|zwear=0|desc=dup X

The file name, the line number (counting blanks and comments, so it matches a
text editor), the reason, and the offending row verbatim. Every field check in
`deserialize_tool`/`serialize_tool` now names the tool and the value: pocket
mismatch gives both P and T, a bad orientation gives the Q it found, an
oversized row gives its byte count and how many characters to cut.

`LegacyToolTableError` still propagates as itself so callers can still offer
the radius/diameter choice; everything else is re-raised as `ValueError`
(a wrapped `KeyError` would have displayed its message in quotes).

Also fixed while here: corrupt wear metadata (`xwear=abc`) escaped as a bare
`could not convert string to float: 'abc'` because `float()` ran before the
`isfinite` check. It now produces the intended message.

### `outputs/run_from_line.py` -- the path that failed on 2026-11-18

`if not 0 < start_index < len(lines)` raised one message for two unrelated
cases. Asking to run from line 1 -- the single most likely mistake -- answered
"Start line is outside the program", which is both confusing and false. Split:

- line 1 -> "Line 1 is the beginning of the program - press Cycle Start to run
  it from the top instead of running from a line."
- past the end -> names the line asked for and the program's actual length.

A canned-cycle refusal now names the cycle and the line that commanded it
(new `ModalState.motion_line`, set in `_apply_line`), and says the two ways
out. An unclosed `o` if-block names the o-number and its opening line
(`o_stack` now carries `(label, line)`).

New `describe_missing_n(text, n)`: the Run tab's "Block N45 was not found"
dialog now reports the range the program uses and the nearest blocks either
side, which is what the owner needs when typing a number off a printout.

### `gui/run_tab.py` -- two silent failures

`_start_from_line` and the Run From path ended a refused start with only
`logger.warning("program_run failed")`. The owner pressed Cycle Start, nothing
moved, and nothing appeared on screen. Both now call `show_error` and log the
task mode and interp state with it. This is the behaviour change in this
commit; it is the same failure shape as the 2026-11-18 incident.

### `gui/program_tab.py` -- saved program loading

`except json.JSONDecodeError:` discarded the exception and said "Not a valid
program file: <path>". `JSONDecodeError` carries `lineno`, `colno` and `msg` --
exactly what fixes a hand-edited file. Now reported. Every schema check names
the block ("Block 2 of 3 (id 1) ...") and the offending value, and the unknown
block-type / strategy messages list what is supported.

### Remaining files

- `pipeline/model_builder.py`: the stock-back-face refusal gives both Z values
  and the Z to set, instead of restating the rule.
- `geometry/zone_builder.py`: the two kernel failures give the stock and
  allowance dimensions and name the likely input cause. "Do NOT create a
  fallback" was a developer instruction in owner-facing text; it is now a code
  comment above the raise, where it belongs, with the reason.
- `outputs/gcode_writer.py`: the finish/spring count mismatch gives all four
  numbers; the coinciding-pass refusal names the pass and the per-pass depth.
- `models/params.py`, `hal/factory.py`: values in the message; the
  fall-back-to-mock warnings now say what it means for the operator ("the
  machine will NOT move and the position shown is not real") rather than
  naming a class.

## Verification

- Full suite on the lathe runtime, LinuxCNC down: **1539 passed, 0 failed**
  (1537 before the two new silent-failure tests; 1520 at 1254c9b).
- Architecture check: **15 errors / 130 warnings**, and the warning list is
  byte-identical to the pre-change tree. No new violations.
- `git diff --check` clean.
- Every reworded path was fired once and its output read: 34 engine/IO paths
  and 14 GUI paths, all formatted, none raising. This caught two defects in
  my own edits that the suite did not: an `UnboundLocalError` from using a
  later loop's index in the coinciding-pass message, and `fin_allowance` read
  off `finishing_params` where it lives on `roughing_params`. Both would have
  turned a clean refusal into a crash on a rare path.

## Tests

- `tests/unit/test_error_message_context.py` (new, 17 cases) pins the context
  into the text: the tool.tbl line number and row, T/P/Q values, the Run-From
  line-1 and past-end split, the canned cycle and its line, the o-block
  opening line, the N range and neighbours, and both Z values on the stock
  back face. These fail if a later edit drops the facts back out.
- `tests/unit/test_run_from_open_guard.py` (+2) covers the two formerly
  silent refusals.
- Eight existing `pytest.raises(match=...)` regexes were retargeted to the new
  wording. Each still names the specific failure, not just any `ValueError`.
- `test_run_from_open_guard.py`'s fixture was order-dependent: it stepped the
  estop sequence on the shared `get_backend()` singleton, which only works
  from `ESTOP_RESET`, and `MockBackend.state` returns a `MachineState` built
  by `poll()`, so raw attribute writes were invisible without it. It now sets
  the state and polls. The 4 setup errors this caused under the full run are
  gone.

## Not done

- `hal/factory.py` still falls back to `MockBackend` with only a log line. The
  GUI's "Offline preview mode" dialog fires on `INDUSTRY_CAM_OFFLINE_REASON`
  from the launcher, so a fallback caused by NML being down rather than by Mesa
  not coming up is **not** announced on screen. That is a behaviour change, not
  a message change, and it is safety-adjacent: left for the owner to decide.
- `_state_async`'s "command accepted (5.00 s)" after a 5 s timeout (flagged in
  the 2026-11-18 note) is still unchanged, for the same reason.
- No machine verification. Nothing here changes motion, but the Run tab's two
  new on-screen errors have been exercised only against the mock backend.
