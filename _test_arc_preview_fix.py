"""Test the arc preview fix with the known-good case from the handoff.

Expected: From (1.0 dia, -0.5) to (1.0 dia, -1.5) with R=-1.0 (CCW)
Should produce a convex bulge outward (toward larger X / away from centerline).
The engine's G-code confirms center at (-0.7321 dia, -1.0) = (-0.366 radius, -1.0).
"""
import math

def test_arc_preview(prev_x_r, prev_z, x_r, z, radius, label=""):
    """Replicate the fixed _update_preview arc logic."""
    print(f"\n{'='*60}")
    print(f"Test: {label}")
    print(f"  From: X_r={prev_x_r:.4f} (dia={prev_x_r*2:.4f}), Z={prev_z:.4f}")
    print(f"  To:   X_r={x_r:.4f} (dia={x_r*2:.4f}), Z={z:.4f}")
    print(f"  Radius: {radius:.4f} ({'CW' if radius > 0 else 'CCW'})")
    print(f"{'='*60}")

    r_abs = abs(radius)
    is_cw = radius > 0

    dx_r = x_r - prev_x_r
    dz = z - prev_z
    chord = math.sqrt(dx_r * dx_r + dz * dz)
    print(f"Chord: {chord:.4f}")

    if chord < 0.0001 or r_abs < chord / 2.0 - 1e-9:
        print("DEGENERATE — would draw as line")
        return

    if r_abs < chord / 2.0:
        r_abs = chord / 2.0

    mid_x_r = (prev_x_r + x_r) / 2.0
    mid_z = (prev_z + z) / 2.0
    h = math.sqrt(max(0.0, r_abs * r_abs - (chord / 2.0) ** 2))

    # Unit perpendicular to chord (rotated 90° CCW from chord direction)
    px = -dz / chord
    pz = dx_r / chord

    # CW → center on RIGHT of chord → positive offset (verified against engine)
    # CCW → center on LEFT of chord → negative offset (verified against engine)
    if is_cw:
        cx_r = mid_x_r + h * px
        cz_arc = mid_z + h * pz
    else:
        cx_r = mid_x_r - h * px
        cz_arc = mid_z - h * pz

    print(f"Center: X_r={cx_r:.4f} (dia={cx_r*2:.4f}), Z={cz_arc:.4f}")

    # Angles and [-pi, pi] normalization
    angle_start = math.atan2(prev_z - cz_arc, prev_x_r - cx_r)
    angle_end = math.atan2(z - cz_arc, x_r - cx_r)
    r_display = math.sqrt((prev_x_r - cx_r) ** 2 + (prev_z - cz_arc) ** 2)

    diff = angle_end - angle_start
    if diff > math.pi:
        diff -= 2 * math.pi
    elif diff < -math.pi:
        diff += 2 * math.pi

    print(f"r_display: {r_display:.4f}")
    print(f"angle_start: {math.degrees(angle_start):.1f} deg")
    print(f"angle_end: {math.degrees(angle_end):.1f} deg")
    print(f"Sweep (normalized): {math.degrees(diff):.1f} deg")

    # Sample midpoint
    mid_angle = angle_start + diff * 0.5
    mid_arc_x = cx_r + r_display * math.cos(mid_angle)
    mid_arc_z = cz_arc + r_display * math.sin(mid_angle)
    print(f"\nArc midpoint: X_r={mid_arc_x:.4f} (dia={mid_arc_x*2:.4f}), Z={mid_arc_z:.4f}")

    # Check direction
    if mid_arc_x > max(prev_x_r, x_r) + 0.001:
        print("✓ Arc bulges OUTWARD (away from centerline) — convex on OD part")
    elif mid_arc_x < min(prev_x_r, x_r) - 0.001:
        print("✓ Arc bulges INWARD (toward centerline) — concave on OD part")
    else:
        print("  Arc stays between start/end X values")

    # Verify endpoints
    start_pt_x = cx_r + r_display * math.cos(angle_start)
    start_pt_z = cz_arc + r_display * math.sin(angle_start)
    end_pt_x = cx_r + r_display * math.cos(angle_start + diff)
    end_pt_z = cz_arc + r_display * math.sin(angle_start + diff)
    print(f"\nEndpoint verification:")
    print(f"  Computed start: ({start_pt_x:.4f}, {start_pt_z:.4f}) vs actual ({prev_x_r:.4f}, {prev_z:.4f})")
    print(f"  Computed end:   ({end_pt_x:.4f}, {end_pt_z:.4f}) vs actual ({x_r:.4f}, {z:.4f})")
    start_err = math.sqrt((start_pt_x - prev_x_r)**2 + (start_pt_z - prev_z)**2)
    end_err = math.sqrt((end_pt_x - x_r)**2 + (end_pt_z - z)**2)
    if start_err < 0.001 and end_err < 0.001:
        print("  ✓ Endpoints match")
    else:
        print(f"  ✗ ENDPOINT ERROR: start_err={start_err:.6f}, end_err={end_err:.6f}")


# Test 1: The known-good case from the handoff
# From (1.0 dia, -0.5) to (1.0 dia, -1.5) with R=-1.0 (CCW)
# Engine confirms center at (-0.7321 dia, -1.0) and arc bulges outward
test_arc_preview(0.5, -0.5, 0.5, -1.5, -1.0,
    "CCW arc R=-1.0, same X endpoints (handoff case)")

# Test 2: CW arc with same geometry (should bulge inward)
test_arc_preview(0.5, -0.5, 0.5, -1.5, 1.0,
    "CW arc R=+1.0, same X endpoints (opposite direction)")

# Test 3: Small CCW arc (quarter circle type)
test_arc_preview(0.5, 0.0, 0.75, -0.25, -0.25,
    "CCW arc R=-0.25, corner radius")

# Test 4: CW arc (quarter circle type)
test_arc_preview(0.5, 0.0, 0.75, -0.25, 0.25,
    "CW arc R=+0.25, corner radius")

# Test 5: Semicircle (radius = chord/2)
test_arc_preview(0.5, -0.5, 0.5, -1.5, -0.5,
    "CCW semicircle R=-0.5 (radius = chord/2)")
