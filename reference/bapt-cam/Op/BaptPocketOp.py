from collections import deque
import math
from BaptPath import GcodeEditorTaskPanel
import BaptPreferences
import FreeCAD as App
import FreeCADGui as Gui
from Op import BaseOp
from Op.PocketNode import noeud
import Part
from PySide import QtGui, QtCore
import sys
import traceback
import BaptUtilities
from Tool.ToolTaskPannel import ToolTaskPanel
from utils import BQuantitySpinBox, GcodeWriter
from utils import Log as Log
from utils.Contour import getFirstPoint, getLastPoint, shiftWire, edgeToGcode

if True:
    Log.setLevel(Log.Level.DEBUG, Log.thisModule())
else:
    Log.setLevel(Log.Level.INFO, Log.thisModule())

pocketFillMode = ["offset", "offset2", "zigzag", "spirale"]

Direction = ["Climb (Avalant)", "Conventional (opposition)"]

Plongee = ["Directe", "Helicoidale", "Rampante"]


class PocketOperation(BaseOp.baseOp):
    """
    Opération d'usinage de poche basée sur ContourGeometry.
    Génère un chemin d'usinage à partir du centre avec un facteur de recouvrement.
    """
    initialized = False
    Type = "PocketOperation"

    def __init__(self, obj):
        super().__init__(obj)
        self.initProperties(obj)
        obj.Proxy = self
        self.initialized = True
        Log.baptDebug("PocketOperation initialized.")

        Log.baptDebug(f"{isinstance(obj.Proxy, PocketOperation)}\n")

        # try:
        #     a = 1/0
        # except Exception as e:
        #     Log.baptDebug(f"PocketOperation init error: {e}\n")
        #     # exc_type, exc_obj, exc_tb = sys.exc_info()
        #     # Log.baptDebug(f'Line {exc_tb.tb_lineno}\n')

    def initProperties(self, obj):
        obj.addProperty("App::PropertyLink", "Contour", "Pocket", "ContourGeometry de la poche")
        obj.addProperty("App::PropertyFloat", "Overlap", "Pocket", "Facteur de recouvrement (0.1-0.9)").Overlap = 0.5
        obj.addProperty("App::PropertyFloat", "ToolDiameter", "Pocket", "Diamètre outil (mm)").ToolDiameter = 6.0
        obj.addProperty("App::PropertyFloat", "StepDown", "Pocket", "Profondeur de passe (mm)").StepDown = 2.0
        obj.addProperty("App::PropertyFloat", "SurepAxiale", "Pocket", "Surépaisseur axiale").SurepAxiale = 0.0

        obj.addProperty("App::PropertyFloat", "SurepRadiale", "Toolpath", "Surépaisseur radiale")
        obj.SurepRadiale = 0.0

        obj.addProperty("App::PropertyEnumeration", "FillMode", "Pocket", "Mode de remplissage").FillMode = pocketFillMode
        obj.FillMode = pocketFillMode[1]

        obj.addProperty("App::PropertyEnumeration", "PlungeType", "Pocket", "Type de plongée").PlungeType = Plongee
        obj.PlungeType = Plongee[0]

        obj.addProperty("Part::PropertyPartShape", "Path", "Pocket", "Chemin d'usinage généré")

        obj.addProperty("App::PropertyInteger", "maxGeneration", "Pocket", "Nombre maximum de générations d'offset").maxGeneration = 2

        obj.addProperty("App::PropertyBool", "useMiddleofFirstEdge", "Pocket", "Utiliser le milieu de la première arête").useMiddleofFirstEdge = False
        obj.addProperty("App::PropertyBool", "debugMode", "General", "Activer le mode debug").debugMode = False

        obj.addProperty("App::PropertyEnumeration", "Direction", "Pocket", "Direction d'usinage").Direction = Direction
        obj.Direction = Direction[0]

        self.installToolProp(obj)

    def onChanged(self, obj, prop):
        # Log.baptDebug(f"{prop}")
        if prop in ["Overlap", "ToolDiameter", "StepDown", "FillMode", "Contour", "maxGeneration", "useMiddleofFirstEdge", "SurepAxiale", "SurepRadiale", "debugMode", "Direction", "PlungeType"]:
            self.execute(obj)

    def is_shape_valid(self, shape: Part.Shape):
        # Vérifie que la shape est utilisable pour le pocketing
        if not shape:
            return False
        if not hasattr(shape, 'BoundBox') or not shape.BoundBox:
            App.Console.PrintError("PocketOperation: pas de boundBox.\n")
            return False
        if hasattr(shape, 'Wires') and shape.Wires:
            for wire in shape.Wires:
                if wire.isClosed():
                    return True
            return False
        return False

    def collectEdges(self, obj) -> list[Part.Edge]:
        # Collecter toutes les arêtes sélectionnées
        edges = []
        for sub in obj.Edges:
            obj_ref = sub[0]  # L'objet référencé
            sub_names = sub[1]  # Les noms des sous-éléments (arêtes)

            for sub_name in sub_names:
                if "Edge" in sub_name:
                    try:
                        edge = obj_ref.Shape.getElement(sub_name)
                        edges.append(edge)
                        # App.Console.PrintMessage(f"Arête ajoutée: {sub_name} de {obj_ref.Name}\n")
                    except Exception as e:
                        App.Console.PrintError(f"Execute : Erreur lors de la récupération de l'arête {sub_name}: {str(e)}\n")
                        exc_type, exc_obj, exc_tb = sys.exc_info()
                        App.Console.PrintMessage(f'{exc_tb.tb_lineno}\n')
        # App.Console.PrintMessage(f'nb collecté {len(edges)}\n')
        return edges

    def execute(self, obj):
        if App.ActiveDocument.Restoring:
            return
        # Chercher le parent ContourGeometry dans l'arborescence
        # if not self.initialized:
        #     Log.baptDebug("execute ignored")
        #     return
        # Log.baptDebug("execute")
        try:
            # parent = None
            # for p in obj.InList:
            #     if hasattr(p, "Proxy") and getattr(p.Proxy, "Type", "") == "ContourGeometry":
            #         parent = p
            #         break

            # if not parent or not hasattr(parent, "Shape"):
            #     App.Console.PrintError("PocketOperation: Aucun parent ContourGeometry valide trouvé.\n")
            #     obj.Path = Part.Shape()
            #     return

            # shape = parent.Shape

            shape = obj.Contour.Shape if obj.Contour and hasattr(obj.Contour, "Shape") else None

            if not shape:
                App.Console.PrintError("PocketOperation: Aucun parent ContourGeometry valide trouvé.\n")
                obj.Shape = None
                return

            if not self.is_shape_valid(shape):
                App.Console.PrintError("PocketOperation: Shape du parent ContourGeometry invalide ou non fermée.\n")
                obj.Path = Part.Shape()
                return

            tool_diam = obj.ToolDiameter
            overlap = obj.Overlap

            gcodeWriter = GcodeWriter.GcodeWriter()

            # spheres pour marquer le debut du contour
            spheres = []

            # Génération du chemin selon le mode choisi
            if hasattr(obj, 'FillMode') and obj.FillMode == "zigzag":
                path = self.generate_zigzag_path(shape, tool_diam, overlap)

            elif hasattr(obj, 'FillMode') and obj.FillMode == "offset":
                edges = self.collectEdges(obj.Contour)

                path = self.generate_offset_path(edges, tool_diam, overlap, obj.maxGeneration)

                if obj.debugMode:
                    for i in range(len(path)):
                        for j in range(len(path[i].Wires)):
                            edge = path[i].Wires[j].Edges[0]
                            # recupere le premier point
                            start_point = edge.Vertexes[0].Point
                            end_point = edge.Vertexes[-1].Point
                            u1, v1 = edge.ParameterRange
                            mid_param = (u1 + v1)/2
                            mid_point = edge.valueAt(mid_param)
                            # ajoute une sphere au millieu
                            # App.Console.PrintMessage(f"start {start_point}, end {end_point} mid {mid_point}\n")
                            sphere = Part.makeSphere(tool_diam/4, mid_point)
                            spheres.append(sphere)

            elif hasattr(obj, 'FillMode') and obj.FillMode == "offset2":
                edges = self.collectEdges(obj.Contour)

                path = []
                nodes = self.generate_offset_path2(edges, tool_diam, overlap, obj.maxGeneration, obj.SurepRadiale)

                if not nodes:
                    App.Console.PrintError("Aucun offset généré\n")
                    obj.Shape = Part.Shape()
                    return

                offset_dist = tool_diam * (1 - overlap)

                # Optionnel : décaler la feuille la plus profonde
                if obj.useMiddleofFirstEdge:
                    for root_node in nodes:
                        _, _, levels_tmp = buildParentDepthLevel(root_node)
                        md = max(levels_tmp.keys())
                        if md in levels_tmp and levels_tmp[md]:
                            dn = levels_tmp[md][0]
                            e0 = dn.wires.Edges[0]
                            u1, v1 = e0.ParameterRange
                            dn.shiftWire(e0.valueAt((u1 + v1) / 2))

                # ===== ALGORITHME D'ÉVIDEMENT DE POCHE =====
                # Principe : partir de la feuille la plus profonde (centre),
                # remonter en usinant chaque nœud, et interrompre un nœud
                # dès qu'une transition perpendiculaire vers un enfant non visité
                # est possible. Après avoir traité le sous-arbre enfant, revenir
                # et finir le nœud interrompu.
                visited = set()

                # S'assurer que le sens de rotation correspond au paramètre Direction
                # Climb (Avalant) = CCW (sens anti-horaire, fraisage en avalant)
                # Conventional (opposition) = CW (sens horaire, fraisage en opposition)
                want_ccw = (obj.Direction == Direction[0])  # Direction[0] = "Climb (Avalant)"
                for root_node in nodes:
                    self._ensure_direction(root_node, want_ccw)

                for root_node in nodes:
                    parent_map = self._build_parent_map(root_node)
                    deepest = self._find_deepest_leaf(root_node)
                    chain = self._get_chain_to_root(deepest, parent_map)

                    App.Console.PrintMessage(
                        f'Chaîne de {len(chain)} nœuds, profondeur max={deepest.depth}\n')

                    for i, node in enumerate(chain):
                        if id(node) in visited:
                            continue

                        # Usiner le nœud (avec interruptions pour ses enfants non visités)
                        self._machine_node(obj, node, offset_dist, visited, path)

                        # Transition perpendiculaire vers le nœud suivant (parent)
                        if i + 1 < len(chain):
                            next_node = chain[i + 1]
                            if id(next_node) not in visited:
                                tp = self._find_climb_transition(
                                    node.wires, next_node.wires, offset_dist)
                                if tp:
                                    path.append(Part.makeLine(
                                        tp['point_on_source'], tp['point_on_target']))
                                    next_node.shiftWire(tp['point_on_target'])
                                    Log.baptDebug(
                                        f'Climb {node} → {next_node}\n')
                                else:
                                    App.Console.PrintWarning(
                                        f'Pas de transition climb {node} → {next_node}\n')

                App.Console.PrintMessage(
                    f'Parcours terminé : {len(path)} segments, '
                    f'{len(visited)} nœuds visités\n')

                # Paramètres d'usinage
                step_down = abs(obj.StepDown)
                final_depth = obj.Contour.depth if hasattr(obj.Contour, "depth") else -5.0
                final_depth += obj.SurepAxiale
                start_depth = obj.Contour.Zref if hasattr(obj.Contour, "Zref") else 0.0
                feed_rate = float(obj.FeedRate.getValueAs('mm/min')) if hasattr(obj, 'FeedRate') else 1000.0
                safe_z = start_depth + 5.0

                total_depth = abs(final_depth - start_depth)
                num_passes = math.ceil(total_depth / step_down)

                Log.baptDebug(
                    f"Génération G-code: {num_passes} passes, "
                    f"step={step_down}, final={final_depth}\n")

                # Trouver le premier point du parcours
                if path:
                    first_edge = path[0].Edges[0]
                    start_pt = first_edge.Vertexes[0].Point
                else:
                    start_pt = App.Vector(0, 0, 0)

                for pass_num in range(num_passes):
                    if pass_num == num_passes - 1:
                        current_z = final_depth
                    else:
                        current_z = start_depth - (pass_num + 1) * step_down

                    gcodeWriter.comment(f"Passe {pass_num + 1}/{num_passes} à Z={current_z:.3f}")

                    # Positionnement rapide et plongée
                    gcodeWriter.linearMove({'X': start_pt.x, 'Y': start_pt.y}, rapid=True)
                    gcodeWriter.linearMove({'Z': safe_z}, rapid=True)
                    if obj.PlungeType == "Directe":
                        gcodeWriter.linearMove({'Z': current_z}, feed=feed_rate, rapid=False)
                    elif obj.PlungeType == "Helicoidale":
                        dz = safe_z - current_z
                        diam = tool_diam * 1.5
                        nbtour = math.ceil(dz / 1.0)  # 1mm par tour
                        prisePasse = (dz/nbtour) / 2
                        gcodeWriter.linearMove({'X': start_pt.x + diam/2, 'Y': start_pt.y, 'Z': safe_z}, feed=feed_rate)
                        Log.baptDebug(f"Plongée hélicoïdale: {nbtour} tours, prise de passe {prisePasse:.3f}\n")
                        Log.baptDebug(f"safe_z {safe_z}, current_z {current_z}\n")
                        for i in range(nbtour):
                            gcodeWriter.arcMove({'X': start_pt.x - diam/2, 'Y': start_pt.y, 'Z': safe_z - ((i+1)*prisePasse + i * prisePasse), 'CCW': True, 'I': -diam/2, 'J': 0}, feed=feed_rate)
                            gcodeWriter.arcMove({'X': start_pt.x + diam/2, 'Y': start_pt.y, 'Z': safe_z - ((i+1)*(prisePasse * 2)), 'CCW': True, 'I': diam/2, 'J': 0}, feed=feed_rate)
                        gcodeWriter.linearMove({'X': start_pt.x, 'Y': start_pt.y, 'Z': current_z}, feed=feed_rate)
                    # Le parcours est continu : pas de repositionnement rapide
                    # On détermine bonSens par arête en suivant la position courante
                    current_pos = App.Vector(start_pt)
                    for segment in path:
                        for edge in segment.Edges:
                            # Déterminer le sens de parcours de l'arête
                            d0 = (edge.Vertexes[0].Point - current_pos).Length
                            d1 = (edge.Vertexes[-1].Point - current_pos).Length
                            bonSens = d0 <= d1
                            edge_gcode = edgeToGcode(
                                edge, bonSens=bonSens,
                                current_z=current_z,
                                rapid=False,
                                feed_rate=feed_rate, gcodeWriter=gcodeWriter)

                            # Mettre à jour la position courante
                            if bonSens:
                                current_pos = edge.Vertexes[-1].Point
                            else:
                                current_pos = edge.Vertexes[0].Point

                    gcodeWriter.linearMove({'Z': safe_z}, rapid=True)

                obj.Gcode = "\n".join(gcodeWriter.lines)
                Log.baptDebug(f"G-code généré: {len(obj.Gcode)} caractères\n")

                # for n in nodes:
                #     wires = n.getWires()
                #     path.extend(wires)
                if obj.debugMode:
                    for segment in path:
                        for edge in segment.Edges:
                            u1, v1 = edge.ParameterRange
                            mid_param = u1 + (v1 - u1) / 4
                            mid_point = edge.valueAt(mid_param)
                            sphere = Part.makeSphere(tool_diam / 4, mid_point)
                            spheres.append(sphere)
            else:
                path = self.generate_spiral_path(shape, tool_diam, overlap)
            # obj.Path = path if path else Part.Shape()

            if path is None:
                App.Console.PrintError("PocketOperation: Échec de la génération du chemin d'usinage.\n")
                obj.Shape = Part.Shape()
                return
            a = path
            for s in spheres:
                a.append(s)
            compound = Part.makeCompound(a)
            # Part.show(compound)
            obj.Shape = compound
        except Exception as e:
            App.Console.PrintError(f"Erreur offset: {e}\n")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_number = exc_traceback.tb_lineno
            App.Console.PrintError(f"Erreur à la ligne {line_number}\n")

    def generate_zigzag_path(self, shape, tool_diam, overlap):
        # On suppose une poche plane, contour fermé
        if not shape or not shape.BoundBox:
            return None
        bbox = shape.BoundBox
        xmin, xmax = bbox.XMin, bbox.XMax
        ymin, ymax = bbox.YMin, bbox.YMax
        pas = tool_diam * (1 - overlap)
        lines = []
        y = ymin + tool_diam/2
        direction = 1
        while y <= ymax - tool_diam/2:
            # Cherche intersections entre la ligne y et la poche
            section = shape.slice(App.Vector(0, 0, 1), y)
            if section and hasattr(section, 'Edges'):
                for edge in section.Edges:
                    p1, p2 = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
                    if direction == 1:
                        lines.append(Part.makeLine(p1, p2))
                    else:
                        lines.append(Part.makeLine(p2, p1))
            y += pas
            direction *= -1
        if lines:
            return Part.Wire(lines)
        return None

    def offsetting(self, wires, offset_dist, maxGen, parentNode=None, generation=0):
        """Fonction récursive pour générer les offsets et construire l'arbre des offsets"""
        node: list[noeud] = []
        for wire in wires.Wires:
            try:
                o = wire.makeOffset2D(-offset_dist, join=0, fill=False, openResult=False)
                for j, w in enumerate(o.Wires):
                    n = noeud(generation, j, w)
                    node.append(n)
                    if parentNode is not None:
                        parentNode.addChild(n)
                    self.offsetting(w, offset_dist, maxGen, n, generation+1)
            except Exception as e:
                print(f"Offsetting generation {generation} échouée: {e}\n")
                pass

        return node

    def generate_offset_path2(self, shape: Part.Shape, tool_diam: float, overlap: float, maxGen: int, surepRadiale: float):
        # Génère un offset intérieur de la forme
        path_edges = []
        try:
            current = Part.Wire(shape)

            # offset_dist = tool_diam * (1 - overlap)
            offset_dist = tool_diam / 2 + surepRadiale
            # generation = 0

            nodes = self.offsetting(current, offset_dist, maxGen)

            # print de l'arbre
            for n in nodes:
                n.printTree()

            if False:
                deepest_nodes = findDeepestNodes(nodes)
                App.Console.PrintMessage(f"Deepest nodes: {len(deepest_nodes)}\n")
                App.Console.PrintMessage(f'Deepest {deepest_nodes[0]}\n')

                arbore_nodes = arbore(nodes)
                App.Console.PrintMessage(f"Arbore nodes: {len(arbore_nodes)}\n")
                for n in arbore_nodes:
                    App.Console.PrintMessage(f'Arbore {n}\n')

            # for n in nodes:
            #     wires = n.getWires()
            #     # for w in wires:
            #     path_edges.append(wires)

            # App.Console.PrintMessage(f"Offset généré: nb {len(path_edges)}\n")
            return nodes

        except Exception as e:
            App.Console.PrintError(f"Erreur offset gen: : {e}\n")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_number = exc_traceback.tb_lineno
            App.Console.PrintError(f"Erreur à la ligne {line_number}\n")
            return path_edges

    def generate_offset_path(self, shape, tool_diam, overlap, maxGen):
        # Génère un offset intérieur de la forme
        path_edges = []
        try:

            current = Part.Wire(shape)

            offset_dist = tool_diam * (1 - overlap)
            generation = 0
            while True:
                generation += 1
                offset = current.makeOffset2D(-offset_dist, join=0, fill=False, openResult=False)

                current = offset

                # on arrete si l'offset n'est plus fermé ou trop petit
                if offset is None:
                    App.Console.PrintMessage("Offset nul, fin de génération.\n")
                    break

                if not offset or not hasattr(offset, 'Wires') or not offset.Wires:
                    App.Console.Warning("PocketOperation: Offset invalide ou vide.\n")
                    break
                    return None

                path_edges.append(offset)

                if generation >= maxGen:
                    break

            App.Console.PrintMessage(f"Offset généré: nb {len(path_edges)}\n")
            return path_edges

        except Exception as e:
            # import json
            # j = json.loads(e)
            # if  j['sErrMsg'] == "makeOffset2D: offset result has no wires.":
            #     App.Console.PrintMessage(f"Erreur offset gen: {generation}: {e.sErrMsg}\n")
            #     return path_edges
            App.Console.PrintError(f"Erreur offset gen: {generation}: {e}\n")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_number = exc_traceback.tb_lineno
            App.Console.PrintError(f"Erreur à la ligne {line_number}\n")
            return path_edges

    def generate_spiral_path(self, shape, tool_diam, overlap):
        # Génère une série d'offsets intérieurs, connecte chaque boucle à la suivante par le point le plus proche
        try:
            offset_dist = tool_diam * (1 - overlap)
            loops = []
            current = shape
            while True:
                # offset = current.makeOffset2D(-offset_dist, fill=False, join=0, openResult=True)

                face = Part.Face(current)
                offset = face.makeOffset(-offset_dist)

                # On arrête si l'offset n'est plus fermé ou trop petit
                if not offset or not hasattr(offset, 'Wires') or not offset.Wires:
                    break
                # Prend la plus grande wire (pour éviter les artefacts)
                main_wire = max(offset.Wires, key=lambda w: w.Length)
                if main_wire.Length < tool_diam:
                    break
                loops.append(main_wire)
                current = main_wire
            # On connecte les boucles entre elles
            if not loops:
                return None
            path_edges = []
            prev_wire = shape.Wires[0] if hasattr(shape, 'Wires') and shape.Wires else shape
            for wire in loops:
                # Trouver le point le plus proche entre la fin du wire précédent et le wire courant
                p_start = prev_wire.Vertexes[-1].Point
                min_dist = None
                min_vert = None
                for v in wire.Vertexes:
                    dist = (p_start - v.Point).Length
                    if min_dist is None or dist < min_dist:
                        min_dist = dist
                        min_vert = v.Point
                # Décale le wire courant pour commencer à ce point
                reordered = wire.copy()
                reordered.rotate(reordered.CenterOfMass, App.Vector(0, 0, 1), 0)  # dummy to force copy
                reordered = reordered
                # Ajoute une liaison
                path_edges.append(Part.makeLine(p_start, min_vert))
                # Ajoute le wire courant
                path_edges.extend(reordered.Edges)
                prev_wire = wire
            # Retourne un wire unique
            return Part.Wire(path_edges)
        except Exception as e:
            App.Console.PrintError(f"Erreur spirale: {e}\n")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_number = exc_traceback.tb_lineno
            App.Console.PrintError(f"Erreur à la ligne {line_number}\n")
            return None

    # ===================================================================
    #  ALGORITHME D'ÉVIDEMENT DE POCHE - Méthodes utilitaires
    # ===================================================================

    @staticmethod
    def _build_parent_map(root_node: noeud) -> dict:
        """Construit un dictionnaire noeud → parent pour tout l'arbre."""
        parent_map = {root_node: None}
        queue = deque([root_node])
        while queue:
            node = queue.popleft()
            for child in node.children:
                parent_map[child] = node
                queue.append(child)
        return parent_map

    @staticmethod
    def _find_deepest_leaf(root_node: noeud) -> noeud:
        """Trouve la feuille la plus profonde (premier DFS)."""
        best = root_node
        best_depth = 0

        def dfs(node, depth):
            nonlocal best, best_depth
            if depth > best_depth:
                best = node
                best_depth = depth
            for child in node.children:
                dfs(child, depth + 1)

        dfs(root_node, 0)
        return best

    @staticmethod
    def _get_chain_to_root(node: noeud, parent_map: dict) -> list[noeud]:
        """Retourne la liste [node, parent, grandparent, ..., root]."""
        chain = []
        current = node
        while current is not None:
            chain.append(current)
            current = parent_map.get(current)
        return chain

    def _find_perp_intersection(self, source_point: App.Vector,
                                source_edge: Part.Edge, source_param: float,
                                target_wire: Part.Wire, offset_dist: float):
        """
        Depuis un point sur une arête source, calcule la perpendiculaire
        et cherche l'intersection avec le wire cible à ~offset_dist.
        Retourne le point d'intersection (App.Vector) ou None.
        """
        tangent = source_edge.tangentAt(source_param)
        tangent_xy = App.Vector(tangent.x, tangent.y, 0)
        if tangent_xy.Length < 1e-10:
            return None
        tangent_xy.normalize()

        normal = tangent_xy.cross(App.Vector(0, 0, 1))
        normal.normalize()

        best_point = None
        best_diff = float('inf')

        for direction in (normal, normal * -1):
            ray = Part.Line(source_point,
                            source_point + direction * offset_dist * 3)

            for target_edge in target_wire.Edges:
                try:
                    intersections = ray.intersect(target_edge.Curve)
                except Exception:
                    continue

                for p in intersections:
                    target_pt = App.Vector(p.X, p.Y, p.Z)
                    d = (target_pt - source_point).Length
                    diff = abs(d - offset_dist)

                    if diff < best_diff and diff < offset_dist * 0.2:
                        # Vérifier que le point est bien SUR l'arête cible
                        try:
                            dist_check = target_edge.distToShape(
                                Part.Vertex(target_pt))[0]
                            if dist_check < 1e-2:
                                best_point = target_pt
                                best_diff = diff
                        except Exception:
                            pass

        return best_point

    def _find_climb_transition(self, child_wire: Part.Wire,
                               parent_wire: Part.Wire,
                               offset_dist: float) -> dict | None:
        """
        Transition de remontée : depuis le point de départ de l'enfant
        (fin du tour = début du wire fermé) vers le parent.
        Retourne {'point_on_source', 'point_on_target'} ou None.
        """
        edge = child_wire.Edges[0]
        u1, u2 = edge.ParameterRange

        if len(child_wire.Edges) > 1:
            idx = getFirstPoint(child_wire.Edges)
            start_point = edge.Vertexes[idx].Point
            param = u1 if idx == 0 else u2
        else:
            start_point = edge.Vertexes[0].Point
            param = u1

        target_pt = self._find_perp_intersection(
            start_point, edge, param, parent_wire, offset_dist)

        if target_pt:
            return {
                'point_on_source': start_point,
                'point_on_target': target_pt,
            }
        return None

    def _find_interrupt_transition(self, parent_wire: Part.Wire,
                                   child_wire: Part.Wire,
                                   offset_dist: float) -> dict | None:
        """
        Transition d'interruption : parcourt les arêtes du parent et
        retourne le PREMIER point depuis lequel une perpendiculaire
        intersecte le wire enfant à ~offset_dist.
        Retourne {'edge_idx', 'param', 'point_on_source', 'point_on_target'}
        ou None.
        """
        for edge_idx, edge in enumerate(parent_wire.Edges):
            u1, u2 = edge.ParameterRange
            # Echantillonner le long de l'arête
            samples = max(5, int(edge.Length / (offset_dist * 0.3)))

            for s in range(samples + 1):
                param = u1 + (u2 - u1) * s / samples
                source_pt = edge.valueAt(param)

                target_pt = self._find_perp_intersection(
                    source_pt, edge, param, child_wire, offset_dist)

                if target_pt:
                    return {
                        'edge_idx': edge_idx,
                        'param': param,
                        'point_on_source': source_pt,
                        'point_on_target': target_pt,
                    }

        return None

    def _ensure_direction(self, node: noeud, want_ccw: bool):
        """S'assure que le wire du nœud et de tous ses enfants est dans le sens
        voulu : CCW si want_ccw=True (Climb/Avalant), CW sinon (Conventional).
        Inverse l'ordre des arêtes ET l'orientation de chaque arête."""
        is_ccw = node.isCCW()
        needs_flip = (want_ccw and not is_ccw) or (not want_ccw and is_ccw)
        if needs_flip:
            try:
                # Inverser l'ordre des arêtes et l'orientation de chacune
                reversed_edges = [e.reversed() for e in reversed(list(node.wires.Edges))]
                node.wires = Part.Wire(reversed_edges)
                direction_str = 'CCW' if want_ccw else 'CW'
                Log.baptDebug(f'Wire inversé pour {direction_str} : {node}\n')
                # Vérification post-inversion
                if node.isCCW() != want_ccw:
                    App.Console.PrintWarning(
                        f'Sens incorrect après inversion pour {node}\n')
            except Exception as e:
                App.Console.PrintWarning(
                    f'Inversion de sens échouée pour {node}: {e}\n')
        for child in node.children:
            self._ensure_direction(child, want_ccw)

    def _machine_node(self, obj, node: noeud, offset_dist: float,
                      visited: set, path: list):
        """
        Usine un nœud. Si le nœud a des enfants non visités, le wire est
        interrompu à l'endroit où une transition perpendiculaire vers un
        enfant est possible. Le sous-arbre enfant est alors traité
        récursivement, puis le wire reprend là où il avait été interrompu.
        """
        visited.add(id(node))

        unvisited = [c for c in node.children if id(c) not in visited]

        # ------ Cas simple : pas d'enfant non visité → tour complet ------
        if not unvisited:
            path.append(node.wires)
            Log.baptDebug(f'Usinage complet : {node}\n')
            return

        # ------ Cas avec interruptions ------
        # Trouver les points d'interruption pour chaque enfant
        transitions = []
        for child in unvisited:
            tp = self._find_interrupt_transition(
                node.wires, child.wires, offset_dist)
            if tp:
                transitions.append((child, tp))
            else:
                App.Console.PrintWarning(
                    f'Pas de transition trouvée pour enfant {child}\n')

        if not transitions:
            # Aucune transition possible → tour complet quand même
            path.append(node.wires)
            Log.baptDebug(f'Usinage complet (pas de transitions) : {node}\n')
            return

        # Trier par position le long du wire (edge_idx, puis param)
        transitions.sort(key=lambda t: (t[1]['edge_idx'], t[1]['param']))

        Log.baptDebug(
            f'Usinage avec {len(transitions)} interruption(s) : {node}\n')

        # Parcourir le wire avec interruptions
        wire_edges = list(node.wires.Edges)
        collected_edges = []     # arêtes accumulées avant la prochaine interruption
        current_start_idx = 0   # index de la première arête pas encore consommée

        for child, tp in transitions:
            edge_idx = tp['edge_idx']
            param = tp['param']
            pt_source = tp['point_on_source']
            pt_target = tp['point_on_target']

            # 1) Ajouter les arêtes complètes avant l'arête d'interruption
            for ei in range(current_start_idx, edge_idx):
                collected_edges.append(wire_edges[ei])

            # 2) Couper l'arête d'interruption au paramètre
            trans_edge = wire_edges[edge_idx]
            eu1, eu2 = trans_edge.ParameterRange
            has_before = abs(param - eu1) > 1e-6
            has_after = abs(param - eu2) > 1e-6

            if has_before:
                try:
                    first_part = trans_edge.Curve.trim(eu1, param).toShape()
                    collected_edges.append(first_part)
                except Exception as exc:
                    App.Console.PrintWarning(
                        f'trim avant interruption échoué : {exc}\n')

            # 3) Émettre le segment accumulé (avant l'interruption)
            if collected_edges:
                try:
                    path.append(Part.Wire(collected_edges))
                except Exception:
                    for e in collected_edges:
                        path.append(e)
                collected_edges = []

            # 4) Transition vers l'enfant (G1 X Y, Z constant)
            path.append(Part.makeLine(pt_source, pt_target))
            Log.baptDebug(
                f'  Interruption → enfant {child}, '
                f'dist={(pt_target - pt_source).Length:.3f}\n')

            # 5) Décaler le wire enfant pour qu'il commence à pt_target
            child.shiftWire(pt_target)

            # 6) Traiter récursivement le sous-arbre enfant
            self._machine_node(obj, child, offset_dist, visited, path)

            # 7) Transition retour enfant → parent
            #    (après le tour complet de l'enfant on est revenu à pt_target)
            path.append(Part.makeLine(pt_target, pt_source))

            # 8) Préparer la suite : la seconde moitié de l'arête coupée
            if has_after:
                try:
                    second_part = trans_edge.Curve.trim(param, eu2).toShape()
                    collected_edges.append(second_part)
                except Exception as exc:
                    App.Console.PrintWarning(
                        f'trim après interruption échoué : {exc}\n')

            current_start_idx = edge_idx + 1

        # 9) Émettre les arêtes restantes du wire (après la dernière interruption)
        for ei in range(current_start_idx, len(wire_edges)):
            collected_edges.append(wire_edges[ei])

        if collected_edges:
            try:
                path.append(Part.Wire(collected_edges))
            except Exception:
                for e in collected_edges:
                    path.append(e)

        Log.baptDebug(f'  Fin usinage {node}\n')

    def makeTransitionToParent(self, obj, childNode: noeud, parentNode: noeud):
        """
        Crée une transition perpendiculaire entre un noeud enfant et son parent
        La transition est perpendiculaire à la première arête du wire enfant

        :param obj: L'objet PocketOperation
        :param childNode: Noeud enfant (intérieur)
        :param parentNode: Noeud parent (extérieur)
        """

        offset_dist = obj.ToolDiameter * (1 - obj.Overlap)

        childWire = childNode.wires
        parentWire = parentNode.wires
        try:
            is_ccw = childNode.isCCW()  # TODO: à implémenter le sens de fraisage

            edge = childWire.Edges[0]
            indice_start_point = getFirstPoint(childWire.Edges)
            u1, u2 = edge.ParameterRange
            if is_ccw:

                start_point: App.Vector = edge.Vertexes[indice_start_point].Point
                end_point: App.Vector = edge.Vertexes[-1 if indice_start_point == 0 else 0].Point
                Log.baptDebug(f'start_point: {start_point} is ccw: {is_ccw}\n')
                # for i,e in enumerate(childWire.Edges):
                #     Log.baptDebug(f'Edge {i}: {e.Vertexes[0].Point} to {e.Vertexes[-1].Point}\n')

            else:
                Log.baptDebug("Inverse le sens de l'arête pour CCW")
                # Inverse le sens de l'arête
                start_point: App.Vector = edge.Vertexes[-1 if indice_start_point == 0 else 0].Point
                end_point: App.Vector = edge.Vertexes[0 if indice_start_point == 0 else -1].Point
                utemp = u1
                u1 = u2
                u2 = utemp

            Log.baptDebug(f'start_point: {start_point}, end_point: {end_point}, is_ccw: {is_ccw}\n')
            # perpendiculaire à l'arête de début du childWire
            if edge.Curve.TypeId == 'Part::GeomLine':
                edge_normal = edge.tangentAt(u1).cross(App.Vector(0, 0, 1))
            elif edge.Curve.TypeId == 'Part::GeomCircle':

                if is_ccw:
                    edge_normal = edge.tangentAt(edge.Curve.parameter(start_point)).cross(App.Vector(0, 0, 1))
                else:
                    # start_point = childWire.Edges[0].Vertexes[-1].Point
                    edge_normal = edge.tangentAt(edge.Curve.parameter(start_point)).cross(App.Vector(0, 0, 1))

            edge_normal.normalize()
            candidates = []
            ray: Part.Line = Part.Line(start_point, start_point + edge_normal*100 if is_ccw else start_point - edge_normal*100)

            # Trouve le point le plus proche sur le parentWire
            for i, e in enumerate(parentWire.Edges):
                # calul le point d'intersection entre la droite perpendiculaire et l'arête

                # inter = ray.distToShape(e)
                inter: list[Part.Point] = ray.intersect(e.Curve)

                def pointToVector(p: Part.Point) -> App.Vector:
                    return App.Vector(p.X, p.Y, p.Z)

                new_start: App.Vector = None
                for i, p in enumerate(inter):
                    # Part.show(Part.makeSphere(0.5, pointToVector(p)))
                    d = (pointToVector(p) - start_point).Length
                    if math.fabs(d - offset_dist) < 1e-6:
                        # candidates.append((inter[1][0][1], i))
                        if obj.debugMode:
                            Part.show(Part.makeSphere(0.5, pointToVector(p)))
                        new_start = pointToVector(p)
                        if obj.debugMode:
                            Part.show(Part.makeLine(start_point, new_start))
                        # Décaler le parent pour commencer au point trouvé
                        parentNode.shiftWire(new_start)
                        # Ajouter la ligne de transition au wire enfant
                        transition_line = Part.makeLine(start_point, new_start)
                        childNode.wires.add(transition_line)
                        Log.baptDebug(f'Transition vers parent: distance={d:.3f}mm\n')
                        return True

            # Si aucune intersection trouvée à la distance exacte, chercher la plus proche
            Log.baptDebug(f'Recherche transition approximative...\n')
            min_dist_diff = float('inf')
            best_intersection = None

            for i, e in enumerate(parentWire.Edges):
                inter: list[Part.Point] = ray.intersect(e.Curve)
                for p in inter:
                    point = pointToVector(p)
                    d = (point - start_point).Length
                    dist_diff = abs(d - offset_dist)
                    if dist_diff < min_dist_diff:
                        min_dist_diff = dist_diff
                        best_intersection = point

            if best_intersection and min_dist_diff < offset_dist * 0.2:  # Tolérance 20%
                parentNode.shiftWire(best_intersection)
                transition_line = Part.makeLine(start_point, best_intersection)
                childNode.wires.add(transition_line)
                Log.baptDebug(f'Transition approximative: diff={min_dist_diff:.3f}mm\n')
                return True

            App.Console.PrintWarning(f'Aucune transition trouvée pour {childNode}\n')
            return False

        except Exception as e:
            line_nr = traceback.extract_tb(sys.exc_info()[2])[-1][1]
            App.Console.PrintError(f"makeTransitionToParent : {e} at line {line_nr}\n")
            return False


