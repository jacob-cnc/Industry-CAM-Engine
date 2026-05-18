import os
import re
import sys

import BaptCamProject
import FreeCAD as App
import FreeCADGui as Gui
from Op import PathOp
from PySide import QtCore, QtGui
import MPFParser
import BaptUtilities
from Tool import tool_utils
from utils import Log

DEBUG = True
if DEBUG:
    Log.setLevel(Log.Level.DEBUG, Log.thisModule())
    FILE_DEBUG = "C:\\Users\\Baptou88\\AppData\\Roaming\\FreeCAD\\Mod\\Bapt\\FAO\\A911.mpf"
else:
    Log.setLevel(Log.Level.INFO, Log.thisModule())
    FILE_DEBUG = ""


class MpfReader:
    """Classe pour lire et analyser les fichiers MPF (programmes d'usinage)"""

    def __init__(self, obj):
        self.Type = "MPFReader"

        obj.addProperty("App::PropertyFile", "FilePath", "File", "Path to MPF file").FilePath = FILE_DEBUG
        # obj.addProperty("App::PropertyString", "Content", "File", "Content of MPF file")
        # obj.addProperty("App::PropertyMap", "Tools", "File", "Liste des outils avec leur diamètre et leur position")
        obj.addProperty("App::PropertyMap", "Origins", "File", "Liste des origines de programme avec leur emplacement")
        obj.Origins = {"54": "App.Vector(0, 0, 0)"}

        obj.addProperty("App::PropertyBool", "Create", "File", "Create objects")
        obj.Create = False
        obj.Proxy = self
        pass

    def onChanged(self, obj, prop):
        """Appelé quand une propriété est modifiée"""
        pass

    def execute(self, obj):

        # self.load_file(obj.FilePath)

        if not obj.Create:
            return

        current_tool = None
        current_op = None
        current_origin = None

        cam_project = BaptUtilities.find_cam_project(obj)

        if not cam_project:
            App.Console.PrintError("No active CamProject found in the document hierarchy.\n")
            return

        operations_group = cam_project.Proxy.getOperationsGroup(cam_project)
        tool_group = cam_project.Proxy.getToolsGroup()
        current_origin = cam_project.Proxy.getOrigin()

        test = ""
        gen = self.load_file_gen(obj.FilePath)
        # for line in gen:
        while True:
            line = ""
            try:
                line = next(gen)
            except StopIteration:
                App.Console.PrintMessage(f'Stop Iter\n')
                break
            App.Console.PrintMessage(f'{line}\n')
            if line == "":
                continue
            if line.startswith('N') or line[0].isdigit():  # Ligne de programme
                space = line.index(' ')
                line = line[space+1:]

            if line.startswith(';'):  # Commentaire
                continue
            elif line.startswith('* -'):
                continue
            elif line.startswith(('WORKPIECE')):
                continue
            elif line.startswith('BLK FORM'):
                line = next(gen)
                continue

            elif line.startswith('S'):
                line = line.replace('S', '')
                space = line.index(' ')
                speed_value = line[:space]
                if current_tool is not None and hasattr(current_tool, 'Speed'):
                    current_tool.Speed = int(speed_value)

            elif line.startswith('T'):  # Changement d'outil
                # Tool call can be like 'T1'  or 'T="1"' or 'TOOL CALL 1'
                match = re.match(r'T(?:="?(\d+)"?|(\d+))|TOOL\s+CALL\s+(\d+)', line)

                if match:
                    tool_number = match.group(1) or match.group(2) or match.group(3)

                    tool_obj = tool_utils.create_tool_obj(id=int(tool_number), name=f"Tool_{tool_number}")

                    tool_group.addObject(tool_obj)

                    current_tool = tool_obj

                if current_op is not None:
                    current_op.Gcode = test
                    test = ""

                # we suppose new operation starts with tool call
                current_op = App.ActiveDocument.addObject("App::FeaturePython", f"Operation_T{tool_number}")
                PathOp.pathOp(current_op)
                operations_group.addObject(current_op)
                current_op.Tool = current_tool
                current_op.Proxy.installAttachment(current_op)
                current_op.recompute()
                if False and hasattr(current_op, "AttachmentSupport"):
                    current_op.AttachmentSupport = current_origin
                    current_op.MapMode = 'ObjectXY'  # "InertialCS"
                current_op.recompute()
                PathOp.pathOpViewProviderProxy(current_op.ViewObject)

            elif line.startswith('MSG('):
                # can be handled later
                continue
            elif line.startswith(('M0', 'M00', 'M1', 'M01', 'M2', 'M02', 'M30')):
                continue  # program stop/pause, can be handled later
            elif line.startswith('M6'):  # Tool change command
                continue  # already handled with T command
            elif line.startswith(('M3', 'M4', 'M5')):
                continue  # spindle commands, can be handled later
            elif line.startswith(('M7', 'M8', 'M9')):
                continue  # coolant commands, can be handled later
            elif line.startswith('G54') or line.startswith('G55') or line.startswith('G56') or line.startswith('G57') or line.startswith('G58') or line.startswith('G59'):
                continue  # work coordinate system change, can be handled later
            elif line.startswith(('G0', 'G1', 'G2', 'G3')):  # G-code command
                if line.find('G17'):
                    line.replace('G17', '')
                    # plane selection, can be handled later

                if current_op is None:
                    Log.baptDebug("G-code command found before any tool call. Skipping.")
                    continue
                # Append G-code command to current operation

                # current_op.Gcode.append(line)
                test += line + '\n'
            elif line.startswith('L'):  # G-code command
                App.Console.PrintMessage(f'par là {line}\n')
                is_rapid = line.find('FMAX') != -1
                is_G40 = line.find('R0') != -1
                is_G41 = line.find('RL') != -1
                is_G42 = line.find('RR') != -1
                line = line.replace('FMAX', '').replace('R0', '').replace('RL', '').replace('RR', '').strip()
                line = line.replace(',', '.')
                # Verifie que G40, G41, G42 ne sont pas combinés
                if sum([is_G40, is_G41, is_G42]) > 1:
                    Log.baptDebug("G-code command L with multiple cutter compensation codes found. Skipping.")
                    continue
                new = f"{'G0 ' if is_rapid else 'G1 '} {'G40 ' if is_G40 else ''}{'G41 ' if is_G41 else ''}{'G42 ' if is_G42 else ''}"
                line = line.replace('L', new)
                if not any(['X' in line, 'Y' in line, 'Z' in line]):
                    continue
                test += line + '\n'
            elif line.startswith(('X', 'Y', 'Z')):
                if current_op is None:
                    Log.baptDebug("G-code command found before any tool call. Skipping.")
                    continue
                # Append G-code command to current operation
                test += line + '\n'
            elif line.startswith('CYCL DEF '):
                line = line.replace('CYCL DEF ', '')
                cycle_type = int(line.split(' ')[0])
                if cycle_type == 247:
                    line = next(gen)
                continue
            elif line.startswith(('CC', 'CR', 'C')):
                Log.baptError("Circular interpolation commands CC and CR are not implemented yet.")
                raise NotImplementedError("Circular interpolation commands CC and CR are not implemented yet.")
            else:
                Log.baptDebug(f"Unknown command: {line}")

        if current_op is not None:
            current_op.Gcode = test
        #     parser = MPFParser.MPFParser(self.content)
    #     commands = parser.parse()
    #     self.activeTool = None
    #     self.activeOrigin = None
    #     self.cursor = 0
    #     while self.cursor < len(commands):
    #         command = commands[self.cursor]
    #         self.cursor += 1
    #         self.process_command(command)

    #     pass

    # def process_command(self, command):
    #     if command["Type"] == "toolCall":
    #         #create object tool
    #         t = App.ActiveDocument.addObject("App::DocumentObjectGroup", f"T{command['T']}")
    #         obj.addObjects([t])
    #         self.activeTool = t

    #     pass

    def load_file(self, file_path):
        if not file_path:
            return False

        try:
            with open(file_path, 'r') as file:
                self.content = file.read()
                return True
        except Exception as e:
            App.Console.PrintError(f"Erreur lors de la lecture du fichier: {str(e)}\n")
            return False

    def load_file_gen(self, file_path):
        """Générateur pour lire un fichier ligne par ligne"""

        with open(file_path, 'r') as file:
            for line in file:
                yield line.strip()


