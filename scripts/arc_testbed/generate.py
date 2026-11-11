"""Generate G-code for saved profile JSONs with whatever repo is on PYTHONPATH.

usage: gen.py OUTDIR file.json [...]
Writes OUTDIR/<name>[__b<id>].ngc or .err. Fixed tools (no tool table) so
main vs branch differ only by engine code.
"""
import json, os, sys, traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute

OD_TOOL = ToolDef(tool_number=4, nose_radius=0.016, tip_angle=80.0, edge_length=0.375,
                  orientation=ToolOrientation(2), direction=ToolDirection.RIGHT,
                  tool_type=ToolType.TURNING, description="CNMG")
ID_TOOL = ToolDef(tool_number=1, nose_radius=0.0157, tip_angle=80.0, edge_length=0.375,
                  orientation=ToolOrientation(3), direction=ToolDirection.RIGHT,
                  tool_type=ToolType.BORING, description="CCMT bar")


def blocks_of(d):
    if "blocks" in d:
        for b in d["blocks"]:
            if b.get("block_type") in ("od_profile", "id_profile"):
                yield f"b{b['block_id']}", b["block_type"].split("_")[0], b["params"], d.get("stock_back_face_z")
    elif d.get("block_type") in ("OD Profile", "ID Profile"):
        yield "", d["block_type"].split()[0].lower(), d, None


def gen(mode, p, back_z):
    st, ro, fi = p.get("stock", {}), p.get("roughing", {}), p.get("finishing", {})
    tool = OD_TOOL if mode == "od" else ID_TOOL
    prof, stock, rp, fp = build_from_fields(
        segments=p.get("segments", []), stock_dia=st.get("diameter", 1.0),
        x_start=st.get("x_start", 0.0), z_start=st.get("z_start", 0.1),
        z_end=st.get("z_end", -1.0), stock_back_z=back_z, mode=mode,
        pilot_hole_dia=st.get("pilot_hole_dia", 0.0), doc_dia=ro.get("doc_dia", 0.03),
        feed=ro.get("feed", 0.005), strategy=ro.get("strategy", "staircase"),
        fin_allowance=ro.get("fin_allowance", 0.01), peck_enabled=ro.get("peck_enabled", False),
        peck_length=ro.get("peck_length"), spindle_rpm=ro.get("spindle_rpm", 1200.0),
        finish_passes=fi.get("passes", 1), finish_doc_dia=fi.get("doc_dia", 0.002),
        finish_feed=fi.get("feed", 0.003), finish_spring_pass=bool(fi.get("spring_pass", False)),
        tool_def=tool, x_park=st.get("x_park", 3.0), z_park=st.get("z_park", 3.0),
        corner_breaks=p.get("corner_breaks", []))
    res = execute(prof, stock, tool, rp, fp)
    if res.plan_result is None:
        raise RuntimeError("pipeline blocked: " + "; ".join(
            v.message for v in res.validations if v.severity.value == "error"))
    return GCodeWriter().write(res.plan_result)


out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for path in sys.argv[2:]:
    d = json.load(open(path))
    base = os.path.splitext(os.path.basename(path))[0].replace(" ", "_")
    for tag, mode, p, back_z in blocks_of(d):
        name = base + (f"__{tag}" if tag else "")
        try:
            code = gen(mode, p, back_z)
            # strip timestamp-ish header lines so diffs show engine changes only
            code = "\n".join(l for l in code.splitlines() if "Generated" not in l and "Date" not in l)
            open(os.path.join(out, name + ".ngc"), "w").write(code + "\n")
            print("OK  ", name)
        except Exception as e:
            open(os.path.join(out, name + ".err"), "w").write(traceback.format_exc())
            print("ERR ", name, type(e).__name__, str(e).splitlines()[0][:150])
