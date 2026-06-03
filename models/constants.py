"""System constants for Industry CAM Engine.

All tolerance values, densification parameters, and arc acceptance windows.
These are the single source of truth for numeric thresholds used throughout the engine.
"""

# System operating tolerance — closure gaps, interval merging, point comparisons
TOLERANCE: float = 0.0005  # inches

# Area threshold for oracle coverage/gouge checks
TOLERANCE_SQ: float = TOLERANCE ** 2  # 0.00000025 sq in

# LinuxCNC's IJK arc acceptance window
CENTER_ARC_RADIUS_TOLERANCE_INCH: float = 0.00283

# LinuxCNC's R-format arc tolerance
RADIUS_TOLERANCE: float = 0.00005

# Zone shading tessellation maximum chord error
DISPLAY_TOLERANCE: float = 0.001  # inches

# Shapely polygon maximum chord error (cos_limit=0.9999)
DENSIFICATION_ERROR: float = 0.000025  # inches

# Adaptive densification cosine limit for Shapely polygons
SHAPELY_COS_LIMIT: float = 0.9999

# Adaptive densification cosine limit for display
DISPLAY_COS_LIMIT: float = 0.999

# Maximum recursion depth for adaptive densification (Shapely)
MAX_DENSIFICATION_DEPTH: int = 12

# Display densification max depth
MAX_DISPLAY_DEPTH: int = 10

# Quadrant arc edge decomposition chord error tolerance (inches)
# Used by finish planner when decomposing elliptical/spline edges into G2/G3 arcs
QUADRANT_CHORD_ERROR: float = 0.0001  # 0.1 thou
