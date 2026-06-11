# Reference Library Index

**Last reviewed:** 2026-06-11

Use this index before substantial design, machine-control, geometry, CAM, or
validation work. References are technical evidence, not automatic authority.
Apply the proportional review policy in
`docs/decisions/ADR-002-evidence-reference-and-change-discipline.md`.

## How to Use This Library

1. Start with current project state, active configuration, tests, and the newest
   relevant session note.
2. Use the topic map below to find applicable reference material.
3. Check version, authority, and limitations before relying on a source.
4. Prefer official material matching the installed runtime for version-dependent
   behavior.
5. Use a targeted experiment when it can resolve uncertainty faster than more
   reading.

## Authority Labels

| Label | Meaning |
|---|---|
| Official | Published by the product, standard, or library maintainer |
| Project measured | Captured from this project or physical machine |
| Vetted ground truth | Reviewed comparison data used to verify project output |
| Reference implementation | External implementation useful for patterns |
| Historical project material | Useful context that may be stale or conflicting |
| Experimental concept | Useful for ideas; requires strong local verification |

## Quick Topic Map

| Topic | Start Here | Then Consult |
|---|---|---|
| Current machine mapping/tuning | `industry-cam.ini`, `industry-cam.hal`, `docs/CURRENT_STATE.md` | Newest related `session-notes/`, Mesa manuals |
| Mesa wiring and electrical limits | `official-docs/mesa/` | `Hardware Integration Resources/`, active HAL, live `mesaflash`/HAL output |
| LinuxCNC arcs and interpretation | `linuxcnc-2.9.6-source/` | LinuxCNC 2.9 docs, NISTIR 6556, later-version source for comparison |
| Threading and spindle synchronization | LinuxCNC 2.9 G76/G33 docs, `linuxcnc-2.9.6-source/` | Active HAL/INI and conservative machine commissioning |
| OD/ID path correctness | `CAD Reference/` | Project tests, `liblathe/`, `freecad-turning-addon/` |
| Toolpath algorithms | `liblathe/`, `bapt-cam/`, `opencamlib/` | Project architecture and validation rules |
| Geometry kernel behavior | Project tests and `.kiro/steering/` | Official Build123d and OCCT docs |
| Runtime safety validation | `.kiro/steering/validation-rules.md`, project tests | Official Shapely/GEOS docs |
| HAL tuning/UI | `HAL&Tuning/` | Active HAL/INI, newest commissioning notes, LinuxCNC docs |
| Compound slide | `Manual Compound Slide/` | Active post-GUI HAL and focused tests |

## Machine and Control References

### `official-docs/mesa/`

- **Authority:** Official hardware manuals
- **Use for:** Connector pinouts, electrical limits, jumper behavior, board
  capabilities, and mesaflash procedures
- **Contains:** Mesa 7i96S manual v1.12 and Mesa 7i85S manual
- **Limitations:** Firmware determines exposed HostMot2 functions and numbering.
  Confirm the installed `7i96s_7i85sd.bin` image with live `mesaflash`/HAL output.

### `linuxcnc-2.9.6-source/`

- **Authority:** Official source matching the documented machine runtime
- **Version:** LinuxCNC `v2.9.6`, tag commit
  `8ed1eb5c486782137810430b1bc1113a597d4722`
- **Use for:** Arc interpretation, G76 conversion, interpreter checks, spindle
  index behavior, and motion behavior relevant to current commissioning
- **Limitations:** Targeted snapshot, not the complete source tree. Runtime
  packaging or machine-local patches still require confirmation on the lathe.

### `linuxcnc-source/`

- **Authority:** Official source snapshot, version-mismatched
- **Version:** `2.10.0~pre1`
- **Use for:** Broader interpreter and motion exploration; identifying later
  implementation changes
- **Limitations:** Does not match the documented LinuxCNC `2.9.6` runtime. Do not
  use it alone to assert current machine behavior.

### `official-docs/standards/NISTIR-6556-RS274NGC.pdf`

- **Authority:** Official NIST interpreter specification
- **Use for:** Historical RS274NGC semantics and terminology
- **Limitations:** LinuxCNC has extended and changed the interpreter. Current
  LinuxCNC documentation and version-matched source take precedence.

### `Hardware Integration Resources/`

- **Authority:** Historical project material
- **Use for:** Connector context, wiring colors, power distribution, and earlier
  machine plans
- **Limitations:** Contains stale/conflicting encoder numbering and commissioning
  status. Current HAL/INI, `docs/CURRENT_STATE.md`, `CLAUDE.md`, and newer dated
  session notes take precedence.

### `HAL&Tuning/`

- **Authority:** Historical project implementation and tuning reference
- **Use for:** HAL monitor/provider patterns, tuning UI ideas, and prior machine
  configuration
- **Limitations:** Reconcile all values and mappings against active
  configuration and newer measurements.

### `SINO WIRING MAP.csv`

