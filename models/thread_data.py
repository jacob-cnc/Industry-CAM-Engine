"""Standard thread data: sizes, class limits, depths, tap drills (owner plan 2026-11-12).

Single source of thread numbers for the threading panel and planner
(docs/handoffs/2026-11-12-threading-workflow-plan.md, phase T1). Values are
generated from the published standard formulas and checked against the
standards' tables in tests/unit/test_thread_data.py - nothing here is an
estimate; a size the data does not cover is not offered (use Custom).

Standards:
    UNC / UNF   ASME B1.1      classes 2A/2B, 3A/3B    (LE = D, as the B1.1 tables)
    Metric      ISO 965-1      classes 6g/6H, 4h/5H
    Tr          ISO 2903 / DIN 103   class 7e/7H
    Acme        ASME B1.5      classes 2G, 3G (general purpose)
    NPT         ASME B1.20.1   (gauged; no class)

Everything returned is in INCHES (diameters), metric values are computed in mm
on the standard's own rounding and converted at the end.

Depth model (plan section 3): each class gives the ROOT diameter relative to
the nominal major X the panel fills in:
    external  root = X + root_offset (root_offset < 0: the class's max minor)
    internal  root = X + root_offset (root_offset >= 0: the class's min major)
so the cut depth is derived from the standard and the class, never typed.
Internal crest = the pilot (tap drill) diameter.

Imports from: nothing (stdlib only).
"""

from dataclasses import dataclass
from math import sqrt
from typing import Dict, List, Optional, Tuple

MM = 25.4

# ---------------------------------------------------------------------------
# Forms: flank angle (included) and basic depths (radial, x pitch)
# ---------------------------------------------------------------------------

FORMS = {
    # name: (included angle deg, default entry angle deg)
    "60":   (60.0, 29.5),
    "acme": (29.0, 14.5),
    "tr":   (30.0, 15.0),
    "npt":  (60.0, 29.5),
}
FORM_LABELS = {"60": "60° (UN / metric)", "acme": "Acme 29°",
               "tr": "Trapezoidal 30°", "npt": "NPT 60° taper"}

NPT_TAPER = 1.0 / 16.0           # on diameter, per unit length (ASME B1.20.1)


def basic_depth(form: str, pitch: float, internal: bool) -> float:
    """Basic radial depth for Custom threads (no class), inches.

    60 deg: external .61343P (to the rounded-root minor), internal .54127P (5H/8).
    Acme:   .5P + .010 (B1.5 basic height + the 2G minor clearance, P >= .1)
            or .5P + .005 for finer pitches.
    Tr:     h3 = .5P + ac (ISO 2903 clearance ac by pitch, in mm).
    NPT:    h = .8P.
    """
    if form == "60":
        return (0.541266 if internal else 0.613435) * pitch
    if form == "acme":
        return 0.5 * pitch + (0.010 if pitch >= 0.1 - 1e-9 else 0.005)
    if form == "tr":
        return (0.5 * pitch * MM + _tr_ac(pitch * MM)) / MM
    if form == "npt":
        return 0.8 * pitch
    raise ValueError(f"Unknown thread form {form!r}")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ThreadSize:
    type: str            # "UNC", "UNF", "Metric Coarse", "Metric Fine", "Tr", "Acme", "NPT"
    label: str           # "1/4-20 UNC", "M6x1", "Tr20x4", "1-5 ACME", "1/4 NPT"
    major: float         # nominal major diameter, inches (NPT: pipe OD)
    pitch: float         # inches per thread
    form: str            # key of FORMS
    tap_drill: Tuple[str, float]   # (label, diameter in inches)


@dataclass(frozen=True)
class ThreadLimits:
    """One class on one side, inches. None = not applicable."""
    size: ThreadSize
    thread_class: str            # "2A", "6H", "2G", ...
    internal: bool
    major_max: Optional[float]
    major_min: Optional[float]
    pd_max: Optional[float]
    pd_min: Optional[float]
    root: float                  # diameter the tool cuts to (ext: minor max, int: major min)
    root_offset: float           # root - nominal major

    @property
    def depth_from_nominal(self) -> float:
        """Radial depth from the nominal major (external) - the hint's 'depth'."""
        return abs(self.root_offset) / 2.0


# ---------------------------------------------------------------------------
# UN (ASME B1.1)
# ---------------------------------------------------------------------------

