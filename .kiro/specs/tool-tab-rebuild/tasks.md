# Implementation Plan: Tool Tab Rebuild

## Overview

Rebuild the Tools tab as a Mazak-style card-based tool geometry editor. Implementation proceeds bottom-up: pure data layer first (dataclass, lookup, cascade, serializer), then UI widgets (orientation graphic, tool card, button bar), then the top-level Tools_Tab wiring with signals, autosave, and LinuxCNC integration.

## Tasks

- [x] 1. Implement data layer modules (no Qt dependencies)
  - [x] 1.1 Create ToolCardData dataclass and constants
    - Create `pipeline/tool_card_data.py` with the `ToolCardData` dataclass
    - Define `TOOL_TYPES` list, `TYPE_ORIENTATIONS` dict, `TYPE_INSERTS` dict
    - Include `tool_card_to_tool_def()` and `tool_def_to_tool_card()` conversion functions
    - _Requirements: 1.2, 1.5, 1.6, 4.5, 6.1, 6.3_

  - [x] 1.2 Create InsertGeometryLookup module
    - Create `pipeline/insert_geometry_lookup.py` with `INSERT_GEOMETRY` dictionary
    - Map all 13 insert codes to (front_angle, back_angle) tuples per Requirement 11
    - Provide `get_angles(insert_code: str) -> Tuple[float, float]` helper function
    - _Requirements: 3.1, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9_

  - [x] 1.3 Create FilterCascade module
    - Create `pipeline/filter_cascade.py` with `get_valid_orientations(tool_type)` and `get_valid_inserts(tool_type)` functions
    - Implement cascade logic: if current selection not in filtered list, return first valid option
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 1.4 Create ToolTableSerializer module
    - Create `pipeline/tool_table_io.py` with `serialize_tool()`, `deserialize_tool()`, `save_tool_table()`, `load_tool_table()`, `create_backup()` functions
    - Implement .tbl format: `T<n> P<n> X<offset> Z<offset> D<nose_dia> I<front_angle> J<back_angle> Q<orient> ;<metadata>`
    - Metadata as pipe-delimited key=value pairs in comment field
    - Handle missing metadata with defaults (type="Turning RH", insert="CNMG", blade=0.0)
    - X offset stored as diameter in file, converted to/from radius on load/save
    - Preserve 6 decimal places for offsets, 1 decimal place for angles
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 12.1, 12.2, 12.3_

- [ ] 2. Property tests for data layer
  - [ ]* 2.1 Write property test for X-axis diameter/radius conversion
    - **Property 1: X-axis diameter/radius display conversion**
    - **Validates: Requirements 1.5, 6.3**
    - Create `tests/properties/test_tool_tab_properties.py`
    - Use Hypothesis to generate random float values, verify `display(store(x)) == x` and `store(display(x)) == x`

  - [ ]* 2.2 Write property test for insert code auto-fill correctness
    - **Property 2: Insert code auto-fill correctness**
    - **Validates: Requirements 3.2**
    - For each insert code in INSERT_GEOMETRY, verify selecting it produces the correct front and back angles

  - [ ]* 2.3 Write property test for filter cascade validity
    - **Property 3: Filter cascade validity**
    - **Validates: Requirements 4.1, 4.2**
    - For each tool type, verify returned orientations and inserts are subsets of the full lists and match TYPE_ORIENTATIONS/TYPE_INSERTS

  - [ ]* 2.4 Write property test for wear plus geometry offset combination
    - **Property 4: Wear plus geometry offset combination**
    - **Validates: Requirements 6.2**
    - Generate random offset pairs, verify combined value equals arithmetic sum with correct diameter conversion

  - [ ]* 2.5 Write property test for tool table serialization round-trip
    - **Property 5: Tool table serialization round-trip**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.5, 11.10, 12.1, 12.3**
    - Generate random ToolCardData instances via Hypothesis strategy, serialize/deserialize, verify field equality within precision bounds

  - [ ]* 2.6 Write property test for tool table idempotent round-trip
    - **Property 6: Tool table idempotent round-trip**
    - **Validates: Requirements 12.2**
    - Generate random tool lists, save/load/save/load, verify stability after one pass

  - [ ]* 2.7 Write property test for sequential renumbering after deletion
    - **Property 7: Sequential renumbering after deletion**
    - **Validates: Requirements 9.2**
    - Generate random-length tool lists and random deletion index, verify resulting list has N-1 tools numbered 1 to N-1

