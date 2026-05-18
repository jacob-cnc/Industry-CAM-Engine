import FreeCAD
import FreeCAD as App
import FreeCADGui
from PySide import QtGui
from pivy import coin  # pyright: ignore[reportMissingImports]
from utils import PointSelectionObserver


class Origin:
    """
    Objet Origine pour l'usinage (G54, G55, etc.) avec nom, numéro et placement.
    """

    def __init__(self, obj):
        obj.Proxy = self
        self.Type = "Origin"
        self.initProperties(obj)

    def initProperties(self, obj):
        obj.addProperty("App::PropertyString", "OriginName", "Origin", "Nom de l'origine").OriginName = "Origine pièce"
        obj.addProperty("App::PropertyString", "OriginNumber", "Origin", "Numéro d'origine (G54, G55...)").OriginNumber = "G54"
        obj.addProperty("App::PropertyPlacement", "Placement", "Origin", "Placement de l'origine").Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0, 1))

    def execute(self, obj):
        # Pas de géométrie calculée, juste l'affichage
        pass


class ViewProviderOrigin:
    def __init__(self, vobj):
        vobj.Proxy = self

    def buildScene(self, vobj):
        root = coin.SoGroup()
        pl = vobj.Object.Placement
        pos = pl.Base
        translation = coin.SoTranslation()
        translation.translation.setValue(pos.x, pos.y, pos.z)
        root.addChild(translation)
        axis_len = 8.0
        # X (rouge)
        x_line = coin.SoSeparator()
        x_color = coin.SoBaseColor()
        x_color.rgb = (1, 0, 0)
        x_line.addChild(x_color)
        x_coords = coin.SoCoordinate3()
        x_coords.point.setValues(0, 2, [(0, 0, 0), (axis_len, 0, 0)])
        x_line.addChild(x_coords)
        x_line.addChild(coin.SoLineSet())
        root.addChild(x_line)
        # Y (vert)
        y_line = coin.SoSeparator()
        y_color = coin.SoBaseColor()
        y_color.rgb = (0, 1, 0)
        y_line.addChild(y_color)
        y_coords = coin.SoCoordinate3()
        y_coords.point.setValues(0, 2, [(0, 0, 0), (0, axis_len, 0)])
        y_line.addChild(y_coords)
        y_line.addChild(coin.SoLineSet())
        root.addChild(y_line)
        # Z (bleu)
        z_line = coin.SoSeparator()
        z_color = coin.SoBaseColor()
        z_color.rgb = (0, 0, 1)
        z_line.addChild(z_color)
        z_coords = coin.SoCoordinate3()
        z_coords.point.setValues(0, 2, [(0, 0, 0), (0, 0, axis_len)])
        z_line.addChild(z_coords)
        z_line.addChild(coin.SoLineSet())
        root.addChild(z_line)
        # Texte (numéro d'origine)
        text_sep = coin.SoSeparator()
        text_color = coin.SoBaseColor()
        text_color.rgb = (0.2, 0.2, 0.8)
        text_sep.addChild(text_color)
        translation = coin.SoTranslation()
        translation.translation = (axis_len + 2, 0, 0)
        text_sep.addChild(translation)
        text = coin.SoText2()
        try:
            obj = vobj.Object
            text.string = obj.OriginNumber if hasattr(obj, 'OriginNumber') else "G54"
        except Exception:
            text.string = "G54"
        text_sep.addChild(text)
        root.addChild(text_sep)
        return root

    def attach(self, vobj):
        self.root = self.buildScene(vobj)
        vobj.addDisplayMode(self.root, "Axes")

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        action = menu.addAction("Edit")
        action.triggered.connect(lambda: self.setEdit(vobj))

    def setEdit(self, vobj, mode=0):
        """Ouvre le panneau de tâches pour l'édition de l'origine"""
        try:
            import importlib
            importlib.reload(OriginTaskPanel)
        except Exception:
            pass
        FreeCADGui.Control.showDialog(OriginTaskPanel(vobj.Object))

    def doubleClicked(self, vobj):
        """Appelé lors d'un double-clic sur l'objet"""
        self.setEdit(vobj)
        return True

    def updateData(self, fp, prop):
        # Reconstruit le repère à chaque modification de propriété
        if hasattr(self, 'root'):
            # Supprime tous les enfants
            self.root.removeAllChildren()
            # Reconstruit la scène avec la nouvelle position
            new_root = self.buildScene(fp.ViewObject)
            for i in range(new_root.getNumChildren()):
                self.root.addChild(new_root.getChild(i))

    def getDisplayModes(self, vobj):
        return ["Axes"]

    def getDefaultDisplayMode(self):
        return "Axes"

    def setDisplayMode(self, vobj, mode=None):
        return self.getDefaultDisplayMode() if mode is None else mode

    def onDelete(self, vobj, subelements):
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class OriginTaskPanel:
    def __init__(self, obj):
        # super().__init__()
        self.obj = obj
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Édition de l'origine")
        layout = QtGui.QFormLayout(self.form)
        # Nom
        self.nameEdit = QtGui.QLineEdit(obj.OriginName)
        layout.addRow("Nom", self.nameEdit)
        # Numéro
        self.numberEdit = QtGui.QLineEdit(obj.OriginNumber)
        layout.addRow("Numéro (G54...)", self.numberEdit)
        # Placement (XYZ)
        pl = obj.Placement
        self.xSpin = QtGui.QDoubleSpinBox()
        self.xSpin.setRange(-10000, 10000)
        self.xSpin.setValue(pl.Base.x)
        self.ySpin = QtGui.QDoubleSpinBox()
        self.ySpin.setRange(-10000, 10000)
        self.ySpin.setValue(pl.Base.y)
        self.zSpin = QtGui.QDoubleSpinBox()
        self.zSpin.setRange(-10000, 10000)
        self.zSpin.setValue(pl.Base.z)
        coordLayout = QtGui.QHBoxLayout()
        coordLayout.addWidget(QtGui.QLabel('X:'))
        coordLayout.addWidget(self.xSpin)
        coordLayout.addWidget(QtGui.QLabel('Y:'))
        coordLayout.addWidget(self.ySpin)
        coordLayout.addWidget(QtGui.QLabel('Z:'))
        coordLayout.addWidget(self.zSpin)
        layout.addRow("Position", coordLayout)
        # Boutons
        btnLayout = QtGui.QHBoxLayout()
        self.okBtn = QtGui.QPushButton("OK")
        self.cancelBtn = QtGui.QPushButton("Annuler")
        btnLayout.addWidget(self.okBtn)
        btnLayout.addWidget(self.cancelBtn)
        layout.addRow(btnLayout)
        self.okBtn.clicked.connect(self.accept)
        self.cancelBtn.clicked.connect(self.reject)

        self.clickOnPartBtn = QtGui.QPushButton("Click on Part")
        self.clickOnPartBtn.clicked.connect(self.clickOnPart)
        btnLayout.addWidget(self.clickOnPartBtn)

    def clickOnPart(self):
        """Appelé quand l'utilisateur clique sur le bouton Click on Part"""
        # Changer le texte du bouton pour indiquer que l'on attend un clic
        self.clickOnPartBtn.setText("Cliquez sur un point...")
        self.clickOnPartBtn.setEnabled(False)

        # Créer et activer l'observer
        self.observer = PointSelectionObserver.PointSelectionObserver(self.pointSelected)
        self.observer.enable()

    def pointSelected(self, point):
        """Appelé quand l'utilisateur a cliqué sur un point"""
        # Mettre à jour les coordonnées du stock origin

        self.xSpin.setValue(point.x)
        self.ySpin.setValue(point.y)
        self.zSpin.setValue(point.z)

        # Mettre à jour la représentation visuelle
        self.updateVisual()

        # Remettre le bouton dans son état initial
        self.clickOnPartBtn.setText("Click on Part")
        self.clickOnPartBtn.setEnabled(True)

    def updateVisual(self):
        self.obj.Placement.Base.x = self.xSpin.value()
        self.obj.Placement.Base.y = self.ySpin.value()
        self.obj.Placement.Base.z = self.zSpin.value()

    def accept(self):
        self.obj.OriginName = self.nameEdit.text()
        self.obj.OriginNumber = self.numberEdit.text()
        pl = self.obj.Placement
        pl.Base.x = self.xSpin.value()
        pl.Base.y = self.ySpin.value()
        pl.Base.z = self.zSpin.value()
        self.obj.Placement = pl
        FreeCAD.ActiveDocument.recompute()
        FreeCADGui.Control.closeDialog()

    def reject(self):
        FreeCADGui.Control.closeDialog()


# Fonction de création utilitaire
def createOrigin(origin_name="Origine pièce", origin_number="G54", placement=None):
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", "Origin")
    Origin(obj)
    ViewProviderOrigin(obj.ViewObject)
    obj.OriginName = origin_name
    obj.OriginNumber = origin_number
    if placement:
        obj.Placement = placement
    return obj
