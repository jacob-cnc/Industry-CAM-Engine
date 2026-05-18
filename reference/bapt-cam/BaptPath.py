# https://forum.freecad.org/viewtopic.php?t=100312&sid=a77831c5cae7ee6feb8cf340f0e19dc6
from collections import deque
import math
import sys
from BaptUtilities import find_cam_project
import FreeCAD as App
import FreeCADGui


from pivy import coin  # type: ignore
from enum import Enum
from PySide import QtGui, QtCore
import Mesh
import MeshPart
from utils import Log


"""
Gcode  | Heidenhain | Description
-------|------------|----------------------------------------------
G0     | L    FMAX  | Rapid positioning
G1     | L          | Linear interpolation (feed)
G2     | C          | Circular interpolation, cw
G3     | CC         | Circular interpolation, ccw
G17    | PLANE XY   | Select XY plane for circular interpolation
G18    | PLANE XZ   | Select XZ plane for circular interpolation
G19    | PLANE YZ   | Select YZ plane for circular interpolation
G40    | R0         | Cutter compensation off
G41    | RL         | Cutter compensation left
G42    | RR         | Cutter compensation right
G90    |            | Absolute programming
G91    | I          | Incremental programming


CHF    |CHF         | Chanfrein
RND    |RND         | Rounding
LABEL  |LBL         | Label declaration
REPEAT |CALL        | Repeat block
"""


class comp(Enum):
    G40 = 0
    G41 = 1
    G42 = 2


class absinc(Enum):
    G90 = 0
    G91 = 1


class memory():
    def __init__(self):
        # labels tableau de string et int
        self.labels = {}
        self.queue = deque()
        self.variables = {}
        self.current_cycle = None
        self.absincMode = absinc.G90
        self.moveMode = None

    def addLabel(self, key, value):
        self.labels[key] = value


class GCodeHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)

        # Format G0 (rouge)
        self.fmt_g0 = QtGui.QTextCharFormat()
        self.fmt_g0.setForeground(QtGui.QColor("red"))
        self.rule_g0 = QtCore.QRegularExpression(r"\bG0\b")
        # QtCore.QRegExp(r"\bG0\b")

        # Format G1 (vert)
        self.fmt_g1 = QtGui.QTextCharFormat()
        self.fmt_g1.setForeground(QtGui.QColor("green"))
        self.rule_g1 = QtCore.QRegularExpression(r"\bG1\b")

        # Format ; or () commentaires (gris)
        self.fmt_comment = QtGui.QTextCharFormat()
        self.fmt_comment.setForeground(QtGui.QColor("gray"))
        self.rule_comment = QtCore.QRegularExpression(r";.*|(\(.*\))")

    def _apply_rule(self, text, regex, fmt):
        it = regex.globalMatch(text)
        while it.hasNext():
            match = it.next()
            start = match.capturedStart()
            length = match.capturedLength()
            self.setFormat(start, length, fmt)

    def highlightBlock(self, text):
        # G0
        self._apply_rule(text, self.rule_g0, self.fmt_g0)
        # G1
        self._apply_rule(text, self.rule_g1, self.fmt_g1)
        # Commentaires
        self._apply_rule(text, self.rule_comment, self.fmt_comment)


class GcodeEditorTaskPanel:
    def __init__(self, obj):
        self.obj = obj
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Gcode Editor")
        layout = QtGui.QVBoxLayout(self.form)

        self.textEdit = QtGui.QPlainTextEdit()
        self.textEdit.setPlainText(self.obj.Gcode)
        layout.addWidget(self.textEdit)

        # Activer le highlighter
        self.highlighter = GCodeHighlighter(self.textEdit.document())

    def accept(self):
        self.obj.Gcode = self.textEdit.toPlainText()
        FreeCADGui.Control.closeDialog()

    def reject(self):
        FreeCADGui.Control.closeDialog()

    def clicked(self, button):
        """clicked(button) ... callback invoked when the user presses any of the task panel buttons."""
        if button == QtGui.QDialogButtonBox.Apply:
            self.obj.Gcode = self.textEdit.toPlainText()
            App.ActiveDocument.recompute()

    def getStandardButtons(self):
        """Définir les boutons standard"""
        return (QtGui.QDialogButtonBox.Ok
                | QtGui.QDialogButtonBox.Apply
                | QtGui.QDialogButtonBox.Cancel)