- **Authority:** Project wiring reference
- **Use for:** Recorded SINO-to-Mesa wiring map
- **Limitations:** Verify against installed scale labels, live counts, Mesa
  jumper settings, and current machine wiring before changes.

## CAM, Geometry, and Validation References

### `CAD Reference/`

- **Authority:** Vetted ground truth and project-generated comparison output
- **Use for:** NX comparisons, regression fixtures, OD/ID/arc expected geometry,
  and toolpath review
- **Limitations:** Coverage is finite. A matching fixture does not prove safety
  outside the fixture set.

### `liblathe/`

- **Authority:** Experimental reference implementation
- **Upstream:** <https://github.com/dubstar-04/LibLathe>
- **Use for:** Lathe roughing, profiling, tool geometry, and intersection
  patterns
- **Limitations:** Its README calls it experimental/proof-of-concept. Do not
  treat generated paths as a safety oracle.

### `freecad-turning-addon/`

- **Authority:** Experimental reference implementation
- **Upstream:** <https://github.com/dubstar-04/FreeCAD_Turning_Addon>
- **Use for:** Turning operation structure and tool parameter flow
- **Limitations:** Experimental, older FreeCAD assumptions, and different
  architecture.

### `bapt-cam/`

- **Authority:** Reference implementation
- **Use for:** CAM workbench structure, geometry-first workflow, transition
  patterns, and G-code writer ideas
- **Limitations:** Primarily milling-focused and not a safety authority for this
  lathe.

### `opencamlib/`

- **Authority:** Reference implementation
- **Upstream:** <https://github.com/aewallin/opencamlib>
- **Use for:** Fibers, intervals, adaptive sampling, cutter contact, and
  computational geometry patterns
- **Limitations:** Much of it targets 3D milling. Translate concepts deliberately
  into this project's 2D lathe architecture.

### `Manual Compound Slide/`

- **Authority:** Project feature prototype
- **Use for:** Compound-slide logic, arc jog behavior, widget patterns, and tests
- **Limitations:** Reconcile with current HAL and machine commissioning before
  integration.

### `freecad-machines/`

- **Authority:** Reference implementation
- **Upstream:** <https://github.com/FreeCAD/Machines>
- **Use for:** Machine definitions and postprocessor organization
- **Limitations:** Generic descriptions do not establish this machine's mappings
  or safe limits.

## Maintainer Documentation Links

These are linked rather than copied because they evolve. Record the retrieval
date and relevant version when a decision depends on them.

| Subject | Maintainer Documentation | Applicability Note |
|---|---|---|
| LinuxCNC 2.9 | <https://linuxcnc.org/docs/2.9/html/> | Primary documentation family for documented runtime |
| LinuxCNC G76 | <https://linuxcnc.org/docs/2.9/html/gcode/g-code.html#gcode:g76> | Verify generated cycle and commissioning plan |
| LinuxCNC HAL | <https://linuxcnc.org/docs/2.9/html/hal/intro.html> | Confirm component and signal semantics |
| Build123d | <https://build123d.readthedocs.io/> | Requirement is `>=0.10.0`; record tested version |
| OCCT | <https://dev.opencascade.org/doc/overview/html/> | Kernel behavior and tolerance concepts |
| Shapely | <https://shapely.readthedocs.io/en/stable/> | Requirement is `>=2.1.0`; GEOS version also matters |
| GEOS | <https://libgeos.org/usage/> | Underlying predicate/precision behavior |

## High-Priority Acquisition Gaps

Do not fill these with an unverified reseller document merely to complete the
list.

| Missing Material | Why It Matters | Next Acquisition Action |
|---|---|---|
| UIRobot UIM8696PM official manual/configuration documentation | Step timing, internal speed/current limits, alarm behavior, and unexplained Z velocity ceiling | Capture labels and obtain official vendor manual/configuration export |
| Exact SINO KA300/KA500 manuals for installed variants | Electrical interface, index behavior, resolution, and pinout verification | Photograph labels/connectors and obtain matching manufacturer documentation |
| Exact spindle encoder model/datasheet | Index pulse behavior and electrical limits affect threading | Record model label and obtain manufacturer datasheet |
| Installed Mesa firmware identity/export | HostMot2 numbering and capabilities depend on firmware | Save `mesaflash --readhmid` and firmware checksum from machine |
| Exact LinuxCNC package/build identity from lathe | Confirms whether runtime is stock `2.9.6` or patched | Record package version, commit/build info, and OS package source |
| Tool-manufacturer data for installed inserts/holders | Feeds, speeds, approach constraints, and thread forms depend on exact tooling | Inventory holder/insert codes and gather matching manufacturer sheets |

## Maintenance

When adding a reference:

1. Prefer official or clearly attributable sources.
2. Record source URL, version/commit, retrieval date, intended use, and limits.
3. Add hashes for downloaded binary documents.
4. Update this index when a reference becomes stale, superseded, or conflicts
   with current evidence.
