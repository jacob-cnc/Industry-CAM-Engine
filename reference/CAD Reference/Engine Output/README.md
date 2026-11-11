# Engine Output reference programs

`Conv Tests/` - conversational programs (.json) with their generated G-code.
`GUI Conv Test` and `Corner Break Test` were regenerated 2026-11-10 after the
arc G-code fix (main 61fb77d, `outputs/gcode_dialect.py`) and switched from
T1 to T4 (CNMG): T1 is now a boring bar, which the Program tab refuses on an
OD profile. Both run to PROGRAM_END in LinuxCNC's interpreter (rs274).

**Old arc format - DO NOT RUN:** `Arc OD/Arc_OD.ngc`, `Arc OD/Arc_OD_Staircase.ngc`
and `Arc OD Contour/Arc_OD_Contour.ngc` are May 2026 outputs of the export
scripts (`scripts/_export_*.py`), kept only as historical comparison
references. Their G02/G03 use the pre-fix format (I as a diameter offset,
G2/G3 mirrored) and predate G7 diameter mode; LinuxCNC would reject them or
cut the wrong arcs. The other files in `Arc OD`, `ID Bore` and `Stepped OD`
have no arcs.
