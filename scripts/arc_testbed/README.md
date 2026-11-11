Arc test bed (2026-11-10). Not imported by the app.
- nx_arc_profiles.py: walks tests/fixtures/nx_corner_break/{broken,id_broken}.stp
  and prints/saves the profile with every fillet as its own ARC segment (mm).
- OD_NX_arcs_noV1.json / ID_NX_arcs_no_undercut.json: those profiles as inch
  programs (OD: V1 chamfer removed - pre-existing comp-entry refusal; ID: the
  undercuts removed - pre-existing retract routing gouge).
- two_quadrant_cases/: OD/ID 180 deg bead and groove, OD 120 deg crest, each
  entered as two <=90 deg arcs.
- generate.py OUTDIR file.json...: headless pipeline + writer with fixed tools.
Check outputs with: rs274 -i industry-cam.ini -t tool.tbl -v <copy of .var> f.ngc out.txt
To become pytest fixtures in Phase 0 (see docs/handoffs/2026-11-10-arc-segment-strategy.md).
