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

ID pair: added 2026-11-10, validated by `tests/unit/test_corner_breaks_id_nx.py`
(same vertex solver as OD). Ø36 bar, blind stepped bore; breaks V1 C1, V2 R0.5,
V3 R0.25, V4 C1, V6 R2, V7 C2. The full part does not generate yet: its two
internal undercuts trip the retract-routing gouge check (pre-existing).
