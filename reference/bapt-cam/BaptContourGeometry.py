import FreeCAD as App
import FreeCADGui as Gui
import Part

import sys
import BaptUtilities
from utils import Log

try:
    from pivy import coin  # type: ignore
except ImportError:
    App.Console.PrintError("Impossible d'importer le module coin. La mise en surbrillance des arêtes ne fonctionnera pas correctement.\n")

DEBUG = True
if DEBUG:
    Log.setLevel(Log.Level.DEBUG, Log.thisModule())
else:
    Log.setLevel(Log.Level.INFO, Log.thisModule())


class ContourGeometry:
    """Classe pour gérer les contours d'usinage"""

    def __init__(self, obj):
        """Ajoute les propriétés"""

        self.Type = "ContourGeometry"

        # Transformer l'objet en groupe
        # obj.addExtension("App::GroupExtensionPython", None)
        # obj.addExtension("App::GroupExtensionPython")
        # DocumentObjectGroupPython

        # Permettre les références à des objets en dehors du groupe
        # obj.addExtension("App::LinkExtensionPython", None)
        # obj.addExtension("App::LinkExtensionPython")
        # obj.addProperty("App::PropertyLinkList", "Group", "Base", "Groupe d'objets géométriques")

        # Propriétés pour stocker les arêtes sélectionnées
        if not hasattr(obj, "Edges"):
            obj.addProperty("App::PropertyLinkSubList", "Edges", "Contour", "Arêtes sélectionnées pour le contour")

        if not hasattr(obj, "Zref"):
            obj.addProperty("App::PropertyFloat", "Zref", "Contour", "Hauteur de référence")
            obj.Zref = 0.0

        if not hasattr(obj, "depth"):
            obj.addProperty("App::PropertyFloat", "depth", "Contour", "Hauteur finale")
            obj.depth = 0.0

        if not hasattr(obj, "DepthMode"):
            obj.addProperty("App::PropertyEnumeration", "DepthMode", "Contour", "Mode de profondeur (Absolu ou Relatif)")
            obj.DepthMode = ["Absolu", "Relatif"]
            obj.DepthMode = "Absolu"

        if not hasattr(obj, "Direction"):
            obj.addProperty("App::PropertyEnumeration", "Direction", "Contour", "Direction d'usinage")
            obj.Direction = ["Horaire", "Anti-horaire"]
            obj.Direction = "Horaire"

        # proprité read only pour savoir si un contour est fermé
        if not hasattr(obj, "IsClosed"):
            obj.addProperty("App::PropertyBool", "IsClosed", "Contour", "Indique si le contour est fermé")
            obj.IsClosed = False

        if not hasattr(obj, "testShape"):
            obj.addProperty("Part::PropertyPartShape", "testShape", "Subsection", "Description for tooltip")
            obj.testShape = Part.Shape()

        if not hasattr(obj, "debugArrow"):
            obj.addProperty("App::PropertyBool", "debugArrow", "debug", "Description for tooltip")
            obj.debugArrow = True

        obj.Shape = obj.testShape

        obj.Proxy = self

    def onDocumentRestored(self, obj):
        """Appelé lors de la restauration du document"""

        self.__init__(obj)

    def onChanged(self, obj, prop):
        """Gérer les changements de propriétés"""
        if prop in ["DepthMode"]:
            if obj.DepthMode == "Relatif":
                obj.depth = obj.depth - obj.Zref
            else:
                obj.depth = obj.Zref + obj.depth
            self.execute(obj)
        elif prop in ["Edges", "Zref", "Direction", "depth", "debugArrow"]:
            self.execute(obj)
        # elif prop == "SelectedEdgeIndex":
        #     # Mettre à jour les couleurs des arêtes lorsque la sélection change
        #     self.updateEdgeColors(obj)

    def debugEdges(self, edges, name=""):
        # Diagnostic avant création du wire
        App.Console.PrintMessage(f"[DEBUG] Nombre d'arêtes pour {name}: {len(edges)}\n")
        for i, e in enumerate(edges):
            self.debugEdge(e, i, name)
        App.Console.PrintMessage(f"[DEBUG] Fin du diagnostic pour {name}\n")

    def debugEdge(self, edge, i=0, name=""):
        start = edge.Vertexes[0].Point
        # Arrondir à 3 chiffres après la virgule
        start = App.Vector(round(start.x, 3), round(start.y, 3), round(start.z, 3))
        end = edge.Vertexes[-1].Point
        end = App.Vector(round(end.x, 3), round(end.y, 3), round(end.z, 3))
        App.Console.PrintMessage(f"[DEBUG] Edge {i}: orientation={edge.Orientation}, start={start}, end={end}, firstParam={round(edge.FirstParameter,3)}, lastParam={round(edge.LastParameter,3)}\n")

    def execute(self, obj):
        """Mettre à jour la représentation visuelle du contour"""
        if App.ActiveDocument.Restoring:
            return
        try:
            if not hasattr(obj, "Edges") or not obj.Edges:
                # App.Console.PrintMessage("Aucune arête sélectionnée pour le contour.\n")
                return

            # Collecter toutes les arêtes sélectionnées
            edges = []
            for sub in obj.Edges:
                obj_ref = sub[0]  # L'objet référencé
                sub_names = sub[1]  # Les noms des sous-éléments (arêtes)

                for sub_name in sub_names:
                    element = obj_ref.Shape.getElement(sub_name)
                    element_type = getattr(element, "ShapeType", "Inconnu")
                    Log.baptDebug(f"Traitement de l'objet {obj_ref.Name} avec les sous-éléments {sub_names}, type:{element_type}\n")
                    if element_type == "Edge":
                        edge = obj_ref.Shape.getElement(sub_name)
                        edges.append(edge)
                        # App.Console.PrintMessage(f"Arête ajoutée: {sub_name} de {obj_ref.Name}\n")

                    elif element_type == "Face":
                        # Si l'élément est une face, ajouter toutes ses arêtes
                        face_edges = element.Edges
                        edges.extend(face_edges)
                        Log.baptDebug(f"Face détectée, ajout de {len(face_edges)} arêtes de {obj_ref.Name}\n")
                    else:
                        App.Console.PrintWarning(f"Element {sub_name} de {obj_ref.Name} n'est ni une arête ni une face (type: {element_type}), ignoré.\n")

            if not edges:
                App.Console.PrintError("Aucune arête valide trouvée.\n")
                return

            # App.Console.PrintMessage(f"Nombre d'arêtes collectées: {len(edges)}\n")

            # Vérifier si une arête est sélectionnée
            selected_index = -1
            if hasattr(obj, "SelectedEdgeIndex"):
                selected_index = obj.SelectedEdgeIndex

            # Créer des arêtes ajustées à la hauteur Zref et à depth
            adjusted_edges_zref = []
            adjusted_edges_depth = []

            # Créer des flèches pour indiquer la direction
            direction_arrows = []

            if obj.Direction == "Anti-horaire":
                edges.reverse()

            # sorted_edges = self.order_edges(edges)  # Trier les arêtes par ordre croissant de edges
            # sorted_edges = Part.__sortEdges__(edges)
            sorted_edges = Part.sortEdges(list(edges))[0]  # https://github.com/FreeCAD/FreeCAD/commit/1031644fa
            # sorted_edges = Part.getSortedClusters(list(edges))[0]
            # sorted_edges = edges.copy()  # Faire une copie des arêtes pour le tri
            # sorted_edges = edges

            if obj.Direction == "Anti-horaire":
                sorted_edges.reverse()

            if DEBUG:
                self.debugEdges(sorted_edges, "Sorted Edges")

            if not sorted_edges:
                App.Console.PrintError("Aucune arête valide après le tri.\n")
                obj.Shape = Part.Shape()  # Shape vide
                obj.testShape = Part.Shape()
                obj.IsClosed = False
                return

            for i, edge in enumerate(sorted_edges):
                # Créer des arêtes ajustées avec des couleurs différentes selon la sélection
                # Pour l'arête sélectionnée, utiliser une couleur différente et une largeur plus grande

                # if edge.Vertexes[0].Orientation == "Reversed":
                #     App.Console.PrintMessage(f"Edge {i} est inversée, inversion de l'arête pour correspondre au sens.\n")
                #     edge = edge.reversed()
                current_edge = edge
                bon_sens = None
                if i < len(sorted_edges)-1:
                    next_edge = sorted_edges[i+1]
                    if current_edge.Vertexes[-1].Point.distanceToPoint(next_edge.Vertexes[0].Point) < 1e-6:
                        bon_sens = True
                        # App.Console.PrintMessage(f"Edge {i} est dans le bon sens.\n")
                    elif current_edge.Vertexes[-1].Point.distanceToPoint(next_edge.Vertexes[-1].Point) < 1e-6:
                        bon_sens = True
                        # App.Console.PrintMessage(f"Edge {i} Ok ,Edge {i+1} est inversée, inversion de l'arête pour correspondre au sens.\n")
                    elif current_edge.Vertexes[0].Point.distanceToPoint(next_edge.Vertexes[-1].Point) < 1e-6:
                        bon_sens = False
                        # App.Console.PrintMessage(f"Edge {i} et Edge {i+1} sont inversées, inversion de l'arête pour correspondre au sens.\n")
                    elif current_edge.Vertexes[0].Point.distanceToPoint(next_edge.Vertexes[0].Point) < 1e-6:
                        bon_sens = False
                        # App.Console.PrintMessage(f"Edge {i} est inversée, inversion de l'arête pour correspondre au sens.\n")
                    else:
                        # App.Console.PrintMessage(f"Edge {i} n'est pas connectée à l'arête suivante, le contour ne sera pas fermé.\n")
                        pass
                else:
                    prev_edge = sorted_edges[i-1]

                    if prev_edge.Vertexes[-1].Point.distanceToPoint(current_edge.Vertexes[0].Point) < 1e-6:
                        bon_sens = True
                        # App.Console.PrintMessage(f"Edge {i} est dans le bon sens.\n")
                    elif prev_edge.Vertexes[-1].Point.distanceToPoint(current_edge.Vertexes[-1].Point) < 1e-6:
                        bon_sens = False
                        # App.Console.PrintMessage(f"Edge {i} NOk ,Edge {i-1} est inversée, inversion de l'arête pour correspondre au sens.\n")
                    elif prev_edge.Vertexes[0].Point.distanceToPoint(current_edge.Vertexes[-1].Point) < 1e-6:
                        bon_sens = False
                        # App.Console.PrintMessage(f"Edge {i} et Edge {i-1} sont inversées, inversion de l'arête pour correspondre au sens.\n")
                    elif prev_edge.Vertexes[0].Point.distanceToPoint(current_edge.Vertexes[0].Point) < 1e-6:
                        bon_sens = True
                        # App.Console.PrintMessage(f"Edge {i} Ok, inversion de l'arête pour correspondre au sens.\n")
                    else:
                        # App.Console.PrintMessage(f"Edge {i} n'est pas connectée à l'arête suivante, le contour ne sera pas fermé.\n")
                        pass

                if DEBUG:
                    self.debugEdge(edge, i, "")

                # Créer une flèche pour indiquer la direction de l'arête
                arrow = self._create_direction_arrow(obj, edge, size=2.0, invert_direction=not bon_sens)
                if arrow:
                    direction_arrows.append(arrow)

                edge_zref = edge.copy().translate(App.Vector(0, 0, obj.Zref - edge.Vertexes[0].Z))

                edge_zfinal = edge.copy().translate(App.Vector(0, 0, obj.Zref - edge.Vertexes[0].Z + obj.depth if obj.DepthMode == "Relatif" else obj.depth - edge.Vertexes[0].Z))
                adjusted_edges_zref.append(edge_zref)
                adjusted_edges_depth.append(edge_zfinal)

            # self.debugEdge(adjusted_edges_zref, "Zref")

            try:
                # Créer le fil à Zref
                wire_zref = Part.Wire(adjusted_edges_zref)

                # Créer le fil à depth
                wire_zfinal = Part.Wire(adjusted_edges_depth)

                # Créer les faces entre les arêtes correspondantes
                faces = []
                if len(adjusted_edges_zref) == len(adjusted_edges_depth):
                    for i in range(len(adjusted_edges_zref)):
                        try:
                            face = Part.makeRuledSurface(adjusted_edges_zref[i], adjusted_edges_depth[i])
                            faces.append(face)
                        except Exception as e:
                            App.Console.PrintError(f"Impossible de créer une face entre les arêtes {i}: {str(e)}\n")
                else:
                    App.Console.PrintError("Les listes d'arêtes ajustées n'ont pas la même taille, impossible de créer les faces.\n")

                first_point = wire_zref.Edges[0].Vertexes[0].Point
                sph = Part.makeSphere(2, first_point)

                # Créer un compound contenant les deux fils, les flèches et les faces
                shapes = [wire_zref, wire_zfinal, sph]
                # shapes = [wire_zref]

                if obj.debugArrow:
                    shapes.extend(direction_arrows)

                shapes.extend(faces)  # Ajouter les faces ici
                compound = Part.makeCompound(shapes)
                obj.Shape = compound
                obj.testShape = compound

                # Vérifier si le fil est fermé (utiliser le fil à Zref pour cette vérification)
                if wire_zref.isClosed():
                    obj.IsClosed = True
                else:
                    obj.IsClosed = False

                # prefs = BaptPreferences()

                # autoRecomputeChildren = prefs.getAutoChildUpdate()
                # if autoRecomputeChildren:
                #     for child in obj.Group:
                #         child.recompute()

            except Exception as e:
                App.Console.PrintError(f"Impossible de créer un fil à partir des arêtes sélectionnées: {str(e)}\n")
                exc_type, exc_value, exc_traceback = sys.exc_info()
                line_number = exc_traceback.tb_lineno
                App.Console.PrintError(f"Erreur à la ligne {line_number}\n")
                App.Console.PrintError(f"[DEBUG] Les arêtes transmises à Part.Wire ne sont pas chaînées ou sont invalides.\n")
                # Essayer de créer une forme composite si le fil échoue
                try:
                    all_edges = adjusted_edges_zref
                    all_edges.extend(adjusted_edges_depth)
                    compound = Part.makeCompound(all_edges)
                    obj.Shape = compound
                    obj.testShape = compound
                    # App.Console.PrintMessage("Forme composite créée à la place du fil.\n")
                    return
                except Exception as e2:
                    # App.Console.PrintError(f"Impossible de créer une forme composite: {str(e2)}\n")
                    return

        except Exception as e:
            App.Console.PrintError(f"Erreur lors de l'exécution: {str(e)}\n")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_number = exc_traceback.tb_lineno
            App.Console.PrintError(f"Erreur à la ligne {line_number}\n")

    def _create_adjusted_edge(self, edge, z_value, selected=False):
        """Crée une arête ajustée à une hauteur Z spécifique avec une couleur optionnelle

        Args:
            edge: L'arête d'origine
            z_value: Valeur Z à appliquer
            selected: Si True, l'arête est sélectionnée et aura une apparence différente

        Returns:
            Nouvelle arête ajustée
        """
        new_edge = None

        p1 = edge.Vertexes[0].Point
        p2 = edge.Vertexes[1].Point
        # Créer de nouveaux points avec Z = z_value
        new_p1 = App.Vector(p1.x, p1.y, z_value)
        new_p2 = App.Vector(p2.x, p2.y, z_value)

        if isinstance(edge.Curve, Part.Line):
            # Pour une ligne droite
            # Créer une nouvelle ligne
            new_edge = Part.makeLine(new_p1, new_p2)
        elif isinstance(edge.Curve, Part.Circle):
            # Pour un arc ou un cercle
            circle = edge.Curve
            center = circle.Center
            new_center = App.Vector(center.x, center.y, z_value)
            # Créer un nouvel axe Z
            new_axis = edge.Curve.Axis
            radius = circle.Radius
            # Créer un nouveau cercle
            new_circle = Part.Circle(new_center, new_axis, radius)
            # On récupère les angles d'origine
            u1, u2 = edge.ParameterRange
            # Si l'arc d'origine est CW, il faut inverser la courbe
            orig_start = edge.valueAt(u1)
            orig_end = edge.valueAt(u2)
            # # On vérifie le sens en comparant les points projetés
            new_edge = Part.Edge(new_circle, u1, u2)
            new_edge = new_edge.reversed()
            if (p1 - orig_start).Length > 1e-6 or (p2 - orig_end).Length > 1e-6:
                # Les points sont inversés, il faut inverser la courbe
                pass

        elif isinstance(edge.Curve, Part.Ellipse):
            # Pour une ellipse
            ellipse = edge.Curve
            center = ellipse.Center
            new_center = App.Vector(center.x, center.y, z_value)
            # Créer un nouvel axe Z
            new_axis = App.Vector(0, 0, 1)
            major_radius = ellipse.MajorRadius
            minor_radius = ellipse.MinorRadius
            # On récupère les angles d'origine
            u1, u2 = edge.ParameterRange
            # Créer une nouvelle ellipse
            new_ellipse = Part.Ellipse(new_center, new_axis, major_radius, minor_radius)
            new_edge = Part.Edge(new_ellipse, u1, u2)
        else:
            # Pour les autres types de courbes, utiliser une approximation par points
            points = []
            for i in range(10):  # Utiliser 10 points pour l'approximation
                param = edge.FirstParameter + (edge.LastParameter - edge.FirstParameter) * i / 9
                point = edge.valueAt(param)
                new_point = App.Vector(point.x, point.y, z_value)
                points.append(new_point)

            # Créer une BSpline à partir des points
            if len(points) >= 2:
                bspline = Part.BSplineCurve()
                bspline.interpolate(points)
                new_edge = Part.Edge(bspline)

        # Si l'arête est sélectionnée, stocker cette information dans la propriété Tag
        if new_edge and selected:
            new_edge.Tag = 1  # Utiliser Tag=1 pour indiquer que c'est une arête sélectionnée

        return new_edge

    def order_edges(self, edges, tol=1e-5):
        """
        Trie et oriente les edges pour qu'ils forment une chaîne continue.
        Gère tous les cas de correspondance de sommets.
        """
        import Part  # type: ignore

        if not edges:
            return []
        try:

            unused = list(edges)
            ordered = [unused.pop(0)]

            while unused:
                # first = ordered[0].Vertexes[0].Point
                # last = ordered[-1].Vertexes[-1].Point
                first = ordered[0].valueAt(ordered[0].FirstParameter)
                last = ordered[-1].valueAt(ordered[-1].LastParameter)
                found = False
                for i, edge in enumerate(unused):
                    start = edge.Vertexes[0].Point
                    end = edge.Vertexes[-1].Point
                    # Cas 1 : la fin du dernier = début du suivant (cas normal)
                    if (start - last).Length < tol:
                        ordered.append(edge)
                        unused.pop(i)
                        found = True
                        break
                    # Cas 2 : la fin du dernier = fin du suivant (il faut inverser)
                    elif (end - last).Length < tol:
                        reversed_edge = self.reverse_edge(edge)
                        ordered.append(reversed_edge)
                        unused.pop(i)
                        found = True
                        break
                    # Cas 3 : le début du premier = fin du suivant (ajouter au début, inversé)
                    elif (end - first).Length < tol:
                        reversed_edge = self.reverse_edge(edge)
                        ordered.insert(0, reversed_edge)
                        unused.pop(i)
                        found = True
                        break
                    # Cas 4 : le début du premier = début du suivant (ajouter au début)
                    elif (start - first).Length < tol:
                        ordered.insert(0, edge)
                        unused.pop(i)
                        found = True
                        break
                if not found:
                    return None
                for idx, e in enumerate(ordered):
                    App.Console.PrintMessage(f"Edge {idx}: {e.Vertexes[0].Point} -> {e.Vertexes[-1].Point}\n")
            return ordered
        except Exception as e:
            App.Console.PrintError(f"Erreur order_edges: {str(e)}\n")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_number = exc_traceback.tb_lineno
            App.Console.PrintError(f"Erreur à la ligne {line_number}\n")

    def reverse_edge(self, edge):
        """
        Retourne un nouvel edge inversé, compatible avec les arcs et segments.
        """
        import Part  # type: ignore
        curve = edge.Curve
        return edge.reversed()
        try:
            curve = edge.Curve
            # Pour les courbes paramétrées (arc, ligne, etc.)
            if isinstance(edge.Curve, Part.Circle):
                # Pour un arc ou un cercle
                circle = edge.Curve
                center = circle.Center
                new_center = App.Vector(center.x, center.y, center.z)
                # Créer un nouvel axe Z
                new_axis = circle.Axis  # *-1
                App.Console.PrintMessage(f"new dir {new_axis}\n")
                radius = circle.Radius

                # Créer un nouveau cercle
                new_circle = Part.Circle(new_center, new_axis, radius)
                # return Part.Edge(new_circle, edge.FirstParameter, edge.LastParameter)
                # return Part.Edge(new_circle, edge.LastParameter, edge.FirstParameter)
                # convertir les paramètres de l'arc en paramètres de cercle
                arctspt = edge.valueAt(edge.FirstParameter)
                arcendpt = edge.valueAt(edge.LastParameter)

                midParam = (edge.LastParameter - edge.FirstParameter) * 0.5 + edge.FirstParameter
                arcmidpt = edge.valueAt(midParam)
                App.Console.PrintMessage(f"Reversing edge: {edge.FirstParameter}, {edge.LastParameter}, {midParam}\n")
                App.Console.PrintMessage(f"Arc2 start point: {arctspt}, end point: {arcendpt}, mid point: {arcmidpt}\n")

                # first_param = -math.tau + first_param
                # Si les paramètres sont différents, c'est un arc
                # if abs(last_param - first_param) < math.tau:  # Moins que 2*pi
                #     print(f"Arc détecté avec paramètres {first_param} et {last_param}\n")
                #     new_edge = Part.Edge(new_circle, last_param, first_param)
                # else:
                #     # Cercle complet
                #     new_edge = Part.Edge(new_circle)
                # new_edge = Part.ArcOfCircle(new_circle,arctspt,arcmidpt,arcendpt)
                new_edge = Part.ArcOfCircle(new_circle, 0, 1.57).toShape()
                # new_edge = Part.ArcOfCircle(0,math.pi/2,math.pi).toShape()
                App.Console.PrintMessage(f"Reversing edge: {new_edge.FirstParameter}, {new_edge.LastParameter}\n")
                return new_edge

            reversed_curve = curve.reversed()
            reversed_curve = curve
            # On inverse aussi les paramètres de début et de fin
            return Part.Edge(reversed_curve, edge.ParameterRange[1], edge.ParameterRange[0])
        except Exception as e:
            App.Console.PrintError(f"Erreur lors de l'inversion de l'arête: {str(e)}\n")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_number = exc_traceback.tb_lineno
            App.Console.PrintError(f"Erreur à la ligne {line_number}\n")
            # Fallback pour les lignes simples
            new_edge = edge.copy()
            new_edge.reverse()
            return new_edge

    def _create_direction_arrow(self, obj, edge, size=2.0, invert_direction=False):
        """Crée une petite flèche au milieu de l'arête pour indiquer la direction

        Args:
            edge: L'arête d'origine
            z_value: Valeur Z à appliquer
            size: Taille de la flèche en mm

        Returns:
            Shape représentant la flèche
        """
        # TODO implemente param: invert_direction pour inverser la direction de la flèche
        try:
            # Point milieu paramétrique
            mid_param = (edge.FirstParameter + edge.LastParameter) / 2.0
            mid_point = edge.valueAt(mid_param)
            mid_point_z = App.Vector(mid_point.x, mid_point.y, obj.Zref)

            # Tangente au point milieu
            tangent = edge.tangentAt(mid_param)
            # Protection : parfois tangentAt peut retourner un vecteur nul
            if tangent.Length < 1e-9:
                tangent = App.Vector(1, 0, 0)
            tangent = tangent.normalize()

            if invert_direction:
                tangent = tangent.multiply(-1)

            # Projet de la tangente sur XY et normalisation
            tangent_z = App.Vector(tangent.x, tangent.y, 0.0)

            tangent_z = tangent_z.normalize()

            # Normale (perpendiculaire) dans le plan XY
            normal_xy = App.Vector(-tangent_z.y, tangent_z.x, 0.0)
            if normal_xy.Length < 1e-9:
                normal_xy = App.Vector(0, 1, 0)
            normal_xy = normal_xy.normalize()

            # Décalage le long de la normale : proportionnel à la taille, ajustable
            offset_distance = size * 0.6

            # if hasattr(obj, "Direction") and obj.Direction == "Anti-horaire" :
            #     offset_distance = -offset_distance

            # Point milieu décalé le long de la normale
            shifted_mid = mid_point_z.add(normal_xy.multiply(offset_distance))

            # Construire la flèche centrée sur shifted_mid, orientée selon la tangente
            start_point = shifted_mid.sub(tangent_z.multiply(size / 2.0))
            end_point = shifted_mid.add(tangent_z.multiply(size / 2.0))

            arrow_line = Part.makeLine(start_point, end_point)

            # Pointe de la flèche (petites lignes perpendiculaires)
            perp = normal_xy  # vecteur perpendiculaire déjà calculé et normalisé

            arrow_p1 = end_point.sub(tangent_z.multiply(size / 3.0)).add(perp.multiply(size / 4.0))
            arrow_p2 = end_point.sub(tangent_z.multiply(size / 3.0)).sub(perp.multiply(size / 4.0))

            # perp_line = Part.makeLine(mid_point, shifted_mid )

            arrow_line1 = Part.makeLine(end_point, arrow_p1)
            arrow_line2 = Part.makeLine(end_point, arrow_p2)

            arrow_shape = Part.makeCompound([arrow_line, arrow_line1, arrow_line2])
            return arrow_shape

        except Exception as e:
            App.Console.PrintWarning(f"Erreur lors de la création de la flèche: {str(e)}\n")
            return None

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None

    def dumps(self):
        """__getstat__(self) ... called when receiver is saved.
        Can safely be overwritten by subclasses."""
        return None

    def loads(self, state):
        """__getstat__(self) ... called when receiver is restored.
        Can safely be overwritten by subclasses."""
        return None

    def updateEdgeColors(self, obj):
        """Met à jour les couleurs des arêtes en fonction de l'index sélectionné"""
        App.Console.PrintMessage('updateEdgeColors\n')
        if not hasattr(obj, "SelectedEdgeIndex") or not hasattr(obj, "Edges") or not obj.Edges:
            return

        selected_index = obj.SelectedEdgeIndex
        if selected_index < 0:
            # Aucune sélection, restaurer les couleurs normales
            self.execute(obj)
            return

        try:
            # Collecter toutes les arêtes
            all_edges = []
            for sub in obj.Edges:
                obj_ref = sub[0]
                sub_names = sub[1]

                for sub_name in sub_names:
                    if "Edge" in sub_name:
                        try:
                            edge = obj_ref.Shape.getElement(sub_name)
                            all_edges.append(edge)
                        except Exception as e:
                            App.Console.PrintError(f"Erreur lors de la récupération de l'arête {sub_name}: {str(e)}\n")

            if not all_edges or selected_index >= len(all_edges):
                return

            # Créer des arêtes ajustées à Zref et depth
            adjusted_edges_zref = []
            adjusted_edges_depth = []

            for i, edge in enumerate(all_edges):
                # Créer des arêtes ajustées avec des couleurs différentes selon la sélection

                # Pour l'arête sélectionnée, utiliser une couleur différente et une largeur plus grande
                edge_zref = self._create_adjusted_edge(edge, obj.Zref, selected=(i == selected_index))
                edge_depth = self._create_adjusted_edge(edge, obj.depth, selected=(i == selected_index))

                adjusted_edges_zref.append(edge_zref)
                adjusted_edges_depth.append(edge_depth)

            # Séparer les arêtes sélectionnées et non sélectionnées
            normal_edges_zref = []
            normal_edges_depth = []
            selected_edges_zref = []
            selected_edges_depth = []

            for i, edge in enumerate(adjusted_edges_zref):
                if i == selected_index:
                    selected_edges_zref.append(edge)
                else:
                    normal_edges_zref.append(edge)

            for i, edge in enumerate(adjusted_edges_depth):
                if i == selected_index:
                    selected_edges_depth.append(edge)
                else:
                    normal_edges_depth.append(edge)

            # Créer des compounds pour les arêtes normales et sélectionnées
            shapes = []

            # Ajouter les arêtes normales
            if normal_edges_zref:
                normal_compound_zref = Part.makeCompound(normal_edges_zref)
                shapes.append(normal_compound_zref)

            if normal_edges_depth:
                normal_compound_depth = Part.makeCompound(normal_edges_depth)
                shapes.append(normal_compound_depth)

            # Ajouter les arêtes sélectionnées
            if selected_edges_zref:
                selected_compound_zref = Part.makeCompound(selected_edges_zref)
                shapes.append(selected_compound_zref)

            if selected_edges_depth:
                selected_compound_depth = Part.makeCompound(selected_edges_depth)
                shapes.append(selected_compound_depth)

            # Créer un compound final
            if shapes:
                compound = Part.makeCompound(shapes)
                obj.Shape = compound

                # Stocker les informations pour le ViewProvider
                if not hasattr(obj, "NormalEdges"):
                    obj.addProperty("App::PropertyPythonObject", "NormalEdges", "Visualization", "Normal edges")
                if not hasattr(obj, "SelectedEdges"):
                    obj.addProperty("App::PropertyPythonObject", "SelectedEdges", "Visualization", "Selected edges")

                # Stocker les compounds pour que le ViewProvider puisse les colorier
                normal_edges = normal_edges_zref + normal_edges_depth
                selected_edges = selected_edges_zref + selected_edges_depth

                obj.NormalEdges = Part.makeCompound(normal_edges) if normal_edges else Part.Shape()
                obj.SelectedEdges = Part.makeCompound(selected_edges) if selected_edges else Part.Shape()

        except Exception as e:
            App.Console.PrintError(f"Erreur lors de la mise à jour des couleurs: {str(e)}\n")
            # En cas d'erreur, revenir à l'affichage normal
            self.execute(obj)


