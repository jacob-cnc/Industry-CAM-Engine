# -*- coding: utf-8 -*-

"""
BaptCommands.py
Contient les commandes principales du workbench
"""

import BaptCamProject
import BaptContourEditableGeometry
import BaptContourGeometry
import BaptDrillGeometry
from BaptHighlight import CreateHighlightCommand
import BaptMpfReader
import BaptPath
import Op.AdaptativeOp as AdaptativeOp
import Op.BaptPocketOp as BaptPocketOp
import BaptPostProcess
import BaptPreferences
import BaptTools
import BaptUtilities
import FreeCAD as App
import FreeCADGui as Gui
import os

import BaptOrigin

from Op import DrillOp, OpContournage, OpSurfacage, PathOp
from Probe import probeFace
from PySide import QtCore, QtGui

from utils import BQuantitySpinBox


class CreateOriginCommand:
    """Commande pour créer une origine d'usinage (G54, G55, ...)."""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("Origin.svg"),
                'MenuText': "Nouvelle Origine",
                'ToolTip': "Créer une nouvelle origine d'usinage (G54, G55, ...)."}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        doc = App.ActiveDocument
        doc.openTransaction('Create Origin')
        obj = BaptOrigin.createOrigin()
        doc.recompute()
        doc.commitTransaction()
        App.Console.PrintMessage(f"Origine créée : {obj.OriginName} ({obj.OriginNumber})\n")


class CreateAdaptativeOperationCommand:
    """Commande pour créer une opération de fraisage adaptatif (trochoïdal)"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("AdaptativeOp.svg"),
                'MenuText': "Nouvelle opération adaptive",
                'ToolTip': "Créer une opération de fraisage adaptatif trochoïdal"}

    def IsActive(self):
        sel = Gui.Selection.getSelection()
        return sel and hasattr(sel[0], "Proxy") and sel[0].Proxy.Type == "ContourGeometry"

    def Activated(self):
        doc = App.ActiveDocument
        doc.openTransaction('Create Adaptive Operation')
        contour_geometry = Gui.Selection.getSelection()[0]
        obj = AdaptativeOp.createAdaptativeOperation(contour=contour_geometry)
        doc.recompute()
        doc.commitTransaction()
        App.Console.PrintMessage(
            f"Opération adaptive créée et liée à {contour_geometry.Label}.\n")


class CreatePocketOperationCommand:
    """Commande pour créer une opération de poche basée sur ContourGeometry"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("Pocket.svg"),
                'MenuText': "Nouvelle opération de poche",
                'ToolTip': "Créer une nouvelle opération de poche pour l'usinage"}

    def IsActive(self):
        sel = Gui.Selection.getSelection()
        return sel and hasattr(sel[0], "Proxy") and sel[0].Proxy.Type == "ContourGeometry"

    def Activated(self):
        doc = App.ActiveDocument
        doc.openTransaction('Create Pocket Operation')
        contour_geometry = Gui.Selection.getSelection()[0]
        obj = BaptPocketOp.createPocketOperation(contour=contour_geometry)
        # if obj.ViewObject:
        #     BaptPocketOperation.ViewProviderPocketOperation(obj.ViewObject)
        #     obj.ViewObject.Proxy.setEdit(obj.ViewObject)
        doc.recompute()
        doc.commitTransaction()
        App.Console.PrintMessage(f"Opération de poche créée et liée à {contour_geometry.Label}.\n")