_UN = [
    # (label, D, tpi, series, tap drill label, tap drill dia)
    ("#4-40", 0.1120, 40, "UNC", "#43", 0.0890),
    ("#4-48", 0.1120, 48, "UNF", "#42", 0.0935),
    ("#6-32", 0.1380, 32, "UNC", "#36", 0.1065),
    ("#6-40", 0.1380, 40, "UNF", "#33", 0.1130),
    ("#8-32", 0.1640, 32, "UNC", "#29", 0.1360),
    ("#8-36", 0.1640, 36, "UNF", "#29", 0.1360),
    ("#10-24", 0.1900, 24, "UNC", "#25", 0.1495),
    ("#10-32", 0.1900, 32, "UNF", "#21", 0.1590),
    ("1/4-20", 0.2500, 20, "UNC", "#7", 0.2010),
    ("1/4-28", 0.2500, 28, "UNF", "#3", 0.2130),
    ("5/16-18", 0.3125, 18, "UNC", "F", 0.2570),
    ("5/16-24", 0.3125, 24, "UNF", "I", 0.2720),
    ("3/8-16", 0.3750, 16, "UNC", "5/16", 0.3125),
    ("3/8-24", 0.3750, 24, "UNF", "Q", 0.3320),
    ("7/16-14", 0.4375, 14, "UNC", "U", 0.3680),
    ("7/16-20", 0.4375, 20, "UNF", "25/64", 0.3906),
    ("1/2-13", 0.5000, 13, "UNC", "27/64", 0.4219),
    ("1/2-20", 0.5000, 20, "UNF", "29/64", 0.4531),
    ("9/16-12", 0.5625, 12, "UNC", "31/64", 0.4844),
    ("9/16-18", 0.5625, 18, "UNF", "33/64", 0.5156),
    ("5/8-11", 0.6250, 11, "UNC", "17/32", 0.5312),
    ("5/8-18", 0.6250, 18, "UNF", "37/64", 0.5781),
    ("3/4-10", 0.7500, 10, "UNC", "21/32", 0.6562),
    ("3/4-16", 0.7500, 16, "UNF", "11/16", 0.6875),
    ("7/8-9", 0.8750, 9, "UNC", "49/64", 0.7656),
    ("7/8-14", 0.8750, 14, "UNF", "13/16", 0.8125),
    ("1-8", 1.0000, 8, "UNC", "7/8", 0.8750),
    ("1-12", 1.0000, 12, "UNF", "59/64", 0.9219),
    ("1-1/8-7", 1.1250, 7, "UNC", "63/64", 0.9844),
    ("1-1/8-12", 1.1250, 12, "UNF", "1-3/64", 1.0469),
    ("1-1/4-7", 1.2500, 7, "UNC", "1-7/64", 1.1094),
    ("1-1/4-12", 1.2500, 12, "UNF", "1-11/64", 1.1719),
    ("1-3/8-6", 1.3750, 6, "UNC", "1-7/32", 1.2188),
    ("1-3/8-12", 1.3750, 12, "UNF", "1-19/64", 1.2969),
    ("1-1/2-6", 1.5000, 6, "UNC", "1-11/32", 1.3438),
    ("1-1/2-12", 1.5000, 12, "UNF", "1-27/64", 1.4219),
]


def _r4(v: float) -> float:
    return round(v + 0.0, 4)


def _un_limits(size: ThreadSize, cls: str, internal: bool) -> ThreadLimits:
    # B1.1 rounds the basic pitch diameter, the allowance and each tolerance to
    # .0001 first, then adds / subtracts (that is how its tables come out).
    D, P = size.major, size.pitch
    td2_2a = 0.0015 * D ** (1.0 / 3.0) + 0.0015 * sqrt(D) + 0.015 * P ** (2.0 / 3.0)
    pd_basic = _r4(D - 0.649519 * P)
    grade = cls[0]                                            # "2" / "3"
    if not internal:
        es = _r4(0.300 * td2_2a) if grade == "2" else 0.0
        td2 = _r4(td2_2a if grade == "2" else 0.75 * td2_2a)
        major_max = _r4(D - es)
        major_min = _r4(major_max - _r4(0.060 * P ** (2.0 / 3.0)))
        pd_max = _r4(pd_basic - es)
        pd_min = _r4(pd_max - td2)
        root = _r4(pd_max - 0.577350 * P)                     # UNR minor, max
    else:
        td2 = _r4((1.3 if grade == "2" else 0.975) * td2_2a)
        major_max = None
        major_min = D
        pd_min = pd_basic
        pd_max = _r4(pd_basic + td2)
        root = D
    return ThreadLimits(size, cls, internal, major_max, major_min, pd_max, pd_min, root, root - D)