class ViewProviderContourGeometry:
    """Classe pour gérer l'affichage des contours"""

    def __init__(self, vobj):
        """Initialise le ViewProvider"""
        vobj.Proxy = self
        self.Object = vobj.Object

        self.deleteOnReject = True

        # Définir la couleur rouge pour le contour
        vobj.LineColor = (1.0, 0.0, 0.0)  # Rouge
        vobj.PointColor = (1.0, 0.0, 0.0)  # Rouge
        vobj.LineWidth = 4.0  # Largeur de ligne plus grande
        vobj.PointSize = 6.0  # Taille des points plus grande

        vobj.ShapeAppearance[0].DiffuseColor = (255, 170, 0)
        vobj.Transparency = 85

        # Ajouter une propriété pour la couleur des arêtes sélectionnées
        if not hasattr(vobj, "SelectedEdgeColor"):
            vobj.addProperty("App::PropertyColor", "SelectedEdgeColor", "Display", "Color of selected edges")
            vobj.SelectedEdgeColor = (0.0, 1.0, 1.0)  # Cyan par défaut

    def deleteObjectsOnReject(self):
        """
        deleteObjectsOnReject() ... return true if all objects should
        be created if the user hits cancel. This is used during the initial
        edit session, if the user does not press OK, it is assumed they've
        changed their mind about creating the operation.
        """

        return hasattr(self, "deleteOnReject") and self.deleteOnReject

    def setDeleteObjectsOnReject(self, state=False):
        # ♦Path.Log.track()
        self.deleteOnReject = state
        return self.deleteOnReject

    def getIcon(self):
        """Retourne l'icône"""
        return BaptUtilities.getIconPath("Tree_Contour.svg")

    def attach(self, vobj):
        """Appelé lors de l'attachement du ViewProvider"""
        self.Object = vobj.Object

        # # Créer un switch pour activer/désactiver la surbrillance
        # self.coin_switch = coin.SoSwitch()
        # self.coin_switch.whichChild = coin.SO_SWITCH_NONE  # Désactivé par défaut

        # # Sépérateur pour la surbrillance
        # sep = coin.SoSeparator()

        # # Style de ligne pour la surbrillance
        # drawstyle = coin.SoDrawStyle()
        # drawstyle.lineWidth = 8.0  # Plus épais que normal
        # sep.addChild(drawstyle)

        # # Couleur de surbrillance (cyan)
        # mat = coin.SoMaterial()
        # mat.diffuseColor = (0.0, 1.0, 1.0)
        # mat.emissiveColor = (0.0, 0.5, 0.5)
        # sep.addChild(mat)

        # # Coordonnées (vides au départ, seront remplies par updateHighlight)
        # self.coin_coords = coin.SoCoordinate3()
        # sep.addChild(self.coin_coords)

        # # LineSet pour dessiner les lignes
        # self.coin_lineset = coin.SoLineSet()
        # sep.addChild(self.coin_lineset)

        # self.coin_switch.addChild(sep)
        # vobj.RootNode.addChild(self.coin_switch)

    def updateData(self, obj, prop):
        """Appelé lorsqu'une propriété de l'objet est modifiée"""
        # Mettre à jour l'affichage si une propriété pertinente change
        if prop == "SelectedEdgeIndex":
            pass

    def onChanged(self, vobj, prop):
        """Appelé lorsqu'une propriété du ViewProvider est modifiée"""
        pass

    def claimChildren(self):
        """Retourne les enfants de cet objet"""
        children = []
        # Récupérer tous les objets de contournage qui référencent cette géométrie par son nom
        if self.Object:
            doc = self.Object.Document
            if not doc:
                return children

            # Vérifier que l'objet a un nom valide
            if not hasattr(self.Object, "Name") or not self.Object.Name:
                return children

            for obj in doc.Objects:
                # Vérifier si l'objet est un cycle de contournage
                if hasattr(obj, "Proxy") and hasattr(obj.Proxy, "Type") and obj.Proxy.Type == "ContournageCycle":
                    # Vérifier si l'objet référence cette géométrie
                    if hasattr(obj, "ContourGeometryName") and obj.ContourGeometryName == self.Object.Name:
                        children.append(obj)

            # Vérifier si l'objet a un groupe
            if hasattr(self.Object, "Group"):
                # Ajouter tous les objets du groupe qui ne sont pas déjà dans la liste
                for obj in self.Object.Group:
                    if obj not in children:
                        children.append(obj)

        return children

    def getDisplayModes(self, vobj):
        """Retourne les modes d'affichage disponibles"""
        return ["Flat Lines"]

    def getDefaultDisplayMode(self):
        """Retourne le mode d'affichage par défaut"""
        return "Path"
        return "Flat Lines"

    def setDisplayMode(self, mode):
        """Définit le mode d'affichage"""
        return mode

    def onChanged(self, vobj, prop):
        """Appelé lorsqu'une propriété du ViewProvider est modifiée"""
        pass

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        action = menu.addAction("Edit")
        action.triggered.connect(lambda: self.setEdit(vobj))

        actionExport = menu.addAction("Export")
        actionExport.triggered.connect(lambda: self.export(vobj))
        return True

    def export(self, vobj, mode=0):
        """Exporte l'objet"""
        sheet = App.activeDocument().addObject('Spreadsheet::Sheet', 'Spreadsheet')
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(App.activeDocument().Name, 'Spreadsheet')

        # recupere les edges de la géométrie
        edges = vobj.Object.Edges

        for i, edge in enumerate(edges):
            obj_ref = edge[0]
            sub_names = edge[1]
            sheet.set("A" + str(i+1), str(i))
            for j, sub_name in enumerate(sub_names):
                sheet.set("B" + str(i+j+1), str(sub_name))
                edge_ref = obj_ref.Shape.getElement(sub_name)
                start_point = edge_ref.Vertexes[0].Point
                end_point = edge_ref.Vertexes[-1].Point
                sheet.set("C" + str(i+j+1), str(start_point))
                sheet.set("D" + str(i+j+1), str(end_point))
                if isinstance(edge_ref.Curve, Part.Circle):
                    sheet.set("E" + str(i+j+1), "Cercle")
                elif isinstance(edge_ref.Curve, Part.Line):
                    sheet.set("E" + str(i+j+1), "Ligne")
                else:
                    sheet.set("E" + str(i+j+1), "Inconnu")
        pass

    def setEdit(self, vobj, mode=0):
        """Appelé lorsque l'objet est édité"""
        try:
            import importlib
            import BaptContourTaskPanel
            # Recharger le module pour prendre en compte les modifications
            importlib.reload(BaptContourTaskPanel)
            # Créer et afficher le panneau
            panel = BaptContourTaskPanel.ContourTaskPanel(vobj.Object, self.setDeleteObjectsOnReject())
            Gui.Control.showDialog(panel)
            self.deleteOnReject = False
            return True
        except Exception as e:
            App.Console.PrintError(f"Erreur lors de l'ouverture du panneau d'édition: {str(e)}\n")
            return False

    def unsetEdit(self, vobj, mode=0):
        """Appelé lorsque l'édition est terminée"""
        Gui.Control.closeDialog()
        return True

    def doubleClicked(self, vobj):
        """Appelé lors d'un double-clic sur l'objet"""
        self.setEdit(vobj)
        return True

    def __getstate__(self):
        """Appelé lors de la sauvegarde"""
        return None
        return {"ObjectName": self.Object.Name if self.Object else None}

    def __setstate__(self, state):
        """Appelé lors du chargement"""
        return None
        if state and "ObjectName" in state and state["ObjectName"]:
            self.Object = App.ActiveDocument.getObject(state["ObjectName"])
        return None

    def onDelete(self, feature, subelements):  # subelements is a tuple of strings

        for child in feature.Object.Group:
            App.ActiveDocument.removeObject(child.Name)
        return True  # If False is returned the object won't be deleted
