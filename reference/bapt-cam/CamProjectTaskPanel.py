import BaptUtilities
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
from utils import PointSelectionObserver
from utils.BQuantitySpinBox import BQuantitySpinBox


class BoundBoxSphere:
    """Classe pour gérer une sphère cliquable sur la bounding box"""

    def __init__(self, position, label, parent_panel):
        self.position = position
        self.label = label
        self.parent_panel = parent_panel
        self.sphere_object = None
        self.callback_node = None

    def create(self):
        """Créer la sphère dans la vue 3D"""
        # Créer un objet Part::Sphere temporaire
        doc = App.ActiveDocument
        sphere = doc.addObject("Part::Sphere", f"BBoxPoint_{self.label}")
        sphere.Radius = 2  # Rayon de 2mm
        sphere.Placement = App.Placement(self.position, App.Rotation())

        # Rendre la sphère semi-transparente et colorée
        if hasattr(sphere, "ViewObject"):
            sphere.ViewObject.Transparency = 30
            sphere.ViewObject.ShapeColor = (1.0, 0.5, 0.0)  # Orange

        doc.recompute()
        self.sphere_object = sphere

        # Ajouter un callback pour la sélection
        self._add_selection_callback()

        return sphere

    def _add_selection_callback(self):
        """Ajouter un callback pour détecter les clics sur la sphère"""
        # Utiliser l'observer de sélection de FreeCAD
        pass  # La sélection sera gérée par le parent

    def remove(self):
        """Supprimer la sphère"""
        if self.sphere_object:
            doc = self.sphere_object.Document
            doc.removeObject(self.sphere_object.Name)
            self.sphere_object = None