# ---------------------------------------------------------------------------
# ISO metric (ISO 965-1)
# ---------------------------------------------------------------------------

_METRIC_COARSE = [(3, 0.5), (4, 0.7), (5, 0.8), (6, 1.0), (8, 1.25), (10, 1.5), (12, 1.75),
                  (14, 2.0), (16, 2.0), (18, 2.5), (20, 2.5), (22, 2.5), (24, 3.0), (27, 3.0),
                  (30, 3.5), (36, 4.0)]
_METRIC_FINE = [(8, 1.0), (10, 1.0), (10, 1.25), (12, 1.25), (12, 1.5), (14, 1.5), (16, 1.5),
                (18, 1.5), (20, 1.5), (22, 1.5), (24, 1.5), (24, 2.0), (27, 2.0), (30, 2.0),
                (36, 3.0)]

# Fundamental deviation es of 'g' (external), micrometres, by pitch (ISO 965-1 table).
_ES_G = {0.5: 20, 0.6: 21, 0.7: 22, 0.75: 22, 0.8: 24, 1.0: 26, 1.25: 28, 1.5: 32, 1.75: 34,
         2.0: 38, 2.5: 42, 3.0: 48, 3.5: 53, 4.0: 60}
# ISO 965-1 diameter ranges (mm) for Td2 / TD2.
_RANGES = [(1.4, 2.8), (2.8, 5.6), (5.6, 11.2), (11.2, 22.4), (22.4, 45.0), (45.0, 90.0)]
# Renard R40 preferred numbers (one decade); ISO tolerance values are rounded to them.
_R40 = [100, 106, 112, 118, 125, 132, 140, 150, 160, 170, 180, 190, 200, 212, 224, 236, 250,
        265, 280, 300, 315, 335, 355, 375, 400, 425, 450, 475, 500, 530, 560, 600, 630, 670,
        710, 750, 800, 850, 900, 950, 1000]
_GRADE = {3: 0.5, 4: 0.63, 5: 0.8, 6: 1.0, 7: 1.25, 8: 1.6, 9: 2.0}


def _r40(um: float) -> float:
    """Round a tolerance (um) to the nearest R40 number, as ISO 965-1's tables."""
    scale = 1.0
    while um >= 1000:
        um, scale = um / 10.0, scale * 10.0
    while um < 100:
        um, scale = um * 10.0, scale / 10.0
    best = min(_R40, key=lambda r: abs(r - um))
    return best * scale


def _range_mean(d_mm: float) -> float:
    for lo, hi in _RANGES:
        if lo < d_mm <= hi:
            return sqrt(lo * hi)
    raise ValueError(f"M{d_mm:g} outside the ISO 965-1 diameter ranges in this table")


def _td2_um(d_mm: float, p_mm: float, grade: int) -> float:
    """Td2: grade 6 from the formula, other grades = factor x the ROUNDED grade-6
    value, each rounded to R40 (reproduces ISO 965-1 incl. 4h, e.g. Td(4) P1.75 = 170)."""
    g6 = _r40(90.0 * p_mm ** 0.4 * _range_mean(d_mm) ** 0.1)
    return g6 if grade == 6 else _r40(_GRADE[grade] * g6)


def _td_major_um(p_mm: float, grade: int) -> float:
    g6 = _r40(180.0 * p_mm ** (2.0 / 3.0) - 3.15 / sqrt(p_mm))
    return g6 if grade == 6 else _r40(_GRADE[grade] * g6)


