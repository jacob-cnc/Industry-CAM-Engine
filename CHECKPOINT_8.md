# Checkpoint 8 — GUI SimViewer Integration

## Date: 2026-05-16

## Summary
Dropped the proven `_visual_test_arc.py` SimViewer directly into the GUI as a reusable
`SimViewerWidget` component. Both Program and Edit tabs now use it for smooth playback,
G-code sync, and toolpath visualization.

## Changes This Session

### SimViewerWidget (`gui/components/sim_viewer.py`) — NEW
- Extracted from proven `_visual_test_arc.py` — identical architecture
- Smooth interpolated playback (80 pts/inch feed, 20 pts/inch rapid, true arc interp)
- G-code panel with centered line highlighting synced to playback
- Controls: Play/Pause, Reset, < Step, Step >, Show All, Hide Code, Hide Rapids
- Collapsible G-code panel (drag splitter or button toggle)
- Speed control: 0.25x to 10x

### Graph Widget (`gui/components/graph_widget.py`)
- Removed setLimits() that caused zoom lock-up
- Kept 1:1 aspect ratio lock
- Inverted Y axis for operator POV (X+ at bottom)
- Double-click to auto-fit view
- Zone shading via QGraphicsPolygonItem (fixed import from QtWidgets)
- Rapids tracked separately for show/hide toggle
- `set_rapids_visible()` API

### Program Tab
- Right panel replaced with SimViewerWidget (was broken PlaybackController)
- `_on_generate_clicked` feeds SimViewerWidget via `.load(graph_data, gcode, sim_moves)`
- `_open_gcode_file` also feeds SimViewerWidget
- File I/O: Open/Save/Save As for both .json programs and .ngc G-code
- Tool integration: uses active tool from Tools tab

### Edit Tab
- Right panel is SimViewerWidget (graph + G-code panel + controls)
- Preview button parses G-code and loads into SimViewerWidget
- File Open handles both G-code and conversational (.json) files
- G-code syntax highlighting with per-code colors (G00=red, G01=green, G02=cyan, G03=purple, etc.)
- Encoding fallback: UTF-8 → Latin-1 for non-UTF files

### Debug Tab
- Export buttons wired to actual exporters (DXF, SVG, PNG, G-code, G-code→DXF)
- All exports functional with error handling and status feedback

### Known Issue
- Zone shading polygons not rendering (QGraphicsPolygonItem added to ViewBox but not visible)

## File Manifest (modified)
- gui/components/sim_viewer.py (NEW)
- gui/components/graph_widget.py
- gui/program_tab.py
- gui/edit_tab.py
- gui/debug_tab.py
- gui/main_window.py
