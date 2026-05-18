---
inclusion: auto
---

# GUI Color System — Industry CAM Engine

## Design Philosophy

**Priority order:**
1. Operator legibility (can you read it at arm's length on a 15.6" touch panel?)
2. Sensible color logic (color communicates meaning without reading labels)
3. Pleasant, calm aesthetic (reduces cognitive fatigue during long sessions)

**Psychological basis:**
- Blue communicates trust, stability, and calm — ideal for a precision tool where confidence matters
- Green communicates safety, correctness, and "go" — natural for feed moves and valid states
- Muted teal/sage bridges blue and green — calming without being cold
- Red/crimson communicates danger and demands attention — reserved for errors and safety violations
- Warm peach/coral communicates caution without alarm — ideal for warnings and advisories
- Neutral grays provide structure without competing for attention

**Dark mode rationale:**
Research shows dark interfaces reduce eye strain in variable-light environments (shop floors have mixed lighting). Dark backgrounds also make colored graph traces more legible and reduce screen glare on reflective surfaces (coolant, metal chips). The graph area uses a dark background; UI panels use a slightly lighter dark tone for depth separation.

## Color Palette (Hex Values)

### Primary — Deep Navy-Teal (Backgrounds & Structure)

| Role | Hex | Usage |
|------|-----|-------|
| Base background (darkest) | `#21536E` | Main window background, graph background |
| Panel background | `#2A5F7A` | Tab content areas, input panels |
| Surface (elevated) | `#346B86` | Cards, grouped sections, modal backgrounds |
| Border/separator | `#7D9AB3` | Divider lines, panel edges |
| Subtle text | `#9AAFC2` | Secondary labels, disabled text |
| Surface highlight | `#B7C6D4` | Hover states on dark backgrounds |
| Status bar | `#1A4560` | Top bar — slightly darker than base |

### Secondary — Teal/Mint (Positive States & Accents)

| Role | Hex | Usage |
|------|-----|-------|
| Teal dark | `#5E9E91` | Active tab indicator, selected state |
| Teal mid | `#7AB5A8` | Primary accent, "Generate" button background |
| Teal light | `#A8D8CC` | Success indicators, valid segment preview |
| Mint pale | `#C8F0E8` | Subtle success background tint |

### Action — Blue Gradient (Interactive Elements)

| Role | Hex | Usage |
|------|-----|-------|
| Blue deep | `#1750AC` | Primary action buttons (pressed state) |
| Blue primary | `#3373C4` | Primary buttons, links, active controls |
| Blue mid | `#5494DA` | Button hover, selected toggle |
| Blue light | `#7BB9EE` | Focus rings, active input borders |
| Blue pale | `#A8D4F5` | Light accent backgrounds, info badges |

### Status — Green (Go / Safe / Feed Moves)

| Role | Hex | Usage |
|------|-----|-------|
| Green feed | `#5E9E91` | Feed moves on graph (same as teal dark — intentional) |
| Green valid | `#7AB5A8` | Valid segment in preview, "ready" indicator |
| Green bright | `#4CAF7C` | "Running" state, spindle on, program active |

### Status — Peach/Coral (Warning / Advisory)

| Role | Hex | Usage |
|------|-----|-------|
| Peach light | `#FFC8A5` | Warning background tint |
| Peach mid | `#FFCF92` | Warning icon fill |
| Coral | `#E56E72` | Warning text, advisory highlight on graph |
| Coral dark | `#C86D52` | Warning border, tool reach region highlight |

### Status — Crimson/Maroon (Error / Danger / Stop)

| Role | Hex | Usage |
|------|-----|-------|
| Pink light | `#D4868A` | Error background tint (soft) |
| Rose | `#B85A6A` | Error icon, invalid segment on preview |
| Crimson | `#8B2030` | Error text, gouge zone on graph, E-Stop indicator |
| Maroon dark | `#5C1520` | Critical error background, hard stop states |

### Neutral — Gray (Structure & Disabled States)

| Role | Hex | Usage |
|------|-----|-------|
| Gray mid | `#A8A8A8` | Disabled buttons, inactive tabs |
| Gray light | `#C8C8C8` | Placeholder text, stock boundary on graph |
| Gray pale | `#E0E0E0` | Light borders on light surfaces (rare) |
| White | `#F0F4F8` | Primary text on dark backgrounds, DRO readout |

### Accent — Purple/Violet (Special States & Differentiation)

| Role | Hex | Name | Usage |
|------|-----|------|-------|
| Mauve pale | `#C7AFF7` | Mauve | Light accent for special/unique states |
| Indigo light | `#A68CEE` | Tropical Indigo | Threading operations, special tool paths |
| Slate blue | `#8569E4` | Medium Slate Blue | Active threading pass on graph, tool type indicator |
| Grape | `#6B39BC` | Grape | Threading zone highlight, distinct from blue/teal |
| Indigo deep | `#510993` | Indigo | Deep accent for emphasis on dark backgrounds |

## Semantic Color Assignments

### Graph (PyQtGraph — Dark Background)

| Element | Color | Hex | Rationale |
|---------|-------|-----|-----------|
| Graph background | Deep navy-teal | `#21536E` | Low glare, blue-forward, high contrast for traces |
| Grid lines | Subtle surface | `#346B86` | Visible but not competing |
| Axis labels/ticks | Light gray | `#C8C8C8` | Legible without being bright |
| Crosshair lines | White 60% | `#F0F4F899` | Visible but not obscuring data |
| Coordinate readout | White | `#F0F4F8` | Maximum legibility for precision reading |
| **Profile boundary** | White bold | `#F0F4F8` | The target shape — highest visual priority |
| **Stock boundary** | Gray dashed | `#7D9AB3` | Reference, not primary focus |
| **Centerline** | White dashed thin | `#9AAFC280` | Spatial reference, subtle |
| **Closure preview** | Gray dashed thin | `#7D9AB360` | Shows where closure will happen |
| **Feed moves** | Teal/green | `#5E9E91` | "Safe cutting" — calm, positive |
| **Rapid moves** | Coral dashed | `#E56E72` | "Attention — fast movement" |
| **Arc moves** | Blue | `#5494DA` | Distinct from linear, visually interesting |
| **Zone: Finished Part** | Crimson fill 30% | `#8B203050` | "Never enter" — danger zone |
| **Zone: Material to Rough** | Blue fill 15% | `#5494DA25` | "Work area" — calm, present |
| **Zone: Finish Allowance** | Peach fill 20% | `#FFC8A533` | "Careful zone" — between safe and danger |
| **Active pass swept region** | Teal fill 25% | `#7AB5A840` | "Currently removing this" |
| **Warning region highlight** | Coral fill 20% | `#E56E7233` | Tool reach advisory area |
| **Round-trip overlay** | Mint semi-transparent | `#A8D8CC80` | Verification trace — distinct from primary |

### UI Elements

| Element | Color | Hex | Rationale |
|---------|-------|-----|-----------|
| Primary text | Near-white | `#F0F4F8` | Maximum readability on dark |
| Secondary text | Steel light | `#B7C6D4` | De-emphasized but legible |
| Disabled text | Steel mid | `#7D9AB3` | Clearly inactive |
| Input field background | Dark surface | `#354550` | Slightly lighter than panel for depth |
| Input field border (normal) | Steel border | `#7D9AB3` | Subtle definition |
| Input field border (focused) | Blue light | `#7BB9EE` | Clear focus indicator |
| Input field border (error) | Rose | `#B85A6A` | Immediate error visibility |
| Button primary | Blue primary | `#3373C4` | Action — "do something" |
| Button primary hover | Blue mid | `#5494DA` | Feedback on interaction |
| Button "Generate" | Teal mid | `#7AB5A8` | Special — the key action, calming green |
| Button danger | Crimson | `#8B2030` | Destructive actions, E-Stop |
| Tab active | Teal dark | `#5E9E91` | Current location indicator |
| Tab inactive | Steel subtle | `#7D9AB3` | Available but not current |
| Progress bar | Blue gradient | `#3373C4 → #5494DA` | Activity indicator |
| Scrollbar | Steel mid | `#7D9AB380` | Present but unobtrusive |

### Status Bar (Top Bar)

| Element | Color | Hex |
|---------|-------|-----|
| Bar background | Darkest navy | `#1A4560` | 
| Status text (normal) | Light gray | `#C8C8C8` |
| Status: E-Stop | Crimson | `#8B2030` |
| Status: Power OK | Teal | `#5E9E91` |
| Status: Homed | Teal | `#5E9E91` |
| Status: Not Homed | Coral | `#E56E72` |
| DRO numbers | White | `#F0F4F8` |
| DRO label | Steel light | `#B7C6D4` |
| Mode indicators (G20, G90, etc.) | Blue light | `#7BB9EE` |

### Playback Controls

| Element | Color | Hex |
|---------|-------|-----|
| Play button | Teal mid | `#7AB5A8` |
| Pause button | Blue primary | `#3373C4` |
| Step buttons | Steel light | `#B7C6D4` |
| N-number display | White | `#F0F4F8` |
| Pass type label | Teal light | `#A8D8CC` |
| Tool dot (animated) | White bright | `#FFFFFF` |

## Contrast & Accessibility Rules

1. **Text on dark backgrounds**: minimum 4.5:1 contrast ratio (WCAG AA). `#F0F4F8` on `#21536E` = 8.5:1 ✓
2. **Graph traces on background**: minimum 3:1 for non-text elements. All graph colors verified against `#21536E`.
3. **Error states**: red/crimson must be distinguishable from green/teal for color-blind operators. The crimson (`#8B2030`) and teal (`#5E9E91`) have sufficient luminance difference (not just hue difference).
4. **Touch targets**: minimum 44×44px for all interactive elements on the touch panel.
5. **No pure black (#000000)**: dark backgrounds use `#21536E` (deep navy-teal) to feel cohesive with the blue-green palette and reduce harshness.
6. **No pure white (#FFFFFF)** for large areas: text uses `#F0F4F8` (slightly warm) to reduce glare. Only the tool dot uses true white for maximum visibility.

## Emotional Design Intent

| User State | Color Response | Feeling |
|------------|---------------|---------|
| Building profile (creative) | Teal/mint accents on dark steel | Calm focus, "I'm in control" |
| Generating (waiting) | Blue progress animation | Trust, "it's working" |
| Viewing toolpath (reviewing) | Green feeds, blue arcs on dark | Confidence, "this looks right" |
| Warning displayed | Coral/peach highlights | Attention without panic, "consider this" |
| Error displayed | Crimson text, rose highlights | Urgency, "stop and fix this" |
| Playback (watching) | White dot moving on green/blue traces | Engagement, "I can see what it does" |

## Implementation Notes

```python
# Color constants for the engine (gui/colors.py)
COLORS = {
    # Backgrounds
    "bg_base": "#21536E",
    "bg_panel": "#2A5F7A",
    "bg_surface": "#346B86",
    "bg_status_bar": "#1A4560",
    
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
    "graph_bg": "#21536E",
    "graph_grid": "#346B86",
    "graph_axis": "#C8C8C8",
    "graph_crosshair": "#F0F4F899",
    "graph_profile": "#F0F4F8",
    "graph_stock": "#7D9AB3",
    "graph_centerline": "#9AAFC280",
    "graph_feed": "#5E9E91",
    "graph_rapid": "#E56E72",
    "graph_arc": "#5494DA",
    "graph_zone_finished": "#8B203050",
    "graph_zone_material": "#5494DA25",
    "graph_zone_allowance": "#FFC8A533",
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
```

## Font Pairing (Carried from my-lathe)

- **UI text**: Inter (clean, legible at small sizes, excellent on screens)
- **DRO / coordinates / code**: JetBrains Mono (monospace, clear digit distinction, no ambiguous characters)
- **Fallbacks**: system sans-serif (Segoe UI on Windows, DejaVu Sans on Linux)
