import math
import FreeCAD as App
import FreeCADGui as Gui
import Part

import BaptPreferences
import BaptUtilities
from Op import BaseOp
from Tool.ToolTaskPannel import ToolTaskPanel
from utils import Log, GcodeWriter
from utils.BQuantitySpinBox import BQuantitySpinBox
from utils.Contour import shiftWire


if True:
    Log.setLevel(Log.Level.DEBUG, Log.thisModule())
else:
    Log.setLevel(Log.Level.INFO, Log.thisModule())

Stock = ["Stock", "PreviousOp"]

Direction = ["Climb (Avalant)", "Conventional (opposition)"]
Plongee = ["Directe", "Helicoidale"]


class AdaptativeOp(BaseOp.baseOp):
    """
    Opération d'usinage adaptatif par pelure (peel milling).
    Usine la matière entre le brut (stock bounding box) et un contour fini
    par des passes concentriques avec engagement radial (ae) contrôlé.
    """
    Type = "AdaptativeOp"

    def __init__(self, obj):
        super().__init__(obj)
        self.initProperties(obj)
        obj.Proxy = self

    def initProperties(self, obj):
        if not hasattr(obj, "Contour"):
            obj.addProperty("App::PropertyLink", "Contour", "Adaptive",
                            "ContourGeometry de la pièce finie")

        if not hasattr(obj, "ToolDiameter"):
            obj.addProperty("App::PropertyFloat", "ToolDiameter", "Adaptive",
                            "Diamètre outil (mm)").ToolDiameter = 6.0

        if not hasattr(obj, "StepDown"):
            obj.addProperty("App::PropertyFloat", "StepDown", "Adaptive",
                            "Profondeur de passe (mm)").StepDown = 20.0

        if not hasattr(obj, "EngagementRadial"):
            obj.addProperty("App::PropertyFloat", "EngagementRadial", "Adaptive",
                            "Engagement radial max (ae) en mm").EngagementRadial = 1.0

        if not hasattr(obj, "SurepAxiale"):
            obj.addProperty("App::PropertyFloat", "SurepAxiale", "Adaptive",
                            "Surépaisseur axiale (mm)").SurepAxiale = 0.0

        if not hasattr(obj, "SurepRadiale"):
            obj.addProperty("App::PropertyFloat", "SurepRadiale", "Adaptive",
                            "Surépaisseur radiale (mm)").SurepRadiale = 0.0

        if not hasattr(obj, "Direction"):
            obj.addProperty("App::PropertyEnumeration", "Direction", "Adaptive",
                            "Direction d'usinage").Direction = Direction
            obj.Direction = Direction[0]

        if not hasattr(obj, "PlungeType"):
            obj.addProperty("App::PropertyEnumeration", "PlungeType", "Adaptive",
                            "Type de plongée").PlungeType = Plongee
            obj.PlungeType = Plongee[0]

        if not hasattr(obj, "debugMode"):
            obj.addProperty("App::PropertyBool", "debugMode", "General",
                            "Activer le mode debug").debugMode = False

        self.installToolProp(obj)

    def onChanged(self, obj, prop):
        if prop in ["Contour", "ToolDiameter", "StepDown", "EngagementRadial",
                    "SurepAxiale", "SurepRadiale", "Direction", "PlungeType",
                    "debugMode"]:
            self.execute(obj)

    def onDocumentRestored(self, obj):
        self.initProperties(obj)

    def execute(self, obj):
        if App.ActiveDocument.Restoring:
            return

        try:
            shape = obj.Contour.Shape if obj.Contour and hasattr(obj.Contour, "Shape") else None
            if not shape:
                App.Console.PrintWarning("AdaptativeOp: Aucun contour sélectionné.\n")
                obj.Shape = Part.Shape()
                return

            # Récupérer le stock (bounding box)
            stock_shape = self._getStockShape(obj)
            if stock_shape is None:
                App.Console.PrintWarning("AdaptativeOp: Aucun stock trouvé.\n")
                obj.Shape = Part.Shape()
                return

            tool_diam = obj.ToolDiameter
            tool_radius = tool_diam / 2.0
            ae = obj.EngagementRadial  # engagement radial max
            surep_rad = obj.SurepRadiale

            # Contour fini = offset du contour pièce par (rayon outil + surépaisseur radiale)
            # Extraire un Wire depuis la Shape (qui peut être Wire, Edge, ou Compound)
            if shape.ShapeType == 'Wire':
                contour_wire = shape
            elif shape.ShapeType == 'Edge':
                contour_wire = Part.Wire([shape])
            elif shape.Wires:
                contour_wire = shape.Wires[0]
            else:
                App.Console.PrintWarning(
                    "AdaptativeOp: La shape du contour n'est ni un Wire ni un Edge.\n")
                obj.Shape = Part.Shape()
                return

            finish_offset = tool_radius + surep_rad
            try:
                finish_wire = contour_wire.makeOffset2D(finish_offset, join=0,
                                                        fill=False, openResult=False)
            except Exception:
                App.Console.PrintWarning(
                    "AdaptativeOp: Impossible de créer l'offset du contour fini.\n")
                obj.Shape = Part.Shape()
                return

            # Wire du stock (rectangle de la bounding box en XY)
            bb = stock_shape.BoundBox
            stock_wire = Part.makePolygon([
                App.Vector(bb.XMin, bb.YMin, 0),
                App.Vector(bb.XMax, bb.YMin, 0),
                App.Vector(bb.XMax, bb.YMax, 0),
                App.Vector(bb.XMin, bb.YMax, 0),
                App.Vector(bb.XMin, bb.YMin, 0),
            ])

            # Sens de rotation — usinage extérieur :
            # Avalant (Climb) = CW, Opposition (Conventional) = CCW
            want_ccw = (obj.Direction != Direction[0])

            # Générer le parcours pelure
            path_shapes = self._generate_path(
                finish_wire, stock_wire, tool_radius, ae, want_ccw)

            if not path_shapes:
                App.Console.PrintWarning("AdaptativeOp: Aucun parcours généré.\n")
                obj.Shape = Part.Shape()
                return

            # Génération du G-code
            gcodeWriter = GcodeWriter.GcodeWriter()

            step_down = abs(obj.StepDown)
            final_depth = obj.Contour.depth if hasattr(obj.Contour, "depth") else -5.0
            final_depth += obj.SurepAxiale
            start_depth = obj.Contour.Zref if hasattr(obj.Contour, "Zref") else 0.0
            feed_rate = float(obj.FeedRate.getValueAs('mm/min')) if hasattr(obj, 'FeedRate') else 1000.0
            safe_z = start_depth + 5.0

            total_depth = abs(final_depth - start_depth)
            num_passes = max(1, math.ceil(total_depth / step_down))

            # Premier point du parcours (basé sur la connectivité)
            start_pt = self._wire_start_point(path_shapes[0])

            for pass_num in range(num_passes):
                current_z = final_depth if pass_num == num_passes - 1 \
                    else start_depth - (pass_num + 1) * step_down

                gcodeWriter.comment(
                    f"Passe {pass_num + 1}/{num_passes} Z={current_z:.3f}")

                # Positionnement rapide
                gcodeWriter.linearMove({'X': start_pt.x, 'Y': start_pt.y}, rapid=True)
                gcodeWriter.linearMove({'Z': safe_z}, rapid=True)

                # Plongée
                if obj.PlungeType == "Directe":
                    gcodeWriter.linearMove({'Z': current_z}, feed=feed_rate)
                elif obj.PlungeType == "Helicoidale":
                    dz = safe_z - current_z
                    nbtour = max(1, math.ceil(dz / 1.0))
                    prise = (dz / nbtour) / 2
                    diam = tool_diam * 1.5
                    gcodeWriter.linearMove(
                        {'X': start_pt.x + diam / 2, 'Y': start_pt.y,
                         'Z': safe_z}, feed=feed_rate)
                    for i in range(nbtour):
                        z1 = safe_z - ((i + 1) * prise + i * prise)
                        z2 = safe_z - ((i + 1) * prise * 2)
                        gcodeWriter.arcMove(
                            {'X': start_pt.x - diam / 2, 'Y': start_pt.y,
                             'Z': z1, 'CCW': True, 'I': -diam / 2, 'J': 0},
                            feed=feed_rate)
                        gcodeWriter.arcMove(
                            {'X': start_pt.x + diam / 2, 'Y': start_pt.y,
                             'Z': z2, 'CCW': True, 'I': diam / 2, 'J': 0},
                            feed=feed_rate)
                    gcodeWriter.linearMove(
                        {'X': start_pt.x, 'Y': start_pt.y, 'Z': current_z},
                        feed=feed_rate)

                # Parcourir les segments du chemin
                # Identifier les transitions Z retract grâce aux lignes
                # de liaison (Part.makeLine) insérées par _generate_path
                transition_idx = 0
                transitions = getattr(self, '_pass_transitions', [])
                current_pos = App.Vector(start_pt)

                for seg_i, segment in enumerate(path_shapes):
                    seg_start = self._wire_start_point(segment)

                    # Si on n'est pas au bon endroit, c'est une transition
                    d_to_seg = (current_pos - seg_start).Length
                    if d_to_seg > 0.5 and transition_idx < len(transitions):
                        transition_type = transitions[transition_idx]
                        transition_idx += 1

                        if transition_type == 'z_retract':
                            # Dégagement Z, rapide vers le segment suivant, replongée
                            gcodeWriter.comment("Dégagement Z")
                            gcodeWriter.linearMove({'Z': safe_z}, rapid=True)
                            gcodeWriter.linearMove(
                                {'X': seg_start.x, 'Y': seg_start.y},
                                rapid=True)
                            gcodeWriter.linearMove(
                                {'Z': current_z}, feed=feed_rate)
                            current_pos = seg_start
                        # 'perp' => la ligne de liaison est dans le path,
                        # elle sera usinée normalement

                    for edge in segment.Edges:
                        d0 = (edge.Vertexes[0].Point - current_pos).Length
                        d1 = (edge.Vertexes[-1].Point - current_pos).Length
                        bonSens = d0 <= d1

                        if edge.Curve.TypeId == 'Part::GeomCircle':
                            circle = edge.Curve
                            center = circle.Center
                            if bonSens:
                                sp = edge.Vertexes[0].Point
                                ep = edge.Vertexes[-1].Point
                            else:
                                sp = edge.Vertexes[-1].Point
                                ep = edge.Vertexes[0].Point

                            is_ccw = circle.Axis.z > 0
                            if not bonSens:
                                is_ccw = not is_ccw

                            gcodeWriter.arcMove({
                                'X': ep.x, 'Y': ep.y,
                                'I': center.x - sp.x,
                                'J': center.y - sp.y,
                                'CCW': is_ccw}, feed=feed_rate)
                            current_pos = ep
                        else:
                            ep = edge.Vertexes[-1].Point if bonSens \
                                else edge.Vertexes[0].Point
                            gcodeWriter.linearMove(
                                {'X': ep.x, 'Y': ep.y}, feed=feed_rate)
                            current_pos = ep

                gcodeWriter.linearMove({'Z': safe_z}, rapid=True)

            obj.Gcode = "\n".join(gcodeWriter.lines)
            Log.baptDebug(f"G-code adaptatif: {len(obj.Gcode)} caractères\n")

            # Shape de visualisation
            compound = Part.makeCompound(path_shapes)
            obj.Shape = compound

        except Exception as e:
            import sys
            import traceback
            App.Console.PrintError(f"AdaptativeOp erreur: {e}\n")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_number = exc_traceback.tb_lineno
            App.Console.PrintError(f"Erreur à la ligne {line_number}\n")

    # ==========================================================================
    # Méthodes internes
    # ==========================================================================

    def _getStockShape(self, obj):
        """Récupère la shape du stock depuis le projet CAM."""
        camProject = BaptUtilities.find_cam_project(obj)
        if not camProject:
            return None
        stock = camProject.Proxy.getStock(camProject)
        if stock and hasattr(stock, 'Shape'):
            return stock.Shape
        return None

    def _point_on_wire(self, wire, dist_along):
        """Retourne (point, tangent) sur le wire à la distance donnée depuis le début."""
        cumulative = 0.0
        for edge in wire.Edges:
            edge_len = edge.Length
            if cumulative + edge_len >= dist_along - 1e-6:
                local_dist = max(0, dist_along - cumulative)
                param = edge.getParameterByLength(local_dist)
                point = edge.valueAt(param)
                tangent = edge.tangentAt(param)
                return point, tangent
            cumulative += edge_len
        # Au-delà du wire : dernier point
        last_edge = wire.Edges[-1]
        param = last_edge.LastParameter
        return last_edge.valueAt(param), last_edge.tangentAt(param)

    def _generate_path(self, finish_wire, stock_wire,
                       tool_radius, ae, want_ccw):
        """
        Algorithme de pelure (peel milling).

        Principe :
        1. Partir du contour fini (finish_wire).
        2. Générer des offsets successifs vers l'extérieur, espacés de ae.
        3. Pour chaque offset, vérifier si le wire est entièrement dans le stock
           (complet) ou partiellement (clippé).
        4. Wires complets : usiner en entier avec transition perpendiculaire
           vers la passe suivante.
        5. Wires clippés : ne garder que les edges à l'intérieur du stock,
           avec dégagement Z entre les segments disjoints.
        6. Usiner de l'extérieur vers l'intérieur.

        Retourne une liste de Part.Shape.
        self._pass_transitions contient les marqueurs de transition pour le G-code.
        """
        # Extraire le wire du finish
        fw = finish_wire.Wires[0] if hasattr(finish_wire, 'Wires') \
            and finish_wire.Wires else finish_wire

        # BoundBox du stock pour les tests d'appartenance
        bb = stock_wire.BoundBox
        margin = 0.01  # tolérance

        # Distance max pour savoir quand s'arrêter
        bb_finish = fw.BoundBox

        Log.baptDebug(
            f"Stock BB: X[{bb.XMin:.2f}, {bb.XMax:.2f}] "
            f"Y[{bb.YMin:.2f}, {bb.YMax:.2f}]\n")
        Log.baptDebug(
            f"Finish BB: X[{bb_finish.XMin:.2f}, {bb_finish.XMax:.2f}] "
            f"Y[{bb_finish.YMin:.2f}, {bb_finish.YMax:.2f}]\n")
        Log.baptDebug(
            f"Finish wire: isClosed={fw.isClosed()}, "
            f"isCCW={self._is_ccw(fw) if fw.isClosed() else 'N/A'}, "
            f"Length={fw.Length:.2f}, Edges={len(fw.Edges)}\n")

        # Distance max : demi-diagonale du stock (couvre tous les cas,
        # même contours circulaires ou complexes).
        # Le compteur consecutive_empty arrêtera la boucle quand tous
        # les offsets seront hors stock.
        max_dist = bb.DiagonalLength / 2.0

        if max_dist < 0.1:
            App.Console.PrintWarning("AdaptativeOp: Pas de matière à enlever.\n")
            return []

        num_passes = max(1, math.ceil(max_dist / ae)) + 2
        Log.baptDebug(
            f"Pelure: max {num_passes} passes, "
            f"dist_max={max_dist:.2f}, ae={ae:.2f}\n")

        # Déterminer le signe correct pour que l'offset aille vers l'extérieur
        # (vers le stock). makeOffset2D(+) va à gauche du wire:
        # - Wire CCW => + = outward
        # - Wire CW  => + = inward
        # On veut aller vers l'extérieur (agrandir la BoundBox).
        offset_sign = 1.0
        try:
            test_ow = fw.makeOffset2D(ae, join=0, fill=False, openResult=False)
            if test_ow and test_ow.Edges:
                test_bb = test_ow.BoundBox
                test_diag = test_bb.DiagonalLength
                fw_diag = bb_finish.DiagonalLength
                if test_diag < fw_diag:
                    # L'offset positif réduit la taille → il faut inverser
                    offset_sign = -1.0
                    Log.baptDebug(
                        "Offset positif va vers l'intérieur, "
                        "inversion du signe\n")
                else:
                    Log.baptDebug(
                        "Offset positif va vers l'extérieur (OK)\n")
        except Exception as e:
            Log.baptDebug(f"Test d'offset échoué: {e}\n")

        # ---- 1. Générer les offsets et les classifier --------------------
        # Chaque entrée : (wire, is_complete, [sub_wires si clippé])
        pass_data = []
        consecutive_empty = 0  # compteur d'offsets vides consécutifs

        for i in range(num_passes):
            offset = (i + 1) * ae * offset_sign

            try:
                ow = fw.makeOffset2D(offset, join=0,
                                     fill=False, openResult=False)
            except Exception as e:
                Log.baptDebug(f"Offset {i} (d={offset:.2f}) échoué: {e}\n")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    Log.baptDebug("3 offsets vides consécutifs, arrêt\n")
                    break
                continue

            if not ow or not ow.Edges:
                Log.baptDebug(f"Offset {i} vide\n")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    Log.baptDebug("3 offsets vides consécutifs, arrêt\n")
                    break
                continue

            offset_wire = ow.Wires[0] if ow.Wires else ow

            ow_bb = offset_wire.BoundBox
            Log.baptDebug(
                f"Offset {i} (d={offset:.2f}): BB X[{ow_bb.XMin:.2f}, "
                f"{ow_bb.XMax:.2f}] Y[{ow_bb.YMin:.2f}, {ow_bb.YMax:.2f}] "
                f"Edges={len(offset_wire.Edges)}\n")

            # NE PAS appliquer _ensure_wire_direction avant le clipping
            # car les edges reversées cassent edge.Curve.toShape(p1, p2).
            # La direction sera appliquée après dans l'étape 3.

            # Classifier en clippant directement (robuste pour arcs/cercles)
            clipped = self._clip_wire_to_stock(offset_wire, bb, margin)

            if not clipped:
                # Rien dans le stock
                Log.baptDebug(
                    f"Offset {i} (d={offset:.2f}): hors stock\n")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    Log.baptDebug("3 offsets vides consécutifs, arrêt\n")
                    break
                continue

            consecutive_empty = 0

            # Vérifier si le wire est entièrement dans le stock
            # en comparant la longueur clippée vs originale
            clipped_length = sum(w.Length for w in clipped)
            is_complete = (abs(clipped_length - offset_wire.Length)
                           < margin * 10)

            if is_complete:
                pass_data.append((offset_wire, True, [offset_wire]))
                Log.baptDebug(
                    f"Offset {i} (d={offset:.2f}): complet (dans stock)\n")
            else:
                pass_data.append((offset_wire, False, clipped))
                Log.baptDebug(
                    f"Offset {i} (d={offset:.2f}): "
                    f"clippé en {len(clipped)} segment(s)\n")

        Log.baptDebug(f"Passes générées: {len(pass_data)}\n")

        if not pass_data:
            return []

        # ---- 2. Inverser l'ordre (extérieur → intérieur) + contour fini --
        pass_data.reverse()
        # Le finish wire n'est pas clippé → on peut appliquer la direction ici
        fw_directed = self._ensure_wire_direction(fw, want_ccw)
        pass_data.append((fw_directed, True, [fw_directed]))

        # ---- 3. Construire le parcours avec transitions ------------------
        path = []
        # Stocker les infos pour le G-code
        self._pass_transitions = []  # liste de 'perp' ou 'z_retract'

        prev_wire = None
        prev_end = None

        for pass_idx, (orig_wire, is_complete, sub_wires) in enumerate(pass_data):

            if is_complete:
                # Appliquer la direction APRÈS clipping (ou directement
                # si le wire est complet et non clippé)
                wire = self._ensure_wire_direction(sub_wires[0], want_ccw)

                # Transition perpendiculaire depuis la passe précédente
                if prev_end is not None:
                    # Chercher le point le plus proche sur ce wire
                    nearest_pt = self._nearest_point_on_wire(wire, prev_end)
                    if nearest_pt is not None:
                        # Réorganiser le wire pour démarrer au point le plus proche
                        try:
                            wire = shiftWire(wire, nearest_pt)
                        except Exception as e:
                            Log.baptDebug(
                                f"shiftWire échoué passe {pass_idx}: {e}\n")

                        # Transition perpendiculaire (ligne courte)
                        d = (prev_end - nearest_pt).Length
                        if d > 0.01:
                            path.append(Part.makeLine(prev_end, nearest_pt))
                            self._pass_transitions.append('perp')

                # Ajouter le wire complet
                path.append(wire)

                # Déterminer le point de fin du wire
                # Après _ensure_wire_direction, Edges[0].Vertexes[0]
                # est le début du wire
                wire_start = self._wire_start_point(wire)
                wire_end = self._wire_end_point(wire)
                is_closed = (wire_start - wire_end).Length < 0.01
                prev_end = wire_start if is_closed else wire_end
                prev_wire = wire

                Log.baptDebug(
                    f"Passe {pass_idx}: complet, L={wire.Length:.1f}\n")

            else:
                # Déterminer si les segments clippés doivent être inversés
                # pour correspondre à la direction d'usinage voulue
                needs_reverse = False
                if orig_wire.isClosed():
                    is_ccw = self._is_ccw(orig_wire)
                    needs_reverse = (is_ccw != want_ccw)

                effective_wires = []
                for seg_wire in sub_wires:
                    if needs_reverse:
                        try:
                            rev_edges = [e.reversed()
                                         for e in reversed(seg_wire.Edges)]
                            seg_wire = Part.Wire(rev_edges)
                        except Exception:
                            pass
                    effective_wires.append(seg_wire)

                if needs_reverse:
                    effective_wires.reverse()

                # Passe clippée : segments disjoints avec Z retract entre eux
                for seg_idx, seg_wire in enumerate(effective_wires):
                    seg_start = self._wire_start_point(seg_wire)

                    # Marquer un dégagement Z avant ce segment
                    if prev_end is not None:
                        d = (prev_end - seg_start).Length
                        if d > 0.01:
                            self._pass_transitions.append('z_retract')

                    path.append(seg_wire)

                    prev_end = self._wire_end_point(seg_wire)

                prev_wire = None

                Log.baptDebug(
                    f"Passe {pass_idx}: clippé, "
                    f"{len(effective_wires)} segment(s)\n")

        return path

    def _clip_wire_to_stock(self, wire, bb, margin):
        """
        Découpe un wire en ne gardant que les portions à l'intérieur
        de la bounding box du stock.
        Les edges qui traversent la frontière sont coupées aux points
        d'intersection exacts.
        Retourne une liste de Part.Wire (segments continus à l'intérieur).
        """
        tol = 1e-6

        def point_inside(pt):
            return (bb.XMin - margin <= pt.x <= bb.XMax + margin
                    and bb.YMin - margin <= pt.y <= bb.YMax + margin)

        def find_intersection_params(edge):
            """Trouve les paramètres où l'edge croise les frontières du stock."""
            params = []
            fp = edge.FirstParameter
            lp = edge.LastParameter
            curve = edge.Curve
            boundaries_x = [bb.XMin, bb.XMax]
            boundaries_y = [bb.YMin, bb.YMax]

            if curve.TypeId == 'Part::GeomLine':
                p1 = edge.valueAt(fp)
                p2 = edge.valueAt(lp)
                dx = p2.x - p1.x
                dy = p2.y - p1.y

                for val in boundaries_x:
                    if abs(dx) > tol:
                        t = (val - p1.x) / dx
                        if tol < t < 1.0 - tol:
                            param = fp + t * (lp - fp)
                            params.append(param)

                for val in boundaries_y:
                    if abs(dy) > tol:
                        t = (val - p1.y) / dy
                        if tol < t < 1.0 - tol:
                            param = fp + t * (lp - fp)
                            params.append(param)

            elif curve.TypeId == 'Part::GeomCircle':
                center = curve.Center
                radius = curve.Radius

                for val in boundaries_x:
                    d = val - center.x
                    if abs(d) < radius - tol:
                        sq = max(0, radius ** 2 - d ** 2)
                        dy_val = math.sqrt(sq)
                        for y in [center.y + dy_val, center.y - dy_val]:
                            pt = App.Vector(val, y, 0)
                            try:
                                p = curve.parameter(pt)
                                # Ajuster p dans [fp, lp] pour les arcs
                                while p < fp - tol:
                                    p += 2 * math.pi
                                while p > lp + tol:
                                    p -= 2 * math.pi
                                if fp + tol < p < lp - tol:
                                    params.append(p)
                            except Exception:
                                pass

                for val in boundaries_y:
                    d = val - center.y
                    if abs(d) < radius - tol:
                        sq = max(0, radius ** 2 - d ** 2)
                        dx_val = math.sqrt(sq)
                        for x in [center.x + dx_val, center.x - dx_val]:
                            pt = App.Vector(x, val, 0)
                            try:
                                p = curve.parameter(pt)
                                while p < fp - tol:
                                    p += 2 * math.pi
                                while p > lp + tol:
                                    p -= 2 * math.pi
                                if fp + tol < p < lp - tol:
                                    params.append(p)
                            except Exception:
                                pass

            else:
                # Fallback pour les autres types de courbe : bisection
                N = 50
                prev_inside = point_inside(edge.valueAt(fp))
                for j in range(1, N + 1):
                    t = fp + (lp - fp) * j / N
                    curr_inside = point_inside(edge.valueAt(t))
                    if curr_inside != prev_inside:
                        lo = fp + (lp - fp) * (j - 1) / N
                        hi = t
                        for _ in range(50):
                            mid = (lo + hi) / 2
                            if point_inside(edge.valueAt(mid)) == prev_inside:
                                lo = mid
                            else:
                                hi = mid
                        params.append((lo + hi) / 2)
                    prev_inside = curr_inside

            # Trier et dédupliquer
            params.sort()
            unique = []
            for p in params:
                if not unique or abs(p - unique[-1]) > tol * 10:
                    unique.append(p)
            return unique

        # Traiter chaque edge : couper aux frontières et garder les parties intérieures
        all_inside_edges = []

        for edge_idx, edge in enumerate(wire.Edges):
            fp = edge.FirstParameter
            lp = edge.LastParameter
            start_pt = edge.Vertexes[0].Point
            end_pt = edge.Vertexes[-1].Point
            params = find_intersection_params(edge)

            Log.baptDebug(
                f"  Edge {edge_idx}: {edge.Curve.TypeId} "
                f"start=({start_pt.x:.2f},{start_pt.y:.2f}) "
                f"end=({end_pt.x:.2f},{end_pt.y:.2f}) "
                f"params=[{fp:.4f},{lp:.4f}] "
                f"intersections={len(params)}\n")

            if not params:
                # Pas d'intersection : tester le milieu
                mid_pt = edge.valueAt((fp + lp) / 2.0)
                inside = point_inside(mid_pt)
                Log.baptDebug(
                    f"    Pas d'intersection, milieu=({mid_pt.x:.2f},"
                    f"{mid_pt.y:.2f}), inside={inside}\n")
                if inside:
                    all_inside_edges.append(edge)
            else:
                # Diviser l'edge aux paramètres d'intersection
                cut_params = [fp] + params + [lp]
                for k in range(len(cut_params) - 1):
                    p1 = cut_params[k]
                    p2 = cut_params[k + 1]
                    if p2 - p1 < tol:
                        continue
                    mid_pt = edge.valueAt((p1 + p2) / 2.0)
                    if point_inside(mid_pt):
                        try:
                            sub_edge = edge.Curve.toShape(p1, p2)
                            all_inside_edges.append(sub_edge)
                        except Exception as e:
                            Log.baptDebug(
                                f"Clip sub-edge échoué: {e}\n")

        if not all_inside_edges:
            Log.baptDebug(f"  Clip result: aucune edge à l'intérieur\n")
            return []

        Log.baptDebug(
            f"  Clip result: {len(all_inside_edges)} edge(s) à l'intérieur\n")

        # Regrouper les edges consécutives en wires continus
        # Vérifier toutes les combinaisons de vertices pour la connexion,
        # car les edges peuvent avoir une orientation quelconque.
        result = []
        current_edges = [all_inside_edges[0]]

        for i in range(1, len(all_inside_edges)):
            prev = current_edges[-1]
            curr = all_inside_edges[i]

            # Tester les 4 combinaisons de vertices pour la connexion
            dists = [
                prev.Vertexes[-1].Point.distanceToPoint(
                    curr.Vertexes[0].Point),
                prev.Vertexes[-1].Point.distanceToPoint(
                    curr.Vertexes[-1].Point),
                prev.Vertexes[0].Point.distanceToPoint(
                    curr.Vertexes[0].Point),
                prev.Vertexes[0].Point.distanceToPoint(
                    curr.Vertexes[-1].Point),
            ]

            if min(dists) < 0.1:
                current_edges.append(curr)
            else:
                try:
                    result.append(Part.Wire(current_edges))
                except Exception:
                    pass
                current_edges = [curr]

        if current_edges:
            try:
                result.append(Part.Wire(current_edges))
            except Exception:
                pass

        return result

    def _wire_start_point(self, wire):
        """Retourne le point de départ du wire en tenant compte
        de la connectivité entre edges (pas seulement Vertexes[0])."""
        edges = wire.Edges
        if len(edges) == 1:
            return edges[0].Vertexes[0].Point
        # Déterminer quelle extrémité de la 1ère edge connecte à la 2ème
        e0, e1 = edges[0], edges[1]
        d00 = e0.Vertexes[0].Point.distanceToPoint(e1.Vertexes[0].Point)
        d01 = e0.Vertexes[0].Point.distanceToPoint(e1.Vertexes[-1].Point)
        d10 = e0.Vertexes[-1].Point.distanceToPoint(e1.Vertexes[0].Point)
        d11 = e0.Vertexes[-1].Point.distanceToPoint(e1.Vertexes[-1].Point)
        # L'extrémité de e0 qui connecte à e1 est la FIN du wire pour e0
        # Donc le DÉBUT est l'autre extrémité
        if min(d10, d11) < min(d00, d01):
            # e0 se termine à Vertexes[-1] → début = Vertexes[0]
            return e0.Vertexes[0].Point
        else:
            # e0 se termine à Vertexes[0] → début = Vertexes[-1]
            return e0.Vertexes[-1].Point

    def _wire_end_point(self, wire):
        """Retourne le point de fin du wire en tenant compte
        de la connectivité entre edges."""
        edges = wire.Edges
        if len(edges) == 1:
            return edges[-1].Vertexes[-1].Point
        # Déterminer quelle extrémité de la dernière edge connecte à l'avant-dernière
        e_last = edges[-1]
        e_prev = edges[-2]
        d00 = e_last.Vertexes[0].Point.distanceToPoint(e_prev.Vertexes[0].Point)
        d01 = e_last.Vertexes[0].Point.distanceToPoint(e_prev.Vertexes[-1].Point)
        d10 = e_last.Vertexes[-1].Point.distanceToPoint(e_prev.Vertexes[0].Point)
        d11 = e_last.Vertexes[-1].Point.distanceToPoint(e_prev.Vertexes[-1].Point)
        # L'extrémité de e_last qui connecte à e_prev est le DÉBUT dans le wire
        # Donc la FIN est l'autre extrémité
        if min(d00, d01) < min(d10, d11):
            # e_last commence à Vertexes[0] → fin = Vertexes[-1]
            return e_last.Vertexes[-1].Point
        else:
            # e_last commence à Vertexes[-1] → fin = Vertexes[0]
            return e_last.Vertexes[0].Point

    def _nearest_point_on_wire(self, wire, point):
        """
        Trouve le point le plus proche sur un wire depuis un point donné.
        Retourne le App.Vector le plus proche ou None.
        """
        best_pt = None
        best_dist = float('inf')

        for edge in wire.Edges:
            try:
                dist, pts, _ = edge.distToShape(Part.Vertex(point))
                if dist < best_dist:
                    best_dist = dist
                    best_pt = pts[0][0]  # Premier point de la paire
            except Exception:
                continue

        return best_pt

    def _is_ccw(self, wire):
        """Vérifie si un wire fermé est dans le sens anti-horaire (CCW)
        en utilisant la formule du lacet (shoelace)."""
        pts = [v.Point for v in wire.Vertexes]
        area = 0.0
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            area += pts[i].x * pts[j].y
            area -= pts[j].x * pts[i].y
        return area > 0

    def _ensure_wire_direction(self, wire, want_ccw):
        """S'assure que le wire fermé est dans le sens voulu
        (CCW si want_ccw=True, CW sinon).
        Pour un wire ouvert, retourne le wire inchangé."""
        if not wire.isClosed():
            return wire
        is_ccw = self._is_ccw(wire)
        if is_ccw == want_ccw:
            return wire
        try:
            reversed_edges = [e.reversed() for e in reversed(wire.Edges)]
            new_wire = Part.Wire(reversed_edges)
            direction_str = 'CCW' if want_ccw else 'CW'
            Log.baptDebug(f'Wire inversé pour {direction_str}\n')
            return new_wire
        except Exception as e:
            App.Console.PrintWarning(
                f'Inversion de sens échouée: {e}\n')
            return wire