class PocketOperationTaskPanel():
    def __init__(self, obj):

        try:
            self.obj = obj
            self.ui1 = Gui.PySideUic.loadUi(BaptUtilities.getPanel("PocketOp.ui"))
            self.uiTool = ToolTaskPanel(obj)
            self.form = [self.ui1, self.uiTool.getForm()]

            self.overlapSpin = BQuantitySpinBox.BQuantitySpinBox(obj=obj, prop="Overlap", widget=self.ui1.overlapSpin)
            self.toolSpin = BQuantitySpinBox.BQuantitySpinBox(obj=obj, prop="ToolDiameter", widget=self.ui1.toolSpin)
            self.nbGenSpin = BQuantitySpinBox.BQuantitySpinBox(obj=obj, prop="maxGeneration", widget=self.ui1.nbGenSpin)
            self.surepAxialeSpin = BQuantitySpinBox.BQuantitySpinBox(obj=obj, prop="SurepAxiale", widget=self.ui1.surepAxialeSpin)
            self.surepRadialeSpin = BQuantitySpinBox.BQuantitySpinBox(obj=obj, prop="SurepRadiale", widget=self.ui1.surepRadialeSpin)
            self.stepDownSpin = BQuantitySpinBox.BQuantitySpinBox(obj=obj, prop="StepDown", widget=self.ui1.stepDownSpin)

            self.ui1.useMiddleofFirstEdge.setChecked(
                obj.useMiddleofFirstEdge if hasattr(obj, 'useMiddleofFirstEdge') else False)
            self.ui1.useMiddleofFirstEdge.stateChanged.connect(self.updateObj)

            for direction in Direction:
                self.ui1.directionCombo.addItem(direction)
            self.ui1.directionCombo.setCurrentText(
                obj.Direction if hasattr(obj, 'Direction') else Direction[0])
            self.ui1.directionCombo.currentTextChanged.connect(self.updateObj)

            for mode in pocketFillMode:
                self.ui1.modeCombo.addItem(mode)
            self.ui1.modeCombo.setCurrentText(
                obj.FillMode if hasattr(obj, 'FillMode') else pocketFillMode[0])
            self.ui1.modeCombo.currentTextChanged.connect(self.updateObj)

            for plunge in Plongee:
                self.ui1.plongeeCombo.addItem(plunge)
            self.ui1.plongeeCombo.setCurrentText(
                obj.PlungeType if hasattr(obj, 'PlungeType') else Plongee[0])
            self.ui1.plongeeCombo.currentTextChanged.connect(self.updateObj)

        except Exception as e:
            App.Console.PrintError(f"PocketOperationTaskPanel init: {str(e)}\n")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            App.Console.PrintMessage(f'ligne {exc_tb.tb_lineno}\n')

    def updateObj(self):
        try:
            self.obj.FillMode = self.ui1.modeCombo.currentText()
            self.obj.Direction = self.ui1.directionCombo.currentText()
            self.obj.useMiddleofFirstEdge = self.ui1.useMiddleofFirstEdge.isChecked()
            self.obj.PlungeType = self.ui1.plongeeCombo.currentText()
            self.obj.touch()
            App.ActiveDocument.recompute()
        except Exception as e:
            App.Console.PrintError(f"PocketOperationTaskPanel updateObj: {str(e)}\n")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            App.Console.PrintMessage(f'ligne {exc_tb.tb_lineno}\n')


