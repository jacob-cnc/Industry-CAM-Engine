"""Trace through the exact arc from the screenshot to find the horizontal line bug."""
import math

# Exact values from the screenshot segments
prev_x_r = 0.5    # segment 4: 1.0 dia / 2
prev_z = -0.5
x_r = 0.625       # segment 5: 1.25 dia / 2
z = -1.0
radius = -1.0     # CCW

r_abs = abs(radius)
is_cw = radius > 0

dx_r = x_r - prev_x_r
dz = z - prev_z
chord = math.sqrt(dx_r * dx_r + dz * dz)
print(f"dx_r={dx_r}, dz={dz}, chord={chord:.6f}")

mid_x_r = (prev_x_r + x_r) / 2.0
mid_z = (prev_z + z) / 2.0
h = math.sqrt(max(0.0, r_abs * r_abs - (chord / 2.0) ** 2))
print(f"mid=({mid_x_r}, {mid_z}), h={h:.6f}")

px = -dz / chord
pz = dx_r / chord
print(f"perp=({px:.6f}, {pz:.6f})")

# CCW: center = mid - h*perp
cx_r = mid_x_r - h * px
cz_arc = mid_z - h * pz
print(f"center=({cx_r:.6f}, {cz_arc:.6f})")

angle_start = math.atan2(prev_z - cz_arc, prev_x_r - cx_r)
angle_end = math.atan2(z - cz_arc, x_r - cx_r)
r_display = math.sqrt((prev_x_r - cx_r) ** 2 + (prev_z - cz_arc) ** 2)
print(f"r_display={r_display:.6f}")
print(f"angle_start={math.degrees(angle_start):.2f}, angle_end={math.degrees(angle_end):.2f}")

diff = angle_end - angle_start
if diff > math.pi:
    diff -= 2 * math.pi
elif diff < -math.pi:
    diff += 2 * math.pi
print(f"diff={math.degrees(diff):.2f} deg")

n_pts = max(10, int(abs(diff) * r_display * 40))
print(f"n_pts={n_pts}")

# Generate all arc points and check their ranges
x_coords = []
z_coords = []
for i in range(n_pts + 1):
    t = i / float(n_pts)
    angle = angle_start + diff * t
    ax = cx_r + r_display * math.cos(angle)
    az = cz_arc + r_display * math.sin(angle)
    x_coords.append(ax)
    z_coords.append(az)

print(f"\nArc point ranges:")
print(f"  X_r: min={min(x_coords):.4f}, max={max(x_coords):.4f}")
print(f"  Z:   min={min(z_coords):.4f}, max={max(z_coords):.4f}")
print(f"  First point: ({x_coords[0]:.4f}, {z_coords[0]:.4f})")
print(f"  Last point:  ({x_coords[-1]:.4f}, {z_coords[-1]:.4f})")
print(f"  Expected start: ({prev_x_r:.4f}, {prev_z:.4f})")
print(f"  Expected end:   ({x_r:.4f}, {z:.4f})")

# Now simulate the FULL coordinate list as the preview builds it
# Segments: LINE(0,0), LINE(0.5dia,0), LINE(0.5dia,-0.5), LINE(1.0dia,-0.5), ARC(1.25dia,-1.0)
all_segments = [
    {"type": "line", "x": 0.0, "z": 0.0, "radius": 0.0},
    {"type": "line", "x": 0.5, "z": 0.0, "radius": 0.0},
    {"type": "line", "x": 0.5, "z": -0.5, "radius": 0.0},
    {"type": "line", "x": 1.0, "z": -0.5, "radius": 0.0},
    {"type": "arc", "x": 1.25, "z": -1.0, "radius": -1.0},
]

full_x = []
full_z = []
prev_xr = 0.0
prev_zz = 0.0

for seg in all_segments:
    x_dia = float(seg.get("x", 0.0))
    zz = float(seg.get("z", 0.0))
    xr = x_dia / 2.0
    rad = float(seg.get("radius", 0.0))
    seg_type = seg.get("type", "line")

    if seg_type == "arc" and abs(rad) > 0.0001:
        r_abs_s = abs(rad)
        is_cw_s = rad > 0
        dx_r_s = xr - prev_xr
        dz_s = zz - prev_zz
        chord_s = math.sqrt(dx_r_s**2 + dz_s**2)
        
        if chord_s > 0.0001 and r_abs_s >= chord_s / 2.0 - 1e-9:
            if r_abs_s < chord_s / 2.0:
                r_abs_s = chord_s / 2.0
            mid_xr = (prev_xr + xr) / 2.0
            mid_zz = (prev_zz + zz) / 2.0
            h_s = math.sqrt(max(0.0, r_abs_s**2 - (chord_s/2.0)**2))
            px_s = -dz_s / chord_s
            pz_s = dx_r_s / chord_s
            if is_cw_s:
                cx = mid_xr + h_s * px_s
                cz = mid_zz + h_s * pz_s
            else:
                cx = mid_xr - h_s * px_s
                cz = mid_zz - h_s * pz_s
            a_start = math.atan2(prev_zz - cz, prev_xr - cx)
            a_end = math.atan2(zz - cz, xr - cx)
            r_disp = math.sqrt((prev_xr - cx)**2 + (prev_zz - cz)**2)
            d = a_end - a_start
            if d > math.pi: d -= 2*math.pi
            elif d < -math.pi: d += 2*math.pi
            np_s = max(10, int(abs(d) * r_disp * 40))
            for i in range(np_s + 1):
                t = i / float(np_s)
                angle = a_start + d * t
                full_x.append(cx + r_disp * math.cos(angle))
                full_z.append(cz + r_disp * math.sin(angle))
        else:
            full_x.append(xr)
            full_z.append(zz)
    else:
        full_x.append(xr)
        full_z.append(zz)
    
    prev_xr = xr
    prev_zz = zz

print(f"\n\nFull profile coordinate list ({len(full_x)} points):")
print(f"  X_r range: [{min(full_x):.4f}, {max(full_x):.4f}]")
print(f"  Z range:   [{min(full_z):.4f}, {max(full_z):.4f}]")
print(f"\nAll points:")
for i, (xv, zv) in enumerate(zip(full_x, full_z)):
    if i < 10 or i > len(full_x) - 5:
        print(f"  [{i:3d}] x_r={xv:.4f} z={zv:.4f}")
    elif i == 10:
        print(f"  ... ({len(full_x) - 14} more arc points) ...")

# Check for any point at x_r ≈ 0.5 with z far from [-0.5, -1.0]
print("\nPoints near x_r=0.5 with Z outside [-1.0, -0.5]:")
for i, (xv, zv) in enumerate(zip(full_x, full_z)):
    if abs(xv - 0.5) < 0.05 and (zv > -0.4 or zv < -1.1):
        print(f"  [{i}] x_r={xv:.4f} z={zv:.4f} *** SUSPICIOUS")