class CreateContourCommand:
    """Commande pour créer un Contournage"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("Contournage.svg"),
                'MenuText': "Nouveau Contournage",
                'ToolTip': "Créer un nouveau contournage pour l'usinage"}

    def IsActive(self):
        """La commande est active si une geometrie de contour est sélectionné"""
        sel = Gui.Selection.getSelection()
        if not sel:
            return False
        # return hasattr(sel[0], "Proxy") and sel[0].Proxy.Type == "ContourGeometry"
        return hasattr(sel[0], "Proxy") and sel[0].Proxy.Type == "ContourGeometry"

    def Activated(self):
        """Créer un nouveau contournage"""
        doc = App.ActiveDocument
        doc.openTransaction('Create Contour')

        # Obtenir la géométrie de contour sélectionnée
        contour_geometry = Gui.Selection.getSelection()[0]

        # Créer l'objet de contournage
        obj = doc.addObject("Part::FeaturePython", "Contournage")

        pref = BaptPreferences.BaptPreferences()
        modeAjout = pref.getModeAjout()

        # 0 = ajouter à la géométrie comme enfant et au groupe opérations du projet CAM comme lien
        # 1 = ajouter à la géométrie comme enfant (pas conseillé)
        # 2 = ajouter au groupe opérations du projet CAM

        if modeAjout == 1 or modeAjout == 0:

            # Ajouter le contournage comme enfant de la géométrie du contour
            contour_geometry.addObject(obj)
            contour_geometry.Group.append(obj)

        if modeAjout == 2 or modeAjout == 0:
            camProject = BaptUtilities.find_cam_project(contour_geometry)
            if camProject:
                operations_group = camProject.Proxy.getOperationsGroup(camProject)
                if modeAjout == 2:
                    operations_group.addObject(obj)
                    operations_group.Group.append(obj)
                elif modeAjout == 0:
                    link = doc.addObject('App::Link', f'Link_{obj.Label}')
                    link.setLink(obj)
                    operations_group.addObject(link)
                    operations_group.Group.append(link)

        # Ajouter la fonctionnalité
        contour = OpContournage.ContournageCycle(obj)

        # Ajouter le ViewProvider
        if obj.ViewObject:
            OpContournage.ViewProviderContournageCycle(obj.ViewObject)

        # Lier à la géométrie du contour par son nom
        obj.ContourGeometryName = contour_geometry.Name

        # # Ajouter le contournage comme enfant de la géométrie du contour
        # # Vérifier si la géométrie du contour est un groupe (a l'extension Group)
        # if hasattr(contour_geometry, "Group") and hasattr(contour_geometry, "addObject"):
        #     # Ajouter directement à la géométrie du contour
        #     contour_geometry.addObject(obj)
        #     App.Console.PrintMessage(f"Contournage ajouté comme enfant de {contour_geometry.Label}\n")
        # else:
        #     # Si la géométrie n'est pas un groupe, essayer de l'ajouter au document
        #     App.Console.PrintWarning(f"La géométrie {contour_geometry.Label} n'est pas un groupe, impossible d'ajouter le contournage comme enfant\n")

        #     # Trouver le groupe parent de la géométrie du contour
        #     for parent in App.ActiveDocument.Objects:
        #         if hasattr(parent, "Group") and contour_geometry in parent.Group:
        #             parent.addObject(obj)
        #             App.Console.PrintMessage(f"Contournage ajouté comme enfant de {parent.Label}\n")
        #             break

        # Recomputer

        doc.recompute()

        # Ouvrir le panneau de tâches pour l'édition
        if obj.ViewObject:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)

        doc.commitTransaction()

        # Message de confirmation
        App.Console.PrintMessage(f"Contournage créé et lié à {contour_geometry.Label}.\n")


class CreateDrillGeometryCommand:
    """Commande pour créer une géométrie de perçage"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("Tree_Drilling.svg"),
                'MenuText': "Nouvelle géométrie de perçage",
                'ToolTip': "Créer une nouvelle géométrie de perçage"}

    def IsActive(self):
        """La commande est active si un projet CAM est sélectionné"""
        doc = App.ActiveDocument
        if doc is None:
            return False
        cam_project = BaptUtilities.getActiveCamProject()

        return cam_project is not None

    def Activated(self):
        """Créer une nouvelle géométrie de perçage"""

        doc = App.ActiveDocument
        # Obtenir le projet CAM sélectionné
        project = BaptUtilities.getActiveCamProject()

        doc.openTransaction('Create Drill Geometry')

        # Créer l'objet avec le type DocumentObjectGroupPython pour pouvoir contenir des enfants
        # obj = doc.addObject("App::DocumentObjectGroupPython", "DrillGeometry")
        obj = doc.addObject("Part::FeaturePython", "DrillGeometry")
        obj.addExtension("App::GroupExtensionPython")

        # Ajouter la fonctionnalité
        BaptDrillGeometry.DrillGeometry(obj)

        # Ajouter le ViewProvider
        if obj.ViewObject:
            BaptDrillGeometry.ViewProviderDrillGeometry(obj.ViewObject)

        # Ajouter au groupe Geometry
        geometry_group = project.Proxy.getGeometryGroup(project)
        geometry_group.addObject(obj)

        # Recomputer
        doc.recompute()

        # Ouvrir l'éditeur
        if obj.ViewObject:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)

        doc.commitTransaction()