class ViewProviderPocketOperation(BaseOp.baseOpViewProviderProxy):
    def __init__(self, vobj):
        super().__init__(vobj)
        self.Object = vobj.Object
        vobj.Proxy = self
        # vobj.Transparency = 90  # Définit la transparence pour mieux voir le chemin

    def attach(self, vobj):
        self.Object = vobj.Object

        return super().attach(vobj)

    def getIcon(self):
        """Retourne l'icône"""

        if not self.Object.Active:
            return BaptUtilities.getIconPath("operation_disabled.svg")
        return BaptUtilities.getIconPath("Pocket.svg")

    def setupContextMenu(self, vobj, menu):
        #     """Configuration du menu contextuel"""
        super().setupContextMenu(vobj, menu)

        action_edit_gcode = QtGui.QAction(Gui.getIcon("Std_TransformManip.svg"), "edit Gcode", menu)
        QtCore.QObject.connect(action_edit_gcode, QtCore.SIGNAL("triggered()"), lambda: self.EditGcode(vobj))
        menu.addAction(action_edit_gcode)
        #     action = menu.addAction("Edit")
        #     action.triggered.connect(lambda: self.setEdit(vobj))

        #     action2 = menu.addAction("Activate" if vobj.Object.desactivated else "Desactivate")
        #     action2.triggered.connect(lambda: self.setDesactivate(vobj))
        return True

    def EditGcode(self, vobj):
        taskPanel = GcodeEditorTaskPanel(vobj.Object)
        Gui.Control.showDialog(taskPanel)

    # def setDesactivate(self, vobj):
    #     """Désactive l'objet"""
    #     vobj.Object.desactivated = not vobj.Object.desactivated
    #     if vobj.Object.desactivated:
    #         vobj.Object.ViewObject.Visibility = False
    #     else:
    #         vobj.Object.ViewObject.Visibility = True

    # def updateData(self, fp, prop):
    #     pass

    # def getDisplayModes(self, vobj):
    #     return ["Flat Lines", "Shaded", "Wireframe"]

    # def getDefaultDisplayMode(self):
    #     return "FlatLines"

    # def setDisplayMode(self, vobj, mode=None):
    #     if mode is None:
    #         return self.getDefaultDisplayMode()
    #     return mode
    # def getDefaultDisplayMode(self):
    #     return super().getDefaultDisplayMode()

    # def setDisplayMode(self, mode):
    #     return super().setDisplayMode(mode)

    # def getDisplayModes(self, vobj):
    #     return super().getDisplayModes(vobj)

    # def onDelete(self, vobj, subelements):
    #     return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def setEdit(self, vobj, mode=0):
        """Ouvre le panneau de tâches pour l'opération de poche"""
        try:
            tp = PocketOperationTaskPanel(vobj.Object)
            Gui.Control.showDialog(tp)

        except Exception as e:
            App.Console.PrintError(f"message setEdit {str(e)}\n")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            App.Console.PrintMessage(f'{exc_tb.tb_lineno}\n')
            Log.baptDebug(f"message setEdit {str(e)}")
            return False
        return True

    def doubleClicked(self, vobj):
        """Gère le double-clic pour ouvrir le panneau de tâches"""
        self.setEdit(vobj)
        return True


