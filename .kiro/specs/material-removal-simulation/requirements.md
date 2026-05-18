# Requirements Document

## Introduction

Replace the current static zone shading in the SimViewerWidget with a dynamic material removal visualization. As the simulation plays back toolpath motion, the filled stock region progressively shrinks to reveal what material has been cut — geometrically matching the post-planning validator's Shapely polygons. This provides the operator with an accurate, real-time visual of the machining process that is guaranteed to agree with the validator's geometric truth.

## Glossary

- **Simulation_Engine**: The subsystem responsible for computing and managing material removal polygon states during playback
- **Graph_Widget**: The MachiningGraphWidget (PyQtGraph PlotWidget) that renders zones, toolpath, and material state
- **SweptRegion**: The Shapely Polygon representing the exact material envelope removed by a single TurningPass
- **Stock_Polygon**: The initial Shapely Polygon representing the full stock material (rectangle from X_start to Stock_OD, Z_start to Z_end)
- **Remaining_Material**: The Shapely Polygon representing stock minus all swept regions applied so far
- **Pipeline**: The pipeline orchestrator (pipeline.py) that generates PlanResult after toolpath planning
- **Validator**: The post-planning validator that checks every move against Shapely zone polygons
- **TNR**: Tool Nose Radius — defines the width of the swept band for arc passes
- **Pass_State**: A pre-computed snapshot of the Remaining_Material polygon after a specific pass has been applied
- **Graph_Adapter**: The module (graph_adapter.py) that converts PlanResult into display-ready coordinate arrays

## Requirements

### Requirement 1: SweptRegion Polygon Computation

**User Story:** As a CAM developer, I want each TurningPass to carry an accurate Shapely polygon representing its swept material envelope, so that the material removal visualization matches the validator's geometric truth.

#### Acceptance Criteria

1. WHEN a face pass or roughing pass is planned, THE Simulation_Engine SHALL compute the SweptRegion as a rectangular Shapely Polygon bounded by the pass X_min, X_max, Z_start, and Z_end
2. WHEN a cleanup pass or finish pass contains arc moves, THE Simulation_Engine SHALL compute the SweptRegion as the actual curved band traced by the tool nose radius along the arc path
3. THE Simulation_Engine SHALL construct arc swept bands by offsetting the toolpath arc inward and outward by the TNR value and closing the resulting boundary into a Shapely Polygon
4. FOR ALL TurningPass objects, THE SweptRegion Shapely Polygon SHALL use RADIUS coordinates for X and INCHES for Z, matching the Validator coordinate convention
5. IF a SweptRegion polygon is invalid or degenerate, THEN THE Simulation_Engine SHALL apply Shapely make_valid and log a warning without blocking the pipeline

### Requirement 2: Pre-Computed Material State Sequence

**User Story:** As a simulation user, I want material removal states pre-computed after the pipeline completes, so that playback is smooth with no per-frame geometry operations.

#### Acceptance Criteria

1. WHEN the Pipeline produces a PlanResult, THE Simulation_Engine SHALL compute an ordered sequence of Pass_State polygons by successively subtracting each SweptRegion from the Stock_Polygon
2. THE Simulation_Engine SHALL store one Pass_State per TurningPass, representing the Remaining_Material after that pass completes
3. THE Simulation_Engine SHALL additionally pre-compute per-move SweptRegion polygons for each cutting move within a pass, enabling the Graph_Widget to interpolate material removal in sync with tool motion
4. THE Simulation_Engine SHALL complete all polygon subtraction operations within 200ms for profiles with up to 30 passes; profiles with more than 30 passes SHALL be allowed without the time guarantee
5. THE Simulation_Engine SHALL convert each Pass_State polygon exterior coordinates into numpy arrays suitable for direct rendering by the Graph_Widget
6. IF a polygon subtraction produces a MultiPolygon result, THEN THE Simulation_Engine SHALL retain all component polygons for accurate rendering of disconnected material regions

### Requirement 3: Stock Polygon Initialization

**User Story:** As a simulation user, I want to see the full stock material displayed as a solid filled region at the start of playback, so that I have a clear reference for what will be removed.

#### Acceptance Criteria

1. WHEN playback begins or is reset, THE Graph_Widget SHALL display the Stock_Polygon as a solid filled region, ensuring the polygon is rendered regardless of its dimensional parameters
2. WHILE the machining mode is OD, THE Simulation_Engine SHALL construct the Stock_Polygon with X ranging from x_start/2 (radius) to stock_diameter/2 (radius)
3. WHILE the machining mode is ID, THE Simulation_Engine SHALL construct the Stock_Polygon with X ranging from pilot_hole_diameter/2 (radius) to x_start/2 (radius)
4. THE Graph_Widget SHALL render the Stock_Polygon using vector graphics (PyQtGraph polygon fill) that remain sharp at all zoom levels

### Requirement 4: Progressive Material Removal During Playback

**User Story:** As a simulation user, I want to see material visually removed in sync with the tool dot's motion during playback, so that I can observe material disappearing exactly where the tool is cutting.

#### Acceptance Criteria

