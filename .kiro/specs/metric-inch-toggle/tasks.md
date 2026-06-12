# Implementation Plan: Metric/Inch Toggle

## Overview

Implement a metric/inch toggle for the CNC lathe GUI that allows operators to switch between unit systems. The internal pipeline stays in inches; conversion happens at the UI display boundary and G-code output boundary. A centralized `UnitState` singleton manages mode and emits Qt signals to all subscribing widgets.

## Tasks

- [x] 1. Create UnitState singleton module
  - [x] 1.1 Create `gui/unit_state.py` with UnitMode enum and UnitState class
    - Implement `UnitMode` enum with INCH and METRIC values
    - Implement `UnitState(QObject)` with `unit_changed = pyqtSignal(str)`
    - Implement `toggle()`, `to_display()`, `from_display()`, `decimals`, `is_metric`, `length_suffix`, `feed_suffix` properties
    - Module-level singleton: `unit_state = UnitState()`
    - Default mode is INCH on instantiation
    - _Requirements: 2.1, 7.1, 7.4_

  - [ ]* 1.2 Write property test for round-trip conversion (Property 1)
    - **Property 1: Round-trip conversion preserves value**
    - Use Hypothesis to generate floats in range (-999999, 999999)
    - Assert `abs(from_display(to_display(x)) - x) < 0.000001` in metric mode
    - **Validates: Requirements 7.4**

  - [ ]* 1.3 Write property test for display scaling (Property 2)
    - **Property 2: Display scaling is exactly 25.4×**
    - Assert `to_display(x) == x * 25.4` in metric mode
    - Assert `to_display(x) == x` in inch mode
    - Assert `from_display(x) == x / 25.4` in metric mode
    - **Validates: Requirements 3.1, 4.1, 4.2, 5.1, 9.1, 10.1, 11.1, 11.2**

- [x] 2. Add Toggle Button to Status Bar
  - [x] 2.1 Add toggle button widget to StatusBar in `lathe_gui.py`
    - Create `QPushButton("IN")` with fixed size and bubble styling
    - Insert between feed rate bubble and tool bubble in the status bar layout
    - Connect `clicked` signal to handler that calls `unit_state.toggle()`
    - Connect `unit_state.unit_changed` to update button text ("IN" ↔ "MM")
    - Apply visually distinct style matching status bar bubble aesthetic
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 2.2 Write unit tests for toggle button behavior
    - Test button text changes on click ("IN" → "MM" → "IN")
    - Test button is positioned between feed bubble and tool bubble
    - Test default state shows "IN"
    - _Requirements: 1.2, 1.3, 2.1_

