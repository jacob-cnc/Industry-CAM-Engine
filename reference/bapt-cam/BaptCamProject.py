"""Module pour gérer le projet CAM dans FreeCAD"""

import FreeCAD as App
import FreeCADGui as Gui
import Part
import BaptUtilities
from PySide import QtWidgets
import PySide.QtCore as QtCore
import PySide.QtGui as QtGui
import Draft
import CamProjectTaskPanel


class Stock:
    """Classe pour gérer le brut d'usinage"""

    def __init__(self, obj):
        """Initialise l'objet Stock

        Args:
            obj: L'objet FreeCAD

        """

        self.Type = "Stock"

        # App.Console.PrintMessage(f'Creating Stock object with parent: {parent.Label}\n')
        # App.Console.PrintMessage(f'Creating Stock object with parent: {parent.Name}\n')
        # App.Console.PrintMessage(f'Creating Stock object with Model: {parent.Model.Label}\n')
        # App.Console.PrintMessage(f'Creating Stock object with Model: {parent.Model.Name}\n')

        # App.Console.PrintMessage(f'Model bounding box: {parent.Model.Shape.BoundBox}\n')
        # App.Console.PrintMessage(f'Model bounding box: {parent.Model.Shape.BoundBox.XMin} {parent.Model.Shape.BoundBox.XMax} {parent.Model.Shape.BoundBox.XLength}\n')

        # Ajouter les propriétés si elles n'existent pas déjà
        # if not hasattr(obj, "Length"):
        #     obj.addProperty("App::PropertyLength", "Length", "Stock", "Longueur du brut")
        #     #obj.Length = parent.Model.Shape.BoundBox.XLength if parent and hasattr(parent, "Model") and hasattr(parent.Model, "Shape") else 200.0
        #     obj.Length = 100.0

        # if not hasattr(obj, "Width"):
        #     obj.addProperty("App::PropertyLength", "Width", "Stock", "Largeur du brut")
        #     obj.Width = 100.0

        # if not hasattr(obj, "Height"):
        #     obj.addProperty("App::PropertyLength", "Height", "Stock", "Hauteur du brut")
        #     obj.Height = 50.0

        if not hasattr(obj, "XNeg"):
            obj.addProperty("App::PropertyFloat", "XNeg",
                            "Stock", "Extension négative en X")
            obj.XNeg = 1.0

        if not hasattr(obj, "YNeg"):
            obj.addProperty("App::PropertyFloat", "YNeg",
                            "Stock", "Extension négative en Y")
            obj.YNeg = 1.0

        if not hasattr(obj, "ZNeg"):
            obj.addProperty("App::PropertyFloat", "ZNeg",
                            "Stock", "Extension négative en Z")
            obj.ZNeg = 1.0

        if not hasattr(obj, "XPos"):
            obj.addProperty("App::PropertyFloat", "XPos",
                            "Stock", "Extension positive en X")
            obj.XPos = 1.0

        if not hasattr(obj, "YPos"):
            obj.addProperty("App::PropertyFloat", "YPos",
                            "Stock", "Extension positive en Y")
            obj.YPos = 1.0

        if not hasattr(obj, "ZPos"):
            obj.addProperty("App::PropertyFloat", "ZPos",
                            "Stock", "Extension positive en Z")
            obj.ZPos = 1.0

        # if not hasattr(obj, "Origin"):
        #     obj.addProperty("App::PropertyVector", "Origin", "Stock", "Origine du brut")
        #     obj.Origin = App.Vector(0, 0, 0)

        if not hasattr(obj, "WorkPlane"):
            obj.addProperty("App::PropertyEnumeration",
                            "WorkPlane", "Stock", "Plan de travail")
            obj.WorkPlane = ["XY", "XZ", "YZ"]
            obj.WorkPlane = "XY"

        if not hasattr(obj, "Material"):
            obj.addProperty("App::PropertyMaterial", "Material",
                            "Stock", "Matériau du brut")
            obj.Material = App.Material()

        if not hasattr(obj, "testShape"):
            obj.addProperty("Part::PropertyPartShape", "testShape",
                            "Subsection", "Description for tooltip")
            obj.testShape = Part.Shape()

        obj.Shape = obj.testShape
        # Créer une forme initiale
        # self.updateShape(obj)

        obj.Proxy = self

    def getParent(self, obj):
        """Obtenir l'objet parent du projet"""
        for o in obj.InList:
            if hasattr(o, "Group"):
                for child in o.Group:
                    # App.Console.PrintMessage(f'Checking child: {child.Name}  {obj.Name}\n')
                    if child.Name == obj.Name:
                        return o
        App.Console.PrintMessage(
            "Parent CamProject not found for Stock object.\n")
        return None

    def onDocumentRestored(self, obj):
        """Appelé lors de la restauration du document"""
        self.__init__(obj)

    def execute(self, obj):
        """Mettre à jour la forme du brut"""
        if App.ActiveDocument.Restoring:
            return

        self.updateShape(obj)

    def updateShape(self, obj):
        """Mettre à jour la forme du brut en fonction des propriétés"""
        if not hasattr(obj, "WorkPlane"):
            return

        # if obj.Length <= 0 or obj.Width <= 0 or obj.Height <= 0:
        #     App.Console.PrintMessage(f'updateShape {obj.Placement.Base}\n')
        #     return
        # App.Console.PrintMessage(f'avant placement {obj.Placement}\n')
        placement = obj.Placement
        # App.Console.PrintMessage(f'APRES placement \n')
        obj.Shape = Part.Shape()
        modelBbox = None
        model = self.getParent(obj).Model
        if model is not None:
            modelBbox = model.Shape.BoundBox
        # if modelBbox is None:

        #     App.Console.PrintMessage("No object selected for Model.\n")
        #     # delete property xneg...
        #     for prop in ["XNeg", "YNeg", "ZNeg", "XPos", "YPos", "ZPos"]:
        #         if hasattr(obj, prop):
        #             obj.removeProperty(prop)

        #     for prop in ["Length", "Width", "Height"]:
        #         if not hasattr(obj, "Length"):
        #             obj.addProperty("App::PropertyLength", "Length", "Stock", "Longueur du brut")
        #             #obj.Length = parent.Model.Shape.BoundBox.XLength if parent and hasattr(parent, "Model") and hasattr(parent.Model, "Shape") else 200.0
        #             obj.Length = 100.0

        #         if not hasattr(obj, "Width"):
        #             obj.addProperty("App::PropertyLength", "Width", "Stock", "Largeur du brut")
        #             obj.Width = 100.0

        #         if not hasattr(obj, "Height"):
        #             obj.addProperty("App::PropertyLength", "Height", "Stock", "Hauteur du brut")
        #             obj.Height = 50.0

        if hasattr(obj, "Length") and hasattr(obj, "Width") and hasattr(obj, "Height"):
            # Créer la boîte en fonction du plan de travail
            # App.Console.PrintMessage(f'plac 1 {obj.Placement}\n')
            if obj.WorkPlane == "XY":
                box = Part.makeBox(obj.Length, obj.Width, obj.Height)
            elif obj.WorkPlane == "XZ":
                box = Part.makeBox(obj.Length, obj.Height, obj.Width)
            else:  # YZ
                box = Part.makeBox(obj.Height, obj.Length, obj.Width)

            # Assigner la forme
            obj.Shape = box
            # App.Console.PrintMessage(f'plac 2 {obj.Placement}\n')
            obj.Placement = placement
        elif hasattr(obj, "XNeg") and hasattr(obj, "YNeg") and hasattr(obj, "ZNeg") and hasattr(obj, "XPos") and hasattr(obj, "YPos") and hasattr(obj, "ZPos"):
            # Créer la boîte centrée sur le modèle avec les extensions
            xMin = modelBbox.XMin - obj.XNeg
            yMin = modelBbox.YMin - obj.YNeg
            zMin = modelBbox.ZMin - obj.ZNeg
            length = modelBbox.XLength + obj.XNeg + obj.XPos
            width = modelBbox.YLength + obj.YNeg + obj.YPos
            height = modelBbox.ZLength + obj.ZNeg + obj.ZPos

            box = Part.makeBox(length, width, height,
                               App.Vector(xMin, yMin, zMin))
            obj.Shape = box
            # obj.Placement =  App.Placement(App.Vector(modelBbox.XMin, modelBbox.YMin, modelBbox.ZMin), App.Rotation(App.Vector(0,0,1),0))
        obj.testShape = obj.Shape

    def onChanged(self, obj, prop):
        """Gérer les changements de propriétés"""
        if App.ActiveDocument.Restoring:
            return
        # App.Console.PrintMessage(f'Stock property changed: {prop}\n')
        if prop in ["Length", "Width", "Height", "WorkPlane"]:
            self.updateShape(obj)
        elif prop in ["XNeg", "YNeg", "ZNeg", "XPos", "YPos", "ZPos"]:
            self.updateShape(obj)

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None


