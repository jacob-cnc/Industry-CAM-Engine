from BaptCamProject import CamProject
from BaptUtilities import find_cam_project
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
import sys
from utils import BQuantitySpinBox, Log
from utils.PointSelectionObserver import PointSelectionObserver


class ContourTaskPanel:
    def __init__(self, obj, deleteOnReject):
        # Garder une référence à l'objet
        self.obj = obj

        self.deleteOnReject = deleteOnReject

        # Créer l'interface utilisateur
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Éditer le contour")
        main_layout = QtGui.QVBoxLayout(self.form)

        # Utiliser des sections repliables verticales (accordion)
        self.contourSection = CollapsibleSection("Contour", expanded=True)
        self.advancedSection = CollapsibleSection("Avancé", expanded=False)
        main_layout.addWidget(self.contourSection)
        main_layout.addWidget(self.advancedSection)
        main_layout.addStretch(1)

        # Par commodité, créer une référence 'layout' vers la zone de contenu du 1er onglet
        layout = self.contourSection.content_layout
        # Groupe Contour
        contourGroup = QtGui.QGroupBox("Contour")
        contourLayout = QtGui.QFormLayout()

        # Boutons pour la sélection des arêtes
        selectionLayout = QtGui.QHBoxLayout()

        self.selectEdgesButton = QtGui.QPushButton("Sélectionner les arêtes")
        self.selectEdgesButton.clicked.connect(self.selectEdges)
        selectionLayout.addWidget(self.selectEdgesButton)

        self.confirmSelectionButton = QtGui.QPushButton("Confirmer la sélection")

        self.confirmSelectionButton.setEnabled(False)  # Désactivé par défaut
        selectionLayout.addWidget(self.confirmSelectionButton)

        contourLayout.addRow("Arêtes:", selectionLayout)

        # Propriété IsClosed
        self.isClosedLabel = QtGui.QLabel("Contour fermé: ")
        contourLayout.addRow("", self.isClosedLabel)

        # Affichage des arêtes sélectionnées
        self.edgesLabel = QtGui.QLabel("Aucune arête sélectionnée")
        contourLayout.addRow("", self.edgesLabel)

        # Tableau des éléments du contour
        self.edgesTable = QtGui.QTableWidget()
        self.edgesTable.setColumnCount(3)
        self.edgesTable.setHorizontalHeaderLabels(["Objet", "Élément", "Type"])
        self.edgesTable.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.edgesTable.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.edgesTable.horizontalHeader().setStretchLastSection(True)
        self.edgesTable.verticalHeader().setVisible(False)
        self.edgesTable.setMinimumHeight(150)
        contourLayout.addRow("Éléments:", self.edgesTable)

        # Connecter le signal de sélection du tableau
        self.edgesTable.itemSelectionChanged.connect(self.onTableSelectionChanged)

        # Direction
        self.direction = QtGui.QComboBox()
        self.direction.addItems(["Horaire", "Anti-horaire"])
        self.direction.setCurrentText(obj.Direction)
        contourLayout.addRow("Direction:", self.direction)

        contourGroup.setLayout(contourLayout)
        layout.addWidget(contourGroup)

        # ReverseOrder btn
        self.reverseOrderButton = QtGui.QPushButton("Inverser l'ordre des arêtes")
        self.reverseOrderButton.clicked.connect(self.reverseOrder)
        layout.addWidget(self.reverseOrderButton)

        # Groupe Coupe
        contourGroup = QtGui.QGroupBox("Paramètres du contour")
        contourLayout = QtGui.QFormLayout()

        # Hauteur de référence
        # self.Zref = QtGui.QDoubleSpinBox()
        # self.Zref.setRange(-1000, 1000)
        # self.Zref.setDecimals(3)
        # self.Zref.setSuffix(" mm")
        # self.Zref.setValue(obj.Zref)
        self.Zref = BQuantitySpinBox.BQuantitySpinBox(obj, "Zref")
        # contourLayout.addRow("Zref:", self.Zref)
        zref_container = QtGui.QWidget()
        zref_h = QtGui.QHBoxLayout()
        zref_h.setContentsMargins(0, 0, 0, 0)
        zref_h.addWidget(self.Zref.getWidget())

        self.pickZrefButton = QtGui.QPushButton("<-")
        self.pickZrefButton.setToolTip("Définir Zref au point le plus haut du contour sélectionné")
        self.pickZrefButton.clicked.connect(self.startPickZref)
        zref_h.addWidget(self.pickZrefButton)
        zref_container.setLayout(zref_h)
        contourLayout.addRow("Zref:", zref_container)

        # Mode de profondeur (absolu ou relatif)
        self.depthModeLayout = QtGui.QHBoxLayout()
        self.depthModeGroup = QtGui.QButtonGroup(self.form)

        self.absoluteDepthRadio = QtGui.QRadioButton("Absolu")
        self.relativeDepthRadio = QtGui.QRadioButton("Relatif")

        # Définir le mode actif en fonction de la propriété de l'objet
        if hasattr(obj, "DepthMode") and obj.DepthMode == "Relatif":
            self.relativeDepthRadio.setChecked(True)
        else:
            self.absoluteDepthRadio.setChecked(True)

        self.depthModeGroup.addButton(self.absoluteDepthRadio)
        self.depthModeGroup.addButton(self.relativeDepthRadio)

        self.depthModeLayout.addWidget(self.absoluteDepthRadio)
        self.depthModeLayout.addWidget(self.relativeDepthRadio)

        contourLayout.addRow("Mode de profondeur:", self.depthModeLayout)

        # Hauteur finale
        self.depth = QtGui.QDoubleSpinBox()
        self.depth.setRange(-1000, 1000)
        if self.relativeDepthRadio.isChecked():
            # self.depth.setRange(-1000, 1000)
            # self.depth.setValue(obj.depth - obj.Zref if obj.depth <= obj.Zref else -1.0)
            self.depth.setValue(obj.depth)
            self.depth.setSuffix(" mm (relatif)")
        else:
            # self.depth.setRange(0.1, 100)
            self.depth.setValue(obj.depth)
            self.depth.setSuffix(" mm (absolu)")

        self.depth.setDecimals(3)
        # contourLayout.addRow("depth:", self.depth)
        depth_container = QtGui.QWidget()
        depth_h = QtGui.QHBoxLayout()
        depth_h.setContentsMargins(0, 0, 0, 0)
        depth_h.addWidget(self.depth)
        self.pickDepthButton = QtGui.QPushButton("<-")
        self.pickDepthButton.setToolTip("Définir depth en cliquant sur un point du modèle")
        self.pickDepthButton.clicked.connect(self.startPickDepth)
        depth_h.addWidget(self.pickDepthButton)
        depth_container.setLayout(depth_h)
        contourLayout.addRow("Depth:", depth_container)

        contourGroup.setLayout(contourLayout)
        layout.addWidget(contourGroup)

        # Mettre à jour l'affichage des arêtes sélectionnées
        self.updateEdgesLabel()

        # Connecter les signaux pour l'actualisation en temps réel
        self.confirmSelectionButton.clicked.connect(self.confirmSelection)
        self.direction.currentTextChanged.connect(self.updateContour)
        # self.Zref.valueChanged.connect(self.updateZref)
        self.depth.valueChanged.connect(self.updateDepth)

        # Connecter les signaux pour le changement de mode de profondeur
        if self.obj.DepthMode == "Relatif":
            self.absoluteDepthRadio.clicked.connect(self.depthModeChanged)
        else:
            self.relativeDepthRadio.clicked.connect(self.depthModeChanged)

        # Variable pour suivre l'état de sélection
        self.selectionMode = False
        self.viewModeToRestore = None

    def reverseOrder(self):
        """Inverser l'ordre des arêtes sélectionnées"""
        if not hasattr(self.obj, "Edges") or not self.obj.Edges:
            return

        a = []
        # Inverser l'ordre des arêtes
        for edge in self.obj.Edges:
            print(edge)
            for subElement in edge[1]:
                print(subElement)
                a.insert(0, (edge[0], [subElement]))
        self.obj.Edges = a
        print(f"new edges: {self.obj.Edges}")
        # print(f"new edges reverse: {self.obj.Edges.reverse()}")

        # Mettre à jour l'affichage
        self.updateEdgesLabel()

    def updateEdgesLabel(self):
        """Met à jour l'affichage des arêtes sélectionnées"""
        if not hasattr(self.obj, "Edges") or not self.obj.Edges:
            self.edgesLabel.setText("Aucune arête sélectionnée")
            # Vider le tableau
            self.edgesTable.setRowCount(0)
            return

        count = 0
        for sub in self.obj.Edges:
            count += len(sub[1])

        self.edgesLabel.setText(f"{count} arête(s) sélectionnée(s)")
        self.isClosedLabel.setText(f"Contour fermé: {self.obj.IsClosed}")

        # Mettre à jour le tableau
        self.edgesTable.setRowCount(0)  # Vider le tableau
        row = 0
        for edge in self.obj.Edges:
            obj = edge[0]
            for subElement in edge[1]:
                self.edgesTable.insertRow(row)
                self.edgesTable.setItem(row, 0, QtGui.QTableWidgetItem(obj.Label))
                self.edgesTable.setItem(row, 1, QtGui.QTableWidgetItem(subElement))

                # Déterminer le type d'élément (ligne droite, arc, etc.)
                try:
                    element = obj.Shape.getElement(subElement)
                    # elementType = element.Curve.__class__.__name__
                    elementType = getattr(element, "ShapeType", "Inconnu4")
                    self.edgesTable.setItem(row, 2, QtGui.QTableWidgetItem(elementType))
                except Exception as e:
                    self.edgesTable.setItem(row, 2, QtGui.QTableWidgetItem("Inconnu3"))
                    App.Console.PrintError(f" {str(e)}\n")
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    App.Console.PrintMessage(f'{exc_tb.tb_lineno}\n')

                row += 1

        # Ajuster la taille des colonnes
        # self.edgesTable.resizeColumnsToContents()

    def selectEdges(self):
        """Permet à l'utilisateur de sélectionner des arêtes"""
        # Activer le mode de sélection
        self.selectionMode = True
        self.confirmSelectionButton.setEnabled(True)

        # recupere l'objet CamProject Parent
        parent = find_cam_project(self.obj)
        if parent:
            self.viewModeToRestore = parent.Model.ViewObject.DisplayMode
            # print(f"viewModeToRestore: {self.viewModeToRestore}")
            # print(f"viewModeToRestore: {parent.Model.Name}")
            if False:
                parent.Model.ViewObject.DisplayMode = u"Wireframe"
        else:
            print("No parent found")
        self.selectable = self.obj.ViewObject.Selectable
        self.obj.ViewObject.Selectable = False

        # Récupérer la sélection actuelle
        # current_selection = Gui.Selection.getSelectionEx()
        # App.Console.PrintMessage(f"Sélection actuelle: {len(current_selection)} objets.\n")

        # Demander à l'utilisateur de sélectionner des arêtes
        App.Console.PrintMessage("Sélectionnez les arêtes pour le contour, puis cliquez sur 'Confirmer la sélection'.\n")

        # Définir le mode de sélection pour les arêtes uniquement
        Gui.Selection.clearSelection()

        if False:
            Gui.Selection.addSelectionGate("SELECT Part::Feature SUBELEMENT Edge")

        # Restaurer la sélection actuelle
        for obj in self.obj.Edges:
            Gui.Selection.addSelection(obj[0], obj[1])
        # for obj in current_selection:
        #    Gui.Selection.addSelection(obj.Object)

        # Changer le texte du bouton
        self.selectEdgesButton.setText("Annuler la sélection")
        self.selectEdgesButton.clicked.disconnect()
        self.selectEdgesButton.clicked.connect(self.cancelSelection)

    def cancelSelection(self):
        """Annule le mode de sélection"""
        # Désactiver le mode de sélection
        self.selectionMode = False
        self.confirmSelectionButton.setEnabled(False)

        self.obj.ViewObject.Selectable = self.selectable

        # recupere l'objet CamProject Parent
        parent = self.obj.getParent()
        while parent and not isinstance(parent, CamProject):
            parent = parent.getParent()
        parent = self.obj.getParent().getParent()  # TODO fixme
        if parent:
            parent.Model.ViewObject.DisplayMode = self.viewModeToRestore

        # Désactiver le mode de sélection
        Gui.Selection.removeSelectionGate()

        # Restaurer le bouton
        self.selectEdgesButton.setText("Sélectionner les arêtes")
        self.selectEdgesButton.clicked.disconnect()
        self.selectEdgesButton.clicked.connect(self.selectEdges)

        App.Console.PrintMessage("Sélection annulée.\n")

    def confirmSelection(self):
        """Confirme la sélection actuelle"""
        # Récupérer la sélection
        selection = Gui.Selection.getSelectionEx()

        self.obj.ViewObject.Selectable = self.selectable

        # recupere l'objet CamProject Parent
        parent = find_cam_project(self.obj)

        if parent:
            parent.Model.ViewObject.DisplayMode = self.viewModeToRestore

        App.Console.PrintMessage(f"Confirmation de la sélection: {len(selection)} objets sélectionnés.\n")

        if not selection:
            # App.Console.PrintMessage("Aucune arête sélectionnée.\n")
            return

        # Mettre à jour les arêtes sélectionnées
        edges = []
        for sel in selection:

            if sel.SubElementNames:
                App.Console.PrintMessage(f"Objet: {sel.ObjectName}, Sous-éléments: {sel.SubElementNames}\n")
                edges.append((sel.Object, sel.SubElementNames))

        # Mettre à jour l'objet
        self.obj.Edges = edges

        # Mettre à jour l'affichage
        self.updateEdgesLabel()

        # Désactiver le mode de sélection
        self.selectionMode = False
        self.confirmSelectionButton.setEnabled(False)
        Gui.Selection.removeSelectionGate()

        # Restaurer le bouton
        self.selectEdgesButton.setText("Sélectionner les arêtes")
        self.selectEdgesButton.clicked.disconnect()
        self.selectEdgesButton.clicked.connect(self.selectEdges)

        self.detectDepth()

        # Mettre à jour la forme
        self.obj.Document.recompute()

        App.Console.PrintMessage("Sélection confirmée.\n")

    def detectDepth(self):
        """Détecte automatiquement la profondeur en fonction des arêtes sélectionnées"""
        if not hasattr(self.obj, "Edges") or not self.obj.Edges:
            Log.baptDebug("Aucune arête sélectionnée, impossible de détecter la profondeur.\n")
            return

        if self.obj.Zref != 0 and self.obj.depth != 0:
            Log.baptDebug("Zref et depth ne sont pas à 0, détection automatique de la profondeur ignorée.\n")
            return

        highest_z = float('-inf')
        lowest_z = float('inf')

        for sub in self.obj.Edges:
            obj_ref = sub[0]
            for sub_name in sub[1]:
                element = obj_ref.Shape.getElement(sub_name)
                element_type = getattr(element, "ShapeType", "Inconnu")
                if element_type == "Edge":
                    edge = obj_ref.Shape.getElement(sub_name)
                    for vertex in edge.Vertexes:
                        if vertex.Point.z > highest_z:
                            highest_z = vertex.Point.z
                        if vertex.Point.z < lowest_z:
                            lowest_z = vertex.Point.z
                elif element_type == "Face":
                    face = obj_ref.Shape.getElement(sub_name)
                    for vertex in face.Vertexes:
                        if vertex.Point.z > highest_z:
                            highest_z = vertex.Point.z
                        if vertex.Point.z < lowest_z:
                            lowest_z = vertex.Point.z

        Log.baptDebug(f"Hauteur la plus haute du contour: {highest_z} mm\n")
        Log.baptDebug(f"Hauteur la plus basse du contour: {lowest_z} mm\n")

        # Mettre à jour Zref et depth
        self.obj.Zref = highest_z
        self.obj.depth = lowest_z

        self.Zref.setValue(self.obj.Zref)
        self.depth.setValue(self.obj.depth)

    def depthModeChanged(self):
        """Gère le changement de mode de profondeur (absolu/relatif)"""

        current_value = self.depth.value()

        if self.relativeDepthRadio.isChecked():
            #     App.Console.PrintMessage('passage en relatif\n')
            self.absoluteDepthRadio.clicked.connect(self.depthModeChanged)
            self.relativeDepthRadio.clicked.disconnect(self.depthModeChanged)

            self.depth.setSuffix(" mm (relatif)")
            self.obj.DepthMode = "Relatif"
        else:
            #     App.Console.PrintMessage('passage en absolu\n')
            self.absoluteDepthRadio.clicked.disconnect(self.depthModeChanged)
            self.relativeDepthRadio.clicked.connect(self.depthModeChanged)

            self.depth.setSuffix(" mm (absolu)")
            self.obj.DepthMode = "Absolu"
        App.Console.PrintMessage('fin calcul\n')
        # Mettre à jour le contour
        self.updateContour()

    # def updateZref(self):
    #     """Met à jour Zref"""
    #     self.obj.Zref = self.Zref.value()

    def updateDepth(self):
        """Met à jour depth"""
        self.obj.depth = self.depth.value()

    def updateContour(self):
        """Met à jour le contour en fonction des paramètres"""
        # Mettre à jour la direction
        self.obj.Direction = self.direction.currentText()

        # Mettre à jour Zref
        # self.obj.Zref = self.Zref.value()

        # self.obj.depth = self.depth.value()
        self.Zref.setValue(self.obj.Zref)
        self.depth.setValue(self.obj.depth)

        # Mettre à jour le mode de profondeur
        # if self.relativeDepthRadio.isChecked():
        # Mode relatif: depth = Zref + valeur relative (négative)
        # self.obj.depth = self.Zref.value() + self.depth.value()
        # self.obj.DepthMode = "Relatif"
        # else:
        # Mode absolu: depth = valeur absolue
        # self.obj.depth = self.depth.value()
        # self.obj.DepthMode = "Absolu"

        self.obj.Document.recompute()

    def accept(self):
        """Appelé quand l'utilisateur clique sur OK"""
        # Mettre à jour toutes les propriétés
        self.obj.Direction = self.direction.currentText()

        # Désactiver le mode de sélection si actif
        if self.selectionMode:
            Gui.Selection.removeSelectionGate()

        # Calculer le point le plus haut du contour
        if hasattr(self.obj, "Edges") and self.obj.Edges:
            highest_z = float('-inf')
            for edge in self.obj.Edges:
                for sub in edge[1]:
                    face = edge[0].Shape.getElement(sub)
                    for vertex in face.Vertexes:
                        if vertex.Point.z > highest_z:
                            highest_z = vertex.Point.z
            # self.obj.Zref = highest_z
        # else:
        #     App.Console.PrintWarning("Aucune arête sélectionnée, Zref non mis à jour.\n")
        # #debug
        # App.Console.PrintMessage(f"Zref mis à jour: {self.obj.Zref}\n")

        # # Mettre à jour les autres propriétés
        # self.obj.Zref = self.Zref.value()

        # # Mettre à jour depth en fonction du mode
        # if self.relativeDepthRadio.isChecked():
        #     # Mode relatif: depth = Zref + valeur relative (négative)
        #     #self.obj.depth = self.Zref.value() + self.depth.value()
        #     self.obj.DepthMode = "Relatif"
        # else:
        #     # Mode absolu: depth = valeur absolue
        #     #self.obj.depth = self.depth.value()
        #     self.obj.DepthMode = "Absolu"

        if hasattr(self, "_clickObserver") and self._clickObserver:
            self._clickObserver.disable()
            self._clickObserver = None
            self.clickObserverActive = False

        # Recomputer
        self.obj.Document.recompute()

        # Fermer la tâche
        Gui.Control.closeDialog()
        return True

    def reject(self):
        """Appelé quand l'utilisateur clique sur Cancel"""
        # Désactiver le mode de sélection si actif
        if self.selectionMode:
            Gui.Selection.removeSelectionGate()
        if self.deleteOnReject:
            App.ActiveDocument.removeObject(self.obj.Name)
        if hasattr(self, "_clickObserver") and self._clickObserver:
            self._clickObserver.disable()
            self._clickObserver = None
            self.clickObserverActive = False

        Gui.Control.closeDialog()
        return False

    def getStandardButtons(self):
        """Définir les boutons standard"""
        # return int(QtGui.QDialogButtonBox.Ok |
        #            QtGui.QDialogButtonBox.Apply|
        #            QtGui.QDialogButtonBox.Cancel)
        return (
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Apply | QtGui.QDialogButtonBox.Cancel
        )

    def clicked(self, button):
        """clicked(button) ... callback invoked when the user presses any of the task panel buttons."""
        if button == QtGui.QDialogButtonBox.Apply:
            # self.panelGetFields()
            # self.setClean()
            App.ActiveDocument.recompute()

    def onTableSelectionChanged(self):
        """Gère la sélection d'une ligne dans le tableau"""
        selected_rows = self.edgesTable.selectedIndexes()
        if not selected_rows:
            # Aucune sélection, effacer la sélection dans FreeCAD
            Gui.Selection.clearSelection()
            return

        # Obtenir l'index de la ligne sélectionnée
        row = selected_rows[0].row()

        # Trouver l'arête correspondante dans la liste des arêtes
        current_row = 0
        for sub in self.obj.Edges:
            obj_ref = sub[0]  # L'objet référencé
            sub_names = sub[1]  # Les noms des sous-éléments (arêtes)

            for sub_name in sub_names:
                if current_row == row:
                    # Sélectionner cette arête dans FreeCAD
                    Gui.Selection.clearSelection()
                    Gui.Selection.addSelection(obj_ref, sub_name)
                    return
                current_row += 1

    def highlightEdge(self, index):
        """Met en surbrillance l'arête sélectionnée"""
        # Vérifier si l'objet a la propriété pour stocker l'index sélectionné
        if not hasattr(self.obj, "SelectedEdgeIndex"):
            self.obj.addProperty("App::PropertyInteger", "SelectedEdgeIndex", "Visualization", "Index of the selected edge")
            self.obj.SelectedEdgeIndex = -1  # -1 signifie aucune sélection

        # Mettre à jour l'index sélectionné
        self.obj.SelectedEdgeIndex = index

        # Mettre à jour la visualisation
        if hasattr(self.obj, "Proxy"):
            self.obj.Proxy.updateEdgeColors(self.obj)

        # Recomputer pour mettre à jour l'affichage
        self.obj.Document.recompute()

    # ---- PICK Z handling ----
    def startPickZref(self):
        """Démarre l'observation pour récupérer une coordonnée Z et l'appliquer à Zref"""
        App.Console.PrintMessage("Pick Zref: cliquez sur un point du modèle pour récupérer Z.\n")
        self._start_point_observer(target="Zref")
        self.pickZrefButton.setEnabled(False)

    def startPickDepth(self):
        """Démarre l'observation pour récupérer une coordonnée Z et l'appliquer à depth"""
        App.Console.PrintMessage("Pick depth: cliquez sur un point du modèle pour récupérer Z.\n")
        self._start_point_observer(target="depth")
        self.pickDepthButton.setEnabled(False)

    def _start_point_observer(self, target):
        # éviter doublons
        try:
            if hasattr(self, "clickObserverActive") and self.clickObserverActive:
                App.Console.PrintMessage("Observation de point déjà active.\n")
                return
        except Exception:
            pass
        self.clickObserverActive = True
        self._pickingTarget = target
        # Ajouter l'observer via PointSelectionObserver

        try:
            # PointSelectionObserver doit prendre en paramètre une fonction callback
            # qui recevra un Base.Vector (ou équivalent). Il doit fournir start()/stop()
            self._clickObserver = PointSelectionObserver(self._on_point_picked)
            self._clickObserver.enable()

        except Exception:
            App.Console.PrintWarning("Impossible d'ajouter l'observer de sélection (PointSelectionObserver unavailable).\n")
            self.clickObserverActive = False
            self._clickObserver = None
            return
        # guider l'utilisateur

    def _on_point_picked(self, point):
        """Callback appelé par l'observer quand un point est sélectionné"""
        if self._pickingTarget == "Zref":
            self.Zref.setValue(point.z)
        elif self._pickingTarget == "depth":
            self.depth.setValue(point.z)
        else:
            App.Console.PrintWarning(f"Target inconnu pour la sélection de point: {self._pickingTarget}\n")
        self.clickObserverActive = False
        self._clickObserver = None
        self.pickZrefButton.setEnabled(True)
        self.pickDepthButton.setEnabled(True)


class CollapsibleSection(QtGui.QWidget):
    """Section repliable (accordion) verticale : header clickable + contenu visible/caché."""

    def __init__(self, title, parent=None, expanded=True):
        super(CollapsibleSection, self).__init__(parent)
        self.header = QtGui.QPushButton(title)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        # Style minimal pour ressembler à un onglet repliant
        self.header.setStyleSheet("text-align: left; font-weight: bold;")
        self.header.clicked.connect(self._toggle)

        self.content = QtGui.QWidget()
        self.content_layout = QtGui.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(6)
        self.content.setVisible(expanded)

        lay = QtGui.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.header)
        lay.addWidget(self.content)

    def _toggle(self):
        shown = self.header.isChecked()
        self.content.setVisible(shown)

    def addWidget(self, widget):
        self.content_layout.addWidget(widget)

    def addLayout(self, layout):
        self.content.setLayout(layout)
