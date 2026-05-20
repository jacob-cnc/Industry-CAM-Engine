# Design Document: Tool Tab Rebuild

## Overview

This design replaces the current split-panel (list + editor) Tools tab with a Mazak-style card-based layout. Each tool is a self-contained `ToolGeometryRow` widget showing all fields inline — wear offsets, geometry offsets, type/insert/orientation dropdowns, angles, and a live orientation graphic. The tab adds a top button bar with file operations, touch-off controls, and active tool display.

The rebuild touches three layers:
1. **Data model** — Extended `ToolCardData` dataclass with wear offsets, front/back angles, insert code, blade width, and tool type (distinct from the pipeline's `ToolDef` which remains unchanged)
2. **Serialization** — New `.tbl` format writer/parser with metadata in comments and I/J angle fields
3. **UI** — Card-based scrollable layout with filter cascades, auto-fill, and orientation graphic

### Design Decisions

- **Separate `ToolCardData` from pipeline `ToolDef`**: The GUI needs fields (wear offsets, insert code, blade width, tool type enum with more granularity) that don't belong in the CAM pipeline's `ToolDef`. A mapping function converts between them at the boundary.
- **Card layout over table**: Cards show all fields without horizontal scrolling and allow per-tool orientation graphics. Trade-off: more vertical space per tool, but the scrollable list handles this.
- **Metadata in .tbl comments**: Preserves LinuxCNC compatibility while storing GUI-specific data. Any LinuxCNC tool table editor ignores comments.
- **Filter cascade as pure functions**: Type-to-orientation and type-to-insert mappings are plain dictionaries, testable without Qt.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Tools_Tab (QWidget)                                                │
│  ├── TopButtonBar                                                   │
│  │   ├── Load Table | Save Table As | Add Tool                      │
│  │   ├── Table Name Label | Current Tool Display                    │
│  │   └── Touch-Off Section (X input, Z input, Set X, Set Z)        │
│  └── QScrollArea                                                    │
│      └── QVBoxLayout (tool_card_container)                          │
│          ├── ToolGeometryRow(tool_1)                                │
│          ├── ToolGeometryRow(tool_2)                                │
│          └── ...                                                    │
├─────────────────────────────────────────────────────────────────────┤
│  Data Layer (no Qt)                                                 │
│  ├── ToolCardData (dataclass)                                       │
│  ├── InsertGeometryLookup (dict)                                    │
│  ├── FilterCascade (type → orientations, type → inserts)            │
│  └── ToolTableSerializer (save/load .tbl with metadata)             │
├─────────────────────────────────────────────────────────────────────┤
│  Integration                                                        │
│  ├── LinuxCNC MDI (G10 L1 commands via stat/command channels)       │
│  └── Signal bridge (tool_changed, tool_selected → MainWindow)       │
└─────────────────────────────────────────────────────────────────────┘
```

### Signal Flow

```
ToolGeometryRow.field_changed → Tools_Tab._on_card_field_changed
    → ToolTableSerializer.save (autosave)
    → Tools_Tab.tool_changed.emit(tool_number)
    → (if wear changed) LinuxCNC MDI G10 L1

ToolGeometryRow.clicked → Tools_Tab._on_card_clicked
    → Tools_Tab.tool_selected.emit(ToolCardData)

TopButtonBar.set_x_clicked → Tools_Tab._on_touch_off('X', value)
    → LinuxCNC MDI G10 L1 P<tool> X<value>

TopButtonBar.set_z_clicked → Tools_Tab._on_touch_off('Z', value)
    → LinuxCNC MDI G10 L1 P<tool> Z<value>
```

---

## Components and Interfaces

### Tools_Tab (QWidget)

The top-level tab widget. Owns the tool list, button bar, and scroll area.

```python
class Tools_Tab(QWidget):
    # Signals
    tool_changed = pyqtSignal(int)        # tool_number
    tool_selected = pyqtSignal(object)    # ToolCardData

    # Public API
    def get_tools(self) -> List[ToolCardData]: ...
    def get_tool(self, tool_number: int) -> Optional[ToolCardData]: ...
    def get_selected_tool(self) -> Optional[ToolCardData]: ...
    def refresh_current_tool_display(self) -> None: ...
```

### ToolGeometryRow (QWidget)

A single tool card. Compact grid layout with all fields inline.

```python
class ToolGeometryRow(QWidget):
    field_changed = pyqtSignal(int)   # tool_number
    delete_requested = pyqtSignal(int)  # tool_number
    clicked = pyqtSignal(int)         # tool_number

    def __init__(self, tool_data: ToolCardData, parent=None): ...
    def get_data(self) -> ToolCardData: ...
    def set_data(self, data: ToolCardData) -> None: ...
    def set_tool_number(self, number: int) -> None: ...
```

**Grid Layout (approximate):**

```
┌──────────────────────────────────────────────────────────────────────────┐
│ T01  [Description________________________]  [Type ▼]  [Insert ▼]  [✕]   │
├──────────────────────────────────────────────────────────────────────────┤
│ Wear X: [±0.0000]  Wear Z: [±0.0000]  │  X Off: 0.000000  Z Off: 0.000 │
│ Orient: [Q1 ▼]  Nose R: [0.0160]      │  Front∠: [95.0]  Back∠: [175.0]│
│ [Blade W: 0.000] (if grooving)         │  ┌────────────────┐            │
│                                         │  │ Orientation     │            │
│                                         │  │ Graphic 160×160 │            │
│                                         │  └────────────────┘            │
└──────────────────────────────────────────────────────────────────────────┘
```

### OrientationGraphicWidget (QWidget)

160×160 pixel custom paint widget showing insert shape, cutting edges, nose radius circle, and control point crosshair.

```python
class OrientationGraphicWidget(QWidget):
    def __init__(self, parent=None): ...
    def set_params(
        self,
        insert_code: str,
        orientation: int,
        nose_radius: float,
        front_angle: float,
        back_angle: float,
    ) -> None: ...
    def paintEvent(self, event) -> None: ...
```

Rendering approach:
- Insert shape derived from front/back angles (not tip_angle as in current implementation)
- Orientation Q1–Q9 determines rotation/mirror of the shape
- Nose radius drawn as a circle at the tool tip
- Control point crosshair at the programmed point (tip of nose radius arc)
- Cutting edges highlighted in accent color

### TopButtonBar (QWidget)

```python
class TopButtonBar(QWidget):
    load_clicked = pyqtSignal()
    save_as_clicked = pyqtSignal()
    add_tool_clicked = pyqtSignal()
    set_x_clicked = pyqtSignal(float)  # diameter value
    set_z_clicked = pyqtSignal(float)

    def set_table_name(self, name: str) -> None: ...
    def set_current_tool(self, number: int, description: str) -> None: ...
```

### ToolTableSerializer (no Qt)

Pure Python module for .tbl file I/O. Lives in `pipeline/tool_table_io.py` (replaces the tool-related functions in `pipeline/file_io.py`).

```python
def serialize_tool(tool: ToolCardData) -> str: ...
def deserialize_tool(line: str) -> ToolCardData: ...
def save_tool_table(tools: List[ToolCardData], path: str) -> None: ...
def load_tool_table(path: str) -> List[ToolCardData]: ...
def create_backup(source_path: str) -> str: ...
```

### FilterCascade (no Qt)

Pure data module defining valid combinations.

```python
# Type → valid orientations
TYPE_ORIENTATIONS: Dict[str, List[int]] = { ... }

# Type → valid insert codes
TYPE_INSERTS: Dict[str, List[str]] = { ... }

def get_valid_orientations(tool_type: str) -> List[int]: ...
def get_valid_inserts(tool_type: str) -> List[str]: ...
```

### InsertGeometryLookup (no Qt)

Pure data dictionary.

```python
INSERT_GEOMETRY: Dict[str, Tuple[float, float]] = {
    "CNMG": (95.0, 175.0),
    "CCMT": (95.0, 175.0),
    "WNMG": (95.0, 175.0),
    "DNMG": (62.5, 117.5),
    "DCMT": (62.5, 117.5),
    "VNMG": (72.5, 107.5),
    "TNMG": (60.0, 120.0),
    "SNMG": (45.0, 135.0),
    "RCMT": (0.0, 0.0),
    "60° UN/Metric": (30.0, 30.0),
    "55° Whitworth": (27.5, 27.5),
    "ACME": (14.5, 14.5),
    "Grooving": (0.0, 0.0),
}
```

---

## Data Models

### ToolCardData

```python
@dataclass
class ToolCardData:
    """GUI-layer tool definition with all fields needed for the card display.

    Coordinates:
        x_offset: X geometry offset in RADIUS (inches) — displayed as diameter
        z_offset: Z geometry offset (inches)
        x_wear: X wear offset in RADIUS (inches) — displayed as diameter
        z_wear: Z wear offset (inches)
        nose_radius: Tool nose radius (inches)
        front_angle: Front cutting edge angle (degrees)
        back_angle: Back cutting edge angle (degrees)
        blade_width: Grooving blade width (inches), 0.0 for non-grooving
    """
    tool_number: int
    tool_type: str          # "Turning RH", "Turning LH", "Boring Bar", etc.
    insert_code: str        # "CNMG", "CCMT", "60° UN/Metric", etc.
    orientation: int        # Q1–Q9
    description: str
    nose_radius: float
    front_angle: float
    back_angle: float
    x_offset: float         # radius internally
    z_offset: float
    x_wear: float           # radius internally
    z_wear: float
    blade_width: float = 0.0
```

### Tool Type Enum Values

```python
TOOL_TYPES = [
    "Turning RH",
    "Turning LH",
    "Boring Bar",
    "Threading External",
    "Threading Internal",
    "Grooving/Parting",
    "Knurling",
    "Custom",
]
```

### Type-to-Insert Mapping

```python
TYPE_INSERTS = {
    "Turning RH": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT"],
    "Turning LH": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT"],
    "Boring Bar": ["CCMT", "DCMT", "VNMG", "RCMT"],
    "Threading External": ["60° UN/Metric", "55° Whitworth", "ACME"],
    "Threading Internal": ["60° UN/Metric", "55° Whitworth", "ACME"],
    "Grooving/Parting": ["Grooving"],
    "Knurling": ["Custom"],
    "Custom": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT",
               "60° UN/Metric", "55° Whitworth", "ACME", "Grooving"],
}
```

### Type-to-Orientation Mapping

```python
TYPE_ORIENTATIONS = {
    "Turning RH": [1, 2, 3, 4],      # OD orientations
    "Turning LH": [1, 2, 3, 4],
    "Boring Bar": [5, 6, 7, 8],       # ID orientations
    "Threading External": [1, 2],
    "Threading Internal": [5, 6],
    "Grooving/Parting": [1, 2, 5, 6], # Front/back face
    "Knurling": [9],                   # Center
    "Custom": [1, 2, 3, 4, 5, 6, 7, 8, 9],
}
```

### .tbl File Format

```
T1 P1 X+0.000000 Z-1.234567 D0.032000 I95.0 J175.0 Q1 ;type=turning_rh|insert=CNMG|blade=0.000|desc=CNMG 432 roughing
T2 P2 X+0.000000 Z-0.500000 D0.032000 I62.5 J117.5 Q2 ;type=boring_bar|insert=DCMT|blade=0.000|desc=DCMT boring
```

Field mapping:
- `T` — tool number
- `P` — pocket (same as tool number for QCTP)
- `X` — X offset in diameter
- `Z` — Z offset
- `D` — nose diameter (nose_radius × 2)
- `I` — front angle (degrees)
- `J` — back angle (degrees)
- `Q` — orientation (1–9)
- `;` — comment containing pipe-delimited metadata

Metadata keys: `type`, `insert`, `blade`, `desc`

### Settings File (.tool_tab_settings.json)

```json
{
    "last_table_path": "/home/jacob/linuxcnc/configs/industry-cam/tool.tbl"
}
```

### Conversion: ToolCardData ↔ ToolDef

```python
def tool_card_to_tool_def(card: ToolCardData) -> ToolDef:
    """Convert GUI card data to pipeline ToolDef for CAM operations."""
    ...

