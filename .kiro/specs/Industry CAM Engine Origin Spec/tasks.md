# Implementation Plan: Industry CAM Engine Origin Spec

## Overview

This plan implements the Industry CAM Engine following the strict module dependency chain: models → tools → geometry → intervals → planners → transitions → validation → outputs → pipeline → gui/components → gui/tabs. Each task is independently testable and builds incrementally on previous work.

## Tasks

- [x] 1. Set up project structure and constants
  - [x] 1.1 Create package structure with `__init__.py` files for all modules
    - Create directories: models/, tools/, geometry/, intervals/, planners/, transitions/, validation/, outputs/, pipeline/, gui/, gui/components/, tests/, tests/unit/, tests/properties/, tests/integration/, tests/oracle/, tests/architecture/
    - Each `__init__.py` exports the module's public API (initially empty, populated as classes are added)
    - Create `requirements.txt` with pinned versions: build123d==0.10.*, shapely==2.1.*, ezdxf==1.4.*, PyQt5==5.15.*, pyqtgraph==0.14.*, hypothesis>=6.0
    - Create `pyproject.toml` or `setup.cfg` with project metadata
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Implement `models/constants.py`
    - Define all system constants: TOLERANCE, TOLERANCE_SQ, CENTER_ARC_RADIUS_TOLERANCE_INCH, RADIUS_TOLERANCE, DISPLAY_TOLERANCE, DENSIFICATION_ERROR, SHAPELY_COS_LIMIT, DISPLAY_COS_LIMIT, MAX_DENSIFICATION_DEPTH, MAX_DISPLAY_DEPTH
    - _Requirements: 2.7, 13.4, 8.4_


- [x] 2. Implement models/ — Pure data structures (zero dependencies)
  - [x] 2.1 Implement `models/profile.py`
    - Define enums: SegmentType (LINE, ARC), MachiningMode (OD, ID)
    - Define frozen dataclasses: ProfileMove (segment_type, x, z, radius), ClosedProfile (segments, mode, z_start, z_end)
    - _Requirements: 1.4_

  - [x] 2.2 Implement `models/stock.py`
    - Define frozen dataclass: StockDef (diameter, z_start, z_end, pilot_hole_dia, mode)
    - _Requirements: 1.4, 11.1_

  - [x] 2.3 Implement `models/tool.py`
    - Define enums: ToolOrientation (1-9), ToolDirection (R, L, N), ToolType (turning, boring, threading, grooving)
    - Define frozen dataclass: ToolDef (tool_number, nose_radius, tip_angle, edge_length, orientation, direction, tool_type, rotation, description, x_offset, z_offset, x_wear, z_wear)
    - _Requirements: 4.1, 4.6_

  - [x] 2.4 Implement `models/params.py`
    - Define enum: RoughingStrategy (STAIRCASE, OFFSET_CONTOUR)
    - Define frozen dataclasses: RoughingParams (doc_dia, feed, strategy, fin_allowance, peck_enabled, peck_length, spindle_rpm), FinishingParams (passes, doc_dia, feed)
    - _Requirements: 3.1, 3.8_

  - [x] 2.5 Implement `models/moves.py`
    - Define enums: MoveType (RAPID, FEED, ARC_CW, ARC_CCW), PassType (FACE, ROUGH, CLEANUP, FINISH, TRANSITION)
    - Define frozen dataclass: ToolMove (move_type, x, z, feed, radius, center_i, center_k, pass_type, pass_index)
    - _Requirements: 5.1_

  - [x] 2.6 Implement `models/transitions.py`
    - Define enum: TransitionType (RETRACT_TRAVERSE_PLUNGE, PERPENDICULAR_LINK, STEP_OVER)
    - Define frozen dataclass: Transition (type, start_position, end_position, safe_x, moves)
    - _Requirements: 5.1_

  - [x] 2.7 Implement `models/results.py`
    - Define frozen dataclasses: SweptRegion (x_min, x_max, z_start, z_end, inner_boundary, outer_boundary), TurningPass (x_level, z_start, z_end, pass_index, pass_type, moves, swept_region), PlanResult (all fields per design)
    - _Requirements: 9.1, 10.7_

  - [x] 2.8 Implement `models/validation.py`
    - Define enums: Severity (ERROR, WARNING), PipelineStatus (SUCCESS, SUCCESS_WITH_WARNINGS, BLOCKED_BY_ERROR, CANCELLED_BY_USER)
    - Define frozen dataclasses: ValidationResult (severity, category, message, recommendation, consequence, location, pass_index, move_index), PipelineResult (plan_result, validations, warnings_overridden, status)
    - _Requirements: 6.6_

  - [x]* 2.9 Write unit tests for models/
    - Test all dataclass instantiation, frozen immutability, enum values
    - Verify ToolDef, ProfileMove, ToolMove field types and defaults
    - _Requirements: 1.4_


