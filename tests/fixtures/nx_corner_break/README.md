# NX corner-break reference parts

Owner-made in Siemens NX. Units mm, turning axis = model X, front face at X0.
Each pair is the same part sharp and after NX applied chamfers/fillets, used as
ground truth for the corner-break engine.

| Fixture | Original NX export | Use |
|---|---|---|
| `sharp.stp` | `184223-001_01-Corner Break Test.stp` | OD, sharp profile |
| `broken.stp` | `184223-001_01-Corner Break Test_1 MODIFIED.stp` | OD, breaks applied (V1-V10) |
| `id_sharp.stp` | `184223-001_01-Corner Break Test_1 ID.stp` | ID, sharp profile |
| `id_broken.stp` | `184223-001_01-Corner Break Test_1 ID MODIFIED.stp` | ID, breaks applied |

OD pair: validated by `tests/unit/test_corner_breaks_od_nx.py`.

ID pair: added 2026-11-10, **not yet used by any test**. Both load with
`build123d.import_step`. Envelope Ø36 x 33 mm. Sharp: 13 straight faces, profile
radii 10.5-18 mm. Broken: 16 straight + 3 toroidal (fillet) faces. Profile
points and break sizes have not been extracted yet. The ID corner-break
solver (separate from OD) is the next step that will read these.