class CreateSurfacageCommand:
    """Commande pour créer un nouveau surfacage"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("Surfacage.svg"),
                'MenuText': "Nouveau Surfacage",
                'ToolTip': "Créer un nouveau surfacage"}

    def IsActive(self):
        """La commande est active si un document est ouvert"""

        doc = App.ActiveDocument
        if doc is None:
            return False
        cam_project = BaptUtilities.getActiveCamProject()

        return cam_project is not None

    def Activated(self):
        """Créer un nouveau surfacage"""

        doc = App.ActiveDocument
        # Créer un nouveau document si aucun n'est ouvert
        if doc is None:
            doc = App.newDocument()

        project = BaptUtilities.getActiveCamProject()

        doc.openTransaction('Create Surfacage')

        # Créer l'objet surfacage
        obj = doc.addObject("Part::FeaturePython", "Surfacage")

        # Ajouter la fonctionnalité
        OpSurfacage.Surfacage(obj)
        model = project.Proxy.getModel(project)
        if model is not None:
            obj.Depth = model.Shape.BoundBox.ZMax

        # Ajouter le ViewProvider
        if obj.ViewObject:
            OpSurfacage.ViewProviderSurfacage(obj.ViewObject)

        # Ajouter au groupe Operations
        operations_group = project.Proxy.getOperationsGroup(project)
        operations_group.addObject(obj)

        obj.Stock = project.Proxy.getStock(project)

        # Recomputer
        doc.recompute()
        doc.commitTransaction()

        # Ouvrir l'éditeur
        if obj.ViewObject:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)


class CreateCamProjectCommand:
    """Commande pour créer un nouveau projet CAM"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("BaptWorkbench.svg"),
                'MenuText': "Nouveau Projet CAM",
                'ToolTip': "Créer un nouveau projet d'usinage"}

    def IsActive(self):
        """La commande est active si un document est ouvert"""
        return App.ActiveDocument is not None

    def Activated(self):
        """Créer un nouveau projet CAM"""

        doc = App.ActiveDocument
        # Créer un nouveau document si aucun n'est ouvert
        if doc is None:
            doc = App.newDocument()

        doc.openTransaction('Create Cam Project')

        # Créer l'objet projet CAM
        obj = doc.addObject("App::DocumentObjectGroupPython", "CamProject")

        # Ajouter la fonctionnalité
        project = BaptCamProject.CamProject(obj)

        # Ajouter le ViewProvider
        if obj.ViewObject and App.GuiUp:
            BaptCamProject.ViewProviderCamProject(obj.ViewObject)

            Gui.activeView().setActiveObject("camproject", obj)

        # Recomputer
        doc.recompute()
        doc.commitTransaction()

        # Ouvrir l'éditeur
        if obj.ViewObject and App.GuiUp:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)

        # Message de confirmation
        App.Console.PrintMessage("Projet CAM créé avec succès!\n")