class MpfReaderTaskPanel:
    """Panneau de tâches pour l'importation de fichiers MPF"""

    def __init__(self, obj):
        self.obj = obj
        # Créer l'interface utilisateur
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Importer un fichier MPF")
        layout = QtGui.QVBoxLayout(self.form)

        # Champ pour le chemin du fichier
        file_layout = QtGui.QHBoxLayout()
        self.file_path = QtGui.QLineEdit()
        self.file_path.setText(FILE_DEBUG)
        self.file_path.setReadOnly(True)
        file_layout.addWidget(self.file_path)

        # Bouton pour sélectionner le fichier
        self.browse_button = QtGui.QPushButton("Parcourir...")
        self.browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(self.browse_button)

        layout.addLayout(file_layout)

        # Zone de texte pour afficher le contenu du fichier
        self.content_preview = QtGui.QTextEdit()
        self.content_preview.setReadOnly(True)
        self.content_preview.setMinimumHeight(200)
        layout.addWidget(QtGui.QLabel("Aperçu du contenu:"))
        layout.addWidget(self.content_preview)

        # Zone de texte pour afficher le résumé des opérations
        self.operations_summary = QtGui.QTextEdit()
        self.operations_summary.setReadOnly(True)
        self.operations_summary.setMinimumHeight(100)
        layout.addWidget(QtGui.QLabel("Résumé des opérations:"))
        layout.addWidget(self.operations_summary)

        # Options d'importation
        options_group = QtGui.QGroupBox("Options d'importation")
        options_layout = QtGui.QVBoxLayout()

        # Option pour créer des objets FreeCAD
        self.create_objects_checkbox = QtGui.QCheckBox("Créer des objets FreeCAD")
        self.create_objects_checkbox.setChecked(obj.Create)
        options_layout.addWidget(self.create_objects_checkbox)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # tableau des origines
        self.origins_table = QtGui.QTableWidget()
        self.origins_table.setRowCount(0)
        self.origins_table.setColumnCount(4)
        self.origins_table.setHorizontalHeaderLabels(["Nom", "X", "Y", "Z"])
        self.updateOriginTable()

        layout.addWidget(self.origins_table)

        # Bouton pour ajouter une origine
        addOriginButton = QtGui.QPushButton("Ajouter une origine")
        addOriginButton.clicked.connect(self.addOrigin)
        layout.addWidget(addOriginButton)

        # Bouton pour supprimer une origine
        removeOriginButton = QtGui.QPushButton("Supprimer une origine")
        removeOriginButton.clicked.connect(self.removeOrigin)
        layout.addWidget(removeOriginButton)

    def addOrigin(self):
        name, ok = QtGui.QInputDialog.getText(self.form, "Ajouter une origine", "Nom:")
        if ok:
            position = App.Vector(0, 0, 0)
            self.obj.Origins[name] = position
            self.updateOriginTable()

    def removeOrigin(self):
        name, ok = QtGui.QInputDialog.getText(self.form, "Supprimer une origine", "Nom:")
        if ok:
            if name in self.obj.Origins:
                del self.obj.Origins[name]
                self.updateOriginTable()

    def updateOriginTable(self):
        self.origins_table.setRowCount(0)
        for i, (name, position) in enumerate(self.obj.Origins.items()):
            self.origins_table.insertRow(i)
            self.origins_table.setItem(i, 0, QtGui.QTableWidgetItem(name))
            self.origins_table.setItem(i, 1, QtGui.QTableWidgetItem(position))

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        action = menu.addAction("Edit")
        action.triggered.connect(lambda: self.setEdit(vobj))
        return True

    def setEdit(self, vobj, mode=0):
        """Ouvre le panneau de tâche pour l'édition"""

        taskd = BaptMpfReaderTaskPanel.MpfReaderTaskPanel(self.Object)
        Gui.Control.showDialog(taskd)
        return True

    def browse_file(self):
        """Ouvre une boîte de dialogue pour sélectionner un fichier MPF"""
        file_path, _ = QtGui.QFileDialog.getOpenFileName(
            self.form,
            "Sélectionner un fichier MPF",
            self.file_path.text(),
            "Fichiers MPF (*.mpf);;Tous les fichiers (*.*)"
        )

        if file_path:
            self.file_path.setText(file_path)
            self.load_file(file_path)

    def load_file(self, file_path):
        """Charge un fichier MPF

        Args:
            file_path: Chemin vers le fichier MPF
        """

    def accept(self):
        """Appelé quand l'utilisateur clique sur OK"""
        file_path = self.file_path.text()

        if not file_path:
            QtGui.QMessageBox.warning(
                self.form,
                "Aucun fichier sélectionné",
                "Veuillez sélectionner un fichier MPF à importer."
            )
            return False
        self.obj.FilePath = file_path
        # Créer des objets FreeCAD si l'option est cochée
        if self.create_objects_checkbox.isChecked():

            # created_objects = self.mpf_reader.create_freecad_objects()
            with open(file_path, "r") as file:
                content = file.read()
                mpf_parser = MPFParser.MPFParser(content)
                op = mpf_parser.parse()
            I = Interpreter(self.obj, op)
            I.process()
        # Fermer le panneau de tâches
        Gui.Control.closeDialog()
        return True

    def reject(self):
        """Appelé quand l'utilisateur clique sur Annuler"""
        Gui.Control.closeDialog()
        return True


