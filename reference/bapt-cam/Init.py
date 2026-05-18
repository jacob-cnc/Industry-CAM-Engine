# -*- coding: utf-8 -*-
import FreeCAD


# class BaptWorkbench (Workbench):
#     def __init__(self):
#         import os
#         import inspect
#         #self.__class__.Icon = os.path.join(os.path.dirname(inspect.getfile(self.__class__)), "resources", "icons", "BaptWorkbench.svg")
#         self.__class__.Icon = BaptUtilities.getIconPath("BaptWorkbench.svg")
#         self.__class__.MenuText = "Bapt"
#         self.__class__.ToolTip = "Bapt Workbench"

#     def Initialize(self):
#         """This function is executed when FreeCAD starts"""
#         # Importer les modules nécessaires
#         import FreeCAD
#         import FreeCADGui
#         import os
#         import BaptCamProject
#         import BaptContourTaskPanel
#         import BaptDrillTaskPanel
#         import BaptMpfReader
#         import BaptCommands # import here all the needed files
#         # Ajouter le répertoire au chemin de recherche Python
#         path = os.path.dirname(__file__)
#         # self.list = ["Bapt_Command"] # A list of command names created in the line above
#         # self.appendToolbar("Bapt Tools", self.list) # creates a new toolbar with your commands
#         # self.appendMenu("Bapt", self.list) # creates a new menu

#     def Activated(self):
#         """This function is executed when the workbench is activated"""
#         return

#     def Deactivated(self):
#         """This function is executed when the workbench is deactivated"""
#         return

#     def GetClassName(self):
#         # this function is mandatory if this is a full Python workbench
#         return "Gui::PythonWorkbench"

# Gui.addWorkbench(BaptWorkbench())


FreeCAD.__unit_test__ += ["TestBaptApp"]