class CreateContourGeometryCommand:
    """Commande pour créer une géométrie de contour"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("Tree_Contour.svg"),
                'MenuText': "Nouvelle géométrie de contour",
                'ToolTip': "Créer une nouvelle géométrie de contour pour l'usinage"}

    def IsActive(self):
        """La commande est active si un projet CAM est sélectionné"""
        doc = App.ActiveDocument
        if doc is None:
            return False
        cam_project = BaptUtilities.getActiveCamProject()

        return cam_project is not None

    def Activated(self):
        """Créer une nouvelle géométrie de contour"""

        doc = App.ActiveDocument
        doc.openTransaction('Create Contour Geometry')

        # Obtenir le projet CAM sélectionné ou actif
        project = BaptUtilities.getActiveCamProject()

        obj = doc.addObject("Part::FeaturePython", "ContourGeometry")
        # obj = App.ActiveDocument.addObject("App::DocumentObjectGroupPython", "ContourGeometry")
        obj.addExtension("App::GroupExtensionPython")

        # Ajouter la fonctionnalité
        BaptContourGeometry.ContourGeometry(obj)

        # Ajouter le ViewProvider
        if obj.ViewObject:
            BaptContourGeometry.ViewProviderContourGeometry(obj.ViewObject)

        # Ajouter au groupe Geometry
        geometry_group = project.Proxy.getGeometryGroup(project)
        geometry_group.addObject(obj)

        # Message de confirmation
        App.Console.PrintMessage("Géométrie de contour créée.\n")

        doc.commitTransaction()
        doc.recompute()

        # Ouvrir l'éditeur
        if obj.ViewObject:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)


class CreateContourEditableGeometryCommand:
    """Commande pour créer une géométrie de contour editable via Sketcher"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("Tree_Contour.svg"),
                'MenuText': "Nouvelle géométrie de contour editable",
                'ToolTip': "Créer une nouvelle géométrie de contour pour l'usinage"}

    def IsActive(self):
        """La commande est active si un projet CAM est sélectionné"""
        sel = Gui.Selection.getSelection()
        if not sel:
            return False
        return hasattr(sel[0], "Proxy") and sel[0].Proxy.Type == "CamProject"

    def Activated(self):
        """Créer une nouvelle géométrie de contour"""
        doc = App.ActiveDocument
        doc.openTransaction('Create Contour Geometry')

        # Obtenir le projet CAM sélectionné
        project = Gui.Selection.getSelection()[0]
        if project is None:
            App.Console.PrintError("Aucun projet CAM actif. Veuillez sélectionner ou activer un projet CAM.\n")
            doc.abortTransaction()
            return

        # Créer l'objet avec le bon type pour avoir une Shape
        obj = App.ActiveDocument.addObject("Part::FeaturePython", "ContourEditableGeometry")
        # obj = App.ActiveDocument.addObject("App::DocumentObjectGroupPython", "ContourGeometry")
        obj.addExtension("App::GroupExtensionPython")

        # Ajouter la fonctionnalité
        BaptContourEditableGeometry.ContourEditableGeometry(obj)

        # Ajouter le ViewProvider
        if obj.ViewObject:
            BaptContourEditableGeometry.ViewProviderContourEditableGeometry(obj.ViewObject)
            obj.ViewObject.addExtension("Gui::ViewProviderGroupExtensionPython")

        # Ajouter au groupe Geometry
        geometry_group = project.Proxy.getGeometryGroup(project)
        geometry_group.addObject(obj)

        # Message de confirmation
        App.Console.PrintMessage("Géométrie de contour editable créée.\n")

        App.ActiveDocument.recompute()

        # Ouvrir le panneau de tâches pour l'édition
        # Gui.Selection.clearSelection()
        # Gui.Selection.addSelection(obj)
        # Gui.ActiveDocument.setEdit(obj.Name)

        # Ouvrir l'éditeur
        # if obj.ViewObject:
        #     obj.ViewObject.Proxy.setEdit(obj.ViewObject)

        App.ActiveDocument.commitTransaction()