- [x] 3. Implement tools/ — Tool geometry and reach analysis
  - [x] 3.1 Implement `tools/tool_shape.py` — ToolShape class interface and segment computation
    - Implement `__init__(self, tool_def: ToolDef)` storing the def and computing segments
    - Implement `_compute_segments()` — compute tool physical outline as line segments from tip_angle, edge_length, nose_radius, orientation
    - Implement `get_reach_boundary()` — return coordinate pairs defining the reach envelope
    - _Requirements: 4.2, 4.3_

  - [x] 3.2 Implement `tools/tool_shape.py` — compensation and reach methods
    - Implement `get_compensation_offset(segment_angle, mode)` — TNR offset distance for a given profile direction
    - Implement `can_reach(x_dia, z, profile_curvature)` — check if tool can physically cut at position, raise ToolReachError if nose_radius > min_concave_radius
    - Define `ToolReachError` exception class
    - _Requirements: 4.3, 4.5_

  - [x]* 3.3 Write unit tests for tools/
    - Test segment computation for known tool geometries (CNMG 80°, VNMG 35°)
    - Test reach boundary for standard orientations
    - Test ToolReachError raised when TNR > concave radius
    - _Requirements: 4.2, 4.3, 4.5_

  - [x]* 3.4 Write property test for tool reach validation (Property 9)
    - **Property 9: Tool Reach Validation**
    - For any profile with concave arc radius R and ToolDef with nose_radius > R, pipeline raises ToolReachError
    - **Validates: Requirements 4.5**

- [x] 4. Checkpoint — Ensure models/ and tools/ tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 5. Implement geometry/ — Build123d zone construction and query API
  - [x] 5.1 Implement `geometry/zone_builder.py` — ZoneSet dataclass and closure computation
    - Define ZoneSet class with fields: finished_part, finish_allowance, material_to_rough, true_face, stock_face, roughing_boundary_wire, profile_boundary_wire
    - Implement `_append_closure_segments(profile, stock)` — compute 3 closure line segments (OD: centerline path, ID: stock OD path)
    - _Requirements: 1.5, 12.1_

  - [x] 5.2 Implement `geometry/zone_builder.py` — `build_zones()` function
    - Build closed profile contour from user segments + closure segments using Build123d Sketch/Wire
    - Create Finished Part face from closed contour
    - Offset profile by fin_allowance + nose_radius → Roughing Boundary wire
    - Create Stock face from stock parameters
    - Boolean subtract: Material to Rough = Stock - Finished Part - Finish Allowance
    - Create True Face zone
    - All coordinates in RADIUS for Build123d sketch plane
    - _Requirements: 1.5, 3.7, 4.4, 12.1_

  - [x] 5.3 Implement `geometry/zone_query.py` — ZoneQueryAPI class
    - Implement `__init__(self, zone_set: ZoneSet)`
    - Implement `boundary_at_x(x_dia, zone_name)` — query Z boundaries using BRepAlgoAPI_Section, return list of (z_start, z_end) pairs sorted Z descending
    - Implement `line_zone_intersection(start, end, zone_name)` — check if line segment intersects zone boundary
    - Implement `offset_boundary(distance)` — offset roughing boundary outward using Build123d offset operation
    - Implement `boundary_wire_extraction(zone_name)` — extract boundary edges as EdgeData objects (type, start, end, center, radius)
    - _Requirements: 2.5, 5.5, 12.2, 12.5, 13.2_

  - [x] 5.4 Implement `geometry/adaptive_sampling.py`
    - Implement `flatness_predicate(start, mid, end, cos_limit)` — OpenCamLib cosine-limit test
    - Implement `adaptive_densify_arc(start, end, center, radius, cos_limit, max_depth)` — recursive bisection until flat
    - Implement `_arc_midpoint(start, end, center, radius)` — angle bisection midpoint on arc
    - _Requirements: 8.1, 8.2, 8.3, 13.4, 13.5_

  - [x]* 5.5 Write unit tests for geometry/
    - Test build_zones with simple straight profile (OD and ID) using ground truth fixtures (`tests/ground_truth/stepped_od.json`, `tests/ground_truth/stepped_id.json`)
    - Test boundary_at_x returns correct intervals for known geometry
    - Test line_zone_intersection detects crossing
    - Test adaptive_densify_arc produces correct point count for known arcs
    - Test closure segments for OD and ID modes
    - Test arc profile zone construction using `tests/ground_truth/arc_od.json`
    - _Requirements: 1.5, 2.5, 8.1_

  - [x]* 5.6 Write property test for adaptive densification (Property 4)
    - **Property 4: Adaptive Densification Accuracy and Conservatism**
    - For any arc with known center/radius, densified points lie on true arc, chords are inscribed, max deviation < R × 0.0001
    - **Validates: Requirements 8.1, 13.4, 13.8**

  - [x]* 5.7 Write property test for automatic closure (Property 7)
    - **Property 7: Automatic Closure Produces Valid Contour**
    - For any valid profile and stock, closure produces 3 segments creating closed contour with gap ≤ TOLERANCE, no self-intersections, area > 0
    - **Validates: Requirements 24.2, 24.3**


