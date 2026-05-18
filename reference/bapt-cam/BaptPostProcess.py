# -*- coding: utf-8 -*-
"""
BaptPostProcess.py
Génère un programme G-code à partir des opérations du projet CAM
"""
import importlib
import os
from BaptPreferences import BaptPreferences
from CamProjectTaskPanel import PostProcessorTaskPanel
from BasePostPro import BasePostPro
import FreeCAD as App  # type: ignore
from Op import AdaptativeOp
from Op.PathOp import pathOp
from PySide import QtGui, QtCore  # type: ignore
import BaptUtilities as BaptUtils


def isOp(obj) -> bool:
    """
    Retourne True si obj est une opération d'usinage (ContournageCycle, DrillOperation, etc.).
    """
    if hasattr(obj, 'Proxy') and hasattr(obj.Proxy, 'Type') and obj.Proxy.Type in [
            'ContournageCycle', 'DrillOperation', 'Surfacage', 'Path', 'PocketOperation', 'AdaptativeOperation']:
        return True
    return False


def list_machining_operations(obj):
    """
    Parcourt récursivement toute l'arborescence de obj (Group, enfants, etc.)
    et retourne la liste de tous les objets d'usinage (ContournageCycle, DrillOperation, etc.).
    """

    ops = []
    if isOp(obj):
        ops.append(obj)
    elif hasattr(obj, 'LinkedObject'):
        linked_obj = obj.LinkedObject
        if linked_obj and isOp(linked_obj):
            # ops.extend(list_machining_operations(linked_obj))
            ops.append(obj)
    # Parcours récursif des groupes/enfants
    if hasattr(obj, 'Group') and obj.Group:
        for child in obj.Group:
            ops.extend(list_machining_operations(child))
    # evite les doublons
    unique_ops = []
    for op in ops:
        if op not in unique_ops:
            unique_ops.append(op)
    ops = unique_ops
    return ops


