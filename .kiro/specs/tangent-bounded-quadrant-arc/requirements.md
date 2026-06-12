# Requirements Document

## Introduction

The tangent-bounded quadrant arc ("Q" segment type) currently uses hand-math polyline approximation in the zone builder to construct its Build123d geometry. This feature replaces that approximation with proper Build123d/OCCT geometric primitives — using EllipticalCenterArc for axis-aligned cases and rational quadratic Bézier splines for off-axis cases. The finish planner's edge decomposition then converts these OCCT edges into G2/G3 circular arc sequences with chord-error tolerance, producing accurate G-code output. The negative-Q convention (concave scoop) mirrors the ellipse center to the opposite side of the chord. Preview rendering in program_tab.py retains the existing hand-math interpolation for real-time display performance.

## Glossary

- **Zone_Builder**: The module (`geometry/zone_builder.py`) that constructs Build123d Faces from profile segments for zone computation
- **Finish_Planner**: The module (`planners/finish_planner.py`) that extracts OCCT wire edges and converts them to ToolMove sequences via `_moves_from_edges`
- **Quadrant_Arc**: A tangent-bounded quarter-ellipse segment identified by the "Q" radius value in the segment list, where endpoints define a bounding box and the curve is tangent to horizontal at one endpoint and tangent to vertical at the other
- **Axis_Aligned**: A quadrant arc whose start and end points share either the same X coordinate or the same Z coordinate (within tolerance), making the arc a true circular quarter-arc
- **Off_Axis**: A quadrant arc whose start and end points differ in both X and Z, forming a true elliptical arc that requires a spline representation
- **EllipticalCenterArc**: A Build123d primitive that creates a circular or elliptical arc from center, radii, and angular parameters — used for axis-aligned quadrant arcs
- **Rational_Quadratic_Bezier**: A degree-2 rational NURBS curve (conic section) that exactly represents a quarter-ellipse with a single control point and appropriate weight — used for off-axis quadrant arcs
- **Chord_Error_Tolerance**: The maximum allowable deviation between an approximating circular arc and the true curve, used when decomposing elliptical/spline edges into G2/G3 sequences
- **Negative_Q**: A quadrant arc with -Q designation, indicating the ellipse center is mirrored to the opposite side of the chord connecting endpoints, producing a concave scoop profile
- **Edge_Decomposition**: The process in `_moves_from_edges` where non-circular OCCT edges (elliptical arcs, splines) are approximated as a sequence of G2/G3 circular arcs within chord-error tolerance
- **Alignment_Tolerance**: The numerical tolerance (matching the project's existing coordinate tolerance) used to determine whether two endpoint coordinates are "the same" for axis-aligned detection

## Requirements

### Requirement 1: Axis-Aligned Detection

**User Story:** As a developer, I want the zone builder to detect when a quadrant arc is axis-aligned, so that the simplest and most accurate geometric primitive (EllipticalCenterArc) is used automatically.

#### Acceptance Criteria

1. WHEN the Zone_Builder processes a Quadrant_Arc segment, THE Zone_Builder SHALL classify the arc as Axis_Aligned if the start and end points share the same X coordinate within Alignment_Tolerance
2. WHEN the Zone_Builder processes a Quadrant_Arc segment, THE Zone_Builder SHALL classify the arc as Axis_Aligned if the start and end points share the same Z coordinate within Alignment_Tolerance
3. WHEN the Zone_Builder processes a Quadrant_Arc segment where endpoints differ in both X and Z beyond Alignment_Tolerance, THE Zone_Builder SHALL classify the arc as Off_Axis

### Requirement 2: Axis-Aligned Quadrant Arc Construction

**User Story:** As a developer, I want axis-aligned quadrant arcs represented as EllipticalCenterArc primitives in Build123d, so that the geometry kernel provides exact arc geometry for offsetting and wire extraction.

#### Acceptance Criteria

1. WHEN a Quadrant_Arc is classified as Axis_Aligned, THE Zone_Builder SHALL construct an EllipticalCenterArc using the Build123d API with center and radius derived from the bounding box of the endpoints
2. THE Zone_Builder SHALL compute the arc center as the endpoint coordinate pair (start_X, end_Z) or (end_X, start_Z) depending on the tangent direction convention
3. THE Zone_Builder SHALL set the arc radius equal to the absolute difference between the non-shared endpoint coordinates (the single semi-axis dimension)
4. THE Zone_Builder SHALL orient the arc sweep to travel from start point to end point in the correct direction for the profile traversal

### Requirement 3: Off-Axis Quadrant Arc Construction

**User Story:** As a developer, I want off-axis quadrant arcs represented as rational quadratic Bézier splines in Build123d, so that true elliptical geometry is preserved without polyline approximation.

#### Acceptance Criteria

1. WHEN a Quadrant_Arc is classified as Off_Axis, THE Zone_Builder SHALL construct a rational quadratic Bézier spline using the Build123d/OCCT NURBS API
2. THE Zone_Builder SHALL set the spline start point to the segment start coordinates and the end point to the segment end coordinates
3. THE Zone_Builder SHALL compute the control point at the intersection of the tangent lines from both endpoints (the corner of the bounding box)
4. THE Zone_Builder SHALL assign the rational weight for the middle control point such that the spline exactly represents a quarter-ellipse (weight = cos(π/4) for a true quarter-ellipse conic)

### Requirement 4: Negative-Q Concave Center Mirroring

**User Story:** As a CNC programmer, I want negative-Q arcs to produce a concave scoop by mirroring the ellipse center to the opposite side of the chord, so that I can program both convex and concave quadrant profiles.

#### Acceptance Criteria

1. WHEN the radius value is "-Q" (Negative_Q), THE Zone_Builder SHALL mirror the ellipse center to the opposite side of the chord connecting the start and end points
2. WHEN a Negative_Q arc is Axis_Aligned, THE Zone_Builder SHALL construct an EllipticalCenterArc with the mirrored center producing a concave profile
3. WHEN a Negative_Q arc is Off_Axis, THE Zone_Builder SHALL construct a rational quadratic Bézier spline with the control point placed at the opposite bounding box corner, producing a concave profile
4. THE Zone_Builder SHALL apply the same axis-aligned detection logic to Negative_Q arcs as to positive-Q arcs

### Requirement 5: Polyline Removal from Zone Builder

**User Story:** As a developer, I want the zone builder to stop using polyline approximation for quadrant arcs, so that all geometry comes from Build123d primitives and offset operations produce accurate results.

#### Acceptance Criteria

1. THE Zone_Builder SHALL replace the current `interpolate_quadrant_arc` polyline call for face construction with EllipticalCenterArc or Rational_Quadratic_Bezier primitives as appropriate
2. THE Zone_Builder SHALL produce a valid closed Build123d wire containing the quadrant arc edge when constructing the profile face
3. WHEN the kernel performs offset operations on a face containing quadrant arc edges, THE offset result SHALL maintain geometric accuracy without polyline faceting artifacts

### Requirement 6: Edge Decomposition to G2/G3 Arcs

**User Story:** As a developer, I want the finish planner to decompose elliptical and spline edges from OCCT into G2/G3 circular arc sequences, so that the G-code writer receives only arc moves it can emit.

#### Acceptance Criteria

1. WHEN the Finish_Planner encounters an elliptical arc edge during wire extraction, THE Finish_Planner SHALL decompose the edge into a sequence of circular G2/G3 arcs
2. WHEN the Finish_Planner encounters a Bézier spline edge during wire extraction, THE Finish_Planner SHALL decompose the edge into a sequence of circular G2/G3 arcs
3. THE Finish_Planner SHALL ensure that the maximum deviation between each approximating circular arc and the original curve does not exceed the Chord_Error_Tolerance
4. THE Finish_Planner SHALL preserve the start and end points of the original edge exactly (no endpoint drift across decomposed arc segments)

### Requirement 7: Chord-Error Tolerance Configuration

**User Story:** As a CNC programmer, I want the chord-error tolerance to be configurable, so that I can balance between G-code file size and surface accuracy for different finishing requirements.

#### Acceptance Criteria

1. THE Finish_Planner SHALL use a Chord_Error_Tolerance parameter when decomposing non-circular edges to G2/G3 arcs
2. THE Chord_Error_Tolerance SHALL have a default value suitable for typical lathe finishing accuracy (matching the project's existing finish tolerance conventions)
3. WHEN Chord_Error_Tolerance is reduced, THE Finish_Planner SHALL produce more G2/G3 arc segments with smaller maximum deviation
4. WHEN Chord_Error_Tolerance is increased, THE Finish_Planner SHALL produce fewer G2/G3 arc segments while respecting the specified maximum deviation

### Requirement 8: G-code Output Compatibility

**User Story:** As a CNC programmer, I want quadrant arc toolpaths output as standard G2/G3 moves, so that any LinuxCNC controller can execute them without custom cycle support.

#### Acceptance Criteria

1. THE GCode_Writer SHALL emit only G2 (CW arc) and G3 (CCW arc) moves for quadrant arc toolpath segments — no native ellipse or spline G-codes
2. EACH emitted G2/G3 move SHALL include endpoint coordinates (X, Z) and incremental center offsets (I, K) as computed by the Finish_Planner edge decomposition
3. THE GCode_Writer SHALL produce the same output format for decomposed quadrant arc moves as for regular circular arc moves (no special handling required)

### Requirement 9: Preview Rendering via Kernel

**User Story:** As a developer, I want the preview renderer to use the same Build123d geometry as the zone builder for quadrant arcs, so that the display is a single source of truth and the hand-math interpolation code can be removed.

#### Acceptance Criteria

1. THE preview renderer (program_tab.py) SHALL construct quadrant arc geometry using Build123d (Spline or RadiusArc) and extract display points from the resulting OCCT edge
2. THE preview renderer SHALL NOT use `interpolate_quadrant_arc()` hand-math for quadrant arc visualization
3. THE preview renderer SHALL produce visually equivalent display output to the zone builder geometry (single source of truth)
4. THE preview rendering time for a profile containing quadrant arcs SHALL remain under 16ms total for typical profiles (up to 10 segments)

### Requirement 10: Model Builder Q Parsing

**User Story:** As a CNC programmer, I want to enter "Q" or "-Q" as the radius value in the segment list to define quadrant arcs, so that the input convention is clear and concise.

#### Acceptance Criteria

1. WHEN the model_builder encounters a radius value of "Q" (string), THE model_builder SHALL create a ProfileMove with `quadrant=True` and a positive-Q orientation flag
2. WHEN the model_builder encounters a radius value of "-Q" (string), THE model_builder SHALL create a ProfileMove with `quadrant=True` and a negative-Q orientation flag indicating concave center mirroring
3. THE segment_list validation SHALL accept both "Q" and "-Q" as valid radius values for arc segments
