# Requirements Document

## Introduction

Rebuild of the Tools tab in the Industry CAM Engine PyQt5 GUI as a Mazak-style tool geometry editor with integrated wear offsets. The tab manages the full tool library using a scrollable list of tool cards (one per tool), with smart auto-population of geometry fields based on insert type selection, and real-time orientation graphics. The design replaces the current split-panel list+editor layout with a card-based vertical scroll layout where all fields are visible per tool.

## Glossary

- **Tools_Tab**: The PyQt5 QWidget implementing the rebuilt tool geometry editor tab.
- **Tool_Card**: A compact grid widget (ToolGeometryRow) representing one tool's complete editable state within the scrollable list.
- **Insert_Geometry_Lookup**: A dictionary mapping insert code names to their front angle and back angle values (e.g., CNMG → front 95°, back 175°).
- **Wear_Offset**: A local GUI-managed X or Z offset that is combined with the geometry offset before being written to LinuxCNC via G10 L1 MDI commands.
- **Geometry_Offset**: The base X and Z tool offsets stored in the LinuxCNC tool table.
- **Orientation**: LinuxCNC cutter compensation orientation code Q1–Q9, indicating the position of the tool tip relative to the tool body.
- **Touch_Off**: The process of setting a tool offset by commanding G10 L1 with measured X or Z values.
- **Tool_Type**: A category (Turning RH, Turning LH, Boring Bar, Threading External, Threading Internal, Grooving/Parting, Knurling, Custom) that determines valid orientations and insert codes.
- **Insert_Code**: An ISO insert designation (e.g., CNMG, CCMT, VNMG) that identifies the insert shape and determines front/back cutting edge angles.
- **Front_Angle**: The front cutting edge angle in degrees measured clockwise from Z+ axis.
- **Back_Angle**: The back cutting edge angle in degrees measured clockwise from Z+ axis.
- **Orientation_Graphic**: A 160×160 pixel live widget showing insert shape, cutting edges, nose radius circle, and control point crosshair.
- **Autosave**: Automatic persistence of tool data to the active .tbl file on every field change.
- **Filter_Cascade**: The behavior where changing Tool_Type filters both the Orientation dropdown and the Insert_Code dropdown to show only valid options.

## Requirements

### Requirement 1: Tool Card Layout

**User Story:** As a CNC operator, I want each tool displayed as a self-contained card with all fields visible, so that I can quickly scan and edit tool geometry without navigating between panels.

#### Acceptance Criteria

1. THE Tools_Tab SHALL display tools as a vertically scrollable list of Tool_Card widgets, one per tool.
2. WHEN a Tool_Card is displayed, THE Tool_Card SHALL show Wear X, Wear Z, X Offset, Z Offset, Type, Insert Code, Orientation, Description, Nose Radius, Front Angle, Back Angle, and a delete button in a compact grid layout.
3. THE Tool_Card SHALL display Wear X and Wear Z values in large orange font to distinguish them from geometry offsets.
4. WHEN Wear X or Wear Z has a non-zero value, THE Tool_Card SHALL visually highlight that field.
5. THE Tool_Card SHALL display X Offset values in diameter units in the UI while storing them as radius internally.
6. WHEN the tool type is Grooving/Parting, THE Tool_Card SHALL display a Blade Width field; otherwise THE Tool_Card SHALL hide the Blade Width field.

### Requirement 2: Orientation Graphic Widget

**User Story:** As a CNC operator, I want a live graphical preview of the tool insert shape and orientation, so that I can visually confirm the tool setup matches the physical tool.

#### Acceptance Criteria

1. THE Tool_Card SHALL include an Orientation_Graphic widget of 160×160 pixels.
2. WHEN any geometry parameter changes (insert code, orientation, nose radius, front angle, or back angle), THE Orientation_Graphic SHALL update in real-time to reflect the current tool configuration.
3. THE Orientation_Graphic SHALL render the insert shape outline, cutting edge indicators, a nose radius circle, and a control point crosshair.

### Requirement 3: Insert Geometry Auto-Fill

**User Story:** As a CNC operator, I want front and back angles to auto-populate when I select an insert code, so that I do not need to manually look up and enter standard insert geometry.

#### Acceptance Criteria

