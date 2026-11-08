# Derived Operation Z End and independent physical stock back face

Classification: motion-affecting; software verification only. Based on
a7a8280 (the ID finish-contour correction), with machine work on Claude's
separate compound-routing branch left untouched.

## Owner-approved behavior

Operation Z End is read-only and derived from the active contour block. It is
not an approach/retract coordinate or the physical stock length. A separate
editable Stock Back Face is shared across the program's profile blocks.

For the owner's example, the bore contour ends at Z-0.568 while the stock back
face remains Z-1.000. Geometry/zone_builder constructs the actual open contour
with the same kernel construction used for zones, and queries its bounding box
for the lowest Z, including circular-arc extrema between entered endpoints.
Corner breaks use the same geometry conversion as zone construction.

Model building recomputes operation depth even if saved fields or API callers
supply a stale legacy z_end value. The validator checks depth against the
kernel contour instead of demanding the last endpoint be the deepest point.
StockDef.z_end remains operation extent for planner compatibility;
back_face_z carries physical stock extent. Material behind the operation is
unioned into the protected finished-part zone, so it is not silently discarded
by the shorter operation. Roughing remains bounded by operation depth.

## UI and file compatibility

- Contour edits and corner-break changes refresh the read-only field.
- Empty or invalid contours display no usable depth rather than retaining an
  earlier block's value. Block selection reloads and recalculates depth.
- Stock Back Face is independent and persists at program level as the additive
  version-2 JSON key stock_back_face_z. It does not change when switching blocks.
- Legacy single-block files retain their old Z End as stock extent, then derive
  operation depth. Old multiblock files use their deepest saved stock Z End as
  the physical extent. A user should check that extent against the actual blank;
  older files never distinguished those meanings.
- Stock ending in front of the operation, or a non-finite stock depth, is rejected.

## Verification and limits

Focused tests cover typing prevention, shallower edits, clearing, block loading,
shared-stock persistence, legacy loading, arc extrema, stale API Z End values,
invalid stock depth, and retained material below the cut. OD and ID are both
exercised with staircase and offset-contour roughing. The eight-tab mock GUI
also starts and completes its event loop.

Existing six quadrant-arc failures remain unrelated. Architecture analysis
retains its 69 existing errors; it additionally flags contour_z_end and the
planner's _get_offset_contour as a possible dual implementation. These perform
different operations (a kernel bounds query versus offset-pass retrieval).

## Machine commissioning gate

Claude reported live G8 radius mode while the writer emits diameter X words
without selecting G7. Owner has been informed; this commit changes neither
writer nor machine INI. Resolve that modal mismatch and X touch-off implications
with Claude before any generated program is bench-run.

After that gate, review the exact commit and regenerated program, confirm stock
back face and pilot depth, preview both strategies, and verify that no cutting
move extends below the intended operation. Physical tests require owner-approved
clearances, conservative limits and single-block checks with physical E-stop
available. Stop on unexpected movement, clearance, or following error. Preserve
tool.tbl and machine-local offsets. Rollback to the previously machine-tested
commit without overwriting that local state. No deployment or machine verification
is claimed by the software tests.