- [x] 3. Checkpoint - Ensure all data layer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement OrientationGraphicWidget
  - [x] 4.1 Create OrientationGraphicWidget
    - Create `gui/components/orientation_graphic.py` with `OrientationGraphicWidget(QWidget)`
    - Fixed 160×160 pixel size, custom `paintEvent` rendering
    - Implement `set_params(insert_code, orientation, nose_radius, front_angle, back_angle)`
    - Render insert shape from front/back angles, rotate/mirror based on Q1-Q9 orientation
    - Draw nose radius circle at tool tip, control point crosshair at programmed point
    - Highlight cutting edges in accent color
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 5. Implement ToolGeometryRow widget
  - [x] 5.1 Create ToolGeometryRow widget
    - Create `gui/components/tool_geometry_row.py` with `ToolGeometryRow(QWidget)`
    - Compact grid layout with all fields: tool number, description, type dropdown, insert code dropdown, orientation dropdown, delete button (✕), wear X/Z (large orange font), X/Z offsets, nose radius, front/back angles, blade width (conditional)
    - Emit `field_changed(int)`, `delete_requested(int)`, `clicked(int)` signals
    - Implement `get_data() -> ToolCardData` and `set_data(ToolCardData)` methods
    - Display X offset and Wear X in diameter (×2 of stored radius value)
    - Show/hide blade width field based on tool type == "Grooving/Parting"
    - Highlight non-zero wear values visually
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 5.2 Wire filter cascade into ToolGeometryRow
    - On tool type change: filter orientation and insert code dropdowns using FilterCascade
    - Reset to first valid option if current selection is no longer valid
    - Trigger auto-fill of front/back angles on insert code reset
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.3 Wire insert auto-fill into ToolGeometryRow
    - On insert code selection change: auto-populate front/back angles from InsertGeometryLookup
    - Track manual edits: if user manually changes angle fields, do not revert on subsequent insert code changes until insert code itself changes
    - Update OrientationGraphicWidget on any geometry parameter change
    - _Requirements: 3.2, 3.4, 2.2_

- [x] 6. Implement TopButtonBar widget
  - [x] 6.1 Create TopButtonBar widget
    - Create `gui/components/top_button_bar.py` with `TopButtonBar(QWidget)`
    - Layout: Load Table, Save Table As, Add Tool buttons on left; table name label and current tool display in center; touch-off section (X input, Z input, Set X, Set Z buttons) on right
    - Emit signals: `load_clicked`, `save_as_clicked`, `add_tool_clicked`, `set_x_clicked(float)`, `set_z_clicked(float)`
    - Implement `set_table_name(name)` and `set_current_tool(number, description)` methods
    - _Requirements: 5.1, 5.5, 5.6, 5.7_

