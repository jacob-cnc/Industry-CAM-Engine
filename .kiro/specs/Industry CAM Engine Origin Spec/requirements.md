# Requirements Document

## Introduction

This document specifies the architecture for Industry CAM Engine, a ground-up rebuild of the my-lathe CAM engine. The rebuild preserves the proven strengths of the current system (visual confirmation, robust debugging, property-based testing, Build123d kernel as single source of truth) while eliminating the structural weaknesses that caused repeated bugs (hand math, sign confusion, dual code paths, implicit assumptions).

All zone definitions, program execution rules, and tool movement constraints are defined in #[[file:.kiro/steering/zone-mental-model.md]] and apply to every requirement in this document.

Machining formulas, cutting parameters, and thread data are defined in #[[file:.kiro/steering/machining-formulas.md]] and #[[file:.kiro/steering/thread-data.md]]. These provide the computational basis for feed/speed calculations, threading operations, and tool geometry validation.

The GUI color system, semantic color assignments, and accessibility rules are defined in #[[file:.kiro/steering/gui-color-system.md]]. All UI implementation must follow this palette.

The round-trip validation chain, no-fallback enforcement, and testing structure are defined in #[[file:.kiro/steering/round-trip-testing.md]]. All zone coordinate extraction must follow this chain — no hand math, no fallbacks.

The architecture is informed by industry-standard open-source CAM codebases:
- **OpenCamLib** — Fiber/Interval pattern, adaptive sampling via cosine-limit predicate, separation of boundary-finding from path-ordering
- **Bapt_CAM** — Peel milling (offset-contour roughing), explicit transition management, position-tracking G-code writer, stock clipping
- **liblathe** — Lathe-specific operation patterns, tool-as-geometry, inline gouge checking, segment group validation
- **FreeCAD Turning Addon** — Tool parameter flow from UI to engine, operation bridging patterns

## Glossary

- **Fiber**: A query line at a fixed coordinate (X or Z) that collects material Intervals where it passes through a zone Face. Modeled after OpenCamLib's Fiber class.
- **Interval**: A contiguous region of material along a Fiber, with merge/containment/gap operations. Modeled after OpenCamLib's Interval class.
- **OffsetContour**: A single equidistant offset of the finish profile, representing one roughing pass boundary. Modeled after Bapt_CAM's peel milling approach.
- **Transition**: The movement between two cutting passes — either a perpendicular link (tool stays engaged) or a retract-traverse-plunge sequence. Modeled after Bapt_CAM's `_pass_transitions`.
- **ToolShape**: The physical geometry of the cutting tool (nose radius, tip angle, edge length, orientation), represented as a segment group for intersection testing. Modeled after liblathe's Tool class.
- **FlatnessPredicate**: A cosine-limit criterion that determines whether adjacent boundary samples are collinear enough to skip intermediate sampling. Modeled after OpenCamLib's `AdaptiveWaterline::flat()`.
- **ZoneQueryAPI**: The direct geometric query interface wrapping OCCT operations against Build123d 2D Faces. Retained from my-lathe.
- **SweptRegion**: The material volume removed by a single pass, defined by the pass boundaries and the previous pass floor. Required for engagement angle computation.
- **GoalContour**: The target surface for a pass — either the Roughing Boundary (for roughing) or the Profile Boundary (for finishing).

## Design Principles

### P1: Top-Down Rule Propagation
Define rules at the highest level (e.g., "tool must never enter Finished Part") and let them propagate downward to cover all geometric cases. No per-case special handling. If a rule doesn't cover a case, the rule is wrong — not the case. If flexibility is needed the user MUST give explicit permission based on the case. 

### P2: Geometry Kernel as Single Source of Truth
All geometric answers come from Build123d/OCCT. No hand math for coordinates, offsets, or intersections. If the kernel can't answer a question, the question is reformulated — not answered by arithmetic. Avoid OCCT tolerance issues when possible. 

### P3: One Path, One Implementation
Every operation has exactly one code path. No legacy fallbacks, no dual implementations, no "try A, fall back to B." If the implementation fails, it raises — never silently degrades.

### P4: Tool as Geometry
The tool is not a scalar (nose radius). It is a geometric shape that participates in offset computations, reach analysis, and interference checking. The tool shape flows from UI to engine as a first-class object.

### P5: Explicit Over Implicit
Transitions between passes are named objects. Interval merging is a method call, not inline arithmetic. Pass boundaries come from queries, not formulas. Every coordinate has a traceable origin.

### P6: Validate at Every Boundary
- Model builder validates profile geometry before engine sees it
- Engine validates zone construction before planner sees it
- Planner validates pass safety before formatter sees it
- Formatter validates G-code geometry before output

### P7: Separation of Boundary-Finding from Path-Ordering
Finding where material exists (Fiber/Interval queries) is a separate concern from deciding what order to cut it (pass sequencing, transition planning). These are different modules with different responsibilities.

## Requirements

### Requirement 1: Module Structure

**User Story:** As a developer, I want a clean module hierarchy where each module has exactly one responsibility and zero circular dependencies.

#### Acceptance Criteria

1. THE project SHALL have the following top-level module structure:
   ```
   Industry CAM Engine/
   ├── models/          # Pure dataclasses, zero dependencies
   ├── geometry/        # Build123d zone construction + query API
   ├── intervals/       # Fiber and Interval classes (boundary finding)
   ├── planners/        # Pass planning (turning, face, cleanup, finish)
   ├── transitions/     # Retract/approach/link logic between passes
   ├── tools/           # Tool geometry and reach analysis
   ├── validation/      # Shapely-based runtime safety checking + polygon builder
   ├── outputs/         # G-code writer, graph adapter, DXF, SVG, simulation adapter
   ├── pipeline/        # Orchestration (wires modules together)
   ├── gui/             # PyQtGraph visualization, Program Tab, Debug Tab (imports outputs/ only)
   └── tests/           # Property-based tests, oracle, ground truth
   ```

2. EACH module SHALL import only from modules above it in this dependency order:
   `models → tools → geometry → intervals → planners → transitions → validation → outputs → pipeline → gui`

3. NO module SHALL import from `pipeline/` except the entry point (UI or test harness) and `gui/`

4. THE `models/` module SHALL have ZERO external dependencies (no Build123d, no OCCT, no PyQt, no Shapely)

5. THE `geometry/` module SHALL be the ONLY module that imports Build123d or OCCT

6. THE `intervals/` module SHALL depend only on `models/` and `geometry/` — it wraps kernel queries into Fiber/Interval objects

7. THE `validation/` module SHALL be the ONLY module that imports Shapely. It depends on `geometry/` (for boundary_wire_extraction) and `models/` (for dataclasses)

8. SHAPELY SHALL be a RUNTIME dependency (listed in `requirements.txt`, not just `requirements-test.txt`). The system SHALL NOT generate G-code without Shapely validation passing.

9. THE `gui/` module SHALL be the ONLY module that imports PyQtGraph or any Qt GUI classes. It depends on `outputs/` (for graph_adapter) and `pipeline/` (for execute entry point). No engine module shall import from `gui/`.

10. THE `outputs/graph_adapter.py` SHALL NOT import PyQtGraph or Qt — it produces plain coordinate arrays and metadata that the `gui/` layer consumes. This keeps the adapter testable without a display server.

### Requirement 2: Interval and Fiber Classes

**User Story:** As a developer, I want first-class Interval and Fiber objects that handle merging, containment, and gap detection, so that pass planning logic is clean and correct.

#### Acceptance Criteria

1. THE `Interval` class SHALL represent a contiguous material region with `z_start` (higher Z) and `z_end` (lower Z) boundaries

2. THE `Interval` class SHALL implement:
   - `contains(other: Interval) -> bool` — true if other is fully inside self
   - `overlaps(other: Interval) -> bool` — true if any overlap exists
   - `merge(other: Interval) -> Interval` — union of two overlapping intervals
   - `gap(other: Interval) -> float` — distance between non-overlapping intervals
   - `length` property — `z_start - z_end`

3. THE `Fiber` class SHALL represent a query line at a fixed X level (diameter) that collects Intervals

4. THE `Fiber` class SHALL implement:
   - `add_interval(interval: Interval)` — adds with automatic merge of overlapping intervals (modeled after OpenCamLib `Fiber::addInterval`)
   - `intervals` property — sorted list of non-overlapping Intervals
   - `material_at(z: float) -> bool` — point-in-material test
   - `total_material_length` property — sum of all interval lengths

5. THE `Fiber` class SHALL obtain its intervals from `ZoneQueryAPI.boundary_at_x()` — never from manual computation

6. WHEN two intervals overlap, `add_interval` SHALL merge them into a single interval spanning both (no duplicates, no gaps within tolerance)

7. THE tolerance for interval merging SHALL be `TOLERANCE = 0.0005"` (matching LinuxCNC arc tolerance)

### Requirement 3: Offset-Contour Roughing Strategy

**User Story:** As a machinist, I want roughing passes that follow the profile shape at constant offset distances, so that engagement angle stays consistent and tool life is preserved.

#### Acceptance Criteria

1. THE roughing planner SHALL support two strategies selectable by the user:
   - **Staircase** (constant-X passes with variable Z boundaries) — current proven approach
   - **Offset-Contour** (equidistant offsets from profile, clipped to stock) — new adaptive approach

2. WHERE offset-contour strategy is selected, THE planner SHALL generate passes by:
   a. Offsetting the keep_zone boundary outward by DOC increments toward stock
   b. Clipping each offset contour to the stock boundary
   c. Each clipped contour becomes one roughing pass

3. WHERE offset-contour strategy is selected, THE planner SHALL produce passes where the tool follows the profile shape (arcs remain arcs, lines remain lines) rather than constant-X horizontal cuts

4. WHERE offset-contour strategy is selected, THE engagement angle SHALL be approximately constant across all passes (within 1.2x of nominal, matching Requirement 5 from next-gen-cam-engine spec)

5. THE staircase strategy SHALL produce identical output to the current my-lathe implementation (regression safety)

6. BOTH strategies SHALL satisfy the two hard rules: all material removed, no gouge of keep zone

7. THE offset-contour strategy SHALL use the geometry kernel's `offset()` operation for contour generation — never manual coordinate shifting

8. THE roughing planner SHALL support an optional **peck roughing** mode, selectable by the user:
   - **Enabled/Disabled** toggle (default: disabled)
   - **Peck length** input field (inches, along the Z-axis feed direction)
   - WHEN enabled, each roughing pass SHALL pause (dwell) at intervals of the peck length along the pass
   - THE dwell SHALL be 5 spindle rotations (computed from current RPM: `dwell_seconds = 5 / RPM * 60`)
   - THE dwell is implemented as a G04 (dwell) command in the G-code output at each peck interval
   - THE purpose is chip breaking — the momentary pause allows the chip to separate cleanly, improving chip control in materials that produce long stringy chips
   - Peck roughing applies to BOTH staircase and offset-contour strategies
   - THE peck intervals are measured along the toolpath (Z travel for staircase, contour distance for offset-contour)
   - THE dwell does NOT retract the tool — it pauses in place (this is a chip-breaking dwell, not a peck-drill retract cycle)

### Requirement 4: Tool as Geometry

**User Story:** As a machinist, I want the engine to understand my tool's physical shape, so that it can compute TNR-compensated paths and detect unreachable geometry.

#### Acceptance Criteria

1. THE `ToolDef` dataclass SHALL contain:
   - `nose_radius: float` — tool nose radius (inches)
   - `tip_angle: float` — included angle of the insert (degrees)
   - `edge_length: float` — cutting edge length (inches)
   - `orientation: ToolOrientation` — X or Z axis orientation
   - `direction: ToolDirection` — R (right), L (left), N (neutral)
   - `rotation: float` — tool rotation about tip (degrees, 0-360)

2. THE `ToolShape` class SHALL compute the tool's physical geometry as a segment group (modeled after liblathe's `Tool.get_segmentgroup()`)

3. THE `ToolShape` class SHALL provide:
   - `get_reach_boundary() -> SegmentGroup` — the envelope of positions the tool tip can reach given the tool's physical constraints
   - `get_compensation_offset(profile_segment, mode) -> float` — the TNR offset distance for a given profile segment direction
   - `can_reach(x_dia, z, profile_curvature) -> bool` — whether the tool can physically cut at this position given the local geometry

4. WHEN `nose_radius > 0`, THE pipeline SHALL offset the roughing boundary by `fin_allowance` only. TNR compensation is handled by LinuxCNC's cutter compensation (G41/G42) at runtime using the tool table's nose radius and orientation — NOT by the engine's coordinate computation.

5. WHEN `nose_radius > min_concave_radius` in the profile, THE pipeline SHALL produce a WARNING (not ERROR) indicating the tool may not cleanly finish tight concave regions. LinuxCNC's cutter comp will attempt the geometry but may gouge or leave material in concave areas tighter than the TNR.

6. THE G-code writer SHALL emit cutter compensation commands:
   - G40 (comp cancel) at program start as a safety reset
   - G41 (comp left) or G42 (comp right) activated before first feed move, based on tool direction (R/L)
   - Cutter compensation remains active for ALL passes (face roughing, turning roughing, cleanup, finish)
   - G40 (comp cancel) emitted at program end (before retract to park)
   - The engine programs to the exact boundary/profile coordinates — LinuxCNC offsets the actual tool path by TNR at runtime

6. THE `ToolDef` SHALL be passed through the pipeline as a first-class parameter alongside `RoughingParams`

### Requirement 5: Explicit Transition Management

**User Story:** As a developer, I want transitions between passes to be named, typed objects so that rapid safety verification and G-code optimization are straightforward.

#### Acceptance Criteria

1. THE `Transition` class SHALL represent the movement between two cutting passes with:
   - `type: TransitionType` — one of `RETRACT_TRAVERSE_PLUNGE`, `PERPENDICULAR_LINK`, `STEP_OVER`
   - `start_position: (x_dia, z)` — where the previous pass ended
   - `end_position: (x_dia, z)` — where the next pass begins
   - `safe_x: float` — retract X level (stock OD for OD, pilot hole for ID)
   - `moves: List[ToolMove]` — the actual rapid/feed moves implementing this transition