class CreateHotReloadCommand:
    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("hotreload.svg"),
                'MenuText': "Hot Reload",
                'ToolTip': "Recharge les modules Bapt"}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        """Recharge les modules Bapt"""
        try:
            from importlib import reload
            reload(BaptCamProject)
            import BaptContourGeometry
            reload(BaptContourGeometry)
            import BaptContournageTaskPanel
            reload(BaptContournageTaskPanel)
            import BaptContourTaskPanel
            reload(BaptContourTaskPanel)
            reload(DrillOp)
            reload(BaptTools)  # Ajouter le module BaptTools
            reload(OpContournage)
            reload(BaptPath)
            import BaptDrillTaskPanel
            reload(BaptDrillTaskPanel)
            import BaptPreferences
            reload(BaptPreferences)
            from Op import OpSurfacage
            reload(OpSurfacage)
            import BaptPostProcess
            reload(BaptPostProcess)
            from Probe import probeFace
            reload(probeFace)
            import BaptDrillOperationTaskPanel
            reload(BaptDrillOperationTaskPanel)
            import utils.BQuantitySpinBox as BQuantitySpinBox
            reload(BQuantitySpinBox)
            import Tool.ToolTaskPannel as ToolTaskPannel
            reload(ToolTaskPannel)
            import BaptHoleRecognition
            reload(BaptHoleRecognition)
            import BaptHoleRecognitionTaskPanel
            reload(BaptHoleRecognitionTaskPanel)
            import Op.BaptPocketOp as BaptPocketOp
            reload(BaptPocketOp)

            # dossier = BaptUtilities.get_module_path()

            # modules = [
            #     f[:-3] for f in os.listdir(dossier)
            #     if f.endswith(".py") and f != "__init__.py"
            # ]

            # print(modules)
            # for module_name in modules:
            #     reload(__import__(module_name))
            # Message de confirmation
            App.Console.PrintMessage("hot Reload avec Succes!\n")

        except Exception as e:
            App.Console.PrintError(f"Erreur lors du rechargement des modules: {str(e)}\n")
            pass

        # Recomputer
        App.ActiveDocument.recompute()


class ToolsManagerCommand:
    """Commande pour ouvrir le gestionnaire d'outils"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("BaptWorkbench.svg"),
                'MenuText': "Gestionnaire d'outils",
                'ToolTip': "Ouvrir le gestionnaire d'outils pour créer et éditer des outils"}

    def IsActive(self):
        """La commande est toujours active"""
        return True

    def Activated(self):
        """Ouvrir le gestionnaire d'outils"""
        panel = BaptTools.ToolsManagerPanel()
        Gui.Control.showDialog(panel)
        App.Console.PrintMessage("Gestionnaire d'outils ouvert.\n")


