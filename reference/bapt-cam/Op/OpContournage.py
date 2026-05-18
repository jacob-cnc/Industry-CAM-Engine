import enum
from BaptPath import GcodeEditorTaskPanel
from Op.BaseOp import baseOpViewProviderProxy
import BaptUtilities
import FreeCAD as App
import FreeCADGui as Gui
from Op.BaseOp import baseOp
import Part
from utils import Contour, GcodeWriter
import PySide.QtGui as QtGui
import PySide.QtCore as QtCore

import math
import sys

# compensation = ["Ordinateur", "Machine", "Ordinateur + G41/G42", "Aucune"]


class compensation(enum.Enum):
    Ordinateur = 0
    Machine = 1
    Ordinateur_G41_G42 = 2
    Aucune = 3

    def __repr__(self): return f"{self.name}"


approach_types = ["Tangentielle", "Perpendiculaire", "Perp+Arc", "Hélicoïdale"]
retract_types = ["Tangentielle", "Perpendiculaire", "Verticale"]


class ContournageCycle(baseOp):
    """Représente un cycle d'usinage de contournage"""

    def __init__(self, obj):
        """Initialise l'objet de cycle de contournage"""
        # Ajouter les propriétés

        self.Type = "ContournageCycle"
        super().__init__(obj)

        # Propriétés pour les paramètres d'usinage
        if not hasattr(obj, "ToolDiameter"):
            obj.addProperty("App::PropertyLength", "ToolDiameter", "Tool", "Diamètre de l'outil")
            obj.ToolDiameter = 6.0

        if not hasattr(obj, "CutDepth"):
            obj.addProperty("App::PropertyLength", "CutDepth", "Cut", "Profondeur de coupe")
            obj.CutDepth = 5.0

        if not hasattr(obj, "StepDown"):
            obj.addProperty("App::PropertyLength", "StepDown", "Cut", "Profondeur par passe")
            obj.StepDown = 2.0

        if not hasattr(obj, "Direction"):
            obj.addProperty("App::PropertyEnumeration", "Direction", "Contour", "Direction d'usinage")
            obj.Direction = ["Climb", "Conventional"]
            obj.Direction = "Climb"

        # Utiliser PropertyString au lieu de PropertyLink pour éviter la dépendance circulaire
        if not hasattr(obj, "ContourGeometryName"):
            obj.addProperty("App::PropertyString", "ContourGeometryName", "Contour", "Nom de la géométrie du contour")

        # Ajout des types d'approche et de sortie
        if not hasattr(obj, "ApproachType"):
            obj.addProperty("App::PropertyEnumeration", "ApproachType", "Approche", "Type d'approche du contour")
            obj.ApproachType = approach_types
            obj.ApproachType = approach_types[0]
        if not hasattr(obj, "RetractType"):
            obj.addProperty("App::PropertyEnumeration", "RetractType", "Sortie", "Type de sortie du contour")
            obj.RetractType = retract_types
            obj.RetractType = retract_types[0]

        # Longueur personnalisable pour l'approche/sortie
        if not hasattr(obj, "ApproachRetractLength"):
            obj.addProperty("App::PropertyLength", "ApproachRetractLength", "Approche", "Longueur de l'approche/sortie")
            obj.ApproachRetractLength = 12.0  # Valeur par défaut en mm

        if not hasattr(obj, "Compensation"):
            obj.addProperty("App::PropertyEnumeration", "Compensation", "Toolpath", "Type de compensation d'outil")
            obj.Compensation = list(compensation.__members__.keys())
            obj.Compensation = compensation.Ordinateur.name

        if not hasattr(obj, "SurepAxiale"):
            obj.addProperty("App::PropertyFloat", "SurepAxiale", "Toolpath", "Surépaisseur axiale")
            obj.SurepAxiale = 0.0

        if not hasattr(obj, "SurepRadiale"):
            obj.addProperty("App::PropertyFloat", "SurepRadiale", "Toolpath", "Surépaisseur radiale")
            obj.SurepRadiale = 0.0

        super().installToolProp(obj)

        if int(App.Version()[0]) >= 1 and int(App.Version()[1]) >= 1:
            obj.setExpression('ToolDiameter', u'.Tool ? .Tool.Radius * 2 : 6')

        obj.Proxy = self

    def onDocumentRestored(self, obj):
        """Appelé lors de la restauration du document"""
        self.__init__(obj)

    def onChanged(self, obj, prop):
        """Gérer les changements de propriétés"""
        if prop in ["ToolDiameter", "CutDepth", "StepDown", "Direction", "ContourGeometryName", "ApproachType", "RetractType", "ApproachRetractLength", "ApproachRetractLength", "desactivated", "Compensation", "SurepAxiale", "SurepRadiale"]:
            self.execute(obj)

    def execute(self, obj):
        """Mettre à jour la représentation visuelle"""
        if App.ActiveDocument.Restoring:
            return
        super().execute(obj)

        obj.Shape = Part.Shape()  # Initialize shape
        all_pass_shapes_collected = []  # To collect all edges/wires from all passes
        gcodeWriter = GcodeWriter.GcodeWriter()

        passes_z_values = self.calculatePasse(obj)

        contour_geom = self.getContourGeometry(obj)
        if not contour_geom:
            App.Console.PrintError("ContourGeometry not found.\n")
            return

        if not hasattr(contour_geom, "Shape") or not contour_geom.Shape or not contour_geom.Shape.Wires:
            App.Console.PrintError("ContourGeometry Shape or Wires not found or empty.\n")
            return

        # Find the Zref wire from ContourGeometry.Shape.Wires
        zref_wire_from_contour = None
        contour_zref = contour_geom.Zref if hasattr(contour_geom, "Zref") else 0.0
        for wire_in_geom in contour_geom.Shape.Wires:
            if wire_in_geom.Edges and abs(wire_in_geom.Edges[0].Vertexes[0].Point.z - contour_zref) < 1e-3:
                zref_wire_from_contour = wire_in_geom
                break

        if not zref_wire_from_contour:
            App.Console.PrintError("Zref wire not found in ContourGeometry.Shape.\n")
            # Fallback: try to use the first wire if any
            if contour_geom.Shape.Wires:
                zref_wire_from_contour = contour_geom.Shape.Wires[0]
                App.Console.PrintWarning("Using the first available wire as Zref wire fallback.\n")
            else:
                return

        # --- Calculations needed once ---
        tool_offset_radius = obj.ToolDiameter.Value / 2.0
        direction_contour = contour_geom.Direction if hasattr(contour_geom, "Direction") else "Horaire"
        direction_usinage = obj.Direction

        is_offset_inward = (direction_contour == "Horaire" and direction_usinage == "Climb") or \
                           (direction_contour == "Anti-horaire" and direction_usinage == "Conventional")
        actual_offset_value = -tool_offset_radius if is_offset_inward else tool_offset_radius

        is_contour_closed = contour_geom.IsClosed if hasattr(contour_geom, "IsClosed") else False
        approach_length = obj.ApproachRetractLength
        approach_type = obj.ApproachType
        retract_type = obj.RetractType

        # use Part.sortEdges to sort the edges of the wire
        # zref_wire_from_contour = Part.sortEdges(zref_wire_from_contour)
        # --- End of once-off calculations ---

        previous_pass_actual_end_point = None
        rapid_traverse_z = contour_zref + 2.0

        for p, pass_z in enumerate(passes_z_values):
            App.Console.PrintMessage(f"Processing pass at Z = {pass_z}\n")
            # current_pass_toolpath_segments list is removed as segments are added directly to all_pass_shapes_collected

            # 1. Create wire at current pass_z by transforming zref_wire_from_contour
            edges_for_current_pass_z = zref_wire_from_contour.Edges

            if not edges_for_current_pass_z:
                App.Console.PrintWarning(f"No edges created for wire at Z={pass_z}. Skipping pass.\n")
                continue
            wire_at_pass_z = Part.Wire(edges_for_current_pass_z)

            # 2. Apply tool offset to wire_at_pass_z
            offset_toolpath_wire = None
            try:
                if actual_offset_value > 0:
                    actual_offset_value_surep = actual_offset_value + obj.SurepRadiale
                else:
                    actual_offset_value_surep = actual_offset_value - obj.SurepRadiale

                if is_contour_closed and False:
                    face_for_offset = Part.Face(wire_at_pass_z)
                    offset_shape_result = face_for_offset.makeOffsetShape(actual_offset_value, 0.1, fill=False)
                    if offset_shape_result.Wires:
                        offset_toolpath_wire = offset_shape_result.Wires[0]
                    elif offset_shape_result.Edges:  # Sometimes returns a compound of edges
                        offset_toolpath_wire = Part.Wire(offset_shape_result.Edges)
                else:

                    offset_shape_result = wire_at_pass_z.makeOffset2D(actual_offset_value_surep, openResult=not is_contour_closed)  # join=0, fill=False,

                    if obj.Compensation == compensation.Machine.name:
                        offset_shape_result = offset_shape_result.Wires[0].makeOffset2D(-actual_offset_value, openResult=not is_contour_closed)  # join=0, fill=False,

                    if offset_shape_result.Wires:
                        offset_toolpath_wire = offset_shape_result.Wires[0]
                        offset_toolpath_edges = offset_toolpath_wire.Edges
                        if obj.Compensation == compensation.Machine.name:
                            # offset_shape_result = offset_shape_result.reversed()
                            offset_toolpath_edges.reverse()

                            pass

                    elif offset_shape_result.Edges:
                        offset_toolpath_wire = Part.Wire(offset_shape_result.Edges)

            except Exception as e:

                App.Console.PrintError(f"Error during offset for pass Z={pass_z}: {e}. Skipping pass.\n")
                exc_type, exc_value, exc_traceback = sys.exc_info()
                line_number = exc_traceback.tb_lineno
                App.Console.PrintError(f"Erreur à la ligne {line_number}\n")
                continue

            # 2.b if is closed, remove the first half of the first edge and place it at the end
            if is_contour_closed:
                import FreeCAD
                translate = FreeCAD.Qt.translate

                App.Console.PrintMessage(translate("op_Contournage", "Closed contour detected, adjusting first edge for continuity.") + "\n")
                first_edge = offset_toolpath_edges[0]
                mid_param = (first_edge.FirstParameter + first_edge.LastParameter) / 2.0
                # Trim the underlying curve and convert back to edges
                first_trimmed_curve = first_edge.Curve.trim(first_edge.FirstParameter, mid_param)
                second_trimmed_curve = first_edge.Curve.trim(mid_param, first_edge.LastParameter)
                first_half_edge = first_trimmed_curve.toShape()
                second_half_edge = second_trimmed_curve.toShape()

                new_edges = [second_half_edge] + offset_toolpath_wire.Edges[1:] + [first_half_edge]
                # offset_toolpath_wire = Part.Wire(new_edges)
                # offset_toolpath_edges = offset_toolpath_wire.Edges
                offset_toolpath_edges = new_edges

            # 3. Generate Approach and Retract for offset_toolpath_wire

            # if offset_toolpath_wire.Orientation == "Forward":
            if True:  # is_offset_inward:
                indexOfFirstPoint = Contour.getFirstPoint(offset_toolpath_edges)
                indexOfLastPoint = Contour.getLastPoint(offset_toolpath_edges)
                first_toolpath_edge = offset_toolpath_edges[0]
                last_toolpath_edge = offset_toolpath_edges[-1]
            else:
                indexOfFirstPoint = Contour.getLastPoint(offset_toolpath_edges)
                indexOfLastPoint = Contour.getFirstPoint(offset_toolpath_edges)
                first_toolpath_edge = offset_toolpath_edges[-1]
                last_toolpath_edge = offset_toolpath_edges[0]

            core_toolpath_start_pt = first_toolpath_edge.Vertexes[indexOfFirstPoint].Point
            core_toolpath_end_pt = last_toolpath_edge.Vertexes[indexOfLastPoint].Point

            pass_approach_edges = []
            pass_retract_edges = []

            App.Console.PrintMessage(f"first point: {core_toolpath_start_pt}, last point: {core_toolpath_end_pt}\n")
            # start_pt and end_pt are now core_toolpath_start_pt and core_toolpath_end_pt

            gcodeWriter.comment(f"Pass at Z={pass_z}")
            # Approach

            tangent_start_vec = first_toolpath_edge.tangentAt(first_toolpath_edge.FirstParameter)
            if tangent_start_vec.Length < 1e-6:
                raise ValueError("Tangent length at start is too small.")

            tangent_start = tangent_start_vec.normalize()
            if approach_type == "Tangentielle":
                if is_offset_inward:
                    approachPoint = core_toolpath_start_pt - tangent_start.multiply(approach_length)
                else:
                    approachPoint = core_toolpath_start_pt + tangent_start.multiply(approach_length)
                pass_approach_edges.append(Part.makeLine(approachPoint, core_toolpath_start_pt))

            elif approach_type in ["Perpendiculaire", "Perp+Arc"]:
                if is_offset_inward:
                    approachPoint = core_toolpath_start_pt + App.Vector(-tangent_start.y, tangent_start.x, 0).normalize().multiply(approach_length)
                else:
                    approachPoint = core_toolpath_start_pt - App.Vector(-tangent_start.y, tangent_start.x, 0).normalize().multiply(approach_length)
                perp_start = App.Vector(-tangent_start.y, tangent_start.x, 0).normalize()  # Assuming XY plane
                pass_approach_edges.append(Part.makeLine(core_toolpath_start_pt + perp_start.multiply(approach_length), core_toolpath_start_pt))
            elif approach_type == "Perp+Arc":
                pass  # TODO: Implement Perp+Arc approach.

            gcodeWriter.linearMove({'X': approachPoint.x, 'Y': approachPoint.y, 'Z': rapid_traverse_z}, rapid=True)
            gcodeWriter.linearMove({'X': approachPoint.x, 'Y': approachPoint.y, 'Z': pass_z + 2}, rapid=True)
            gcodeWriter.linearMove({'Z': pass_z}, feed=float(obj.FeedRate.getValueAs('mm/min')), rapid=False)

            comp = "G40"
            if obj.Compensation in [compensation.Machine.name, compensation.Ordinateur_G41_G42.name]:
                if is_offset_inward:
                    comp = "G41"
                else:
                    comp = "G42"
            if p == 0:
                gcodeWriter.lines.append(f"{obj.Label}_start:")

            if approach_type == "Perp+Arc":
                r = 1
                a = approach_length.Value - r
                angle = math.asin(r/a)
                D = App.Vector(((a*a-r*r)/a)*math.cos(angle), -((r/a)*math.sqrt(a*a-r*r))*math.sin(angle), 0)
                gcodeWriter.linearMove({'X': approachPoint.x + D.x, 'Y': approachPoint.y + D.y}, feed=float(obj.FeedRate.getValueAs('mm/min')))
                gcodeWriter.arcMove({'X': core_toolpath_start_pt.x, 'Y': core_toolpath_start_pt.y, 'R': r, 'CCW': True}, feed=float(obj.FeedRate.getValueAs('mm/min')))
                pass  # TODO: Implement Perp+Arc G-code
            else:

                gcodeWriter.linearMove({'X': core_toolpath_start_pt.x, 'Y': core_toolpath_start_pt.y, 'comp': comp}, feed=float(obj.FeedRate.getValueAs('mm/min')))
            # TODO: Add Helicoidal approach if needed, ensuring Z movement relative to pass_z

            current_edge = None
            for i, edge in enumerate(offset_toolpath_edges):
                current_edge = edge
                bon_sens = None
                if i < len(offset_toolpath_edges)-1:
                    next_edge = offset_toolpath_edges[i+1]
                    if current_edge.Vertexes[-1].Point.distanceToPoint(next_edge.Vertexes[0].Point) < 1e-6:
                        bon_sens = True

                    elif current_edge.Vertexes[-1].Point.distanceToPoint(next_edge.Vertexes[-1].Point) < 1e-6:
                        bon_sens = True

                    elif current_edge.Vertexes[0].Point.distanceToPoint(next_edge.Vertexes[-1].Point) < 1e-6:
                        bon_sens = False

                    elif current_edge.Vertexes[0].Point.distanceToPoint(next_edge.Vertexes[0].Point) < 1e-6:
                        bon_sens = False

                    else:
                        pass
                else:
                    prev_edge = offset_toolpath_edges[i-1]

                    if prev_edge.Vertexes[-1].Point.distanceToPoint(current_edge.Vertexes[0].Point) < 1e-6:
                        bon_sens = True

                    elif prev_edge.Vertexes[-1].Point.distanceToPoint(current_edge.Vertexes[-1].Point) < 1e-6:
                        bon_sens = False

                    elif prev_edge.Vertexes[0].Point.distanceToPoint(current_edge.Vertexes[-1].Point) < 1e-6:
                        bon_sens = False

                    elif prev_edge.Vertexes[0].Point.distanceToPoint(current_edge.Vertexes[0].Point) < 1e-6:
                        bon_sens = True

                    else:
                        pass

                Contour.edgeToGcode(edge, bonSens=bon_sens, current_z=pass_z, rapid=False, gcodeWriter=gcodeWriter)

            # Retract

            tangent_end_vec = last_toolpath_edge.tangentAt(last_toolpath_edge.LastParameter)
            if tangent_end_vec.Length > 1e-6:
                tangent_end = tangent_end_vec.normalize()
                if retract_type == "Tangentielle":
                    if is_offset_inward:
                        SortiePt = core_toolpath_end_pt + tangent_end.multiply(approach_length)
                    else:
                        SortiePt = core_toolpath_end_pt - tangent_end.multiply(approach_length)
                    pass_retract_edges.append(Part.makeLine(core_toolpath_end_pt, SortiePt))

                elif retract_type == "Perpendiculaire":
                    if is_offset_inward:
                        perp_end = App.Vector(-tangent_end.y, tangent_end.x, 0).normalize()
                        SortiePt = core_toolpath_end_pt + perp_end.multiply(approach_length)
                    else:
                        perp_end = App.Vector(-tangent_end.y, tangent_end.x, 0).normalize()
                        SortiePt = core_toolpath_end_pt - perp_end.multiply(approach_length)
                    pass_retract_edges.append(Part.makeLine(core_toolpath_end_pt, SortiePt))

                gcodeWriter.linearMove({'X': SortiePt.x, 'Y': SortiePt.y, 'comp': 'G40'}, feed=float(obj.FeedRate.getValueAs('mm/min')))

            gcodeWriter.linearMove({'Z': rapid_traverse_z}, rapid=True)

            if p == 0:
                gcodeWriter.lines.append(f"{obj.Label}_end:")

            # Determine the actual start point of this pass's full trajectory (including approach)
            current_pass_trajectory_start_point = core_toolpath_start_pt  # Default to core path start
            if pass_approach_edges:
                current_pass_trajectory_start_point = pass_approach_edges[0].Vertexes[0].Point

            # LINKING LOGIC: Add rapid move from previous pass end to current pass start
            if previous_pass_actual_end_point:  # If there was a previous pass
                link_p1 = previous_pass_actual_end_point
                link_p2 = App.Vector(link_p1.x, link_p1.y, rapid_traverse_z)
                link_p3 = App.Vector(current_pass_trajectory_start_point.x, current_pass_trajectory_start_point.y, rapid_traverse_z)
                link_p4 = current_pass_trajectory_start_point

                all_pass_shapes_collected.append(Part.makeLine(link_p1, link_p2))  # Retract to rapid_traverse_z
                if link_p2.distanceToPoint(link_p3) > 1e-6:

                    all_pass_shapes_collected.append(Part.makeLine(link_p2, link_p3))  # Traverse at rapid_traverse_z
                all_pass_shapes_collected.append(Part.makeLine(link_p3, link_p4))  # Plunge to current pass start

            # Add current pass's trajectory segments (approach, core path, retract)
            all_pass_shapes_collected.extend(pass_approach_edges)
            all_pass_shapes_collected.extend(offset_toolpath_wire.Edges)
            all_pass_shapes_collected.extend(pass_retract_edges)

            # Determine the actual end point of this pass's full trajectory (including retract) for the next iteration's link
            current_pass_trajectory_end_point = core_toolpath_end_pt  # Default to core path end
            if pass_retract_edges:
                current_pass_trajectory_end_point = pass_retract_edges[-1].Vertexes[-1].Point
            previous_pass_actual_end_point = current_pass_trajectory_end_point

        if all_pass_shapes_collected:
            try:
                obj.Shape = Part.makeCompound(all_pass_shapes_collected)
                App.Console.PrintMessage(f"Multi-pass toolpath generated with {len(passes_z_values)} passes.\n")
            except Exception as e_compound:
                App.Console.PrintError(f"Failed to create final compound shape: {e_compound}\n")
                obj.Shape = Part.Shape()  # Fallback to empty shape
        else:
            App.Console.PrintWarning("No toolpath segments generated for any pass.\n")
            obj.Shape = Part.Shape()

        obj.Gcode = '\n'.join(gcodeWriter.lines)

    def reorder_wire(self, shape):
        """
        Trie et oriente les edges d'un wire ou shape, retourne un wire ordonné.
        """
        if hasattr(shape, "Edges"):
            sorted_edges = Part.__sortEdges__(list(shape.Edges))
            wire = Part.Wire(sorted_edges)
            # Afficher la séquence ordonnée des points
            ordered_points = []
            for edge in wire.Edges:
                for v in edge.Vertexes:
                    pt = (round(v.Point.x, 5), round(v.Point.y, 5), round(v.Point.z, 5))
                    if not ordered_points or pt != ordered_points[-1]:
                        ordered_points.append(pt)

            return wire
        return shape

    def calculatePasse(self, obj):
        geom = self.getContourGeometry(obj)
        if not geom:
            return []

        Zref = geom.Zref
        depth = geom.depth
        prise = obj.StepDown

        passes = []

        if geom.DepthMode == "Relatif":
            depth = geom.Zref + geom.depth + obj.SurepAxiale
        else:
            depth = geom.depth + obj.SurepAxiale

        if Zref < depth:  # TODO
            App.Console.PrintError("La hauteur de référence est inférieure à la profondeur de coupe.\n")
            return []

        passeEquilibre = True

        if passeEquilibre:
            nbPasses = math.ceil(math.fabs(depth - Zref) / prise)
            prise = math.fabs(depth - Zref) / nbPasses
            for i in range(nbPasses):
                passes.append(Zref - (i + 1) * prise)
        else:
            while True:
                if Zref - prise >= depth + prise:
                    passes.append(depth)
                    depth -= prise
                    break
                else:
                    passes.append(depth)

        return passes

    def getContourGeometry(self, obj):
        """Récupérer la géométrie du contour associée"""
        if not hasattr(obj, "ContourGeometryName") or not obj.ContourGeometryName:
            # App.Console.PrintError("Aucune géométrie de contour associée.\n")
            return None

        doc = obj.Document
        for o in doc.Objects:
            if o.Name == obj.ContourGeometryName:
                return o

        App.Console.PrintError(f"Impossible de trouver la géométrie du contour '{obj.ContourGeometryName}'.\n")
        return None

    def __getstate__(self):
        """Appelé lors de la sauvegarde"""
        return None
        # return {
        #     "Type": self.Type,
        #     "ContourGeometryName": getattr(self.Object, "ContourGeometryName", "")
        # }

    def __setstate__(self, state):
        """Appelé lors du chargement"""
        return None

        # if state:
        #     self.Type = state.get("Type", "ContournageCycle")
        # return None