class BoundBoxSphereManager:
    """Gestionnaire pour les sphères de la bounding box"""

    def __init__(self, parent_panel):
        self.parent_panel = parent_panel
        self.spheres = []
        self.selection_observer = None

    def create_spheres_for_model(self, model):
        """Créer des sphères aux coins et milieux de la bounding box du model"""
        if not model or not hasattr(model, "Shape"):
            App.Console.PrintWarning("Aucun modèle valide sélectionné\n")
            return

        # Nettoyer les sphères existantes
        self.clear_spheres()

        bbox = model.Shape.BoundBox

        # Les 8 coins de la bounding box
        corners = [
            (App.Vector(bbox.XMin, bbox.YMin, bbox.ZMin), "Coin_XMin_YMin_ZMin"),
            (App.Vector(bbox.XMax, bbox.YMin, bbox.ZMin), "Coin_XMax_YMin_ZMin"),
            (App.Vector(bbox.XMin, bbox.YMax, bbox.ZMin), "Coin_XMin_YMax_ZMin"),
            (App.Vector(bbox.XMax, bbox.YMax, bbox.ZMin), "Coin_XMax_YMax_ZMin"),
            (App.Vector(bbox.XMin, bbox.YMin, bbox.ZMax), "Coin_XMin_YMin_ZMax"),
            (App.Vector(bbox.XMax, bbox.YMin, bbox.ZMax), "Coin_XMax_YMin_ZMax"),
            (App.Vector(bbox.XMin, bbox.YMax, bbox.ZMax), "Coin_XMin_YMax_ZMax"),
            (App.Vector(bbox.XMax, bbox.YMax, bbox.ZMax), "Coin_XMax_YMax_ZMax"),
        ]

        # Les 12 milieux des arêtes
        middles = [
            # Arêtes parallèles à X
            (App.Vector(bbox.Center.x, bbox.YMin, bbox.ZMin), "Milieu_X_YMin_ZMin"),
            (App.Vector(bbox.Center.x, bbox.YMax, bbox.ZMin), "Milieu_X_YMax_ZMin"),
            (App.Vector(bbox.Center.x, bbox.YMin, bbox.ZMax), "Milieu_X_YMin_ZMax"),
            (App.Vector(bbox.Center.x, bbox.YMax, bbox.ZMax), "Milieu_X_YMax_ZMax"),
            # Arêtes parallèles à Y
            (App.Vector(bbox.XMin, bbox.Center.y, bbox.ZMin), "Milieu_Y_XMin_ZMin"),
            (App.Vector(bbox.XMax, bbox.Center.y, bbox.ZMin), "Milieu_Y_XMax_ZMin"),
            (App.Vector(bbox.XMin, bbox.Center.y, bbox.ZMax), "Milieu_Y_XMin_ZMax"),
            (App.Vector(bbox.XMax, bbox.Center.y, bbox.ZMax), "Milieu_Y_XMax_ZMax"),
            # Arêtes parallèles à Z
            (App.Vector(bbox.XMin, bbox.YMin, bbox.Center.z), "Milieu_Z_XMin_YMin"),
            (App.Vector(bbox.XMax, bbox.YMin, bbox.Center.z), "Milieu_Z_XMax_YMin"),
            (App.Vector(bbox.XMin, bbox.YMax, bbox.Center.z), "Milieu_Z_XMin_YMax"),
            (App.Vector(bbox.XMax, bbox.YMax, bbox.Center.z), "Milieu_Z_XMax_YMax"),
        ]

        # Les 6 centres des faces
        center = [
            (App.Vector(bbox.Center.x, bbox.Center.y, bbox.ZMin), "bottomFace"),
            (App.Vector(bbox.Center.x, bbox.Center.y, bbox.ZMax), "topFace"),
            (App.Vector(bbox.XMin, bbox.Center.y, bbox.Center.z), "leftFace"),
            (App.Vector(bbox.XMax, bbox.Center.y, bbox.Center.z), "rightFace"),
            (App.Vector(bbox.Center.x, bbox.YMin, bbox.Center.z), "frontFace"),
            (App.Vector(bbox.Center.x, bbox.YMax, bbox.Center.z), "backFace"),
        ]

        # Créer toutes les sphères
        all_points = corners + middles + center
        for position, label in all_points:
            sphere = BoundBoxSphere(position, label, self.parent_panel)
            sphere.create()
            self.spheres.append(sphere)

        App.Console.PrintMessage(f"{len(self.spheres)} sphères créées pour le positionnement\n")

        # Activer l'observer de sélection
        self._enable_selection_observer()

    def _enable_selection_observer(self):
        """Activer l'observer pour détecter les clics sur les sphères"""
        if self.selection_observer:
            self._disable_selection_observer()

        self.selection_observer = BBoxSelectionObserver(self)
        Gui.Selection.addObserver(self.selection_observer)

    def _disable_selection_observer(self):
        """Désactiver l'observer"""
        if self.selection_observer:
            Gui.Selection.removeObserver(self.selection_observer)
            self.selection_observer = None

    def on_sphere_clicked(self, sphere_name):
        """Appelé quand une sphère est cliquée"""
        # Trouver la sphère correspondante
        sphere_to_remove = None
        for sphere in self.spheres:
            if sphere.sphere_object and sphere.sphere_object.Name == sphere_name:
                sphere_to_remove = sphere
                break

        if sphere_to_remove:
            # Afficher les coordonnées dans la console
            pos = sphere_to_remove.position
            App.Console.PrintMessage(f"Sphère cliquée: {sphere_to_remove.label}\n")
            App.Console.PrintMessage(f"Coordonnées: X={pos.x:.3f}, Y={pos.y:.3f}, Z={pos.z:.3f}\n")

            self.parent_panel.obj.Model.Placement.translate(App.Vector(pos.x * -1, pos.y * -1, pos.z * -1))
            # Désélectionner d'abord la sphère pour éviter les problèmes
            Gui.Selection.clearSelection()

            # Différer la suppression de toutes les sphères
            QtCore.QTimer.singleShot(100, lambda: self._remove_all_spheres_deferred())

    def _remove_all_spheres_deferred(self):
        """Supprimer toutes les sphères de manière différée pour éviter les violations d'accès"""
        count = len(self.spheres)
        self.clear_spheres()
        App.Console.PrintMessage(f"Toutes les {count} sphères ont été supprimées\n")

    def clear_spheres(self):
        """Supprimer toutes les sphères"""
        self._disable_selection_observer()
        for sphere in self.spheres:
            sphere.remove()
        self.spheres = []
        App.Console.PrintMessage("Toutes les sphères ont été supprimées\n")


class BBoxSelectionObserver:
    """Observer pour détecter la sélection des sphères de bounding box"""

    def __init__(self, manager):
        self.manager = manager

    def addSelection(self, document, object_name, element, position):
        """Appelé quand un objet est sélectionné"""
        # Vérifier si c'est une de nos sphères
        if object_name.startswith("BBoxPoint_"):
            self.manager.on_sphere_clicked(object_name)