class CreateDrillOperationCommand:
    """Commande pour créer une opération d'usinage de perçage"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("Tree_Drilling.svg"),
                'MenuText': "Nouvelle opération de perçage",
                'ToolTip': "Créer une nouvelle opération d'usinage pour les géométries de perçage"}

    def IsActive(self):
        """La commande est active si une géométrie de perçage est sélectionnée"""
        sel = Gui.Selection.getSelection()
        if not sel:
            return False

        # Vérifier si l'objet sélectionné est une géométrie de perçage
        # en vérifiant directement le type de Proxy.Type
        return hasattr(sel[0], "Proxy") and hasattr(sel[0].Proxy, "Type") and sel[0].Proxy.Type == "DrillGeometry"

    def Activated(self):
        """Créer une nouvelle opération de perçage"""

        doc = App.ActiveDocument
        doc.openTransaction('Create Drill Operation')

        # Obtenir la géométrie de perçage sélectionnée
        drill_geometry = Gui.Selection.getSelection()[0]

        # Créer l'objet avec le bon type pour avoir une Shape
        obj = doc.addObject("Part::FeaturePython", "DrillOperation")

        # Ajouter la fonctionnalité
        operation = DrillOp.DrillOperation(obj)

        # Ajouter le ViewProvider
        if obj.ViewObject:
            DrillOp.ViewProviderDrillOperation(obj.ViewObject)
            obj.ViewObject.ShapeColor = (0.0, 0.0, 1.0)  # Bleu
            obj.ViewObject.Transparency = 70

        # Définir le nom de la géométrie de perçage associée (au lieu d'un lien direct)
        obj.DrillGeometryName = drill_geometry.Name

        pref = BaptPreferences.BaptPreferences()
        modeAjout = pref.getModeAjout()

        # 0 = ajouter à la géométrie comme enfant et au groupe opérations du projet CAM comme lien
        # 1 = ajouter à la géométrie comme enfant (pas conseillé)
        # 2 = ajouter au groupe opérations du projet CAM

        if modeAjout == 1 or modeAjout == 0:
            App.Console.PrintMessage(f'm10 \n')
            # Ajouter le contournage comme enfant de la géométrie du contour
            drill_geometry.addObject(obj)
            drill_geometry.Group.append(obj)

        if modeAjout == 2 or modeAjout == 0:
            camProject = BaptUtilities.find_cam_project(drill_geometry)
            if camProject:
                operations_group = camProject.Proxy.getOperationsGroup(camProject)
                if modeAjout == 2:
                    App.Console.PrintMessage(f'm2 \n')
                    operations_group.addObject(obj)
                    operations_group.Group.append(obj)
                elif modeAjout == 0:
                    App.Console.PrintMessage(f'm0 \n')
                    link = doc.addObject('App::Link', f'Link_{obj.Label}')
                    link.setLink(obj)
                    operations_group.addObject(link)
                    operations_group.Group.append(link)

        # Recomputer
        doc.recompute()

        # Ouvrir l'éditeur
        if obj.ViewObject:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)

        # Message de confirmation
        App.Console.PrintMessage("Opération de perçage créée et ajoutée comme enfant de la géométrie de perçage.\n")

        doc.commitTransaction()


class PostProcessGCodeCommand:
    """Commande pour générer un programme G-code à partir du projet CAM"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("PostProcess.svg"),
                'MenuText': "Post-process G-code",
                'ToolTip': "Générer un programme G-code à partir des opérations d'usinage"}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        BaptPostProcess.postprocess_gcode()


class ProbeFaceCommand:
    """Commande pour générer un Probing sur une face"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("ProbeSurface.svg"),
                'MenuText': "Probing sur une face",
                'ToolTip': "Générer un Probing sur une face"}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        # import probe.ProbeFace

        doc = App.ActiveDocument
        doc.openTransaction('Create Probe Face')

        obj = doc.addObject("Part::FeaturePython", "ProbeFace")

        probeFace.ProbeFace(obj)

        if obj.ViewObject:
            probeFace.ViewProviderProbeFace(obj.ViewObject)

        # Ouvrir l'éditeur
        if obj.ViewObject:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)

        doc.commitTransaction()


class TestPathCommand:
    """Commande pour tester le chemin d'accès des icônes"""

    def GetResources(self):
        return {'Pixmap': BaptUtilities.getIconPath("BaptWorkbench.svg"),
                'MenuText': "Test Path",
                'ToolTip': "Tester Path"}

    def IsActive(self):
        doc = App.ActiveDocument
        if doc is None:
            return False
        cam_project = BaptUtilities.getActiveCamProject()

        return cam_project is not None

    def Activated(self):
        doc = App.ActiveDocument
        project = BaptUtilities.getActiveCamProject()
        if project is None:
            App.Console.PrintError("Aucun projet CAM actif. Veuillez sélectionner ou activer un projet CAM.\n")
            return
        doc.openTransaction('Test Path')

        obj = doc.addObject("App::FeaturePython", "Test")

        PathOp.pathOp(obj)

        # obj.Gcode ="G0 X0 Y-20 Z50\nG0 Z2\nG1 Z0 F500\nG1 Y-10\nG3 X-10 Y0 I-10 J0\nG1 X-48\nG2 X-50 Y2 I0 J2\nG1 Y20\nG91\nG1 X5\nG0 Z50\n"

        obj.Gcode = "R1=10\nG0 X0 Y0 Z10\nG1 Z0 F500\nLABEL1:\nG91\nG1 Z-2\nG90\nG1 X16 Y0\nG3 X20 Y4 I0 J4 \nG1 X20 Y20\nG1 X0 Y20\nG1 X0 Y0\nREPEAT LABEL1 P=R1\nG0 Z10\n"
        obj.Gcode = "G0 X20 Y20 Z2\nG81 Z-20 R2\nG0 X30\nG80\nG0 X40\nG83 Z-30 R2 Q2"
        PathOp.pathOpViewProviderProxy(obj.ViewObject)

        # Ajouter au groupe Operations
        operations_group = project.Proxy.getOperationsGroup(project)
        operations_group.addObject(obj)

        # vp = obj.ViewObject.Proxy
        # vp.animator = BaptPath.GcodeAnimator(vp)
        # vp.animator.load_paths(include_rapid=True)
        # vp.animator.start(speed_mm_s=20)
        doc.commitTransaction()

        doc.recompute()