class ViewProviderContournageCycle(baseOpViewProviderProxy):
    """Classe pour gérer l'affichage du cycle de contournage"""

    def __init__(self, vobj):
        """Initialise le ViewProvider"""
        super().__init__(vobj)

        vobj.Proxy = self
        self.Object = vobj.Object

        # Ajouter des propriétés pour l'affichage
        if not hasattr(vobj, "ShowToolPath"):
            vobj.addProperty("App::PropertyBool", "ShowToolPath", "Display", "Afficher la trajectoire d'outil")
            vobj.ShowToolPath = True

        if not hasattr(vobj, "PathColor"):
            vobj.addProperty("App::PropertyColor", "PathColor", "Display", "Couleur de la trajectoire")
            vobj.PathColor = (0.0, 0.0, 1.0)  # Bleu par défaut

        if not hasattr(vobj, "PathWidth"):
            vobj.addProperty("App::PropertyFloat", "PathWidth", "Display", "Épaisseur de la trajectoire")
            vobj.PathWidth = 2.0

    def getIcon(self):
        """Retourne l'icône"""

        if not self.Object.Active:
            return BaptUtilities.getIconPath("operation_disabled.svg")
        return BaptUtilities.getIconPath("Contournage.svg")

    def attach(self, vobj):
        """Appelé lors de l'attachement du ViewProvider"""
        self.Object = vobj.Object

        # Configuration de l'affichage
        vobj.LineColor = (0.0, 0.0, 1.0)  # Bleu
        vobj.PointColor = (0.0, 0.0, 1.0)  # Bleu
        vobj.LineWidth = 2.0
        vobj.PointSize = 4.0

        return super().attach(vobj)

    # def setupContextMenu(self, vobj, menu):
    #     """Configuration du menu contextuel"""
    #     action = menu.addAction("Edit")
    #     action.triggered.connect(lambda: self.setEdit(vobj))

    #     action2 = menu.addAction("Activate" if vobj.Object.desactivated else "Desactivate")
    #     action2.triggered.connect(lambda: self.setDesactivate(vobj))
    #     return True

    def onChanged(self, vobj, prop):
        """Appelé lorsqu'une propriété du ViewProvider est modifiée"""
        # Mettre à jour l'affichage si une propriété d'affichage change
        if prop in ["ShowToolPath", "PathColor", "PathWidth"]:
            # Appliquer les nouvelles propriétés d'affichage
            if hasattr(vobj, "LineColor") and hasattr(vobj, "PathColor"):
                vobj.LineColor = vobj.PathColor

            if hasattr(vobj, "LineWidth") and hasattr(vobj, "PathWidth"):
                vobj.LineWidth = vobj.PathWidth

    def claimChildren(self):
        """Retourne les enfants de cet objet"""
        # Ne pas réclamer la géométrie du contour comme enfant
        # car c'est le contour qui doit être l'enfant de la géométrie
        return []

    def setupContextMenu(self, vobj, menu):
        super().setupContextMenu(vobj, menu)

        viewGcode = QtGui.QAction(Gui.getIcon("Std_TransformManip.svg"), "View G-code", menu)
        QtCore.QObject.connect(viewGcode, QtCore.SIGNAL("triggered()"), lambda: self.viewGcode(vobj))
        menu.addAction(viewGcode)
        return True

    def viewGcode(self, vobj):
        """Afficher le G-code dans une boîte de dialogue"""
        taskPanel = GcodeEditorTaskPanel(vobj.Object)
        Gui.Control.showDialog(taskPanel)

    def setEdit(self, vobj, mode=0):
        """Ouvre le panneau de tâche pour l'édition"""
        import BaptContournageTaskPanel
        taskd = BaptContournageTaskPanel.ContournageTaskPanel(self.Object)
        Gui.Control.showDialog(taskd)
        return True

    def unsetEdit(self, vobj, mode=0):
        """Ferme le panneau de tâche"""
        Gui.Control.closeDialog()
        return True

    def getDisplayModes(self, vobj):
        """Retourne les modes d'affichage disponibles"""
        return ["Flat Lines", "Shaded", "Wireframe", "Path"]

    def getDefaultDisplayMode(self):
        """Retourne le mode d'affichage par défaut"""
        return "Flat Lines"

    def setDisplayMode(self, mode):
        """Définit le mode d'affichage"""
        return mode

    def __getstate__(self):
        """Appelé lors de la sauvegarde"""
        return None
        return {"ObjectName": self.Object.Name if self.Object else None}

    def __setstate__(self, state):
        """Appelé lors du chargement"""
        return None
        if state and "ObjectName" in state and state["ObjectName"]:
            self.Object = App.ActiveDocument.getObject(state["ObjectName"])
        return None