def _metric_limits(size: ThreadSize, cls: str, internal: bool) -> ThreadLimits:
    d, p = round(size.major * MM, 3), round(size.pitch * MM, 4)
    d2 = d - 0.649519 * p
    if not internal:
        grade, letter = int(cls[0]), cls[1]                    # "6g" / "4h"
        es = (_ES_G[p] if letter == "g" else 0.0) / 1000.0
        d_max = d - es
        d_min = d_max - _td_major_um(p, grade) / 1000.0
        d2_max = d2 - es
        d2_min = d2_max - _td2_um(d, p, grade) / 1000.0
        d3_max = d - 1.226869 * p - es
        vals = [round(v, 3) / MM for v in (d_max, d_min, d2_max, d2_min, d3_max)]
        root = vals[4]
        return ThreadLimits(size, cls, False, vals[0], vals[1], vals[2], vals[3], root, root - size.major)
    # Internal (H): the root is the basic major (EI = 0). The internal pitch-diameter
    # window is not offered (the ID hint is the tap drill only; owner 2026-11-12).
    return ThreadLimits(size, cls, True, None, size.major, None, None, size.major, 0.0)


# ---------------------------------------------------------------------------
# Trapezoidal (ISO 2903 / DIN 103) and Acme (ASME B1.5) - see _TR / _ACME
# ---------------------------------------------------------------------------

def _tr_ac(p_mm: float) -> float:
    """ISO 2903 crest clearance ac (mm) by pitch."""
    if p_mm <= 1.5:
        return 0.15
    if p_mm <= 5:
        return 0.25
    if p_mm <= 12:
        return 0.5
    return 1.0


# ---------------------------------------------------------------------------
# NPT (ASME B1.20.1)
# ---------------------------------------------------------------------------

_NPT = [
    # (label, pipe OD D, tpi, L1 hand-tight, tap drill label, dia)
    ("1/8", 0.405, 27, 0.1615, "R", 0.3390),
    ("1/4", 0.540, 18, 0.2278, "7/16", 0.4375),
    ("3/8", 0.675, 18, 0.240, "37/64", 0.5781),
    ("1/2", 0.840, 14, 0.320, "23/32", 0.7188),
    ("3/4", 1.050, 14, 0.339, "59/64", 0.9219),
    ("1", 1.315, 11.5, 0.400, "1-5/32", 1.1562),
    ("1-1/4", 1.660, 11.5, 0.420, "1-1/2", 1.5000),
    ("1-1/2", 1.900, 11.5, 0.420, "1-47/64", 1.7344),
    ("2", 2.375, 11.5, 0.436, "2-7/32", 2.2188),
]


@dataclass(frozen=True)
class NptData:
    size: ThreadSize
    e0: float        # pitch diameter at the small end of the external thread
    e1: float        # pitch diameter at the gauge plane (L1 from the small end)
    l1: float        # hand-tight engagement
    h: float         # thread height (.8P)

    @property
    def major_small_end(self) -> float:
        return self.e0 + self.h

    @property
    def major_at_gauge_plane(self) -> float:
        return self.e1 + self.h


def npt_data(label: str) -> NptData:
    for name, D, tpi, l1, _dl, _dd in _NPT:
        if f"{name} NPT" == label:
            p = 1.0 / tpi
            e0 = D - (0.05 * D + 1.1) * p
            return NptData(size(label), e0, e0 + l1 * NPT_TAPER, l1, 0.8 * p)
    raise KeyError(label)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

THREAD_TYPES = ["UNC", "UNF", "Metric Coarse", "Metric Fine", "Metric Trapezoidal", "Acme", "NPT"]

CLASSES = {
    # type: [(external, internal)]
    "UNC": [("2A", "2B"), ("3A", "3B")],
    "UNF": [("2A", "2B"), ("3A", "3B")],
    "Metric Coarse": [("6g", "6H"), ("4h", "5H")],
    "Metric Fine": [("6g", "6H"), ("4h", "5H")],
    "Metric Trapezoidal": [("7e", "7H")],
    "Acme": [("2G", "2G"), ("3G", "3G")],
    "NPT": [],
}


