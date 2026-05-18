# -*- coding: utf-8 -*-

"""
BaptHoleRecognition.py
Module pour la reconnaissance automatique de trous cylindriques perpendiculaires au plan de travail
"""

import FreeCAD as App
import FreeCADGui as Gui
import Part
import math
from PySide import QtCore, QtGui
from pivy import coin  # type: ignore


class HoleInfo:
    """Classe pour stocker les informations d'un trou détecté"""

    def __init__(self, center, diameter, depth, axis_direction, face):
        self.center = center  # FreeCAD.Vector
        self.diameter = diameter  # float (mm)
        self.depth = depth  # float (mm)
        self.axis_direction = axis_direction  # FreeCAD.Vector (direction normalisée)
        self.face = face  # Face FreeCAD

    def __repr__(self):
        return f"Hole(center={self.center}, dia={self.diameter:.2f}, depth={self.depth:.2f})"


class HoleGroup:
    """Classe pour regrouper des trous similaires"""

    def __init__(self, diameter, depth, tolerance_dia=0.1, tolerance_depth=0.5):
        self.diameter = diameter
        self.depth = depth
        self.tolerance_dia = tolerance_dia
        self.tolerance_depth = tolerance_depth
        self.holes = []  # Liste de HoleInfo

    def matches(self, hole):
        """Vérifie si un trou correspond à ce groupe"""
        dia_match = abs(hole.diameter - self.diameter) <= self.tolerance_dia
        depth_match = abs(hole.depth - self.depth) <= self.tolerance_depth
        return dia_match and depth_match

    def add_hole(self, hole):
        """Ajoute un trou au groupe"""
        self.holes.append(hole)

    def count(self):
        """Retourne le nombre de trous dans le groupe"""
        return len(self.holes)

    def __repr__(self):
        return f"Group(dia={self.diameter:.2f}, depth={self.depth:.2f}, count={self.count()})"


