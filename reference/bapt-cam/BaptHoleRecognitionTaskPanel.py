# -*- coding: utf-8 -*-

"""
BaptHoleRecognitionTaskPanel.py
Interface utilisateur pour la reconnaissance de trous
"""

import BaptDrillGeometry
from BaptUtilities import find_cam_project
import BaptUtilities
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
from utils import BQuantitySpinBox as QSB

UI = True


class HoleRecognitionTaskPanel(object):
    """TaskPanel pour la reconnaissance de trous"""

    def __init__(self, obj):
        self.obj = obj
        # try:
        if UI:
            self.form = Gui.PySideUic.loadUi(BaptUtilities.getPanel("holeRecognition.ui"))
            if self.obj.SourceShape:
                self.form.source_label.setText(self.obj.SourceShape.Label)

            self.axisXSpinBox = QSB.BQuantitySpinBox(self.obj, 'Axis.x', self.form.axisX)
            self.axisYSpinBox = QSB.BQuantitySpinBox(self.obj, 'Axis.y', self.form.axisY)
            self.axisZSpinBox = QSB.BQuantitySpinBox(self.obj, 'Axis.z', self.form.axisZ)

            self.dia_tolerance_spin = QSB.BQuantitySpinBox(self.obj, 'DiameterTolerance', self.form.dia_tolerance)
            self.depth_tolerance_spin = QSB.BQuantitySpinBox(self.obj, 'DepthTolerance', self.form.depth_tolerance)

            self.form.select_source_btn.clicked.connect(self.on_select_source)
            # self.form.dia_tolerance_spin.valueChanged.connect(self.on_dia_tolerance_changed)
            # self.form.depth_tolerance_spin.valueChanged.connect(self.on_depth_tolerance_changed)
            self.form.detect_btn.clicked.connect(self.on_detect_holes)
            self.form.export_btn.clicked.connect(self.on_export)
        else:
            self.form = self.create_ui()
            self.form.setWindowTitle("Reconnaissance de Trous")

        # except Exception as e:
        #     App.Console.PrintError(f"HoleRecognitionTaskPanel __init__ error: {e}\n")
    def create_ui(self):
        """Créer l'interface utilisateur"""
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(widget)

        # === Section Source ===
        source_group = QtGui.QGroupBox("Source")
        source_layout = QtGui.QFormLayout()

        # Sélection de la forme source
        source_widget = QtGui.QWidget()
        source_hlayout = QtGui.QHBoxLayout(source_widget)
        source_hlayout.setContentsMargins(0, 0, 0, 0)

        self.source_label = QtGui.QLabel("Aucune sélection")
        if self.obj.SourceShape:
            self.source_label.setText(self.obj.SourceShape.Label)

        self.select_source_btn = QtGui.QPushButton("Sélectionner")
        self.select_source_btn.clicked.connect(self.on_select_source)

        source_hlayout.addWidget(self.source_label)
        source_hlayout.addWidget(self.select_source_btn)

        source_layout.addRow("Forme/Face:", source_widget)

        # Sélection de l'axe de perçage
        self.axis_combo = QtGui.QComboBox()
        self.axis_combo.addItems(["Z", "X", "Y"])
        self.axis_combo.setCurrentText(self.obj.DrillAxis)
        self.axis_combo.currentTextChanged.connect(self.on_axis_changed)
        source_layout.addRow("Axe de perçage:", self.axis_combo)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        axis_widget = QtGui.QWidget()
        source_hlayout = QtGui.QHBoxLayout(axis_widget)
        self.axisX = QSB.BQuantitySpinBox(self.obj, 'Axis.x')
        self.axisY = QSB.BQuantitySpinBox(self.obj, 'Axis.y')
        self.axisZ = QSB.BQuantitySpinBox(self.obj, 'Axis.z')
        source_hlayout.addWidget(self.axisX.getWidget())
        source_hlayout.addWidget(self.axisY.getWidget())
        source_hlayout.addWidget(self.axisZ.getWidget())

        layout.addWidget(axis_widget)

        # === Section Paramètres ===
        params_group = QtGui.QGroupBox("Paramètres de détection")
        params_layout = QtGui.QFormLayout()

        # Tolérance diamètre
        self.dia_tolerance_spin = QtGui.QDoubleSpinBox()
        self.dia_tolerance_spin.setRange(0.01, 10.0)
        self.dia_tolerance_spin.setSingleStep(0.05)
        self.dia_tolerance_spin.setValue(self.obj.DiameterTolerance)
        self.dia_tolerance_spin.setSuffix(" mm")
        params_layout.addRow("Tolérance diamètre:", self.dia_tolerance_spin)

        # Tolérance profondeur
        self.depth_tolerance_spin = QtGui.QDoubleSpinBox()
        self.depth_tolerance_spin.setRange(0.1, 50.0)
        self.depth_tolerance_spin.setSingleStep(0.5)
        self.depth_tolerance_spin.setValue(self.obj.DepthTolerance)
        self.depth_tolerance_spin.setSuffix(" mm")
        self.depth_tolerance_spin.valueChanged.connect(self.on_depth_tolerance_changed)
        params_layout.addRow("Tolérance profondeur:", self.depth_tolerance_spin)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # === Bouton de détection ===
        self.detect_btn = QtGui.QPushButton("Détecter les trous")
        self.detect_btn.clicked.connect(self.on_detect_holes)
        self.detect_btn.setStyleSheet("QPushButton { font-weight: bold; padding: 8px; }")
        layout.addWidget(self.detect_btn)

        # === Section Résultats ===
        results_group = QtGui.QGroupBox("Résultats")
        results_layout = QtGui.QVBoxLayout()

        # Statistiques
        stats_widget = QtGui.QWidget()
        stats_layout = QtGui.QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 0, 0, 0)

        self.hole_count_label = QtGui.QLabel(f"Trous détectés: {self.obj.HoleCount}")
        self.group_count_label = QtGui.QLabel(f"Groupes: {self.obj.GroupCount}")

        stats_layout.addWidget(self.hole_count_label)
        stats_layout.addWidget(self.group_count_label)
        stats_layout.addStretch()

        results_layout.addWidget(stats_widget)

        # Onglets pour les tableaux
        self.tabs = QtGui.QTabWidget()

        # Table des trous individuels
        self.holes_table = QtGui.QTableWidget()
        self.holes_table.setColumnCount(4)
        self.holes_table.setHorizontalHeaderLabels(["Position (X, Y, Z)", "Diamètre", "Profondeur", "Groupe"])
        self.holes_table.horizontalHeader().setStretchLastSection(True)
        self.holes_table.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.holes_table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tabs.addTab(self.holes_table, "Trous individuels")

        # Table des groupes
        self.groups_table = QtGui.QTableWidget()
        self.groups_table.setColumnCount(4)
        self.groups_table.setHorizontalHeaderLabels(["Diamètre", "Profondeur", "Quantité", "Actions"])
        self.groups_table.horizontalHeader().setStretchLastSection(True)
        self.groups_table.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.groups_table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tabs.addTab(self.groups_table, "Groupes")

        results_layout.addWidget(self.tabs)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Boutons d'action
        action_layout = QtGui.QHBoxLayout()

        self.export_btn = QtGui.QPushButton("Exporter")
        self.export_btn.clicked.connect(self.on_export)
        self.export_btn.setEnabled(False)
        action_layout.addWidget(self.export_btn)

        action_layout.addStretch()
        layout.addLayout(action_layout)

        return widget

    def on_select_source(self):
        """Sélectionner la forme source"""
        sel = Gui.Selection.getSelection()
        if sel:
            self.obj.SourceShape = sel[0]
            if UI:
                self.form.source_label.setText(sel[0].Label)
            else:
                self.source_label.setText(sel[0].Label)
            App.Console.PrintMessage(f"Forme source sélectionnée: {sel[0].Label}\n")

    def on_axis_changed(self, axis):
        """Changement de l'axe de perçage"""
        self.obj.DrillAxis = axis

    def on_dia_tolerance_changed(self, value):
        """Changement de la tolérance de diamètre"""
        self.obj.DiameterTolerance = value

    def on_depth_tolerance_changed(self, value):
        """Changement de la tolérance de profondeur"""
        self.obj.DepthTolerance = value

    def on_detect_holes(self):
        """Lancer la détection des trous"""
        if not self.obj.SourceShape:
            QtGui.QMessageBox.warning(
                None,
                "Erreur",
                "Veuillez d'abord sélectionner une forme source"
            )
            return

        # Lancer la détection
        self.obj.Proxy.detect_holes(self.obj)

        # Mettre à jour l'interface
        self.update_results()

    def update_results(self):
        """Mettre à jour les tableaux de résultats"""
        # Mettre à jour les statistiques
        if UI:
            self.form.hole_count_label.setText(f"Trous détectés: {self.obj.HoleCount}")
            self.form.group_count_label.setText(f"Groupes: {self.obj.GroupCount}")
        else:
            self.hole_count_label.setText(f"Trous détectés: {self.obj.HoleCount}")
            self.group_count_label.setText(f"Groupes: {self.obj.GroupCount}")

        # Mettre à jour la visualisation 3D
        if hasattr(self.obj, 'ViewObject') and hasattr(self.obj.ViewObject, 'Proxy'):
            self.obj.ViewObject.Proxy.update_visualization()

        # Mettre à jour la table des trous
        self.form.holes_table.setRowCount(len(self.obj.Proxy.detected_holes))

        for row, hole in enumerate(self.obj.Proxy.detected_holes):
            # Position
            pos_str = f"({hole.center.x:.2f}, {hole.center.y:.2f}, {hole.center.z:.2f})"
            self.form.holes_table.setItem(row, 0, QtGui.QTableWidgetItem(pos_str))

            # Diamètre
            dia_str = f"{hole.diameter:.2f} mm"
            self.form.holes_table.setItem(row, 1, QtGui.QTableWidgetItem(dia_str))

            # Profondeur
            depth_str = f"{hole.depth:.2f} mm"
            self.form.holes_table.setItem(row, 2, QtGui.QTableWidgetItem(depth_str))

            # Groupe (trouver le groupe correspondant)
            group_index = self.find_group_for_hole(hole)
            group_str = f"Groupe {group_index + 1}" if group_index >= 0 else "N/A"
            self.form.holes_table.setItem(row, 3, QtGui.QTableWidgetItem(group_str))

        # Mettre à jour la table des groupes
        self.form.groups_table.setRowCount(len(self.obj.Proxy.hole_groups))

        for row, group in enumerate(self.obj.Proxy.hole_groups):
            # Diamètre
            dia_str = f"{group.diameter:.2f} mm"
            self.form.groups_table.setItem(row, 0, QtGui.QTableWidgetItem(dia_str))

            # Profondeur
            depth_str = f"{group.depth:.2f} mm"
            self.form.groups_table.setItem(row, 1, QtGui.QTableWidgetItem(depth_str))

            # Quantité
            qty_str = str(group.count())
            self.form.groups_table.setItem(row, 2, QtGui.QTableWidgetItem(qty_str))

            # Actions (bouton pour créer une opération de perçage)
            action_widget = QtGui.QPushButton("Créer opération")
            action_widget.clicked.connect(lambda checked=True, g=group: self.create_drill_operation(g))
            self.form.groups_table.setCellWidget(row, 3, action_widget)

        # Activer le bouton d'export si des trous ont été détectés
        if UI:
            self.form.export_btn.setEnabled(self.obj.HoleCount > 0)
        else:
            self.export_btn.setEnabled(self.obj.HoleCount > 0)

    def find_group_for_hole(self, hole):
        """Trouve l'index du groupe contenant ce trou"""
        for idx, group in enumerate(self.obj.Proxy.hole_groups):
            if hole in group.holes:
                return idx
        return -1

    def create_drill_operation(self, group):
        """Créer une opération de perçage pour un groupe"""
        App.Console.PrintMessage(f"Création d'une opération de perçage pour {group}\n")
        # TODO: implémenter la création d'opération de perçage
        QtGui.QMessageBox.information(
            None,
            "Information - WIP",
            f"Fonctionnalité à venir:\nCréer une opération de perçage pour {group.count()} trou(s)\n"
            f"Diamètre: {group.diameter:.2f} mm\n"
            f"Profondeur: {group.depth:.2f} mm"
        )
        doc = App.ActiveDocument
        doc.openTransaction('Create Drill Geometry')
        # Obtenir le projet CAM sélectionné
        project = find_cam_project(self.obj)
        if project is None:
            App.Console.PrintError("Aucun projet CAM trouvé. Veuillez sélectionner un projet CAM.\n")
            return

        # Créer l'objet avec le type DocumentObjectGroupPython pour pouvoir contenir des enfants
        # obj = doc.addObject("App::DocumentObjectGroupPython", "DrillGeometry")
        obj = doc.addObject("Part::FeaturePython", "DrillGeometry")
        obj.addExtension("App::GroupExtensionPython")

        # Ajouter la fonctionnalité
        drill = BaptDrillGeometry.DrillGeometry(obj)

        # Ajouter le ViewProvider
        if obj.ViewObject:
            BaptDrillGeometry.ViewProviderDrillGeometry(obj.ViewObject)

        # Ajouter au groupe Geometry
        geometry_group = project.Proxy.getGeometryGroup(project)
        geometry_group.addObject(obj)
        # Initialiser les paramètres de l'opération
        faces = []
        pos = []

        def whichFace(shp, face):
            for i, f in enumerate(shp.Faces):
                if f.isEqual(face):
                    return i
            return -1

        for hole in group.holes:
            # faces.append(hole.face)
            face_index = whichFace(self.obj.SourceShape.Shape, hole.face)
            if face_index >= 0:
                faces.append(f"Face{face_index + 1}")
            # obj.DrillPositions.append(App.Vector(hole.center.x, hole.center.y, hole.center.z)) #TODO Renamer en HolePositions
            pos.append(App.Vector(hole.center.x, hole.center.y, hole.center.z))
            pass
        try:
            App.Console.PrintMessage(f'{self.obj.SourceShape.Label }{[tuple([self.obj.SourceShape , tuple(faces)])]}\n')
            obj.DrillFaces = [tuple([self.obj.SourceShape, tuple(faces)])]
            # obj.DrillPositions= pos #TODO Renamer en HolePositions

        except Exception as e:
            App.Console.PrintError(f"Erreur lors de l'assignation des faces de perçage: {e}\n")

        doc.commitTransaction()

    def on_export(self):
        """Exporter les résultats"""
        filename, _ = QtGui.QFileDialog.getSaveFileName(
            None,
            "Exporter les résultats",
            "",
            "CSV (*.csv);;All Files (*)"
        )

        if filename:
            self.export_to_csv(filename)

    def export_to_csv(self, filename):
        """Exporter les résultats vers un fichier CSV"""
        try:
            with open(filename, 'w') as f:
                # En-têtes
                f.write("Position X,Position Y,Position Z,Diametre,Profondeur,Groupe\n")

                # Données
                for hole in self.obj.Proxy.detected_holes:
                    group_index = self.find_group_for_hole(hole)
                    f.write(f"{hole.center.x:.3f},{hole.center.y:.3f},{hole.center.z:.3f},")
                    f.write(f"{hole.diameter:.3f},{hole.depth:.3f},{group_index + 1}\n")

            App.Console.PrintMessage(f"Résultats exportés vers: {filename}\n")
            QtGui.QMessageBox.information(
                None,
                "Export réussi",
                f"Les résultats ont été exportés vers:\n{filename}"
            )
        except Exception as e:
            App.Console.PrintError(f"Erreur lors de l'export: {e}\n")
            QtGui.QMessageBox.critical(
                None,
                "Erreur",
                f"Erreur lors de l'export:\n{e}"
            )

    def accept(self):
        """Accepter les modifications"""
        Gui.Control.closeDialog()
        App.ActiveDocument.recompute()
        return True

    def reject(self):
        """Annuler les modifications"""
        Gui.Control.closeDialog()
        return True
