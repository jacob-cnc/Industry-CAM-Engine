"""Offset join policy (hand-math inquiry F4, owner decision 2026-11-12).

Contour roughing asks the kernel for ROUNDED joins on purpose; every other
offset asks for sharp joins and, when OCCT can only build rounded ones, that
fallback is recorded and reaches the operator as one Generate WARNING.
"""
import pytest
from build123d import Kind, Rectangle

from geometry import kernel_offset
from geometry.kernel_offset import KernelOffsetError, offset_face, record_join_fallbacks
from models.validation import PipelineResult, PipelineStatus, Severity
from pipeline.pipeline import _with_join_fallback_note


def _sharp_fails(kind):
    """A stand-in for an OCCT offset whose sharp join returns a null shape."""
    if kind is Kind.INTERSECTION:
        raise ValueError("Null TopoDS_Shape object")
    return Rectangle(1.0, 1.0)


def test_rounded_policy_uses_arc_joins_only():
    kinds = []
    kernel_offset._attempt(lambda k: kinds.append(k) or Rectangle(1, 1), "x", "rounded")
    assert kinds == [Kind.ARC]


def test_sharp_policy_tries_sharp_first():
    kinds = []
    kernel_offset._attempt(lambda k: kinds.append(k) or Rectangle(1, 1), "x", "sharp")
    assert kinds == [Kind.INTERSECTION]


def test_unknown_policy_is_refused():
    with pytest.raises(ValueError):
        kernel_offset._attempt(lambda k: Rectangle(1, 1), "x", "bevel")


def test_sharp_fallback_is_recorded_while_listening():
    with record_join_fallbacks() as found:
        kernel_offset._attempt(_sharp_fails, "cleanup/finish contour by 0.0100", "sharp")
    assert found == ["cleanup/finish contour by 0.0100"]


def test_fallback_outside_a_recording_block_is_only_logged():
    kernel_offset._attempt(_sharp_fails, "x", "sharp")       # must not raise
    assert kernel_offset._fallbacks.get() is None


def test_rounded_request_is_not_a_fallback():
    with record_join_fallbacks() as found:
        kernel_offset._attempt(lambda k: Rectangle(1, 1), "x", "rounded")
    assert found == []


def test_rounded_offset_keeps_constant_distance_at_convex_corners():
    """A unit square offset by .1 with rounded joins: area 1 + 4*.1 + pi*.01."""
    import math
    out = offset_face(Rectangle(1.0, 1.0), 0.1, joins="rounded")
    assert out.area == pytest.approx(1.0 + 0.4 + math.pi * 0.01, abs=1e-6)
    sharp = offset_face(Rectangle(1.0, 1.0), 0.1, joins="sharp")
    assert sharp.area == pytest.approx(1.2 ** 2, abs=1e-6)


def test_both_kinds_failing_raises_readable_error():
    def never(kind):
        raise ValueError("Null TopoDS_Shape object")
    with pytest.raises(KernelOffsetError):
        kernel_offset._attempt(never, "x", "sharp")


def _result(status=PipelineStatus.SUCCESS):
    return PipelineResult(plan_result=None, validations=[], warnings_overridden=False, status=status)


def test_no_fallbacks_leaves_result_untouched():
    r = _result()
    assert _with_join_fallback_note(r, []) is r


def test_fallbacks_become_one_operator_warning():
    r = _with_join_fallback_note(_result(), ["finished part (finish allowance band) by 0.0050",
                                             "cleanup/finish contour by 0.0100",
                                             "cleanup/finish contour by 0.0200"])
    assert r.status == PipelineStatus.SUCCESS_WITH_WARNINGS
    assert len(r.validations) == 1
    w = r.validations[0]
    assert w.severity == Severity.WARNING
    assert "3 offset(s)" in w.message
    assert "cleanup/finish contour" in w.message and "finish allowance band" in w.message
    assert "No gouge" in w.consequence


def test_blocked_result_stays_blocked():
    r = _with_join_fallback_note(_result(PipelineStatus.BLOCKED_BY_ERROR), ["x by 1"])
    assert r.status == PipelineStatus.BLOCKED_BY_ERROR


def test_contour_roughing_kernel_failure_raises_instead_of_stopping(monkeypatch):
    """Before 2026-11-12 a failed offset returned None and roughing silently ended."""
    import planners.contour_roughing_planner as crp

    def boom(*a, **k):
        raise KernelOffsetError("could not offset", "INTERSECTION: null")
    monkeypatch.setattr(crp, "offset_face", boom)
    with pytest.raises(KernelOffsetError):
        crp.ContourRoughingPlanner()._do_offset(Rectangle(1, 1), 0.1)


def test_contour_roughing_asks_for_rounded_joins(monkeypatch):
    import planners.contour_roughing_planner as crp
    seen = {}

    def spy(face, amount, what="profile", *, joins="sharp"):
        seen["joins"] = joins
        return face
    monkeypatch.setattr(crp, "offset_face", spy)
    crp.ContourRoughingPlanner()._do_offset(Rectangle(1, 1), 0.1)
    assert seen["joins"] == "rounded"
