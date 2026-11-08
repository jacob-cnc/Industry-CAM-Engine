# Tool offset units, wear persistence, and live table synchronization

Owner-authorized handoff from Claude, agent-sync 1443de7. Implementation base:
lathe/bench-2026-11-08 at 549bcc4. Classification: machine-control (tool offsets).
Software-verified only; no lathe deployment or measured-cut claim.

## Contract and implementation

- GUI X geometry and X wear remain diameter entry/display. ToolCardData stores
  radius; its existing conversion to/from CAM ToolDef diameter remains intact.
  The ToolDef docstring now distinguishes that CAM boundary from machine storage.
- File X is radius geometry + radius wear. File Z is geometry + wear in inches.
  File D remains actual nose diameter. Those numeric file fields are the applied
  source of truth; versioned comment metadata stores only the recoverable wear
  split plus existing descriptive data. Geometry is reconstructed as total-wear.
- Metadata schema `ice=2|xwear=...|zwear=...` survives a LinuxCNC rewrite, including
  changed applied totals. Parsing accepts reordered words and omitted zero fields.
  Descriptions/inserts are escaped, and oversized metadata is rejected rather than
  risking a truncated wear split. The full entry and the padded/six-decimal
  LinuxCNC rewrite must both fit CANON_TOOL_ENTRY_LEN=256 (emctool.h:26). This two-axis QCTP editor rejects nonzero extra
  axes, unsupported Q0 orientation, and P != T rather than silently remapping them.
- Both pipeline.tool_table_io and the older public pipeline.file_io APIs use the
  same serializer. No generator, simulation scaling, or G-code output is changed.

## Source evidence for comment preservation

Inspected official LinuxCNC v2.9.6 source at commit
68dfb4b1721cc8762309e8b49334549257074b7d, src/emc/tooldata/tooldata_common.cc:
tooldata_read_entry copies comments into ttcomments (around lines 214-217);
tooldata_format_toolline appends them to output (264-267); tooldata_save calls
write_tool_line with ttcomments (368-397). The formatter emits D before X/Z and
omits zero-valued fields, so the former fixed-order parser would not round-trip it.
No reference source was copied into application code.

## Live synchronization

Live path comes exclusively from [EMCIO] TOOL_TABLE in the active INI, resolved
against the INI directory, using INI_FILE_NAME or stat.ini_filename. An absent or
invalid live INI blocks loading/saving instead of falling back to another table.
Offline mode uses an existing remembered path or local tool.tbl. The settings
JSON is removed from Git tracking, retained locally, and ignored; both reading
and writing use the working directory's local convenience file.

Edits require INTERP_IDLE, MANUAL mode, no pause, and no cutter/dynamic tool
compensation. Active G43 must agree with the spindle tool's known offset.
The editor checks the table's hash before saving, retains a non-overwriting
backup, atomically writes combined offsets, then load_tool_table(), waits for
RCS_DONE, and checks controller tool IDs, offsets, nose diameter, angles and Q.
An already active G43 is reapplied with G43 H<spindle-tool> and verified, then
mode returns to MANUAL. G49 is left inactive. No tool motion is commanded.

On failure, disk contents are restored and controller rollback is attempted.
Unverifiable rollback blocks further edits and reports that controller/table
reload is required. The GUI restores the last accepted values after a rejected
edit. External G10/file rewrites cause a conflict instead of being overwritten;
use Load Table to reload/verify before editing again. Live Load Table always
uses the INI table. Save As exports without changing the live authoritative path.

Claude's _on_set_x_clicked, _on_set_z_clicked, _send_mdi_command and
_on_wear_offset_changed methods are unchanged (AST comparison verified). GUI wear
fields already connect to the general field-change/autosave path; no second G10
write is connected by this change.

## Legacy migration

Unversioned all-zero X tables can load safely and gain metadata on the next save.
Any unversioned nonzero X is flagged, including plain-description files from the
older API, since those cannot be distinguished reliably from native radius
tables. There is no automatic halving/doubling guess. Preserve a backup, reconcile
with actual machine offsets, then explicitly migrate offline:

```python
from pipeline.tool_table_io import create_backup, load_tool_table, save_tool_table
create_backup(path)
tools = load_tool_table(path, unversioned_x_units="radius")  # or "diameter", only after verification
save_tool_table(tools, path)
```

Do not run this migration while LinuxCNC is using the file. The existing checked-in
and reported lathe tables have X=0; neither table nor machine-local offsets were
modified during this work. Existing .bak files are preserved; subsequent backups
receive numbered names.

## Verification and commissioning

Tests cover radius-file/diameter-GUI round-trip, preserved wear after a geometry
autosave, LinuxCNC-style rewrite, native/legacy ambiguity and explicit migration,
both public serializers, INI path selection, stale Windows path fallback,
busy-controller rejection, active G43 refresh, differing active-offset rejection,
external-change detection, and failed reload rollback/blocking.

Claude should review the exact handed-off commit and regenerate/load the versioned
table only while idle. Preserve tool.tbl, existing backups, INI and work offsets.
With owner-approved limits and safe clearance, verify a known turned diameter,
then apply 0.002 diameter X wear (0.001 radius in file/controller), change another
field, restart/reload and verify the same split and combined total. Measure the
result before treating this as machine-verified. Check external G10 rewrite and
reload once on the installed 2.9.6 runtime. Abort unexpected motion, dimensional
change, controller error, or synchronization failure. Roll back software and the
matching preserved table together; do not overwrite machine-local G54 offsets.

Final software results: 43 focused tool-table/persistence cases pass in the full run. Full suite:
357 passed, the same six pre-existing quadrant-arc failures, 2 skipped, 2 xfailed,
2 xpassed. Architecture check: 69 errors, 179 warnings (existing source findings).
Eight-tab mock GUI smoke and git diff --check pass. No changes to outputs/,
Claude's four reserved methods, tool.tbl, INI, or HAL relative to 549bcc4.