class CamProjectTaskPanel:
    def __init__(self, obj, deleteOnReject):
        # Garder une référence à l'objet
        self.obj = obj
        self.deleteOnReject = deleteOnReject
        # Obtenir l'objet Stock
        self.stock = self.getStockObject(obj)

        self.ui1 = Gui.PySideUic.loadUi(BaptUtilities.getPanel("CAMProject.ui"))
        self.ui1.setWindowTitle("Edit CAM Project")
        # Créer l'interface utilisateur
        ui2 = PostProcessorTaskPanel(obj)

        self.form = [self.ui1, ui2.getForm()]

        self.ui1.workPlane.addItems(["XY", "XZ", "YZ"])

        self.ui1.model.addItems([obj.Name for obj in App.ActiveDocument.Objects if obj.isDerivedFrom("Part::Feature")])

        self.ui1.stockMode.addItems(["box", "Extend Bounding Box"])

        self.stockLength = BQuantitySpinBox(self.stock, "Length", self.ui1.stockLength)
        self.stockWidth = BQuantitySpinBox(self.stock, "Width", self.ui1.stockWidth)
        self.stockHeight = BQuantitySpinBox(self.stock, "Height", self.ui1.stockHeight)

        self.stockOriginX = BQuantitySpinBox(self.stock, "Placement.Base.x", self.ui1.stockOriginX)
        self.stockOriginY = BQuantitySpinBox(self.stock, "Placement.Base.y", self.ui1.stockOriginY)
        self.stockOriginZ = BQuantitySpinBox(self.stock, "Placement.Base.z", self.ui1.stockOriginZ)

        self.ui1.clickOnPartBtn.clicked.connect(self.clickOnPart)

        self.stockXNeg = BQuantitySpinBox(self.stock, "XNeg", self.ui1.stockXNeg)
        self.stockXPos = BQuantitySpinBox(self.stock, "XPos", self.ui1.stockXPos)
        self.stockYNeg = BQuantitySpinBox(self.stock, "YNeg", self.ui1.stockYNeg)
        self.stockYPos = BQuantitySpinBox(self.stock, "YPos", self.ui1.stockYPos)
        self.stockZNeg = BQuantitySpinBox(self.stock, "ZNeg", self.ui1.stockZNeg)
        self.stockZPos = BQuantitySpinBox(self.stock, "ZPos", self.ui1.stockZPos)

        if hasattr(self.stock, "Length"):
            self.ui1.stackedWidget.setCurrentIndex(0)
            self.ui1.stockMode.setCurrentText("box")
        elif hasattr(self.stock, "XNeg"):
            self.ui1.stackedWidget.setCurrentIndex(1)
            self.ui1.stockMode.setCurrentText("Extend Bounding Box")

        # Initialiser les valeurs
            self.ui1.workPlane.setCurrentText(obj.WorkPlane)
        if obj.Model:
            self.ui1.model.setCurrentText(obj.Model.Name)

        # Connecter les signaux
        self.ui1.workPlane.currentIndexChanged.connect(lambda: self.updateVisual())
        self.ui1.model.currentIndexChanged.connect(lambda: self.updateVisual())
        self.ui1.stockMode.currentIndexChanged.connect(lambda: self.stockModeChanged())

        self.ui1.placeModel.clicked.connect(lambda: self.placeModel())

        # Initialiser le gestionnaire de sphères pour le positionnement du modèle
        self.sphere_manager = BoundBoxSphereManager(self)
        self.sphere_manager_active = False

    def placeModel(self):
        App.Console.PrintMessage(f'placeModel\n')
        if self.sphere_manager_active:
            # Désactiver le mode de positionnement
            self.sphere_manager.clear_spheres()
            self.sphere_manager_active = False
            self.ui1.placeModel.setText("Place Model")
            return

        self.sphere_manager_active = True
        # Obtenir le modèle sélectionné
        model_name = self.ui1.model.currentText()
        model = None
        for obj in App.ActiveDocument.Objects:
            if obj.Name == model_name:
                model = obj
                break

        if model:
            # Créer les sphères aux coins et milieux de la bounding box
            self.sphere_manager.create_spheres_for_model(model)
        else:
            App.Console.PrintWarning("Aucun modèle sélectionné\n")

    def stockModeChanged(self):
        """Gérer le changement de mode de stock"""

        mode = self.ui1.stockMode.currentText()

        if mode == "box":
            # supprimer les propriétés Xneg... de l'objet stock et ajouter Length, Width, Height

            self.ui1.stackedWidget.setCurrentIndex(0)

            if hasattr(self.stock, "XNeg"):
                for prop in ["XNeg", "YNeg", "ZNeg", "XPos", "YPos", "ZPos"]:
                    self.stock.removeProperty(prop)
            if not hasattr(self.stock, "Length"):

                bbox = self.stock.Shape.BoundBox
                # self.stockLength.setValue(bbox.XLength)
                self.stockWidth.setValue(bbox.YLength)
                self.stockHeight.setValue(bbox.ZLength)
                self.stock.addProperty("App::PropertyLength", "Length", "Stock", "Length of the stock").Length = bbox.XLength
                self.stock.addProperty("App::PropertyLength", "Width", "Stock", "Width of the stock").Width = bbox.YLength
                self.stock.addProperty("App::PropertyLength", "Height", "Stock", "Height of the stock").Height = bbox.ZLength

                self.stockLength.attach(self.stock, "Length")
                self.stockWidth.attach(self.stock, "Width")
                self.stockHeight.attach(self.stock, "Height")

                self.stock.Placement = App.Placement(App.Vector(bbox.XMin + bbox.XLength / 2, bbox.YMin + bbox.YLength / 2, bbox.ZMin + bbox.ZLength / 2), App.Rotation(App.Vector(0, 0, 1), 0))
        elif mode == "Extend Bounding Box":

            self.ui1.stackedWidget.setCurrentIndex(1)

            # supprimer les propriétés Length, Width, Height de l'objet stock et ajouter Xneg...
            for prop in ["Length", "Width", "Height"]:
                if hasattr(self.stock, prop):
                    self.stock.removeProperty(prop)
            if not hasattr(self.stock, "XNeg"):
                self.stock.addProperty("App::PropertyLength", "XNeg", "Stock", "Negative X extension").XNeg = 1
                self.stock.addProperty("App::PropertyLength", "YNeg", "Stock", "Negative Y extension").YNeg = 1
                self.stock.addProperty("App::PropertyLength", "ZNeg", "Stock", "Negative Z extension").ZNeg = 1
                self.stock.addProperty("App::PropertyLength", "XPos", "Stock", "Positive X extension").XPos = 1
                self.stock.addProperty("App::PropertyLength", "YPos", "Stock", "Positive Y extension").YPos = 1
                self.stock.addProperty("App::PropertyLength", "ZPos", "Stock", "Positive Z extension").ZPos = 1
            self.stockXNeg.attach(self.stock, "XNeg")
            self.stockXPos.attach(self.stock, "XPos")
            self.stockYNeg.attach(self.stock, "YNeg")
            self.stockYPos.attach(self.stock, "YPos")
            self.stockZNeg.attach(self.stock, "ZNeg")
            self.stockZPos.attach(self.stock, "ZPos")
        self.updateVisual()

    def getStockObject(self, obj):
        """Obtenir l'objet Stock à partir du projet CAM"""
        if hasattr(obj, "Group"):
            for child in obj.Group:
                if child.Name.startswith("Stock"):
                    return child
        return None

    def clickOnPart(self):
        """Appelé quand l'utilisateur clique sur le bouton Click on Part"""
        # Changer le texte du bouton pour indiquer que l'on attend un clic

        self.ui1.clickOnPartBtn.setText("Cliquez sur un point...")
        self.ui1.clickOnPartBtn.setEnabled(False)

        # Créer et activer l'observer
        self.observer = PointSelectionObserver.PointSelectionObserver(self.pointSelected)
        self.observer.enable()

    def pointSelected(self, point):
        """Appelé quand l'utilisateur a cliqué sur un point"""
        # Mettre à jour les coordonnées du stock origin
        self.stockOriginX.setValue(point.x)
        self.stockOriginY.setValue(point.y)
        self.stockOriginZ.setValue(point.z)

        # Mettre à jour la représentation visuelle
        self.updateVisual()

        # Remettre le bouton dans son état initial

        self.ui1.clickOnPartBtn.setText("Click on Part")
        self.ui1.clickOnPartBtn.setEnabled(True)

    def updateVisual(self):
        """Met à jour la représentation visuelle"""
        App.Console.PrintMessage(f'updateVisual\n')
        # Mettre à jour les propriétés du projet

        self.obj.WorkPlane = self.ui1.workPlane.currentText()
        model = self.ui1.model.currentText()

        # Mettre à jour les propriétés du model
        for obj in App.ActiveDocument.Objects:
            if obj.Name == model:
                self.obj.Model = obj
                break

        # Recomputer
        self.obj.Document.recompute()

    def updatePlacement(self):
        """Met à jour le placement du stock"""
        if self.stock and hasattr(self.stock, "Placement"):

            placement = App.Placement(App.Vector(self.stockOriginX.value(), self.stockOriginY.value(), self.stockOriginZ.value()), App.Rotation(App.Vector(0, 0, 1), 0))
            self.stock.Placement = placement

    def accept(self):
        """Appelé quand l'utilisateur clique sur OK"""

        self.updateVisual()

        # Nettoyer les sphères de positionnement
        if hasattr(self, 'sphere_manager'):
            self.sphere_manager.clear_spheres()

        # Fermer la tâche
        Gui.Control.closeDialog()
        return True

    def reject(self):
        """Appelé quand l'utilisateur clique sur Cancel"""

        # Nettoyer les sphères de positionnement
        if hasattr(self, 'sphere_manager'):
            self.sphere_manager.clear_spheres()

        Gui.Control.closeDialog()
        self.obj.Document.recompute()
        if self.deleteOnReject:
            # Supprimer l'objet CAM Project

            App.ActiveDocument.removeObject(self.obj.Name)

        return False

    def getStandardButtons(self):
        """Définir les boutons standard"""
        return (QtGui.QDialogButtonBox.Ok
                | QtGui.QDialogButtonBox.Cancel)


