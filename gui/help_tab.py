"""Help Tab — In-app documentation and reference.

Provides searchable, categorized help content for the operator:
    - Quick Start guide
    - Tab-by-tab usage reference
    - G-code reference (exhaustive, searchable table of all LinuxCNC codes)
    - Machine info (hardware, limits, conventions)
    - Troubleshooting

Architecture:
    - QTabWidget with two sub-tabs:
        1. Documentation — topic tree (left) + content browser (right)
        2. G-code Reference — searchable table of all G/M/O codes
"""

import logging
from typing import Dict, List, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QTextBrowser,
    QLineEdit, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox,
)
from PyQt5.QtGui import QFont, QColor

from gui.colors import COLORS, FONTS
from gui.gcode_reference import G_CODES, M_CODES, OTHER_CODES, get_all_codes

logger = logging.getLogger(__name__)


# =============================================================================
# Help Content — structured as (title, html_body) tuples per category
# =============================================================================

HELP_CONTENT: Dict[str, List[Tuple[str, str]]] = {
    "Getting Started": [
        ("Quick Start", """
<h2>Quick Start</h2>
<p>Industry CAM Engine is a conversational CAM system for your 2-axis CNC lathe.
The typical workflow is:</p>
<ol>
<li><b>Program tab</b> — Define your part profile, stock, and cutting parameters</li>
<li><b>Generate</b> — Click Generate to create the toolpath</li>
<li><b>Preview</b> — Review the toolpath animation and G-code</li>
<li><b>Run tab</b> — Open the .ngc file and execute on the machine</li>
</ol>
<h3>First Time Setup</h3>
<ul>
<li>Set up your tools in the <b>Tools</b> tab (nose radius, orientation, offsets)</li>
<li>Home the machine (Manual tab → Home All)</li>
<li>Touch off your workpiece (set X and Z zero)</li>
</ul>
"""),
        ("Coordinate System", """
<h2>Coordinate System</h2>
<h3>Axis Conventions</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Axis</th><th>Positive Direction</th><th>Units</th></tr>
<tr><td>X+</td><td>Away from spindle center (increasing diameter)</td><td>Inches (diameter)</td></tr>
<tr><td>Z+</td><td>Toward tailstock (away from chuck)</td><td>Inches</td></tr>
</table>
<h3>X Diameter vs Radius</h3>
<p>All user-facing values (DRO, G-code, input fields) are in <b>diameter</b>.
Internally the engine works in radius. You never need to worry about this —
the conversion is automatic.</p>
<h3>Work Coordinate Systems</h3>
<p>G54 is the default work coordinate system. Touch-off sets the G54 origin.
G55–G59 are available for multiple setups.</p>
"""),
    ],
    "Tabs": [
        ("Manual Tab", """
<h2>Manual Tab</h2>
<p>Direct machine control for jogging, homing, and manual operations.</p>
<h3>MPG Modes</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Mode</th><th>Type</th><th>Behavior</th></tr>
<tr><td>.0002</td><td>Position</td><td>0.0002" per MPG click (finest)</td></tr>
<tr><td>.001</td><td>Position</td><td>0.001" per MPG click (standard)</td></tr>
<tr><td>Slow</td><td>Velocity</td><td>~0.1 in/s at moderate spin</td></tr>
<tr><td>Medium</td><td>Velocity</td><td>~0.3 in/s at moderate spin</td></tr>
<tr><td>Fast</td><td>Velocity</td><td>~0.6 in/s (capped by MAX_VEL)</td></tr>
</table>
<p><b>Position modes:</b> Each MPG click moves a fixed distance. If you spin fast,
moves queue up and the axis continues after you stop.</p>
<p><b>Velocity modes:</b> Axis speed is proportional to how fast you spin the wheel.
Stopping the wheel stops the axis within the deceleration ramp. No backlog.</p>
<h3>Touch-Off</h3>
<p>To set your work zero:</p>
<ol>
<li>Jog the tool to touch the workpiece surface</li>
<li>Select the axis (X or Z) in the touch-off section</li>
<li>Enter the value at this position (e.g., X = stock diameter for OD touch)</li>
<li>Click Touch Off</li>
</ol>
"""),
        ("Program Tab", """
<h2>Program Tab</h2>
<p>Conversational part programming — define geometry and cutting parameters,
then generate a complete toolpath.</p>
<h3>Workflow</h3>
<ol>
<li><b>Select block type</b> — OD Profile or ID Profile</li>
<li><b>Define stock</b> — diameter, Z start/end, pilot hole (if boring)</li>
<li><b>Set roughing parameters</b> — depth of cut, feed, stepover</li>
<li><b>Set finishing parameters</b> — spring passes, finish feed, allowance</li>
<li><b>Define profile segments</b> — lines and arcs that form the finished part shape</li>
<li><b>Select tool</b> — from the Tools tab</li>
<li><b>Click Generate</b> — creates the toolpath with full validation</li>
</ol>
<h3>Profile Segments</h3>
<p>Segments are defined from Z-start toward Z-end (left to right in the graph).
Each segment is a LINE or ARC with an endpoint (X diameter, Z) and optional radius.</p>
<ul>
<li><b>LINE</b> — straight cut to the endpoint</li>
<li><b>ARC CW</b> — clockwise arc (as seen on screen) to the endpoint</li>
<li><b>ARC CCW</b> — counter-clockwise arc to the endpoint</li>
</ul>
<h3>Saving Programs</h3>
<p>Save creates two files:</p>
<ul>
<li><b>.json</b> — conversational parameters (reloadable in Program tab)</li>
<li><b>.ngc</b> — G-code output (loadable in Run tab)</li>
</ul>
"""),
        ("Run Tab", """
<h2>Run Tab</h2>
<p>Load, preview, and execute G-code programs on the machine.</p>
<h3>Loading a Program</h3>
<ol>
<li>Click <b>Open</b> to select a .ngc file</li>
<li>Click <b>Preview</b> to render the toolpath on the graph</li>
<li>Use the sim playback controls (Play/Step/Slider) to walk through the program</li>
</ol>
<h3>Executing a Program</h3>
<ol>
<li>Ensure the machine is ON and homed</li>
<li>Click <b>Cycle Start</b> to run from line 1</li>
<li>Or set a line number and click <b>Run From</b></li>
<li>Use <b>Pause</b> to hold, <b>Stop</b> to abort</li>
</ol>
<p>During execution, the G-code panel highlights the current line and the
tool dot tracks the machine position in real time.</p>
"""),
        ("Tools Tab", """
<h2>Tools Tab</h2>
<p>Manage the tool table — define tool geometry for accurate toolpath generation.</p>
<h3>Key Fields</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Field</th><th>Description</th></tr>
<tr><td>Tool #</td><td>Position in the quick-change tool post (T1–T6)</td></tr>
<tr><td>X Offset</td><td>Tool tip X position relative to reference (diameter)</td></tr>
<tr><td>Z Offset</td><td>Tool tip Z position relative to reference</td></tr>
<tr><td>Nose Radius</td><td>Insert corner radius (affects finish quality)</td></tr>
<tr><td>Orientation</td><td>Q1–Q8 quadrant (determines which side cuts)</td></tr>
</table>
<h3>Tool Orientation (Q Codes)</h3>
<p>For a standard RH turning tool cutting OD toward the chuck: <b>Q2</b><br>
For a boring bar cutting ID toward the chuck: <b>Q6</b></p>
"""),
        ("Edit Tab", """
<h2>Edit Tab</h2>
<p>G-code text editor with syntax highlighting and toolpath preview.</p>
<h3>Features</h3>
<ul>
<li>Full text editing of G-code</li>
<li>Click <b>Preview</b> to parse and visualize the toolpath</li>
<li>Sim playback with line-by-line highlighting</li>
<li>Save edited G-code as .ngc files</li>
</ul>
<p>The Edit tab automatically receives G-code when you click Generate in the Program tab.</p>
"""),
        ("Setup Tab", """
<h2>Setup Tab</h2>
<p>Machine commissioning and diagnostics. Three sub-tabs:</p>
<h3>HAL Monitor</h3>
<p>Browse all HAL pins in a tree view. Filter by category (PID, Stepgen, Encoders, MPG).
Double-click a pin to add it to the watch list for live value monitoring.</p>
<h3>Tuning</h3>
<p>Real-time following error graph, PID parameter editor. Workflow:</p>
<ol>
<li>Load from INI — populates fields with current config</li>
<li>Watch the error graph while jogging</li>
<li>Adjust PID gains (P, FF1, deadband are the main ones)</li>
<li>Apply Live — pushes to HAL immediately</li>
<li>Save to INI — persists for next startup</li>
</ol>
<h3>Commission</h3>
<p>Guided 9-step checklist for initial machine validation.</p>
"""),
    ],
    "G-code Reference": [
        ("Overview", """
<h2>G-code Reference</h2>
<p>For the complete, searchable G-code and M-code reference, switch to the
<b>G-code Reference</b> sub-tab at the bottom of this Help panel.</p>
<p>It contains all valid LinuxCNC codes with descriptions, searchable by
code number, keyword, or category.</p>
<h3>Quick Tips</h3>
<ul>
<li>LinuxCNC uses <b>G18</b> (XZ plane) by default for lathes</li>
<li>This machine uses <b>G7</b> (diameter mode) — X values are diameters</li>
<li>Feed mode <b>G95</b> (per revolution) is standard for lathe turning</li>
<li>Arc centers (I/K) are <b>incremental</b> by default (G91.1)</li>
<li>Tool format: <b>T0101</b> = tool 1, offset 1</li>
</ul>
"""),
    ],
    "Machine Info": [
        ("Hardware", """
<h2>Machine Hardware</h2>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Component</th><th>Details</th></tr>
<tr><td>Controller</td><td>Mesa 7i96s (Ethernet FPGA) + 7i85s daughter card</td></tr>
<tr><td>Steppers</td><td>UIRobot UIM8696PM closed-loop integrated (48V)</td></tr>
<tr><td>Linear Encoders</td><td>Sino KA300/KA500, 5µm resolution (5080 counts/inch)</td></tr>
<tr><td>Spindle</td><td>Manual (no VFD), 1000 PPR rotary encoder</td></tr>
<tr><td>MPG Handwheels</td><td>2× (100 PPR), X on 7i85s TB2, Z on 7i85s TB3</td></tr>
<tr><td>Tool Post</td><td>Quick-change, 6 positions</td></tr>
</table>
"""),
        ("Axis Limits", """
<h2>Axis Travel and Limits</h2>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Parameter</th><th>X Axis</th><th>Z Axis</th></tr>
<tr><td>Travel</td><td>0 – 4.25" (diameter)</td><td>0 – 23.5"</td></tr>
<tr><td>Max Velocity</td><td>1.7 in/s</td><td>0.20 in/s *</td></tr>
<tr><td>Max Acceleration</td><td>10.0 in/s²</td><td>10.0 in/s²</td></tr>
<tr><td>Encoder Resolution</td><td>0.0002" (5µm)</td><td>0.0002" (5µm)</td></tr>
<tr><td>Home Position</td><td>4.25" (full retract)</td><td>0.0" (near headstock)</td></tr>
</table>
<p>* Z velocity is temporarily capped at 0.20 in/s pending motor investigation.
The UIM8696PM motor ceiling on Z is ~0.25 in/s.</p>
"""),
        ("PID Tuning", """
<h2>PID Tuning Reference</h2>
<h3>Current Settings</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Parameter</th><th>X Axis</th><th>Z Axis</th></tr>
<tr><td>P</td><td>125</td><td>100</td></tr>
<tr><td>I</td><td>0</td><td>0</td></tr>
<tr><td>D</td><td>0.001</td><td>0.0001</td></tr>
<tr><td>FF1</td><td>1.0</td><td>1.0</td></tr>
<tr><td>Deadband</td><td>0.0002"</td><td>0.0002"</td></tr>
<tr><td>FERROR</td><td>0.020"</td><td>0.500"</td></tr>
<tr><td>MIN_FERROR</td><td>0.005"</td><td>0.100"</td></tr>
</table>
<h3>Tuning Rules for Closed-Loop Steppers</h3>
<ul>
<li><b>FF1 = 1.0</b> — does the heavy lifting (velocity feedforward)</li>
<li><b>P = 50–200</b> — light proportional correction</li>
<li><b>I = 0</b> — not needed for steppers</li>
<li><b>D = 0.0001–0.001</b> — small damping if needed</li>
<li><b>Deadband = 1 encoder count</b> (0.0002") — prevents hunting</li>
</ul>
<h3>Diagnostic Patterns</h3>
<ul>
<li><b>Hunting at rest</b> → Deadband too small or P too high</li>
<li><b>FERROR on fast jog only</b> → Motor velocity ceiling hit</li>
<li><b>Instant FERROR on first click</b> → Sign mismatch (STEP_SCALE vs ENCODER_SCALE)</li>
<li><b>FERROR on direction reversal</b> → Mechanical backlash</li>
</ul>
"""),
    ],
    "Troubleshooting": [
        ("Common Issues", """
<h2>Common Issues</h2>
<h3>Machine won't come out of E-Stop</h3>
<ul>
<li>Physical E-stop button must be released/twisted</li>
<li>Click "Reset E-Stop" in the GUI status bar</li>
<li>Then click "Machine On"</li>
</ul>
<h3>Following Error on Machine On</h3>
<p>Usually means encoder direction is wrong. Quick fix: negate ENCODER_SCALE
in the INI file for the affected joint. See Setup → Tuning for live diagnostics.</p>
<h3>MPG doesn't move the axis</h3>
<ol>
<li>Machine must be ON (not just E-Stop Reset)</li>
<li>Check encoder counts in Setup → HAL Monitor</li>
<li>Verify jog-enable is TRUE</li>
<li>Check jog scale is > 0</li>
</ol>
<h3>Program won't start</h3>
<ul>
<li>Machine must be ON and homed</li>
<li>A program file must be loaded (Open in Run tab)</li>
<li>Interpreter must be IDLE (not paused from a previous run — click Stop first)</li>
</ul>
<h3>Preview shows no toolpath</h3>
<ul>
<li>The G-code must contain motion commands (G00/G01/G02/G03 with X or Z)</li>
<li>Check for parse errors in the status bar</li>
<li>Try the Edit tab's Preview button for more detailed error messages</li>
</ul>
"""),
        ("Error Messages", """
<h2>Error Messages</h2>
<h3>LinuxCNC Errors</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Error</th><th>Cause</th><th>Fix</th></tr>
<tr><td>Joint N following error</td><td>Motor can't keep up with commanded position</td>
    <td>Reduce MAX_VEL or check for mechanical binding</td></tr>
<tr><td>Joint N on limit switch</td><td>Axis hit a soft limit</td>
    <td>Jog away from the limit, check program coordinates</td></tr>
<tr><td>Cannot unhome while moving</td><td>Tried to unhome during motion</td>
    <td>Wait for motion to stop, then unhome</td></tr>
<tr><td>Cannot jog: not homed</td><td>NO_FORCE_HOMING=0 and axis not homed</td>
    <td>Home the axis first, or set NO_FORCE_HOMING=1 in INI</td></tr>
</table>
<h3>CAM Engine Errors</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Error</th><th>Cause</th><th>Fix</th></tr>
<tr><td>Profile not closed</td><td>Segments don't form a closed contour</td>
    <td>Check that the last segment endpoint matches the first</td></tr>
<tr><td>Tool cannot reach feature</td><td>Tool geometry prevents access</td>
    <td>Use a smaller nose radius or different orientation</td></tr>
<tr><td>Gouge detected</td><td>Toolpath would cut into finished part</td>
    <td>Increase finish allowance or adjust profile</td></tr>
</table>
"""),
    ],
}


