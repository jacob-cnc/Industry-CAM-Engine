# Point Charts

Default location for CSV files exchanged between the Industry CAM Engine
segment list and the NX Sketch Point Manager.

## Format

```
type,x,z,radius
line,1.5000,-0.5000,0.0000
arc,0.7500,-1.2500,-0.1250
```

- **type**: `line` or `arc`
- **x**: X diameter in inches
- **z**: Z position in inches (negative = into workpiece)
- **radius**: signed float — 0 for lines, negative = CW (G03), positive = CCW (G02)

CSV files in this folder are git-ignored except this README.