class PostProcessorTaskPanel:
    def __init__(self, obj):
        self.obj = obj
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Edit Post Processor Settings")
        layout = QtGui.QVBoxLayout(self.form)

        label = QtGui.QLabel("Post Processor specific settings can be configured here.")
        layout.addWidget(label)
        # Liste des PostProcessors disponibles
        self.postProcessors = ["Siemens828", "ITnc530", "Fanuc"]  # TODO : récupérer dynamiquement la liste des postprocessors disponibles

        # Groupe PostProcessors
        postProcGroup = QtGui.QGroupBox("PostProcessors")
        postProcLayout = QtGui.QVBoxLayout()

        # Table des postprocessors
        self.postProcTable = QtGui.QTableWidget()
        self.postProcTable.setColumnCount(2)
        self.postProcTable.setHorizontalHeaderLabels(["Sélectionné", "PostProcessor"])
        self.postProcTable.horizontalHeader().setStretchLastSection(True)
        self.postProcTable.setSelectionMode(QtGui.QAbstractItemView.NoSelection)
        self.postProcTable.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)

        # Remplir le tableau avec les postprocessors
        self.postProcTable.setRowCount(len(self.postProcessors))
        for i, postProc in enumerate(self.postProcessors):
            # Checkbox dans la première colonne
            checkBox = QtGui.QCheckBox()
            # Stocker le nom du postprocessor comme propriété
            checkBox.setProperty("postProcessorName", postProc)
            checkBox.setChecked(postProc in self.obj.PostProcessor)
            checkBox.stateChanged.connect(lambda state, name=postProc: self.postProcessorSelectionChanged(state, name))

            # Widget container pour centrer la checkbox
            checkWidget = QtGui.QWidget()
            checkLayout = QtGui.QHBoxLayout(checkWidget)
            checkLayout.addWidget(checkBox)
            checkLayout.setAlignment(QtCore.Qt.AlignCenter)
            checkLayout.setContentsMargins(0, 0, 0, 0)

            self.postProcTable.setCellWidget(i, 0, checkWidget)

            # Nom du postprocessor dans la deuxième colonne
            nameItem = QtGui.QTableWidgetItem(postProc)
            nameItem.setFlags(nameItem.flags() & ~QtCore.Qt.ItemIsEditable)
            self.postProcTable.setItem(i, 1, nameItem)

        # Ajuster la largeur des colonnes
        self.postProcTable.setColumnWidth(0, 80)

        postProcLayout.addWidget(self.postProcTable)
        postProcGroup.setLayout(postProcLayout)
        layout.addWidget(postProcGroup)

        # Ajouter un espace extensible en bas
        layout.addStretch()

        layout.addStretch()

    def getForm(self):
        return self.form

    def postProcessorSelectionChanged(self, state, PostProcessorName):
        """Appelé quand une checkbox de postprocessor est modifiée"""
        isChecked = (state == 2)
        # App.Console.PrintMessage(f'{state} {QtCore.Qt.Checked}\n')
        # App.Console.PrintMessage(f"PostProcessor '{PostProcessorName}' {'sélectionné' if isChecked else 'désélectionné'}\n")

        # Mettre à jour la propriété du projet CAM si elle existe
        if hasattr(self.obj, "PostProcessor"):
            selected = list(self.obj.PostProcessor)
            if isChecked and PostProcessorName not in selected:
                selected.append(PostProcessorName)
            elif not isChecked and PostProcessorName in selected:
                selected.remove(PostProcessorName)
            self.obj.PostProcessor = list(selected)