class ViewProviderStock:
    """Classe pour gérer l'affichage du brut"""

    def __init__(self, vobj):
        """Initialise le ViewProvider"""
        vobj.Proxy = self
        self.Object = vobj.Object

        # Définir la couleur et la transparence du stock
        vobj.ShapeColor = (0.8, 0.8, 0.8)  # Gris clair
        vobj.Transparency = 80  # 80% de transparence

    def getIcon(self):
        """Retourne l'icône"""
        return BaptUtilities.getIconPath("Tree_Stock.svg")

    def attach(self, vobj):
        """Appelé lors de l'attachement du ViewProvider"""
        self.Object = vobj.Object

    def updateData(self, obj, prop):
        """Appelé lorsqu'une propriété de l'objet est modifiée"""
        pass

    def onChanged(self, vobj, prop):
        """Appelé lorsqu'une propriété du ViewProvider est modifiée"""
        pass

    def doubleClicked(self, vobj):
        """Gérer le double-clic"""
        return False

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None


class ObjSelector(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # self.objectsToShow = {}
        self.setWindowTitle("Sélection d'objet")
        self.resize(350, 250)
        layout = QtWidgets.QVBoxLayout(self)

        # Liste des objets du document actif
        self.listWidget = QtWidgets.QListWidget()
        self.objects = []
        doc = App.ActiveDocument
        if doc:
            for obj in doc.Objects:
                if hasattr(obj, "Shape") and obj.isDerivedFrom("Part::Feature"):
                    self.objects.append(obj)
                    # self.listWidget.addItem(f"{obj.Label} ({obj.Name})")
                    item = QtWidgets.QListWidgetItem(
                        f"{obj.Label} ({obj.Name})")
                    # Ajouter l'icône si disponible
                    if hasattr(obj, "ViewObject") and obj.ViewObject:
                        item.setIcon(QtGui.QIcon(obj.ViewObject.Icon))
                    self.listWidget.addItem(item)
        layout.addWidget(self.listWidget)

        # Bouton OK
        self.okBtn = QtWidgets.QPushButton("OK")
        self.okBtn.clicked.connect(self.accept)
        layout.addWidget(self.okBtn)

        # Label pour afficher la bounding box
        self.resultLabel = QtWidgets.QLabel("")
        layout.addWidget(self.resultLabel)

        # Action lors de la sélection
        self.listWidget.currentRowChanged.connect(self.showObj)
        self.listWidget.doubleClicked.connect(self.accept)

    def showObj(self, row):
        if row < 0 or row >= len(self.objects):
            self.resultLabel.setText("")
            return
        # for obj, visibility in self.objectsToShow.items():
        #     obj.ViewObject.BoundingBox = visibility
        # self.objectsToShow={}
        obj = self.objects[row]
        # self.objectsToShow[obj] = obj.ViewObject.BoundingBox
        # obj.ViewObject.BoundingBox = True
        self.resultLabel.setText(obj.Label)

    def getSelectedObject(self):
        row = self.listWidget.currentRow()
        if row < 0 or row >= len(self.objects):
            return None
        return self.objects[row]


class BoundingBoxSelector(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sélection d'objet")
        self.resize(350, 200)
        layout = QtWidgets.QVBoxLayout(self)

        # Liste des objets du document actif
        self.listWidget = QtWidgets.QListWidget()
        self.objects = []
        doc = App.ActiveDocument
        if doc:
            for obj in doc.Objects:
                if hasattr(obj, "Shape"):
                    self.objects.append(obj)
                    self.listWidget.addItem(f"{obj.Label} ({obj.Name})")
        layout.addWidget(self.listWidget)

        # Bouton OK
        self.okBtn = QtWidgets.QPushButton("OK")
        self.okBtn.clicked.connect(self.accept)
        layout.addWidget(self.okBtn)

        # Label pour afficher la bounding box
        self.resultLabel = QtWidgets.QLabel("")
        layout.addWidget(self.resultLabel)

        # Action lors de la sélection
        self.listWidget.currentRowChanged.connect(self.showBoundingBox)

    def showBoundingBox(self, row):
        if row < 0 or row >= len(self.objects):
            self.resultLabel.setText("")
            return
        obj = self.objects[row]
        bbox = obj.Shape.BoundBox
        dims = f"X: {bbox.XLength:.2f} mm\nY: {bbox.YLength:.2f} mm\nZ: {bbox.ZLength:.2f} mm"
        self.resultLabel.setText(dims)

    def getSelectedBoundingBox(self):
        row = self.listWidget.currentRow()
        if row < 0 or row >= len(self.objects):
            return None
        obj = self.objects[row]
        return obj.Shape.BoundBox


class CamProject:
    def __init__(self, obj):
        """Ajoute les propriétés"""
        self.Type = "CamProject"
        self.Object = obj
        # Transformer l'objet en groupe
        # obj.addExtension("App::GroupExtensionPython")

        # Propriétés du projet
        # if not hasattr(obj, "Origin"):
        #     obj.addProperty("App::PropertyVector", "Origin", "Project", "Origine du projet")
        #     obj.Origin = App.Vector(0, 0, 0)

        if not hasattr(obj, "WorkPlane"):
            obj.addProperty("App::PropertyEnumeration",
                            "WorkPlane", "Project", "Plan de travail")
            obj.WorkPlane = ["XY", "XZ", "YZ"]
            obj.WorkPlane = "XY"

        if not hasattr(obj, "Model"):
            obj.addProperty("App::PropertyLink", "Model", "Base",
                            "The base objects for all operations")

        if not hasattr(obj, "PostProcessor"):
            obj.addProperty("App::PropertyStringList", "PostProcessor",
                            "Project", "Post Processor to use for G-Code generation")
            obj.PostProcessor = ["Siemens828"]  # Valeur par défaut

        if not hasattr(obj, "toolChangePos"):
            obj.addProperty("App::PropertyVector", "toolChangePos", "Project", "Origine de la pièce")
            obj.toolChangePos = App.Vector(0, 0, 250)

        # Créer le groupe Operations
        self.getOperationsGroup(obj)

        # Créer le groupe Geometry
        self.getGeometryGroup(obj)

        self.getModel(obj)

        obj.recompute()

        # Créer ou obtenir l'objet Stock
        self.getStock(obj)

        # Obtenir l'objet Origin
        self.origin = self.getOrigin()

        # Créer ou obtenir l'objet Tools
        self.getToolsGroup()

        # Assigner le proxy à la fin pour éviter les problèmes de récursion
        obj.Proxy = self

    def onDocumentRestored(self, obj):
        """Appelé lors de la restauration du document"""
        self.__init__(obj)

    def getModel(self, obj):
        """Obtenir ou créer l'objet Model pour le projet"""
        if hasattr(obj, "Model") and obj.Model:
            return obj.Model

        App.Console.PrintMessage(
            "Model not found in project. Creating new model.\n")

        dlg = ObjSelector()
        if dlg.exec_():
            selected_obj = dlg.getSelectedObject()
            if selected_obj:
                selected_obj.ViewObject.Visibility = False

                clone = Draft.clone(selected_obj)
                clone.Label = f"Clone_{selected_obj.Label}"
                clone.ViewObject.Visibility = True
                clone.ViewObject.Transparency = 50
                obj.Model = clone
                obj.addObject(clone)
                clone.recompute()
                bbox = selected_obj.Shape.BoundBox
                # App.Console.PrintMessage(f"Dimensions: X={bbox.XLength} Y={bbox.YLength} Z={bbox.ZLength}\n")
                # print(f"X Range: {bbox.XMin} to {bbox.XMax}")
                # print(f"Y Range: {bbox.YMin} to {bbox.YMax}")
                # print(f"Z Range: {bbox.ZMin} to {bbox.ZMax}")

    def getOperationsGroup(self, obj):
        """Obtenir ou créer le groupe Operations"""
        operations_group = None

        # Vérifier si le groupe existe déjà
        for child in obj.Group:
            if child.Name.startswith("Operations"):
                operations_group = child
                break

        # Créer le groupe s'il n'existe pas
        if not operations_group:
            operations_group = App.ActiveDocument.addObject(
                "App::DocumentObjectGroupPython", "Operations")
            if hasattr(operations_group, "ViewObject"):
                operationGroupViewProviderProxy(operations_group.ViewObject)
            operations_group.Label = "Operations"
            obj.Group.append(operations_group)
            obj.addObject(operations_group)

        return operations_group

    def getGeometryGroup(self, obj):
        """Obtenir ou créer le groupe Geometry"""
        geometry_group = None

        # Vérifier si le groupe existe déjà
        for child in obj.Group:
            if child.Name.startswith("Geometry"):
                geometry_group = child
                break

        # Créer le groupe s'il n'existe pas
        if not geometry_group:
            geometry_group = App.ActiveDocument.addObject(
                "App::DocumentObjectGroupPython", "Geometry")
            geometry_group.Label = "Geometry"
            obj.addObject(geometry_group)

        return geometry_group

    def getOrigin(self):
        """Obtenir ou créer l'objet Origin pour le projet"""
        # if hasattr(obj, "Origin") and obj.Origin:
        #     return obj.Origin
        # App.Console.PrintMessage("Origin not found in project. Creating new origin.\n")
        # Chercher un objet Origin dans le groupe du projet
        if hasattr(self.Object, "Group"):
            for child in self.Object.Group:
                if hasattr(child, "Proxy") and getattr(child.Proxy, "Type", "") == "Origin":
                    # obj.Origin = child
                    return child
        # Sinon, créer un nouvel objet Origin

        import BaptOrigin

        origin = BaptOrigin.createOrigin()
        origin.Label = "WCS_G54"
        self.Object.addObject(origin)
        # obj.Origin = origin
        App.Console.PrintMessage("Origin created: " + origin.Name + "\n")
        return origin

    def getStock(self, obj):
        """Obtenir ou créer l'objet Stock"""
        stock = None

        # Vérifier si le stock existe déjà
        if hasattr(obj, "Group"):
            for child in obj.Group:
                # App.Console.PrintMessage(f'Checking child: {child.Name}\n')
                if child.Name.startswith("Stock"):
                    # App.Console.PrintMessage(f'Stock found: {child.Name}\n')
                    stock = child
                    break

        # Créer le stock s'il n'existe pas
        if not stock:
            stock = App.ActiveDocument.addObject(
                "Part::FeaturePython", "Stock")
            Stock(stock)

            # Ajouter le stock au groupe
            obj.addObject(stock)
            obj.Group.append(stock)

            # Ajouter le ViewProvider
            if stock.ViewObject:
                ViewProviderStock(stock.ViewObject)

                # self.updateStockShape(obj)

            # dlg = BoundingBoxSelector()
            # if dlg.exec_():
            #     bbox = dlg.getSelectedBoundingBox()
            #     if bbox:
            #         # App.Console.PrintMessage(f"Dimensions: X={bbox.XLength} Y={bbox.YLength} Z={bbox.ZLength}\n")
            #         # print(f"X Range: {bbox.XMin} to {bbox.XMax}")
            #         # print(f"Y Range: {bbox.YMin} to {bbox.YMax}")
            #         # print(f"Z Range: {bbox.ZMin} to {bbox.ZMax}")
            #         stock.Length = bbox.XLength
            #         stock.Width = bbox.YLength
            #         stock.Height = bbox.ZLength
            #         stock.Placement = App.Placement(App.Vector(bbox.XMin, bbox.YMin, bbox.ZMin), App.Rotation(App.Vector(0,0,1),0))
            #         App.Console.PrintMessage(f"Stock created: {stock.Name}\n")
            #         App.Console.PrintMessage(f"Stock origin: {stock.Placement.Base}\n")
            #         #stock.Origin = App.Vector(bbox.XMin, bbox.YMin, bbox.ZMin)
            #     else:
            #         App.Console.PrintMessage("Aucun objet sélectionné.\n")
            #         # Initialiser les propriétés du stock
            #         stock.Length = 100.0
            #         stock.Width = 100.0
            #         stock.Height = 50.0
            #         stock.Placement.Base = App.Vector(0, 0, 0)

            stock.WorkPlane = obj.WorkPlane

        return stock

    # def updateStockShape(self, obj):
    #     """Mettre à jour la forme du stock en fonction de l'objet modèle"""
    #     stock = self.getStock(obj)
    #     model = obj.Model
    #     if stock and model and hasattr(model, "Shape"):
    #         bbox = model.Shape.BoundBox
    #         stock.Length = bbox.XLength
    #         stock.Width = bbox.YLength
    #         stock.Height = bbox.ZLength
    #         stock.Placement = App.Placement(App.Vector(bbox.XMin, bbox.YMin, bbox.ZMin), App.Rotation(App.Vector(0,0,1),0))

    def getToolsGroup(self):
        """Obtenir ou créer le groupe Tools"""
        tools_group = None

        # Vérifier si le groupe existe déjà
        for child in self.Object.Group:
            if child.Name.startswith("Tools"):
                tools_group = child
                break

        # Créer le groupe s'il n'existe pas
        if not tools_group:
            tools_group = App.ActiveDocument.addObject(
                "App::DocumentObjectGroupPython", "Tools")
            tools_group.Label = "Tools"
            self.Object.addObject(tools_group)

        return tools_group

    def execute(self, obj):
        """Mettre à jour le projet"""
        # Rien à faire ici, le stock gère sa propre mise à jour
        pass

    def onChanged(self, obj, prop):
        """Gérer les changements de propriétés"""
        if hasattr(obj, "WorkPlane") and prop == "WorkPlane":
            # Synchroniser le plan de travail avec le stock
            stock = self.getStock(obj)
            if stock and hasattr(stock, "WorkPlane"):
                stock.WorkPlane = obj.WorkPlane

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None

    def onDelete(self, obj, subelements):
        """Appelé lors de la suppression de l'objet"""
        App.Console.PrintMessage(f'onDelete obj {subelements}\n')
        return True


class ViewProviderCamProject:
    def __init__(self, vobj):
        """Initialise le ViewProvider"""
        vobj.Proxy = self
        self.Object = vobj.Object
        self.deleteOnReject = True

    def getIcon(self):
        """Retourne l'icône"""
        return BaptUtilities.getIconPath("BaptWorkbench.svg")

    def attach(self, vobj):
        """Appelé lors de l'attachement du ViewProvider"""
        self.Object = vobj.Object

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        action_edit = QtGui.QAction(Gui.getIcon(
            "Std_TransformManip.svg"), "Edit", menu)
        QtCore.QObject.connect(action_edit, QtCore.SIGNAL(
            "triggered()"), lambda: self.setEdit(vobj))
        # action = menu.addAction("Edit")
        menu.addAction(action_edit)

        # action.triggered.connect(lambda: self.setEdit(vobj))

        action2 = menu.addAction("Active Object")
        action2.triggered.connect(lambda: self.activateObject(vobj))
        return True

    def activateObject(self, vobj):
        """Activer l'objet dans le document"""
        # App.ActiveDocument.ActiveObject = vobj.Object
        Gui.activeView().setActiveObject("camproject", vobj.Object)
        return True

    def updateData(self, obj, prop):
        """Appelé quand une propriété de l'objet est modifiée"""
        pass

    def onChanged(self, vobj, prop):
        """Appelé quand une propriété du ViewProvider est modifiée"""
        pass

    def doubleClicked(self, vobj):
        """Gérer le double-clic"""
        self.setEdit(vobj)
        return True

    def updateData(self, obj, prop):
        """Appelé quand une propriété de l'objet est modifiée"""
        pass

    def onChanged(self, vobj, prop):
        """Appelé quand une propriété du ViewProvider est modifiée"""
        pass

    def doubleClicked(self, vobj):
        """Gérer le double-clic"""
        self.setEdit(vobj)
        return True

    def deleteObjectsOnReject(self):
        """Indique si l'objet doit être supprimé si l'édition est annulée"""
        return hasattr(self, "deleteOnReject") and self.deleteOnReject

    def onDelete(self, vobj, subelements):
        """Appelé lors de la suppression de l'objet"""
        App.Console.PrintMessage(f'onDelete vobj {subelements}\n')

        def deleteSubelements(subelements):
            for sub in subelements:
                if hasattr(sub, "Group"):
                    deleteSubelements(sub.Group)
                App.Console.PrintMessage(f'Deleting subelement: {sub.Name}\n')
                App.ActiveDocument.removeObject(sub.Name)
        deleteSubelements(vobj.Object.Group)
        return True

    def setEdit(self, vobj, mode=0):
        """Appelé lorsque l'objet est édité"""

        taskd = CamProjectTaskPanel.CamProjectTaskPanel(
            vobj.Object, self.deleteObjectsOnReject())
        Gui.Control.showDialog(taskd)
        self.deleteOnReject = False
        return True

    def unsetEdit(self, vobj, mode=0):
        """Appelé lorsque l'édition est terminée"""
        Gui.Control.closeDialog()
        return True

    def doubleClicked(self, vobj):
        """Gérer le double-clic"""
        self.setEdit(vobj)
        return True

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None


class operationGroupViewProviderProxy():
    def __init__(self, vobj):
        App.Console.PrintMessage("Initializing operation group view provider proxy for: {}\n".format(__class__.__name__))
        vobj.Proxy = self
        self.Object = vobj.Object

    def attach(self, vobj):
        """Appelé lors de l'attachement du ViewProvider"""
        self.Object = vobj.Object

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        simulateAllOp = QtGui.QAction(Gui.getIcon(
            "Std_TransformManip.svg"), "Simul", menu)
        QtCore.QObject.connect(simulateAllOp, QtCore.SIGNAL(
            "triggered()"), lambda: self.simulateAllOperations(vobj))
        # action = menu.addAction("Edit")
        menu.addAction(simulateAllOp)

        # action.triggered.connect(lambda: self.setEdit(vobj))

        return True

    def simulateAllOperations(self, vobj):
        """Simuler toutes les opérations dans le groupe"""
        from BaptPath import GcodeAnimationControl, GcodeAnimator

        App.Console.PrintMessage("Simulating all operations in group: {}\n".format(vobj.Object.Name))

        # Collecter toutes les opérations actives
        operations = []
        for child in vobj.Object.Group:
            # Gérer les liens
            actual_obj = child.LinkedObject if hasattr(child, 'LinkedObject') else child

            # Vérifier que l'objet a un ViewObject et est actif
            if hasattr(actual_obj, "ViewObject") and hasattr(actual_obj, "Active"):
                if actual_obj.Active:
                    operations.append(actual_obj)
                    App.Console.PrintMessage(f"  Adding operation: {actual_obj.Label}\n")

        if not operations:
            App.Console.PrintWarning("Aucune opération active trouvée dans le groupe\n")
            return False

        # Afficher le panneau de contrôle avec toutes les opérations
        panel = GcodeAnimationControl(operations=operations)
        Gui.Control.showDialog(panel)

        return True