class Interpreter:
    def __init__(self, obj, commands):
        self.commands = commands
        self.cursor = 0
        self.currentTool = None
        self.currentOrigin = None
        self.obj = obj
        pass

    def hasNext(self):
        return self.cursor < len(self.commands) - 1

    def hasPrevious(self):
        return self.cursor > 0

    def next(self):
        if not self.hasNext():
            return False
        self.cursor += 1
        return self.commands[self.cursor]

    def get(self):
        return self.commands[self.cursor]

    def process(self):
        while self.hasNext():
            command = self.get()
            if command['Type'] == 'toolCall':
                App.Console.PrintMessage('process ToolCall\n')
                self.process_tool_call(command)
            elif command['Type'] == 'gcode':
                self.process_gcode(command)
            command = self.next()

    def process_tool_call(self, command):
        tNumber = command['T']

        if self.hasPrevious():
            previousCommand = self.commands[self.cursor-1]
            if previousCommand['Type'] == 'commentaire':
                tComment = previousCommand['Commentaire']
            else:
                tComment = ''
        t = App.ActiveDocument.addObject("App::FeaturePython", f"T{tNumber}_{tComment}")
        t.addProperty("App::PropertyString", "Name", "Base", "Name of the tool")  # .setGroupAccessMethod("RO")
        t.addProperty("App::PropertyString", "Id", "Base", "Id of the tool").Id = str(tNumber)
        t.addProperty("App::PropertyString", "Comment", "Base", "Comment of the tool").Comment = tComment
        self.obj.addObject(t)
        self.currentTool = t

    def process_gcode(self, command):
        if command['G'] in [0, 1, 2, 3]:
            self.process_move(command)
        elif command['G'] in [54, 55, 56, 57, 58, 59]:
            self.currentOrigin = command['G']
            self.process_origin(command)

    def process_origin(self, command):
        pass

    def process_move(self, command):
        """
        Traite une séquence de déplacements (G0, G1, G2, G3), accumule les éléments de trajectoire (lignes et arcs),
        crée un wire pour visualiser la trajectoire de l'outil, et l'ajoute dans le groupe d'opérations du WCS courant.
        Les arcs (G2/G3) sont correctement affichés en utilisant Part.Arc. Logs et gestion d'erreur inclus.
        """
        import Part
        isMove = True
        elements = []  # Contiendra Part.LineSegment et Part.Arc
        current_pos = None
        try:
            # Initialiser la position courante à partir du premier mouvement
            if 'X' in command and 'Y' in command and 'Z' in command:
                current_pos = App.Vector(float(command['X']), float(command['Y']), float(command['Z']))
                App.Console.PrintMessage(f"[Trajectoire] Départ: {current_pos}\n")
            else:
                App.Console.PrintWarning("[Trajectoire] Commande initiale sans coordonnées XYZ.\n")

            while self.hasNext() and isMove:
                command = self.next()
                if command['Type'] == 'gcode' and command['G'] in [0, 1, 2, 3]:
                    # Extraire la position cible
                    x = float(command['X']) if 'X' in command else (current_pos.x if current_pos else 0.0)
                    y = float(command['Y']) if 'Y' in command else (current_pos.y if current_pos else 0.0)
                    z = float(command['Z']) if 'Z' in command else (current_pos.z if current_pos else 0.0)
                    target_pos = App.Vector(x, y, z)

                    if command['G'] in [0, 1]:
                        # Mouvement linéaire
                        if current_pos:
                            # App.Console.PrintMessage(f"[Trajectoire] Ligne: {current_pos} -> {target_pos}\n")
                            elements.append(Part.LineSegment(current_pos, target_pos))
                        current_pos = target_pos
                    elif command['G'] in [2, 3]:
                        # Mouvement circulaire (arc)
                        if current_pos:
                            # Calcul du centre de l'arc (donné en relatif par IJK)
                            i = float(command['I']) if 'I' in command else 0.0
                            j = float(command['J']) if 'J' in command else 0.0
                            k = float(command['K']) if 'K' in command else 0.0
                            center = current_pos.add(App.Vector(i, j, k))
                            # Calcul d'un vrai point intermédiaire sur l'arc (à mi-angle)
                            # Ceci est nécessaire car Part.Arc attend 3 points sur l'arc, pas le centre !
                            import math
                            v_start = current_pos.sub(center)
                            v_end = target_pos.sub(center)
                            # Calcul des angles
                            angle_start = math.atan2(v_start.y, v_start.x)
                            angle_end = math.atan2(v_end.y, v_end.x)
                            # Détermination du sens (horaire/antihoraire)
                            if command['G'] == 2:  # G2 = horaire
                                if angle_end > angle_start:
                                    angle_end -= 2 * math.pi
                            else:  # G3 = antihoraire
                                if angle_end < angle_start:
                                    angle_end += 2 * math.pi
                            angle_mid = (angle_start + angle_end) / 2
                            radius = (v_start.Length + v_end.Length) / 2
                            mid_point = App.Vector(
                                center.x + radius * math.cos(angle_mid),
                                center.y + radius * math.sin(angle_mid),
                                center.z  # plan XY, Z constant
                            )
                            # Créer l'arc avec les trois points sur l'arc
                            arc = Part.Arc(current_pos, mid_point, target_pos)

                            if command['G'] == 2:
                                # G2 = sens horaire, FreeCAD suit l'ordre des points
                                elements.append(arc)
                                App.Console.PrintMessage(f"[Trajectoire] Arc horaire: {current_pos} -> {target_pos} (centre: {center})\n")
                            else:
                                # G3 = sens antihoraire, inverser les points pour FreeCAD
                                # arc = Part.Arc(target_pos, center, current_pos)
                                elements.append(arc)
                                App.Console.PrintMessage(f"[Trajectoire] Arc antihoraire: {current_pos} -> {target_pos} (centre: {center})\n")
                            current_pos = target_pos
                    else:
                        App.Console.PrintWarning(f"[Trajectoire] Mouvement non pris en charge: G{command['G']}\n")
                else:
                    isMove = False
            self.cursor -= 1
            if len(elements) > 0:
                # Création du wire
                try:
                    wire_shape = Part.Wire([e.toShape() for e in elements])
                    suiviTrajectoire = App.ActiveDocument.addObject("Part::Feature", "SuiviTrajectoireWire")
                    suiviTrajectoire.Shape = wire_shape
                    suiviTrajectoire.Label = "Trajectoire Outil"
                    App.Console.PrintMessage(f"[Trajectoire] Wire créé avec {len(elements)} éléments.\n")

                    # Ajouter dans le groupe d'opérations du WCS courant si possible
                    if hasattr(self, 'currentOrigin') and self.currentOrigin:
                        group_found = False
                        for obj in App.ActiveDocument.Objects:
                            if obj.Name == str(self.currentOrigin):
                                if hasattr(obj, 'Group'):
                                    obj.Group.append(suiviTrajectoire)
                                    group_found = True
                                    App.Console.PrintMessage(f"[Trajectoire] Ajouté à {obj.Name}\n")
                                    break
                        if not group_found:
                            self.obj.addObject(suiviTrajectoire)
                            App.Console.PrintWarning(f"[Trajectoire] Groupe WCS '{self.currentOrigin}' non trouvé. Wire ajouté à la racine.\n")
                    else:
                        App.Console.PrintWarning("[Trajectoire] currentOrigin non défini. Wire ajouté à la racine.\n")
                except Exception as e:
                    App.Console.PrintError(f"[Trajectoire] Erreur lors de la création du wire: {str(e)}\n")
            else:
                App.Console.PrintWarning("[Trajectoire] Aucun élément pour créer une trajectoire.\n")
        except Exception as e:
            App.Console.PrintError(f"[Trajectoire] Erreur générale dans process_move: {str(e)}\n")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            App.Console.PrintError(f"[Trajectoire] Ligne {exc_tb.tb_lineno}\n")


