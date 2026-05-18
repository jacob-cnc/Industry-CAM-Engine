import math
from BasePostPro import BasePostPro
import FreeCAD as App


class PostPro(BasePostPro):
    Name = "ITnc530"
    Ext = "h"

    def __init__(self):
        super().__init__()

    def writeHeader(self):
        header = ""
        header += "BEGIN PGM ITNC530 MM\n"

        return header

    def writeFooter(self):
        footer = ""
        footer += "END PGM ITNC530 MM\n"

        return footer

    def writeComment(self, comment):
        return f"; {comment}"

    def blockForm(self, stock):
        bb = stock.Shape.BoundBox
        blk = f"BLK FORM 01 X{bb.XMin:.3f} Y{bb.YMin:.3f} Z{bb.ZMin:.3f}\n"
        blk += f"BLK FORM 02 X{bb.XMax:.3f} Y{bb.YMax:.3f} Z{bb.ZMax:.3f}\n"
        return blk

    def transformGCode(self, gcode):
        current_move = None
        current_pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
        lines = gcode.split('\n')
        retour = []

        def linear_move(line: str, rapid: bool = None):
            if rapid is not None:
                current_move = 'G0' if rapid else 'G1'

            if line.startswith('G'):
                space = line.index(' ')
                new_line = line[space+1:]
            else:
                new_line = line

            for axis in ['X', 'Y', 'Z']:
                if axis in new_line:
                    parts = new_line.split(axis)
                    coord_part = parts[1]
                    coord_str = ''
                    for c in coord_part:
                        if c in ' XYZFMG':
                            break
                        coord_str += c
                    if coord_str != '':
                        current_pos[axis] = float(coord_str)

            if 'G40' in line:
                new_line = new_line.replace('G40', '')
                new_line += ' R0'

            if 'G41' in line:
                new_line = new_line.replace('G41', '')
                new_line += ' RL'

            if 'G42' in line:
                new_line = new_line.replace('G42', '')
                new_line += ' RR'

            if 'F' in new_line:
                parts = new_line.split('F')
                # remove feed from line
                new_line = parts[0]
                feed = parts[1]
                new_line += f' F{feed}'

            if current_move == 'G0':
                new_line += ' FMAX'
            return 'L ' + new_line

        for i in range(len(lines)):
            if lines[i].startswith('(') and lines[i].endswith(')'):
                lines[i] = lines[i][1:-1]  # Remove parentheses
                lines[i] = self.writeComment(lines[i])
            elif lines[i].startswith(('G0', 'G00')):
                lines[i] = linear_move(lines[i], rapid=True)
            elif lines[i].startswith(('G1', 'G01')):
                lines[i] = linear_move(lines[i], rapid=False)
                # current_move = 'G1'
                # lines[i] = lines[i].replace('G1', 'L ')
                # feed = None
                # if 'F' in lines[i]:
                #     parts = lines[i].split('F')
                #     # remove feed from line
                #     lines[i] = parts[0]
                #     feed = parts[1]
                # if 'G40' in lines[i]:
                #     lines[i] = lines[i].replace('G40', '')
                #     lines[i] += ' R0'
                # if 'G41' in lines[i]:
                #     # parts = lines[i].split('F')
                #     # lines[i] = parts[0] + ' F' + parts[1]
                #     lines[i] = lines[i].replace('G41', '')
                #     lines[i] += ' RL'
                # if 'G42' in lines[i]:
                #     lines[i] = lines[i].replace('G42', '')
                #     lines[i] += ' RR'
                # if feed is not None:
                #    lines[i] += f' F{feed}'
            elif lines[i].startswith(('X', 'Y', 'Z')):
                lines[i] = linear_move(lines[i], rapid=None)

            retour.append(lines[i])
        return '\n'.join(retour)

    def toolChange(self, tool, cam_project):
        tool_id = getattr(tool, 'Id', None)
        tool_name = getattr(tool, 'Label', None)
        spindle = getattr(tool, 'Speed', None).Value
        Feed = getattr(tool, 'Feed', None).Value
        return f"TOOL CALL {tool_id} Z S{spindle} DL+0 DR+0\nL R0 F{Feed} M3\n"

    def G81(self, obj):
        doc = App.ActiveDocument
        geom = doc.getObject(obj.DrillGeometryName)
        if geom and hasattr(geom, 'DrillPositions'):
            points = geom.DrillPositions
        safe_z = getattr(obj, 'SafeHeight', 5.0).Value
        final_z = getattr(obj, 'FinalDepth', -5.0).Value

        gcode_lines = ""
        gcode_lines += (f"CYCL DEF 200 PERCAGE \n\
            Q200={safe_z};DISTANCE D'APPROCHE\n\
            Q201={final_z};PROFONDEUR\n\
            Q206=250;AVANCE PLONGÉE PROF.\n\
            Q202={math.fabs(final_z)};PROFONDEUR DE PASSE\n\
            Q210=0;TEMPO. EN HAUT\n\
            Q203=+0;COORD. SURFACE PIÈCE\n\
            Q204=100;SAUT DE BRID\n\
            Q211=0.1;TEMPO. AU FOND\n")
        for pt in points:
            gcode_lines += (f"L X{pt.x:.3f} Y{pt.y:.3f} FMAX M99\n")

        return gcode_lines
