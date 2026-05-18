"""Color system for Industry CAM Engine GUI.

Single source of truth for all colors used in the application.
All widgets reference this dictionary — never hardcoded hex values.

See .kiro/steering/gui-color-system.md for design rationale.
"""

COLORS = {
    # Backgrounds
    "bg_base": "#263F58",
    "bg_panel": "#2E4B66",
    "bg_surface": "#365774",
    "bg_status_bar": "#1E3548",

    # Text
    "text_primary": "#F0F4F8",
    "text_secondary": "#B7C6D4",
    "text_disabled": "#7D9AB3",
    "text_subtle": "#9AAFC2",

    # Borders & Structure
    "border_normal": "#7D9AB3",
    "border_focused": "#7BB9EE",
    "border_error": "#B85A6A",

    # Actions
    "btn_primary": "#3373C4",
    "btn_primary_hover": "#5494DA",
    "btn_generate": "#7AB5A8",
    "btn_danger": "#8B2030",

    # Status
    "status_ok": "#5E9E91",
    "status_warning": "#E56E72",
    "status_error": "#8B2030",
    "status_info": "#7BB9EE",

    # Graph
    "graph_bg": "#263F58",
    "graph_grid": "#365774",
    "graph_axis": "#C8C8C8",
    "graph_crosshair": "#A0A0A080",
    "graph_profile": "#F0F4F8",
    "graph_stock": "#7D9AB3",
    "graph_centerline": "#9AAFC280",
    "graph_feed": "#5E9E91",
    "graph_rapid": "#E56E72",
    "graph_arc": "#5494DA",
    "graph_zone_finished": "#6B8EA850",
    "graph_zone_material": "#C0404060",
    "graph_zone_true_face": "#A0353560",
    "graph_zone_allowance": "#D4A84060",
    "graph_swept_active": "#7AB5A840",
    "graph_warning_region": "#E56E7233",
    "graph_roundtrip": "#A8D8CC80",
    "graph_tool_dot": "#FFFFFF",

    # Tabs
    "tab_active": "#5E9E91",
    "tab_inactive": "#7D9AB3",

    # Purple/Violet Accents
    "purple_pale": "#C7AFF7",
    "purple_light": "#A68CEE",
    "purple_mid": "#8569E4",
    "purple_dark": "#6B39BC",
    "purple_deep": "#510993",
}

# Font configuration
FONTS = {
    "ui_family": "Inter",
    "mono_family": "JetBrains Mono",
    "fallback_sans": "Segoe UI, DejaVu Sans, sans-serif",
    "fallback_mono": "Consolas, DejaVu Sans Mono, monospace",
    "dro_size": 24,
    "ui_size": 10,
    "code_size": 11,
    "small_size": 9,
}

# Touch target sizes (minimum 44px per WCAG/Apple HIG)
TOUCH = {
    "target_min": 44,       # Minimum touch target (px)
    "slider_handle": 36,    # Slider thumb diameter (px)
    "splitter_width": 12,   # Splitter drag handle width (px)
    "scrollbar_width": 20,  # Scrollbar track width (px)
    "row_height": 44,       # Table/list row minimum height (px)
    "button_height": 44,    # Button minimum height (px)
    "margin_between": 8,    # Minimum gap between touch targets (px)
}

# Stylesheet template for the application
STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLORS['bg_base']};
    color: {COLORS['text_primary']};
    font-family: {FONTS['ui_family']}, {FONTS['fallback_sans']};
    font-size: {FONTS['ui_size']}pt;
}}

QTabBar::tab {{
    background-color: {COLORS['bg_panel']};
    color: {COLORS['tab_inactive']};
    padding: 8px 16px;
    min-width: 60px;
    min-height: 44px;
    border: none;
}}

QTabBar::tab:selected {{
    background-color: {COLORS['bg_surface']};
    color: {COLORS['tab_active']};
    border-bottom: 2px solid {COLORS['tab_active']};
}}

QPushButton {{
    background-color: {COLORS['btn_primary']};
    color: {COLORS['text_primary']};
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    min-height: 44px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {COLORS['btn_primary_hover']};
}}

QPushButton:pressed {{
    background-color: {COLORS['btn_primary']};
}}

QPushButton#generateBtn {{
    background-color: {COLORS['btn_generate']};
}}

QPushButton#dangerBtn {{
    background-color: {COLORS['btn_danger']};
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {COLORS['bg_panel']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_normal']};
    border-radius: 3px;
    padding: 6px;
    min-height: 36px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {COLORS['border_focused']};
}}

QLabel {{
    color: {COLORS['text_secondary']};
}}

QTableWidget {{
    background-color: {COLORS['bg_panel']};
    color: {COLORS['text_primary']};
    gridline-color: {COLORS['border_normal']};
    border: none;
}}

QTableWidget::item:selected {{
    background-color: {COLORS['bg_surface']};
}}

QHeaderView::section {{
    background-color: {COLORS['bg_surface']};
    color: {COLORS['text_secondary']};
    padding: 6px;
    border: none;
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {COLORS['bg_panel']};
    width: 20px;
    height: 20px;
}}

QScrollBar::handle {{
    background-color: {COLORS['border_normal']};
    border-radius: 6px;
    min-height: 44px;
    min-width: 44px;
    margin: 2px;
}}

QScrollBar::handle:hover {{
    background-color: {COLORS['text_disabled']};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}

QSplitter::handle {{
    background-color: {COLORS['border_normal']};
}}

QSplitter::handle:horizontal {{
    width: 12px;
    margin: 0px 2px;
    border-radius: 3px;
}}

QSplitter::handle:vertical {{
    height: 12px;
    margin: 2px 0px;
    border-radius: 3px;
}}

QSplitter::handle:hover {{
    background-color: {COLORS['text_disabled']};
}}

QSlider::groove:horizontal {{
    border: 1px solid {COLORS['border_normal']};
    height: 10px;
    background: {COLORS['bg_panel']};
    border-radius: 5px;
}}

QSlider::handle:horizontal {{
    background: {COLORS['btn_primary']};
    border: 2px solid {COLORS['border_focused']};
    width: 36px;
    height: 36px;
    margin: -14px 0;
    border-radius: 18px;
}}

QSlider::handle:horizontal:hover {{
    background: {COLORS['btn_primary_hover']};
}}

QSlider::groove:vertical {{
    border: 1px solid {COLORS['border_normal']};
    width: 10px;
    background: {COLORS['bg_panel']};
    border-radius: 5px;
}}

QSlider::handle:vertical {{
    background: {COLORS['btn_primary']};
    border: 2px solid {COLORS['border_focused']};
    width: 36px;
    height: 36px;
    margin: 0 -14px;
    border-radius: 18px;
}}

QSlider::handle:vertical:hover {{
    background: {COLORS['btn_primary_hover']};
}}

QHeaderView::section {{
    background-color: {COLORS['bg_surface']};
    color: {COLORS['text_secondary']};
    padding: 8px;
    min-height: 36px;
    border: none;
}}
"""
