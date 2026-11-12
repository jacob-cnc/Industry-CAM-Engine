# Regression: what does a code change do to real programs?

Two scripts, for refactors and any change that may alter generated G-code.

1. `regen.py` regenerates saved programs (.json from the Program tab) exactly
   like the GUI's Generate button (a real ProgramTab, Qt offscreen) and records
   the G-code plus the cut sections from LinuxCNC's own interpreter
   (`outputs/cut_regions.py`: nose circle + insert wedge swept along the path
   rs274 really runs; face / rough / cleanup / finish / finished part / uncut /
   gouge / not removed). Dialogs the GUI would show are recorded and answered
   with their default. Refuses to run while LinuxCNC is up.
2. `compare.py BASE NEW` compares two runs like a machinist: same text,
   comments only, motion changed but the finished part identical (no new gouge
   or left material), or PART-CHANGED (stop and look).

Typical use (baseline from a detached worktree of main):

    git worktree add --detach /tmp/wt-base main
    regen.py --repo /tmp/wt-base --tool-table ~/linuxcnc/configs/industry-cam/tool.tbl \
             --out /tmp/base  <programs...>
    regen.py --tool-table ~/linuxcnc/configs/industry-cam/tool.tbl --out /tmp/new <programs...>
    compare.py /tmp/base /tmp/new

Corpus used 2026-11-12 (21 programs): reference/CAD Reference/Engine Output/**.json,
~/Desktop/CNC Program Files/**.json (the GCH programs the owner ran, the NX
corner-break set, the T4 regenerations), and four "(T4 derived)" copies of old
reference programs whose T1 is now a boring bar (roughing/finishing tool 1 -> 4,
as the owner did for the T4 copies). Generation is deterministic: two runs of
the same code compare SAME for all of them.

The list is `corpus.txt` (paths relative to the repo, or absolute for the owner's
Desktop programs); the derived copies are in `corpus/`. Run with:

    mapfile -t P < scripts/regression/corpus.txt
    regen.py --tool-table ... --out DIR "${P[@]}"