class HoleRecognitionCommand:
    """Commande pour la reconnaissance automatique de trous"""

    def GetResources(self):
        return {
            'Pixmap': BaptUtilities.getIconPath("Tree_HoleRecognition.svg"),
            'MenuText': "Reconnaissance de trous",
            'ToolTip': "Détecter automatiquement les trous cylindriques perpendiculaires au plan de travail"
        }

    def IsActive(self):
        """La commande est active si un document est ouvert"""
        doc = App.ActiveDocument
        if doc is None:
            return False
        cam_project = BaptUtilities.getActiveCamProject()

        return cam_project is not None

    def Activated(self):
        """Créer un nouvel objet de reconnaissance de trous"""
        import BaptHoleRecognition

        doc = App.ActiveDocument

        cam_project = BaptUtilities.getActiveCamProject()
        if cam_project is None:
            App.Console.PrintError("Aucun projet CAM actif. Veuillez sélectionner ou activer un projet CAM.\n")
            return

        doc.openTransaction('Create Hole Recognition')
        obj = BaptHoleRecognition.createHoleRecognition()
        cam_project.Proxy.getGeometryGroup(cam_project).addObject(obj)
        # Ouvrir le TaskPanel
        if obj.ViewObject:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)

        doc.commitTransaction()
        App.Console.PrintMessage("Objet de reconnaissance de trous créé.\n")


# Enregistrer les commandes
Gui.addCommand('Bapt_CreateOrigin', CreateOriginCommand())
Gui.addCommand('Bapt_CreateCamProject', CreateCamProjectCommand())
Gui.addCommand('Bapt_CreateDrillGeometry', CreateDrillGeometryCommand())
Gui.addCommand('Bapt_CreateContourGeometry', CreateContourGeometryCommand())
Gui.addCommand('Bapt_CreateContourEditableGeometry', CreateContourEditableGeometryCommand())
Gui.addCommand('Bapt_CreateMachiningCycle', CreateContourCommand())
Gui.addCommand('Bapt_CreatePocketOperation', CreatePocketOperationCommand())
Gui.addCommand('Bapt_CreateHotReload', CreateHotReloadCommand())
Gui.addCommand('Bapt_ToolsManager', ToolsManagerCommand())
Gui.addCommand('Bapt_CreateDrillOperation', CreateDrillOperationCommand())  # Ajouter la nouvelle commande
Gui.addCommand('ImportMpf', BaptMpfReader.ImportMpfCommand())  # Ajouter la commande d'importation MPF
Gui.addCommand('Bapt_PostProcessGCode', PostProcessGCodeCommand())
Gui.addCommand('Bapt_CreateSurfacage', CreateSurfacageCommand())
Gui.addCommand('Bapt_CreateProbeFace', ProbeFaceCommand())
Gui.addCommand('Bapt_TestPath', TestPathCommand())
Gui.addCommand('Bapt_HighlightCollisions', CreateHighlightCommand())
Gui.addCommand('Bapt_HoleRecognition', HoleRecognitionCommand())
Gui.addCommand('Bapt_CreateAdaptativeOperation', CreateAdaptativeOperationCommand())
