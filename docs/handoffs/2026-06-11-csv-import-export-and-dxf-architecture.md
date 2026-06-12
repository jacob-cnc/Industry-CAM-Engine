# Session: 2026-06-11 - CSV Import/Export & DXF Architecture Discussion

## Workstream

Branch: main
Commit: e741cac (repo synced to origin/main) + uncommitted local changes
Environment: Windows development (offline mode)
Change classification: Software-only

## Starting State

- SegmentListWidget existed with Add/Remove/Move Up/Move Down buttons
- `get_segments()` and `set_segments()` already used a dict format identical to
  the shared NX Point Manager CSV format
- No file-based segment exchange capability existed
- No DXF import capability existed (export only via `outputs/dxf_exporter.py`
  for PlanResult toolpath visualization)
- Program tab supports one segment list, one block type (OD or ID) at a time
- No multi-toolpath-per-program architecture yet

## Goal and Acceptance Criteria

- Goal: Add CSV import/export to SegmentListWidget for NX Sketch Point Manager
  integration, then discuss DXF import/export architecture.
- Acceptance criteria:
  - CSV Export button writes `type,x,z,radius` format from `get_segments()`
  - CSV Import button reads the same format and calls `set_segments()`
  - Default file location is `point_charts/` folder at project root
  - Architectural direction for DXF import/export is documented

## Changes Made

1. **CSV Import/Export buttons** added to `gui/components/segment_list.py`:
   - `_on_export_csv()`: Writes header + segment rows with 4-decimal precision
   - `_on_import_csv()`: Parses CSV, skips header, handles malformed rows
   - Buttons placed right-side of button bar after a stretch spacer
   - Added `QFileDialog` and `QMessageBox` imports
   - Added `os` import for path resolution

2. **`point_charts/` folder** created at project root:
   - `README.md` documents the CSV format
   - `.gitignore` updated to exclude `point_charts/*.csv` (data files ignored,
     README tracked)

3. **File dialog defaults** point to `point_charts/` folder for both import and
   export operations.

## Evidence and Measurements

- **Verified:** All 157 existing tests pass after changes (`python -m pytest
  tests/ -q` — 157 passed, 11 warnings in 15.44s)
- **Verified:** `segment_list.py` parses cleanly (`ast.parse` — Syntax OK)
- **Verified:** No diagnostics (lint/type errors) reported on modified file
- **Observed:** The CSV format is a direct serialization of the
  `get_segments()`/`set_segments()` dict format — no unit conversion or sign
  remapping required on the CAM engine side

## Verification Performed

| Check | Result | Notes |
|---|---|---|
| Focused tests | N/A | No existing segment_list tests; CSV methods are UI-triggered |
| Full tests | Pass (157/157) | No regressions |
| Architecture checks | Not run | No architecture-layer changes |
| Ground-truth comparison | N/A | |
| G-code round-trip | N/A | No pipeline changes |
| Offline LinuxCNC/mock | Not tested | GUI not launched this session |
| Physical machine | N/A | Software-only change |

## Safety Impact

None. CSV import/export is purely a file I/O feature on the GUI input side. It
does not affect G-code generation, toolpath planning, or machine motion. Segment
data passes through the same `set_segments()` path that manual editing uses.

## Deployment and Rollback

Deployment commit: Not yet committed (changes are local, working tree dirty)
Preserved machine-state files: N/A
Rollback location/commit: e741cac (pre-change state)

## Decisions

1. **CSV buttons live on SegmentListWidget** (not program_tab) because
   `get_segments()`/`set_segments()` are already on that widget.

2. **DXF import/export deferred** until multi-toolpath-per-program architecture
   is implemented. Rationale: a complete DXF part naturally contains both OD and
   ID profiles, but the current program tab only holds one segment list for one
   block type at a time. Implementing DXF properly requires the program to store
   multiple profiles simultaneously.

3. **Layer-based separation** is the agreed direction for DXF when implemented:
   - Layer `OD` / `PROFILE_OD` → OD turning profile
   - Layer `ID` / `PROFILE_ID` → bore profile
   - Layer `STOCK` → optional stock boundary for auto-fill
   - Layer `0` → fallback (import all entities as current block type)

4. **Shared geometry I/O module** (`geometry/profile_io.py` or `io/profile_io.py`)
   is the preferred architecture for DXF/CSV/future format handling — keeps
   parsing logic testable without Qt, reusable by scripts.

## Known Problems and Risks

- The CSV import/export has not been manually tested in the running GUI yet
  (only verified via syntax/test-suite checks).
- No unit tests exist for the CSV round-trip path. Should be added when test
  infrastructure for SegmentListWidget is built.
- DXF entity chaining (ordering unordered LINE/ARC entities into a continuous
  wire) is the main complexity for future DXF import. Will need endpoint
  matching within tolerance and branch/disconnection detection.

## Exact Next Step

**Prerequisite for DXF import:** Implement multi-toolpath-per-program
architecture so a single program can hold both OD and ID profiles (and
potentially multiple operations: rough, finish, thread, groove). This unblocks:

1. DXF import that reads OD + ID layers into their respective profile slots
2. DXF export of the complete part definition
3. The `geometry/profile_io.py` module (read_csv, write_csv, read_dxf, write_dxf)

**Immediate follow-up (independent of DXF):**
- Commit the CSV import/export + point_charts folder changes
- Manually test the Import/Export CSV buttons in the running GUI
- Confirm round-trip: export segments → import the same file → segments match
