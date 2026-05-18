---
inclusion: auto
---

# Visualization Libraries — API Reference

This steering file documents the three visualization libraries used by Industry CAM Engine.
Content was rephrased for compliance with licensing restrictions. See source links for full documentation.

## PyQtGraph (Interactive Visualization — Program Tab + Debug Tab)

**Source:** [pyqtgraph.readthedocs.io](https://pyqtgraph.readthedocs.io/en/latest/)
**Version:** 0.13+ (supports PyQt5 and PyQt6)
**Install:** `pip install pyqtgraph`

### Overview

PyQtGraph is a graphics and UI library for Python providing fast, interactive graphics for engineering and science applications. It uses Qt's GraphicsView framework (vector-based, infinite zoom) and numpy for computation. It runs on Linux, Windows, and macOS.

Key advantages over matplotlib for our use case:
- Fast enough for real-time update (animated playback)
- Vector-based rendering (no pixelation at any zoom level)
- Native PyQt5 widget (embeds directly in our tab layout)
- Interactive scaling/panning built-in
- Coordinate readout at arbitrary precision

### Core Classes (Hierarchy)

```
QWidget subclasses (embeddable in PyQt GUIs):
├── PlotWidget          — QWidget with a single PlotItem (OUR PRIMARY WIDGET)
├── GraphicsLayoutWidget — QWidget with a grid of PlotItems
└── GraphicsView        — Base QWidget wrapping QGraphicsView

QGraphicsItem subclasses (data display):
├── PlotDataItem    — Combines PlotCurveItem + ScatterPlotItem
├── PlotCurveItem   — Line plot from x,y arrays
├── ScatterPlotItem — Point markers from x,y arrays
├── FillBetweenItem — Filled region between two curves (ZONE SHADING)
├── InfiniteLine    — Horizontal/vertical line (CROSSHAIR)
├── LinearRegionItem — Selectable region
└── ImageItem       — 2D image display

Container QGraphicsItems:
├── PlotItem    — Contains ViewBox + AxisItems + title (plot area)
├── ViewBox     — Scalable/pannable container for data items
├── AxisItem    — Axis with ticks and labels
└── GraphicsLayout — Grid of PlotItems
```

### PlotWidget Usage (Our Primary Widget)

```python
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets

# Create and embed in a layout
plot_widget = pg.PlotWidget()
layout.addWidget(plot_widget)

# Access the PlotItem for configuration
plot_item = plot_widget.getPlotItem()

# Plot data
plot_widget.plot(x_array, z_array, pen='g')  # green line
plot_widget.plot(x_array, z_array, pen=pg.mkPen('r', style=pg.QtCore.Qt.DashLine))  # red dashed

# Zone shading (FillBetweenItem)
curve_top = pg.PlotCurveItem(x_top, z_top)
curve_bot = pg.PlotCurveItem(x_bot, z_bot)
fill = pg.FillBetweenItem(curve_top, curve_bot, brush=(255, 0, 0, 50))  # red, 50 alpha
plot_widget.addItem(fill)

# Crosshair
vLine = pg.InfiniteLine(angle=90, movable=False)
hLine = pg.InfiniteLine(angle=0, movable=False)
plot_widget.addItem(vLine)
plot_widget.addItem(hLine)
```

### ViewBox (Zoom/Pan Control)

The ViewBox is the core of PyQtGraph's interactive viewing. Key methods:

```python
vb = plot_widget.getViewBox()

# Set visible range
vb.setRange(xRange=(0.0, 1.25), yRange=(-2.5, 0.0))

# Lock aspect ratio (1:1 for machining — X and Z same scale)
vb.setAspectLocked(True, ratio=1)

# Set zoom/pan limits
vb.setLimits(
    xMin=-0.1, xMax=2.0,      # Pan limits
    yMin=-3.0, yMax=0.5,
    minXRange=0.0005,          # Max zoom in (matches TOLERANCE)
    minYRange=0.0005
)

# Enable/disable mouse axes independently
vb.setMouseEnabled(x=True, y=True)

# Get current view range
[[xmin, xmax], [ymin, ymax]] = vb.viewRange()

# Get pixel size in view coordinates (for adaptive detail)
px_width, px_height = vb.viewPixelSize()

# Auto-fit all content
vb.autoRange()
```

### Coordinate Readout (Crosshair Pattern)

```python
from pyqtgraph.Qt import QtCore

def mouse_moved(evt):
    pos = evt[0]
    if plot_widget.sceneBoundingRect().contains(pos):
        mouse_point = vb.mapSceneToView(pos)
        x_radius = mouse_point.x()
        z_inches = mouse_point.y()
        x_diameter = x_radius * 2.0
        label.setText(
            f"X: {x_radius:.5f}\" (Ø{x_diameter:.4f})  Z: {z_inches:.5f}\""
        )
        vLine.setPos(mouse_point.x())
        hLine.setPos(mouse_point.y())

proxy = pg.SignalProxy(plot_widget.scene().sigMouseMoved, rateLimit=60, slot=mouse_moved)
```

### Axis Tick Formatting (Adaptive Precision)

```python
class PrecisionAxisItem(pg.AxisItem):
    """Axis that adapts decimal places to zoom level."""
    def tickStrings(self, values, scale, spacing):
        if spacing < 0.001:
            return [f"{v:.5f}" for v in values]
        elif spacing < 0.01:
            return [f"{v:.4f}" for v in values]
        elif spacing < 0.1:
            return [f"{v:.3f}" for v in values]
        else:
            return [f"{v:.2f}" for v in values]

# Use custom axis
plot_widget = pg.PlotWidget(
    axisItems={'bottom': PrecisionAxisItem(orientation='bottom'),
               'left': PrecisionAxisItem(orientation='left')}
)
```

### Performance Notes

- PlotCurveItem with 10,000 points: ~1ms render time
- FillBetweenItem: efficient for polygon fills
- For animated playback: update data arrays in-place, call `curve.setData(x, y)`
- ViewBox handles zoom/pan without re-rendering data (just transforms)

### Known Bug: Segmented Line Ghost Artifact (Issue #2178)

PyQtGraph's "segmented line" optimization (PR #2011) for thick lines (width > 1) causes ghost horizontal line artifacts. The artifact appears as a solid line at the bounding-box edge of a PlotCurveItem, same color/weight as the curve. It appears/disappears with the curve when panning.

**Trigger conditions:**
- Pen width > 1
- Many closely-spaced points (e.g., arc interpolation with 20+ points)
- Anti-aliasing enabled (makes it worse but not required)

**Fix:** Set pen alpha to 254 (not 255). This is visually identical but forces pyqtgraph to bypass the segmented line optimization:
```python
from PyQt5.QtGui import QColor
color = QColor(COLORS['graph_profile'])
color.setAlpha(254)  # 254 disables segmented line optimization
pen = pg.mkPen(color, width=2)
```

**Alternative fixes:**
- `pg.setConfigOption('segmentedLineMode', 'off')` — global disable
- Disable anti-aliasing on the widget
- Split polylines into separate PlotCurveItems per logical segment (reduces bounding-box size)

**Rule:** Always use alpha=254 for any pen with width > 1 that may render curves with many points.

### Arc Preview Rendering — Correct Math

When rendering arc segments in the preview (from signed radius, no I/K available):

1. **Work in radius space** — convert X_diameter / 2 for all coordinates
2. **Compute chord** between start and end points in radius+Z space
3. **Find center** using perpendicular offset from chord midpoint:
   - Unit perpendicular: `px = -dz/chord`, `pz = dx_r/chord` (points LEFT of chord direction)
   - CW (G02, positive radius): center = `mid + h*perp` (RIGHT side)
   - CCW (G03, negative radius): center = `mid - h*perp` (LEFT side)
4. **Normalize sweep to [-π, π]** — do NOT use CW/CCW direction-based adjustment:
   ```python
   diff = angle_end - angle_start
   if diff > math.pi: diff -= 2*math.pi
   elif diff < -math.pi: diff += 2*math.pi
   ```
   This always produces the short arc from the correctly-placed center.

**Why this works:** The center placement (step 3) already encodes which arc to draw. The [-π, π] normalization then gives the short path around that center. This matches the proven sim viewer (`_visual_test_arc.py`) which uses I/K from G-code to find the center, then normalizes identically.

**Verified against engine output:** G03 X1.0 Z-1.5 I-1.7321 K-0.5 confirms center at (-0.366 radius, -1.0) for the CCW arc from (0.5r, -0.5) to (0.5r, -1.5) with R=1.0.

### Profile Drawing Strategy

Draw the profile as **separate PlotCurveItems per segment type** (line sub-paths and arc sub-paths), not one giant polyline. This:
- Avoids bounding-box artifacts from a single large item
- Allows different styling per segment type if needed
- Reduces the spatial extent of each item's bounding rect

### GUI Left Panel Sizing

The Program Tab uses a QSplitter with left (input fields) and right (graph/sim) panels:
- Left panel: fixed initial width ~220px, min 210, max 320
- `setStretchFactor(0, 0)` — left panel doesn't grow with window resize
- `setStretchFactor(1, 1)` — right panel (graph) takes all extra space
- The left panel contains a QScrollArea so all fields are accessible regardless of window height

### Zero-Area Zone Guard (Build123d)

`_build_true_face()` in `zone_builder.py` returns `None` when `x_min == x_max` or `z_start == 0`. This prevents Build123d from crashing on zero-length `Line()` calls. The downstream code (ZoneQueryAPI, FacePlanner) already handles `None` gracefully — face planner returns empty passes, zone query skips it in lookups.

### Touch/Gesture Support

PyQtGraph's ViewBox responds to standard Qt touch events. For pinch-to-zoom:
```python
# ViewBox handles pinch-to-zoom natively when Qt touch events are enabled
plot_widget.viewport().setAttribute(QtCore.Qt.WA_AcceptTouchEvents, True)
```

---

## Matplotlib (Static PNG Export Only)

**Source:** [matplotlib.org](https://matplotlib.org/stable/)
**Version:** 3.8+
**Install:** `pip install matplotlib`

### Our Usage (Export Panel Only)

Matplotlib is used ONLY for generating static PNG images of Shapely validation polygons in the Debug Tab's Export panel. It is NOT used for interactive display.

```python
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from shapely.geometry import Polygon
import numpy as np

def export_validation_png(plan_result, output_path, dpi=300):
    """Generate a static PNG of Shapely validation polygons + toolpath."""
    fig, ax = plt.subplots(figsize=(12, 8), layout='constrained')
    
    # Plot zone polygons
    for zone_name, poly, color in [
        ("Finished Part", plan_result.finished_part_poly, 'red'),
        ("Finish Allowance", plan_result.finish_allowance_poly, 'gold'),
        ("Material to Rough", plan_result.material_to_rough_poly, 'lightblue'),
    ]:
        x, y = poly.exterior.xy
        ax.fill(x, y, alpha=0.3, color=color, label=zone_name)
        ax.plot(x, y, color=color, linewidth=1)
    
    # Plot toolpath
    for move in plan_result.tool_moves:
        color = 'green' if move.is_feed else 'red'
        style = '-' if move.is_feed else '--'
        ax.plot([move.start_x, move.end_x], [move.start_z, move.end_z],
                color=color, linestyle=style, linewidth=0.5)
    
    ax.set_xlabel('X (radius, inches)')
    ax.set_ylabel('Z (inches)')
    ax.set_title(f'Validation Polygons — {len(plan_result.tool_moves)} moves')
    ax.set_aspect('equal')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    fig.savefig(output_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
```

### Key Matplotlib Concepts for Our Use

- `fig, ax = plt.subplots()` — Create figure with single axes
- `ax.plot(x, y)` — Line plot
- `ax.fill(x, y)` — Filled polygon
- `ax.set_aspect('equal')` — Equal X/Y scaling (critical for machining geometry)
- `fig.savefig(path, dpi=300)` — Export to PNG
- `plt.close(fig)` — Free memory (important in batch export)

### Why NOT for Interactive Display

- Redraws entire figure on every interaction (slow for pan/zoom)
- Canvas is rasterized at fixed resolution (pixelates on zoom)
- No native touch gesture support
- Coordinate readout requires toolbar, not inline

---

## ezdxf (DXF CAD File Export)

**Source:** [ezdxf.readthedocs.io](https://ezdxf.readthedocs.io/en/stable/)
**Version:** 1.0+
**Install:** `pip install ezdxf`

### Overview

ezdxf is a pure Python library for creating and modifying DXF files. It supports DXF R12 through R2018 formats. Key advantage: it can write TRUE ARC entities (not polyline approximations), which is critical for our toolpath export.

### Our Usage (Export Panel)

```python
import ezdxf
from ezdxf.enums import TextEntityAlignment

def export_dxf(plan_result, output_path):
    """Export zones and toolpath as layered DXF."""
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    
    # Create layers
    doc.layers.add("PROFILE_BOUNDARY", color=7)      # White
    doc.layers.add("STOCK_BOUNDARY", color=8)         # Gray
    doc.layers.add("FINISHED_PART", color=1)          # Red
    doc.layers.add("FINISH_ALLOWANCE", color=2)       # Yellow
    doc.layers.add("MATERIAL_TO_ROUGH", color=4)      # Cyan
    doc.layers.add("TOOLPATH_RAPID", color=1)         # Red
    doc.layers.add("TOOLPATH_FEED", color=3)          # Green
    doc.layers.add("TOOLPATH_ARC", color=5)           # Blue
    doc.layers.add("SWEPT_REGIONS", color=6)          # Magenta
    
    # Add profile boundary (lines and TRUE arcs)
    for segment in plan_result.profile_segments:
        if segment.is_line:
            msp.add_line(
                (segment.start_x, segment.start_z),
                (segment.end_x, segment.end_z),
                dxfattribs={"layer": "PROFILE_BOUNDARY"}
            )
        elif segment.is_arc:
            # TRUE DXF ARC entity — not a polyline approximation
            msp.add_arc(
                center=(segment.center_x, segment.center_z),
                radius=segment.radius,
                start_angle=segment.start_angle_deg,
                end_angle=segment.end_angle_deg,
                dxfattribs={"layer": "PROFILE_BOUNDARY"}
            )
    
    # Add toolpath moves
    for move in plan_result.tool_moves:
        layer = "TOOLPATH_RAPID" if move.is_rapid else "TOOLPATH_FEED"
        if move.is_arc:
            layer = "TOOLPATH_ARC"
            msp.add_arc(
                center=(move.center_x, move.center_z),
                radius=abs(move.radius),
                start_angle=move.start_angle_deg,
                end_angle=move.end_angle_deg,
                dxfattribs={"layer": layer}
            )
        else:
            msp.add_line(
                (move.start_x, move.start_z),
                (move.end_x, move.end_z),
                dxfattribs={"layer": layer}
            )
    
    # Add stock boundary rectangle
    stock = plan_result.stock_boundary
    msp.add_lwpolyline(
        [(0, stock.z_start), (stock.x_radius, stock.z_start),
         (stock.x_radius, stock.z_end), (0, stock.z_end), (0, stock.z_start)],
        dxfattribs={"layer": "STOCK_BOUNDARY"}
    )
    
    doc.saveas(output_path)
```

### Key ezdxf Concepts for Our Use

| Method | Purpose | Our Use |
|--------|---------|---------|
| `ezdxf.new("R2010")` | Create new DXF document | One per export |
| `doc.modelspace()` | Get modelspace layout | All entities go here |
| `doc.layers.add(name, color=N)` | Create layer | One per zone/toolpath type |
| `msp.add_line(start, end)` | Add LINE entity | Straight toolpath moves |
| `msp.add_arc(center, radius, start_angle, end_angle)` | Add ARC entity | Arc toolpath moves (TRUE arcs) |
| `msp.add_lwpolyline(points)` | Add lightweight polyline | Stock boundary, zone boundaries |
| `msp.add_circle(center, radius)` | Add CIRCLE entity | Tool nose radius visualization |
| `doc.saveas(path)` | Save to file | Final output |

### DXF Color Codes

| Code | Color | Our Assignment |
|------|-------|----------------|
| 1 | Red | Finished Part / Rapids |
| 2 | Yellow | Finish Allowance |
| 3 | Green | Feed moves |
| 4 | Cyan | Material to Rough |
| 5 | Blue | Arc moves |
| 6 | Magenta | Swept regions |
| 7 | White/Black | Profile boundary |
| 8 | Gray | Stock boundary |

### Why ezdxf Over Alternatives

- **Pure Python** — no compiled dependencies, works on Windows and Linux
- **True ARC entities** — not polyline approximations (critical for precision)
- **Layered output** — each zone/toolpath type on its own layer for CAD filtering
- **R2010 format** — compatible with AutoCAD, LibreCAD, FreeCAD, NX, SolidWorks
- **Mature and maintained** — active development since 2011

---

## Coordinate Convention Reminder (All Libraries)

All visualization uses the Build123d/Shapely coordinate system:
- **X axis:** RADIUS (not diameter) — matches kernel internal representation
- **Z axis:** INCHES (negative = into workpiece)
- **Crosshair readout:** Shows BOTH radius and diameter for X

The graph_adapter converts from PlanResult (which uses DIAMETER for X in ToolMove) to radius for display. The G-code writer converts back to diameter for output. The user sees diameter in the crosshair readout alongside radius.

```
PlanResult (X = diameter) → graph_adapter (X = radius) → PyQtGraph display
                                                          ↓
                                                   Crosshair shows:
                                                   "X: 0.6250\" (Ø1.2500)  Z: -0.7500\""
```


## Graph Display Convention: Diameter Labels, Radius Geometry

### The Rule

The graph plots ALL geometry in **radius** coordinates (matching Build123d, Shapely, and the kernel's internal representation). The X axis **labels** display diameter values. The shape, proportion, and spatial relationships on screen are physically accurate — never distorted by a coordinate transform.

### Why This Works

- Build123d works in radius internally
- Shapely polygons are constructed in radius
- The graph_adapter passes radius coordinates directly to PyQtGraph
- PyQtGraph renders true geometry (a 0.250" radius arc IS a 0.250" radius arc on screen)
- Only the axis tick labels and crosshair readout multiply by 2.0 for display

### Implementation

```python
class DiameterAxisItem(pg.AxisItem):
    """X axis that displays diameter while plotting in radius."""
    def tickStrings(self, values, scale, spacing):
        # values = radius (true position), display = diameter
        if spacing < 0.001:
            return [f"{v * 2.0:.5f}" for v in values]
        elif spacing < 0.01:
            return [f"{v * 2.0:.4f}" for v in values]
        else:
            return [f"{v * 2.0:.3f}" for v in values]
```

The Z axis uses standard labels (no conversion — Z is always inches).

### Crosshair Readout

```
X: 0.6250" (Ø1.2500)  Z: -0.7500"
```

Shows radius first (matches the graph position), diameter in parentheses (matches G-code X words and UI input fields). The machinist sees both — radius for reading the graph, diameter for correlating to G-code and input.

### Half-Part Display (One Side of Centerline)

The graph shows ONLY the positive-X side (tool side). No mirroring across the centerline.

Reasons:
- The tool only operates on one side — mirroring adds zero information for toolpath verification
- Maximizes screen resolution on a 15.6" panel (full graph width = one side of the part)
- Zone shading is unambiguous (no mirrored "phantom" zones)
- Toolpath traces are clear (one line per move, not two converging lines)
- Matches industry convention (Mazak, Haas, Fanuc conversational all show half-profile)
- Zoom to 0.001" uses full graph width for the region of interest

A thin white dashed centerline at X=0 (radius=0) is always drawn as a spatial reference.

### What This Means for the Pipeline

| Stage | X Convention | Notes |
|-------|-------------|-------|
| UI input fields | Diameter | User types "1.250" for stock dia |
| ProfileMove.x | Diameter | Stored as user entered |
| model_builder | Converts to radius | For Build123d sketch plane |
| Build123d / OCCT | Radius | Kernel operates in radius |
| Shapely polygons | Radius | Validation in radius |
| PlanResult.tool_moves[].x | Diameter | Back to diameter for G-code compatibility |
| graph_adapter | Converts to radius | Divides by 2.0 for display |
| PyQtGraph plot | Radius | True geometry on screen |
| Axis labels | Diameter (×2) | Display-only label transform |
| Crosshair | Both | "X: 0.6250\" (Ø1.2500)" |
| G-code output | Diameter | X words in diameter per LinuxCNC convention |
