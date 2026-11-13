"""Thread data (models/thread_data.py) against PUBLISHED table values.

Sources (2026-11-12): UN - ASME B1.1 tables (Machinery's Handbook); ISO metric 6g -
amesweb / optimas (ASME B1.13M = ISO 965-2); 4h - ISO 965-1 tolerance grades (roymech
worked example M12x1.25 4h); Tr 7e - DIN 103 table (amesweb); Acme 2G / 3G -
Machinery's Handbook 31st ed. tables 2b / 2c (ASME B1.5); NPT - ASME B1.20.1
(engineersedge / amesweb agree). Agreement to the tables' last digit (+-1 in that
digit where the standard rounds per size range).
"""
import pytest

from models import thread_data as td

IN = 1e-4 + 1e-9          # inch tables: last digit
MM = 0.001 + 1e-9         # mm tables: last digit


@pytest.mark.parametrize("label, cls, major, pd, root", [
    ("1/4-20 UNC", "2A", (0.2489, 0.2408), (0.2164, 0.2127), 0.1876),
    ("1/4-20 UNC", "3A", (0.2500, 0.2419), (0.2175, 0.2147), None),
    ("1/2-13 UNC", "2A", (0.4985, 0.4876), (0.4485, 0.4435), 0.4041),
    ("3/4-10 UNC", "2A", (0.7482, 0.7353), (0.6832, 0.6773), 0.6255),
])
def test_un_external(label, cls, major, pd, root):
    lim = td.limits(label, cls, False)
    assert (lim.major_max, lim.major_min) == pytest.approx(major, abs=IN)
    assert (lim.pd_max, lim.pd_min) == pytest.approx(pd, abs=IN)
    if root is not None:
        assert lim.root == pytest.approx(root, abs=IN)


@pytest.mark.parametrize("cls, pd", [("2B", (0.2175, 0.2224)), ("3B", (0.2175, 0.2211))])
def test_un_internal_root_is_the_basic_major(cls, pd):
    lim = td.limits("1/4-20 UNC", cls, True)
    assert lim.root == 0.25 and lim.root_offset == 0.0
    assert (lim.pd_min, lim.pd_max) == pytest.approx(pd, abs=IN)


@pytest.mark.parametrize("label, d, d2", [
    ("M6x1", (5.974, 5.794), (5.324, 5.212)),
    ("M10x1.5", (9.968, 9.732), (8.994, 8.862)),
    ("M12x1.75", (11.966, 11.701), (10.829, 10.679)),
    ("M20x2.5", (19.958, 19.623), (18.334, 18.164)),
])
def test_metric_6g(label, d, d2):
    lim = td.limits(label, "6g", False)
    assert (lim.major_max * 25.4, lim.major_min * 25.4) == pytest.approx(d, abs=MM)
    assert (lim.pd_max * 25.4, lim.pd_min * 25.4) == pytest.approx(d2, abs=MM)


def test_metric_4h():
    lim = td.limits("M12x1.25", "4h", False)
    assert (lim.major_max * 25.4, lim.major_min * 25.4) == pytest.approx((12.000, 11.868), abs=MM)
    assert (lim.pd_max * 25.4, lim.pd_min * 25.4) == pytest.approx((11.188, 11.103), abs=MM)
    # ISO 965-1 grade-4 tolerance widths (um): Td2 M6x1 71, M10x1.5 85, M12x1.75 95, M20x2.5 106
    for label, td2 in (("M6x1", 71), ("M10x1.5", 85), ("M12x1.75", 95), ("M20x2.5", 106)):
        lim = td.limits(label, "4h", False)
        assert (lim.pd_max - lim.pd_min) * 25400 == pytest.approx(td2, abs=1.0)
    assert td._td_major_um(1.75, 4) == 170 and td._td_major_um(1.0, 4) == 112


