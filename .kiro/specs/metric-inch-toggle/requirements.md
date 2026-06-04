# Requirements Document

## Introduction

The Industry CAM Engine currently operates exclusively in inches. This feature adds a metric/inch toggle that allows CNC operators to work in either unit system. The toggle affects all user-facing numeric displays and inputs while preserving the internal inches-only pipeline. When metric mode is active, the G-code output switches to G21 with millimeter values; when in inches mode, G-code uses G20 with inch values. Conversational program files remain stored in inches regardless of display mode.

## Glossary

- **Toggle_Button**: A QPushButton in the status bar that switches the display unit system between inches and metric (millimeters)
- **Unit_Mode**: The currently active display unit system — either "inch" or "metric"
- **DRO**: Digital Readout — the live position display showing X (diameter) and Z axis coordinates in the status bar
- **NumericField**: The custom QLineEdit-based widget used for all numeric input fields throughout the application
- **Conversion_Factor**: The constant 25.4 used to convert inches to millimeters (multiply) or millimeters to inches (divide)
- **GCode_Writer**: The module responsible for generating G-code output from the internal pipeline results
- **Status_Bar**: The top ribbon widget that displays machine state, DRO, feed rate, RPM, and control buttons — always visible regardless of active tab
- **Internal_Value**: A numeric value stored in inches (radius for X, linear for Z) within the pipeline and data models
- **Display_Value**: A numeric value converted for user presentation — multiplied by 25.4 when in metric mode

## Requirements

### Requirement 1: Toggle Button Placement and Behavior

**User Story:** As a CNC operator, I want a clearly visible unit toggle button in the status bar, so that I can switch between metric and inch display at any time without navigating away from my current tab.

#### Acceptance Criteria

1. THE Status_Bar SHALL display the Toggle_Button between the feed rate bubble and the tool bubble
2. WHEN the operator clicks the Toggle_Button, THE Toggle_Button SHALL switch the Unit_Mode between "inch" and "metric"
3. THE Toggle_Button SHALL display the text "IN" when Unit_Mode is "inch" and "MM" when Unit_Mode is "metric"
4. THE Toggle_Button SHALL use a visually distinct style that indicates the current Unit_Mode (matching the status bar bubble aesthetic)
5. THE Toggle_Button SHALL remain visible and accessible regardless of which tab is currently active

### Requirement 2: Default Unit Mode and Session Persistence

**User Story:** As a CNC operator, I want the application to start in inches mode by default, so that behavior is predictable and consistent with LinuxCNC conventions.

#### Acceptance Criteria

1. WHEN the application starts, THE Unit_Mode SHALL default to "inch"
2. WHEN the application is closed and reopened, THE Unit_Mode SHALL reset to "inch" (no persistence across sessions)
3. THE Unit_Mode SHALL persist for the duration of the current application session without requiring re-selection

### Requirement 3: DRO Display Conversion

**User Story:** As a CNC operator, I want the DRO to show positions in my selected unit system, so that I can read coordinates in the units I am thinking in.

#### Acceptance Criteria

1. WHILE Unit_Mode is "metric", THE DRO SHALL display X and Z positions multiplied by the Conversion_Factor (25.4) with units in millimeters
2. WHILE Unit_Mode is "inch", THE DRO SHALL display X and Z positions in inches with 4 decimal places
3. WHILE Unit_Mode is "metric", THE DRO SHALL display positions with 3 decimal places (0.001 mm resolution)
4. WHEN Unit_Mode changes, THE DRO SHALL immediately update the displayed values without requiring a position change from LinuxCNC

### Requirement 4: Numeric Input Field Conversion

**User Story:** As a CNC operator, I want all input fields to accept values in my selected unit system, so that I can enter dimensions directly from metric or inch drawings without manual conversion.

#### Acceptance Criteria

1. WHILE Unit_Mode is "metric", THE NumericField SHALL display stored Internal_Values multiplied by the Conversion_Factor
2. WHILE Unit_Mode is "metric", THE NumericField SHALL convert operator-entered metric values to inches (divide by 25.4) before storing as Internal_Values
3. WHEN Unit_Mode changes, THE NumericField SHALL re-display all current values in the new unit system without altering the stored Internal_Values
4. THE NumericField SHALL adjust its suffix label to reflect the active Unit_Mode (e.g., "mm" instead of "in", "mm/min" instead of "in/min")
5. WHILE Unit_Mode is "metric", THE NumericField SHALL adjust its min/max validation range by multiplying the inch-based limits by the Conversion_Factor

### Requirement 5: Feed Rate Display Conversion

