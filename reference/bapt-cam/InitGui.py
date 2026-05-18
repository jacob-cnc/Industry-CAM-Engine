# -*- coding: utf-8 -*-

"""
InitGui.py for Bapt Workbench
This file is executed when FreeCAD starts up and loads your workbench
"""

import FreeCAD as App
import FreeCADGui as Gui
from FreeCADGui import Workbench
import os


class BaptWorkbench (Workbench):
    def __init__(self):
        self.__class__.MenuText = "Bapt"
        self.__class__.ToolTip = "Bapt Workbench"
        import BaptUtilities
        self.__class__.Icon = BaptUtilities.getIconPath("BaptWorkbench.svg")

    def Initialize(self):
        """This function is executed when the workbench is first activated.
        It is executed once in a FreeCAD session."""
        import BaptCommands
        import BaptTools

        self.addExamplePath()

        translate = App.Qt.translate
        import BaptUtilities
        App.Console.PrintMessage(f'Activing tr {os.path.join(BaptUtilities.getResourcesPath(), "translations")}\n')
        Gui.addLanguagePath(os.path.join(BaptUtilities.getResourcesPath(), "translations"))
        # Gui.addLanguagePath(r"C:\\Users\\Baptou88\\AppData\\Roaming\\FreeCAD\\Mod\\Bapt\\resources\\translations")
        # Gui.addLanguagePath("C:/Users/Baptou88/AppData/Roaming/FreeCAD/Mod/Bapt/resources/translations")
        # Gui.addLanguagePath("C:/Users/Baptou88/AppData/Roaming/FreeCAD/Mod/Bapt/resources/translations/")

        from PySide.QtCore import QT_TRANSLATE_NOOP

        # Register preferences
        from BaptPreferences import BaptPreferencesPage
        Gui.addPreferencePage(BaptPreferencesPage, QT_TRANSLATE_NOOP("QObject", "Bapt"))
        Gui.addIconPath(os.path.join(BaptUtilities.getResourcesPath(), "icons"))

        self.list = ["Bapt_CreateCamProject", "Bapt_CreateSurfacage", "Bapt_CreateDrillGeometry", "Bapt_CreateDrillOperation", "Bapt_HoleRecognition", "Bapt_ToolsManager", "Bapt_CreateContourGeometry", "Bapt_CreateContourEditableGeometry", "Bapt_CreateMachiningCycle", "Bapt_CreatePocketOperation", "Bapt_CreateOrigin", "Bapt_CreateHotReload", "ImportMpf", "Bapt_PostProcessGCode", "Bapt_CreateProbeFace", "Bapt_TestPath", "Bapt_HighlightCollisions", "Bapt_CreateAdaptativeOperation"]  # Ajout des commandes d'opération, poche et origine
        self.appendToolbar("Bapt Tools", self.list)
        self.appendMenu("Bapt", self.list)

    def Activated(self):
        """This function is executed whenever the workbench is activated"""
        return

    def Deactivated(self):
        """This function is executed whenever the workbench is deactivated"""
        return

    def GetClassName(self):
        """This function is mandatory if this is a full Python workbench"""
        return "Gui::PythonWorkbench"

    def addExamplePath(self):
        """Add the examples path to FreeCAD's standard paths"""
        start_prefs = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Start")
        customFolder = start_prefs.GetString(
            "CustomFolder", ""
        )  # Note: allow multiple locations separated by ";;"

        customFolders = [f.strip() for f in customFolder.split(";;") if f.strip()]
        import BaptUtilities
        exPath = BaptUtilities.getExamplesPath()

        if exPath not in customFolders:
            # boite de dialogue pour demander à l'utilisateur s'il veut ajouter le dossier d'exemples

            from PySide import QtWidgets, QtCore, QtGui
            msgBox = QtWidgets.QMessageBox()
            msgBox.setIcon(QtWidgets.QMessageBox.Question)
            msgBox.setWindowTitle("Add Examples Folder")
            msgBox.setText("Do you want to add the Bapt examples folder to the Start workbench?")
            msgBox.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msgBox.setDefaultButton(QtWidgets.QMessageBox.Yes)
            ret = msgBox.exec()
            if ret != QtWidgets.QMessageBox.Yes:
                return
            customFolders.append(exPath)
            newCustomFolder = ";;".join(customFolders)
            start_prefs.SetString("CustomFolder", newCustomFolder)
            msgBox = QtWidgets.QMessageBox()
            msgBox.setIcon(QtWidgets.QMessageBox.Information)
            msgBox.setWindowTitle("Add Examples Folder")
            msgBox.setText("The Bapt examples folder has been added to the Start workbench.\nYou may need to restart FreeCAD for the changes to take effect.")
            msgBox.exec()
            # class addExamplePath(QtGui.QMainWindow):
            #     def __init__(self):
            #         super(addExamplePath, self).__init__()
            #         self.initUI()
            #     def initUI(self):
            #         self.result = "Canceled"
            #         # create our window
            #         # define window		xLoc,yLoc,xDim,yDim
            #         self.setGeometry(	250, 250, 400, 150)
            #         self.setWindowTitle("Add Examples Folder")
            #         self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
            #         self.setMouseTracking(True)
            #         # create Labels
            #         self.label4 = QtGui.QLabel("Do you want to add the Bapt examples folder to the Start workbench?", self)
            #         self.label4.move(20, 20)
            #         # cancel button
            #         cancelButton = QtGui.QPushButton('Cancel', self)
            #         cancelButton.clicked.connect(self.onCancel)
            #         cancelButton.setAutoDefault(True)
            #         cancelButton.move(150, 110)
            #         # OK button
            #         okButton = QtGui.QPushButton('OK', self)
            #         okButton.clicked.connect(self.onOk)
            #         okButton.move(260, 110)
            #         # now make the window visible
            #         self.show()
            #     def onCancel(self):
            #         self.result			= "Canceled"
            #         self.close()
            #     def onOk(self):
            #         self.result			= "OK"
            #         self.close()

            # form = addExamplePath()


Gui.addWorkbench(BaptWorkbench())