def tool_def_to_tool_card(tool: ToolDef) -> ToolCardData:
    """Convert pipeline ToolDef to GUI card data (with defaults for GUI-only fields)."""
    ...
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: X-axis diameter/radius display conversion

*For any* X-axis value (geometry offset or wear offset) stored internally as radius, the value displayed in the UI shall equal exactly 2× the stored radius value, and conversely, any value entered by the user in the UI (diameter) shall be stored as exactly half that value (radius).

**Validates: Requirements 1.5, 6.3**

### Property 2: Insert code auto-fill correctness

*For any* insert code present in the Insert_Geometry_Lookup, selecting that insert code in the dropdown shall set the front angle field to the lookup's front angle value and the back angle field to the lookup's back angle value.

**Validates: Requirements 3.2**

### Property 3: Filter cascade validity

*For any* tool type, the orientation dropdown shall contain only orientations listed in TYPE_ORIENTATIONS for that type, and the insert code dropdown shall contain only insert codes listed in TYPE_INSERTS for that type.

**Validates: Requirements 4.1, 4.2**

### Property 4: Wear plus geometry offset combination

*For any* wear offset value and geometry offset value (both in radius for X, direct for Z), the combined value written to LinuxCNC via G10 L1 shall equal the arithmetic sum of wear and geometry (with X converted to diameter for the G10 command).