**User Story:** As a CNC operator, I want the feed rate display to show values in my selected unit system, so that I can verify cutting parameters match my metric or inch programming.

#### Acceptance Criteria

1. WHILE Unit_Mode is "metric", THE Status_Bar SHALL display the feed rate multiplied by the Conversion_Factor with the unit label "mm/min"
2. WHILE Unit_Mode is "inch", THE Status_Bar SHALL display the feed rate in inches per minute with the unit label "in/min"
3. WHEN Unit_Mode changes, THE Status_Bar SHALL immediately update the feed rate display and unit label

### Requirement 6: G-code Output Unit Selection

**User Story:** As a CNC operator, I want generated G-code to match my selected unit system, so that the output program is ready to run without manual G20/G21 editing.

#### Acceptance Criteria

1. WHILE Unit_Mode is "metric", THE GCode_Writer SHALL emit G21 in the safety preamble instead of G20
2. WHILE Unit_Mode is "metric", THE GCode_Writer SHALL output all coordinate values (X, Z, I, K) multiplied by the Conversion_Factor
3. WHILE Unit_Mode is "metric", THE GCode_Writer SHALL output feed rate values (F words) multiplied by the Conversion_Factor
4. WHILE Unit_Mode is "inch", THE GCode_Writer SHALL emit G20 in the safety preamble and output all values in inches
5. THE GCode_Writer SHALL format metric coordinate values with 3 decimal places and inch coordinate values with 4 decimal places

### Requirement 7: Internal Pipeline Invariance

**User Story:** As a developer, I want the internal pipeline to remain in inches regardless of display mode, so that all computation logic stays unchanged and unit conversion is isolated to the UI boundary.

#### Acceptance Criteria

1. THE pipeline SHALL process all coordinates, depths of cut, and feed rates in inches regardless of the active Unit_Mode
2. THE NumericField SHALL convert metric input values to inches before passing them to the pipeline or data models
3. THE GCode_Writer SHALL receive inch values from the pipeline and apply conversion only during output formatting
4. FOR ALL valid Internal_Values, converting to Display_Value and back SHALL produce a value within 0.000001 inches of the original (round-trip property)

### Requirement 8: File I/O Unit Invariance

**User Story:** As a CNC operator, I want saved conversational programs to always use inches internally, so that files are portable and consistent regardless of which display mode was active when they were saved or loaded.

#### Acceptance Criteria

1. WHEN saving a conversational program file, THE application SHALL store all numeric values in inches regardless of the active Unit_Mode
2. WHEN loading a conversational program file, THE application SHALL read values as inches and apply display conversion based on the current Unit_Mode
3. THE application SHALL produce identical file content when saving the same program in inch mode versus metric mode

### Requirement 9: Segment List Column Conversion

**User Story:** As a CNC operator, I want the profile segment list to display X, Z, and radius values in my selected unit system, so that I can verify my part geometry in familiar units.

#### Acceptance Criteria

1. WHILE Unit_Mode is "metric", THE Segment_List SHALL display X, Z, and Radius column values multiplied by the Conversion_Factor
2. WHILE Unit_Mode is "inch", THE Segment_List SHALL display X, Z, and Radius column values in inches
3. WHEN Unit_Mode changes, THE Segment_List SHALL refresh all displayed values without modifying the underlying segment data

### Requirement 10: Tool Geometry Display Conversion

**User Story:** As a CNC operator, I want tool offset values displayed in my selected unit system, so that I can verify tool geometry matches my setup sheets.

#### Acceptance Criteria

1. WHILE Unit_Mode is "metric", THE Tools_Tab SHALL display all tool geometry offsets (nose radius, X offset, Z offset) multiplied by the Conversion_Factor
2. WHILE Unit_Mode is "inch", THE Tools_Tab SHALL display all tool geometry offsets in inches
3. WHEN Unit_Mode changes, THE Tools_Tab SHALL refresh all displayed tool geometry values without modifying the stored tool data

### Requirement 11: Manual Tab DRO and Input Conversion

**User Story:** As a CNC operator, I want the manual tab's DRO and touch-off fields to respect the unit toggle, so that I can perform manual operations in my preferred unit system.

#### Acceptance Criteria

1. WHILE Unit_Mode is "metric", THE Manual_Tab SHALL display touch-off input values and jog velocity in millimeters
2. WHILE Unit_Mode is "metric", THE Manual_Tab SHALL convert operator-entered metric touch-off values to inches before sending to LinuxCNC
3. WHEN Unit_Mode changes, THE Manual_Tab SHALL update all displayed values and input field suffixes to reflect the new unit system