- [x] 6. Implement intervals/ — Fiber and Interval classes
  - [x] 6.1 Implement `intervals/interval.py` — Interval class
    - Implement dataclass with z_start, z_end fields
    - Implement `length` property (z_start - z_end)
    - Implement `contains(other)` — true if other fully inside self within TOLERANCE
    - Implement `overlaps(other)` — true if any overlap within TOLERANCE
    - Implement `merge(other)` — union of two overlapping intervals, raises if no overlap
    - Implement `gap(other)` — distance between non-overlapping intervals
    - _Requirements: 2.1, 2.2_

  - [x] 6.2 Implement `intervals/fiber.py` — Fiber class
    - Implement `__init__(x_dia, zone_query)` — stores x_dia, calls `_query(zone_query)`
    - Implement `_query(zone_query)` — obtains intervals from `ZoneQueryAPI.boundary_at_x()`
    - Implement `add_interval(interval)` — add with automatic merge of overlapping intervals
    - Implement `intervals` property — sorted list of non-overlapping Intervals (z_start descending)
    - Implement `material_at(z)` — point-in-material test
    - Implement `total_material_length` property — sum of all interval lengths
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [x]* 6.3 Write unit tests for intervals/
    - Test Interval contains, overlaps, merge, gap with known values
    - Test Fiber add_interval merges overlapping intervals correctly
    - Test Fiber material_at returns correct results
    - Test tolerance-edge cases (intervals separated by exactly TOLERANCE)
    - _Requirements: 2.1, 2.2, 2.6, 2.7_

  - [x]* 6.4 Write property test for interval merge invariant (Property 3)
    - **Property 3: Interval Merge Invariant**
    - For any sequence of Interval additions, resulting list has no overlapping pairs, is sorted z_start descending, total length equals sum of individual lengths
    - **Validates: Requirements 2.2, 2.6**

- [x] 7. Checkpoint — Ensure geometry/ and intervals/ tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 8. Implement planners/ — Pass planning
  - [x] 8.1 Implement `planners/protocols.py` — RoughingPlanner Protocol
    - Define Protocol class with `plan()` method signature
    - _Requirements: 3.1_

  - [x] 8.2 Implement `planners/staircase_planner.py` — StaircasePlanner
    - Implement `plan(fibers, tool, params, stock, mode)` returning List[TurningPass]
    - Compute X levels from stock boundary toward profile (OD: decreasing, ID: increasing)
    - At each X level, query Fiber for material intervals → each interval becomes one pass
    - Order passes: outermost X first, then by Z (face-to-tail)
    - Compute SweptRegion for each pass
    - Handle peck roughing: insert dwell moves at peck_length intervals
    - _Requirements: 3.1, 3.5, 3.8, 9.1, 9.2_

  - [x] 8.3 Implement `planners/offset_contour_planner.py` — OffsetContourPlanner
    - Implement `plan(zone_query, tool, params, stock, mode)` returning List[TurningPass]
    - Offset roughing boundary outward by DOC increments using `zone_query.offset_boundary()`
    - Clip each offset contour to stock boundary
    - Preserve geometry type (arcs remain arcs, lines remain lines)
    - Compute SweptRegion with inner/outer boundary coordinate arrays
    - Handle peck roughing along contour distance
    - _Requirements: 3.2, 3.3, 3.4, 3.7, 9.3_

  - [x] 8.4 Implement `planners/face_planner.py` — FacePlanner
    - Implement `plan(stock, tool, params, mode, zone_query)` returning List[TurningPass]
    - OD: Feed from stock OD toward centerline at Z=0, stepping Z by DOC
    - ID: Feed from pilot hole toward x_start at Z=0, stepping Z by DOC
    - _Requirements: 3.1_

  - [x] 8.5 Implement `planners/cleanup_planner.py` — CleanupPlanner
    - Implement `plan(zone_query, tool, params, mode)` returning List[TurningPass]
    - Follow roughing boundary contour using boundary_wire_extraction
    - Only used with staircase strategy
    - _Requirements: 3.1_

  - [x] 8.6 Implement `planners/finish_planner.py` — FinishPlanner
    - Implement `plan(zone_query, tool, finishing_params, mode)` returning List[TurningPass]
    - Follow profile boundary exactly using boundary_wire_extraction
    - Support multiple finish passes with DOC stepping
    - _Requirements: 3.1_

  - [x]* 8.7 Write unit tests for planners/
    - Test StaircasePlanner with simple straight profile produces correct pass count and ordering
    - Test FacePlanner produces passes at correct Z levels
    - Test OffsetContourPlanner produces contour-following passes
    - Test peck roughing inserts dwell moves at correct intervals
    - _Requirements: 3.1, 3.2, 3.5, 3.8_

  - [x]* 8.8 Write property test for peck roughing dwell insertion (Property 11)
    - **Property 11: Peck Roughing Dwell Insertion**
    - For any pass with peck_enabled=True, G04 dwells spaced at peck_length intervals, dwell time = 5/RPM*60 seconds
    - **Validates: Requirements 3.8**


