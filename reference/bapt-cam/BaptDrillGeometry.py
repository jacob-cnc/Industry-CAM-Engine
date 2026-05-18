import FreeCAD as App
import FreeCADGui as Gui
import Part
import BaptUtilities


class DrillGeometry:
    def __init__(self, obj):
        """Ajoute les propriétés"""

        self.Type = "DrillGeometry"

        # obj.addExtension("App::GroupExtensionPython")
        # obj.addExtension("App::DocumentObjectGroupPython")
        # obj.addExtension("App::LinkExtensionPython")

        # Référence aux faces sélectionnées
        if not hasattr(obj, "DrillFaces"):
            obj.addProperty("App::PropertyLinkSubList", "DrillFaces", "Drill", "Selected drill faces")

        # Liste des positions de perçage
        if not hasattr(obj, "DrillPositions"):  # TODO Renamer en HolePositions
            obj.addProperty("App::PropertyVectorList", "DrillPositions", "Drill", "Drill positions")

        # Diamètre des perçages (détecté automatiquement)
        if not hasattr(obj, "DrillDiameter"):
            obj.addProperty("App::PropertyLength", "DrillDiameter", "Drill", "Detected drill diameter")
            obj.setEditorMode("DrillDiameter", 1)  # en lecture seule

        # Profondeur des perçages (détectée automatiquement)
        if not hasattr(obj, "DrillDepth"):
            obj.addProperty("App::PropertyLength", "DrillDepth", "Drill", "Detected drill depth")
            obj.setEditorMode("DrillDepth", 1)  # en lecture seule

        # Taille des sphères de visualisation
        if not hasattr(obj, "MarkerSize"):
            obj.addProperty("App::PropertyLength", "MarkerSize", "Display", "Size of position markers")
            obj.MarkerSize = 2.0  # 2mm par défaut

        # Couleur des sphères
        if not hasattr(obj, "MarkerColor"):
            obj.addProperty("App::PropertyColor", "MarkerColor", "Display", "Color of position markers")
            obj.MarkerColor = (1.0, 0.0, 0.0)  # Rouge par défaut

        # Index de la position sélectionnée (-1 si aucune)
        if not hasattr(obj, "SelectedPosition"):
            obj.addProperty("App::PropertyInteger", "SelectedPosition", "Display", "Index of the selected position")
            obj.SelectedPosition = -1

        # Couleur de surbrillance pour la position sélectionnée
        if not hasattr(obj, "HighlightColor"):
            obj.addProperty("App::PropertyColor", "HighlightColor", "Display", "Color of the highlighted position")
            obj.HighlightColor = (1.0, 1.0, 0.0)  # Jaune par défaut

        # Créer ou obtenir l'objet de visualisation
        # self.getOrCreateVisualObject(obj)

        obj.Proxy = self

    def onChanged(self, obj, prop):
        """Appelé quand une propriété est modifiée"""
        if prop == "DrillFaces":
            self.updateDrillParameters(obj)
        elif prop in ["DrillPositions", "MarkerSize", "SelectedPosition"]:
            self.execute(obj)

    def updateDrillParameters(self, obj):
        """Met à jour les paramètres de perçage en fonction des faces sélectionnées"""
        if not obj.DrillFaces:
            return

        positions = []
        diameters = set()
        depths = set()

        for link, subs in obj.DrillFaces:
            # Pour chaque sous-élément dans la liste
            for subname in subs:
                # Obtenir la face
                face = getattr(link.Shape, subname)

                if face.Surface.TypeId == 'Part::GeomCylinder':
                    # Récupérer le centre de la face cylindrique
                    center = face.Surface.Center
                    axis = face.Surface.Axis

                    # Trouver le point le plus haut de la face
                    z_max = float('-inf')
                    for vertex in face.Vertexes:
                        if vertex.Point.z > z_max:
                            z_max = vertex.Point.z

                    # Créer le point au sommet en gardant X,Y du centre
                    pos = App.Vector(center.x, center.y, z_max)
                    positions.append(pos)

                    # Récupérer le diamètre
                    diameters.add(face.Surface.Radius * 2)
                    # App.Console.PrintMessage(f'diam detected {face.Surface.Radius * 2}\n')
                    # Calculer la profondeur en trouvant la face plane associée
                    # TODO: Implémenter la détection de profondeur
                    depths.add(10.0)  # valeur temporaire

        # Mettre à jour les propriétés
        obj.DrillPositions = positions

        # Si tous les perçages ont le même diamètre, le définir
        if len(diameters) == 1:
            obj.DrillDiameter = list(diameters)[0]
        elif len(diameters) > 1:
            # sinon prendre le plus petit
            obj.DrillDiameter = min(diameters)

        # Si tous les perçages ont la même profondeur, la définir
        if len(depths) == 1:
            obj.DrillDepth = list(depths)[0]

    def execute(self, obj):
        """Mettre à jour la représentation visuelle"""
        # Obtenir l'objet de visualisation
        # visual = self.getOrCreateVisualObject(obj)

        if not obj.DrillPositions:
            obj.Shape = Part.Shape()  # Shape vide
            return

        # Créer une sphère pour chaque position
        spheres = []
        highlighted_spheres = []  # Liste séparée pour les sphères en surbrillance
        radius = obj.MarkerSize / 2.0  # Rayon = moitié de la taille

        for i, pos in enumerate(obj.DrillPositions):
            # Utiliser la couleur de surbrillance pour la position sélectionnée
            if i == obj.SelectedPosition:
                # Créer une sphère légèrement plus grande pour la position sélectionnée
                highlight_radius = radius * 1.5
                sphere = Part.makeSphere(highlight_radius, pos)
                # Stocker l'index pour l'utiliser dans ViewProvider
                sphere.Tag = i  # Utiliser Tag pour stocker l'index
                highlighted_spheres.append(sphere)  # Ajouter à la liste des sphères en surbrillance
            else:
                sphere = Part.makeSphere(radius, pos)
                sphere.Tag = i  # Stocker l'index
                spheres.append(sphere)

        # Fusionner toutes les sphères
        if spheres or highlighted_spheres:
            # Créer un compound pour les sphères normales
            normal_compound = Part.makeCompound(spheres) if spheres else Part.Shape()

            # Créer un compound pour les sphères en surbrillance
            highlight_compound = Part.makeCompound(highlighted_spheres) if highlighted_spheres else Part.Shape()

            # Stocker les deux compounds dans des propriétés de l'objet
            if not hasattr(obj, "NormalSpheres"):
                obj.addProperty("App::PropertyPythonObject", "NormalSpheres", "Visualization", "Normal spheres")
            obj.NormalSpheres = normal_compound

            if not hasattr(obj, "HighlightedSpheres"):
                obj.addProperty("App::PropertyPythonObject", "HighlightedSpheres", "Visualization", "Highlighted spheres")
            obj.HighlightedSpheres = highlight_compound

            # Combiner les deux compounds
            all_spheres = spheres + highlighted_spheres
            compound = Part.makeCompound(all_spheres)
            obj.Shape = compound

    def onDocumentRestored(self, obj):
        """Appelé lors de la restauration du document"""
        self.__init__(obj)

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None

    def onBeforeDelete(self, obj, subelements):
        # Custom logic before deletion
        App.Console.PrintMessage("Object is about to be deleted: " + obj.Name + "\n")