2. FOR `RETRACT_TRAVERSE_PLUNGE` transitions, THE moves SHALL be:
   a. Retract X to safe level (away from part)
   b. Traverse Z at safe X to next pass start Z
   c. Approach X to previous cleared level at next pass start Z
   d. Feed step-down to next pass X level

3. FOR `PERPENDICULAR_LINK` transitions (offset-contour strategy), THE moves SHALL be:
   a. Feed from current contour endpoint perpendicular to next contour start
   b. No retract (tool stays in material)

4. EACH transition SHALL be verified for safety BEFORE being added to the toolpath:
   - `RETRACT_TRAVERSE_PLUNGE`: verify retract path doesn't cross keep_zone
   - `PERPENDICULAR_LINK`: verify link path stays within material_to_remove
   - `STEP_OVER`: verify step-down doesn't exceed DOC

5. THE transition module SHALL use `ZoneQueryAPI.line_zone_intersection()` for safety verification — never geometric assumptions

### Requirement 6: Runtime Validation Pipeline (Shapely-Accelerated)

**User Story:** As a machinist, I want the engine to catch errors before they become G-code, so that I never run a program that gouges my part.

#### Acceptance Criteria

1. THE validation module SHALL implement three levels of checking:
   - **Pre-planning**: Profile geometry validation (arc validity, closure, segment connectivity)
   - **Post-planning**: Full pass safety validation using Shapely polygons (every endpoint, every rapid, every feed move)
   - **Pre-output**: G-code geometry validation (arc tolerance, zero-length moves, feed consistency)

2. PRE-PLANNING validation SHALL check:
   - Arc radius >= chord_length / 2 for every ARC segment
   - Arc center is computable (discriminant >= 0)
   - Profile closure gap <= TOLERANCE
   - No self-intersecting segments
   - All X values positive (diameter convention)

3. POST-PLANNING validation SHALL use Shapely polygons for comprehensive safety checking of ALL planned moves (not spot-checks — every move is verified):
   - Every pass endpoint (x_level, z_end) is NOT in keep_zone polygon
   - Every pass start (x_level, z_start) is NOT in keep_zone polygon
   - Every rapid move segment does NOT intersect keep_zone polygon boundary
   - Every feed move segment does NOT intersect finished_part polygon
   - At least one point per pass IS in material_to_remove polygon (confirms material exists)

4. THE Shapely validation polygons SHALL be constructed ONCE after Build123d zone construction completes, by converting the exact zone boundary wires into Shapely Polygons with adaptive arc densification (see Requirement 13)