def _build() -> Dict[str, List[ThreadSize]]:
    out: Dict[str, List[ThreadSize]] = {t: [] for t in THREAD_TYPES}
    for name, D, tpi, series, dl, dd in _UN:
        out[series].append(ThreadSize(series, f"{name} {series}", D, 1.0 / tpi, "60", (dl, dd)))
    for key, table in (("Metric Coarse", _METRIC_COARSE), ("Metric Fine", _METRIC_FINE)):
        for d, p in table:
            drill = d - p
            out[key].append(ThreadSize(key, f"M{d:g}x{p:g}", d / MM, p / MM, "60",
                                       (f"{drill:g} mm", drill / MM)))
    for d, p in _TR:
        out["Metric Trapezoidal"].append(ThreadSize(
            "Metric Trapezoidal", f"Tr{d:g}x{p:g}", d / MM, p / MM, "tr",
            (f"{d - p:g} mm", (d - p) / MM)))
    for name, D, tpi, drill_label, drill in _ACME:
        out["Acme"].append(ThreadSize("Acme", f"{name}-{tpi:g} ACME", D, 1.0 / tpi, "acme",
                                      (drill_label, drill)))
    for name, D, tpi, _l1, dl, dd in _NPT:
        out["NPT"].append(ThreadSize("NPT", f"{name} NPT", D, 1.0 / tpi, "npt", (dl, dd)))
    return out


# Trapezoidal (ISO 2901 profile, 7e / 7H limits from the DIN 103 tables): only the
# sizes whose 7e pitch-diameter limits are taken from the published table are
# offered - (d mm, P mm, d2 max, d2 min).
_TR_7E = [(10, 2, 8.929, 8.739), (16, 4, 13.905, 13.640), (20, 4, 17.905, 17.640),
          (24, 5, 21.394, 21.094), (40, 7, 36.375, 36.020)]
_TR: List[Tuple[float, float]] = [(d, p) for d, p, _a, _b in _TR_7E]
# Acme general purpose (ASME B1.5): (label, D, tpi, internal minor-min label, dia)
_ACME_SIZES = [("1/4", 0.25, 16), ("5/16", 0.3125, 14), ("3/8", 0.375, 12), ("7/16", 0.4375, 12),
               ("1/2", 0.5, 10), ("5/8", 0.625, 8), ("3/4", 0.75, 6), ("7/8", 0.875, 6),
               ("1", 1.0, 5), ("1-1/8", 1.125, 5), ("1-1/4", 1.25, 5), ("1-3/8", 1.375, 4),
               ("1-1/2", 1.5, 4), ("1-3/4", 1.75, 4), ("2", 2.0, 4)]
_ACME: List[Tuple[str, float, float, str, float]] = [
    (n, D, tpi, f"{D - 1.0 / tpi:.4f}\" (minor)", round(D - 1.0 / tpi, 4))
    for n, D, tpi in _ACME_SIZES]


def sizes(thread_type: str) -> List[ThreadSize]:
    return list(_catalogue()[thread_type])


def size(label: str) -> ThreadSize:
    for lst in _catalogue().values():
        for s in lst:
            if s.label == label:
                return s
    raise KeyError(label)


def classes(thread_type: str, internal: bool) -> List[str]:
    return [pair[1 if internal else 0] for pair in CLASSES[thread_type]]


def limits(label: str, thread_class: str, internal: bool) -> ThreadLimits:
    s = size(label)
    if s.type in ("UNC", "UNF"):
        return _un_limits(s, thread_class, internal)
    if s.type.startswith("Metric") and s.form == "60":
        return _metric_limits(s, thread_class, internal)
    if s.type == "Metric Trapezoidal":
        return _tr_limits(s, thread_class, internal)
    if s.type == "Acme":
        return _acme_limits(s, thread_class, internal)
    raise ValueError(f"{label}: no class limits (NPT is gauged)")


_CAT: Optional[Dict[str, List[ThreadSize]]] = None


def _catalogue() -> Dict[str, List[ThreadSize]]:
    global _CAT
    if _CAT is None:
        _CAT = _build()
    return _CAT


def _tr_limits(size_: ThreadSize, cls: str, internal: bool) -> ThreadLimits:
    """ISO 2901 / 2903: es (7e) applies to d2 only - d and d3 max are basic.
    External root = d3 = d - 2(.5P + ac); internal root = D4 = d + 2ac."""
    d, p = round(size_.major * MM, 3), round(size_.pitch * MM, 3)
    ac = _tr_ac(p)
    if internal:
        root = (d + 2 * ac) / MM
        return ThreadLimits(size_, cls, True, None, root, None, None, root, root - size_.major)
    d2max, d2min = next((a, b) for dd, pp, a, b in _TR_7E if dd == d and pp == p)
    root = (d - 2 * (0.5 * p + ac)) / MM
    return ThreadLimits(size_, cls, False, size_.major, None, d2max / MM, d2min / MM, root,
                        root - size_.major)


