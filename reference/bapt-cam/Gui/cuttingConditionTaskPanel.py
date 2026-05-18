import FreeCAD as App
from Op.utils import CoolantMode
from PySide import QtGui
from utils import BQuantitySpinBox


class cuttingConditionTaskPanel:
    """Panneau de tâche pour éditer les conditions de coupe"""

    def __init__(self, obj):
        """Initialise le panneau avec l'objet de conditions de coupe"""
        self.obj = obj

        # Créer l'interface utilisateur
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Conditions de coupe")

        self.layout = QtGui.QFormLayout(self.form)

        # Rotations par minute
        self.Speed = BQuantitySpinBox.BQuantitySpinBox(obj, "SpindleSpeed")
        self.Speed.setValue(obj.SpindleSpeed)
        self.layout.addRow("Speed:", self.Speed.getWidget())

        # Avance
        self.Feed = BQuantitySpinBox.BQuantitySpinBox(obj, "FeedRate")
        self.Feed.setValue(obj.FeedRate)
        self.layout.addRow("Feed:", self.Feed.getWidget())

        # lubrification
        self.CoolantMode = QtGui.QComboBox()
        self.CoolantMode.addItems(CoolantMode)
        if hasattr(obj, "CoolantMode"):
            idx = self.CoolantMode.findText(obj.CoolantMode)
            self.CoolantMode.setCurrentIndex(idx)
        self.layout.addRow("Coolant Mode:", self.CoolantMode)

        button = QtGui.QPushButton("Use Tool Settings")
        button.clicked.connect(lambda: self.useToolSettings())
        self.layout.addRow(button)

        self.CoolantMode.currentTextChanged.connect(lambda: self.updateCoolantMode())

    def getLayout(self):
        """Retourne le layout du panneau de tâche"""
        return self.layout

    def getForm(self):
        """Retourne le formulaire du panneau de tâche"""
        return self.form

    def updateCoolantMode(self):
        """Met à jour le mode de lubrification"""
        self.obj.CoolantMode = self.CoolantMode.currentText()

    def useToolSettings(self):
        """Utilise les paramètres de l'outil pour les conditions de coupe"""
        if self.obj.Tool:
            self.obj.SpindleSpeed = self.obj.Tool.Speed
            self.obj.FeedRate = self.obj.Tool.Feed
            self.Speed.setValue(self.obj.Tool.Speed)
            self.Feed.setValue(self.obj.Tool.Feed)
            App.Console.PrintMessage(f'Using tool settings: Speed={self.obj.Tool.Speed}, Feed={self.obj.Tool.Feed}\n')
        else:
            App.Console.PrintMessage('No tool assigned to the operation.\n')