1. THE Tools_Tab SHALL maintain an Insert_Geometry_Lookup dictionary mapping each insert code to its front angle and back angle values.
2. WHEN the user selects an insert code from the Insert Code dropdown, THE Tool_Card SHALL auto-populate the Front Angle and Back Angle fields from the Insert_Geometry_Lookup.
3. THE Insert_Geometry_Lookup SHALL contain entries for turning inserts (CNMG, CCMT, WNMG, DNMG, DCMT, VNMG, TNMG, SNMG, RCMT), threading inserts (60° UN/Metric, 55° Whitworth, ACME), and grooving inserts (Grooving).
4. WHEN the user manually edits Front Angle or Back Angle after auto-fill, THE Tool_Card SHALL retain the user-entered values without reverting to lookup values.

### Requirement 4: Type-Driven Filter Cascade

**User Story:** As a CNC operator, I want the orientation and insert code dropdowns to show only valid options for my selected tool type, so that I cannot accidentally configure an invalid combination.

#### Acceptance Criteria

1. WHEN the user changes the Tool Type dropdown, THE Tool_Card SHALL filter the Orientation dropdown to show only orientations valid for that tool type.
2. WHEN the user changes the Tool Type dropdown, THE Tool_Card SHALL filter the Insert Code dropdown to show only insert codes valid for that tool type.
3. WHEN the filtered options no longer include the currently selected orientation, THE Tool_Card SHALL reset the orientation to the first valid option for the new type.
4. WHEN the filtered options no longer include the currently selected insert code, THE Tool_Card SHALL reset the insert code to the first valid option and trigger auto-fill of front and back angles.
5. THE Filter_Cascade SHALL define the following type-to-insert mappings: Turning RH and Turning LH map to CNMG, CCMT, WNMG, DNMG, DCMT, VNMG, TNMG, SNMG, RCMT; Threading External and Threading Internal map to 60° UN/Metric, 55° Whitworth, ACME; Grooving/Parting maps to Grooving; Boring Bar maps to CCMT, DCMT, VNMG, RCMT.

### Requirement 5: Top Button Bar

**User Story:** As a CNC operator, I want a toolbar with file operations, tool addition, and touch-off controls, so that I can manage the tool table and set offsets without leaving the tab.

#### Acceptance Criteria

1. THE Tools_Tab SHALL display a top button bar containing Load Table, Save Table As, Add Tool, a table name label, a current tool display, and a touch-off section.
2. WHEN the user clicks Load Table, THE Tools_Tab SHALL open a file dialog filtered to .tbl files and load the selected tool table.
3. WHEN the user clicks Save Table As, THE Tools_Tab SHALL create a .bak backup of the existing file before saving the current tool data to the user-specified path.
4. WHEN the user clicks Add Tool, THE Tools_Tab SHALL append a new blank tool card to the end of the scrollable list.
5. THE Tools_Tab SHALL display the filename of the currently loaded table in the table name label.
6. WHEN LinuxCNC stat channel is available, THE Tools_Tab SHALL display the active tool number and description in the current tool display area.
7. THE touch-off section SHALL provide X and Z numeric input fields and Set X / Set Z buttons on the right side of the button bar.
8. WHEN the user clicks Set X or Set Z, THE Tools_Tab SHALL emit a signal to perform a G10 touch-off command on the currently loaded tool using the entered value.

### Requirement 6: Wear Offset Management

**User Story:** As a CNC operator, I want to manage wear offsets separately from geometry offsets, so that I can make small compensating adjustments without altering the base tool setup.

#### Acceptance Criteria

1. THE Tool_Card SHALL store Wear X and Wear Z values independently from Geometry X Offset and Z Offset.
2. WHEN the user modifies a wear offset, THE Tools_Tab SHALL combine the wear offset with the geometry offset and write the combined value to LinuxCNC via a G10 L1 MDI command.
3. THE Tool_Card SHALL display Wear X in diameter units consistent with the X Offset display convention.

### Requirement 7: Tool Table File I/O

**User Story:** As a CNC operator, I want the tool table saved in standard LinuxCNC format with metadata preserved in comments, so that the file remains compatible with LinuxCNC while retaining GUI-specific data.

#### Acceptance Criteria

1. THE Tools_Tab SHALL save tool data in LinuxCNC .tbl format: `T<n> P<n> X<offset> Z<offset> D<nose_dia> I<front_angle> J<back_angle> Q<orient> ;<metadata>`.
2. THE Tools_Tab SHALL encode tool type, insert code, blade width, and description as pipe-delimited key=value pairs in the comment field (e.g., `type=turning_rh|insert=CNMG|blade=0.000|desc=CNMG 432 roughing`).
3. WHEN loading a .tbl file, THE Tools_Tab SHALL parse the metadata comment to restore tool type, insert code, blade width, and description.
4. WHEN loading a .tbl file that lacks metadata comments, THE Tools_Tab SHALL use default values for tool type (Turning RH), insert code (CNMG), and blade width (0.0).
5. THE Tools_Tab SHALL store front angle in the I field and back angle in the J field of the tool table line.