- [x] 9. Implement transitions/ — Retract/approach/link logic
  - [x] 9.1 Implement `transitions/transition_planner.py` — TransitionPlanner class
    - Implement `plan_transition(from_pass, to_pass, mode, stock, zone_query, strategy)` returning Transition
    - Implement RETRACT_TRAVERSE_PLUNGE: retract X → traverse Z → approach X → feed step-down
    - Implement PERPENDICULAR_LINK: feed perpendicular from one contour to next (offset-contour only)
    - Implement STEP_OVER: feed step-down for adjacent passes at same Z
    - Implement `_get_safe_x(mode, stock)` — safe retract X parameterized by mode
    - Implement `_verify_transition_safety(transition, zone_query)` — verify moves don't violate zone rules using line_zone_intersection
    - Implement `plan_all(all_passes, mode, stock, zone_query, strategy)` — generate transitions between all consecutive passes
    - Note: ZoneQueryAPI received as parameter (dependency injection), not imported from geometry/
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 11.4_

  - [x]* 9.2 Write unit tests for transitions/
    - Test RETRACT_TRAVERSE_PLUNGE produces correct move sequence
    - Test safe_x computation for OD and ID modes
    - Test PERPENDICULAR_LINK for offset-contour passes
    - Test safety verification catches unsafe transitions
    - _Requirements: 5.1, 5.2, 5.4_

- [x] 10. Implement validation/ — Shapely runtime safety checking
  - [x] 10.1 Implement `validation/polygon_builder.py` — ValidationPolygons class
    - Define ValidationPolygons class with finished_part_poly, finish_allowance_poly, material_to_rough_poly fields
    - Implement `from_zone_set(zone_set, zone_query)` classmethod
    - Extract boundary edges via boundary_wire_extraction
    - For LINE edges: use exact start/end coordinates
    - For ARC edges: use adaptive_densify_arc with cos_limit=0.9999, max_depth=12
    - Construct Shapely Polygon objects from densified coordinate lists
    - Performance target: < 10ms for profiles with up to 20 arc segments
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.9, 13.10, 13.11_

  - [x] 10.2 Implement `validation/pre_planning_validator.py`
    - Implement `validate_profile(profile, stock)` returning List[ValidationResult]
    - Check: arc radius >= chord_length / 2, arc center computable, profile closure gap <= TOLERANCE, no self-intersections, all X > 0, profile starts at Z=0
    - OD: profile X <= stock_dia; ID: profile X >= pilot_hole_dia
    - _Requirements: 6.2_

  - [x] 10.3 Implement `validation/post_planning_validator.py`
    - Implement `validate_all_moves(moves, polygons, mode)` returning List[ValidationResult]
    - Check EVERY move: endpoint not in finished_part_poly, start not in finished_part_poly, rapid segment doesn't intersect finished_part_poly boundary, feed segment doesn't intersect finished_part_poly, at least one point per pass in material_to_rough_poly
    - _Requirements: 6.3, 6.8_

  - [x] 10.4 Implement `validation/pre_output_validator.py`
    - Implement `validate_gcode_geometry(moves)` returning List[ValidationResult]
    - Check: no zero-length moves, arc endpoint distance from center matches radius within CENTER_ARC_RADIUS_TOLERANCE, no consecutive identical positions, feed rate set before first feed move, all coordinates finite
    - _Requirements: 6.5_

  - [x]* 10.5 Write unit tests for validation/
    - Test polygon_builder constructs valid Shapely polygons from known zone boundaries
    - Test pre_planning catches invalid arcs, unclosed profiles
    - Test post_planning catches moves inside finished_part_poly
    - Test pre_output catches zero-length moves and invalid arcs
    - _Requirements: 6.2, 6.3, 6.5, 13.1_

  - [x]* 10.6 Write property test for no gouge (Property 1)
    - **Property 1: No Gouge (Hard Rule 2)**
    - For any valid inputs producing successful execution, no ToolMove endpoint or segment intersects finished_part_poly
    - **Validates: Requirements 3.6, 5.4, 6.3, 11.5**

  - [x]* 10.7 Write property test for complete material removal (Property 2)
    - **Property 2: Complete Material Removal (Hard Rule 1)**
    - For any valid inputs producing successful execution, area of material_to_rough minus union of swept regions < TOLERANCE_SQ
    - **Validates: Requirements 3.6, 9.6**

