# Session: 2026-06-12 - Multi-Toolpath & Threading Implementation (REVERTED)

## Workstream

Branch: main (working tree only — nothing committed)
Commit: None — all changes reverted to match GitHub HEAD
Environment: Windows offline development
Change classification: Motion-affecting (threading G-code generation)

## Starting State

Program tab supported single OD/ID profile toolpath per program. Threading and
Grooving block types were disabled in the combo box. No multi-toolpath support.

## Goal and Acceptance Criteria

- Goal: Add support for multiple toolpaths per program, implement threading
  toolpath with G76 cycle generation, standard thread size lookup with
  tolerance bands (LMC/MMC/Mid), and sim visualization of threading.
- Acceptance criteria: Generate valid multi-toolpath G-code, proper G76
  parameters from standard thread specs, sim playback shows threading passes.

## Changes Made (ALL REVERTED)

The following was implemented then fully reverted due to reckless integration
that broke existing functionality:

### Multi-Toolpath System
- `gui/components/toolpath_list.py` — Collapsible list widget with add/remove/
  reorder (▲▼) controls, 44px touch targets
- Program tab modified to support multiple toolpaths with per-toolpath data
  storage, selection switching, and combined G-code generation
- File format v2: `{"version": 2, "toolpaths": [...]}`
- Backward-compatible loading of v1 single-toolpath files

### Threading Implementation
- `models/threading.py` — ThreadingParams dataclass, ThreadStandard/Direction/
  InfeedStrategy enums, depth computation, constant-area pass progression
- `models/thread_specs.py` — ASME B1.1 tolerance computation (class 1A/2A/3A),
  ISO 965 metric, ACME B1.5. Standard size database (UNC/UNF interleaved by
  diameter, metric coarse+fine, ACME). `resolve_thread_spec()` function.
- `outputs/threading_writer.py` — G76 G-code generation with NPT taper support,
  multi-start, chamfer lead-out, retract clearance above major dia
- Threading UI panel with: Size dropdown (standard sizes + Custom), Fit
  (MMC/Mid/LMC), Class (1A/2A/3A), Direction, Z Start/End, Infeed strategy,
  Passes, Spring passes, RPM, Tool, Chamfer, Starts
- G76 sim expansion in `parse_gcode_for_sim` — expands G76 into rapid/feed
  SimMoves for visualization

### Other Changes
- Z End field hidden (auto-derived from last segment Z)
- X Park / Z Park fields added to Stock section
- Generate button always enabled (validation on click with guidance)
- Help tab threading documentation
- `graph_threading` color (#E5B84C gold) added to palette
- Play button resets after Show All

## Mistakes Identified by User

### 1. Broke segment highlighting
The toolpath segment rebuild from sim_moves destroyed the PlanResult-based
color-coded segments (face/rough/cleanup/finish) that the graph widget uses
for progressive reveal during playback. The index correspondence between
toolpath_segments and sim_moves was broken.

### 2. Broke corner break options
User reports corner break options were removed. Investigation showed corner
breaks were never exposed in the Program tab UI (only in the data model), but
the user asserts they were present — indicating I failed to properly audit
existing functionality before making changes.

### 3. Sim expansion visible in G-code panel
Initial implementation put expanded G0/G1 moves after M2 in the G-code text,
visible to the user. This was confusing and reduced confidence. Later fixed to
parser-side expansion, but the initial approach was wrong.

### 4. Threading sim not displaying
G76 expansion in the sim parser worked but the graph wasn't rendering the
threading lines because graph_data segments were empty for threading-only
programs.

### 5. Wrong X diameter during threading
Tool was positioned at safe_x (major + clearance) when G76 was called, but
the sim parser used current_x as the thread start position, causing incorrect
pass depths in visualization.

### 6. Thread retraction dragging across crests
G76 retract position was set to major_dia (surface of thread) instead of
major_dia + clearance, meaning the tool would drag across thread crests
between passes.

### 7. Diagonal retracts not visually rendering
The toolpath segment rebuild from sim_moves broke the 1:1 correspondence
between graph segments and reveal indices, causing diagonal rapids to display
as vertical + horizontal.

### 8. Test program had X=0 first segment
The conv test program's profile started at X=0 Z=0, which caused the engine
to rough all the way to centerline (9 passes to X=0.015). This was a data
error, not a code bug.

## Verification Performed

| Check | Result | Notes |
|---|---|---|
| Focused tests | N/A | Reverted |
| Full tests | 157 passed | Passed throughout but UI was broken |
| Architecture checks | Pre-existing failures | 45 errors, none from new code |
| Ground-truth comparison | N/A | |
| G-code round-trip | N/A | |
| Physical machine | N/A | |

## Safety Impact

Motion-affecting: threading G-code generation directly controls synchronized
spindle motion. The G76 parameters (depth, pitch, retract) must be correct.
The retraction bug (dragging across crests) would damage threads on a real
machine. The X=0 profile bug would crash the tool into the centerline.

## Deployment and Rollback

Deployment commit: None — all reverted
Rollback: `git checkout -- .` completed, working tree matches GitHub HEAD

## Decisions

- Multi-toolpath architecture (toolpath list + per-toolpath data) is sound
- Threading spec database approach (standard sizes + tolerance bands) is correct
- G76 expansion should live in the sim parser (not the writer) — Option A
- Thread retract must clear major dia by 0.020" minimum
- Z End should be auto-derived from segments (no user field)

## Known Problems and Risks

- Corner break UI needs to be located and verified before any future work
- Segment highlighting / toolpath reveal mechanism needs audit — the index
  correspondence between PlanResult.tool_moves and parsed SimMoves is fragile
- Any future multi-toolpath implementation must NOT rebuild toolpath_segments
  from sim_moves — this destroys pass-type coloring

## Exact Next Step

1. Audit existing segment highlighting and corner break functionality — read
   the ACTUAL current state of gui/program_tab.py and gui/components/ to
   understand what features are present BEFORE making changes
2. Re-implement multi-toolpath and threading as INCREMENTAL additions that
   do not modify existing OD/ID profile generation, segment list, graph
   rendering, or sim playback code paths
3. Test each change against the existing Conv Test programs to verify no
   regression before proceeding to the next feature