class GcodeAnimator:
    """
    Simule le parcours d'usinage en déplaçant un marqueur (sphere) le long des segments
    feed (optionnellement rapid). Utilise QTimer (PySide) pour l'animation.
    Supporte la simulation de plusieurs opérations à la suite.
    Usage:
      anim = GcodeAnimator(view_provider)
      anim.load_paths(include_rapid=False)   # lit les listes du view provider
      anim.start(speed_mm_s=20.0)
      anim.pause()
      anim.stop()
      anim.step()                            # avance d'un pas de timer
      # Pour simuler plusieurs opérations:
      anim.set_operations([op1, op2, op3])
      anim.start(speed_mm_s=20.0)
    """

    def __init__(self, view_provider=None):
        from PySide import QtCore
        self.vp = view_provider
        self.timer = QtCore.QTimer()
        self.timer.setInterval(30)  # ms, ~33 FPS default
        self.timer.timeout.connect(self._on_timer)
        self.speed = 20.0  # mm / sec
        self.include_rapid = True

        self.tool = None
        self.toolMesh = None
        self.stock = None
        self.stockMesh = None
        self.project = None

        # Multi-operations support
        self.operations = []  # Liste des opérations à simuler
        self.current_operation_index = 0  # Index de l'opération en cours
        self.current_vp = view_provider  # ViewProvider de l'opération en cours
        self.segment_to_operation = []  # Map segment index -> operation index

        self.frequence_cut = 0
        self.indice_frequence_cut = 0

        # animation state
        self.segments = []      # list of (p0,p1) tuples
        self.seg_index = 0
        self.seg_pos = 0.0      # distance along current segment
        self.seg_len = 0.0
        self.running = False

        # marker attributes (will be created when needed)
        self.marker_switch = None
        self.marker_sep = None
        self.marker_trans = None
        self.marker_color = None
        self.marker_sphere = None

        # Initialiser depuis le view_provider si fourni
        if view_provider:
            self._init_from_vp(view_provider)

    def _init_from_vp(self, view_provider):
        """Initialise l'animator depuis un ViewProvider"""
        self.current_vp = view_provider

        # Récupérer le projet CAM actif
        if hasattr(view_provider, 'Object'):
            self.project = find_cam_project(view_provider.Object)
            if self.project:
                self.stock = self.project.Proxy.getStock(self.project)
                if self.stock and not self.stockMesh:
                    try:
                        self.stockMesh = App.activeDocument().addObject("Mesh::Feature", "stockMesh")
                        self.stockMesh.Mesh = MeshPart.meshFromShape(Shape=self.stock.Shape, MaxLength=5)
                    except Exception as e:
                        Log.log(f"Error creating stock mesh: {e}")

                # Récupérer l'outil
                if hasattr(view_provider.Object, "Tool") and view_provider.Object.Tool is not None and not self.tool:
                    self.tool = view_provider.Object.Tool
                    try:
                        self.toolMesh = App.activeDocument().addObject("Mesh::Feature", "toolMesh")
                        self.toolMesh.Mesh = MeshPart.meshFromShape(Shape=self.tool.Shape, MaxLength=5)
                    except Exception as e:
                        Log.log(f"Error creating tool mesh: {e}")

        # Créer le marqueur
        self._create_marker()

    def _create_marker(self):
        # marker group: switch to show/hide
        self.marker_switch = coin.SoSwitch()
        self.marker_switch.whichChild = coin.SO_SWITCH_NONE

        self.marker_sep = coin.SoSeparator()
        self.marker_trans = coin.SoTranslation()
        self.marker_color = coin.SoBaseColor()
        self.marker_sphere = coin.SoSphere()
        self.marker_sphere.radius = 1.0

        # default color yellow
        self.marker_color.rgb.setValues(0, 1, [(1.0, 1.0, 0.0)])

        self.marker_sep.addChild(self.marker_trans)
        self.marker_sep.addChild(self.marker_color)
        self.marker_sep.addChild(self.marker_sphere)
        self.marker_switch.addChild(self.marker_sep)

        # attach to view provider display group if available
        try:
            if self.current_vp and hasattr(self.current_vp, 'my_displaymode'):
                self.current_vp.my_displaymode.addChild(self.marker_switch)
        except Exception:
            pass

    def set_operations(self, operations):
        """
        Définit la liste des opérations à simuler
        Args:
            operations: liste d'objets opération (doivent avoir un ViewObject avec un Proxy contenant feed_coords/rapid_coords)
        """
        self.operations = [op for op in operations if op is not None]
        self.current_operation_index = 0

        # Initialiser le projet et les outils depuis la première opération
        if self.operations:
            first_op = self.operations[0]
            if hasattr(first_op, "ViewObject") and hasattr(first_op.ViewObject, "Proxy"):
                self.current_vp = first_op.ViewObject.Proxy

                # Récupérer le projet CAM actif
                self.project = find_cam_project(first_op)
                if self.project:
                    self.stock = self.project.Proxy.getStock(self.project)
                    if self.stock and not self.stockMesh:
                        try:
                            self.stockMesh = App.activeDocument().addObject("Mesh::Feature", "stockMesh")
                            self.stockMesh.Mesh = MeshPart.meshFromShape(Shape=self.stock.Shape, MaxLength=5)
                        except Exception as e:
                            Log.log(f"Error creating stock mesh: {e}")

                    # Récupérer l'outil de la première opération
                    if hasattr(first_op, "Tool") and first_op.Tool is not None and not self.tool:
                        self.tool = first_op.Tool
                        try:
                            self.toolMesh = App.activeDocument().addObject("Mesh::Feature", "toolMesh")
                            self.toolMesh.Mesh = MeshPart.meshFromShape(Shape=self.tool.Shape, MaxLength=5)
                        except Exception as e:
                            Log.log(f"Error creating tool mesh: {e}")

                # Créer le marqueur si ce n'est pas déjà fait
                if self.marker_switch is None:
                    self._create_marker()

    def load_paths(self, include_rapid=False):
        """
        Construit la liste de segments à partir des feed_coords (et éventuellement rapid_coords)
        en respectant l'ordre d'origine du programme si disponible (self.vp.ordered_segments).
        Si plusieurs opérations sont définies, charge tous les segments de toutes les opérations.
        """
        self.include_rapid = include_rapid
        segs = []
        self.segment_to_operation = []  # Réinitialiser le mapping

        # Si plusieurs opérations sont définies, charger tous les segments
        if self.operations:
            for op_idx, op in enumerate(self.operations):
                if hasattr(op, "ViewObject") and hasattr(op.ViewObject, "Proxy"):
                    vp = op.ViewObject.Proxy
                    op_segs = self._load_segments_from_vp(vp, include_rapid)
                    # Enregistrer à quelle opération appartient chaque segment
                    for _ in op_segs:
                        self.segment_to_operation.append(op_idx)
                    segs.extend(op_segs)
        else:
            # Comportement par défaut : charger depuis self.current_vp ou self.vp
            vp = self.current_vp if self.current_vp else self.vp
            if vp:
                segs = self._load_segments_from_vp(vp, include_rapid)
                # Un seul segment d'opération (index 0)
                self.segment_to_operation = [0] * len(segs)

        self.segments = segs
        self.stop()  # reset indices

    def _load_segments_from_vp(self, vp, include_rapid):
        """
        Charge les segments depuis un ViewProvider donné
        """
        segs = []
        # prefer ordered_segments if provided by the view provider (keeps original program order)
        if hasattr(vp, "ordered_segments") and vp.ordered_segments:
            for typ, a, b in vp.ordered_segments:
                if typ == "rapid" and not include_rapid:
                    continue
                segs.append((a, b))
        else:
            # fallback: keep previous behavior (rapid then feed)
            if include_rapid and hasattr(vp, "rapid_coords"):
                rc = getattr(vp, "rapid_coords") or []
                for i in range(0, len(rc), 2):
                    if i+1 < len(rc):
                        segs.append((rc[i], rc[i+1]))
            if hasattr(vp, "feed_coords"):
                fc = getattr(vp, "feed_coords") or []
                for i in range(0, len(fc), 2):
                    if i+1 < len(fc):
                        segs.append((fc[i], fc[i+1]))
        return segs

    def start(self, speed_mm_s=20.0):
        self.speed = float(speed_mm_s)
        if not self.segments:
            self.load_paths(self.include_rapid)
        if not self.segments:
            return
        self.running = True
        # initialize first segment
        self.seg_index = 0
        self._prepare_segment(0)
        self.marker_switch.whichChild = 0  # show marker
        self.timer.start()

    def pause(self):
        self.running = False
        self.timer.stop()

    def stop(self):
        self.pause()
        self.seg_index = 0
        self.seg_pos = 0.0
        self.seg_len = 0.0
        # hide marker
        try:
            self.marker_switch.whichChild = coin.SO_SWITCH_NONE
        except Exception:
            pass

    def step(self):
        """Avance d'un tick (utile pour debug ou pas-à-pas)."""
        if not self.segments:
            return
        self._on_timer()

    def set_speed(self, speed_mm_s):
        self.speed = float(speed_mm_s)

    def _prepare_segment(self, idx):
        if idx < 0 or idx >= len(self.segments):
            self.seg_len = 0.0
            return
        p0, p1 = self.segments[idx]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        dz = p1[2] - p0[2]
        self.seg_len = math.sqrt(dx*dx + dy*dy + dz*dz)
        self.seg_pos = 0.0
        self._set_marker_position(p0)

    def _set_marker_position(self, point):
        # set translation to point (x,y,z)
        try:
            self.marker_trans.translation.setValue(point[0], point[1], point[2])
            if self.tool is not None:
                self.tool.Placement = App.Placement(App.Vector(point[0], point[1], point[2]), App.Rotation(0, 0, 0, 1))
                self.tool.recompute()
            if self.toolMesh is not None:
                self.toolMesh.Placement = App.Placement(App.Vector(point[0], point[1], point[2]), App.Rotation(0, 0, 0, 1))
            self.indice_frequence_cut += 1
            if self.frequence_cut != 0 and self.indice_frequence_cut % self.frequence_cut == 0:
                self.stock.Shape = self.stock.Shape.cut(self.tool.Shape)
            # ☺self.updateMesh(App.Vector(point[0],point[1],point[2]))
        except Exception as e:
            App.Console.PrintError(f" {str(e)}\n")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            App.Console.PrintMessage(f'{exc_tb.tb_lineno}\n')
            Log.baptDebug(f"Error setting marker position: {str(e)}")
            pass

    def updateMesh(self, outil_pos):
        tolerance = 0.01
        m = self.stockMesh.Mesh
        new_facets = []
        # for f in m.Facets:
        #     d = sum([(App.Vector(p) - outil_pos).Length for p in f.Points]) / 3
        #     if d > self.tool.Radius:
        #         new_facets.append(f)
        for f in m.Facets:
            inside_count = 0
            for p in f.Points:
                global_p = App.Vector(p)
                if self.toolMesh.isInside(global_p, tolerance, True):
                    inside_count += 1
                    if inside_count < 2:
                        new_facets.append(f)

        newMesh = Mesh.Mesh(new_facets)
        self.stockMesh.Mesh = newMesh

    def _on_timer(self):
        # single step of animation based on timer interval and speed
        if not self.running or not self.segments or self.seg_index >= len(self.segments):
            self.stop()
            return

        interval_s = max(0.001, self.timer.interval() / 1000.0)
        distance = self.speed * interval_s

        # ensure current segment prepared
        if self.seg_len <= 0.0:
            self._prepare_segment(self.seg_index)

        while distance > 0 and self.seg_index < len(self.segments):
            # Mettre à jour l'index de l'opération en cours
            if self.segment_to_operation and self.seg_index < len(self.segment_to_operation):
                new_op_idx = self.segment_to_operation[self.seg_index]
                if new_op_idx != self.current_operation_index:
                    self.current_operation_index = new_op_idx
                    Log.baptDebug(f"Passage à l'opération {self.current_operation_index + 1}/{len(self.operations)}")

            p0, p1 = self.segments[self.seg_index]
            if self.seg_len <= 1e-12:
                # zero-length segment -> advance
                self.seg_index += 1
                if self.seg_index < len(self.segments):
                    self._prepare_segment(self.seg_index)
                continue

            remaining = self.seg_len - self.seg_pos
            if distance < remaining:
                # advance within current segment
                t = (self.seg_pos + distance) / self.seg_len
                x = p0[0] + (p1[0]-p0[0]) * t
                y = p0[1] + (p1[1]-p0[1]) * t
                z = p0[2] + (p1[2]-p0[2]) * t
                self.seg_pos += distance
                self._set_marker_position((x, y, z))
                distance = 0
            else:
                # jump to end of segment
                self._set_marker_position(p1)
                distance -= remaining
                self.seg_index += 1
                if self.seg_index < len(self.segments):
                    self._prepare_segment(self.seg_index)
                else:
                    # finished all segments
                    self.stop()
                    return

    def is_running(self):
        return self.running

    def get_current_operation_index(self):
        """Retourne l'index de l'opération en cours"""
        return self.current_operation_index

    def get_operations_count(self):
        """Retourne le nombre d'opérations à simuler"""
        return len(self.operations) if self.operations else 0