class ImportMpfCommand:
    """Commande pour importer un fichier MPF"""

    def GetResources(self):
        return {
            'Pixmap': BaptUtilities.getIconPath("ImportMpf.svg"),
            'MenuText': "Importer un fichier MPF",
            'ToolTip': "Importer un programme d'usinage au format MPF"
        }

    def IsActive(self):
        return True
        return App.ActiveDocument is not None

    def Activated(self):

        doc = App.ActiveDocument

        if not doc:
            doc = App.newDocument()
        doc.openTransaction('Create MPFReader Operation')

        obj = doc.addObject("App::DocumentObjectGroupPython", "MpfReader")

        mpfReader = MpfReader(obj)

        sel = Gui.Selection.getSelection()
        for s in sel:
            if isinstance(s.Proxy, BaptCamProject.CamProject):
                s.addObject(obj)
                break
        # else:
        #     for d in App.ActiveDocument.Objects:
        #         if isinstance(d.Proxy, BaptCamProject.CamProject):
        #             d.addObject(obj)
        #             break

        if obj.ViewObject:
            ViewProviderMpfReader(obj.ViewObject)

        doc.recompute()

        if obj.ViewObject:
            obj.ViewObject.Proxy.setEdit(obj.ViewObject)

        # panel = MpfReaderTaskPanel()
        # Gui.Control.showDialog(panel)

        App.ActiveDocument.commitTransaction()


