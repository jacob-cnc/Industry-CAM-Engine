"""Robust 2D offsets for the geometry kernel (OCCT via Build123d).

The engine offsets profiles with sharp (Kind.INTERSECTION) joins so convex
corners keep their extended-corner shape. OCCT's intersection-join offset
returns a NULL shape for some valid outlines - notably two arcs meeting at
an angle, which is exactly what an NX-style trimmed corner break leaves
(a fillet cut short against a neighbouring fillet). The raw result is a
"Null TopoDS_Shape object" error deep inside Build123d.

These helpers try the sharp join first and fall back to rounded joins
(Kind.ARC, the true constant-distance offset - every point at exactly the
requested distance) only when the sharp join fails. If both fail, a
RuntimeError with a readable message replaces the kernel error.
"""

import logging

from build123d import Kind

logger = logging.getLogger(__name__)

_HINT = ("This usually means two corner breaks meet at an angle (a break "
         "that was trimmed to fit). Smoothing that trim, or changing one of "
         "the break sizes, avoids it.")


def _has_shape(result) -> bool:
    try:
        faces = result.faces() if hasattr(result, "faces") else []
        edges = result.edges() if hasattr(result, "edges") else []
        return bool(faces) or bool(edges)
    except Exception:
        return False


class KernelOffsetError(RuntimeError):
    """A readable offset failure. The raw kernel error is kept: chained as
    __cause__ (full traceback in the error dialog's technical details and
    the log) and summarised in .kernel_detail."""

    def __init__(self, message: str, kernel_detail: str):
        super().__init__(f"{message}\n\nKernel detail: {kernel_detail}")
        self.kernel_detail = kernel_detail


def _attempt(make, what: str):
    """Try sharp joins, then rounded joins. Returns the first non-empty
    result; raises KernelOffsetError (chained to the last kernel exception)
    when both fail."""
    errors, last_exc = [], None
    for kind in (Kind.INTERSECTION, Kind.ARC):
        try:
            result = make(kind)
            if _has_shape(result):
                if kind is not Kind.INTERSECTION:
                    logger.warning("Offset of %s: sharp-join offset failed (%s); used "
                                   "rounded joins", what, errors[-1] if errors else "")
                return result
            errors.append(f"{kind.name}: empty result")
        except Exception as exc:              # OCCT null shape and friends
            errors.append(f"{kind.name}: {type(exc).__name__}: {exc}")
            last_exc = exc
            logger.debug("Offset of %s with %s joins failed", what, kind.name,
                         exc_info=True)
    raise KernelOffsetError(
        f"The geometry kernel could not offset the {what}. {_HINT}",
        "; ".join(errors)) from last_exc


def offset_face(face, amount: float, what: str = "profile"):
    """Offset a Build123d face by `amount` (sharp joins, rounded fallback)."""
    from build123d import offset as b3d_offset
    return _attempt(lambda kind: b3d_offset(face, amount=amount, kind=kind),
                    f"{what} by {amount:.4f}")


def offset_wire(wire, amount: float, *, side, closed: bool, what: str = "contour"):
    """Offset an open/closed Build123d wire (sharp joins, rounded fallback)."""
    return _attempt(
        lambda kind: wire.offset_2d(amount, kind=kind, side=side, closed=closed).clean(),
        f"{what} by {amount:.4f}")