**Validates: Requirements 6.2**

### Property 5: Tool table serialization round-trip

*For any* valid `ToolCardData` instance, serializing it to .tbl format and deserializing the resulting line back shall produce a `ToolCardData` with matching tool_number, x_offset (to 6 decimal places), z_offset (to 6 decimal places), nose_radius (to 6 decimal places), orientation, front_angle (to 1 decimal place), back_angle (to 1 decimal place), tool_type, insert_code, blade_width, and description.

**Validates: Requirements 7.1, 7.2, 7.3, 7.5, 11.10, 12.1, 12.3**

### Property 6: Tool table idempotent round-trip

*For any* valid list of `ToolCardData` instances, saving to a .tbl file, loading back, saving again, and loading a second time shall produce the same list of tool definitions as the first load (the save/load cycle is stable after one pass).

**Validates: Requirements 12.2**

### Property 7: Sequential renumbering after deletion

*For any* tool list of size N (where N ≥ 2) and any valid deletion index i (0 ≤ i < N), after deleting the tool at index i and renumbering, the resulting list shall have exactly N−1 tools numbered sequentially from 1 to N−1.

**Validates: Requirements 9.2**

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| .tbl file not found on startup | Display empty tool list, clear table name label, log warning |
| .tbl file parse error (malformed line) | Skip malformed lines, load valid tools, show warning toast |
| .tbl file missing metadata comment | Use defaults: type="Turning RH", insert="CNMG", blade=0.0 |
| Autosave write failure | Silent fail (non-blocking), set dirty indicator on tab title |
| LinuxCNC not connected (offline mode) | Disable touch-off buttons and G10 writes; all other functionality works |
| G10 MDI command failure | Show error toast with command text, do not revert wear value |
| Invalid numeric input in field | NumericField shows red border, reverts to last valid value on focus loss |
| Tool number conflict on add | Auto-assign next available number (1–99) |
| Delete last remaining tool | Disable delete button when only 1 tool remains |
| Settings JSON corrupt/missing | Use default tool table path, recreate settings on next save |