- [x] 11. Checkpoint — Ensure planners/, transitions/, validation/ tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 12. Implement outputs/ — G-code writer, graph adapter, exporters
  - [x] 12.1 Implement `outputs/gcode_writer.py` — GCodeWriter class
    - Implement position-tracking writer with current X, Z, feed state
    - Implement axis word suppression (don't emit unchanged values)
    - Implement feed word suppression (don't emit unchanged feed rate)
    - Implement zero-motion detection and rejection (raises on planning bug)
    - Implement arc validation before emitting (start/end distance from center within tolerance)
    - Support both R-format and IJK-format arc output (configurable)
    - Implement `write(plan_result)` — generate complete G-code with section comments
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 12.2 Implement `outputs/gcode_parser.py` — parse function
    - Implement `parse(gcode_text)` returning List[ToolMove]
    - Handle G00, G01, G02, G03 (modal), X/Z axis words (absolute, diameter), I/K (incremental) and R formats, F (modal feed)
    - LinuxCNC interpretation: G90 absolute, I/K incremental from start
    - _Requirements: 7.6_

  - [x] 12.3 Implement `outputs/graph_adapter.py` — GraphData conversion
    - Define dataclasses: ZoneShading, ToolpathSegment, PlaybackFrame, GraphData
    - Implement `convert(plan_result)` — convert PlanResult to PyQtGraph-ready coordinate arrays
    - Convert X from DIAMETER to RADIUS, densify arcs, group moves by type, construct playback frames, extract zone boundaries
    - Implement `convert_from_moves(moves)` — convert raw move list for Edit tab preview
    - NOTE: No PyQtGraph or Qt imports — produces plain arrays only
    - _Requirements: 1.10, 10.4_

  - [x] 12.4 Implement `outputs/dxf_exporter.py` — DXF export
    - Implement `export(plan_result, path)` — write DXF with true arc entities using ezdxf
    - Separate layers for profile, toolpath, zones
    - _Requirements: 1.1_

  - [x] 12.5 Implement `outputs/svg_exporter.py` — SVG export
    - Implement `export(plan_result, path)` — write SVG with zone fills and toolpath
    - _Requirements: 1.1_

  - [x] 12.6 Implement `outputs/sim_adapter.py` — Simulation adapter
    - Implement `export(plan_result)` — produce SimMove list for playback
    - _Requirements: 10.4_

  - [x]* 12.7 Write unit tests for outputs/
    - Test GCodeWriter produces correct G-code for known move sequences
    - Test axis word suppression works correctly
    - Test zero-motion detection raises
    - Test arc validation catches invalid arcs
    - Test gcode_parser round-trips simple programs
    - Test graph_adapter produces correct coordinate arrays
    - _Requirements: 7.1, 7.4, 7.5_

  - [x]* 12.8 Write property test for G-code round-trip fidelity (Property 5)
    - **Property 5: G-Code Round-Trip Fidelity**
    - For any valid PlanResult, write → parse produces moves matching original within TOLERANCE
    - **Validates: Requirements 17.4, 17.10**

  - [x]* 12.9 Write property test for position-tracking writer correctness (Property 6)
    - **Property 6: Position-Tracking Writer Correctness**
    - For any move sequence, writer never emits unchanged axis/feed words, rejects zero-motion moves
    - **Validates: Requirements 7.1, 7.4**


- [x] 13. Implement pipeline/ — Orchestration (file_io and model_builder first, then pipeline)
  - [x] 13.1 Implement `pipeline/file_io.py` — File I/O operations
    - Implement `save_conversational(data, path)` — save as JSON with indent=2, update modified timestamp
    - Implement `load_conversational(path)` — load JSON, validate version field
    - Implement `save_tool_table(tools, path)` — save in LinuxCNC .tbl format
    - Implement `load_tool_table(path)` — parse .tbl format into List[ToolDef]
    - Implement `create_backup(source_path, backup_dir, max_backups)` — timestamped backup with pruning
    - Implement `save_gcode(gcode_text, path)` — save to .ngc file
    - _Requirements: 10.8_

  - [x] 13.2 Implement `pipeline/model_builder.py` — UI field to dataclass conversion
    - Implement `build_from_fields(...)` — convert raw UI field values into typed dataclasses (ClosedProfile, StockDef, RoughingParams, FinishingParams)
    - String → Enum conversion, field completeness checking, segment dict → ProfileMove conversion
    - No Qt imports — testable without display
    - _Requirements: 6.1_

  - [x] 13.3 Implement `pipeline/pipeline.py` — Main execution orchestrator
    - Implement `execute(profile, stock, tool, roughing_params, finishing_params, verify_roundtrip)` returning PipelineResult
    - Wire all modules in order: pre-planning validation → build_zones → build_polygons → plan_face → plan_turning → plan_cleanup → plan_finish → plan_transitions → assemble moves → post-planning validation → pre-output validation → construct PlanResult
    - Extract zone boundary coordinates for PlanResult (finished_part_boundary, finish_allowance_boundary, etc.)
    - Handle ERROR/WARNING status correctly
    - Optional round-trip verification
    - _Requirements: 1.3, 6.1, 6.7, 10.6, 10.7_

  - [x]* 13.4 Write unit tests for pipeline/
    - Test model_builder converts valid field dicts to correct dataclasses
    - Test model_builder raises ValueError on missing required fields
    - Test file_io round-trips conversational JSON
    - Test file_io round-trips tool table
    - Test pipeline.execute with simple straight OD profile produces valid PlanResult
    - _Requirements: 6.1, 10.8_

  - [x]* 13.5 Write property test for conversational file round-trip (Property 10)
    - **Property 10: Conversational File Round-Trip**
    - For any valid Program Tab state, serialize → deserialize produces identical field values
    - **Validates: Requirements 30.5**

  - [x]* 13.6 Write property test for tool table mapping (Property 12)
    - **Property 12: Tool Table to ToolDef Mapping**
    - For any valid tool table entry, resulting ToolDef has matching nose_radius, tip_angle, edge_length, orientation, direction
    - **Validates: Requirements 27.17**

  - [x]* 13.7 Write property test for OD/ID mode symmetry (Property 13)
    - **Property 13: OD/ID Mode Symmetry**
    - For any profile expressible in both modes, pipeline produces valid toolpath for both using same code path
    - **Validates: Requirements 11.1, 11.5**

- [x] 14. Checkpoint — Ensure outputs/ and pipeline/ tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 15. Implement gui/components/ — Reusable Qt widgets (no engine logic)
  - [x] 15.1 Implement `gui/colors.py` — Color system and stylesheet
    - Define COLORS dict with semantic color assignments per gui-color-system.md
    - Define STYLESHEET string for global application styling
    - Define font constants (Inter for UI, JetBrains Mono for DRO/code)
    - _Requirements: 1.9_

  - [x] 15.2 Implement `gui/components/graph_widget.py` — MachiningGraphWidget
    - Subclass pg.PlotWidget with 1:1 aspect ratio, crosshair with coordinate readout
    - Implement `set_graph_data(data: GraphData)` — load zone shadings, toolpath segments, profile line, stock rect
    - Implement `set_preview_mode(segments, stock)` — real-time profile preview (Qt geometry only, no kernel)
    - Implement `highlight_pass(pass_index)` — highlight specific pass swept region
    - Implement `set_tool_position(x_radius, z)` — update animated tool dot
    - Define signals: coordinate_changed, move_selected
    - Implement PrecisionAxisItem for adaptive tick precision
    - Implement touch support (pinch-to-zoom, two-finger pan)
    - _Requirements: 10.4, 8.4_

  - [x] 15.3 Implement `gui/components/playback_controller.py` — PlaybackController
    - QTimer-based frame stepper for toolpath animation
    - Implement load_frames, play, pause, step_forward, step_backward, set_speed
    - Define signals: frame_changed (index, x_r, z, pass_type, n_number), playback_finished
    - Configurable speed: 0.5x to 5x, base interval 50ms (20fps at 1x)
    - _Requirements: 10.4_

  - [x] 15.4 Implement `gui/components/numeric_field.py` — Validated numeric input widget
    - QLineEdit subclass with float validation, range checking, unit suffix display
    - Emit value_changed signal on valid input
    - Visual error state (red border) on invalid input
    - _Requirements: 1.9_

  - [x] 15.5 Implement `gui/components/segment_list.py` — Profile segment list widget
    - QTableWidget-based segment editor (type, X, Z, radius columns)
    - Add/Remove/Move Up/Move Down buttons
    - Inline validation (arc radius >= chord/2)
    - Emit segments_changed signal on any edit
    - _Requirements: 1.9_

  - [x] 15.6 Implement `gui/components/status_bar.py` — Status bar widget
    - Machine state indicators, live DRO (X dia, Z inches), active G-codes, spindle RPM
    - Offline mode: show "OFFLINE" indicator with demo values
    - _Requirements: 10.8_

  - [x]* 15.7 Write unit tests for gui/components/
    - Test numeric_field validation accepts/rejects correct values
    - Test segment_list emits correct signals on edit
    - Test playback_controller frame advancement logic
    - _Requirements: 1.9_


- [x] 16. Implement gui/ tabs — Program, Edit, Tools, Debug
  - [x] 16.1 Implement `gui/program_tab.py` — ProgramTab (state machine and layout)
    - QSplitter layout: left panel (input fields) + right panel (MachiningGraphWidget + playback controls)
    - Implement state machine: IDLE → BUILDING → READY → GENERATING → DISPLAYING ↔ PLAYING
    - Stock fields (diameter, z_start, z_end, pilot_hole_dia, mode selector)
    - Cutting params (DOC, feed, strategy selector, fin_allowance, peck toggle + length, RPM)
    - Finishing params (passes, DOC, feed)
    - Segment list widget (from gui/components/)
    - Block type selector (OD Profile, ID Profile; Threading/Grooving disabled for P2)
    - _Requirements: 10.4, 10.8_

  - [x] 16.2 Implement `gui/program_tab.py` — Generation and playback wiring
    - Implement `_on_generate_clicked()` — call model_builder.build_from_fields → pipeline.execute → graph_adapter.convert → display
    - Implement `_on_field_changed()` — DISPLAYING → BUILDING, clear toolpath, update preview
    - Implement `_update_preview()` — real-time profile preview (< 16ms, pure Qt geometry)
    - Implement `_validate_inline()` — show/clear validation errors as user types
    - Wire playback controller to graph widget (play/pause/step/speed controls)
    - Emit signals: gcode_generated, plan_result_ready, tool_requested
    - _Requirements: 10.4, 6.6_

  - [x] 16.3 Implement `gui/edit_tab.py` — EditTab
    - G-code text editor with JetBrains Mono font, syntax highlighting (G/M codes, axis words, comments)
    - Find/Replace (Ctrl+F), line numbers, current line highlight
    - File operations: Open, Save, Save As, Clear, Reload
    - Preview button: parse G-code → emit preview_requested signal with List[ToolMove]
    - Implement `receive_gcode(gcode_text)` — populate editor from Program Tab
    - Undo/Redo support, handle up to 10,000 lines without lag
    - _Requirements: 10.4_

  - [x] 16.4 Implement `gui/tools_tab.py` — ToolsTab
    - Tool list/grid with editable fields (tool_number, nose_radius, tip_angle, edge_length, orientation, direction, offsets, wear)
    - Insert shape dropdown with auto-populate (CNMG, VNMG, CCMT, etc.)
    - Real-time tool graphic preview (QPainterPath — NOT engine ToolShape)
    - Auto-save on every change + explicit Save/Save As
    - Session backup on launch (max 5) via pipeline/file_io
    - LinuxCNC tool.tbl format compatibility
    - Emit tool_changed signal on edit
    - _Requirements: 4.1, 4.6_

  - [x] 16.5 Implement `gui/debug_tab.py` — DebugTab
    - Sub-panels via horizontal tab bar: Fibers, Swept, Heatmap, Diagnostic, Round-Trip, Export
    - Implement `update_panels(plan_result)` — store PlanResult, invalidate panels, render current
    - Lazy rendering: compute panel content only when selected
    - Fibers panel: interval chart visualization
    - Swept panel: cumulative swept region display
    - Diagnostic panel: structured text dump of PlanResult
    - Round-Trip panel: G-code fidelity comparison overlay
    - Export panel: DXF, SVG, PNG, G-code→DXF buttons
    - _Requirements: 10.4_

  - [x] 16.6 Implement `gui/main_window.py` — MainWindow and signal wiring
    - QMainWindow with status bar (top), tab bar, tab content area
    - Tabs: Program (P1), Edit (P1), Tools (P1), Debug (P1), Run (P2 placeholder), Manual (P2 placeholder), Setup (P3 placeholder), Help (P3 placeholder)
    - Signal wiring: program_tab.gcode_generated → edit_tab.receive_gcode, program_tab.plan_result_ready → debug_tab.update_panels, tools_tab.tool_changed → program_tab.on_tool_changed, edit_tab.preview_requested → program_tab.show_parsed_preview
    - Offline preview mode (HAS_LINUXCNC = False)
    - Application entry point with QApplication setup
    - _Requirements: 1.9, 10.8_

  - [x]* 16.7 Write integration tests for GUI signal flow
    - Test Program Tab generate → Edit Tab receives G-code
    - Test Program Tab generate → Debug Tab receives PlanResult
    - Test Tools Tab change → Program Tab marks stale
    - Test Edit Tab preview → Program Tab shows parsed overlay
    - _Requirements: 10.4_

- [x] 17. Checkpoint — Ensure GUI components and tabs work end-to-end
  - Ensure all tests pass, ask the user if questions arise.


- [x] 18. Implement architecture integrity enforcement
  - [x] 18.1 Implement `validation/architecture_check.py` — Static analysis
    - Implement dependency violation detection (AST-based import analysis)
    - Implement dead code detection (functions/classes with zero callers, unused imports)
    - Implement fallback pattern detection (try/except with alternative implementation)
    - Implement dual implementation detection (two functions computing same geometric quantity)
    - Implement hand math detection (manual arc center, circle intersection, offset formulas)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x]* 18.2 Write property test for module dependency integrity (Property 8)
    - **Property 8: Module Dependency Integrity**
    - For any source file, all imports reference only modules LEFT in the dependency chain; models/ imports no external packages
    - **Validates: Requirements 1.2, 1.4**

  - [x]* 18.3 Write integration test for full pipeline (OD and ID)
    - Test pipeline.execute with hump test profile (OD) produces valid PlanResult with all passes
    - Test pipeline.execute with simple bore profile (ID) produces valid PlanResult
    - Verify Shapely validation passes for both
    - Verify G-code round-trip fidelity
    - _Requirements: 10.1, 10.2, 10.3, 11.1_

- [x] 19. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at natural module boundaries
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The dependency chain order (models → tools → geometry → intervals → planners → transitions → validation → outputs → pipeline → gui) is strictly followed
- `pipeline/file_io.py` and `pipeline/model_builder.py` have no Qt dependency and are implemented before gui/ tasks
- `outputs/graph_adapter.py` produces plain arrays — no PyQtGraph imports
- The gui/ module is the ONLY one that imports PyQt5/PyQtGraph
- **Corner Breaks (Requirement 32, P1.5):** The `CornerBreak` dataclass and `corner_breaks` field on `ClosedProfile` are included in the models/ task (Task 2.1). The UI fields are present but disabled in the Program Tab (Task 16.1). The actual geometry computation (Build123d fillet/chamfer on the profile wire) is a separate P1.5 task to be added AFTER the basic pipeline is verified working. Do NOT implement corner break geometry during P1 — only the data model and disabled UI placeholder.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8"] },
    { "id": 2, "tasks": ["2.9", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4"] },
    { "id": 4, "tasks": ["5.1", "5.4"] },
    { "id": 5, "tasks": ["5.2"] },
    { "id": 6, "tasks": ["5.3", "5.5", "5.6", "5.7"] },
    { "id": 7, "tasks": ["6.1"] },
    { "id": 8, "tasks": ["6.2", "6.3", "6.4"] },
    { "id": 9, "tasks": ["8.1", "8.4"] },
    { "id": 10, "tasks": ["8.2", "8.3", "8.5", "8.6"] },
    { "id": 11, "tasks": ["8.7", "8.8", "9.1"] },
    { "id": 12, "tasks": ["9.2", "10.1", "10.2"] },
    { "id": 13, "tasks": ["10.3", "10.4", "10.5", "10.6", "10.7"] },
    { "id": 14, "tasks": ["12.1", "12.2", "12.3", "12.4", "12.5", "12.6"] },
    { "id": 15, "tasks": ["12.7", "12.8", "12.9"] },
    { "id": 16, "tasks": ["13.1", "13.2"] },
    { "id": 17, "tasks": ["13.3"] },
    { "id": 18, "tasks": ["13.4", "13.5", "13.6", "13.7"] },
    { "id": 19, "tasks": ["15.1", "15.4", "15.5", "15.6"] },
    { "id": 20, "tasks": ["15.2", "15.3"] },
    { "id": 21, "tasks": ["15.7", "16.1"] },
    { "id": 22, "tasks": ["16.2", "16.3", "16.4", "16.5"] },
    { "id": 23, "tasks": ["16.6"] },
    { "id": 24, "tasks": ["16.7", "18.1"] },
    { "id": 25, "tasks": ["18.2", "18.3"] }
  ]
}
```
