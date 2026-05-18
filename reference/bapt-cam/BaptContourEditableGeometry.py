import sys
import FreeCAD as App
import FreeCADGui as Gui
import Part


class ContourEditableGeometry:
    """Contour éditable via Sketcher"""

    def __init__(self, obj):
        self.Type = "ContourEditableGeometry"
        obj.addProperty("App::PropertyLink", "Sketch", "Base", "Sketch associé à la géométrie")

        if not hasattr(obj, "depth"):
            obj.addProperty("App::PropertyFloat", "depth", "Contour", "Hauteur finale")
            obj.depth = 0.0

        if not hasattr(obj, "Direction"):
            obj.addProperty("App::PropertyEnumeration", "Direction", "Contour", "Direction d'usinage")
            obj.Direction = ["Horaire", "Anti-horaire"]
            obj.Direction = "Horaire"

        if not hasattr(obj, "DepthMode"):
            obj.addProperty("App::PropertyEnumeration", "DepthMode", "Contour", "Mode de profondeur (Absolu ou Relatif)")
            obj.DepthMode = ["Absolu", "Relatif"]
            obj.DepthMode = "Absolu"

        self.createSketch(obj)
        obj.Proxy = self

    def createSketch(self, obj):
        """Crée un Sketch si besoin"""
        if not obj.Sketch:
            sketch = App.ActiveDocument.addObject("Sketcher::SketchObject", obj.Name + "_Sketch")
            obj.Sketch = sketch
            # Optionnel : placer le sketch dans le même groupe que la géométrie
            if hasattr(obj, "Group"):

                obj.addObject(sketch)

    def execute(self, obj):
        """Met à jour la forme à partir du Sketch"""
        if not obj.Sketch and len(obj.Sketch.Shape.Edges) <= 0:
            obj.Shape = Part.Shape()
            return
        try:
            shape = obj.Sketch.Shape

            adjusted_edges_depth = []

            for i, edge in enumerate(shape.Edges):
                if obj.DepthMode == "Relatif":
                    z_offset = obj.depth
                    translation = App.Vector(0, 0, z_offset)
                else:  # Absolu
                    z_value = obj.depth
                    translation = App.Vector(0, 0, z_value - edge.Vertexes[0].Z)

                moved_edge = edge.translate(translation)
                adjusted_edges_depth.append(moved_edge)

            wire_z_final = Part.Wire(adjusted_edges_depth)
            # shape = Part.Shape([wire_z_final])
            shapes = [shape, wire_z_final]
            coumpound = Part.Compound(shapes)
            obj.Shape = coumpound
        except Exception as e:
            App.Console.PrintError(f"Erreur lors de la récupération du shape du sketch : {e}\n")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            App.Console.PrintMessage(f'{exc_tb.tb_lineno}\n')
            obj.Shape = Part.Shape()

    def onChanged(self, obj, prop):
        """Synchronise la forme si le Sketch change"""
        return
        if prop in ["Sketch", "depth", "Direction", "DepthMode"]:
            self.execute(obj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class ViewProviderContourEditableGeometry:
    """Affichage pour ContourEditableGeometry"""

    def __init__(self, vobj):
        vobj.Proxy = self
        self.Object = vobj.Object

    def getIcon(self):
        return ":/icons/Sketcher_NewSketch.svg"

    def attach(self, vobj):
        self.Object = vobj.Object

    def doubleClicked(self, vobj):
        """Ouvre le Sketch en édition"""
        if hasattr(self.Object, "Sketch") and self.Object.Sketch:
            Gui.activeDocument().setEdit(self.Object.Sketch.Name)
            return True
        return False

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        action = menu.addAction("Edit Sketch")
        action.triggered.connect(lambda: self.setEditSketch(vobj))

    def setEditSketch(self, vobj):
        """Ouvre le Sketch en édition"""
        if hasattr(self.Object, "Sketch") and self.Object.Sketch:
            Gui.activeDocument().setEdit(self.Object.Sketch.Name)

    def onDelete(self, vobj, subelements):
        """Nettoyage lors de la suppression"""
        if hasattr(self.Object, "Sketch") and self.Object.Sketch:
            App.ActiveDocument.removeObject(self.Object.Sketch.Name)
        return True