@pytest.mark.parametrize("label, d3, d4, drill", [
    ("Tr10x2", 7.500, 10.500, 8.0), ("Tr16x4", 11.500, 16.500, 12.0),
    ("Tr20x4", 15.500, 20.500, 16.0), ("Tr24x5", 18.500, 24.500, 19.0),
    ("Tr40x7", 32.000, 41.000, 33.0),
])
def test_trapezoidal(label, d3, d4, drill):
    assert td.limits(label, "7e", False).root * 25.4 == pytest.approx(d3, abs=MM)
    assert td.limits(label, "7H", True).root * 25.4 == pytest.approx(d4, abs=MM)
    assert td.size(label).tap_drill[1] * 25.4 == pytest.approx(drill, abs=MM)


@pytest.mark.parametrize("label, major, minor, pd2g, pd3g, int_major", [
    ("1/2-10 ACME", (0.5000, 0.4950), 0.3800, (0.4443, 0.4306), (0.4458, 0.4394), 0.5200),
    ("3/4-6 ACME", (0.7500, 0.7417), 0.5633, (0.6598, 0.6424), (0.6615, 0.6534), 0.7700),
    ("1-5 ACME", (1.0000, 0.9900), 0.7800, (0.8920, 0.8726), (0.8940, 0.8849), 1.0200),
    ("1-1/2-4 ACME", (1.5000, 1.4875), 1.2300, (1.3652, 1.3429), (1.3677, 1.3573), 1.5200),
])
def test_acme(label, major, minor, pd2g, pd3g, int_major):
    for cls, pd in (("2G", pd2g), ("3G", pd3g)):
        lim = td.limits(label, cls, False)
        assert (lim.major_max, lim.major_min) == pytest.approx(major, abs=IN)
        assert lim.root == pytest.approx(minor, abs=IN)
        assert (lim.pd_max, lim.pd_min) == pytest.approx(pd, abs=IN)
        assert td.limits(label, cls, True).root == pytest.approx(int_major, abs=IN)


@pytest.mark.parametrize("label, e0, e1, l1, h", [
    ("1/8 NPT", 0.36351, 0.37360, 0.1615, 0.02963),
    ("1/4 NPT", 0.47739, 0.49163, 0.2278, 0.04444),
    ("3/8 NPT", 0.61201, 0.62701, 0.2400, 0.04444),
    ("1/2 NPT", 0.75843, 0.77843, 0.3200, 0.05714),
    ("1 NPT", 1.21363, 1.23863, 0.4000, 0.06957),
    ("2 NPT", 2.26902, 2.29627, 0.4360, 0.06957),
])
def test_npt(label, e0, e1, l1, h):
    n = td.npt_data(label)
    assert (n.e0, n.e1, n.l1, n.h) == pytest.approx((e0, e1, l1, h), abs=1e-5)


def test_every_listed_size_resolves_for_every_class():
    for t in td.THREAD_TYPES:
        for s in td.sizes(t):
            for internal in (False, True):
                for cls in td.classes(t, internal):
                    lim = td.limits(s.label, cls, internal)
                    assert (lim.root < s.major) != internal or lim.root == s.major


def test_derived_depth_for_custom_uses_the_form():
    d = td.derive("Custom", "Custom", "", "60", False, 0.05)
    assert d.root_offset == pytest.approx(-2 * 0.613435 * 0.05)


def test_legacy_block_converts():
    fields, notes = td.from_saved({"designation": "M10×1.5", "major_diameter": 0.39,
                                   "pitch": 1.5 / 25.4, "thread_depth": 0.036, "start_z": 0.05,
                                   "end_z": -0.5, "infeed_method": "radial", "num_passes": 6,
                                   "spring_passes": 1, "chamfer_threads": 1.0,
                                   "spindle_rpm": 300, "tool_number": 3}, False)
    assert fields["designation"] == "M10x1.5" and fields["thread_class"] == "6g"
    assert fields["entry_angle"] == 0.0 and any("chamfer" in n for n in notes)
