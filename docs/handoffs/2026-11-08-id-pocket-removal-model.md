# Follow-up: model the interior pocket/removal region explicitly

Status: proposed; design/investigation not started. Priority: after the immediate
GCH counterbore wall/shoulder cleanup correction. No general pocket solution has
been approved or validated by the current open-contour fix.

## Owner request (verbatim)

> leave a note that we should investigate defining the pocket which we are removing more carefully, I think relying on the open contour could bite us with more complicated interior geometry - but right now I want to prioritize this specific case because it’s relevant to the GCH job I’m doing at the moment

The owner accepts the open-contour solution for the immediate case while retaining
this concern as an active follow-up, not as a resolved modeling decision.

## Current evidence

GCH case: stock OD4, pilot diameter2.995, stock backZ-1, user contour
(X3.117,Z0)->(X3.117,Z-.568)->(X2.995,Z-.568). Cleanup's duplicate closed-face
construction retraced the terminal shoulder, offsetting failed, and the failure
was silently converted to no cleanup. Bottom face clipping/filtering also lost
the shoulder. The targeted correction offsets the actual open contour in the
geometry layer and clips the wire while retaining real boundary edges.

This is a path-construction correction, not proof that complex interior pockets,
remaining stock, access, or rapid safety are fully modeled. In particular, the
existing remaining-material validation gap R-001 stays open.

## Investigation to perform

- Define pocket/removal regions from actual stock, pilot geometry/depth, contour,
  operation extent and retained material. Distinguish the keep region, removable
  material and air; do not swap their meanings implicitly through closure choice.
- Determine how to retain semantic identity of authored walls/shoulders versus
  artificial closure and clipping boundaries, including arcs and corner breaks.
- Evaluate re-entrant/stepped interiors, narrow features, disconnected regions,
  offset collapse, tool access/body clearance and changes in remaining material.
- Compare open-contour offsets with offsets derived from a properly defined pocket.
  Choose based on kernel evidence and representative fixtures, not convention.
- Document required model/API changes in an ADR before implementation, including
  interaction with finishing passes, spring repeats and sequential-stock validation.

Preserve owner-authored final dimensions and diameter/radius boundaries. Keep the
GCH regression as a required baseline alongside broader interior fixtures. Powered
machine verification remains separate from geometry and software verification.