# =============================================================================
# Help Tab Widget
# =============================================================================

class HelpTab(QWidget):
    """In-app documentation browser with topic tree and G-code reference."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sub-tabs: Documentation + G-code Reference
        self._sub_tabs = QTabWidget()
        self._sub_tabs.setDocumentMode(True)
        self._sub_tabs.setTabPosition(QTabWidget.South)

        # Tab 1: Documentation browser
        self._docs_widget = DocsBrowserWidget()
        self._sub_tabs.addTab(self._docs_widget, "Documentation")

        # Tab 2: G-code Reference (searchable table)
        self._gcode_ref = GCodeReferenceWidget()
        self._sub_tabs.addTab(self._gcode_ref, "G-code Reference")

        layout.addWidget(self._sub_tabs)


# =============================================================================
# G-code Reference Widget — Searchable table of all codes
# =============================================================================

class GCodeReferenceWidget(QWidget):
    """Exhaustive, searchable G-code and M-code reference table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_codes = get_all_codes()
        self._build_ui()
        self._populate_table(self._all_codes)
        self._connect_signals()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        lbl = QLabel("Search:")
        lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        filter_row.addWidget(lbl)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Type code or keyword (e.g. 'G2', 'arc', 'spindle')...")
        self._search.setFixedHeight(36)
        filter_row.addWidget(self._search, stretch=1)

        cat_lbl = QLabel("Category:")
        cat_lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        filter_row.addWidget(cat_lbl)

        self._category_filter = QComboBox()
        self._category_filter.setFixedHeight(36)
        self._category_filter.setFixedWidth(160)
        self._category_filter.addItem("All")
        # Collect unique categories
        categories = sorted(set(c[1] for c in self._all_codes))
        for cat in categories:
            self._category_filter.addItem(cat)
        filter_row.addWidget(self._category_filter)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {COLORS['text_disabled']}; min-width: 80px;"
        )
        filter_row.addWidget(self._count_label)

        layout.addLayout(filter_row)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Code", "Category", "Description", "Example"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setWordWrap(True)
        self._table.setStyleSheet(
            f"QTableWidget {{ font-family: {FONTS['ui_family']}, {FONTS['fallback_sans']};"
            f" font-size: {FONTS['ui_size']}pt; }}"
            f"QTableWidget::item {{ padding: 4px 8px; }}"
        )

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setMinimumSectionSize(80)

        layout.addWidget(self._table, stretch=1)

    def _populate_table(self, codes):
        """Fill the table with the given code list."""
        self._table.setRowCount(len(codes))
        for row, entry in enumerate(codes):
            code, category, description = entry[0], entry[1], entry[2]
            example = entry[3] if len(entry) > 3 else ""

            code_item = QTableWidgetItem(code)
            code_item.setFont(QFont(FONTS['mono_family'], FONTS['ui_size']))
            code_item.setForeground(QColor(COLORS['status_info']))
            self._table.setItem(row, 0, code_item)

            cat_item = QTableWidgetItem(category)
            cat_item.setForeground(QColor(COLORS['text_secondary']))
            self._table.setItem(row, 1, cat_item)

            desc_item = QTableWidgetItem(description)
            self._table.setItem(row, 2, desc_item)

            ex_item = QTableWidgetItem(example)
            ex_item.setFont(QFont(FONTS['mono_family'], FONTS['small_size']))
            ex_item.setForeground(QColor(COLORS['text_subtle']))
            self._table.setItem(row, 3, ex_item)

        self._table.resizeRowsToContents()
        self._count_label.setText(f"{len(codes)} codes")

    def _connect_signals(self):
        self._search.textChanged.connect(self._apply_filter)
        self._category_filter.currentTextChanged.connect(self._apply_filter)

    def _apply_filter(self, _=None):
        """Filter table by search text and category."""
        text = self._search.text().lower()
        category = self._category_filter.currentText()

        filtered = []
        for entry in self._all_codes:
            code, cat, desc = entry[0], entry[1], entry[2]
            example = entry[3] if len(entry) > 3 else ""
            # Category filter
            if category != "All" and cat != category:
                continue
            # Text filter — search in code, category, description, and example
            if text and (text not in code.lower() and
                         text not in cat.lower() and
                         text not in desc.lower() and
                         text not in example.lower()):
                continue
            filtered.append(entry)

        self._populate_table(filtered)