def _acme_limits(size_: ThreadSize, cls: str, internal: bool) -> ThreadLimits:
    """ASME B1.5 general purpose (Machinery's Handbook tables 1, 2a, 4, 5):
    allowance a = .020 (10 tpi and coarser) / .010 (finer);
    external minor max = D - P - a, internal major min = D + a;
    PD allowance 2G .008 sqrt(D), 3G .006 sqrt(D); PD tolerance
    2G .006 sqrt(D) + .030 sqrt(P), 3G .0028 sqrt(D) + .014 sqrt(P)."""
    D, P = size_.major, size_.pitch
    a = 0.020 if P >= 0.1 - 1e-9 else 0.010
    if internal:
        return ThreadLimits(size_, cls, True, None, _r4(D + a), None, None, _r4(D + a), a)
    allow = (0.008 if cls == "2G" else 0.006) * sqrt(D)
    tol = (0.006 * sqrt(D) + 0.030 * sqrt(P)) if cls == "2G" else (0.0028 * sqrt(D) + 0.014 * sqrt(P))
    # rounded to .0001 before combining, as the B1.5 tables
    pd_max = _r4(_r4(D - 0.5 * P) - _r4(allow))
    pd_min = _r4(pd_max - _r4(tol))
    root = _r4(D - P - a)
    return ThreadLimits(size_, cls, False, D, _r4(D - max(0.05 * P, 0.005)), pd_max, pd_min,
                        root, root - D)


# ---------------------------------------------------------------------------
# Operation fields -> ThreadingParams (panel, generate, saved programs)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Derived:
    """What the standard / class gives for the current fields."""
    root_offset: float           # root - X (dia)
    form_depth: float            # radial; internal tapers: crest = root - 2 x this
    pilot: float                 # suggested pilot (tap drill) for internal, else 0
    entry_angle: float           # default compound angle for the form
    limits: Optional[ThreadLimits]
    source: str                  # "UN 2A", "basic 60 deg (Custom)", ...


def derive(thread_type: str, designation: str, thread_class: str, form: str,
           internal: bool, pitch: float) -> Derived:
    """Depth source for the fields (plan section 3): the standard + class, or the
    form's basic depth for Custom."""
    if thread_type != "Custom":
        s = size(designation)
        form = s.form
        entry = FORMS[form][1]
        if s.type == "NPT":
            h = 0.8 * s.pitch
            return Derived(0.0 if internal else -2.0 * h, h, s.tap_drill[1] if internal else 0.0,
                           entry, None, "NPT (h = .8P)")
        lim = limits(designation, thread_class, internal)
        return Derived(lim.root_offset, basic_depth(form, s.pitch, internal),
                       s.tap_drill[1] if internal else 0.0, entry, lim,
                       f"{_family(s.type)} {thread_class}")
    d = basic_depth(form, pitch, internal)
    if internal:
        return Derived(0.0, d, 0.0, FORMS[form][1], None,
                       f"basic {FORM_LABELS[form]} (Custom)")
    return Derived(-2.0 * d, d, 0.0, FORMS[form][1], None, f"basic {FORM_LABELS[form]} (Custom)")


def _family(t: str) -> str:
    return {"UNC": "UN", "UNF": "UN", "Metric Coarse": "ISO", "Metric Fine": "ISO",
            "Metric Trapezoidal": "Tr", "Acme": "Acme"}.get(t, t)


_LEGACY_INFEED = {"radial": 0.0, "flank": 29.5, "modified_flank": 29.5, "alternating": 29.5}


def _legacy_label(old: str) -> Optional[str]:
    """Map a v1 / v2 panel designation onto the new catalogue (None = Custom)."""
    import re
    label = old.replace("×", "x").replace(" Fine", "").strip()
    m = re.fullmatch(r"M(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", label)
    if m:
        label = f"M{float(m.group(1)):g}x{float(m.group(2)):g}"
    m = re.fullmatch(r"(.+)-\d+(?:\.\d+)? NPT", label)
    if m:
        label = f"{m.group(1)} NPT"
    try:
        size(label)
        return label
    except KeyError:
        return None


