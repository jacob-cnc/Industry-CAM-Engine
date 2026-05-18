import sys
from BaptUtilities import find_cam_project, getIconPath
import FreeCAD as App
import FreeCADGui as Gui

from PySide import QtCore, QtGui
from Tool import ToolSelectorDialog, tool_utils

from utils import Log
import utils.BQuantitySpinBox as BQantitySpinBox


class ToolTaskPanel:
    def __init__(self, obj, parent=None):

        self.obj = obj
        self.parent = parent

        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Sélection d'outil")
        self.form.setWindowIcon(QtGui.QIcon(getIconPath("tool.svg")))

        layout = QtGui.QVBoxLayout(self.form)

        self.selectToolButton = QtGui.QPushButton("Sélectionner un outil")
        layout.addWidget(self.selectToolButton)

        self.toolComboBox = QtGui.QComboBox()
        layout.addWidget(self.toolComboBox)

        self.toolLayout = QtGui.QFormLayout()
        # champ pour afficher l'outil sélectionné
        self.selectedToolLabel = QtGui.QLabel("Aucun outil sélectionné")
        layout.addWidget(self.selectedToolLabel)

        # champ edit id
        self.idTool = QtGui.QSpinBox()
        self.idTool.setRange(0, 10000)
        self.toolLayout.addRow("ID Outil:", self.idTool)

        # champ edit name
        self.nameTool = QtGui.QLineEdit()
        self.toolLayout.addRow("Nom Outil:", self.nameTool)

        # champ d'edition diametre
        self.diameter = QtGui.QDoubleSpinBox()
        self.diameter.setRange(0, 100)
        self.toolLayout.addRow("Diamètre:", self.diameter)

        # champ d'edition Speed
        self.speed = QtGui.QDoubleSpinBox()
        self.speed = BQantitySpinBox.BQuantitySpinBox(self.obj, "Tool.Speed")
        # self.speed.setRange(0, 10000)
        self.toolLayout.addRow("Vitesse de coupe (RPM):", self.speed.getWidget())

        # champ d'edition Feed
        # self.feed = QtGui.QDoubleSpinBox()
        self.feed = BQantitySpinBox.BQuantitySpinBox(self.obj, "Tool.Feed")
        # self.feed.setRange(0, 10000)
        self.toolLayout.addRow("Vitesse d'avance:", self.feed.getWidget())

        layout.addLayout(self.toolLayout)

        self.initValues()

        self.initListeners()

    def onToolComboBoxChanged(self):

        tool = self.toolComboBox.currentText()
        if tool:
            self.obj.Tool = App.ActiveDocument.getObject(tool)
            self.selectedToolLabel.setText(f"Outil sélectionné: {self.obj.Tool.Name} (ID: {self.obj.Tool.Id})")
            self.diameter.setValue(self.obj.Tool.Radius * 2.0)
            self.idTool.setValue(self.obj.Tool.Id)
            self.nameTool.setText(self.obj.Tool.Name)
            self.speed.setValue(self.obj.Tool.Speed)
            self.feed.setValue(self.obj.Tool.Feed)

    def selectTool(self):
        """Ouvre le dialogue de sélection d'outil"""

        current_tool = getattr(self.obj, "Tool", None)

        dialog = ToolSelectorDialog.ToolSelectorDialog(current_tool.Id if current_tool else -1, self.form)
        result = dialog.exec_()
        sel = dialog.selected_tool
        if result == QtGui.QDialog.Rejected and sel is None:
            return
        # Récupérer le projet CAM actif
        p = find_cam_project(self.obj)
        if not p:
            return

        groupTools = p.Proxy.getToolsGroup()

        if current_tool is None or current_tool.Id != sel.id:
            new_tool = tool_utils.create_tool_obj(sel.id, sel.name, sel.diameter, sel.speed, sel.feed)
            groupTools.addObject(new_tool)
            new_tool.recompute()
            self.obj.Tool = new_tool

            if current_tool is not None:
                # Supprimer l'ancien outil s'il n'est utilisé par aucun autre objet
                if len(current_tool.InList) <= 1:
                    App.Console.PrintMessage("L'outil n'est utilisé par plusieurs objets, il sera supprimé.\n")
                    groupTools.removeObject(current_tool)
                    App.ActiveDocument.removeObject(current_tool.Label)

        App.Console.PrintMessage(f'label: {self.obj.Tool.Label}\n')
        new_tool.Height = sel.length
        self.idTool.setValue(sel.id)
        self.nameTool.setText(sel.name)
        self.diameter.setValue(sel.diameter)
        self.speed.updateWidget()
        self.feed.updateWidget()

        self.obj.recompute()

        self.initToolComboBox()

    def initValues(self):

        self.initToolComboBox()

        if hasattr(self.obj, "Tool") and self.obj.Tool is not None:
            tool = self.obj.Tool
            self.selectedToolLabel.setText(f"Outil sélectionné: {tool.Name} (ID: {tool.Id})")
            self.diameter.setValue(tool.Radius * 2.0)
            self.idTool.setValue(tool.Id)
            self.nameTool.setText(tool.Name)
            # self.speed.setValue(tool.Speed)
            # self.feed.setValue(tool.Feed)

    def initToolComboBox(self):
        '''populate tool combo box'''
        p = find_cam_project(self.obj)
        if not p:
            return

        groupTools = p.Proxy.getToolsGroup()
        self.toolComboBox.clear()
        for t in groupTools.Group:
            self.toolComboBox.addItem(t.Label)
        if hasattr(self.obj, "Tool") and self.obj.Tool is not None:
            idx = self.toolComboBox.findText(self.obj.Tool.Label)
            Log.baptDebug(f'Finding tool {self.obj.Tool.Label} in tool group idx {idx}\n')
            if idx >= 0:
                self.toolComboBox.setCurrentIndex(idx)
        else:
            self.toolComboBox.setCurrentIndex(-1)

    def initListeners(self):
        self.selectToolButton.clicked.connect(lambda: self.selectTool())
        self.idTool.valueChanged.connect(lambda: self.updateToolId())
        self.nameTool.textChanged.connect(lambda: self.updateToolName())
        self.diameter.valueChanged.connect(lambda: self.updateToolDiameter())
        self.toolComboBox.currentTextChanged.connect(lambda: self.onToolComboBoxChanged())

    def updateToolDiameter(self):
        if hasattr(self.obj, "Tool") and self.obj.Tool is not None:
            tool = self.obj.Tool
            tool.Radius = self.diameter.value() / 2.0

    def updateToolId(self):
        if hasattr(self.obj, "Tool") and self.obj.Tool is not None:
            tool = self.obj.Tool
            tool.Id = self.idTool.value()
            self.selectedToolLabel.setText(f"Outil sélectionné: {tool.Name} (ID: {tool.Id})")

    def updateToolName(self):
        if hasattr(self.obj, "Tool") and self.obj.Tool is not None:
            tool = self.obj.Tool
            tool.Name = self.nameTool.text()
            self.selectedToolLabel.setText(f"Outil sélectionné: {tool.Name} (ID: {tool.Id})")

    def getForm(self):
        return self.form
