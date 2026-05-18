"""Parse the NX Arc Reference Toolpath DXF to understand contour roughing ground truth."""
import sys
import os
import math
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

import ezdxf

MM = 1.0 / 25.4

filepath = r'c:\Users\jhonick\linuxcnc\Industry CAM Engine\reference\CAD Reference\Arc Reference\175934-001_01-Arc Reference Toolpath.dxf'

doc = ezdxf.readfile(filepath)
msp = doc.modelspace()

entities = list(msp)
print(f"Total entities: {len(entities)}")

# Categorize
lines = []
arcs = []
points = []
others = []

for ent in entities:
    etype = ent.dxftype()
    layer = ent.dxf.layer if hasattr(ent.dxf, 'layer') else '0'
    
    if etype == 'LINE':
        sx = ent.dxf.start.x * MM
        sy = ent.dxf.start.y * MM
        ex = ent.dxf.end.x * MM
        ey = ent.dxf.end.y * MM
        lines.append(((sx, sy), (ex, ey), layer))
    elif etype == 'ARC':
        cx = ent.dxf.center.x * MM
        cy = ent.dxf.center.y * MM
        r = ent.dxf.radius * MM
        sa = ent.dxf.start_angle
        ea = ent.dxf.end_angle
        # Compute start/end points
        sp_x = cx + r * math.cos(math.radians(sa))
        sp_y = cy + r * math.sin(math.radians(sa))
        ep_x = cx + r * math.cos(math.radians(ea))
        ep_y = cy + r * math.sin(math.radians(ea))
        arcs.append({
            'center': (cx, cy), 'radius': r,
            'start_angle': sa, 'end_angle': ea,
            'start_pt': (sp_x, sp_y), 'end_pt': (ep_x, ep_y),
            'layer': layer
        })
    elif etype == 'POINT':
        px = ent.dxf.location.x * MM
        py = ent.dxf.location.y * MM
        if abs(px) > 0.001 or abs(py) > 0.001:
            points.append((px, py, layer))
    else:
        others.append((etype, layer))

print(f"\nLines: {len(lines)}")
print(f"Arcs: {len(arcs)}")
print(f"Points: {len(points)}")
print(f"Others: {len(others)}")

# Print all lines grouped by approximate X value (contour passes are at constant X)
print(f"\n{'='*60}")
print("LINES (sorted by start X):")
print(f"{'='*60}")
lines.sort(key=lambda l: (round(l[0][0], 3), -l[0][1]))

# Group vertical lines (constant X) vs horizontal lines (constant Z)
vertical = [(s, e, layer) for (s, e, layer) in lines if abs(s[0] - e[0]) < 0.001]
horizontal = [(s, e, layer) for (s, e, layer) in lines if abs(s[1] - e[1]) < 0.001]
diagonal = [(s, e, layer) for (s, e, layer) in lines if abs(s[0] - e[0]) >= 0.001 and abs(s[1] - e[1]) >= 0.001]

print(f"\nVertical lines (constant X): {len(vertical)}")
for (s, e, layer) in vertical:
    z_top = max(s[1], e[1])
    z_bot = min(s[1], e[1])
    print(f"  X={s[0]:.4f}r  Z[{z_top:.4f} -> {z_bot:.4f}]  [L:{layer}]")

print(f"\nHorizontal lines (constant Z): {len(horizontal)}")
for (s, e, layer) in horizontal:
    x_left = min(s[0], e[0])
    x_right = max(s[0], e[0])
    print(f"  Z={s[1]:.4f}  X[{x_left:.4f}r -> {x_right:.4f}r]  [L:{layer}]")

print(f"\nDiagonal lines: {len(diagonal)}")
for (s, e, layer) in diagonal:
    print(f"  ({s[0]:.4f}r, {s[1]:.4f}) -> ({e[0]:.4f}r, {e[1]:.4f})  [L:{layer}]")

print(f"\n{'='*60}")
print("ARCS:")
print(f"{'='*60}")
for arc in arcs:
    print(f"  Center=({arc['center'][0]:.4f}r, {arc['center'][1]:.4f}), R={arc['radius']:.4f}")
    print(f"    Start=({arc['start_pt'][0]:.4f}r, {arc['start_pt'][1]:.4f}), End=({arc['end_pt'][0]:.4f}r, {arc['end_pt'][1]:.4f})")
    print(f"    Angles: {arc['start_angle']:.1f} -> {arc['end_angle']:.1f}  [L:{arc['layer']}]")

print(f"\n{'='*60}")
print("REFERENCE POINTS:")
print(f"{'='*60}")
for (px, py, layer) in points:
    print(f"  ({px:.4f}r, {py:.4f})  [L:{layer}]")