class ViewProviderDrillGeometry:
    def __init__(self, vobj):
        """Initialise le ViewProvider"""
        vobj.Proxy = self
        self.Object = vobj.Object

    def getIcon(self):
        """Retourne l'icône"""
        return BaptUtilities.getIconPath("Tree_Drilling.svg")

    def attach(self, vobj):
        """Appelé lors de l'attachement du ViewProvider"""
        self.Object = vobj.Object

        # Définir la couleur de l'objet de visualisation
        self.updateColors()

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        action = menu.addAction("Edit")
        action.triggered.connect(lambda: self.setEdit(vobj))
        return True

    def updateData(self, obj, prop):
        """Appelé quand une propriété de l'objet est modifiée"""
        # Si un nouvel objet de visualisation est ajouté, définir sa couleur
        if prop == "Group":
            self.updateColors()
        # Si la position sélectionnée change, mettre à jour les couleurs
        elif prop in ["SelectedPosition", "MarkerColor", "HighlightColor"]:
            self.updateColors()

    def updateColors(self):
        """Met à jour les couleurs des marqueurs visuels"""
        if not hasattr(self, "Object") or not self.Object:
            return

        # Vérifier si l'objet visuel existe
        # visual = None
        # for child in self.Object.Group:
        #     if child.Name.startswith("DrillVisual") and hasattr(child, "ViewObject"):
        #         visual = child
        #         break

        # if not visual:
        #     return

        # Définir les couleurs en fonction de la position sélectionnée
        if hasattr(self.Object, "SelectedPosition") and self.Object.SelectedPosition >= 0:
            # Vérifier si l'objet visuel a des sphères en surbrillance
            if hasattr(self.Object, "HighlightedSpheres") and self.Object.HighlightedSpheres:
                # Utiliser un ShapeColorExtension pour colorer individuellement les sous-éléments
                if hasattr(self.Object.ViewObject, "DiffuseColor"):
                    # Créer une liste de couleurs pour chaque sous-élément
                    colors = []

                    # Couleur normale pour les sphères normales
                    normal_color = self.Object.MarkerColor

                    # Couleur de surbrillance pour les sphères en surbrillance
                    highlight_color = self.Object.HighlightColor

                    # Appliquer les couleurs appropriées
                    if hasattr(self.Object, "NormalSpheres") and self.Object.NormalSpheres:
                        # Nombre de sous-éléments dans les sphères normales
                        if hasattr(self.Object.NormalSpheres, "SubShapes"):
                            normal_count = len(self.Object.NormalSpheres.SubShapes)
                        else:
                            normal_count = 1

                        # Ajouter la couleur normale pour chaque sphère normale
                        colors.extend([normal_color] * normal_count)

                    # Ajouter la couleur de surbrillance pour chaque sphère en surbrillance
                    if hasattr(self.Object, "HighlightedSpheres") and self.Object.HighlightedSpheres:
                        if hasattr(self.Object.HighlightedSpheres, "SubShapes"):
                            highlight_count = len(self.Object.HighlightedSpheres.SubShapes)
                        else:
                            highlight_count = 1

                        colors.extend([highlight_color] * highlight_count)

                    # Appliquer les couleurs
                    self.Object.ViewObject.DiffuseColor = colors
            else:
                # Aucune sphère en surbrillance, utiliser la couleur normale pour tout
                self.Object.ViewObject.ShapeColor = self.Object.MarkerColor
        else:
            # Aucune position sélectionnée, utiliser la couleur normale pour tout
            self.Object.ViewObject.ShapeColor = self.Object.MarkerColor

    def onChanged(self, vobj, prop):
        """Appelé quand une propriété du ViewProvider est modifiée"""
        pass

    def doubleClicked(self, vobj):
        """Gérer le double-clic"""
        self.setEdit(vobj)
        return True

    def setEdit(self, vobj, mode=0):
        """Ouvrir l'éditeur"""
        import BaptDrillTaskPanel
        panel = BaptDrillTaskPanel.DrillGeometryTaskPanel(vobj.Object)
        Gui.Control.showDialog(panel)
        return True

    def unsetEdit(self, vobj, mode=0):
        """Fermer l'éditeur"""
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        return True

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None

    def claimChildren(self):
        """Retourne les enfants de cet objet"""

        children = []
        # Récupérer tous les objets de contournage qui référencent cette géométrie par son nom
        if self.Object:
            doc = self.Object.Document
            if not doc:
                return children

            # Vérifier que l'objet a un nom valide
            if not hasattr(self.Object, "Name") or not self.Object.Name:
                return children

            for obj in doc.Objects:
                # Vérifier si l'objet est un cycle de contournage
                if hasattr(obj, "Proxy") and hasattr(obj.Proxy, "Type") and obj.Proxy.Type == "DrillOperation":
                    # Vérifier si l'objet référence cette géométrie
                    if hasattr(obj, "DrillGeometryName") and obj.DrillGeometryName == self.Object.Name:
                        children.append(obj)

            # Vérifier si l'objet a un groupe
            if hasattr(self.Object, "Group"):
                # Ajouter tous les objets du groupe qui ne sont pas déjà dans la liste
                for obj in self.Object.Group:
                    if obj not in children:
                        children.append(obj)

        return children

    def onDelete(self, feature, subelements):  # subelements is a tuple of strings

        App.Console.PrintMessage(f"onDelete de {feature.Object.Name}\n")
        for child in feature.Object.Group:
            App.ActiveDocument.removeObject(child.Name)
        return True  # If False is returned the object won't be deleted

    def onBeforeDelete(self, obj, subelements):
        """Supprime tous les enfants lors de la suppression du parent"""
        # debug
        App.Console.PrintMessage(f"onBeforeDelete de {obj.Name}\n")
        children = self.claimChildren()
        for child in children:
            try:
                if child and hasattr(child, "Document") and child.Document:
                    child.Document.removeObject(child.Name)
            except Exception as e:
                App.Console.PrintError(f"Erreur suppression enfant {child.Name}: {e}\n")