class GcodeAnimationControl():
    """Interface graphique pour contrôler GcodeAnimator"""

    def __init__(self, operations=None):
        # super(GcodeAnimationControl, self).__init__(parent)

        self.animator = GcodeAnimator()

        # Si des opérations sont fournies, les configurer
        if operations:
            self.animator.set_operations(operations)

        self.ui1 = QtGui.QWidget()
        self.ui1.setWindowTitle("Animation Control")

        self.ui2 = QtGui.QWidget()
        self.ui2.setWindowTitle("Tool Position")

        self.ui3 = QtGui.QWidget()
        self.ui3.setWindowTitle("Operations")

        self.form = [self.ui1, self.ui2, self.ui3]

        # Layout principal vertical
        layout = QtGui.QVBoxLayout(self.ui1)

        # Boutons de contrôle dans un layout horizontal
        btnLayout = QtGui.QHBoxLayout()

        # Bouton Play
        self.playBtn = QtGui.QPushButton()
        self.playBtn.setIcon(QtGui.QIcon(":/icons/media-playback-start.svg"))
        self.playBtn.setToolTip("Play")
        self.playBtn.clicked.connect(self.play)

        # Bouton Pause
        self.pauseBtn = QtGui.QPushButton()
        self.pauseBtn.setIcon(QtGui.QIcon(":/icons/media-playback-pause.svg"))
        self.pauseBtn.setToolTip("Pause")
        self.pauseBtn.clicked.connect(self.pause)

        # Bouton Stop
        self.stopBtn = QtGui.QPushButton()
        self.stopBtn.setIcon(QtGui.QIcon(":/icons/media-playback-stop.svg"))
        self.stopBtn.setToolTip("Stop")
        self.stopBtn.clicked.connect(self.stop)

        # Bouton Step
        self.stepBtn = QtGui.QPushButton()
        self.stepBtn.setIcon(QtGui.QIcon(":/icons/media-skip-forward.svg"))
        self.stepBtn.setToolTip("Single Step")
        self.stepBtn.clicked.connect(self.step)

        # Contrôle de vitesse
        speedLayout = QtGui.QHBoxLayout()
        speedLayout.addWidget(QtGui.QLabel("Speed:"))
        self.speedSpinBox = QtGui.QDoubleSpinBox()
        self.speedSpinBox.setRange(0.1, 1000.0)
        self.speedSpinBox.setValue(self.animator.speed)
        self.speedSpinBox.setSuffix(" mm/s")
        self.speedSpinBox.valueChanged.connect(self.speedChanged)
        speedLayout.addWidget(self.speedSpinBox)

        # Contrôle de frequence
        frequenceLayout = QtGui.QHBoxLayout()
        frequenceLayout.addWidget(QtGui.QLabel("Frequence:"))
        self.frequenceSpinBox = QtGui.QDoubleSpinBox()
        self.frequenceSpinBox.setRange(0., 1000.0)
        self.frequenceSpinBox.setValue(self.animator.frequence_cut)
        self.frequenceSpinBox.valueChanged.connect(self.frequenceChanged)
        frequenceLayout.addWidget(self.frequenceSpinBox)

        # Include Rapid moves checkbox
        self.rapidCheckBox = QtGui.QCheckBox("Include Rapid Moves")
        self.rapidCheckBox.setChecked(self.animator.include_rapid)
        self.rapidCheckBox.stateChanged.connect(self.rapidChanged)

        # Ajouter les widgets aux layouts
        btnLayout.addWidget(self.playBtn)
        btnLayout.addWidget(self.pauseBtn)
        btnLayout.addWidget(self.stopBtn)
        btnLayout.addWidget(self.stepBtn)

        layout.addLayout(btnLayout)
        layout.addLayout(speedLayout)
        layout.addLayout(frequenceLayout)
        layout.addWidget(self.rapidCheckBox)

        layoutToolPos = QtGui.QVBoxLayout(self.ui2)
        self.toolPosXLabel = QtGui.QLabel("X: 0.0")
        self.toolPosYLabel = QtGui.QLabel("Y: 0.0")
        self.toolPosZLabel = QtGui.QLabel("Z: 0.0")

        layoutToolPos.addWidget(self.toolPosXLabel)
        layoutToolPos.addWidget(self.toolPosYLabel)
        layoutToolPos.addWidget(self.toolPosZLabel)

        # Onglet Operations
        layoutOperations = QtGui.QVBoxLayout(self.ui3)

        # Label pour afficher l'opération en cours
        self.currentOpLabel = QtGui.QLabel("Opération en cours: -")
        layoutOperations.addWidget(self.currentOpLabel)

        # Liste des opérations
        self.operationsListWidget = QtGui.QListWidget()
        if self.animator.operations:
            for i, op in enumerate(self.animator.operations):
                item_text = f"{i+1}. {op.Label if hasattr(op, 'Label') else op.Name}"
                self.operationsListWidget.addItem(item_text)
        layoutOperations.addWidget(QtGui.QLabel("Opérations à simuler:"))
        layoutOperations.addWidget(self.operationsListWidget)

        # Timer pour mettre à jour l'état des boutons
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.timeout.connect(self.updateButtons)
        self.updateTimer.start(100)  # 10 Hz

        self.updateButtons()

        if self.animator.tool is not None:
            self.animator.tool.Visibility = True

    def play(self):
        """Démarre ou reprend l'animation"""
        if not self.animator.is_running():
            self.animator.start(self.speedSpinBox.value())
        self.updateButtons()

    def pause(self):
        """Met en pause l'animation"""
        self.animator.pause()
        self.updateButtons()

    def stop(self):
        """Arrête l'animation"""
        self.animator.stop()
        self.updateButtons()

    def step(self):
        """Avance d'un pas"""
        self.animator.step()
        self.updateButtons()

    def speedChanged(self, value):
        """Appelé quand la vitesse change"""
        self.animator.set_speed(value)

    def frequenceChanged(self, value):
        self.animator.frequence_cut = value

    def rapidChanged(self, state):
        """Appelé quand la case Include Rapid change"""
        include_rapid = (state == QtCore.Qt.Checked)
        self.animator.include_rapid = include_rapid
        self.animator.load_paths(include_rapid)

    def updateButtons(self):
        """Met à jour l'état des boutons selon l'état de l'animation"""
        running = self.animator.is_running()
        self.playBtn.setEnabled(not running)
        self.pauseBtn.setEnabled(running)
        self.stopBtn.setEnabled(running)
        self.stepBtn.setEnabled(not running)

        if running:
            self.toolPosXLabel.setText(f"X: {self.animator.marker_trans.translation.getValue()[0]:.3f}")
            self.toolPosYLabel.setText(f"Y: {self.animator.marker_trans.translation.getValue()[1]:.3f}")
            self.toolPosZLabel.setText(f"Z: {self.animator.marker_trans.translation.getValue()[2]:.3f}")

        # Mettre à jour l'affichage de l'opération en cours
        if self.animator.operations:
            total_ops = self.animator.get_operations_count()
            current_idx = self.animator.get_current_operation_index()
            if current_idx < total_ops:
                op = self.animator.operations[current_idx]
                op_name = op.Label if hasattr(op, 'Label') else op.Name
                self.currentOpLabel.setText(f"Opération en cours: {current_idx + 1}/{total_ops} - {op_name}")
                # Mettre en surbrillance l'opération en cours dans la liste
                self.operationsListWidget.setCurrentRow(current_idx)
            else:
                self.currentOpLabel.setText("Simulation terminée")

    def closeEvent(self, event):
        """Arrête l'animation quand on ferme la fenêtre"""
        self.animator.stop()
        self.updateTimer.stop()
        if self.animator.tool is not None:
            self.animator.tool.Visibility = False
        if self.animator.stockMesh is not None:
            App.activeDocument().removeObject(self.animator.stockMesh.Name)
            self.animator.stockMesh = None
        if self.animator.toolMesh is not None:
            App.activeDocument().removeObject(self.animator.toolMesh.Name)
            self.animator.toolMesh = None
        # super(GcodeAnimationControl, self).closeEvent(event)

    def accept(self):
        self.stop()
        self.closeEvent(None)
        FreeCADGui.Control.closeDialog()
        return True

    def reject(self):
        self.stop()
        self.closeEvent(None)
        FreeCADGui.Control.closeDialog()
        return False