- [x] 3. Enhance NumericField with unit awareness
  - [x] 3.1 Add `unit_aware` flag to NumericFieldConfig
    - Add `unit_aware: bool = True` to the NumericFieldConfig dataclass
    - Fields like RPM, tool number, pass count should set `unit_aware=False`
    - _Requirements: 4.1, 4.2, 7.2_

  - [x] 3.2 Implement unit conversion in NumericField display and input
    - Subscribe to `unit_state.unit_changed` signal
    - On display: multiply stored value by 25.4 when metric (if `unit_aware`)
    - On input: divide entered value by 25.4 before storing (if `unit_aware`)
    - Update suffix label on mode change ("in" ↔ "mm", "in/min" ↔ "mm/min")
    - Adjust validation min/max by conversion factor in metric mode
    - Adjust decimal places (4 inch, 3 metric) for unit-aware fields
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 3.3 Write property test for toggle invariance (Property 3)
    - **Property 3: Toggle does not mutate stored values**
    - Set a value on NumericField, toggle mode N times, verify `.value()` unchanged
    - Use Hypothesis to generate random values and toggle counts
    - **Validates: Requirements 4.3, 7.2, 9.3, 10.3**

  - [ ]* 3.4 Write unit tests for NumericField unit behavior
    - Test suffix updates on toggle
    - Test validation range scales correctly in metric mode
    - Test unit-independent fields (RPM, tool number) are NOT converted
    - Test decimal places change (4 → 3) on toggle
    - _Requirements: 4.4, 4.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update DRO and Feed Rate display
  - [x] 5.1 Update StatusBar DRO to respect unit mode
    - Subscribe DRO labels to `unit_state.unit_changed`
    - Apply conversion factor to X and Z position display when metric
    - Format with 4 decimal places (inch) or 3 decimal places (metric)
    - Immediately update displayed values on mode change without requiring position change
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 5.2 Update StatusBar feed rate display to respect unit mode
    - Subscribe feed rate bubble to `unit_state.unit_changed`
    - Multiply feed rate by 25.4 when metric
    - Update unit label ("in/min" ↔ "mm/min")
    - Immediately update on mode change
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 6. Enhance GCodeWriter with unit mode support
  - [x] 6.1 Add `unit_mode` parameter to GCodeWriter.write()
    - Accept optional `unit_mode: str = "inch"` parameter
    - When metric: emit G21 instead of G20 in safety preamble
    - When metric: multiply all X, Z, I, K coordinates by 25.4
    - When metric: multiply all F (feed) values by 25.4
    - When metric: format coordinates with 3 decimal places (`.3f`)
    - When inch: emit G20, output values unchanged with 4 decimal places (`.4f`)
    - Raise ValueError for invalid unit_mode strings
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.3_

  - [ ]* 6.2 Write property test for G-code preamble (Property 5)
    - **Property 5: G-code preamble matches unit mode**
    - Generate random PlanResults, write in each mode
    - Assert G21 present (not G20) in metric output
    - Assert G20 present (not G21) in inch output
    - **Validates: Requirements 6.1, 6.4**

  - [ ]* 6.3 Write property test for G-code value scaling (Property 6)
    - **Property 6: G-code value scaling is consistent**
    - Write same PlanResult in both modes, parse coordinates
    - Assert metric values ≈ inch values × 25.4 (within 0.0005 mm tolerance)
    - **Validates: Requirements 6.2, 6.3**

  - [ ]* 6.4 Write property test for G-code decimal formatting (Property 7)
    - **Property 7: G-code decimal formatting matches unit mode**
    - Write G-code in each mode, regex-verify coordinate decimal places
    - Assert 3 decimal places in metric, 4 in inch
    - **Validates: Requirements 3.3, 6.5**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Update Segment List display
  - [x] 8.1 Add unit conversion to SegmentListWidget
    - Subscribe to `unit_state.unit_changed` signal
    - On mode change, re-read all rows from internal storage
    - Display X, Z, and Radius columns multiplied by 25.4 when metric
    - Do not modify underlying segment data
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 9. Update Tools Tab display
  - [x] 9.1 Add unit conversion to Tools_Tab
    - Subscribe to `unit_state.unit_changed` signal
    - Display nose radius, X offset, Z offset multiplied by 25.4 when metric
    - Refresh all displayed values on mode change
    - Do not modify stored tool data
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 10. Update Manual Tab
  - [x] 10.1 Add unit conversion to Manual Tab DRO and inputs
    - Subscribe to `unit_state.unit_changed` signal
    - Display touch-off values and jog velocity in mm when metric
    - Convert metric touch-off input to inches before sending to LinuxCNC
    - Update input field suffixes on mode change
    - _Requirements: 11.1, 11.2, 11.3_

- [x] 11. Wire G-code generation to current unit mode
  - [x] 11.1 Pass current unit mode to GCodeWriter from GUI
    - When generating G-code from conversational programming, pass `unit_state.mode.value` to `GCodeWriter.write()`
    - Ensure pipeline still processes everything in inches
    - Only the final output formatting respects the unit mode
    - _Requirements: 6.1, 6.4, 7.1, 7.3_

- [x] 12. Ensure File I/O unit invariance
  - [x] 12.1 Verify save/load uses internal inch values
    - Confirm `_write_program_file` uses `NumericField.value()` (always inches)
    - Confirm `_load_program_data` sets values via `set_value()` (stores inches)
    - Display conversion happens automatically via `unit_changed` signal on load
    - No code changes expected if NumericField.value() already returns inches
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 12.2 Write property test for file I/O invariance (Property 4)
    - **Property 4: File I/O is unit-mode invariant**
    - Generate random program state dicts with Hypothesis
    - Serialize in both inch and metric modes
    - Assert identical JSON output regardless of active mode
    - **Validates: Requirements 8.1, 8.3**

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The internal pipeline (all planners, validators, contour logic) requires zero changes
- All conversion logic is isolated to `unit_state.py`, NumericField, StatusBar, and GCodeWriter
- File I/O task (12.1) may require no code changes — it's a verification step to confirm the existing architecture already handles this correctly

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "5.1", "5.2", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3", "6.4", "8.1", "9.1", "10.1"] },
    { "id": 5, "tasks": ["11.1", "12.1"] },
    { "id": 6, "tasks": ["12.2"] }
  ]
}
```