def generate_gcode_for_ops(ops, cam_project=None, Postpro=BasePostPro):
    """
    Génère le G-code à partir d'une liste ordonnée d'opérations (ops).
    Semblable à generate_gcode mais prend une liste explicite d'objets.
    """
    gcode_lines = [Postpro.writeHeader()]

    current_tool = None
    current_spindle = None
    current_feed = None

    blockForm = Postpro.blockForm(cam_project.Proxy.getStock(cam_project))
    gcode_lines.append(blockForm)

    App.Console.PrintMessage(f"Nombre d'opérations d'usinage sélectionnées: {len(ops)}\n")
    for obj in ops:
        if hasattr(obj, 'LinkedObject'):
            linked_obj = obj.LinkedObject
            if linked_obj and isOp(linked_obj):
                obj = linked_obj
        if not (hasattr(obj, 'Proxy') and hasattr(obj.Proxy, 'Type')):
            continue
        tool = getattr(obj, 'Tool', None)
        if tool is None:
            App.Console.PrintWarning(f"L'opération {obj.Label} n'a pas d'outil associé !\n")
            gcode_lines.append(Postpro.writeComment(f"Skipping operation {obj.Label} due to missing tool."))
            continue
        if current_tool != tool:
            tool_change_code = Postpro.toolChange(tool, cam_project)
            gcode_lines.append(tool_change_code)

            current_tool = tool

        # --- Surfacage ---
        if obj.Proxy.Type == 'Surfacage' and hasattr(obj, 'Shape'):

            gcode_lines.append(Postpro.writeComment(f"Surfacage: {obj.Label}"))

            gcode_lines.append(obj.Gcode)

        # --- Contournage ---
        if obj.Proxy.Type == 'ContournageCycle' and hasattr(obj, 'Shape'):
            transformed = Postpro.transformGCode(obj.Gcode)
            gcode_lines.append(Postpro.writeComment(f"Contournage operation: {obj.Label}"))

            gcode_lines.append(transformed)
            # gcode_lines.append(obj.Gcode)

        # --- Perçage ---
        elif obj.Proxy.Type == 'DrillOperation':
            tool_id = getattr(obj, 'ToolId', None)
            tool_name = getattr(obj, 'ToolName', None)
            spindle = getattr(obj, 'SpindleSpeed', None)
            feed = getattr(obj, 'FeedRate', None).Value
            safe_z = getattr(obj, 'SafeHeight').Value
            final_z = getattr(obj, 'FinalDepth', -5.0).Value
            cycle = getattr(obj, 'CycleType', "Simple")
            dwell = getattr(obj, 'DwellTime', 0.5)
            peck = getattr(obj, 'PeckDepth', 2.0).Value
            retract = getattr(obj, 'Retract', 1.0).Value

            gcode_lines.append(Postpro.writeComment(f"Perçage: {obj.Label}"))
            points = []
            if hasattr(obj, 'DrillGeometryName'):
                doc = App.ActiveDocument
                geom = doc.getObject(obj.DrillGeometryName)
                if geom and hasattr(geom, 'DrillPositions'):
                    points = geom.DrillPositions
            if cycle == "Simple":
                gcode_lines.append(f"{Postpro.writeComment('Cycle: G81 - Simple')}")
                gcode_lines.append(Postpro.G81(obj))

            elif cycle == "Peck":
                commentaire = Postpro.writeComment(f"Cycle: G83 - Perçage par reprise")
                gcode_lines.append(commentaire)
                for pt in points:
                    gcode_lines.append(f"G0 X{pt.x:.3f} Y{pt.y:.3f} Z{safe_z:.3f}")
                    gcode_lines.append(f"G83 X{pt.x:.3f} Y{pt.y:.3f} Z{final_z:.3f} R{safe_z:.3f} Q{peck:.3f} F{feed}")
                    gcode_lines.append(f"G80")

            elif cycle == "Tapping":
                commentaire = Postpro.writeComment(f"Cycle: G84 - Taraudage")
                gcode_lines.append(commentaire)
                gcode_lines.append(Postpro.G84(obj))

            elif cycle == "Boring":
                commentaire = Postpro.writeComment(f"Cycle: G85 - Alésage")
                gcode_lines.append(commentaire)
                for pt in points:
                    gcode_lines.append(f"G0 X{pt.x:.3f} Y{pt.y:.3f} Z{safe_z:.3f}")
                    gcode_lines.append(f"G85 X{pt.x:.3f} Y{pt.y:.3f} Z{final_z:.3f} R{safe_z:.3f} F{feed}")
                    gcode_lines.append(f"G80")
            elif cycle == "Reaming":
                gcode_lines.append(f"(Cycle: G85 - Alésage/finition)")
                commentaire = Postpro.writeComment(f"Cycle: Contournage personnalisé")
                gcode_lines.append(commentaire)
                for pt in points:
                    gcode_lines.append(f"G0 X{pt.x:.3f} Y{pt.y:.3f} Z{safe_z:.3f}")
                    gcode_lines.append(f"G85 X{pt.x:.3f} Y{pt.y:.3f} Z{final_z:.3f} R{safe_z:.3f} F{feed}")
                    gcode_lines.append(f"G80")
            elif cycle == "Contournage":
                commentaire = Postpro.writeComment(f"Cycle: Contournage personnalisé")
                gcode_lines.append(commentaire)
                gcode_lines.append(obj.Gcode)

        elif isinstance(obj.Proxy, pathOp):
            gcode_lines.append(Postpro.writeComment(f"Path operation: {obj.Label}"))
            gcode_lines.append(Postpro.transformGCode(obj.Gcode))

        elif isinstance(obj.Proxy, AdaptativeOp):
            gcode_lines.append(Postpro.writeComment(f"Adaptative operation: {obj.Label}"))
            gcode_lines.append(Postpro.transformGCode(obj.Gcode))

        else:
            gcode_lines.append('M30')  # code de fin de programme
            gcode_lines.append(Postpro.writeComment(f"Opération non prise en charge: {obj.Label} (Class: {obj.Proxy.__class__.__name__})"))

    gcode_lines.append(Postpro.writeFooter())

    return '\n'.join(gcode_lines)


def postprocess_gcode():
    doc = App.ActiveDocument
    if not doc:
        App.Console.PrintError("Aucun document actif !\n")
        return
    # Chercher le projet CAM principal
    cam_project = None
    for obj in doc.Objects:
        if hasattr(obj, 'Proxy') and hasattr(obj.Proxy, 'Type') and obj.Proxy.Type == 'CamProject':
            cam_project = obj
            break
    if not cam_project:
        App.Console.PrintError("Aucun projet CAM trouvé !\n")
        return

    dlg = PostProcessDialog(cam_project)
    dlg.exec_()

    # gcode = generate_gcode(cam_project)
    # # Demander où sauvegarder le fichier
    # prefs = BaptPreferences()
    # filename, _ = QtGui.QFileDialog.getSaveFileName(None, "Enregistrer le G-code", prefs.getGCodeFolderPath(), "Fichiers G-code (*.nc *.gcode *.tap);;Tous les fichiers (*)")
    # if not filename:
    #     App.Console.PrintMessage("Sauvegarde annulée.\n")
    #     return
    # try:
    #     with open(filename, 'w') as f:
    #         f.write(gcode)
    #     App.Console.PrintMessage(f"G-code généré et sauvegardé dans : {filename}\n")

    # except Exception as e:
    #     App.Console.PrintError(f"Erreur lors de la sauvegarde du G-code : {str(e)}\n")


