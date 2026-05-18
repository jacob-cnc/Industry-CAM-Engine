import FreeCAD as App
import BasePostPro

Name = "Siemens828D"

Ext = "MPF"


class PostPro(BasePostPro.BasePostPro):
    def __init__(self):
        super().__init__()

    def writeHeader(self):
        return ""

    def coolantModeToCode(self, mode):
        if mode == "Off":
            return "9"
        elif mode == "Flood":
            return "8"
        elif mode == "Mist":
            return "7"
        else:
            return "9"  # Default to Off if unknown mode

    def transformGCode(self, gcode):
        lines = gcode.split('\n')
        retour = []
        for i in range(len(lines)):
            if lines[i].startswith('(') and lines[i].endswith(')'):
                lines[i] = lines[i][1:-1]  # Remove parentheses
                lines[i] = self.writeComment(lines[i])
            retour.append(lines[i])
        return '\n'.join(retour)

    def writeComment(self, comment):
        return f"; {comment}"

    def blockForm(self, stock):
        bb = stock.Shape.BoundBox

        return f"WORKPIECE(,\"\",,\"BOX\",112,{bb.ZMax},{bb.ZMin},-80,{bb.XMin},{bb.YMin},{bb.XMax},{bb.YMax})"

    def toolChange(self, tool, cam_project):
        tool_id = getattr(tool, 'Id', None)
        tool_name = getattr(tool, 'Name', None)
        spindle = getattr(tool, 'Speed', None).getValueAs("mm/min")  # FIXME Speed
        return f"\nT=\"{tool_name}\" D1\nM6\nS{spindle} M3\n"

    def G81(self, obj):
        doc = App.ActiveDocument
        geom = doc.getObject(obj.DrillGeometryName)
        if geom and hasattr(geom, 'DrillPositions'):
            points = geom.DrillPositions

        safe_z = getattr(obj, 'SafeHeight', 5.0).Value
        final_z = getattr(obj, 'FinalDepth', -5.0).Value
        dwell = getattr(obj, 'DwellTime', 0.0)
        coolant = getattr(obj, 'CoolantMode', False)
        planDeRetrait = safe_z
        DistSecurite = safe_z
        z0 = None
        Speed = getattr(obj, 'SpindleSpeed', None).getValueAs("mm/min")  # FIXME Speed
        Feed = getattr(obj, 'FeedRate', None).getValueAs("mm/min")
        gcode_lines = f"S{Speed}\n"
        gcode_lines += f"F{Feed}\n"
        gcode_lines += f"M{self.coolantModeToCode(coolant)}\n"
        for pt in points:
            if z0 is None or z0 != pt.z:
                z0 = pt.z
                gcode_lines += (f"CYCLE81({z0 + planDeRetrait},{z0},{DistSecurite},{final_z},,{dwell},0,1,12)\n")
            gcode_lines += (f"G0 X{pt.x:.3f} Y{pt.y:.3f} \n")
        gcode_lines += "MCALL\n"
        return gcode_lines

    def G84(self, obj):
        doc = App.ActiveDocument
        geom = doc.getObject(obj.DrillGeometryName)
        if geom and hasattr(geom, 'DrillPositions'):
            points = geom.DrillPositions

        safe_z = getattr(obj, 'SafeHeight', 5.0).Value
        final_z = getattr(obj, 'FinalDepth', -5.0).Value
        coolant = getattr(obj, 'CoolantMode', False)
        planDeRetrait = safe_z
        DistSecurite = safe_z
        z0 = None
        Speed = getattr(obj, 'SpindleSpeed', None).getValueAs("mm/min")  # FIXME Speed
        Feed = getattr(obj, 'FeedRate', None).getValueAs("mm/min")
        gcode_lines = f"S{Speed}\n"
        gcode_lines += f"F{Feed}\n"
        gcode_lines += f"M{self.coolantModeToCode(coolant)}\n"
        for pt in points:
            if z0 is None or z0 != pt.z:
                z0 = pt.z
                gcode_lines += (f"CYCLE84({z0 + planDeRetrait},{z0},{DistSecurite},{final_z},,1,12)\n")
            gcode_lines += (f"G0 X{pt.x:.3f} Y{pt.y:.3f} \n")
        gcode_lines += "MCALL\n"
        return gcode_lines