def createPocketOperation(contour=None) -> Part.Feature:
    doc = App.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", "PocketOperation")

    PocketOperation(obj)
    ViewProviderPocketOperation(obj.ViewObject)

    if contour:
        obj.Contour = contour
        # Ajoute PocketOperation comme enfant de ContourGeometry dans l'arborescence
        # if hasattr(contour, "addObject"):
        #     contour.addObject(obj)
        # if hasattr(contour, "Group") and obj not in contour.Group:
        #     contour.Group.append(obj)

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


def findDeepestNodes(rootNodes: list[noeud]):
    deepest_nodes = []
    max_depth = -1

    queue = deque()
    for root in rootNodes:
        queue.append((root, 0))  # (node, depth)

    while queue:
        node, depth = queue.popleft()

        if depth > max_depth:
            max_depth = depth
            deepest_nodes = [node]
        elif depth == max_depth:
            deepest_nodes.append(node)

        for child in node.children:
            queue.append((child, depth + 1))

    return deepest_nodes


def arbore(rootNodes):
    result = []

    def visite(n):
        result.append(n)
        for c in n.children:
            visite(c)
    for r in rootNodes:
        visite(r)
    return result


def buildParentDepthLevel(node):
    """
    Docstring for buildParentDepthLevel

    :param node: node of the tree to start from
    :return: parent, depth, levels
    """
    parent = {node: None}
    depth = {node: 0}
    levels = {}
    q = deque([node])
    while q:
        current = q.popleft()
        d = depth[current]
        levels.setdefault(d, []).append(current)
        for child in current.children:
            parent[child] = current
            depth[child] = d + 1
            q.append(child)
    return parent, depth, levels
