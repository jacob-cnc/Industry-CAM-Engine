import ezdxf

base = r'c:\Users\jhonick\linuxcnc\Industry CAM Engine\reference\CAD Reference\OD Reference'
files = [
    '175932-001_01-Stepped OD Finished Part Zone.dxf',
    '175932-001_01-Stepped OD Material to Rough Zone.dxf',
    '175932-001_01-Stepped OD True Face Zone.dxf',
    '175932-001_01-Stepped OD Finish Allowance Zone.dxf',
]

for filename in files:
    path = f'{base}\\{filename}'
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    
    label = filename.replace('175932-001_01-Stepped OD ', '').replace('.dxf', '')
    lines = []
    for e in msp:
        if e.dxftype() == 'LINE' and e.dxf.layer != '61':
            lines.append((e.dxf.start.x/25.4, e.dxf.start.y/25.4, e.dxf.end.x/25.4, e.dxf.end.y/25.4))
    
    print(f"=== {label} ({len(lines)} lines) ===")
    for sx, sy, ex, ey in lines:
        print(f"  ({sx:.5f}, {sy:.5f}) -> ({ex:.5f}, {ey:.5f})")
    print()