class PostProcessDialog(QtGui.QDialog):
    """
    Dialog qui liste les opérations, permet checkbox + réordonner (Up/Down),
    et génère le G-code pour la sélection ordonnée.
    """

    def __init__(self, cam_project, parent=None):
        super(PostProcessDialog, self).__init__(parent)
        self.setWindowTitle("PostProcess - Sélection des opérations")
        self.resize(600, 400)
        self.cam_project = cam_project

        # Disposition principale avec un splitter gauche/droite
        main_layout = QtGui.QHBoxLayout(self)
        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal, self)
        main_layout.addWidget(splitter)

        # Panneau gauche: liste d'opérations + contrôles
        leftPane = QtGui.QWidget()
        leftLayout = QtGui.QVBoxLayout(leftPane)

        # Liste des opérations avec items checkables
        self.listWidget = QtGui.QListWidget(self)
        self.listWidget.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        leftLayout.addWidget(self.listWidget)

        # Boutons Up/Down sous la liste
        btn_layout = QtGui.QHBoxLayout()
        self.upBtn = QtGui.QPushButton("Up", self)
        self.downBtn = QtGui.QPushButton("Down", self)
        btn_layout.addWidget(self.upBtn)
        btn_layout.addWidget(self.downBtn)
        btn_layout.addStretch(1)
        leftLayout.addLayout(btn_layout)

        # Checkbox: ouvrir le pgm dans un éditeur après création
        self.openInEditorCheck = QtGui.QCheckBox("Ouvrir le programme dans un éditeur de texte après génération", self)
        self.openInEditorCheck.setChecked(True)
        leftLayout.addWidget(self.openInEditorCheck)

        # Boutons en bas
        bottom_layout = QtGui.QHBoxLayout()
        self.generateBtn = QtGui.QPushButton("Générer & Sauvegarder", self)
        self.cancelBtn = QtGui.QPushButton("Annuler", self)
        bottom_layout.addWidget(self.generateBtn)
        bottom_layout.addWidget(self.cancelBtn)
        leftLayout.addLayout(bottom_layout)

        splitter.addWidget(leftPane)

        # Panneau droit: paramètres PostProcessor (réutilise PostProcessorTaskPanel)
        self.postProcPanel = PostProcessorTaskPanel(self.cam_project)
        splitter.addWidget(self.postProcPanel.getForm())

        # Répartition des tailles
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Connects
        self.upBtn.clicked.connect(self.move_item_up)
        self.downBtn.clicked.connect(self.move_item_down)
        self.generateBtn.clicked.connect(self.on_generate)
        self.cancelBtn.clicked.connect(self.reject)

        self.populate_list()

    def populate_list(self):
        self.listWidget.clear()
        groupeOps = self.cam_project.Proxy.getOperationsGroup(self.cam_project)

        ops = list_machining_operations(groupeOps)
        for op in ops:
            displayText = f"{op.Label} {self._tool_label(op)}"
            item = QtGui.QListWidgetItem(displayText)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            item.setCheckState(QtCore.Qt.Checked if op.Active else QtCore.Qt.Unchecked)
            item.setData(QtCore.Qt.UserRole, op)
            self.listWidget.addItem(item)
            # set icon for the operation
            try:
                icon = self._icon_for_op(op)
                if not icon.isNull():
                    item.setIcon(icon)
            except Exception:
                pass

    def _tool_label(self, op):
        """Retourne une petite chaîne descriptive de l'outil associé à l'opération."""
        try:
            tool_name = op.Tool.Label
            tool_id = getattr(op.Tool, "Id", None)
            if tool_name and tool_id is not None:
                return f"{tool_name} (T{tool_id})"
            if tool_name:
                return tool_name
            if tool_id is not None:
                return f"T{tool_id}"
        except Exception:
            pass
        return "—"

    def _icon_for_op(self, op):
        """
        Retourne un QtGui.QIcon pour l'opération `op`.
        Essaie plusieurs sources (ViewObject.getIcon, ViewObject.Icon), puis un mapping par type.
        """
        try:
            # attempt: ViewObject.getIcon() returns a path or QIcon-compatible value
            vo = getattr(op, "ViewObject", None)
            if vo:
                try:
                    iconpath = vo.getIcon()
                    if iconpath:
                        return QtGui.QIcon(iconpath)
                except Exception:
                    pass
                # some viewproviders expose an 'Icon' attribute
                ico = getattr(vo, "Icon", None)
                if ico:
                    return QtGui.QIcon(ico)
        except Exception:
            pass
        # fallback mapping by Proxy.Type
        try:
            typ = getattr(op, "Proxy", None) and getattr(op.Proxy, "Type", "")
        except Exception:
            typ = ""
        mapping = {
            "Surfacage": ":/icons/Surface.svg",
            "ContournageCycle": ":/icons/Sketcher_Constraint.svg",
            "DrillOperation": ":/icons/drill.png",
        }
        if typ in mapping:
            return QtGui.QIcon(mapping[typ])
        # final fallback: empty icon
        return QtGui.QIcon()

    def updateOrder(self):
        # reorganise le groupeOperations dans le cam_project
        groupeOps = self.cam_project.Proxy.getOperationsGroup(self.cam_project)
        for r in range(self.listWidget.count()):
            item = self.listWidget.item(r)
            op = item.data(QtCore.Qt.UserRole)
            if op in groupeOps.Group:
                groupeOps.removeObject(op)
        for r in range(self.listWidget.count()):
            item = self.listWidget.item(r)
            op = item.data(QtCore.Qt.UserRole)
            groupeOps.addObject(op)

    def move_item_up(self):
        row = self.listWidget.currentRow()
        if row > 0:
            item = self.listWidget.takeItem(row)
            self.listWidget.insertItem(row-1, item)
            self.listWidget.setCurrentRow(row-1)

            self.updateOrder()

    def move_item_down(self):
        row = self.listWidget.currentRow()
        if row < self.listWidget.count()-1 and row >= 0:
            item = self.listWidget.takeItem(row)
            self.listWidget.insertItem(row+1, item)
            self.listWidget.setCurrentRow(row+1)

            self.updateOrder()

    def get_selected_ordered_ops(self):
        ops = []
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                ops.append(item.data(QtCore.Qt.UserRole))
        return ops

    def on_generate(self):
        ops = self.get_selected_ordered_ops()
        if not ops:
            QtGui.QMessageBox.warning(self, "Aucune opération", "Veuillez sélectionner au moins une opération.")
            return
        # load post processing module
        chemin_du_module = f"{BaptUtils.getPostProPath(self.cam_project.PostProcessor[0] + '.py')}"
        nom_du_module = os.path.splitext(os.path.basename(chemin_du_module))[0]
        App.Console.PrintMessage(f'{chemin_du_module}\n')
        App.Console.PrintMessage(f'{nom_du_module}\n')
        try:
            spec = importlib.util.spec_from_file_location(nom_du_module, chemin_du_module)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            pp = module.PostPro()
        except Exception as e:
            App.Console.PrintError(f"Erreur lors du chargement du module de post-traitement : {e}\n")
            QtGui.QMessageBox.critical(self, "Erreur", f"Impossible de charger le module de post-traitement:\n{e}")
            return
        gcode = generate_gcode_for_ops(ops, self.cam_project, pp)
        prefs = BaptPreferences()
        filename, _ = QtGui.QFileDialog.getSaveFileName(self, "Enregistrer le G-code", prefs.getGCodeFolderPath(), "Fichiers G-code (*.nc *.gcode *.tap);;Tous les fichiers (*)")
        if not filename:
            return
        try:
            with open(filename, 'w') as f:
                f.write(gcode)
            App.Console.PrintMessage(f"G-code généré et sauvegardé dans : {filename}\n")
            QtGui.QMessageBox.information(self, "Succès", "G-code généré et sauvegardé.")

            try:
                if self.openInEditorCheck.isChecked():
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(filename))
            except Exception as e:
                App.Console.PrintWarning(f"Impossible d'ouvrir le fichier dans l'éditeur: {e}\n")

            self.accept()
        except Exception as e:
            App.Console.PrintError(f"Erreur lors de la sauvegarde du G-code : {str(e)}\n")
            QtGui.QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder le G-code:\n{e}")