class HoleRecognition:
    """Classe principale pour la reconnaissance de trous"""
    Type = "HoleRecognition"

    def __init__(self, obj):
        """Initialise l'objet de reconnaissance"""
        obj.Proxy = self

        # Propriété pour la forme source
        obj.addProperty("App::PropertyLink", "SourceShape", "Source",
                        "Forme ou face à analyser pour la détection de trous")

        # Propriété pour l'axe de perçage
        obj.addProperty("App::PropertyEnumeration", "DrillAxis", "Detection",
                        "Axe de perçage (perpendiculaire au plan de travail)")
        obj.DrillAxis = ["Z", "X", "Y"]
        obj.DrillAxis = "Z"

        # Propriété pour l'axe de perçage
        obj.addProperty("App::PropertyVector", "Axis", "Detection",
                        "Axe de perçage (perpendiculaire au plan de travail)")
        obj.Axis = App.Vector(0, 0, -1)

        # Propriété pour la tolérance de diamètre
        obj.addProperty("App::PropertyFloat", "DiameterTolerance", "Detection",
                        "Tolérance pour regrouper les trous par diamètre (mm)")
        obj.DiameterTolerance = 0.1

        # Propriété pour la tolérance de profondeur
        obj.addProperty("App::PropertyFloat", "DepthTolerance", "Detection",
                        "Tolérance pour regrouper les trous par profondeur (mm)")
        obj.DepthTolerance = 0.5

        # Détecter uniquement les trous traversants
        obj.addProperty("App::PropertyBool", "OnlyThrough", "Detection",
                        "Ne détecter que les trous traversants (through-holes)")
        obj.OnlyThrough = False

        # Propriétés pour stocker les résultats (en lecture seule via code)
        obj.addProperty("App::PropertyInteger", "HoleCount", "Results",
                        "Nombre total de trous détectés")
        obj.setEditorMode("HoleCount", 1)  # Read-only

        obj.addProperty("App::PropertyInteger", "GroupCount", "Results",
                        "Nombre de groupes de trous")
        obj.setEditorMode("GroupCount", 1)  # Read-only

        # Stockage interne des données
        self.detected_holes = []  # Liste de HoleInfo
        self.hole_groups = []  # Liste de HoleGroup

    def get_drill_axis_vector(self, obj):
        """Retourne le vecteur normalisé de l'axe de perçage"""
        axis_map = {
            "X": App.Vector(1, 0, 0),
            "Y": App.Vector(0, 1, 0),
            "Z": App.Vector(0, 0, 1)
        }
        return axis_map.get(obj.DrillAxis, App.Vector(0, 0, 1))

    def is_cylindrical_face(self, face):
        """Vérifie si une face est cylindrique"""
        try:
            surface = face.Surface
            return str(type(surface).__name__) == "Cylinder"
        except:
            return False

    def is_perpendicular_to_axis(self, face, drill_axis, tolerance_angle=5.0):
        """
        Vérifie si le cylindre est perpendiculaire à l'axe de perçage
        tolerance_angle: tolérance en degrés
        """
        try:
            surface = face.Surface
            cylinder_axis = surface.Axis

            # Calculer l'angle entre l'axe du cylindre et l'axe de perçage
            angle_rad = cylinder_axis.getAngle(drill_axis)
            angle_deg = math.degrees(angle_rad)

            # Le cylindre doit être parallèle à l'axe de perçage
            # (angle proche de 0° ou 180°)
            is_parallel = angle_deg < tolerance_angle or angle_deg > (180 - tolerance_angle)

            return is_parallel
        except:
            return False

    def extract_hole_info(self, face, drill_axis):
        """Extrait les informations d'un trou depuis une face cylindrique"""
        try:
            surface = face.Surface

            # Diamètre = 2 * rayon
            diameter = 2 * surface.Radius

            # Centre du cylindre
            center = surface.Center

            # Profondeur: calculer la longueur du cylindre le long de son axe
            # On utilise la BoundBox de la face et on projette ses 8 coins
            bbox = face.BoundBox

            # Calculer la profondeur selon l'axe du cylindre
            cylinder_axis = surface.Axis

            # Générer les 8 coins de la bounding box
            corners = [
                App.Vector(x, y, z)
                for x in (bbox.XMin, bbox.XMax)
                for y in (bbox.YMin, bbox.YMax)
                for z in (bbox.ZMin, bbox.ZMax)
            ]

            # Projeter les coins sur l'axe du cylindre pour trouver l'étendue
            projections = [(corner - center).dot(cylinder_axis) for corner in corners]
            depth = max(projections) - min(projections)

            return HoleInfo(center, diameter, depth, cylinder_axis, face)
        except Exception as e:
            App.Console.PrintWarning(f"Erreur lors de l'extraction des infos du trou: {e}\n")
            return None

    def is_through_hole(self, hole, faces, radius_tol=0.2, axis_angle_tol_deg=5.0):
        """Approximate test whether a detected hole is through by finding
        another cylindrical face with similar radius and opposite position
        along the hole axis. This is a heuristic that works when holes are
        represented by two cylinder faces (one at each end).
        """
        try:
            a_axis = hole.axis_direction.normalize() if hasattr(hole.axis_direction, 'normalize') else hole.axis_direction
        except Exception:
            a_axis = hole.axis_direction

        for f in faces:
            if not self.is_cylindrical_face(f):
                continue
            try:
                s = f.Surface
                # radius close?
                if abs((2 * s.Radius) - hole.diameter) > radius_tol:
                    continue
                # axis parallel?
                other_axis = s.Axis
                angle = 0.0
                try:
                    angle = math.degrees(other_axis.getAngle(a_axis))
                except Exception:
                    pass
                if not (angle < axis_angle_tol_deg or angle > (180.0 - axis_angle_tol_deg)):
                    continue

                # position along axis: check that centers are on opposite sides
                other_center = s.Center
                delta = (other_center - hole.center)
                proj = delta.dot(a_axis)
                # If projection is sufficiently large and opposite sign, consider through
                if abs(proj) > (hole.diameter * 0.5):
                    return True
            except Exception:
                continue
        return False

    def detect_holes(self, obj):
        """Détecte tous les trous dans la forme source"""
        if not obj.SourceShape:
            App.Console.PrintWarning("Aucune forme source sélectionnée\n")
            return

        self.detected_holes = []
        drill_axis = self.get_drill_axis_vector(obj)

        # Obtenir toutes les faces de la forme
        shape = obj.SourceShape.Shape if hasattr(obj.SourceShape, 'Shape') else obj.SourceShape
        faces = shape.Faces

        App.Console.PrintMessage(f"Analyse de {len(faces)} faces...\n")

        for face in faces:
            # Vérifier si c'est un cylindre
            if not self.is_cylindrical_face(face):
                continue

            # Vérifier si perpendiculaire à l'axe
            if not self.is_perpendicular_to_axis(face, drill_axis):
                continue

            # Extraire les informations du trou
            hole_info = self.extract_hole_info(face, drill_axis)
            if hole_info:
                # Si on ne veut que les trous traversants, vérifier heuristiquement
                if getattr(obj, 'OnlyThrough', False):
                    if not self.is_through_hole(hole_info, faces):
                        App.Console.PrintMessage(f"Trou non traversant ignoré: {hole_info}\n")
                        continue

                self.detected_holes.append(hole_info)
                App.Console.PrintMessage(f"Trou détecté: {hole_info}\n")

        obj.HoleCount = len(self.detected_holes)
        App.Console.PrintMessage(f"Total: {obj.HoleCount} trou(s) détecté(s)\n")

        # Créer les groupes
        self.group_holes(obj)

    def group_holes(self, obj):
        """Regroupe les trous par diamètre et profondeur"""
        self.hole_groups = []

        for hole in self.detected_holes:
            # Chercher un groupe existant
            group_found = False
            for group in self.hole_groups:
                if group.matches(hole):
                    group.add_hole(hole)
                    group_found = True
                    break

            # Si aucun groupe trouvé, en créer un nouveau
            if not group_found:
                new_group = HoleGroup(
                    hole.diameter,
                    hole.depth,
                    obj.DiameterTolerance,
                    obj.DepthTolerance
                )
                new_group.add_hole(hole)
                self.hole_groups.append(new_group)

        obj.GroupCount = len(self.hole_groups)
        App.Console.PrintMessage(f"Trous regroupés en {obj.GroupCount} groupe(s)\n")
        for group in self.hole_groups:
            App.Console.PrintMessage(f"  {group}\n")

    def execute(self, obj):
        """Exécuté lors du recalcul"""
        pass

    def onChanged(self, obj, prop):
        """Appelé quand une propriété change"""
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class ViewProviderHoleRecognition:
    """ViewProvider pour l'objet de reconnaissance de trous"""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):

        self.Object = vobj.Object

        # Créer le groupe principal pour la visualisation
        self.visualization = coin.SoSeparator()

        # Groupe pour les sphères (positions des trous)
        self.spheres_group = coin.SoSeparator()
        self.spheres_switch = coin.SoSwitch()
        self.spheres_switch.whichChild = coin.SO_SWITCH_ALL
        self.spheres_switch.addChild(self.spheres_group)

        self.visualization.addChild(self.spheres_switch)
        vobj.addDisplayMode(self.visualization, "Holes")

    def getIcon(self):
        import BaptUtilities
        return BaptUtilities.getIconPath("Tree_HoleRecognition.svg")

    def update_visualization(self):
        """Met à jour la visualisation 3D des trous détectés"""

        # Vider le groupe de sphères
        self.spheres_group.removeAllChildren()

        if not hasattr(self.Object.Proxy, 'detected_holes'):
            return

        holes = self.Object.Proxy.detected_holes
        if not holes:
            return

        for idx, hole in enumerate(holes):
            # Créer un séparateur pour chaque trou
            hole_sep = coin.SoSeparator()

            # Position de la sphère
            trans = coin.SoTranslation()
            trans.translation.setValue(hole.center.x, hole.center.y, hole.center.z)
            hole_sep.addChild(trans)

            # Couleur de la sphère (varie selon le groupe)
            color = coin.SoBaseColor()
            # Trouver le groupe de ce trou pour déterminer la couleur
            group_idx = self.find_group_index(hole)
            colors = [
                (1.0, 0.0, 0.0),  # Rouge
                (0.0, 1.0, 0.0),  # Vert
                (0.0, 0.0, 1.0),  # Bleu
                (1.0, 1.0, 0.0),  # Jaune
                (1.0, 0.0, 1.0),  # Magenta
                (0.0, 1.0, 1.0),  # Cyan
            ]
            color_idx = group_idx % len(colors) if group_idx >= 0 else 0
            color.rgb.setValue(colors[color_idx])
            hole_sep.addChild(color)

            # Sphère représentant le trou
            sphere = coin.SoSphere()
            # Rayon de la sphère = rayon du trou ou min 1mm pour visibilité
            # sphere.radius = max(hole.diameter / 2.0, 1.0)
            sphere.radius = 1
            hole_sep.addChild(sphere)

            # Ajouter un cylindre pour visualiser l'axe et la profondeur
            axis_sep = coin.SoSeparator()

            # Translation pour positionner le cylindre : il doit partir du centre et aller dans la direction de l'axe
            # Le cylindre Coin3D est centré, donc on le translate de height/2 dans la direction de l'axe
            axis_trans = coin.SoTranslation()
            offset = hole.depth / 2.0
            axis_trans.translation.setValue(
                hole.axis_direction.x * offset,
                hole.axis_direction.y * offset,
                hole.axis_direction.z * offset * -1  # FIXME
            )
            axis_sep.addChild(axis_trans)

            # Rotation pour aligner le cylindre avec l'axe du trou
            rotation = coin.SoRotation()
            # L'axe par défaut du cylindre est Y, on doit le tourner vers l'axe du trou
            default_axis = coin.SbVec3f(0, 1, 0)
            hole_axis = coin.SbVec3f(hole.axis_direction.x, hole.axis_direction.y, hole.axis_direction.z)
            rot = coin.SbRotation(default_axis, hole_axis)
            rotation.rotation.setValue(rot)
            axis_sep.addChild(rotation)

            # Couleur semi-transparente pour l'axe
            axis_color = coin.SoBaseColor()
            axis_color.rgb.setValue(colors[color_idx])
            axis_sep.addChild(axis_color)

            # Matériau transparent
            material = coin.SoMaterial()
            material.transparency.setValue(0.7)
            axis_sep.addChild(material)

            # Cylindre représentant la profondeur
            cylinder = coin.SoCylinder()
            cylinder.radius = hole.diameter / 2.0
            cylinder.height = hole.depth
            axis_sep.addChild(cylinder)

            hole_sep.addChild(axis_sep)

            self.spheres_group.addChild(hole_sep)

    def find_group_index(self, hole):
        """Trouve l'index du groupe contenant ce trou"""
        if not hasattr(self.Object.Proxy, 'hole_groups'):
            return -1
        for idx, group in enumerate(self.Object.Proxy.hole_groups):
            if hole in group.holes:
                return idx
        return -1

    def doubleClicked(self, vobj):
        """Ouvrir le panneau d'édition"""
        self.setEdit(vobj)
        return True

    def setEdit(self, vobj, mode=0):
        """Ouvrir le TaskPanel"""
        from BaptHoleRecognitionTaskPanel import HoleRecognitionTaskPanel
        panel = HoleRecognitionTaskPanel(vobj.Object)
        Gui.Control.showDialog(panel)
        return True

    def unsetEdit(self, vobj, mode=0):
        Gui.Control.closeDialog()
        return True

    def getDisplayModes(self, vobj):
        return ["Holes"]

    def getDefaultDisplayMode(self):
        return "Holes"

    def setDisplayMode(self, mode):
        return mode

    def updateData(self, obj, prop):
        """Appelé quand les données de l'objet changent"""
        if prop in ["HoleCount", "GroupCount"]:
            self.update_visualization()

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def createHoleRecognition():
    """Fonction helper pour créer un objet de reconnaissance de trous"""
    doc = App.ActiveDocument
    obj = doc.addObject("App::FeaturePython", "HoleRecognition")
    HoleRecognition(obj)
    ViewProviderHoleRecognition(obj.ViewObject)
    doc.recompute()
    return obj