class ViewProviderAdaptiveOp(BaseOp.baseOpViewProviderProxy):
    def __init__(self, vobj):
        super().__init__(vobj)
        self.Object = vobj.Object
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object
        return super().attach(vobj)

    def getIcon(self):
        if not self.Object.Active:
            return BaptUtilities.getIconPath("operation_disabled.svg")
        return BaptUtilities.getIconPath("AdaptativeOp.svg")

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def setEdit(self, vobj, mode=0):
        """Ouvre le panneau de tâches pour l'opération adaptive."""
        try:
            tp = AdaptativeOpTaskPanel(vobj.Object)
            Gui.Control.showDialog(tp)
        except Exception as e:
            App.Console.PrintError(f"AdaptativeOp setEdit: {e}\n")
            return False
        return True

    def doubleClicked(self, vobj):
        self.setEdit(vobj)
        return True


class AdaptativeOpTaskPanel():
    """Panneau de tâches pour l'opération de fraisage Adaptatif."""

    def __init__(self, obj):

        try:
            self.obj = obj
            self.ui1 = Gui.PySideUic.loadUi(
                BaptUtilities.getPanel("AdaptativeOp.ui"))
            self.uiTool = ToolTaskPanel(obj)
            self.form = [self.ui1, self.uiTool.getForm()]

            self.toolDiamSpin = BQuantitySpinBox(obj, "ToolDiameter", self.ui1.toolDiamSpin)
            self.stepDownSpin = BQuantitySpinBox(obj, "StepDown", self.ui1.stepDownSpin)
            self.aeSpin = BQuantitySpinBox(obj, "EngagementRadial", self.ui1.aeSpin)
            self.surepAxialeSpin = BQuantitySpinBox(obj, "SurepAxiale", self.ui1.surepAxialeSpin)
            self.surepRadialeSpin = BQuantitySpinBox(obj, "SurepRadiale", self.ui1.surepRadialeSpin)

            for d in Direction:
                self.ui1.directionCombo.addItem(d)
            self.ui1.directionCombo.setCurrentText(
                obj.Direction if hasattr(obj, 'Direction') else Direction[0])

            for p in Plongee:
                self.ui1.plungeCombo.addItem(p)
            self.ui1.plungeCombo.setCurrentText(
                obj.PlungeType if hasattr(obj, 'PlungeType') else Plongee[0])

            # Connexions
            # self.ui1.toolDiamSpin.valueChanged.connect(self.updateObj)
            # self.ui1.stepDownSpin.valueChanged.connect(self.updateObj)
            # self.ui1.aeSpin.valueChanged.connect(self.updateObj)
            # self.ui1.surepAxialeSpin.valueChanged.connect(self.updateObj)
            # self.ui1.surepRadialeSpin.valueChanged.connect(self.updateObj)
            # self.ui1.directionCombo.currentTextChanged.connect(self.updateObj)
            # self.ui1.plungeCombo.currentTextChanged.connect(self.updateObj)

        except Exception as e:
            App.Console.PrintError(f"AdaptativeOpTaskPanel init: {e}\n")
            import sys
            exc_type, exc_obj, exc_tb = sys.exc_info()
            App.Console.PrintMessage(f'ligne {exc_tb.tb_lineno}\n')

    def updateObj(self):
        try:
            self.obj.ToolDiameter = self.ui1.toolDiamSpin.value()
            self.obj.StepDown = self.ui1.stepDownSpin.value()
            self.obj.EngagementRadial = self.ui1.aeSpin.value()
            self.obj.SurepAxiale = self.ui1.surepAxialeSpin.value()
            self.obj.SurepRadiale = self.ui1.surepRadialeSpin.value()
            self.obj.Direction = self.ui1.directionCombo.currentText()
            self.obj.PlungeType = self.ui1.plungeCombo.currentText()
            self.obj.touch()
            App.ActiveDocument.recompute()
        except Exception as e:
            App.Console.PrintError(f"AdaptativeOp updateObj: {e}\n")


def createAdaptativeOperation(contour=None) -> Part.Feature:
    doc = App.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", "AdaptativeOperation")

    AdaptativeOp(obj)
    ViewProviderAdaptiveOp(obj.ViewObject)

    if contour:
        obj.Contour = contour

        pref = BaptPreferences.BaptPreferences()
        modeAjout = pref.getModeAjout()

        # 0 = ajouter à la géométrie comme enfant et au groupe opérations du projet CAM comme lien
        # 1 = ajouter à la géométrie comme enfant (pas conseillé)
        # 2 = ajouter au groupe opérations du projet CAM

        if modeAjout == 1 or modeAjout == 0:

            # Ajouter le contournage comme enfant de la géométrie du contour
            contour.addObject(obj)
            contour.Group.append(obj)

        if modeAjout == 2 or modeAjout == 0:
            camProject = BaptUtilities.find_cam_project(contour)
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

    if hasattr(obj, "ViewObject"):
        obj.ViewObject.Proxy.setEdit(obj.ViewObject)
    return obj