def from_saved(data: dict, internal: bool):
    """Saved block data (new or legacy) -> (fields dict in the new format, notes).

    Legacy blocks (major_diameter / thread_depth / infeed_method / chamfer_threads)
    are mapped onto the catalogue where the designation exists, else Custom with
    the old major as X; their chamfer is dropped (Z end is the pull-out point)."""
    if "x_start" in data:
        return dict(data), []
    notes = []
    old = data.get("designation", "")
    label = _legacy_label(old) if old else None
    pitch = float(data.get("pitch", 0.05))
    fields = {
        "start_z": float(data.get("start_z", 0.05)),
        "end_z": float(data.get("end_z", -0.75)),
        "num_passes": int(data.get("num_passes", 6)),
        "spring_passes": int(data.get("spring_passes", 2)),
        "num_starts": int(data.get("num_starts", 1)),
        "spindle_rpm": float(data.get("spindle_rpm", 400)),
        "tool_number": int(data.get("tool_number", 2)),
    }
    if label is not None:
        s = size(label)
        pairs = CLASSES[s.type]
        old_cls = str(data.get("thread_class", "2A"))
        grade3 = old_cls.startswith("3")
        cls = ""
        if pairs:
            pair = pairs[1] if grade3 and len(pairs) > 1 else pairs[0]
            cls = pair[1 if internal else 0]
        fields.update(thread_type=s.type, designation=label, thread_class=cls, form=s.form,
                      x_start=s.major, x_end=s.major, pitch=s.pitch)
        if s.type == "NPT":
            npt = npt_data(label)
            fields["x_start"] = npt.major_at_gauge_plane if internal else npt.major_small_end
            fields["x_end"] = npt_x_end(fields["x_start"], fields["start_z"], fields["end_z"], internal)
        if old_cls == "1A":
            notes.append(f"{old}: class 1A is no longer offered - converted to {cls}")
    else:
        major = float(data.get("major_diameter", 0.5))
        form = "acme" if str(data.get("thread_standard", "")).upper().startswith("ACME") else "60"
        fields.update(thread_type="Custom", designation="Custom", thread_class="", form=form,
                      x_start=major, x_end=major, pitch=pitch)
        if old:
            notes.append(f"{old}: not in the thread lists - converted to Custom (X {major:.4f})")
    fields["entry_angle"] = _LEGACY_INFEED.get(data.get("infeed_method", "flank"), 29.5)
    if fields["form"] in ("acme", "tr") and fields["entry_angle"]:
        fields["entry_angle"] = FORMS[fields["form"]][1]
    if internal:
        old_major = float(data.get("major_diameter", fields["x_start"]))
        old_depth = float(data.get("thread_depth", 0.0))
        fields["pilot_dia"] = (old_major - 2.0 * old_depth) if old_depth > 0 else (
            size(label).tap_drill[1] if label else 0.0)
    else:
        fields["pilot_dia"] = 0.0
    if float(data.get("chamfer_threads", 0.0) or 0.0) > 0:
        notes.append(f"{old or 'thread'}: pull-out chamfer dropped - Z end is where the tool pulls out")
    return fields, notes


def npt_x_end(x_start: float, z_start: float, z_end: float, internal: bool) -> float:
    """NPT: X end from X start and the Z length (1:16 on diameter). External
    threads grow toward the chuck (the pipe end is the small end); internal
    threads shrink going into the hole (the mouth is the large end)."""
    run = abs(z_start - z_end) * NPT_TAPER
    return x_start - run if internal else x_start + run


def params_from_fields(f: dict, internal: bool):
    """Fields dict (new format) -> ThreadingParams with the derived root offset."""
    from models.program import ThreadingParams
    d = derive(f["thread_type"], f["designation"], f.get("thread_class", ""), f.get("form", "60"),
               internal, f["pitch"])
    return ThreadingParams(
        designation=f["designation"], thread_type=f["thread_type"],
        thread_class=f.get("thread_class", ""), form=f.get("form", "60"), is_internal=internal,
        x_start=float(f["x_start"]), x_end=float(f["x_end"]),
        start_z=float(f["start_z"]), end_z=float(f["end_z"]), pitch=float(f["pitch"]),
        root_offset=d.root_offset, pilot_dia=float(f.get("pilot_dia", 0.0)) if internal else 0.0,
        num_passes=int(f["num_passes"]), spring_passes=int(f["spring_passes"]),
        num_starts=int(f.get("num_starts", 1)), entry_angle=float(f["entry_angle"]),
        spindle_rpm=float(f["spindle_rpm"]), tool_number=int(f["tool_number"]))
