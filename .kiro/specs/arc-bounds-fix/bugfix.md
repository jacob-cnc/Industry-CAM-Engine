# Bugfix Requirements Document

## Introduction

Arc segments in the Profile Segments table produce geometry that exceeds the X bounds defined by the start and end points. When a user defines an arc from X_start to X_end, the computed arc path overshoots beyond `max(X_start, X_end)` or undershoots below `min(X_start, X_end)`. This occurs because the arc center selection logic picks the wrong center (producing the major arc path instead of the minor arc), and the arc helper functions suggest radius values without verifying that the resulting arc stays within the X bounds of the endpoints.

The impact is that arcs render incorrectly in the preview graph, generate invalid toolpaths in the finish planner, and the helper suggestions guide users toward geometrically invalid configurations that would gouge the part.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an arc segment is defined with endpoints where the chord is nearly equal to the diameter (2×radius), and the cross-product center selection picks the center on the far side of the chord THEN the system computes the major arc path (>180°) which exceeds the X bounds of the start and end points

1.2 WHEN a positive radius (CW) arc is defined going from a smaller X_start to a larger X_end (e.g., X=0.5 dia to X=0.75 dia) and the selected center produces an arc that peaks above X_end THEN the system renders and plans an arc that overshoots beyond X_end in the positive X direction

1.3 WHEN a negative radius (CCW) arc is defined going from a smaller X_start to a larger X_end and the selected center produces an arc that dips below X_start THEN the system renders and plans an arc that undershoots below X_start in the negative X direction

1.4 WHEN the arc helper computes a suggested minimum radius via `compute_min_radius()` THEN the system suggests a radius value without checking whether the resulting arc would stay within the X bounds [min(X_start, X_end), max(X_start, X_end)]

1.5 WHEN the pre-planning validator checks an arc segment THEN the system only validates that the radius is geometrically sufficient (radius >= chord/2) but does not reject arcs whose computed path exceeds the X bounds of the endpoints

### Expected Behavior (Correct)

2.1 WHEN an arc segment is defined with two endpoints and a signed radius THEN the system SHALL select the arc center that produces a path staying within the X bounds [min(X_start, X_end), max(X_start, X_end)] (the minor/bounded arc)

2.2 WHEN a positive radius (CW) arc is defined going from X_start to X_end THEN the system SHALL compute an arc whose maximum X value does not exceed max(X_start, X_end) and whose minimum X value does not go below min(X_start, X_end)

2.3 WHEN a negative radius (CCW) arc is defined going from X_start to X_end THEN the system SHALL compute an arc whose maximum X value does not exceed max(X_start, X_end) and whose minimum X value does not go below min(X_start, X_end)

2.4 WHEN the arc helper computes suggested radius values THEN the system SHALL only suggest radii that produce arcs bounded within [min(X_start, X_end), max(X_start, X_end)], rejecting or clamping values that would cause the arc to exceed these bounds

2.5 WHEN the pre-planning validator checks an arc segment THEN the system SHALL reject arc configurations where the computed arc peak (extremum in X) would exceed the X bounds of the start and end points, providing an actionable error message

### Unchanged Behavior (Regression Prevention)

3.1 WHEN an arc segment has a radius significantly larger than chord/2 (producing a shallow arc well within bounds) THEN the system SHALL CONTINUE TO compute and render the arc correctly without any change in behavior

3.2 WHEN an arc segment connects two points at the same X value (vertical chord, e.g., X=1.0 to X=1.0 with different Z) THEN the system SHALL CONTINUE TO render the convex bulge arc correctly (this case is inherently bounded since start and end X are equal and the arc bulges outward then returns)

3.3 WHEN a LINE segment is defined THEN the system SHALL CONTINUE TO render and plan it as a straight line between endpoints without any arc validation applied

3.4 WHEN the radius is exactly chord/2 (semicircle case) and the arc stays within X bounds THEN the system SHALL CONTINUE TO accept and render the semicircular arc correctly

3.5 WHEN the pre-planning validator detects a radius smaller than chord/2 THEN the system SHALL CONTINUE TO report the existing "radius too small" error with the same message format and alternatives

---

## Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type ArcSegment {x_start_r, z_start, x_end_r, z_end, radius, is_cw}
  OUTPUT: boolean

  // Compute the arc center using the current cross-product selection
  center ← selectCenter(X.x_start_r, X.z_start, X.x_end_r, X.z_end, |X.radius|, X.is_cw)
  
  // Compute the arc extremum in X (the peak/valley of the arc path)
  x_min_bound ← min(X.x_start_r, X.x_end_r)
  x_max_bound ← max(X.x_start_r, X.x_end_r)
  arc_x_extremum ← computeArcExtremumX(center, |X.radius|, X.x_start_r, X.z_start, X.x_end_r, X.z_end)
  
  // Bug triggers when the arc exceeds the X bounds of the endpoints
  RETURN arc_x_extremum > x_max_bound + TOLERANCE OR arc_x_extremum < x_min_bound - TOLERANCE
END FUNCTION
```

## Property Specification

```pascal
// Property: Fix Checking — Arc stays within X bounds
FOR ALL X WHERE isBugCondition(X) DO
  center' ← selectCenter'(X.x_start_r, X.z_start, X.x_end_r, X.z_end, |X.radius|, X.is_cw)
  arc_points ← interpolateArc(center', |X.radius|, X.x_start_r, X.z_start, X.x_end_r, X.z_end)
  
  x_min_bound ← min(X.x_start_r, X.x_end_r)
  x_max_bound ← max(X.x_start_r, X.x_end_r)
  
  FOR EACH point IN arc_points DO
    ASSERT point.x >= x_min_bound - TOLERANCE
    ASSERT point.x <= x_max_bound + TOLERANCE
  END FOR
END FOR
```

```pascal
// Property: Preservation Checking — Non-buggy arcs unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```