class ViewProviderMpfReader:
    """
    ViewProvider pour le MpfReader
    """

    def __init__(self, vobj):
        """
        Initialisation du ViewProvider
        """
        self.Object = vobj.Object
        vobj.Proxy = self

    def getIcon(self):
        """Retourne l'icône"""
        return BaptUtilities.getIconPath("ImportMpf.svg")

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        action = menu.addAction("Edit")
        action.triggered.connect(lambda: self.setEdit(vobj))
        return True

    def setEdit(self, vobj, mode=0):
        """Ouvre le panneau de tâche pour l'édition"""
        taskd = MpfReaderTaskPanel(self.Object)
        Gui.Control.showDialog(taskd)
        return True

    def unsetEdit(self, vobj, mode=0):
        """Ferme l'éditeur"""
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        return True

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None

    def getIcon(self):
        """
        Retourne l'icône associée à l'objet
        """
        return BaptUtilities.getIconPath("ImportMpf.svg")

    def attach(self, vobj):
        """
        Appelé lors de l'attachement du ViewProvider
        """
        self.Object = vobj.Object
        # self.onChanged(vobj, "Visibility")

    def doubleClicked(self, vobj):
        """Gérer le double-clic"""
        self.setEdit(vobj)
        return True

    def onChanged(self, obj, prop):
        """
        Appelé lorsqu'une propriété de l'objet est modifiée
        """
        if prop == "Visibility":
            if obj.Visibility:
                self.show()
            else:
                self.hide()

    def show(self):
        """
        Affiche le ViewProvider
        """
        pass

    def hide(self):
        """
        Cache le ViewProvider
        """
        pass


# Ajouter la commande à FreeCAD
# Gui.addCommand('ImportMpf', ImportMpfCommand())
