import FreeCAD as App


class BasePostPro:
    Ext = ""

    def __init__(self):
        pass

    def writeComment(self, comment):
        return f"({comment})"

    def writeHeader(self):
        h = []
        h.append("%")
        h.append("O0001")
        h.append("G21 (mm)")
        h.append("G90 (absolute programming)")
        h.append("G40 (cutter radius compensation off)")
        h.append("G80 (cancel canned cycle)")
        h.append("G17 (XY plane selection)")
        return '\n'.join(h)

    def transformGCode(self, gcode):
        return gcode

    def writeFooter(self):
        f = []
        f.append("M30 ")
        return '\n'.join(f)

    def blockForm(self, stock):
        bb = stock.Shape.BoundBox
        s = f"{bb.XMin},{bb.YMin},{bb.ZMin} to {bb.XMax},{bb.YMax},{bb.ZMax}"
        return f"{self.writeComment(s)}"

    def toolChange(self, tool, cam_project):
        tool_id = getattr(tool, 'Id', None)
        tool_name = getattr(tool, 'Label', None)
        spindle = getattr(tool, 'SpindleSpeed', None)
        feed = getattr(tool, 'FeedRate', None)

        gcode_lines = []
        gcode_lines.append(f"(Changement d'outil: {tool_name if tool_name else ''})")
        gcode_lines.append(f"M6 T{tool_id}")
        if spindle:
            gcode_lines.append(f"S{spindle} M3")
            current_spindle = spindle
        return '\n'.join(gcode_lines)

    def G81(self, obj):
        doc = App.ActiveDocument
        geom = doc.getObject(obj.DrillGeometryName)
        if geom and hasattr(geom, 'DrillPositions'):
            points = geom.DrillPositions

        safe_z = getattr(obj, 'SafeHeight').Value
        gcode_lines = []
        gcode_lines.append(f"G81 R{safe_z} Z{obj.FinalDepth.Value} F{obj.FeedRate.Value}")
        for pt in points:
            gcode_lines.append(f"G0 X{pt.x} Y{pt.y} Z{safe_z}")
        gcode_lines.append(f"G80")
        return '\n'.join(gcode_lines)

    def G84(self, obj):
        doc = App.ActiveDocument
        geom = doc.getObject(obj.DrillGeometryName)
        if geom and hasattr(geom, 'DrillPositions'):
            points = geom.DrillPositions

        safe_z = getattr(obj, 'SafeHeight').Value
        spindle = getattr(obj, 'SpindleSpeed', None)
        gcode_lines = []
        gcode_lines.append(f"S{spindle} M3")
        gcode_lines.append(f"G84 R{safe_z} Z{obj.FinalDepth.Value} F{obj.FeedRate.Value}")
        for pt in points:
            gcode_lines.append(f"G0 X{pt.x} Y{pt.y} Z{safe_z}")
        gcode_lines.append(f"G80")
        return '\n'.join(gcode_lines)