### Requirement 8: Autosave and Persistence

**User Story:** As a CNC operator, I want changes saved automatically so that I never lose tool data due to forgetting to save.

#### Acceptance Criteria

1. WHEN any field in any Tool_Card changes, THE Tools_Tab SHALL automatically save the entire tool table to the active file.
2. THE Tools_Tab SHALL persist the last loaded table file path in a `.tool_tab_settings.json` file.
3. WHEN the Tools_Tab initializes, THE Tools_Tab SHALL read `.tool_tab_settings.json` and auto-load the previously active tool table.
4. IF the previously active tool table file does not exist at startup, THEN THE Tools_Tab SHALL display an empty tool list and clear the table name label.

### Requirement 9: Tool Deletion and Renumbering

**User Story:** As a CNC operator, I want to delete tools with confirmation and have remaining tools renumbered, so that the tool table stays clean and sequential.

#### Acceptance Criteria

1. WHEN the user clicks the delete button (✕) on a Tool_Card, THE Tools_Tab SHALL display a confirmation dialog before removing the tool.
2. WHEN the user confirms deletion, THE Tools_Tab SHALL remove the tool and renumber all remaining tools sequentially starting from T1.
3. IF the user cancels deletion, THEN THE Tools_Tab SHALL leave the tool list unchanged.

### Requirement 10: Signal Integration

**User Story:** As a developer integrating the Tools tab with other GUI components, I want the tab to emit signals when tools change or are selected, so that other tabs can react to tool state.

#### Acceptance Criteria

1. WHEN any tool field is edited, THE Tools_Tab SHALL emit a `tool_changed(int)` signal with the tool number.
2. WHEN the user selects a tool card (clicks on it), THE Tools_Tab SHALL emit a `tool_selected(ToolDef)` signal with the complete tool definition.
3. THE Tools_Tab SHALL operate in offline mode without requiring a LinuxCNC connection, disabling only the touch-off and G10 write functionality.

### Requirement 11: Insert Geometry Lookup Table Correctness

**User Story:** As a CNC operator, I want the auto-filled angles to match real-world insert geometry standards, so that cutter compensation calculations are accurate.

#### Acceptance Criteria

1. THE Insert_Geometry_Lookup SHALL map CNMG to front angle 95° and back angle 175°.
2. THE Insert_Geometry_Lookup SHALL map CCMT to front angle 95° and back angle 175°.
3. THE Insert_Geometry_Lookup SHALL map WNMG to front angle 95° and back angle 175°.
4. THE Insert_Geometry_Lookup SHALL map DNMG to front angle 62.5° and back angle 117.5°.
5. THE Insert_Geometry_Lookup SHALL map DCMT to front angle 62.5° and back angle 117.5°.
6. THE Insert_Geometry_Lookup SHALL map VNMG to front angle 72.5° and back angle 107.5°.
7. THE Insert_Geometry_Lookup SHALL map TNMG to front angle 60° and back angle 120°.
8. THE Insert_Geometry_Lookup SHALL map SNMG to front angle 45° and back angle 135°.
9. THE Insert_Geometry_Lookup SHALL map RCMT to front angle 0° and back angle 0° (round insert, no angular edges).
10. FOR ALL entries in the Insert_Geometry_Lookup, formatting the entry as a tool table line and parsing it back SHALL produce the same front angle and back angle values (round-trip property).

### Requirement 12: Tool Table Parser Round-Trip

**User Story:** As a developer, I want the tool table serializer and parser to be inverses of each other, so that no data is lost across save/load cycles.

#### Acceptance Criteria

1. FOR ALL valid tool definitions, saving to .tbl format and loading back SHALL produce an equivalent tool definition with matching tool number, X offset, Z offset, nose radius, orientation, front angle, back angle, tool type, insert code, blade width, and description.
2. FOR ALL valid tool table files, loading and then saving SHALL produce a file that when loaded again yields the same tool definitions (idempotent round-trip).
3. THE parser SHALL preserve numeric precision to 6 decimal places for offset values and 1 decimal place for angle values.
