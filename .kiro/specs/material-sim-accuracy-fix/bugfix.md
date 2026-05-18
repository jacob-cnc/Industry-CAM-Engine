# Bugfix Requirements Document

## Introduction

The material removal simulation in the playback viewer does not track the tool position accurately during animated playback. Material snaps between discrete pass states instead of progressively removing as the tool moves, face passes remove material in incorrect Z-slices instead of tracking X movement, arc passes show full removal instantly, and the move index mapping between the G-code SimMove path and PlanResult.tool_moves is misaligned. These issues make the simulation visually misleading — the material polygon does not correspond to where the tool actually is during playback.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN playback progress is between 0 and 1 within a pass (intermediate cutting move) THEN the system displays the previous pass's material state unchanged, ignoring the pre-computed `move_states` dictionary that contains per-move polygon data

1.2 WHEN a face pass is in progress (tool moving primarily in X) THEN the system clips the partial swept region using only Z bounds spanning the full X range, causing material to vanish in Z-slices rather than tracking the tool's X position

1.3 WHEN an arc pass is in progress THEN the system uses `partial_swept = full_swept` for all cutting moves, removing the entire arc band at the first cutting move instead of progressively along the arc path

1.4 WHEN `_update_material_state()` maps the current SimMove index to a toolpath segment THEN the system indexes into `graph_data.toolpath_segments[move_idx]` using the interpolated playback path index (G-code SimMove index) which may not align with `PlanResult.tool_moves` indices that the segment list and pass move ranges are built from

### Expected Behavior (Correct)

2.1 WHEN playback progress is between 0 and 1 within a pass (intermediate cutting move) THEN the system SHALL render the pre-computed `move_states[move_index]` polygon data directly, showing material progressively removed as each cutting move completes

2.2 WHEN a face pass is in progress (tool moving primarily in X) THEN the system SHALL compute the partial swept region as a toolpath-traced rectangle/parallelogram offset ±TNR perpendicular to the move direction, tracking the tool's actual X position rather than spanning the full X range

2.3 WHEN an arc pass is in progress THEN the system SHALL compute a cumulative swept region that grows incrementally with each arc cutting move, using a TNR-offset band for just the arc segment traversed so far

2.4 WHEN `_update_material_state()` maps the current playback position to material state THEN the system SHALL use the pre-computed `move_states` dictionary keyed by the correct tool_moves index, with a verified mapping between SimMove indices and PlanResult.tool_moves indices

### Unchanged Behavior (Regression Prevention)

3.1 WHEN playback reaches the end of a complete pass THEN the system SHALL CONTINUE TO display the same final pass state polygon as currently computed by the sequential stock.difference(swept_region) logic

3.2 WHEN the simulation is at frame 0 (start) THEN the system SHALL CONTINUE TO display the full stock polygon unchanged

3.3 WHEN playback encounters a rapid move (G00) THEN the system SHALL CONTINUE TO skip material state updates (no material is removed during rapids)

3.4 WHEN the material simulation is computed for profiles with up to 30 passes THEN the system SHALL CONTINUE TO complete computation within the 200ms performance budget

3.5 WHEN all passes are complete (final state) THEN the system SHALL CONTINUE TO display the canonical final state computed as stock minus union of all swept regions

3.6 WHEN the simulation operates in ID mode versus OD mode THEN the system SHALL CONTINUE TO use the correct coordinate conventions (radius for X, inches for Z) and mode-aware stock polygon construction
