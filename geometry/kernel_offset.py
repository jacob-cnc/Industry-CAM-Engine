"""Robust 2D offsets for the geometry kernel (OCCT via Build123d).

Join policy (owner decision 2026-11-12, hand-math inquiry F4):

  joins="rounded"  Kind.ARC only - the true constant-distance offset (every
                   point exactly `amount` from the source). Contour roughing
                   uses this deliberately: it is the path a round nose keeps
                   to the allowance, and OCCT computes it reliably.
  joins="sharp"    Kind.INTERSECTION (convex corners extended sharp), falling
                   back to rounded when OCCT cannot build it. Each fallback is
                   recorded (see record_join_fallbacks) so the pipeline can
                   tell the operator; it is no longer only a log line.

The engine offsets the finish-allowance keep zone and the cleanup/finish
contours with sharp joins so convex corners keep their extended-corner shape. OCCT's intersection-join offset
returns a NULL shape for some valid outlines - notably two arcs meeting at
an angle, which is exactly what an NX-style trimmed corner break leaves
(a fillet cut short against a neighbouring fillet). The raw result is a
"Null TopoDS_Shape object" error deep inside Build123d.

These helpers try the sharp join first and fall back to rounded joins
(Kind.ARC, the true constant-distance offset - every point at exactly the
requested distance) only when the sharp join fails. If both fail, a
RuntimeError with a readable message replaces the kernel error.
"""

import contextlib
import contextvars
import logging

from build123d import Kind

logger = logging.getLogger(__name__)

# Fallback records for the current planning run (None = nobody is listening).
_fallbacks: contextvars.ContextVar = contextvars.ContextVar("join_fallbacks", default=None)


@contextlib.contextmanager
def record_join_fallbacks():
    """Collect a readable line for every sharp-join offset that had to use
    rounded joins inside this block. Yields the (growing) list."""
    found: list = []
    token = _fallbacks.set(found)
    try:
        yield found
    finally:
        _fallbacks.reset(token)

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


_KINDS = {"sharp": (Kind.INTERSECTION, Kind.ARC), "rounded": (Kind.ARC,)}


def _attempt(make, what: str, joins: str):
    """Try the policy's join kinds in order. Returns the first non-empty
    result; raises KernelOffsetError (chained to the last kernel exception)
    when all fail."""
    if joins not in _KINDS:
        raise ValueError(f"joins must be one of {sorted(_KINDS)}, not {joins!r}")
    errors, last_exc = [], None
    for kind in _KINDS[joins]:
        try:
            result = make(kind)
            if _has_shape(result):
                if errors:                    # a sharp request ended up rounded
                    logger.warning("Offset of %s: sharp-join offset failed (%s); used "
                                   "rounded joins", what, errors[-1])
                    found = _fallbacks.get()
                    if found is not None:
                        found.append(what)
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


def offset_face(face, amount: float, what: str = "profile", *, joins: str = "sharp"):
    """Offset a Build123d face by `amount` with the given join policy."""
    from build123d import offset as b3d_offset
    return _attempt(lambda kind: b3d_offset(face, amount=amount, kind=kind),
                    f"{what} by {amount:.4f}", joins)


def offset_wire(wire, amount: float, *, side, closed: bool, what: str = "contour",
                joins: str = "sharp"):
    """Offset an open/closed Build123d wire with the given join policy."""
    return _attempt(
        lambda kind: wire.offset_2d(amount, kind=kind, side=side, closed=closed).clean(),
        f"{what} by {amount:.4f}", joins)