- [x] 7. Implement Tools_Tab top-level widget
  - [x] 7.1 Create Tools_Tab widget with scroll area and card management
    - Create new `gui/tools_tab.py` (replace existing) with `Tools_Tab(QWidget)`
    - QScrollArea containing QVBoxLayout of ToolGeometryRow widgets
    - Emit `tool_changed(int)` and `tool_selected(object)` signals
    - Implement `get_tools()`, `get_tool(tool_number)`, `get_selected_tool()`, `refresh_current_tool_display()`
    - Wire TopButtonBar signals to handlers
    - _Requirements: 1.1, 10.1, 10.2_

  - [x] 7.2 Implement file I/O handlers (Load, Save As, autosave)
    - Load Table: open file dialog filtered to .tbl, call `load_tool_table()`, populate cards
    - Save Table As: call `create_backup()` then `save_tool_table()` to user-specified path
    - Autosave: on any `field_changed` signal, save entire table to active file path
    - _Requirements: 5.2, 5.3, 8.1_

  - [x] 7.3 Implement settings persistence and startup auto-load
    - Create/read `.tool_tab_settings.json` with `last_table_path`
    - On init: load settings, auto-load previously active table
    - If file not found: display empty list, clear table name label
    - _Requirements: 8.2, 8.3, 8.4_

  - [x] 7.4 Implement tool addition and deletion with renumbering
    - Add Tool: append new blank ToolCardData with next available number, create ToolGeometryRow
    - Delete: show confirmation dialog, remove card, renumber all remaining tools sequentially from T1
    - Disable delete button when only 1 tool remains
    - _Requirements: 5.4, 9.1, 9.2, 9.3_

  - [x] 7.5 Implement LinuxCNC integration and offline mode
    - Touch-off: emit G10 L1 MDI command with entered X (diameter) or Z value for current tool
    - Wear offset change: combine wear + geometry, write via G10 L1 MDI (X in diameter)
    - Current tool display: read from LinuxCNC stat channel when available
    - Offline mode: disable touch-off buttons and G10 writes, show "Offline" in current tool display
    - _Requirements: 5.6, 5.8, 6.2, 10.3_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Unit and integration tests
  - [ ]* 9.1 Write unit tests for InsertGeometryLookup
    - Create `tests/unit/test_insert_geometry_lookup.py`
    - Verify all 13 entries exist with correct angle values per Requirements 11.1–11.9
    - Verify lookup returns correct tuple for each insert code
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9_

  - [ ]* 9.2 Write unit tests for FilterCascade
    - Create `tests/unit/test_filter_cascade.py`
    - Verify type-to-insert and type-to-orientation mappings match Requirement 4.5
    - Verify unknown type returns empty list or raises appropriately
    - _Requirements: 4.5_

  - [ ]* 9.3 Write unit tests for ToolTableSerializer
    - Create `tests/unit/test_tool_table_serializer.py`
    - Test parsing lines with and without metadata comments
    - Test default values for missing metadata (Req 7.4)
    - Test backup file creation
    - Test numeric precision preservation
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 12.3_

  - [ ]* 9.4 Write integration tests for Tools_Tab
    - Create `tests/integration/test_tools_tab.py`
    - Test load real `tool.tbl` file from project root, verify all tools parse
    - Test end-to-end: create tool → edit fields → autosave → reload → verify data intact
    - Test offline mode disables only touch-off functionality
    - _Requirements: 8.1, 10.3, 12.1_

- [x] 10. Wire Tools_Tab into MainWindow
  - [x] 10.1 Integrate Tools_Tab with MainWindow signal bridge
    - Update `gui/main_window.py` to instantiate new Tools_Tab
    - Connect `tool_changed` and `tool_selected` signals to MainWindow handlers
    - Ensure tab switching and signal flow works with existing ProgramTab integration
    - _Requirements: 10.1, 10.2_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The data layer (tasks 1.1–1.4) has zero Qt dependencies and can be tested independently
- The design specifies Python with PyQt5, Hypothesis for property tests, and pytest for unit tests
- File paths follow existing project conventions: `pipeline/` for data modules, `gui/components/` for widgets, `tests/properties/` and `tests/unit/` for tests

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4"] },
    { "id": 3, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7"] },
    { "id": 4, "tasks": ["4.1", "6.1"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3"] },
    { "id": 7, "tasks": ["7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3", "7.4", "7.5"] },
    { "id": 9, "tasks": ["9.1", "9.2", "9.3"] },
    { "id": 10, "tasks": ["9.4"] },
    { "id": 11, "tasks": ["10.1"] }
  ]
}
```