1. WHEN the playback tool dot advances through a cutting move, THE Graph_Widget SHALL remove material in sync with the tool position by clipping the Remaining_Material polygon up to the tool dot's current location along the pass
2. THE Graph_Widget SHALL compute the partial swept region from the pass start to the current tool position and subtract it from the displayed Remaining_Material each frame
3. THE Graph_Widget SHALL render the Remaining_Material polygon as a filled region that progressively shrinks in real-time as the tool dot moves through cutting moves
4. WHILE the tool dot is traversing a rapid move, THE Graph_Widget SHALL NOT remove any material (only cutting moves remove material)
5. THE Graph_Widget SHALL render material removal using vector-based polygon fills that remain accurate at all zoom levels

### Requirement 5: Show All Final State

**User Story:** As a simulation user, I want the "Show All" button to immediately display the final material state (stock minus all passes), so that I can see the finished result without waiting for full playback.

#### Acceptance Criteria

1. WHEN the user activates "Show All", THE Graph_Widget SHALL display the final Pass_State representing stock minus all swept regions
2. THE Graph_Widget SHALL display the final state within one frame (16ms) by loading the last pre-computed Pass_State coordinate arrays
3. THE Remaining_Material displayed after "Show All" SHALL visually represent the material surrounding the finished part profile

### Requirement 6: Reset to Full Stock

**User Story:** As a simulation user, I want the "Reset" button to restore the full stock rectangle, so that I can replay the simulation from the beginning.

#### Acceptance Criteria

1. WHEN the user activates "Reset", THE Graph_Widget SHALL restore the display to the initial Stock_Polygon (full material, no passes applied); IF restoration cannot be guaranteed due to memory constraints or corrupted initial state data, THEN THE Graph_Widget SHALL prevent reset activation
2. THE Graph_Widget SHALL clear all progressive toolpath reveals and return the tool dot to the home position when reset is activated

### Requirement 7: Geometric Accuracy Agreement with Validator

**User Story:** As a CAM developer, I want the material removal visualization to exactly match the validator's geometric model, so that the simulation never shows material removed where the validator would disagree.

#### Acceptance Criteria

1. THE Simulation_Engine SHALL construct SweptRegion polygons using the same adaptive arc densification parameters (SHAPELY_COS_LIMIT, MAX_DENSIFICATION_DEPTH) as the Validator
2. THE Simulation_Engine SHALL use the same coordinate convention (RADIUS for X, INCHES for Z) as the Validator polygon_builder
3. FOR ALL passes where the Validator confirms no gouge, THE SweptRegion polygon SHALL NOT extend into the finished_part_poly boundary beyond TOLERANCE (0.0005 inches)
4. THE Simulation_Engine SHALL construct arc swept bands from the same I/K center offsets and TNR values used by the toolpath planner, ensuring geometric identity with the planned path

### Requirement 8: Compatibility with Existing Simulation Features

**User Story:** As a simulation user, I want material removal visualization to work alongside the existing toolpath line reveal, G-code sync, and playback controls without breaking them.

#### Acceptance Criteria

1. THE Graph_Widget SHALL continue to progressively reveal toolpath lines during playback alongside the material removal visualization
2. THE Graph_Widget SHALL continue to emit sim_line_changed signals for G-code panel highlighting during material removal playback
3. THE Graph_Widget SHALL always support Play, Pause, Step Forward, Step Back, speed control, and slider scrubbing regardless of whether material removal is active, with material state updating accordingly when material removal visualization is enabled
4. WHEN the user scrubs the slider to an arbitrary position, THE Graph_Widget SHALL display the Pass_State corresponding to the last completed pass at or before that position
5. THE Graph_Widget SHALL continue to support the "Hide Rapids" toggle independently of material removal display

### Requirement 9: OD and ID Profile Support

**User Story:** As a simulation user, I want material removal visualization to work correctly for both OD turning and ID boring operations.

#### Acceptance Criteria

1. WHILE the machining mode is OD, THE Simulation_Engine SHALL subtract swept regions from the outer stock boundary inward toward the finished part
2. WHILE the machining mode is ID, THE Simulation_Engine SHALL subtract swept regions from the inner bore boundary outward toward the finished part
3. THE Graph_Widget SHALL render the Remaining_Material polygon correctly for both OD profiles (material above the profile) and ID profiles (material below the profile in the bore), and SHALL render both simultaneously when both profile types are present

### Requirement 10: Material Removal Polygon Serialization for Graph Adapter

**User Story:** As a CAM developer, I want the pre-computed material states to flow through the existing graph_adapter pattern, so that the GUI layer receives plain coordinate arrays with no Shapely dependency.

#### Acceptance Criteria

1. THE Graph_Adapter SHALL convert each Pass_State Shapely Polygon into coordinate arrays (x_coords in radius, z_coords in inches) before passing data to the Graph_Widget
2. THE Graph_Adapter SHALL include the Stock_Polygon coordinate arrays and the ordered sequence of Pass_State coordinate arrays in the GraphData structure
3. THE Graph_Widget SHALL NOT import or depend on Shapely directly — all polygon data SHALL arrive as pre-computed coordinate arrays
