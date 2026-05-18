import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
import BaptUtilities
import Part
from Tool import ToolSelectorDialog


class ProbeFace:
    def __init__(self, obj):

        obj.addProperty("App::PropertyLinkSub", "Face", "Base", "Face à mesurer")
        obj.addProperty("App::PropertyVector", "Origin", "Base", "Point d'origine")
        obj.addProperty("App::PropertyVector", "Direction", "Base", "Direction de l'outil")
        obj.addProperty("App::PropertyVector", "UV", "Base", "UV")
        obj.addProperty("App::PropertyLength", "NormalLength", "Base", "Longueur de la normal")
        obj.NormalLength = 10

        obj.Proxy = self

    def execute(self, obj):
        if App.ActiveDocument.Restoring:
            return

        obj.Shape = Part.Shape()

        if not obj.Face or not obj.Origin or not obj.Direction:
            return

        if obj.Direction == App.Vector(0, 0, 0):
            return

        print(obj.Face)
        # surface = App.getDocument(obj.Face[0].Document).getObject(obj.Face[0].Object).Shape.getElement(obj.Face[1])
        # obj.Direction = surface.normalAt(0, 0)

        Sphere = Part.makeSphere(1, obj.Origin)
        print(f'obj.Origin: {obj.Origin}')
        print(f'obj.Direction: {obj.Direction}')
        print(f'obj.Direction * 10: {obj.Origin + (obj.Direction * obj.NormalLength)}')
        Normal = Part.makeLine(obj.Origin, obj.Origin + (obj.Direction * obj.NormalLength))
        normalWire = Part.Wire([Normal])
        compound = Part.makeCompound([Sphere, normalWire])
        obj.Shape = compound

        pass

    def onChanged(self, obj, prop):
        if prop in ["Face", "Origin", "Direction", "NormalLength"]:
            self.execute(obj)
        pass

    def onDocumentRestored(self, obj):
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        print(f"state: {state}")
        return None


class ViewProviderProbeFace:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.Object = vobj.Object

    def getIcon(self):
        return BaptUtilities.getIconPath("ProbeSurface.svg")

    def attach(self, vobj):
        self.Object = vobj.Object

    def setupContextMenu(self, vobj, menu):
        action = menu.addAction("Edit")
        action.triggered.connect(lambda: self.setEdit(vobj))

    def setEdit(self, vobj):
        """Démarrer l'édition"""
        Gui.Control.showDialog(ProbeFaceTaskPanel(vobj.Object))
        return True

    def unsetEdit(self, vobj):
        """Fermer l'édition"""
        Gui.Control.closeDialog()
        return True

    def doubleClicked(self, vobj):
        """Appelé lorsque l'objet est double-cliqué"""
        # Ouvrir le panneau de tâche pour l'édition
        self.setEdit(vobj)
        return True

    def getDisplayModes(self, vobj):
        """Retourne les modes d'affichage disponibles"""
        return ["Flat Lines", "Shaded", "Wireframe"]

    def getDefaultDisplayMode(self):
        """Retourne le mode d'affichage par défaut"""
        return "Flat Lines"

    def setDisplayMode(self, mode):
        """Définit le mode d'affichage"""
        return mode


