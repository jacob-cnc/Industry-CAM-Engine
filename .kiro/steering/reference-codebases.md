---
inclusion: auto
---

# Reference Codebases

## Directive

Whenever analyzing, theorizing, designing, or discussing code structure and logic for the Industry CAM Engine, PROACTIVELY scan the reference codebases for:
- Examples of the functionality being discussed or implemented
- Code structure patterns that match or inform the architecture
- How other projects solved the same problem

Start with `reference/INDEX.md` to check each source's scope, version, authority,
and limitations. Existing project behavior and reference implementations are
evidence, not automatic authority. Keep review proportional to risk and
uncertainty.

## Location

All reference repos live under `Industry CAM Engine/reference/`:

```
reference/
├── liblathe/              ← Lathe-specific toolpath library (Python + C++)
├── freecad-turning-addon/ ← FreeCAD lathe turning operations (uses liblathe)
├── opencamlib/            ← Computational geometry for CAM (C++ with Python bindings)
├── bapt-cam/             ← FreeCAD CAM workbench (milling-focused, adaptive ops)
├── freecad-machines/      ← FreeCAD machine definitions and postprocessors
└── linuxcnc-source/       ← LinuxCNC interpreter, motion planner, arc math
```

## Module Cross-Reference

| Engine Module | Primary Reference | Pattern |
|---|---|---|
| `intervals/fiber.py` | OpenCamLib `src/algo/fiber.cpp` | Fiber collects Intervals with merge |
| `intervals/interval.py` | OpenCamLib `src/algo/interval.cpp` | contains/overlaps/merge/gap |
| `planners/offset_contour_planner.py` | Bapt_CAM `Op/AdaptativeOp.py` | Peel milling offsets |
| `planners/staircase_planner.py` | liblathe `liblathe/op/rough.py` | Horizontal passes with intersection |
| `transitions/transition.py` | Bapt_CAM `_pass_transitions` | Named transition types |
| `tools/tool_shape.py` | liblathe `liblathe/tool/tool.py` | Tool as segment group |
| `tools/tool_def.py` | FreeCAD Turning Addon `PathTurnBase.py` | Tool param flow |
| `outputs/gcode_writer.py` | Bapt_CAM `utils/GcodeWriter.py` | Position tracking, feed suppression |
| `geometry/adaptive_sampling.py` | OpenCamLib `src/algo/adaptivewaterline.cpp` | Cosine-limit flatness |
| `validation/polygon_builder.py` | my-lathe `tests/oracle/shapely_oracle.py` | Promoted to runtime |
| `validation/gouge_checker.py` | liblathe `op/rough.py` inline check | intersectsGroup pattern |
| `geometry/zone_builder.py` | my-lathe `engines/geometry.py` | Build123d Face booleans |
| `geometry/zone_query.py` | my-lathe `engines/zone_query.py` | ZoneQueryAPI with caching |

## Key Files by Topic

### Roughing Strategy
- `reference/liblathe/liblathe/op/rough.py` — staircase passes, boundary intersection
- `reference/bapt-cam/Op/AdaptativeOp.py` — offset-contour (peel milling), engagement control

### Tool Nose Radius
- `reference/liblathe/liblathe/tool/tool.py` — tool shape as segment group
- `reference/liblathe/liblathe/op/profile.py` — profile offset by stock_to_leave
- `reference/freecad-turning-addon/PathTurnScripts/PathTurnBase.py` — tool param flow

### Geometry Algorithms
- `reference/opencamlib/src/algo/fiber.cpp` — fiber-based interval collection
- `reference/opencamlib/src/algo/interval.cpp` — interval merge/containment
- `reference/opencamlib/src/algo/adaptivewaterline.cpp` — adaptive sampling
- `reference/opencamlib/src/geo/arc.cpp` — arc geometry operations

### G-Code Output
- `reference/bapt-cam/utils/GcodeWriter.py` — position tracking, feed suppression
- `reference/bapt-cam/utils/Contour.py` — edge-to-gcode conversion with arc direction

### LinuxCNC Internals
- `reference/linuxcnc-2.9.6-source/` — preferred for runtime-dependent decisions
  while the machine is documented as LinuxCNC 2.9.6
- `reference/linuxcnc-source/src/emc/rs274ngc/interp_arc.cc` — arc tolerance validation
- `reference/linuxcnc-source/src/emc/rs274ngc/interp_internal.hh` — tolerance constants
- `reference/linuxcnc-source/src/emc/motion/` — trajectory planner behavior