### Offline Mode Behavior

When `HAS_LINUXCNC = False`:
- Touch-off section: Set X / Set Z buttons disabled, inputs grayed out
- Current tool display: shows "Offline" instead of active tool
- G10 writes on wear change: skipped (wear stored locally only)
- All other functionality (editing, saving, loading, auto-fill, cascades): fully operational

---

## Testing Strategy

### Property-Based Tests (Hypothesis)

The feature is well-suited for property-based testing because it has pure data transformation functions (serialization, filter cascades, numeric conversions) with large input spaces.

**Library:** Hypothesis (already used in the project — `.hypothesis/` directory exists)

**Configuration:** Minimum 100 examples per property test.

**Tag format:** `# Feature: tool-tab-rebuild, Property N: <property text>`

Tests to implement:
1. **Diameter/radius conversion round-trip** — Generate random floats, verify `display(store(x)) == x` and `store(display(x)) == x`
2. **Insert auto-fill correctness** — For each insert code in lookup, verify angles match
3. **Filter cascade validity** — For each tool type, verify returned options are subsets of the full option lists and match the mapping
4. **Wear + geometry combination** — Generate random offset pairs, verify sum correctness
5. **Serialization round-trip** — Generate random `ToolCardData` instances, serialize/deserialize, verify equality
6. **Idempotent round-trip** — Generate random tool lists, save/load/save/load, verify stability
7. **Renumbering after deletion** — Generate random-length tool lists, delete at random index, verify sequential numbering

### Unit Tests (pytest)

- Insert geometry lookup contains all required entries with correct values (Req 11.1–11.9)
- Filter cascade mapping matches specification (Req 4.5)
- Blade width field visibility toggles on tool type change (Req 1.6)
- Auto-fill does not overwrite manual edits (Req 3.4)
- Default values applied for missing metadata (Req 7.4)
- Settings file persistence and recovery (Req 8.2, 8.3, 8.4)
- Signal emissions on field edit and card selection (Req 10.1, 10.2)
- Backup creation on Save As (Req 5.3)
- Confirmation dialog on delete (Req 9.1)
- Offline mode disables touch-off only (Req 10.3)

### Integration Tests

- Load a real LinuxCNC .tbl file (from `tool.tbl` in project root), verify all tools parse
- G10 MDI command formatting with mock LinuxCNC command channel
- End-to-end: create tool → edit fields → autosave → reload → verify data intact

### File Structure

```
tests/
├── gui/
│   ├── test_tool_card_data.py          # ToolCardData creation, validation
│   ├── test_tool_table_serializer.py   # Property tests for round-trip
│   ├── test_filter_cascade.py          # Property tests for cascade validity
│   ├── test_insert_geometry_lookup.py  # Unit tests for lookup values
│   └── test_tools_tab_integration.py   # Qt widget tests (QTest)
└── pipeline/
    └── test_tool_table_io.py           # Serialization unit tests
```