class ProbeFaceTaskPanel:
    def __init__(self, obj):
        self.obj = obj

        # Créer l'interface utilisateur
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Éditer le cycle")
        layout = QtGui.QVBoxLayout(self.form)

        # bouton pour la selection de la face
        self.selectFaceButton = QtGui.QPushButton("Sélectionner la face")
        self.selectFaceButton.clicked.connect(self.selectFace)
        layout.addWidget(self.selectFaceButton)

        # champ pour l'origine
        self.originLabel = QtGui.QLabel("Origine:")
        layout.addWidget(self.originLabel)
        self.originEdit = QtGui.QLineEdit()
        layout.addWidget(self.originEdit)

        # champ pour la direction
        self.directionLabel = QtGui.QLabel("Direction:")
        layout.addWidget(self.directionLabel)

        # champ pour la longueur de la normal
        self.normalLengthLabel = QtGui.QLabel("Longueur de la normal:")
        layout.addWidget(self.normalLengthLabel)

        # Groupe pour l'outil
        toolGroup = QtGui.QGroupBox("Outil")
        toolLayout = QtGui.QVBoxLayout()

        # Informations sur l'outil sélectionné
        self.toolInfoLayout = QtGui.QFormLayout()
        self.toolIdLabel = QtGui.QLabel("Aucun outil sélectionné")
        self.toolNameLabel = QtGui.QLabel("")
        self.toolTypeLabel = QtGui.QLabel("")
        self.toolDiameterLabel = QtGui.QLabel("")

        self.toolInfoLayout.addRow("ID:", self.toolIdLabel)
        self.toolInfoLayout.addRow("Nom:", self.toolNameLabel)
        self.toolInfoLayout.addRow("Type:", self.toolTypeLabel)
        self.toolInfoLayout.addRow("Diamètre:", self.toolDiameterLabel)

        toolLayout.addLayout(self.toolInfoLayout)

        # Bouton pour sélectionner un outil
        self.selectToolButton = QtGui.QPushButton("Sélectionner un outil")
        self.selectToolButton.clicked.connect(self.selectTool)
        toolLayout.addWidget(self.selectToolButton)

        toolGroup.setLayout(toolLayout)
        layout.addWidget(toolGroup)

    def selectTool(self):
        """Sélectionner un outil"""
        dialog = ToolSelectorDialog.ToolSelectorDialog(self.obj.ToolID)
        if dialog.exec_():
            self.obj.ToolID = dialog.selected_tool_id
            self.updateToolInfo()

    def selectFace(self):
        """Sélectionner la face"""
        Gui.Selection.clearSelection()

        self.surfaceSelectionObserver = SurfaceSelectionObserver(self.onSelection)
        self.surfaceSelectionObserver.enable()

    def onSelection(self, doc, obj, sub, pos):
        """Appelé quand l'utilisateur sélectionne quelque chose"""
        print(f"Selection: {obj} {sub}")
        # self.obj.Face = App.getDocument(doc).getObject(obj).Shape.getElement(sub)
        self.obj.Face = (App.getDocument(doc).getObject(obj), [sub])
        self.obj.Origin = pos

        # face2 = App.getDocument(doc).getObject(obj).Shape.getSubObject(sub)
        print(self.obj.Face)
        print(self.obj.Face[0])
        surface = App.getDocument(doc).getObject(obj).Shape.getElement(sub)
        print(f"surface: {surface}")
        u, v = surface.Surface.parameter(pos)
        print(f"u,v: {u},{v}")
        self.obj.UV = App.Vector(u, v, 0)
        # print(App.getDocument(doc).getObject(obj).Shape.getElement(sub))
        # self.obj.Face[0].CenterOfMass()

        # self.obj.Direction = obj.Shape.getElement(sub).NormalAt(0, 0)
        # self.obj.Direction = self.obj.Face[0].NormalAt(0, 0)
        # self.obj.Direction = self.obj.Face[0].Shape.getElement(sub).NormalAt(0, 0)
        self.obj.Direction = surface.normalAt(u, v)

        self.surfaceSelectionObserver.disable()

    def confirmSelection(self):
        """Confirmer la sélection"""

    def reject(self):
        """Rejeter la sélection"""
        self.surfaceSelectionObserver.disable()
        Gui.Control.closeDialog()

    def accept(self):
        """Accepter la sélection"""
        self.surfaceSelectionObserver.disable()
        Gui.Control.closeDialog()


class SurfaceSelectionObserver:
    def __init__(self, callback):
        self.callback = callback
        self.active = False

    def enable(self):
        """Activer l'observer"""
        self.active = True
        Gui.Selection.addSelectionGate("SELECT Part::Feature SUBELEMENT Face")
        Gui.Selection.addObserver(self)
        App.Console.PrintMessage("Observer activé. Cliquez sur une face de la pièce.\n")

    def disable(self):
        """Désactiver l'observer"""
        self.active = False
        Gui.Selection.removeObserver(self)
        Gui.Selection.removeSelectionGate()
        App.Console.PrintMessage("Observer désactivé.\n")

    def addSelection(self, document, object, element, position):
        """Appelé quand l'utilisateur sélectionne quelque chose"""
        if not self.active:
            return

        # Récupérer les coordonnées du point sélectionné
        point = App.Vector(position[0], position[1], position[2])
        App.Console.PrintMessage(f"Point sélectionné: {point.x}, {point.y}, {point.z}\n")

        # Appeler le callback avec le point
        self.callback(document, object, element, point)

        # Désactiver l'observer après la sélection
        self.disable()