5. PRE-OUTPUT validation SHALL check:
   - No zero-length moves (start == end within TOLERANCE)
   - Arc endpoint distance from center matches radius within `CENTER_ARC_RADIUS_TOLERANCE_INCH` (0.00283")
   - No consecutive identical positions
   - Feed rate is set before first feed move
   - All coordinates are finite (no NaN, no Inf)

6. IF any validation fails, THE pipeline SHALL raise a descriptive error with:
   - Which validation level caught it
   - The specific check that failed
   - The coordinates/values involved
   - The pass number and move index (if applicable)

7. THE pipeline SHALL NEVER silently skip a failed validation — errors propagate to the user

8. THE Shapely validation layer SHALL be a RUNTIME dependency (not test-only) — it runs on every generation, not just in the test suite

### Requirement 13: Shapely Validation Polygon Construction

**User Story:** As a developer, I want the Shapely validation polygons to be accurate enough that they never produce false positives or false negatives at the system's operating tolerance.

#### Acceptance Criteria

1. AFTER `build_zones()` completes, THE pipeline SHALL construct Shapely Polygon objects for:
   - `finished_part_poly` — the Finished Part (no move may ever enter)
   - `finish_allowance_poly` — the Finish Allowance Zone (only finish tool enters)
   - `material_to_rough_poly` — the Material to Rough Out (feed moves should be inside during roughing)

2. THE polygon construction SHALL extract boundary edges from Build123d zone Faces using `boundary_wire_extraction()` (the same edges the kernel computed — not independently constructed)

3. FOR LINE edges, THE polygon construction SHALL use the exact start/end coordinates (no densification needed)

4. FOR ARC edges, THE polygon construction SHALL use adaptive densification with a cosine-limit flatness predicate:
   ```
   flat(start, mid, end) = dot(normalize(mid - start), normalize(end - mid)) > cos_limit
   ```
   WHERE `cos_limit = 0.9999` (guarantees maximum chord error < `R × 0.0001`)

5. THE adaptive densification SHALL recursively bisect arc segments until the flatness predicate is satisfied OR maximum recursion depth (12) is reached

6. FOR the hump test profile (R=0.251" offset arc), THE adaptive densification SHALL produce a polygon boundary with maximum deviation from the true arc of less than 0.000025" (50× tighter than the system TOLERANCE of 0.0005")

7. THE densification error budget SHALL satisfy: `max_chord_error < TOLERANCE / 20` — ensuring that a point 0.0005" outside the true boundary is NEVER misclassified as inside the polygon

8. THE inscribed-chord property SHALL be documented as a safety guarantee: polygon chords are always INSIDE the true arc curve, so the Shapely polygon is a conservative (smaller) approximation of the true zone. This means:
   - If Shapely says a point is INSIDE the polygon → it is DEFINITELY inside the true zone (no false positives for gouge detection)
   - If Shapely says a point is OUTSIDE the polygon → it MIGHT be barely inside the true zone by up to chord_error, but with 0.000025" error this is irrelevant at 0.0005" operating tolerance

9. THE polygon construction SHALL complete in under 10ms for profiles with up to 20 arc segments

10. THE constructed polygons SHALL be cached on the `PlanResult` or a validation context object — never reconstructed per-query

11. THE polygon construction module SHALL live in `validation/polygon_builder.py` and SHALL import from both `geometry/` (for boundary_wire_extraction) and `shapely` (for Polygon construction)

12. IF Shapely is not installed, THE pipeline SHALL raise `ImportError` at startup with a clear message — never silently skip validation

### Requirement 7: Position-Tracking G-Code Writer

**User Story:** As a machinist, I want clean, minimal G-code that only emits what changes, so that programs are readable and zero-motion errors are impossible.

#### Acceptance Criteria

1. THE G-code writer SHALL track current machine position (X, Z) and current feed rate

2. THE G-code writer SHALL suppress axis words that don't change from the current position (modeled after Bapt_CAM's `GcodeWriter`)

3. THE G-code writer SHALL suppress feed words when the feed rate hasn't changed from the previous feed move

4. THE G-code writer SHALL detect and reject zero-motion moves (where no axis word would be emitted) — these indicate a planning bug

5. THE G-code writer SHALL validate arc geometry before emitting:
   - Compute distance from arc start to center
   - Compute distance from arc end to center
   - Verify both match the programmed radius within `CENTER_ARC_RADIUS_TOLERANCE_INCH`
   - If validation fails, raise error (never emit invalid arc)

6. THE G-code writer SHALL support both R-format and IJK-format arc output, selectable by configuration

7. THE G-code writer SHALL emit section comments marking face passes, turning passes, cleanup pass, and finish pass boundaries

### Requirement 8: Adaptive Sampling for Zone Display

**User Story:** As a user, I want zone shading that accurately represents arc regions without excessive point count.

#### Acceptance Criteria

1. THE zone tessellator SHALL use OpenCamLib's cosine-limit flatness predicate:
   ```
   flat(start, mid, stop) = dot(normalize(mid-start), normalize(stop-mid)) > cosLimit
   ```

2. THE tessellator SHALL recursively bisect arc segments until the flatness predicate is satisfied OR max recursion depth (10) is reached

3. THE tessellator SHALL produce fewer points than fixed-step for straight regions and more points for tight-radius regions

4. THE maximum chord deviation SHALL be less than 0.001" (display tolerance)

5. THE `cosLimit` parameter SHALL be configurable (default 0.999, matching OpenCamLib)

6. THE same adaptive sampling logic SHALL be available to the turning planner for determining X-level density in arc regions (denser passes where profile curves sharply)

### Requirement 9: Swept Region Tracking

**User Story:** As a developer, I want each pass to know what material it removes, so that engagement angle computation and material-remaining queries are straightforward.

#### Acceptance Criteria

1. EACH `TurningPass` SHALL have a `swept_region` field describing the material removed by that pass

2. FOR staircase passes, the swept region SHALL be defined by:
   - X bounds: `[prev_x_level, x_level]` (the DOC band)
   - Z bounds: `[z_start, z_end]` (the pass extent)
   - Shape: rectangle (for straight sections) or bounded by the zone boundary (for arc sections)

3. FOR offset-contour passes, the swept region SHALL be defined by:
   - Inner boundary: the current offset contour
   - Outer boundary: the previous offset contour (or stock boundary for first pass)

4. THE swept region SHALL be queryable: `pass.material_at(x_dia, z) -> bool`

5. THE engagement angle at any point along a pass SHALL be computable from the swept region:
   `engagement_angle = arccos(1 - DOC_effective / tool_radius)` where `DOC_effective` comes from the swept region width at that Z position

6. THE sum of all swept regions SHALL equal the material_to_remove zone (verified by the oracle in tests)

### Requirement 10: Preserved Strengths from my-lathe

**User Story:** As a developer, I want to carry forward the proven patterns from my-lathe that provide reliability and user trust.

#### Acceptance Criteria

1. THE property-based test suite (Hypothesis) SHALL be carried forward with the same correctness properties:
   - Hard Rule 1: All material removed (area-based verification)
   - Hard Rule 2: No gouge of finished part (per-move intersection check)

2. THE Shapely oracle SHALL be carried forward for independent verification of kernel results

3. THE NX CAD ground truth comparisons SHALL be carried forward (hump test profile baseline)

4. THE visual confirmation system SHALL be carried forward:
   - Zone shading on the position graph
   - Simulated toolpath playback
   - Interval chart display

5. THE steering rules SHALL be carried forward (zone interval mental model, roughing correctness rules, cleanup pass geometry)

6. THE "no silent fallbacks" principle SHALL be enforced: if any operation fails, it raises — never produces degraded output

7. THE pipeline SHALL produce a `PlanResult` that is immutable after `execute()` returns — output adapters cannot modify planning results

8. THE offline preview mode SHALL be preserved for Windows development without LinuxCNC

### Requirement 11: ID Mode as First-Class Citizen

**User Story:** As a machinist, I want ID mode (boring) to work with the same reliability as OD mode, using the same architecture — not a bolted-on special case.

#### Acceptance Criteria

1. THE architecture SHALL treat OD and ID as a `mode` parameter that affects direction conventions — not as separate code paths with duplicated logic

2. THE following conventions SHALL be parameterized by mode:
   - Safe retract direction: toward stock OD (OD) or toward pilot hole (ID)
   - Offset direction: away from centerline (OD) or toward centerline (ID)
   - Pass stepping direction: decreasing X (OD) or increasing X (ID)
   - Stock boundary: stock OD (OD) or pilot hole (ID)

3. THE Fiber class SHALL work identically for OD and ID — it queries `boundary_at_x` regardless of mode. The mode only affects which X levels are queried and which direction is "safe."

4. THE transition module SHALL use the mode parameter to determine safe retract X — not hardcoded stock_dia

5. ALL validation checks SHALL work for both modes without mode-specific branches

6. THE flat-bottom bore case SHALL be handled by the same pass-planning logic as regular turning — the Fiber at the bore bottom simply returns a horizontal interval

### Requirement 12: No Hand Math

**User Story:** As a developer, I want to never see `z + fin_allowance` or `x - offset` in the codebase, so that sign confusion and manual offset bugs are impossible.

#### Acceptance Criteria

1. ALL coordinate offsets SHALL come from the geometry kernel's offset operation — never from arithmetic on coordinates

2. ALL boundary crossings SHALL come from `ZoneQueryAPI.boundary_at_x()` or `line_zone_intersection()` — never from solving circle equations manually

3. ALL arc geometry (center, radius, endpoints) SHALL come from the kernel's edge extraction — never from midpoint/perpendicular formulas

4. THE ONLY arithmetic allowed on coordinates SHALL be:
   - Diameter ↔ radius conversion (`x_dia / 2.0`)
   - Tolerance comparisons (`abs(a - b) < TOLERANCE`)
   - Pass level computation (`stock_dia - n * doc_dia`)

5. IF a developer needs a geometric answer that requires more than the allowed arithmetic, they SHALL add a new query method to `ZoneQueryAPI` that delegates to the kernel

6. THE codebase SHALL have ZERO instances of:
   - `center_x = (start_x + end_x) / 2 + h * perp_x` (manual arc center)
   - `z_crossing = center_z + sqrt(r^2 - dx^2)` (manual circle intersection)
   - `offset_x = profile_x + fin_allowance` (manual offset)

### Requirement 14: Architecture Integrity Enforcement

**User Story:** As a developer, I want automated checks that detect dead code, fallback paths, dual implementations, and design principle violations, so that the architecture stays clean as the codebase evolves.

#### Acceptance Criteria

1. THE project SHALL include a static analysis pass (`validation/architecture_check.py`) that runs as part of the test suite and CI, verifying structural invariants of the codebase

2. THE architecture check SHALL detect and FAIL on **dead code**:
   - Any function or class with zero callers (excluding public API entry points and test helpers)
   - Any import that is never used
   - Any conditional branch that is unreachable (e.g., `if False:`, legacy feature flags)
   - Any module listed in the project that is never imported by any other module or test

3. THE architecture check SHALL detect and FAIL on **fallback patterns**:
   - Any `try/except` that catches a failure and substitutes a different implementation (e.g., `except: use_legacy_engine()`)
   - Any `if hasattr(...):` pattern that selects between two code paths for the same operation
   - Any function with multiple return paths that produce geometrically different results for the same input
   - Any import guarded by `try/except ImportError` that provides an alternative implementation (optional dependencies that degrade functionality)

4. THE architecture check SHALL detect and FAIL on **dual implementations**:
   - Two or more functions/methods that compute the same geometric quantity (e.g., two ways to get boundary crossings, two ways to compute cleanup contour)
   - Any module pair where both implement the same Protocol interface unless explicitly registered as strategy alternatives (staircase vs offset-contour is allowed; two staircase implementations is not)

5. THE architecture check SHALL detect and FAIL on **dependency violations**:
   - Any import from `geometry/` in a module other than `intervals/`, `validation/`, or `pipeline/`
   - Any import of `build123d` or `OCP` outside of `geometry/`
   - Any import of `shapely` outside of `validation/`
   - Any import from `pipeline/` in any module other than the entry point
   - Any circular import between modules

6. THE architecture check SHALL detect and FAIL on **hand math violations** (Requirement 12 enforcement):
   - Any arithmetic expression involving both a coordinate variable and `fin_allowance`, `offset`, `doc`, or `radius` that is not a simple diameter↔radius conversion or tolerance comparison
   - Any call to `math.sqrt` with arguments derived from coordinate variables (indicates manual circle intersection)
   - Any `atan2` call on coordinate differences (indicates manual arc center computation)

7. THE architecture check SHALL detect and WARN on **potential design drift**:
   - Functions exceeding 100 lines (suggests multiple responsibilities)
   - Modules exceeding 500 lines (suggests need for splitting)
   - More than 3 parameters of the same type in a function signature (suggests missing dataclass)
   - Any `# TODO` or `# HACK` or `# FIXME` comment (tracked as tech debt)

8. THE architecture check SHALL produce a report listing:
   - PASS/FAIL status for each invariant category
   - For each FAIL: the file, line number, and specific violation
   - For each WARN: the file, line number, and suggestion
   - Summary counts: dead code items, fallback patterns, dual implementations, dependency violations, hand math violations

9. THE architecture check SHALL be runnable as:
   - `python -m pytest tests/test_architecture.py` (integrated with test suite)
   - `python -m validation.architecture_check` (standalone CLI for quick checks)

10. THE architecture check SHALL use Python's `ast` module for static analysis — it parses source files without importing them, so it works even when Build123d/OCCT are not installed (Windows development)

11. ON EVERY PR or commit, the architecture check SHALL pass with zero FAILs. WARNs are informational and do not block.

### Requirement 15: Steering File Overhaul for Industry CAM Engine

**User Story:** As a developer, I want Industry CAM Engine to have its own clean steering rules that reflect its architecture, so that legacy my-lathe assumptions, workarounds, and mental models do not contaminate the new build.

#### Acceptance Criteria

1. THE Industry CAM Engine workspace SHALL have its own `.kiro/steering/` directory with steering files written specifically for the new architecture — NOT copied from my-lathe

2. THE following my-lathe steering files SHALL NOT apply to Industry CAM Engine code (they reference patterns, files, and workarounds that no longer exist):
   - `zone-interval-mental-model.md` — references `engines/geometry.py`, `engines/turning_planner.py`, manual offset formulas, and NX ground truth values that may change with the new architecture
   - `roughing-correctness-rules.md` — references `engines/*.py`, `pipeline/pipeline.py`, and the Shapely oracle as test-only (it's now runtime)
   - `cleanup-pass-offset-geometry.md` — references `engines/geometry.py`, `engines/cleanup_planner.py`, `engines/ocp_helpers.py` and CadQuery-era lessons
   - `cleanup-pass-edge-extraction.md` — references `engines/cleanup_planner.py`, `outputs/gcode_formatter.py`
   - `cleanup-pass-arc-radius.md` — references `engines/cleanup_planner.py`, `engines/geometry.py`, `engines/ocp_helpers.py`
   - `conv-tab-mental-model.md` — references `conv_profile.py`, `conv_tab/*.py`, legacy pipeline dual-path
   - `pipeline-architecture.md` — references the old module layout (`engines/`, `pipeline/`, `outputs/`)
   - `geometry-verification-protocol.md` — references `engines/*.py`, `arc_math.py`, SymPy verification scripts
   - `linuxcnc-source-reference.md` — this one is still valid (LinuxCNC tolerances don't change) but should be reviewed for path references

3. THE Industry CAM Engine steering files SHALL be written to reflect:
   - The new module structure (`geometry/`, `intervals/`, `planners/`, `transitions/`, `tools/`, `validation/`, `outputs/`, `pipeline/`)
   - The new design principles (P1-P7 from this spec)
   - Shapely as runtime validation (not test-only oracle)
   - The Fiber/Interval pattern (not raw `intervals_at_x` calls)
   - Offset-contour as a first-class roughing strategy
   - Tool as geometry (not scalar nose radius)
   - Explicit transitions (not implicit move generation)
   - The "no hand math" rule with specific examples of what IS and ISN'T allowed

4. THE Industry CAM Engine steering files SHALL include at minimum:
   - `architecture-rules.md` — module boundaries, dependency order, import rules, the 7 design principles
   - `geometry-kernel-rules.md` — Build123d as sole truth source, what queries exist, how to add new ones, no-fallback policy
   - `validation-rules.md` — Shapely runtime validation, adaptive densification parameters, error budget, polygon construction
   - `coordinate-conventions.md` — diameter vs radius, X/Z sign conventions, tolerance constants, what arithmetic is allowed
   - `reference-codebases.md` — updated version pointing to the same repos but with Industry CAM Engine module mappings

5. THE Industry CAM Engine steering files SHALL use `inclusion: conditional` with globs matching the NEW module paths (e.g., `planners/*.py`, `geometry/*.py`) — not the old my-lathe paths

6. THE `reference-codebases.md` steering file SHALL be updated to use `inclusion: auto` (always loaded) since architecture discussions can happen in any context

7. HISTORICAL LESSONS from my-lathe steering files SHALL be distilled into the new steering files as concise rules — not as narrative history. For example:
   - OLD: "The previous implementation required negating the arc radius when building closed solids..." (narrative about past bugs)
   - NEW: "Arc direction in Build123d RadiusArc: +profile_radius → -RadiusArc_radius (CW in lathe = negative in Build123d)" (concise rule)

8. THE my-lathe steering files SHALL remain in place for my-lathe development — they are NOT deleted. Industry CAM Engine simply has its own workspace-level steering that takes precedence when working in that directory

9. NO steering file for Industry CAM Engine SHALL reference:
   - `CadQuery` or `cadquery_engine` (deleted, never existed in Industry CAM Engine)
   - `roughing_engine.py` or `roughing_engine_v2.py` (legacy, not carried forward)
   - `zone_definitions.py` (legacy analytical code)
   - `edge_case_rules.py` (eliminated by top-down rule propagation)
   - `_legacy.py` (self-explanatory)
   - Any "evaluate early" warnings about Build123d behavior (those were discovery-phase notes, not permanent rules)

10. THE steering overhaul SHALL be completed BEFORE any implementation code is written for Industry CAM Engine — the rules must exist before the code they govern

### Requirement 16: Validation Severity Classification and G-Code Generation Policy

**User Story:** As a machinist, I want the engine to distinguish between hard errors (which must block G-code generation) and warnings (which inform my decision but let me proceed), so that I'm not blocked from generating code when the issue is advisory rather than catastrophic.

#### Acceptance Criteria

1. THE validation system SHALL classify all results using a `Severity` enum:
   - `ERROR` — pipeline halts, no G-code generated, no graph output
   - `WARNING` — user is prompted with a specific, actionable message and may choose to continue or abort

2. THE following conditions SHALL be classified as `ERROR` (always blocks G-code):
   - **Geometry Invalid**: Self-intersecting profile, arc radius < chord_length/2, unclosed profile, non-computable arc center
   - **Safety Violation**: Any move enters `finished_part_poly` (Shapely gouge detection), any rapid crosses keep_zone boundary, any feed move intersects finished_part polygon
   - **System Integrity**: NaN/Inf coordinates, missing feed rate before first feed move, Shapely not installed

3. THE following conditions SHALL be classified as `WARNING` (user decides):
   - **Tool Reach Advisory**: Tool nose radius exceeds minimum concave radius in profile — finish pass may leave material in tight concave regions
   - **Tool Edge Length Advisory**: Cutting edge length is shorter than maximum pass depth — tool may not physically reach full depth
   - **Engagement Advisory**: Engagement angle exceeds 1.2× nominal on one or more passes — tool life may be reduced
   - **Thin Wall Advisory**: Remaining wall thickness between passes is below recommended minimum
   - **Quality Advisory**: Offset-contour pass spacing produces scallop height exceeding surface finish target

4. EACH `WARNING` SHALL include:
   - A specific, machinist-readable message describing what may go wrong (not developer jargon)
   - The location in the profile where the issue occurs (X diameter, Z position)
   - A recommendation (e.g., "Consider a tool with TNR ≤ 0.025" or "Reduce DOC to 0.030"")
   - The consequence of proceeding (e.g., "Material may remain in the R0.025 concave at Z=-0.750")

5. THE pipeline SHALL collect ALL validation results (errors and warnings) before halting or prompting — not stop at the first issue

6. IF the result set contains any `ERROR`, THE pipeline SHALL halt immediately after collection — no G-code, no graph, full error report displayed

7. IF the result set contains only `WARNING`s (zero errors), THE pipeline SHALL:
   a. Display all warnings to the user in the GUI with clear descriptions
   b. Offer "Continue with G-code Generation" and "Cancel" options
   c. If user continues: proceed through remaining pipeline stages (G-code writer, graph adapter) with warnings logged in the output
   d. If user cancels: halt cleanly, no output produced

8. THE Shapely safety net (post-planning gouge detection) SHALL ALWAYS run regardless of user warning overrides — it is the final hard gate. If a user overrides a tool reach warning and the resulting toolpath actually gouges the part, Shapely catches it as an ERROR.

9. THE `ValidationResult` dataclass SHALL contain:
   ```python
   class Severity(Enum):
       ERROR = "error"
       WARNING = "warning"

   @dataclass
   class ValidationResult:
       severity: Severity
       category: str        # "geometry", "safety", "tool_reach", "tool_edge",
                            # "engagement", "thin_wall", "quality", "system"
       message: str         # Machinist-readable description
       recommendation: Optional[str]  # Suggested fix
       consequence: Optional[str]     # What happens if user proceeds
       location: Optional[Tuple[float, float]]  # (x_dia, z) where issue occurs
       pass_index: Optional[int]      # Which pass (if applicable)
       move_index: Optional[int]      # Which move within pass (if applicable)
   ```

10. THE pipeline's `execute()` method SHALL return a `PipelineResult` that includes:
    - `plan_result: Optional[PlanResult]` — None if errors blocked generation
    - `validations: List[ValidationResult]` — all errors and warnings
    - `warnings_overridden: bool` — whether user chose to proceed past warnings
    - `status: PipelineStatus` — one of `SUCCESS`, `SUCCESS_WITH_WARNINGS`, `BLOCKED_BY_ERROR`, `CANCELLED_BY_USER`

11. THE G-code output SHALL include a header comment listing any overridden warnings:
    ```gcode
    ( WARNING: Tool TNR 0.032 exceeds min concave R0.025 at Z=-0.750 )
    ( WARNING: User accepted - material may remain in concave region )
    ```

12. THE graph visualization SHALL indicate warning regions visually (e.g., highlighted zone where tool reach is questionable) so the user can see the advisory in spatial context before deciding

### Requirement 17: G-Code Round-Trip Verification

**User Story:** As a developer, I want to verify that the G-code writer's output, when parsed back, produces the same toolpath that the graph displays — so that I can guarantee "what you see is what will cut" with mathematical certainty.

#### Acceptance Criteria

1. THE `outputs/` module SHALL include a `gcode_parser.py` that can parse the engine's own G-code output back into a `List[ToolMove]`

2. THE parser SHALL handle the full G-code subset the writer emits:
   - G00 (rapid), G01 (linear feed), G02 (CW arc), G03 (CCW arc)
   - X, Z axis words (diameter mode)
   - I, K (incremental arc center) and R (radius) arc formats
   - F (feed rate), modal G-code state tracking
   - Comments (ignored during parse, preserved for display)

3. THE pipeline SHALL support a **round-trip verification mode** that:
   a. Takes the `PlanResult.tool_moves[]` (the primary graph source)
   b. Writes G-code via `gcode_writer.write()`
   c. Parses the G-code back via `gcode_parser.parse()`
   d. Compares the parsed moves against the original `tool_moves[]`
   e. Reports any divergence as a `WriterFidelityError`

4. THE round-trip comparison SHALL check for each move pair (original vs parsed):
   - Move type matches (rapid/feed/cw_arc/ccw_arc)
   - End position matches within `TOLERANCE` (0.0005")
   - Arc center matches within `CENTER_ARC_RADIUS_TOLERANCE` (0.00283") for arc moves
   - Feed rate matches for feed moves

5. THE graph widget SHALL support an optional **verification overlay** mode:
   - Primary trace: drawn from `PlanResult.tool_moves[]` (blue/normal color)
   - Verification trace: drawn from parsed G-code (semi-transparent green overlay)
   - Divergence highlighting: any segment where traces differ by more than `TOLERANCE` is highlighted in red
   - Toggle: user can enable/disable the overlay (off by default for performance)

6. IF round-trip verification detects divergence, THE system SHALL:
   - Log the specific move index, expected vs actual coordinates, and the G-code line number
   - Display a developer-facing diagnostic (not shown to end users in normal mode)
   - NOT block G-code generation (this is a writer bug detector, not a safety gate — Shapely is the safety gate)

7. THE round-trip verification SHALL run automatically in the test suite (every test that generates G-code also verifies round-trip fidelity)

8. THE round-trip verification SHALL be available as an optional flag in production: `pipeline.execute(..., verify_roundtrip=True)` — disabled by default for performance, enabled during development and debugging

9. THE G-code parser SHALL be intentionally minimal — it only needs to parse the engine's own output format, not arbitrary G-code from external sources. This keeps it simple and correct.

10. THE parser SHALL use LinuxCNC's interpretation rules for modal state:
    - G00/G01/G02/G03 are modal (persist until changed)
    - X/Z are absolute (G90 mode assumed — the engine never emits G91)
    - I/K are incremental from start point (LinuxCNC convention)
    - Feed rate is modal (persists until changed)

11. IF the engine's G-code output format changes (new G-codes, new axis words), THE parser SHALL be updated in the same commit — they are a matched pair

### Requirement 33: Round-Trip Validation Chain

**User Story:** As a developer, I want a formal three-checkpoint validation chain that proves the G-code is safe by validating at every stage — from zone construction through G-code output — with no fallback paths or hand-math workarounds.

#### Acceptance Criteria

1. THE validation chain SHALL have three checkpoints, all using the SAME Shapely polygons built from Build123d wire extraction:
   - **Checkpoint 1 (Zone Validity)**: Shapely polygons constructed from wire extraction are geometrically valid (`is_valid == True`, `area > 0`)
   - **Checkpoint 2 (Engine Moves)**: Every move in `PlanResult.tool_moves[]` is validated against zone polygons (no gouge)
   - **Checkpoint 3 (G-code Round-Trip)**: G-code is written, parsed back, and every parsed move is validated against the SAME zone polygons (no gouge)

2. ALL three checkpoints SHALL use polygons derived from `boundary_wire_extraction()` — the Build123d geometry kernel's output. There SHALL be NO alternative polygon source (no hand math, no manual coordinate computation, no "display-only" approximation).

3. IF `boundary_wire_extraction()` fails or produces invalid polygons, THE pipeline SHALL RAISE an error. It SHALL NOT fall back to manual coordinate computation. The failure must be fixed at the source.

4. THE pipeline SHALL produce TWO DXF outputs for visual verification:
   - **Engine DXF**: Zone polygons (from wire extraction) + toolpath (from PlanResult.tool_moves[])
   - **G-code DXF**: Toolpath derived from parsing the generated G-code text back into moves
   - Both DXFs use the same coordinate convention (radius for X, inches for Z, millimeters in DXF)

5. IF the G-code DXF shows a gouge that the Engine DXF does not, THE G-code writer has a bug (it introduced an unsafe move during retract/approach generation). This is a hard error.

6. THE round-trip validation chain is defined in #[[file:.kiro/steering/round-trip-testing.md]] and applies to every pipeline execution.

7. THERE SHALL BE NO FUNCTION in the codebase that computes zone polygon coordinates using arithmetic on profile coordinates (e.g., `x + fin_r`, `z + offset`). All zone coordinates come from Build123d's offset and boolean operations, extracted via `boundary_wire_extraction()`.

8. IF a developer cannot get correct coordinates from wire extraction, THE CORRECT ACTION is to fix the extraction — NOT to create a parallel computation path. The steering file documents this explicitly as a mandatory workflow.

9. THE validation chain SHALL include a **Checkpoint 0 (Ground Truth Comparison)** that runs BEFORE the pipeline proceeds past zone construction:
   - IF a ground truth DXF exists for the current profile (in `reference/CAD Reference/`) → comparison is MANDATORY
   - Engine zone vertices are compared against ground truth DXF vertices (within TOLERANCE)
   - IF vertices don't match (extra vertices, missing vertices, wrong coordinates) → pipeline STOPS with descriptive error
   - The developer MUST fix zone_builder until the output matches ground truth
   - The pipeline MUST NOT proceed to planning if zone construction doesn't match ground truth

10. GROUND TRUTH comparison catches Build123d-specific issues that Shapely cannot:
    - Fillet/chamfer corners from offset operations (extra diagonal vertices)
    - Face zone material incorrectly included in Material to Rough
    - Zone boundaries extending beyond stock limits (Z < Z_end, X < 0)
    - These are zone_builder bugs, not wire extraction bugs — the extraction is correct but the underlying geometry is wrong

### Requirement 18: Program Tab Visualization

**User Story:** As a machinist, I want the Program Tab graph to give me immediate visual confidence that my profile is correct and the generated toolpath is safe, without overwhelming me with developer-level detail.

#### Acceptance Criteria

1. THE Program Tab graph SHALL display the following layers during toolpath display (post-generation):
   - **Zone shading** (filled polygons): Finished Part = red/dark, Material to Rough = light blue, Finish Allowance = amber/gold
   - **Toolpath trace**: feed moves = green, rapid moves = red dashed, arc moves = blue
   - **Profile boundary**: white, bold line weight — the target finish surface
   - **Stock boundary**: rectangle outline always visible (gray or dim white)

2. THE Program Tab graph SHALL support pass-by-pass playback with touch-friendly controls:
   - Play / Pause / Step Forward / Step Back buttons
   - Animated tool dot showing current position during playback
   - Pass display SHALL show the G-code N-number and operation type: e.g., "N0040 — Roughing", "N0120 — Finish"
   - Playback speed control (0.5×, 1×, 2×, 5×)

3. THE Program Tab graph SHALL support overlay toggles accessible from the top status bar area (inside the existing bar, minimal footprint):
   - **Round-Trip overlay**: semi-transparent green trace from parsed G-code (toggle on/off)
   - **Warning regions**: amber highlight on profile sections where tool reach or quality advisories exist (toggle on/off)
   - **Clearance heatmap**: color gradient showing distance to keep zone (toggle on/off, replaces normal toolpath coloring when active)
   - Default state: all overlays OFF (clean view)

4. THE Program Tab graph SHALL support a **real-time profile preview** mode during input (before "Generate" is pressed):
   - Profile segments drawn as simple Qt geometry (QPainterPath lines and arcs) — NO kernel involvement
   - Arcs drawn using Qt's arc parameterization (start point, end point, radius)
   - Stock boundary rectangle drawn from user input fields (stock_dia, z_start, z_end)
   - Current segment highlighted as user edits it
   - Partial/unclosed profiles display without error (just draw what's defined so far)
   - No zone shading during preview mode (zones require closed profile + kernel)

5. WHEN the user presses "Generate", THE graph SHALL transition from preview mode to full display:
   - Simple Qt preview geometry replaced by kernel-accurate zone shading and toolpath
   - Profile boundary line updates to kernel-computed position (white, bold)
   - If the kernel-accurate profile visibly differs from the Qt preview, briefly flash the old preview in gray (0.5s fade) so the user can see what shifted
   - Playback controls appear after generation completes

6. THE Program Tab layout SHALL use a `QSplitter` between the input fields panel and the graph panel:
   - Default split position optimized for 1920×1080 (15.6" FHD touch panel)
   - User may drag the splitter to give more room to graph or input fields
   - Splitter position persists across sessions (saved in settings)

7. THE graph SHALL support pinch-to-zoom and drag-to-pan on the touch panel, with a "Fit All" button to reset the view to show the entire stock + toolpath

8. DURING playback, THE graph SHALL highlight the active pass's swept region (light fill showing material being removed by the current pass) — this is the ONE debug-tier feature promoted to the Program Tab because it directly answers "what is this pass doing?"

9. THE Program Tab graph SHALL work in Windows offline mode with demo/simulated data (no LinuxCNC required for development and preview)

### Requirement 19: Debug/Diagnostics Tab

**User Story:** As a developer or advanced operator, I want a dedicated diagnostics tab with full pipeline visibility, so that I can investigate why the engine made specific decisions and verify correctness at every stage.

#### Acceptance Criteria

1. THE Debug/Diagnostics tab SHALL be a tab in the main GUI (same tab bar as Program, Edit, etc.) — NOT a separate window

2. THE Debug tab SHALL contain sub-panels selectable via a horizontal tab bar or button row at the top of the tab:
   - **Fibers** — Interval chart
   - **Swept** — Cumulative swept region visualization
   - **Heatmap** — Clearance/distance visualization
   - **Diagnostic** — Structured text dump
   - **Round-Trip** — G-code fidelity comparison detail
   - **Export** — File output (DXF, SVG, PNG)

3. THE **Fibers** panel SHALL display:
   - Horizontal bars at each queried X level (diameter) showing material intervals
   - Gaps between intervals clearly visible (empty space)
   - Color coding: material = solid fill, merged regions = highlighted border
   - X level labels on the left axis, Z positions on the horizontal axis
   - Clickable: selecting a fiber highlights the corresponding X level on the Program Tab graph

4. THE **Swept** panel SHALL display:
   - Each pass's swept region as a filled polygon, stacked cumulatively
   - Color gradient by pass number (first pass = lightest, last = darkest)
   - Toggle: show individual pass vs cumulative union
   - Gap detection: any area within Material to Rough zone NOT covered by swept regions highlighted in red (indicates missed material — Hard Rule 1 violation)
   - Pass selection: click a swept region to see its pass parameters (x_level, z_start, z_end, DOC)

5. THE **Heatmap** panel SHALL display:
   - The toolpath colored by minimum distance to `finished_part_poly` at each point
   - Color scale: red (< 2× TOLERANCE) → yellow (< fin_allowance) → green (comfortable clearance)
   - Numeric readout on hover/touch showing exact clearance value
   - Profile boundary and finished part polygon shown as reference

6. THE **Diagnostic** panel SHALL display a structured text dump including:
   - Profile summary: segment count, closed status, min radius, total Z travel
   - Stock parameters: OD, Z start, Z end, mode (OD/ID), pilot hole (if ID)
   - Tool parameters: TNR, tip angle, edge length, orientation, direction
   - Zone construction: face count, edge count, offset distance used
   - Fiber summary: levels queried, intervals per level, total material length
   - Pass planning: pass count by type (face/rough/cleanup/finish), total moves
   - Transition summary: count by type (retract-traverse-plunge, link, step-over)
   - Validation results: moves checked, errors, warnings (with details)
   - G-code stats: line count, arc count, total travel distance
   - Round-trip result: max deviation, pass/fail
   - Timing: milliseconds per pipeline stage

7. THE **Round-Trip** panel SHALL display:
   - Side-by-side or overlaid comparison: PlanResult trace vs parsed G-code trace
   - Divergence list: table of move index, expected position, actual position, delta, G-code line number
   - Per-move type breakdown: rapids matched, feeds matched, arcs matched
   - Overall verdict: PASS (max deviation < TOLERANCE) or FAIL with details

8. THE **Export** panel SHALL provide file output in the following formats:
   - **DXF** (primary CAD exchange format — most reliable cross-platform compatibility):
     - Layers: Profile Boundary, Stock Boundary, Zone Boundaries, Toolpath (by type), Swept Regions
     - Arcs exported as true DXF ARC entities (not polyline approximations)
     - Compatible with AutoCAD, LibreCAD, FreeCAD, NX, SolidWorks
   - **SVG** (web/documentation):
     - Same layer structure as DXF
     - Styled with colors matching the GUI display
     - Suitable for embedding in reports, bug tickets, steering file illustrations
   - **PNG** (Shapely polygon visualization):
     - Matplotlib-rendered plot of all Shapely validation polygons
     - Shows: finished_part_poly, finish_allowance_poly, material_to_rough_poly boundaries
     - Toolpath overlaid on polygon plot
     - Includes coordinate grid, axis labels, title with parameters
     - Resolution: 300 DPI minimum for print-quality debugging
     - Useful for: sharing in bug reports, comparing against expected geometry, archiving test results

9. THE Export panel SHALL support batch export (all formats at once) with a single button, saving to a user-configured output directory

10. THE Debug tab SHALL read the sealed `PlanResult` — it performs NO separate computation or pipeline execution. All panels visualize the same data the Program Tab uses.

11. THE Debug tab panels SHALL be lazy-rendered: visualization is computed only when the panel is selected (not all panels on every generation)

12. THE Debug tab SHALL update automatically when a new `PlanResult` is generated (user regenerates from Program Tab)

13. THE Debug tab SHALL work in Windows offline mode (no LinuxCNC required) — all visualizations are computed from the PlanResult data structure

14. THE Debug tab SHALL be touch-accessible (panels selectable by touch, scrollable) but optimized for mouse interaction (hover tooltips, precise selection)

15. DXF export SHALL use the `ezdxf` library (mature, well-maintained, pure Python, handles R2010+ format reliably). SVG export SHALL use Python's built-in `xml.etree` or `svgwrite`. PNG export SHALL use `matplotlib`.

### Requirement 20: Visualization as Core Architecture (PyQtGraph Hybrid)

**User Story:** As a machinist and developer, I want the visualization system to be a first-class architectural component — not a bolt-on afterthought — so that the graph is always reliable, always precise, and never fights the engine for data access.

#### Design Intent

The legacy my-lathe build treated the graph as a "bonus" feature layered on top of the engine. This caused repeated friction: the graph couldn't access the data it needed, coordinate transforms were duplicated between engine and display, and visualization bugs were deprioritized because the graph wasn't considered load-bearing.

In Industry CAM Engine, the visualization IS the primary user interface. The machinist's confidence in the program comes from seeing it on screen. The graph is not optional, not a debugging aid, not a nice-to-have. It is the operator's window into the engine's decisions. The architecture must be designed FROM THE START to feed the graph cleanly.

#### Acceptance Criteria

##### Technology Selection

1. THE primary interactive visualization library SHALL be **PyQtGraph** (version 0.13+):
   - Built on Qt's QGraphicsView — vector-based, infinite zoom, zero pixelation at any scale
   - Native PyQt5 widget — integrates directly into the tab layout via QSplitter
   - Built-in ViewBox with mouse/touch pan and zoom
   - Built-in axis system with adaptive tick formatting (auto-adjusts decimal places to zoom level)
   - Built-in crosshair (InfiniteLine pair) with coordinate readout
   - PlotCurveItem for toolpath traces, FillBetweenItem for zone shading, ScatterPlotItem for endpoints
   - Real-time update performance suitable for animated playback

2. THE static export visualization library SHALL be **Matplotlib** (used ONLY in the Debug tab's Export panel for PNG generation of Shapely polygon plots). Matplotlib SHALL NOT be used for any interactive or real-time display.

3. THE CAD file export library SHALL be **ezdxf** (for DXF output with true arc entities and layered structure).

4. PyQtGraph SHALL be listed as a RUNTIME dependency in `requirements.txt` alongside Build123d, Shapely, and ezdxf. It is not optional.

##### Architecture Integration

5. THE `outputs/` module SHALL include a `graph_adapter.py` that converts `PlanResult` into PyQtGraph-ready data structures:
   - `ZoneShading` — list of polygon coordinate arrays (one per zone) ready for FillBetweenItem
   - `ToolpathTrace` — list of segment arrays with move type annotation (rapid/feed/arc) ready for PlotCurveItem
   - `ProfileLine` — coordinate array of the profile boundary ready for PlotCurveItem
   - `StockRect` — bounding coordinates for stock boundary rectangle
   - `PlaybackFrames` — ordered list of (move_index, position) tuples for animated playback
   - `WarningRegions` — coordinate arrays of profile sections with active warnings

6. THE `graph_adapter.py` SHALL depend ONLY on `models/` — it reads the sealed PlanResult dataclasses and produces plain coordinate arrays. It SHALL NOT import PyQtGraph, Qt, or any GUI library. This keeps the adapter testable without a display.

7. THE GUI layer (`gui/`) SHALL import from `graph_adapter.py` and PyQtGraph. The GUI layer is the ONLY place where PyQtGraph is imported. This maintains the separation: engine produces data → adapter formats it → GUI displays it.

8. THE data flow for visualization SHALL be:
   ```
   pipeline.execute() → PlanResult (sealed)
       → graph_adapter.convert(plan_result) → GraphData (plain arrays + metadata)
           → GUI reads GraphData → PyQtGraph renders
   ```
   No step in this chain requires the previous step's library. PlanResult doesn't know about PyQtGraph. GraphData doesn't know about Build123d. The GUI doesn't know about the pipeline internals.

9. ARC segments in the toolpath SHALL be pre-densified by `graph_adapter.py` using the same adaptive cosine-limit algorithm as the Shapely polygon builder (cos_limit=0.9999, max error < 0.000025"). This means:
   - At maximum useful zoom (0.001" per screen), arcs appear perfectly smooth
   - The densification is computed ONCE during adapter conversion, not on every frame
   - The same densified points serve both the Program Tab graph and the Debug tab overlays

10. THE coordinate system displayed on the graph SHALL match the machinist's mental model:
    - X axis: DIAMETER (matching G-code X words and UI input fields)
    - Z axis: INCHES (negative = into workpiece)
    - Crosshair readout format: `X: 0.8742" (Ø1.7484)  Z: -1.2305"` — showing radius AND diameter for X
    - Axis tick labels: adaptive precision (whole numbers at wide zoom, 4-5 decimal places at tight zoom)

11. THE graph SHALL support zoom to at least 0.0005" per pixel resolution (matching system TOLERANCE) without visual degradation, coordinate readout loss, or performance issues

12. THE graph widget SHALL be designed as a reusable component (`gui/graph_widget.py`) that both the Program Tab and Debug Tab instantiate. Shared behavior (zoom, pan, crosshair, coordinate readout, zone shading) is implemented ONCE. Tab-specific behavior (playback controls, overlay toggles, fiber chart) is added by composition.

##### Preventing Legacy Mistakes

13. THE PlanResult dataclass SHALL include ALL data the graph needs — no secondary queries required:
    - Zone boundary coordinates (for shading)
    - Tool moves with full metadata (for toolpath trace)
    - Profile boundary coordinates (for white profile line)
    - Stock boundary coordinates (for rectangle)
    - Pass boundaries with N-numbers (for playback)
    - Warning locations (for overlay)
    - Swept regions per pass (for active pass highlight)

14. IF a new engine feature produces data that should be visible on the graph, THE PlanResult SHALL be extended to carry that data. The graph SHALL NEVER need to call back into the engine or re-run queries to display something.

15. THE graph_adapter conversion SHALL complete in under 50ms for a typical program (20 passes, 200 moves, 5 arc segments). The graph SHALL NEVER be the bottleneck in the generate → display cycle.

16. THE graph SHALL be tested independently of the engine:
    - Unit tests for graph_adapter (given a known PlanResult, verify correct coordinate arrays)
    - Visual regression tests (render to PNG via PyQtGraph's export, compare against baseline)
    - Performance tests (verify 50ms adapter budget, verify 60fps playback)

17. THE graph widget SHALL handle the case where no PlanResult exists yet (pre-generation state) gracefully:
    - Display stock boundary rectangle and real-time profile preview (from Qt geometry, not engine)
    - All interactive features (zoom, pan, crosshair) work in this state
    - "Generate" button triggers pipeline → PlanResult → graph_adapter → full display

18. TOUCH interaction SHALL be first-class:
    - Pinch-to-zoom (maps to ViewBox zoom)
    - Two-finger drag to pan
    - Single tap on toolpath segment shows move details (type, coordinates, N-number)
    - Long-press shows coordinate readout at touch point (equivalent to crosshair hover)
    - All scrollable lists (segment list, tool table, fiber chart) support drag-to-scroll with momentum
    - Physical keyboard always available — no virtual keyboard required
    - Minimum touch target: 44×44px for all interactive elements

19. THE visualization system SHALL be documented in a steering file (`visualization-architecture.md`) that explains:
    - Why PyQtGraph was chosen (precision zoom, vector rendering, Qt native, coordinate readout)
    - The data flow from PlanResult → GraphData → PyQtGraph
    - How to add new visual layers (the pattern for extending GraphData and the graph widget)
    - Common pitfalls (don't import PyQtGraph in engine code, don't query engine from GUI, don't skip the adapter)

### Requirement 22: Actionable Validation Error Messages

**User Story:** As a machinist, I want validation errors to tell me exactly which input is wrong and how to fix it, so that I can correct my profile without guessing.

#### Acceptance Criteria

1. WHEN pre-planning validation fails, THE error message SHALL include:
   - **Which segment** failed (segment index and type, e.g., "Segment 3 (Arc)")
   - **What's wrong** in plain language (e.g., "Arc radius is smaller than the chord length")
   - **The values involved** (e.g., "Radius: 0.020\", Chord: 0.045\"")
   - **A fix suggestion** (e.g., "Increase radius to at least 0.023\" or adjust endpoint positions")

2. THE Program Tab input fields SHALL visually indicate which row contains the error:
   - Red border or highlight on the segment row that failed validation
   - Error icon with tooltip showing the full message
   - Clears automatically when the user corrects the value

3. THE fix suggestions SHALL be specific and computable, not generic:
   - Arc radius too small → suggest minimum valid radius (chord_length / 2 + TOLERANCE)
   - Profile not closed → show the gap distance and which endpoint to move
   - Self-intersection → identify the two segments that cross and their intersection point
   - X value negative → "X must be positive (diameter convention) — did you mean {abs(x)}?"

4. WHEN multiple validation errors exist, ALL errors SHALL be reported simultaneously (not just the first one). The user sees the full list and can fix them in any order.

5. THE real-time profile preview (basic Qt geometry) SHALL show valid segments normally and invalid segments in a distinct error style (e.g., red dashed line) so the user can see spatially where the problem is before reading the error text.

6. THE validation error system SHALL use the same `ValidationResult` dataclass from Requirement 16, with `category="geometry"` and `severity=ERROR` for profile issues that prevent generation.

### Requirement 23: Pipeline Performance and Generation Lifecycle

**User Story:** As a machinist, I want the profile preview to be instant and the full toolpath generation to prioritize accuracy over speed, with a clear separation between the two modes.

#### Acceptance Criteria

1. THE Program Tab SHALL operate in two distinct modes with a clear boundary between them:
   - **Profile Building Mode** — real-time, basic Qt geometry, no pipeline involvement
   - **Toolpath Display Mode** — entered by clicking "Generate", shows full pipeline output

2. IN Profile Building Mode:
   - Segment preview updates instantly on every input change (< 16ms, pure QPainterPath drawing)
   - No kernel calls, no Shapely, no pipeline execution
   - Stock boundary rectangle drawn from input fields
   - Validation errors shown inline (Requirement 22)
   - "Generate" button is enabled when profile has zero validation errors

3. WHEN the user clicks "Generate":
   - The full pipeline executes synchronously (accuracy-first, no shortcuts)
   - A subtle progress indicator is shown (thin animated bar, not a modal blocker)
   - On completion: graph transitions from Profile Building Mode to Toolpath Display Mode
   - On error: graph stays in Profile Building Mode, error displayed with fix suggestions

4. IN Toolpath Display Mode:
   - Full zone shading, toolpath trace, playback controls visible
   - Profile preview geometry is replaced by kernel-accurate geometry
   - User may zoom, pan, step through playback
   - Editing input fields does NOT auto-regenerate — it returns the graph to Profile Building Mode with a visual indicator that the toolpath is stale

5. THE pipeline SHALL target the following performance budgets (accuracy is NEVER sacrificed for speed):
   - **Typical profile** (5 segments, ≤20 roughing passes): under 2 seconds
   - **Complex profile** (15+ segments, 40+ passes, offset-contour): under 5 seconds
   - **Hard ceiling**: if any generation exceeds 10 seconds, investigate architectural issues (excessive kernel calls, redundant validation)

6. IF the user edits any input field while in Toolpath Display Mode:
   - The graph immediately returns to Profile Building Mode
   - The previous toolpath is cleared (not shown dimmed — clean slate)
   - The profile preview updates to reflect the new input
   - The user must click "Generate" again to see the new toolpath

7. DURING playback (step-through or animated), input fields SHALL be read-only. The user must stop playback before editing. This prevents the ambiguous state of editing mid-animation.

8. THE "Generate" button SHALL be clearly labeled and visually prominent — it is the single action that bridges the two modes. No hidden auto-generation, no implicit triggers.

### Requirement 24: Automatic Profile Closure

**User Story:** As a machinist, I want to define only the finish profile shape (the part I'm cutting) and have the engine automatically close the contour using stock parameters, so that I never think about closure segments or Build123d's internal requirements.

#### Design Intent

The geometry kernel (Build123d) requires a closed 2D Face for boolean zone construction. The user defines an open profile (the finish shape). The engine closes it automatically using stock parameters the user already provided. No "Verify Closed" button, no user-visible closure segments, no state persistence issues. The closure is computed fresh at generation time from the explicit rules below.

#### Acceptance Criteria

##### Closure Rules

1. THE user's profile SHALL be an open contour defined by their input segments:
   - Profile ALWAYS starts at Z=0 (enforced by validation — Requirement 22)
   - Profile ALWAYS ends at Z_end (enforced by validation — Requirement 22)
   - The profile defines the finish shape only — not the closure path

2. AT generation time, `geometry/zone_builder.py` SHALL automatically append closure segments to create a closed contour. The closure is exactly 3 line segments with NO user interaction:

   **OD Mode** (closure follows centerline — produces Finished Part between profile and centerline):
   ```
   Closure segment 1: profile_end(x_end, Z_end) → (centerline, Z_end)
                       Line from profile endpoint to centerline at Z_end
   
   Closure segment 2: (centerline, Z_end) → (centerline, Z=0)
                       Line up the centerline from Z_end to Z=0
   
   Closure segment 3: (centerline, Z=0) → profile_start(x_start, Z=0)
                       Line from centerline to profile start at Z=0
   ```

   **ID Mode** (closure follows stock OD — produces Finished Part between profile and stock OD, away from centerline):
   ```
   Closure segment 1: profile_end(x_end, Z_end) → (stock_OD_radius, Z_end)
                       Line from profile endpoint to stock OD at Z_end
   
   Closure segment 2: (stock_OD_radius, Z_end) → (stock_OD_radius, Z=0)
                       Line up the stock OD boundary from Z_end to Z=0
   
   Closure segment 3: (stock_OD_radius, Z=0) → profile_start(x_start, Z=0)
                       Line from stock OD to profile start at Z=0
   ```

3. THE closure rules SHALL produce zones that exactly match the Zone Mental Model definitions:
   - **OD Finished Part** = area enclosed by (profile + closure to centerline), bounded by Z=0 and Z(most negative) — matches: "Profile Boundary closed to centerline"
   - **ID Finished Part** = area enclosed by (profile + closure to stock OD), bounded by Z=0 and Z(most negative) — matches: "Profile Boundary closed to Stock Boundary on the X+ side"
   - **Stock Boundary (OD)** = rectangle from stock_dia to centerline, Z=0 to Z_end — the closure path traces the inner boundary of the Finished Part, stock boundary is the outer limit of material
   - **Stock Boundary (ID)** = area from pilot hole to profile — the closure path traces the outer boundary of the Finished Part

4. THE closure segments SHALL be computed in RADIUS coordinates (matching Build123d's sketch plane convention):
   - `centerline` = X radius = 0.0
   - `stock_OD_radius` = stock_dia / 2.0
   - `x_start` = profile_start_x_dia / 2.0
   - `x_end` = profile_end_x_dia / 2.0

5. THE closure segments SHALL NEVER be shown in the Program Tab segment list. They are internal to the engine. The user's segment list contains ONLY their profile segments.

6. THE closure segments SHALL NOT be saved in the project file. They are recomputed from stock parameters at every generation. If stock parameters change, closure adapts automatically.

##### Preview and Validation

7. IN Profile Building Mode, THE graph SHALL show a subtle dashed line (light gray, thin) indicating where closure WILL occur:
   - From profile end toward the closure boundary (centerline or stock OD)
   - Along the closure boundary
   - From closure boundary to profile start
   - This gives spatial context without making closure editable

8. THE following validation errors SHALL prevent generation (Requirement 22 integration):
   - Profile first segment Z_start ≠ 0.000 (within TOLERANCE): ERROR — "Profile must start at Z=0.000. Current: Z={value}. Adjust first segment."
   - Profile last segment Z_end ≠ Z_end parameter (within TOLERANCE): ERROR — "Profile must end at Z={z_end}. Current: Z={value}. Adjust last segment."
   - OD mode: profile start X > stock_dia: ERROR — "Profile start (Ø{x}) exceeds stock diameter (Ø{stock_dia}). No material at this position."
   - OD mode: profile contains X=0 (on centerline): WARNING — "Profile touches centerline. Closure may produce zero-area region."
   - ID mode: profile start X < pilot_hole_dia: ERROR — "Profile start (Ø{x}) is inside pilot hole (Ø{pilot}). No material at this position."
   - ID mode: profile X > stock_dia: ERROR — "Profile (Ø{x}) exceeds stock diameter (Ø{stock_dia}). Cannot bore beyond stock OD."

9. THE closed contour produced by (profile + closure) SHALL be validated by the geometry kernel:
   - Closure gap ≤ TOLERANCE (guaranteed by construction since both ends are at Z=0)
   - No self-intersection between profile segments and closure segments
   - Enclosed area > 0 (the closed contour actually encloses material)
   - If kernel validation fails, raise ERROR with the specific geometric issue

10. THE "Verify Closed" button from the legacy system SHALL NOT exist in Industry CAM Engine. Closure is automatic, deterministic, and invisible to the user.

### Requirement 32: Corner Breaks Between Segments (P1.5 — After Pipeline Verification)

**User Story:** As a CNC machinist, I want to easily add a radius, fillet, or chamfer between profile segments without manually calculating start/end points, so that I can create smooth, deburr-free parts with minimal effort.

**Implementation Phase:** P1.5 — The data model and UI fields are included from day one, but the geometry computation is implemented AFTER the basic pipeline is verified working with raw segments. This avoids risking the core pipeline on fillet/chamfer geometry before the fundamentals are proven.

#### Acceptance Criteria

1. BETWEEN any two adjacent profile segments, THE user SHALL have the option to define a **corner break** with one of the following types:
   - **None** (default) — sharp corner, no modification
   - **Fillet/Radius** — a tangent arc of user-specified radius connecting the two segments
   - **Chamfer** — a straight line at user-specified size and angle connecting the two segments

2. FOR fillet/radius corner breaks:
   - The user specifies the radius (inches)
   - The fillet arc is tangent to both adjacent segments
   - Both segments are trimmed back equally (equidistant from the theoretical intersection point)
   - The fillet arc connects the trimmed endpoints smoothly (G1 continuity — tangent at both junctions)

3. FOR chamfer corner breaks:
   - The user specifies the chamfer size (inches, measured along each segment from the corner)
   - Optionally specifies the angle (default 45°)
   - Both segments are trimmed back by the chamfer size
   - A straight line (chamfer) connects the trimmed endpoints

4. THE corner break SHALL be computed by the geometry kernel (Build123d fillet/chamfer operations on the profile wire) — NOT by manual coordinate arithmetic. This maintains the "No Hand Math" rule (Requirement 12).

5. THE corner break computation SHALL happen inside `geometry/zone_builder.py` during profile wire construction:
   - User segments are assembled into a wire
   - Corner breaks are applied to the wire vertices using Build123d's `fillet()` or `chamfer()` operations
   - The modified wire (with fillets/chamfers) becomes the profile boundary for zone construction
   - The original user segments (without breaks) are preserved in the conversational file for editing

6. THE Program Tab segment list SHALL display corner break options between each pair of adjacent segments:
   - A small row or dropdown between segment rows: [None | Fillet R=___ | Chamfer ___×___°]
   - The real-time profile preview SHALL show the corner break geometry (arc or chamfer line) when defined
   - Invalid corner breaks (radius too large for the corner geometry) SHALL show an inline error

7. THE conversational JSON file SHALL store corner breaks as part of the segment data:
   ```json
   "segments": [
     {"type": "line", "x": 0.5, "z": 0.0},
     {"corner_break": {"type": "fillet", "radius": 0.030}},
     {"type": "line", "x": 0.5, "z": -0.5},
     {"corner_break": {"type": "chamfer", "size": 0.020, "angle": 45}},
     {"type": "line", "x": 1.0, "z": -0.5}
   ]
   ```

8. THE ProfileMove dataclass SHALL NOT be modified for corner breaks. Corner breaks are stored separately (between segments) and applied during zone construction. The user's raw segments remain clean and editable.

9. VALIDATION for corner breaks:
   - Fillet radius must be achievable given the corner angle and adjacent segment lengths (radius too large → ERROR with suggestion)
   - Chamfer size must not exceed half the length of either adjacent segment
   - Corner breaks at the first segment start or last segment end are not allowed (no corner to break)

10. THE design inspiration is Mazak's conversational system (ShopTurn/Mazatrol) where corner breaks are defined as properties of the junction between contour elements, not as separate segments the user must calculate.

11. FOR P1 implementation: the corner break UI fields SHALL be present but disabled with tooltip: "Available after pipeline verification." The data model includes the fields so that conversational files saved during P1 can include corner break definitions that will work when the feature is enabled.

### Requirement 25: GUI Color System

**User Story:** As a machinist working long shifts, I want the GUI to use a calm, legible color scheme where color communicates meaning intuitively, so that I can read values at a glance and understand system state without reading labels.

#### Acceptance Criteria

1. THE GUI SHALL use the color system defined in #[[file:.kiro/steering/gui-color-system.md]] for ALL visual elements. No ad-hoc color choices outside this system.

2. THE base background SHALL be deep navy-teal (`#21536E`) — blue-forward, low glare, high contrast for graph traces and text.

3. THE color system SHALL follow semantic meaning consistently throughout the GUI:
   - **Green/Teal** (`#5E9E91` family) = safe, go, correct, feed moves, valid states, Generate button
   - **Blue** (`#3373C4` family) = interactive, informational, arc moves, focus states, buttons
   - **Coral/Peach** (`#E56E72` / `#FFC8A5` family) = caution, advisory, warnings, rapid moves
   - **Crimson/Maroon** (`#8B2030` family) = danger, stop, error, gouge zones, E-Stop
   - **White** (`#F0F4F8`) = precision data (DRO, coordinates, profile boundary)
   - **Gray/Steel** (`#7D9AB3` family) = structure, disabled states, reference geometry

4. ALL text on dark backgrounds SHALL meet WCAG AA contrast ratio (minimum 4.5:1). Primary text `#F0F4F8` on base `#21536E` = 8.5:1.

5. ALL graph traces SHALL meet minimum 3:1 contrast ratio against the graph background (`#21536E`).

6. ERROR and SUCCESS states SHALL be distinguishable by luminance (not just hue) to support color-blind operators. Crimson (`#8B2030`) and teal (`#5E9E91`) differ by >3:1 in relative luminance.

7. THE GUI SHALL use NO pure black (`#000000`) for backgrounds and NO pure white (`#FFFFFF`) for large areas. Dark backgrounds use `#21536E`; text uses `#F0F4F8`. Only the animated tool dot uses true white.

8. ALL touch targets SHALL be minimum 44×44 pixels for reliable touch interaction on the 15.6" panel.

9. THE color palette SHALL be implemented as a single `COLORS` dictionary in `gui/colors.py` — all widgets reference this dictionary, never hardcoded hex values. Changing a color in one place changes it everywhere.

10. THE font pairing SHALL be:
    - UI text: Inter (clean, legible at small sizes)
    - DRO / coordinates / G-code: JetBrains Mono (monospace, clear digit distinction)
    - Fallbacks: Segoe UI (Windows), DejaVu Sans (Linux)

11. THE visual design priority order SHALL be:
    1. Operator legibility (readable at arm's length)
    2. Sensible color logic (meaning without labels)
    3. Pleasant, calm aesthetic (reduces fatigue over long sessions)

### Requirement 26: G-Code Editor Tab

**User Story:** As a machinist, I want a built-in G-code text editor where I can load, view, search, edit, and preview any G-code program — so that I can refine individual lines, make bulk edits, and visually verify the toolpath without leaving the GUI.

#### Acceptance Criteria

1. THE GUI SHALL include an "Edit" tab in the main tab bar that provides a full-featured G-code text editor.

2. THE editor SHALL use a monospace font (JetBrains Mono) with G-code syntax highlighting:
   - G-codes (G00, G01, G02, G03, G20, G90, etc.) — blue (`#5494DA`)
   - M-codes (M2, M3, M5, M6, etc.) — teal (`#5E9E91`)
   - Axis words (X, Z, I, K, R, F) — white (`#F0F4F8`)
   - Numeric values — light blue (`#A8D4F5`)
   - Comments (parentheses or semicolon) — subtle text (`#9AAFC2`)
   - N-numbers — gray (`#7D9AB3`)
   - Line numbers in gutter — dim, non-editable

3. THE editor SHALL support loading G-code via:
   - **File picker** — standard file dialog to open .ngc, .nc, .gcode, .tap files
   - **Paste** — Ctrl+V or right-click paste from clipboard
   - **Drag and drop** — drag a file onto the editor area
   - **From Program Tab** — "Send to Editor" button on the Program Tab that copies the generated G-code into the editor

4. THE editor SHALL provide a **Find/Replace** toolbar (Ctrl+F to open, Esc to close):
   - Find field with match highlighting (all occurrences highlighted in the editor)
   - Replace field with "Replace" (single) and "Replace All" buttons
   - Case-sensitive toggle
   - Match count display ("3 of 17 matches")
   - Enter key advances to next match
   - Highlighted matches use a distinct background color (`#7AB5A840`) that doesn't obscure text

5. THE editor SHALL provide the following file operations:
   - **Save** (Ctrl+S) — save to current file path (if loaded from file)
   - **Save As** (Ctrl+Shift+S) — save to new file path via file dialog
   - **Clear** — clear the entire editor content with a confirmation prompt: "Clear editor? This cannot be undone." with "Clear" and "Cancel" buttons
   - **Reload** — reload from the original file (if loaded from file), discarding edits

6. THE editor SHALL indicate unsaved changes:
   - Modified indicator in the tab title (e.g., "Edit •" or asterisk)
   - If the user navigates away from the Edit tab with unsaved changes, no prompt (edits are preserved in memory until explicitly cleared)

7. THE editor SHALL provide a **"Preview"** button that:
   - Parses the current editor content via `gcode_parser.parse()`
   - Sends the parsed moves through the graph display pipeline (same as round-trip overlay)
   - Switches to the Program Tab graph (or a split view) showing the toolpath visualization
   - Displays: feed moves (green), rapids (coral dashed), arcs (blue) on the graph
   - Stock boundary shown if parseable from header comments
   - If parsing fails (invalid G-code), shows error with line number and description in the editor (highlights the offending line in red)

8. THE Preview function SHALL use the same `gcode_parser.parse()` → `graph_adapter.convert_from_moves()` pipeline as the G-code to DXF utility (Requirement 21). No separate parsing implementation.

9. THE editor SHALL support standard text editing operations:
   - Undo/Redo (Ctrl+Z / Ctrl+Y) with full history
   - Select All (Ctrl+A)
   - Line numbers in left gutter
   - Current line highlight (subtle background tint)
   - Tab key inserts spaces (configurable: 2 or 4 spaces, default 2)
   - Auto-indent on Enter (match previous line indentation)
   - Go to line number (Ctrl+G)

10. THE editor SHALL support touch-friendly interaction:
    - Text selection via long-press and drag
    - Scroll via swipe (with momentum/inertia)
    - Toolbar buttons large enough for touch (44×44px minimum)
    - Physical keyboard always available — no on-screen keyboard needed

11. THE editor background SHALL use `#21536E` (matching the GUI base) with text in `#F0F4F8`. The gutter uses a slightly darker shade (`#1A4560`). This maintains visual consistency with the rest of the GUI.

12. THE editor SHALL handle large files (up to 10,000 lines) without lag. Syntax highlighting SHALL be computed lazily (visible lines only, not the entire document on every keystroke).

13. THE editor is a VIEWER/EDITOR only — it does NOT send G-code to LinuxCNC. Loading a program for execution is handled by a separate "Load Program" function (outside the Edit tab). The Edit tab is for inspection and modification.

### Requirement 27: Tool Table Tab

**User Story:** As a machinist, I want a tool table that shows me each tool's geometry, offsets, and wear values — with a visual preview of the tool shape from my perspective at the lathe — so that I can manage my tools confidently and the engine has accurate data for toolpath generation.

#### Acceptance Criteria

##### Tool Table Structure

1. THE GUI SHALL include a "Tools" tab in the main tab bar that displays the tool table as an editable list/grid.

2. EACH tool entry SHALL contain the following fields:

   | Field | Type | Description |
   |-------|------|-------------|
   | Tool # | Integer (1-99) | Tool pocket number (matches LinuxCNC tool table) |
   | Description | Text (free-form) | User label, e.g., "Aluminum Finishing Tool" |
   | Tool Type | Dropdown | Turning, Boring, Threading, Grooving |
   | Insert Shape | Dropdown (filtered by Tool Type) | VNMG, CNMG, CCMT, DNMG, WNMG, etc. + "Custom" |
   | Nose Radius (RE) | Float (inches) | Tool nose radius |
   | Tip Angle | Float (degrees) | Included angle of insert (auto-populated from Insert Shape, editable) |
   | Edge Length | Float (inches) | Cutting edge length |
   | Orientation | Dropdown (filtered by Tool Type) | LinuxCNC orientation 1-9 |
   | Direction | Dropdown | R (right-hand), L (left-hand), N (neutral) |
   | X Offset | Float (inches, diameter) | Tool X offset from reference |
   | Z Offset | Float (inches) | Tool Z offset from reference |
   | X Wear | Float (inches, diameter) | X wear compensation (additive to offset) |
   | Z Wear | Float (inches) | Z wear compensation (additive to offset) |

3. THE Tool Type dropdown SHALL filter available Insert Shapes and Orientations:

   | Tool Type | Available Insert Shapes | Available Orientations |
   |-----------|------------------------|----------------------|
   | Turning | CNMG, VNMG, DNMG, WNMG, CCMT, DCMT, VCMT, TCMT, Custom | 1, 2, 3, 4 (OD orientations) |
   | Boring | CCMT, DCMT, VCMT, TCMT, Custom | 5, 6, 7, 8 (ID orientations) |
   | Threading | Threading inserts (60°, 55°, ACME 29°), Custom | 1, 2 (OD), 5, 6 (ID) |
   | Grooving | Grooving inserts (by width), Custom | 1, 2 (OD), 5, 6 (ID) |

4. WHEN the user selects an Insert Shape, THE following fields SHALL auto-populate (but remain editable):
   - **Tip Angle**: from insert geometry (e.g., VNMG → 35°, CNMG → 80°, DNMG → 55°, WNMG → 80°, TCMT → 60°)
   - **Nose Radius**: common default for that family (user should verify against actual insert)

5. THE "Custom" insert shape option SHALL leave all angle fields blank for the user to fill in manually.

##### Tool Shape Visualization

6. THE Tools tab SHALL display a simple 2D graphic of the selected tool's shape, drawn from the **lathe operator's perspective** (looking at the cross-slide from the front of the machine):
   - X axis = vertical (up = away from centerline)
   - Z axis = horizontal (left = toward chuck, right = toward tailstock)
   - The tool tip points toward the workpiece
   - The insert shape is drawn based on: tip angle, nose radius, edge length, orientation

7. THE tool graphic SHALL update in real-time as the user edits angle, radius, or orientation fields — providing immediate visual feedback that the geometry is correct.

8. THE tool graphic SHALL be drawn using simple Qt geometry (QPainterPath) — NOT the engine's ToolShape class. This is a UI preview, not a precision computation. The engine's `tools/tool_shape.py` computes the actual geometry for toolpath generation independently.

9. THE tool graphic SHALL show:
   - Insert outline (based on tip angle and edge length)
   - Nose radius arc at the tip
   - Orientation indicator (arrow showing cutting direction)
   - Shank/holder as a simple rectangle extending away from the insert
   - Color: insert in teal (`#5E9E91`), holder in gray (`#7D9AB3`), nose radius arc highlighted in white

##### Offsets and Wear

10. THE X Offset and Z Offset fields represent the tool's position relative to the machine reference point. These are set during tool touch-off and typically don't change unless the tool is removed and re-mounted.

11. THE X Wear and Z Wear fields represent accumulated wear compensation. These are adjusted during production to maintain dimensional accuracy. The effective tool position is: `effective_offset = offset + wear`.

12. WEAR values SHALL be displayed with a distinct visual treatment (e.g., slightly different background color or label) to distinguish them from the base offsets — preventing the common mistake of editing the offset when you meant to edit the wear.

13. THE tool table SHALL write to LinuxCNC's `tool.tbl` format for compatibility:
    ```
    T1 P1 X+0.000000 Z+0.000000 D0.031200 I0 J0 Q1 ;Description
    ```
    Where D = nose radius diameter (2×RE), I/J = front/back angle (orientation-derived), Q = orientation number.

##### Persistence and Backup

14. THE tool table SHALL auto-save on every change (field edit, tool add/delete). Changes are immediately persisted.

15. THE Tools tab SHALL also provide explicit **Save** and **Save As** buttons:
    - **Save** — writes to the current tool table file path (same as auto-save target)
    - **Save As** — exports to a user-chosen file path via file dialog (does not change the auto-save target)

15. AT the beginning of each GUI session (application launch), THE system SHALL create a timestamped backup of the current tool table:
    - Backup location: `tool_backups/` directory alongside the tool table
    - Filename format: `tool_table_YYYY-MM-DD_HHMMSS.tbl`
    - Maximum backups retained: 5 (configurable)
    - When the limit is reached, the oldest backup is deleted before creating a new one

16. THE user SHALL be able to:
    - **Load** a tool table from file (file picker, .tbl format)
    - **Export** the current tool table to a file (Save As)
    - **Restore** from a backup (dropdown showing available backups with timestamps)

##### Integration with Engine

17. THE `ToolDef` dataclass used by the engine (Requirement 4) SHALL be populated from the tool table entry for the selected tool. The mapping is:
    - `nose_radius` ← Tool table RE field
    - `tip_angle` ← Tool table Tip Angle field
    - `edge_length` ← Tool table Edge Length field
    - `orientation` ← Tool table Orientation field
    - `direction` ← Tool table Direction field

18. WHEN the user selects a tool in the Program Tab (for roughing or finishing), THE engine receives the full `ToolDef` from the tool table — not just a tool number. The tool table is the single source of truth for tool geometry.

19. IF a tool's geometry changes in the tool table after a program was generated, THE Program Tab SHALL indicate that the toolpath is stale (parameters changed since last generation) — same behavior as any other parameter change (Requirement 23).

### Requirement 28: GUI Tab Architecture and Reserved Tabs

**User Story:** As a machinist, I want the GUI to serve as my complete machine interface — not just a programming tool — so that I can jog, run programs, tune the machine, and look up reference information without leaving the application.

#### Acceptance Criteria

1. THE GUI SHALL use a tab-based layout with the following planned tabs (in order):

   | Tab | Priority | Status | Purpose |
   |-----|----------|--------|---------|
   | **Program** | P1 — Build first | Specified (Req 18, 23, 24) | Conversational programming + toolpath visualization |
   | **Edit** | P1 — Build first | Specified (Req 26) | G-code text editor with preview |
   | **Tools** | P1 — Build first | Specified (Req 27) | Tool table management + geometry preview |
   | **Debug** | P1 — Build first | Specified (Req 19) | Diagnostics, export, pipeline visibility |
   | **Run** | P2 — Build second | Reserved (this requirement) | Program loading, execution, live DRO, cycle control |
   | **Manual** | P2 — Build second | Reserved (this requirement) | Jogging, handwheel, MDI, manual spindle control |
   | **Setup** | P3 — Build third | Reserved (this requirement) | HAL configuration, stepper/encoder tuning, commissioning |
   | **Help** | P3 — Build third | Reserved (this requirement) | G/M code reference, LinuxCNC documentation, user guides |

2. THE tab bar SHALL be designed to accommodate all 8 tabs on a 1920×1080 display without scrolling or overflow. Tab labels SHALL be short (≤6 characters) and touch-friendly (minimum 44px height).

3. THE architecture SHALL ensure that reserved tabs (Run, Manual, Setup, Help) can be implemented later WITHOUT modifying the existing P1 tabs. This means:
   - No shared mutable state between tabs (each tab owns its own state)
   - The pipeline and PlanResult are accessible to any tab that needs them (via the pipeline module)
   - LinuxCNC connection management is centralized (not embedded in any single tab)
   - The status bar (top) is independent of all tabs and always visible

4. THE **Run** tab (P2, reserved) SHALL eventually provide:
   - Program file loading (file picker → LinuxCNC `program_open()`)
   - Cycle Start / Feed Hold / Stop controls
   - Live DRO position display (from LinuxCNC status channel)
   - Program progress (current line, % complete)
   - Feed override and rapid override sliders
   - Toolpath display showing current position on the graph (live tracking)

5. THE **Manual** tab (P2, reserved) SHALL eventually provide:
   - Jog controls (X+, X-, Z+, Z-) with selectable increment (0.0001, 0.001, 0.010, 0.100, continuous)
   - Handwheel (MPG) mode selection and axis assignment
   - MDI input line (single G-code command entry and execution)
   - Home axis buttons (Home X, Home Z, Home All)
   - Manual spindle control (start CW, start CCW, stop — for our manual spindle with encoder)
   - Touch-off function (set current position as tool offset reference)

6. THE **Setup** tab (P3, reserved) SHALL eventually provide:
   - HAL pin viewer (read current HAL pin states for debugging)
   - Stepper tuning parameters (acceleration, velocity, step timing)
   - Encoder configuration (scale, direction, index)
   - Axis limit configuration (soft limits, home position, home sequence)
   - Mesa 7i96s/7i85s I/O mapping display
   - INI file parameter viewer (read-only display of current machine configuration)

7. THE **Help** tab (P3, reserved) SHALL eventually provide:
   - G-code reference library (all G-codes supported by LinuxCNC, with descriptions and examples)
   - M-code reference library (all M-codes, with machine-specific notes)
   - Canned cycle reference (G76 threading, G71/G72 roughing cycles if supported)
   - Quick-reference cards for common operations (tool touch-off procedure, homing sequence, etc.)
   - Link/reference to LinuxCNC documentation
   - Search function across all reference content

8. FOR the P1 build phase, THE reserved tabs (Run, Manual, Setup, Help) SHALL exist as tab buttons in the tab bar but display a simple placeholder message: "Coming soon — [Tab Name]". This ensures the tab bar layout is finalized from day one and the user sees the full planned interface.

9. THE LinuxCNC connection layer SHALL be designed as a centralized service (`gui/linuxcnc_service.py`) that any tab can access:
   - Status polling (position, mode, state, interp state)
   - Command sending (MDI, program control, jog)
   - Error/message handling
   - Connection state management (connected/disconnected/error)
   - Offline mode detection (Windows development — service returns demo data)

10. THE status bar (top of GUI, always visible regardless of active tab) SHALL display:
    - Machine state indicators (E-Stop, Power, Homed, Program status)
    - Live DRO (X diameter, Z inches) — always visible, not tab-dependent
    - Active G-codes (G20, G90, G54, etc.)
    - Feed/Rapid override percentages
    - Spindle RPM (from encoder)
    - Current tool number

### Requirement 29: Reserved Operations — Threading and Grooving/Parting

**User Story:** As a machinist, I want the system architecture to support threading and grooving/parting operations that will be built after the OD/ID profile engine is verified.

#### Acceptance Criteria

1. THE Program Tab SHALL support the following **parent block** types:
   - **OD Profile** (P1 — build first, fully specified)
   - **ID Profile** (P1 — build first, fully specified)
   - **Threading OD** (P2 — reserved, build after profile engine verified)
   - **Threading ID** (P2 — reserved, build after profile engine verified)
   - **Grooving OD** (P2 — reserved, build after profile engine verified)
   - **Grooving ID** (P2 — reserved, build after profile engine verified)
   - **Parting/Cutoff** (P2 — reserved, subset of grooving)

2. WITHIN OD/ID Profile parent blocks, the children are **segments** (line, arc) that define the profile contour — as specified in Requirements 18, 23, 24.

3. WITHIN Threading and Grooving parent blocks, the children SHALL be **parameter fields** (not segments). These operations are defined by numeric inputs (pitch, depth, width, position) rather than contour geometry.

4. THE pipeline architecture SHALL accommodate threading and grooving by:
   - Threading planner plugs into the same pipeline as turning planners (produces `List[ToolMove]`)
   - Grooving planner plugs into the same pipeline (produces `List[ToolMove]`)
   - Both pass through the same validation and G-code writer
   - Both produce PlanResult data that the graph can display

5. THREADING operations (when implemented) SHALL support:
   - Thread standards: UN (UNC/UNF/UNEF), NPT, Metric (M), ACME
   - Parameters: pitch/TPI, major diameter, thread length, infeed method, number of passes, spring passes
   - G76 output for LinuxCNC (with spindle encoder synchronization)
   - OD and ID threading using the same planner with mode parameter
   - Multi-start threads (lead = pitch × starts)
   - Thread data from #[[file:.kiro/steering/thread-data.md]]

6. GROOVING operations (when implemented) SHALL support:
   - Plunge grooving (radial feed to depth)
   - Peck grooving (retract cycles for chip control)
   - Multiple groove positions in one operation
   - Groove width, depth, and position parameters
   - OD and ID grooving
   - Parting/cutoff as a special case (groove to centerline or near-centerline)

7. THE engine verification strategy SHALL be:
   - Phase 1: Verify OD Profile pipeline end-to-end (face + rough + cleanup + finish)
   - Phase 2: Verify ID Profile pipeline (same engine, mode parameter)
   - Phase 3: Add threading planner (simpler geometry — no zone booleans needed)
   - Phase 4: Add grooving planner (simplest — rectangular geometry)

8. FOR the P1 build, threading and grooving parent blocks SHALL appear in the Program Tab block selector as disabled/grayed options with tooltip: "Available after profile engine verification."

### Requirement 30: Conversational Program Save/Load Format

**User Story:** As a machinist, I want to save my conversational programs so I can pick up where I left off, make edits to existing programs, and share them between sessions — without losing any input parameters or contour information.

#### Acceptance Criteria

1. WHEN the user generates a program from the Program Tab, THE system SHALL save TWO files:
   - **G-code file** (`.ngc`) — the machine-executable program (standard G-code text)
   - **Conversational file** (`.json`) — the complete user input state for reloading into the GUI

2. THE conversational file format SHALL be JSON (human-readable, easily parsed, compatible with Python's stdlib `json` module, no external dependencies).

3. THE conversational JSON file SHALL contain ALL information needed to fully reconstruct the Program Tab state:
   ```json
   {
     "version": "1.0",
     "created": "2026-05-14T22:30:00",
     "modified": "2026-05-14T22:45:00",
     "blocks": [
       {
         "type": "od_profile",
         "stock": {
           "diameter": 1.25,
           "z_start": 0.0,
           "z_end": -2.0
         },
         "roughing": {
           "doc_dia": 0.030,
           "feed": 0.005,
           "strategy": "staircase",
           "peck_enabled": false,
           "peck_length": null,
           "tool_number": 1
         },
         "finishing": {
           "passes": 1,
           "doc_dia": 0.002,
           "feed": 0.003,
           "tool_number": 1
         },
         "spindle_rpm": 1200,
         "segments": [
           {"type": "line", "x": 1.0, "z": 0.0},
           {"type": "line", "x": 1.0, "z": -0.5},
           {"type": "arc", "x": 1.0, "z": -1.0, "radius": 0.25},
           {"type": "line", "x": 1.0, "z": -2.0}
         ]
       }
     ]
   }
   ```

4. THE Program Tab SHALL support the following file operations:
   - **Save** (Ctrl+S) — save conversational JSON to current file path (if previously saved/loaded)
   - **Save As** (Ctrl+Shift+S) — save conversational JSON to new file path via file dialog
   - **Open** (Ctrl+O) — load a conversational JSON file via file dialog, populating all Program Tab fields
   - **New** — clear all fields to start a fresh program (with confirmation if unsaved changes exist)

5. WHEN a conversational file is opened, THE Program Tab SHALL:
   - Populate all input fields (stock params, cutting params, tool selection, spindle RPM)
   - Populate the segment list with all profile segments
   - Update the real-time profile preview immediately
   - NOT auto-generate (user must click "Generate" to see the toolpath)

6. THE conversational file SHALL be independent of the G-code file. The user can:
   - Save the conversational file without generating G-code (save work-in-progress)
   - Generate G-code without saving the conversational file (quick one-off)
   - Save both simultaneously (normal workflow after generation)

7. THE file dialog SHALL default to a user-configurable programs directory (e.g., `~/linuxcnc/nc_files/`) and remember the last-used directory.

8. THE conversational file SHALL include a `version` field for forward compatibility. If the format changes in future versions, the loader can detect and migrate old files.

9. THE G-code output SHALL include a header comment referencing the conversational file:
   ```gcode
   ( Conversational source: my_part.json )
   ( Generated: 2026-05-14 22:45:00 )
   ```

10. THE conversational file format SHALL be extensible — threading and grooving blocks (when implemented) add new block types to the `blocks` array without changing the file structure.

### Requirement 31: Spindle Speed and Machine Control Conventions

**User Story:** As a machinist with a manual spindle (no VFD), I want the GUI to let me set spindle RPM as a parameter that the program knows about, without attempting automatic speed control or CSS.

#### Acceptance Criteria

1. THE Program Tab SHALL include a **Spindle RPM** input field where the user enters their chosen speed. This value is used for:
   - G-code header comment (informational: `( RPM: 1200 )`)
   - Threading dwell calculations (peck dwell = 5 rotations / RPM × 60 seconds)
   - Threading synchronization (G76 requires known spindle speed for encoder sync)
   - Display in the program summary

2. THE engine SHALL NOT recommend or calculate spindle speed based on diameter, material, or cutting speed. The operator chooses RPM based on their experience and the manual spindle's available speeds.

3. THE G-code output SHALL emit `S[rpm]` at the program start (informational — LinuxCNC uses this for threading sync with the spindle encoder). No M3/M4 (spindle start) commands — the spindle is manually controlled.

4. THE engine SHALL NOT emit:
   - G96 (constant surface speed) — not available without VFD
   - G97 (constant RPM) — implied by default, no need to emit explicitly
   - M3/M4 (spindle start CW/CCW) — manual spindle
   - M5 (spindle stop) — manual spindle

5. THE status bar SHALL display live spindle RPM from the encoder (when connected to LinuxCNC). This is a READ from the encoder, not a command to the spindle.

6. FOR threading operations (when implemented), THE spindle encoder provides the synchronization signal. The user MUST have the spindle running at the programmed RPM before starting a threading cycle. The GUI SHALL display a warning if the measured RPM differs from the programmed RPM by more than 5%.

7. NO coolant control (M8/M9) SHALL be emitted by the engine. Coolant is manually controlled by the operator.

### Requirement 21: G-Code to DXF Conversion Utility

**User Story:** As a machinist, I want to convert any G-code program into a DXF file so I can inspect the toolpath in CAD software, measure geometry, and verify the program before running it. As a developer, I want a structured G-code → DXF pipeline that can serve as a foundation for future automated round-trip verification testing.

#### Acceptance Criteria

##### User-Facing (Export Panel + Standalone)

1. THE Debug Tab's Export panel SHALL include a "G-code → DXF" function that:
   - Accepts a G-code file path (file picker) OR the currently generated G-code from PlanResult
   - Parses the G-code into a `List[ToolMove]` via `gcode_parser.parse()`
   - Exports the parsed moves as a layered DXF via `dxf_exporter.export_from_moves()`
   - Saves to a user-selected output path

2. THE G-code → DXF export SHALL produce a DXF with the following layers:
   - `RAPID` (color 1/red) — G00 moves as LINE entities
   - `FEED_LINEAR` (color 3/green) — G01 moves as LINE entities
   - `FEED_ARC_CW` (color 5/blue) — G02 moves as true ARC entities
   - `FEED_ARC_CCW` (color 5/blue) — G03 moves as true ARC entities
   - `ENDPOINTS` (color 7/white) — POINT entities at every move start/end position
   - `STOCK_BOUNDARY` (color 8/gray) — if stock parameters are available in the G-code header comments
   - `ANNOTATIONS` (color 2/yellow) — TEXT entities showing N-numbers at pass boundaries

3. THE G-code → DXF conversion SHALL handle the full G-code subset the engine emits:
   - G00, G01, G02, G03 with X, Z axis words (diameter mode)
   - I, K (incremental arc center) and R (radius) arc formats
   - Modal state tracking (G-code persists until changed, feed rate persists)
   - Comments parsed for metadata (pass type, stock parameters) but not as geometry

4. THE G-code → DXF conversion SHALL also be available as a standalone CLI utility:
   ```
   python -m outputs.gcode_to_dxf input.ngc output.dxf
   ```
   This allows use outside the GUI (batch processing, CI pipelines, developer debugging)

5. THE DXF output SHALL use the same coordinate convention as the graph:
   - X axis: RADIUS (DXF geometry is in true physical coordinates)
   - Z axis: INCHES
   - G-code X words (diameter) are divided by 2.0 during parsing before DXF export
   - This means the DXF can be overlaid directly on kernel-generated zone DXFs for comparison

6. ARC entities in the DXF SHALL be true DXF ARC entities (not polyline approximations):
   - Arc center computed from I,K (incremental from start) or from R (radius)
   - Start angle and end angle computed from start/end points and center
   - If arc geometry is invalid (center doesn't match radius within tolerance), the move is exported as a LINE with an annotation noting the error

7. THE user SHALL be able to generate a DXF from:
   - The engine's own generated G-code (primary use case — "show me what I just generated")
   - An external .ngc file loaded from disk (secondary use case — "show me what this legacy program does")
   - Both paths use the same parser and exporter — no dual implementations

##### Developer-Facing (Architecture for Future Testing)

8. THE G-code → DXF pipeline SHALL be structured as composable functions:
   ```python
   # Step 1: Parse G-code text into structured moves
   moves: List[ToolMove] = gcode_parser.parse(gcode_text)
   
   # Step 2: Export moves to DXF
   dxf_exporter.export_from_moves(moves, output_path, options)
   
   # Step 3 (future): Compare two DXFs for geometric equivalence
   # diff = dxf_comparator.compare(dxf_a, dxf_b, tolerance)
   ```
   Step 3 is NOT implemented now — it is reserved for a future side-quest to validate the approach before relying on it for automated testing.

9. THE `gcode_parser.parse()` function SHALL return the same `List[ToolMove]` dataclass that the pipeline produces internally. This means:
   - A DXF generated from PlanResult.tool_moves (direct) and a DXF generated from parse(write(PlanResult)) (round-trip) should be geometrically identical
   - This property is the foundation for future round-trip testing, but is NOT automatically verified until the side-quest confirms the approach works

10. THE `dxf_exporter` module SHALL expose two entry points:
    - `export_from_plan_result(plan_result, output_path)` — full export with zones, toolpath, profile, stock (used by Export panel)
    - `export_from_moves(moves, output_path, options)` — toolpath-only export from parsed moves (used by G-code → DXF utility)
    Both use the same underlying DXF writing logic — no duplication.

11. THE G-code → DXF utility SHALL preserve move metadata as DXF entity attributes (extended data / XDATA) where available:
    - Move type (rapid/feed/arc)
    - N-number (line number from G-code)
    - Feed rate (for feed moves)
    - Pass type (if parseable from comments: face/rough/cleanup/finish)
    This metadata enables future tooling to query the DXF programmatically.

12. THE G-code → DXF utility SHALL handle malformed G-code gracefully:
    - Missing axis words: use last known position (modal behavior)
    - Invalid arc geometry: export as LINE with error annotation, continue parsing
    - Unrecognized G-codes: skip with warning, don't halt
    - Empty file or no motion commands: produce empty DXF with warning

13. THE module structure SHALL be:
    - `outputs/gcode_parser.py` — G-code text → List[ToolMove] (already required by Req 17)
    - `outputs/dxf_exporter.py` — List[ToolMove] or PlanResult → DXF file (already required by Req 19)
    - `outputs/gcode_to_dxf.py` — CLI entry point that chains parser → exporter (new, thin wrapper)
    No new modules needed — this requirement composes existing pieces.

## Appendix A: Migration Path from my-lathe

### What to Keep (copy directly)
- `models/profile.py` — ClosedProfile, ProfileMove (proven data structures)
- `models/stock.py` — StockDef
- `models/operations.py` — RoughingParams (extended with ToolDef)
- `models/constants.py` — TOLERANCE, coordinate conventions
- `tests/oracle/` — Shapely-based correctness oracle
- `tests/correctness_properties.py` — property-based test definitions
- `outputs/sim_adapter.py` — simulation move format
- `outputs/dxf_exporter.py`, `outputs/svg_exporter.py` — visualization exports

### What to Rewrite
- `engines/geometry.py` → `geometry/zone_builder.py` + `geometry/zone_query.py` (split construction from queries)
- `engines/turning_planner.py` → `planners/staircase_planner.py` + `planners/offset_contour_planner.py` (two strategies, one interface)
- `engines/cleanup_planner.py` → `planners/cleanup_planner.py` (uses boundary_wire_extraction only, no compute_cleanup_edges)
- `engines/face_planner.py` → `planners/face_planner.py` (uses Fiber queries, shared transition logic)
- `outputs/gcode_formatter.py` → `outputs/gcode_writer.py` (position-tracking, validation)
- `pipeline/pipeline.py` → `pipeline/pipeline.py` (adds validation stages, tool flow)

### What to Delete (not carried forward)
- `engines/cadquery_engine.py` — legacy, replaced by Build123d
- `roughing_engine.py`, `roughing_engine_v2.py` — legacy, replaced by planners
- `zone_definitions.py` — legacy analytical zone code
- `turning_staircase.py` — legacy, absorbed into staircase_planner
- `face_zone_planner.py` — legacy, absorbed into face_planner
- `edge_case_rules.py` — eliminated by top-down rule propagation
- `_legacy.py` — self-explanatory

## Appendix B: Reference Codebase Cross-Map

| Industry CAM Engine Module | Primary Reference | Pattern Adopted |
|---|---|---|
| `intervals/fiber.py` | OpenCamLib `fiber.cpp` | Fiber collects Intervals, addInterval with merge |
| `intervals/interval.py` | OpenCamLib `interval.cpp` | contains/overlaps/merge/gap operations |
| `planners/offset_contour_planner.py` | Bapt_CAM `AdaptativeOp.py` | Peel milling — offsets from profile outward |
| `planners/staircase_planner.py` | liblathe `rough.py` | Horizontal passes with boundary intersection |
| `transitions/transition.py` | Bapt_CAM `_pass_transitions` | Named transition types (retract vs link) |
| `tools/tool_shape.py` | liblathe `tool.py` | Tool as segment group geometry |
| `tools/tool_def.py` | FreeCAD Turning Addon `PathTurnBase.py` | Tool params flow UI → engine |
| `outputs/gcode_writer.py` | Bapt_CAM `GcodeWriter.py` | Position tracking, feed suppression |
| `geometry/adaptive_sampling.py` | OpenCamLib `adaptivewaterline.cpp` | Cosine-limit flatness predicate |
| `validation/gouge_checker.py` | liblathe `rough.py` inline check | `intersectsGroup(internalOffset)` pattern |
| `validation/polygon_builder.py` | my-lathe `shapely_oracle.py` | Promoted from test-only to runtime with adaptive densification |
| `geometry/zone_builder.py` | my-lathe `geometry.py` | Build123d Face booleans (proven) |
| `geometry/zone_query.py` | my-lathe `zone_query.py` | ZoneQueryAPI (proven, with caching added) |

## Appendix C: Your Question About Offset-Contour for Cleanup

> "Could this apply to generating our cleanup pass? Instead of staircase to cleanup to finish we could have the staircase act more like the cleanup?"

Yes. In the offset-contour strategy, the distinction between "roughing" and "cleanup" dissolves. Each pass IS a profile-following contour at a different offset distance. The last roughing pass is already at `fin_allowance` offset — it IS the cleanup pass. The finish pass is at zero offset — it IS the profile.

This means:
- **Staircase strategy**: Rough (horizontal passes) → Cleanup (one profile-following pass at fin_allowance) → Finish (profile at zero offset)
- **Offset-contour strategy**: Pass N at N×DOC offset → ... → Pass 2 at 2×DOC offset → Pass 1 at 1×DOC offset (≈ cleanup) → Pass 0 at zero offset (= finish)

The offset-contour approach eliminates the cleanup pass as a separate concept. Every pass follows the profile shape. The "staircase" of material left behind by horizontal passes (which the cleanup pass exists to remove) simply doesn't exist.

This is architecturally cleaner AND produces better surface finish on the roughing passes (no staircase steps to clean up). The tradeoff is that offset-contour passes are longer (they follow the full profile length) and may have higher cycle time on simple straight profiles where horizontal passes are faster.

The spec supports both strategies (Requirement 3) so you can choose per-operation.