# =============================================================================
# Documentation Browser Widget (original topic tree + content)
# =============================================================================

class DocsBrowserWidget(QWidget):
    """Topic tree + HTML content browser for documentation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._populate_tree()
        self._connect_signals()

        # Show the first topic by default
        first = self._tree.topLevelItem(0)
        if first and first.childCount() > 0:
            child = first.child(0)
            self._tree.setCurrentItem(child)
            self._on_topic_selected(child, 0)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Search bar
        search_row = QHBoxLayout()
        lbl = QLabel("Search:")
        lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        search_row.addWidget(lbl)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Type to filter topics...")
        self._search.setFixedHeight(36)
        search_row.addWidget(self._search, stretch=1)
        layout.addLayout(search_row)

        # Splitter: tree (left) + content (right)
        splitter = QSplitter(Qt.Horizontal)

        # Left: topic tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(200)
        self._tree.setMaximumWidth(300)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background-color: {COLORS['bg_panel']};"
            f" border: 1px solid {COLORS['border_normal']}; }}"
            f"QTreeWidget::item {{ padding: 4px; min-height: 28px; }}"
            f"QTreeWidget::item:selected {{ background-color: {COLORS['bg_surface']}; }}"
        )
        splitter.addWidget(self._tree)

        # Right: content browser
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            f"QTextBrowser {{ background-color: {COLORS['bg_panel']};"
            f" color: {COLORS['text_primary']};"
            f" border: 1px solid {COLORS['border_normal']};"
            f" padding: 12px;"
            f" font-family: {FONTS['ui_family']}, {FONTS['fallback_sans']};"
            f" font-size: {FONTS['ui_size']}pt; }}"
        )
        splitter.addWidget(self._browser)

        splitter.setSizes([220, 780])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        layout.addWidget(splitter, stretch=1)

    def _populate_tree(self):
        """Build the topic tree from HELP_CONTENT."""
        self._topic_map: Dict[str, str] = {}  # item_id → html content

        for category, topics in HELP_CONTENT.items():
            cat_item = QTreeWidgetItem(self._tree)
            cat_item.setText(0, category)
            cat_item.setExpanded(True)
            font = cat_item.font(0)
            font.setBold(True)
            cat_item.setFont(0, font)

            for title, html in topics:
                topic_item = QTreeWidgetItem(cat_item)
                topic_item.setText(0, title)
                item_id = f"{category}::{title}"
                topic_item.setData(0, Qt.UserRole, item_id)
                self._topic_map[item_id] = html

    def _connect_signals(self):
        self._tree.itemClicked.connect(self._on_topic_selected)
        self._search.textChanged.connect(self._on_search)

    def _on_topic_selected(self, item, column):
        """Display the selected topic's content."""
        item_id = item.data(0, Qt.UserRole)
        if item_id and item_id in self._topic_map:
            html = self._topic_map[item_id]
            # Wrap in styled container
            styled = f"""
            <style>
                body {{ color: {COLORS['text_primary']}; }}
                h2 {{ color: {COLORS['status_info']}; margin-top: 0; }}
                h3 {{ color: {COLORS['text_secondary']}; }}
                table {{ border-collapse: collapse; margin: 8px 0; }}
                th {{ background-color: {COLORS['bg_surface']}; padding: 6px 10px;
                      color: {COLORS['text_secondary']}; text-align: left; }}
                td {{ padding: 6px 10px; border: 1px solid {COLORS['border_normal']}; }}
                code {{ background-color: {COLORS['bg_surface']}; padding: 2px 4px;
                        border-radius: 3px; font-family: {FONTS['mono_family']}; }}
                li {{ margin: 4px 0; }}
            </style>
            {html}
            """
            self._browser.setHtml(styled)

    def _on_search(self, text: str):
        """Filter topics by search text."""
        text_lower = text.lower()
        for i in range(self._tree.topLevelItemCount()):
            cat_item = self._tree.topLevelItem(i)
            any_visible = False
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                item_id = child.data(0, Qt.UserRole)
                # Search in title and content
                title_match = text_lower in child.text(0).lower()
                content_match = (item_id and text_lower in
                                 self._topic_map.get(item_id, "").lower())
                visible = not text or title_match or content_match
                child.setHidden(not visible)
                if visible:
                    any_visible = True
            cat_item.setHidden(not any_visible)
            if any_visible:
                cat_item.setExpanded(True)
