from BaptPath import GcodeAnimationControl, GcodeAnimator, absinc, comp, memory
from BaptPreferences import BaptPreferences
import BaptUtilities
import FreeCAD as App
import FreeCADGui as Gui

from Op.utils import CoolantMode
from PySide import QtCore, QtGui
from pivy import coin  # type: ignore
import math

from utils import Log

DEBUG = True
if DEBUG:
    Log.setLevel(Log.Level.DEBUG, Log.thisModule())
else:
    Log.setLevel(Log.Level.INFO, Log.thisModule())


class baseOp:

    def __init__(self, obj):
        # App.Console.PrintMessage("Initializing baseOp object proxy for: {}\n".format(__class__.__name__))
        if not hasattr(obj, "Gcode"):
            obj.addProperty("App::PropertyString", "Gcode", "Gcode", "Gcode").Gcode = ""
            # obj.Gcode ="G0 X0 Y-20 Z50\nG0 Z2\nG1 Z0 F500\nG1 Y-10\nG3 X-10 Y0 I-10 J0\nG1 X-48\nG2 X-50 Y2 I0 J2\nG1 Y20\nG91\nG1 X5\nG0 Z50\n"
        if not hasattr(obj, "Active"):
            obj.addProperty("App::PropertyBool", "Active", "Gcode", "Active")
            obj.Active = True

        if not hasattr(obj, "FeedRate"):
            obj.addProperty("App::PropertySpeed", "FeedRate", "Feeds", "Feed rate")
            obj.FeedRate = "100.0 mm/min"  # mm/min par défaut

        if not hasattr(obj, "SpindleSpeed"):
            obj.addProperty("App::PropertySpeed", "SpindleSpeed", "Feeds", "Spindle speed")  # TODO  Speed changer en PropertyRotationalSpeed
            obj.SpindleSpeed = "1000.0 mm/min"  # tr/min par défaut

        if not hasattr(obj, "CoolantMode"):
            obj.addProperty("App::PropertyEnumeration", "CoolantMode", "Coolant", "Coolant mode")
            obj.CoolantMode = CoolantMode
            obj.CoolantMode = "Flood"  # Valeur par défaut

        # set property "Gcode" hidden
        obj.setEditorMode("Gcode", 2)

        # obj.Proxy = self

    def installToolProp(self, obj):
        if not hasattr(obj, "Tool"):
            obj.addProperty("App::PropertyLink", "Tool", "Op", "Tool")

        if int(App.Version()[0]) >= 1 and int(App.Version()[1]) >= 1:
            obj.setExpression('ToolDiameter', u'.Tool ? .Tool.Radius * 2 : 6')

    def onChanged(self, fp, prop):
        self.execute(fp)

    def execute(self, obj):
        self.cam_proj = BaptUtilities.find_cam_project(obj)
        pass

    def __getstate__(self):
        """Sérialisation"""
        return None

    def __setstate__(self, state):
        """Désérialisation"""
        return None


class repeatGcodeException(Exception):
    def __init__(self, message):
        super().__init__(self, message)
        self.message = message

    def __str__(self):
        return self.message

    pass


class baseOpViewProviderProxy:
    def __init__(self, obj):
        "Set this object as the proxy object of the actual view provider"
        # App.Console.PrintMessage("Initializing baseOpViewProviderProxy for: {}\n".format(__class__.__name__))
        self.deleteOnReject = True
        self.pick_radius = 5  # pixels
        self.icon = "BaptWorkbench.svg"

        BaptPref = BaptPreferences()

        if not hasattr(obj, "Rapid"):
            obj.addProperty("App::PropertyColor", "Rapid", "Gcode", "Color for rapid moves")
            obj.Rapid = BaptPref.DefaultRapidColor

        if not hasattr(obj, "Feed"):
            obj.addProperty("App::PropertyColor", "Feed", "Gcode", "Color for feed moves")
            obj.Feed = BaptPref.DefaultFeedColor

        # self.Object = obj.Object
        # obj.Proxy = self

    def onDocumentRestored(self, obj):
        """Appelé lors de la restauration du document"""
        raise Exception("Must be Overided")

    def onChanged(self, vp, prop):
        ''' Print the name of the property that has changed '''
        # Log.baptDebug("Change property: " + str(prop))
        if prop in "Rapid":
            r = vp.Rapid
            self.rapid_color.rgb.setValues(0, 1, [(r[0], r[1], r[2])])
            return
        if prop == "Feed":
            f = vp.Feed
            self.feed_color.rgb.setValues(0, 1, [(f[0], f[1], f[2])])
            return

    def __getstate__(self):
        ''' When saving the document this object gets stored using Python's cPickle module.
        Since we have some un-pickable here -- the Coin stuff -- we must define this method
        to return a tuple of all pickable objects or None.
        '''
        return None

    def __setstate__(self, state):
        ''' When restoring the pickled object from document we have the chance to set some
        internals here. Since no data were pickled nothing needs to be done here.
        '''
        return None

    def attach(self, obj):
        # App.Console.PrintMessage("Attaching view provider proxy to object: {}\n".format(__class__.__name__))
        self.pick_radius = 5
        self.Path = coin.SoGroup()

        self.rapid_group = coin.SoSeparator()
        self.rapid_color = coin.SoBaseColor()
        self.rapid_points = coin.SoCoordinate3()
        self.rapid_lines = coin.SoIndexedLineSet()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.SHAPE
        self.rapid_group.insertChild(pick, 0)
        self.rapid_group.addChild(self.rapid_color)
        self.rapid_group.addChild(self.rapid_points)
        self.rapid_group.addChild(self.rapid_lines)

        self.feed_group = coin.SoSeparator()
        self.feed_color = coin.SoBaseColor()
        self.feed_points = coin.SoCoordinate3()
        self.feed_lines = coin.SoIndexedLineSet()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.SHAPE
        self.feed_group.insertChild(pick, 0)
        self.feed_group.addChild(self.feed_color)
        self.feed_group.addChild(self.feed_points)
        self.feed_group.addChild(self.feed_lines)

        self.line_set_kind = {
            self.rapid_lines: "rapid",
            self.feed_lines: "feed",
        }
        # Créer le groupe pour le cône de direction
        self.direction_group = coin.SoSeparator()
        self.direction_switch = coin.SoSwitch()  # Pour montrer/cacher le cône
        self.direction_translation = coin.SoTranslation()
        self.direction_rotation = coin.SoRotation()
        self.direction_color = coin.SoBaseColor()

        # Créer le cône
        self.direction_cone = coin.SoCone()
        self.direction_cone.height = 2
        self.direction_cone.bottomRadius = 0.5

        # Assembler le groupe du cône
        self.direction_group.addChild(self.direction_translation)
        self.direction_group.addChild(self.direction_rotation)
        self.direction_group.addChild(self.direction_color)
        self.direction_group.addChild(self.direction_cone)
        self.direction_switch.addChild(self.direction_group)
        self.direction_switch.whichChild = coin.SO_SWITCH_NONE  # Cacher par défaut

        # Ajouter les événements de souris
        self.mouse_cb = coin.SoEventCallback()
        # self.mouse_cb.setCallback(self.mouse_event_cb)

        # self.mouse_cb.addEventCallback(coin.SoLocation2Event.getClassTypeId(), self.mouse_event_cb)

        self.Path.addChild(self.rapid_group)
        self.Path.addChild(self.feed_group)

        self.Path.addChild(self.direction_switch)
        self.Path.addChild(self.mouse_cb)

        # self.color = coin.SoBaseColor()
        # self.points = coin.SoCoordinate3()
        # self.lines = coin.SoIndexedLineSet()
        # self.Path.addChild(self.points)
        # self.Path.addChild(self.color)
        # self.Path.addChild(self.lines)

        # view = FreeCADGui.ActiveDocument.ActiveView
        # sg = view.getSceneGraph()
        # sg.addChild(self.Path)
        obj.addDisplayMode(self.Path, "Path")

    def mouse_event_cb(self, user_data, event_callback):
        event = event_callback.getEvent()
        if not isinstance(event, coin.SoLocation2Event):
            return

        if not hasattr(self, "segment_metadata"):
            return

        pos = event.getPosition()
        view = Gui.ActiveDocument.ActiveView
        renderer = view.getViewer().getSoRenderManager().getViewportRegion()
        picking = coin.SoRayPickAction(renderer)
        picking.setPoint(pos)
        picking.setRadius(self.pick_radius)
        picking.apply(self.Path)
        App.Console.PrintMessage(f'mouse event cb 0\n')

        picked = picking.getPickedPoint()
        if picked is None:
            self.direction_switch.whichChild = coin.SO_SWITCH_NONE
            return

        App.Console.PrintMessage(f'mouse event cb 01\n')
        detail = picked.getDetail()
        if not isinstance(detail, coin.SoLineDetail):
            self.direction_switch.whichChild = coin.SO_SWITCH_NONE
            return

        App.Console.PrintMessage(f'mouse event cb 1\n')

        path = picked.getPath()
        kind = None
        if path is not None:
            line_set_kind = getattr(self, "line_set_kind", {})
            for i in range(path.getLength() - 1, -1, -1):
                node = path.getNode(i)
                kind = line_set_kind.get(node)
                if kind is not None:
                    break

        if kind is None or kind not in self.segment_metadata:
            self.direction_switch.whichChild = coin.SO_SWITCH_NONE
            return
        App.Console.PrintMessage(f'mouse event cb 2\n')

        line_index = detail.getLineIndex()
        segments = self.segment_metadata.get(kind, [])
        if not (0 <= line_index < len(segments)):
            self.direction_switch.whichChild = coin.SO_SWITCH_NONE
            return

        pt1, pt2 = segments[line_index]
        App.Console.PrintMessage(f'mouse event cb 3\n')

        default_color = (1.0, 0.0, 0.0) if kind == "rapid" else (0.0, 1.0, 0.0)
        view_obj = getattr(self.Object, "ViewObject", None)
        prop_color = None
        if view_obj is not None:
            prop_color = getattr(view_obj, kind.capitalize(), None)
        if prop_color is None:
            prop_color = getattr(self.Object, kind.capitalize(), default_color)
        if hasattr(prop_color, "x"):
            color = (prop_color.x, prop_color.y, prop_color.z)
        else:
            color = tuple(prop_color)

        mid_point = (
            (pt1[0] + pt2[0]) / 2.0,
            (pt1[1] + pt2[1]) / 2.0,
            (pt1[2] + pt2[2]) / 2.0,
        )
        self.direction_translation.translation.setValue(*mid_point)

        direction = (pt2[0] - pt1[0], pt2[1] - pt1[1], pt2[2] - pt1[2])
        length = (direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2) ** 0.5
        if length <= 1e-9:
            self.direction_switch.whichChild = coin.SO_SWITCH_NONE
            return

        dir_norm = (direction[0] / length, direction[1] / length, direction[2] / length)
        rot = coin.SbRotation(coin.SbVec3f(0, 0, 1), coin.SbVec3f(*dir_norm))
        self.direction_rotation.rotation.setValue(rot)

        h = max(length * 0.6, 2.0)
        r = max(h * 0.25, 0.2)
        try:
            self.direction_cone.height = h
            self.direction_cone.bottomRadius = r
        except AttributeError:
            pass

        self.direction_color.rgb.setValues(0, 1, [color])
        self.direction_switch.whichChild = 0

    def updateData(self, fp, prop):
        if prop == "Gcode":
            self.updatePathGeometry(fp)
            return

    def updatePathGeometry(self, fp):
        # if no Gcode property, nothing to do
        if not hasattr(self.Object, "Gcode"):
            return

        gcode_text = str(self.Object.Gcode or "")
        self.lines = [l.strip() for l in gcode_text.splitlines() if l.strip()]

        def parse_xyz(line: str, prev, absinc_mode=absinc.G90):
            """helper to parse coords in a G-code line (X Y Z)"""
            x, y, z = prev

            for token in line.split():
                if token.upper().startswith("X"):
                    try:
                        x = float(token[1:]) if absinc_mode == absinc.G90 else prev[0] + float(token[1:])
                    except:
                        pass
                elif token.upper().startswith("Y"):
                    try:
                        y = float(token[1:]) if absinc_mode == absinc.G90 else prev[1] + float(token[1:])
                    except:
                        pass
                elif token.upper().startswith("Z"):
                    try:
                        z = float(token[1:]) if absinc_mode == absinc.G90 else prev[2] + float(token[1:])
                    except:
                        pass
            return (x, y, z)

        # build coordinate lists and index arrays for each group
        rapid_coords = []
        rapid_idx = []
        feed_coords = []
        feed_idx = []

        toolChangePos = App.Vector(0, 0, 0)
        if hasattr(fp, "Proxy") and hasattr(fp.Proxy, "cam_proj"):
            cam_project = fp.Proxy.cam_proj
            if cam_project is not None and hasattr(cam_project, "toolChangePos"):
                toolChangePos = cam_project.toolChangePos
            else:
                Log.baptDebug("No CamProject found for Op object {}".format(self.Object.Name))

        # current position (start at tool change position)
        self.cur = (toolChangePos.x, toolChangePos.y, toolChangePos.z)

        self.ordered_segments = []
        self.segment_metadata = {"rapid": [], "feed": []}

        self.comp_mode = comp.G40  # default cutter compensation off
        self.absinc_mode = absinc.G90  # default absolute mode
        self.mem = memory()
        self.line = 0
        self.pending_chamfer = None  # Pour stocker le chanfrein en attente (distance CHF)
        self.pending_rnd = None  # Pour stocker l'arrondi en attente (rayon RND)

        def parse_chf_rnd(line: str):
            """Parse CHF (chamfer) and RND (rounding) commands"""
            chf = None
            rnd = None
            up = line.upper()

            # Chercher CHF (chanfrein)
            if "CHF" in up:
                try:
                    idx = up.index("CHF")
                    # Extraire la valeur après CHF
                    rest = up[idx+3:].strip()
                    if rest and (rest[0].isdigit() or rest[0] == '.'):
                        # Extraire le nombre
                        num_str = ""
                        for c in rest:
                            if c.isdigit() or c == '.' or c == '-':
                                num_str += c
                            else:
                                break
                        if num_str:
                            chf = float(num_str)
                except (ValueError, IndexError):
                    pass

            # Chercher RND (arrondi)
            if "RND" in up:
                try:
                    idx = up.index("RND")
                    # Extraire la valeur après RND
                    rest = up[idx+3:].strip()
                    if rest and (rest[0].isdigit() or rest[0] == '.'):
                        # Extraire le nombre
                        num_str = ""
                        for c in rest:
                            if c.isdigit() or c == '.' or c == '-':
                                num_str += c
                            else:
                                break
                        if num_str:
                            rnd = float(num_str)
                except (ValueError, IndexError):
                    pass

            return chf, rnd

        def parse_ijr(line: str, prev):
            """helper to parse I/J/R (center offsets or radius)"""
            I = J = R = None
            for token in line.split():
                t = token.upper()
                if t.startswith("I"):
                    try:
                        if t.startswith("I=AC("):
                            I = float(token[5:-1]) - prev[0]
                            continue
                        I = float(token[1:])
                    except:
                        pass
                elif t.startswith("J"):
                    try:
                        if t.startswith("J=AC("):
                            J = float(token[5:-1]) - prev[1]
                            continue
                        J = float(token[1:])
                    except:
                        pass
                elif t.startswith("R"):
                    try:
                        R = float(token[1:])
                    except:
                        pass
                elif t.startswith("CR="):
                    try:
                        R = float(token[3:])
                    except:
                        pass
            return I, J, R

        def centers_from_radius(p0, p1, R):
            """compute circle centers from radius R (returns one center that matches direction if requested)"""
            (x1, y1) = (p0[0], p0[1])
            (x2, y2) = (p1[0], p1[1])
            dx = x2 - x1
            dy = y2 - y1
            d2 = dx*dx + dy*dy
            if d2 == 0.0:
                return None  # identical points
            d = math.sqrt(d2)
            if d > 2.0 * R + 1e-12:
                return None  # impossible with given radius
            # midpoint
            mx = (x1 + x2) / 2.0
            my = (y1 + y2) / 2.0
            # distance from midpoint to center
            h = math.sqrt(max(R*R - (d/2.0)*(d/2.0), 0.0))
            ux = -dy / d
            uy = dx / d
            c1 = (mx + ux * h, my + uy * h)
            c2 = (mx - ux * h, my - uy * h)
            return c1, c2

        def append_segment(coords_list, idx_list, a, b):
            """helper to append a segment to a group's arrays"""
            i = len(coords_list)
            coords_list.append(a)
            coords_list.append(b)
            idx_list.extend([i, i+1, -1])
            group = "rapid" if coords_list is rapid_coords else "feed"
            self.ordered_segments.append((group, a, b))
            self.segment_metadata[group].append((a, b))

        def _create_chamfer(coords_list, idx_list, p0, p1, chf_dist):
            """
            Crée un chanfrein entre le segment précédent et le segment actuel.
            Le chanfrein coupe le coin au point p0 (point de jonction)
            chf_dist: distance du chanfrein depuis le point de jonction

            Cette fonction:
            1. Modifie rétroactivement le dernier point du segment précédent pour le raccourcir
            2. Crée le segment de chanfrein
            3. Crée le segment actuel qui commence après le chanfrein
            """
            # Vérifier qu'il y a un segment précédent à modifier
            if len(coords_list) < 2:
                # Pas de segment précédent, créer un segment normal
                append_segment(coords_list, idx_list, p0, p1)
                return

            # Calculer le vecteur directionnel du segment actuel
            dx_next = p1[0] - p0[0]
            dy_next = p1[1] - p0[1]
            dz_next = p1[2] - p0[2]
            length_next = math.sqrt(dx_next*dx_next + dy_next*dy_next + dz_next*dz_next)

            if length_next < chf_dist:
                Log.baptWarning(f"Chamfer distance {chf_dist} is larger than next segment length {length_next}. Using normal segment.")
                append_segment(coords_list, idx_list, p0, p1)
                return

            # Récupérer le point précédent (avant-dernier point dans coords_list)
            p_prev = coords_list[-2]

            # Calculer le vecteur directionnel du segment précédent
            dx_prev = p0[0] - p_prev[0]
            dy_prev = p0[1] - p_prev[1]
            dz_prev = p0[2] - p_prev[2]
            length_prev = math.sqrt(dx_prev*dx_prev + dy_prev*dy_prev + dz_prev*dz_prev)

            if length_prev < chf_dist:
                Log.baptWarning(f"Chamfer distance {chf_dist} is larger than previous segment length {length_prev}. Using normal segment.")
                append_segment(coords_list, idx_list, p0, p1)
                return

            # Point avant le chanfrein (raccourcir le segment précédent)
            t_prev = (length_prev - chf_dist) / length_prev
            before_chf = (
                p_prev[0] + dx_prev * t_prev,
                p_prev[1] + dy_prev * t_prev,
                p_prev[2] + dz_prev * t_prev
            )

            # Point après le chanfrein (début du segment actuel)
            t_next = chf_dist / length_next
            after_chf = (
                p0[0] + dx_next * t_next,
                p0[1] + dy_next * t_next,
                p0[2] + dz_next * t_next
            )

            # Modifier rétroactivement le dernier point du segment précédent
            coords_list[-1] = before_chf

            # Ajouter le segment de chanfrein
            append_segment(coords_list, idx_list, before_chf, after_chf)

            # Ajouter le segment actuel
            append_segment(coords_list, idx_list, after_chf, p1)

        def _create_rounding(coords_list, idx_list, p0, p1, rnd_radius):
            """
            Crée un arrondi au point de jonction p0 entre le segment précédent et le segment actuel.
            Approxime l'arc par plusieurs petits segments
            rnd_radius: rayon de l'arrondi

            Cette fonction:
            1. Modifie rétroactivement le dernier point du segment précédent
            2. Crée plusieurs segments pour approximer l'arc arrondi
            3. Crée le segment actuel qui commence après l'arrondi
            """
            # Vérifier qu'il y a un segment précédent à modifier
            if len(coords_list) < 2:
                append_segment(coords_list, idx_list, p0, p1)
                return

            # Calculer le vecteur directionnel du segment actuel
            dx_next = p1[0] - p0[0]
            dy_next = p1[1] - p0[1]
            dz_next = p1[2] - p0[2]
            length_next = math.sqrt(dx_next*dx_next + dy_next*dy_next + dz_next*dz_next)

            # Récupérer le point précédent
            p_prev = coords_list[-2]

            # Calculer le vecteur directionnel du segment précédent
            dx_prev = p0[0] - p_prev[0]
            dy_prev = p0[1] - p_prev[1]
            dz_prev = p0[2] - p_prev[2]
            length_prev = math.sqrt(dx_prev*dx_prev + dy_prev*dy_prev + dz_prev*dz_prev)

            # Distance de tangence (approximation simple : rayon = distance)
            tang_dist = rnd_radius

            if length_prev < tang_dist or length_next < tang_dist:
                Log.baptWarning(f"Rounding radius {rnd_radius} is too large for segments. Using normal segment.")
                append_segment(coords_list, idx_list, p0, p1)
                return

            # Point de début de l'arc (raccourcir le segment précédent)
            t_prev = (length_prev - tang_dist) / length_prev
            arc_start = (
                p_prev[0] + dx_prev * t_prev,
                p_prev[1] + dy_prev * t_prev,
                p_prev[2] + dz_prev * t_prev
            )

            # Point de fin de l'arc (début du segment actuel)
            t_next = tang_dist / length_next
            arc_end = (
                p0[0] + dx_next * t_next,
                p0[1] + dy_next * t_next,
                p0[2] + dz_next * t_next
            )

            # Modifier rétroactivement le dernier point du segment précédent
            coords_list[-1] = arc_start

            # Créer un arc circulaire simple
            # Le centre de l'arc est à l'intersection des perpendiculaires à arc_start et arc_end
            # passant par ces points à distance rnd_radius

            # Vecteurs unitaires des deux segments en 2D
            u_prev_x = dx_prev / length_prev
            u_prev_y = dy_prev / length_prev
            u_next_x = dx_next / length_next
            u_next_y = dy_next / length_next

            # Vecteur de arc_start vers arc_end
            chord_x = arc_end[0] - arc_start[0]
            chord_y = arc_end[1] - arc_start[1]
            chord_len = math.sqrt(chord_x*chord_x + chord_y*chord_y)

            if chord_len > 1e-6:
                # Milieu de la corde
                mid_x = (arc_start[0] + arc_end[0]) / 2.0
                mid_y = (arc_start[1] + arc_end[1]) / 2.0

                # Vecteur perpendiculaire à la corde (vers le centre)
                perp_x = -chord_y / chord_len
                perp_y = chord_x / chord_len

                # Distance du milieu de la corde au centre (théorème de Pythagore)
                # rnd_radius² = (chord_len/2)² + h²
                half_chord = chord_len / 2.0
                if rnd_radius > half_chord:
                    h = math.sqrt(rnd_radius * rnd_radius - half_chord * half_chord)

                    # Déterminer le sens (le centre doit être du côté "intérieur" de l'angle)
                    # Produit vectoriel pour savoir de quel côté
                    cross = u_prev_x * u_next_y - u_prev_y * u_next_x
                    if cross < 0:
                        h = -h

                    # Centre de l'arc
                    cx = mid_x + perp_x * h
                    cy = mid_y + perp_y * h

                    # Créer l'arc avec plusieurs segments
                    num_segments = max(3, min(20, int(rnd_radius * 2)))

                    # Angles de départ et de fin
                    angle_start = math.atan2(arc_start[1] - cy, arc_start[0] - cx)
                    angle_end = math.atan2(arc_end[1] - cy, arc_end[0] - cx)

                    # Calculer la différence d'angle (sens le plus court)
                    angle_diff = angle_end - angle_start
                    if angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    elif angle_diff < -math.pi:
                        angle_diff += 2 * math.pi

                    # Générer les points sur l'arc
                    prev_point = arc_start
                    for i in range(1, num_segments + 1):
                        t = i / num_segments
                        angle = angle_start + angle_diff * t

                        seg_point = (
                            cx + rnd_radius * math.cos(angle),
                            cy + rnd_radius * math.sin(angle),
                            arc_start[2] + (arc_end[2] - arc_start[2]) * t
                        )
                        append_segment(coords_list, idx_list, prev_point, seg_point)
                        prev_point = seg_point
                else:
                    # Rayon trop petit pour la corde, ligne droite
                    append_segment(coords_list, idx_list, arc_start, arc_end)
            else:
                # Points identiques, ligne droite
                append_segment(coords_list, idx_list, arc_start, arc_end)

            # Ajouter le segment actuel
            append_segment(coords_list, idx_list, arc_end, p1)

        def executeCycle():
            new = self.cur

            if self.mem.current_cycle["type"] == 81 or self.mem.current_cycle["type"] == 84:

                a = list(new[0:2])
                a.append(self.mem.current_cycle["Z"])
                new = tuple(a)

                append_segment(feed_coords, feed_idx, self.cur, new)
                self.cur = new
                a = list(new[0:2])
                a.append(self.mem.current_cycle["R"])
                new = tuple(a)
                append_segment(rapid_coords, rapid_idx, self.cur, new)
                self.cur = new

            elif self.mem.current_cycle["type"] == 83:
                start_z = self.cur[-1]
                final_Z = self.mem.current_cycle["Z"]
                done = start_z
                prisePasse = self.mem.current_cycle["Q"]
                while done > final_Z:
                    done = done-prisePasse
                    if done < final_Z:
                        prisePasse = final_Z
                    a = list(new[0:2])
                    a.append(done)
                    new = tuple(a)

                    append_segment(feed_coords, feed_idx, self.cur, new)
                    self.cur = new
                    a = list(new[0:2])
                    a.append(self.mem.current_cycle["R"])
                    new = tuple(a)
                    append_segment(rapid_coords, rapid_idx, self.cur, new)
                    self.cur = new

            else:
                raise ValueError()

        def interpretArg(arg: str):
            ''' arg : X+0 retourne ('X', 0)'''
            ''' arg : X=R0 Retourne ('X', le contenu de la variable R0)'''
            ''' arg : X=(10 + R0) Retourne ('X', 10 + le contenu de la variable R0)'''
            ''' arg : X=(10 + 5)*2 Retourne ('X', retourne le resultat de l'expression)'''

            if not arg:
                return None, None

            arg = arg.strip()
            cursor = 0

            # Extraire le nom de l'argument (lettres au début)
            argName = ""
            while cursor < len(arg) and arg[cursor].isalpha():
                argName += arg[cursor].upper()
                cursor += 1

            if not argName:
                return None, None

            # Le reste est la valeur
            value_str = arg[cursor:].strip()

            if not value_str:
                return argName, None

            # Cas 1: Simple nombre (X+10, X-5, X10.5)
            if value_str[0] in ['+', '-', '.'] or value_str[0].isdigit():
                try:
                    num_str = value_str.replace(',', '.')
                    value = float(num_str) if '.' in num_str else int(num_str)
                    return argName, value
                except ValueError:
                    pass

            # Cas 2: Référence à variable (X=R0)
            if value_str.startswith('='):
                var_name = value_str[1:].strip()
                if var_name.startswith('R') and var_name[1:].isdigit():
                    # Récupérer la valeur de la variable
                    if var_name in self.mem.variables:
                        return argName, self.mem.variables[var_name]
                    else:
                        Log.baptWarning(f"Variable {var_name} not defined")
                        return argName, 0

            # Cas 3: Expression (X=(10 + R0), X=(10 + 5)*2)
            if '(' in value_str or 'R' in value_str.upper():
                try:
                    # Remplacer les variables R par leurs valeurs
                    expr = value_str.replace('=', '').strip()

                    # Remplacer R0, R1, etc. par leurs valeurs
                    import re

                    def replace_var(match):
                        var_name = match.group(0)
                        if var_name in self.mem.variables:
                            return str(self.mem.variables[var_name])
                        else:
                            Log.baptWarning(f"Variable {var_name} not defined, using 0")
                            return "0"

                    expr = re.sub(r'R\d+', replace_var, expr)

                    # Évaluer l'expression mathématique
                    # Sécurité: seulement les opérations de base
                    allowed_chars = set('0123456789+-*/().() ')
                    if all(c in allowed_chars for c in expr.replace(' ', '')):
                        value = eval(expr)
                        return argName, float(value) if isinstance(value, float) else int(value)
                    else:
                        Log.baptWarning(f"Invalid expression: {expr}")
                        return argName, 0
                except Exception as e:
                    Log.baptWarning(f"Error evaluating expression {value_str}: {e}")
                    return argName, 0

            # Cas par défaut: essayer de parser comme nombre
            try:
                value_str = value_str.replace(',', '.')
                value = float(value_str) if '.' in value_str else int(value_str)
                return argName, value
            except ValueError:
                Log.baptWarning(f"Cannot parse argument: {arg}")
                return argName, 0

        def processGcode():
            while self.line < len(self.lines):

                if len(self.mem.queue) > 0:
                    # App.Console.PrintMessage("Checking memory queue for line {}\n".format(self.line))
                    if self.line == self.mem.queue[0]:
                        self.mem.queue.popleft()
                        break

                ln = self.lines[self.line]
                # App.Console.PrintMessage("Processing line {}: {}\n".format(self.line, ln))
                self.line += 1
                up = ln.upper()
                # consider only movement commands G0/G00 and G1/G01
                if up.startswith(("G0", "G00")):
                    new = parse_xyz(ln, self.cur, self.absinc_mode)
                    append_segment(rapid_coords, rapid_idx, self.cur, new)
                    self.cur = new
                    self.mem.moveMode = "rapid"
                    if self.mem.current_cycle is not None:
                        executeCycle()

                elif up.startswith(("G1", "G01")):
                    new = parse_xyz(ln, self.cur, self.absinc_mode)

                    # Si un chanfrein ou arrondi était en attente depuis la ligne précédente
                    if self.pending_chamfer is not None:
                        # Créer un chanfrein entre self.cur et new
                        _create_chamfer(feed_coords, feed_idx, self.cur, new, self.pending_chamfer)
                        self.pending_chamfer = None
                    elif self.pending_rnd is not None:
                        # Créer un arrondi entre self.cur et new
                        _create_rounding(feed_coords, feed_idx, self.cur, new, self.pending_rnd)
                        self.pending_rnd = None
                    else:
                        # Pas de chanfrein/arrondi, segment normal
                        append_segment(feed_coords, feed_idx, self.cur, new)

                    self.cur = new

                    # Détecter CHF et RND dans la ligne pour le PROCHAIN segment
                    chf, rnd = parse_chf_rnd(ln)
                    if chf is not None:
                        self.pending_chamfer = chf
                    if rnd is not None:
                        self.pending_rnd = rnd

                    self.mem.moveMode = "feed"
                    if self.mem.current_cycle is not None:
                        executeCycle()

                elif up.startswith(("G2", "G02", "G3", "G03")):
                    # Circular interpolation. Prefer I/J (center offsets). If only R given, compute center(s).
                    is_ccw = up.startswith(("G3", "G03"))
                    end = parse_xyz(ln, self.cur, self.absinc_mode)
                    I, J, R = parse_ijr(ln, self.cur)
                    self.mem.moveMode = "arc"
                    # if no XY endpoint given, skip (cannot handle)
                    if (end[0], end[1]) == (self.cur[0], self.cur[1]):
                        # nothing to do if no movement in XY
                        self.cur = (end[0], end[1], end[2])
                        continue

                    center = None
                    radius = None
                    if I is not None or J is not None:
                        # center relative to start
                        i_val = I or 0.0
                        j_val = J or 0.0
                        cx = self.cur[0] + i_val
                        cy = self.cur[1] + j_val
                        center = (cx, cy)
                        radius = math.hypot(self.cur[0] - cx, self.cur[1] - cy)
                    elif R is not None:
                        # compute possible centers from R
                        cs = centers_from_radius(self.cur, end, R)
                        if cs is None:
                            # fallback to linear if impossible
                            append_segment(feed_coords, feed_idx, self.cur, end)
                            self.cur = end
                            continue
                        # choose center that yields correct direction (G2 cw => negative sweep)
                        c1, c2 = cs
                        # compute sweeps for both centers

                        def compute_sweep(c):
                            sx = math.atan2(self.cur[1]-c[1], self.cur[0]-c[0])
                            ex = math.atan2(end[1]-c[1], end[0]-c[0])
                            sweep = ex - sx
                            return sweep, sx, ex
                        s1, s1s, s1e = compute_sweep(c1)
                        s2, s2s, s2e = compute_sweep(c2)
                        # normalize sweeps

                        def norm_sweep(s):
                            if is_ccw:
                                if s <= 0:
                                    s += 2*math.pi
                            else:
                                if s >= 0:
                                    s -= 2*math.pi
                            return s
                        ns1 = norm_sweep(s1)
                        ns2 = norm_sweep(s2)
                        # choose the center with smaller absolute normalized sweep
                        if abs(ns1) <= abs(ns2):
                            center = c1
                            radius = R
                        else:
                            center = c2
                            radius = R
                    else:
                        # no center info -> fallback to linear
                        Log.baptDebug("G2/G3 command without I/J or R info; treating as linear move")
                        append_segment(feed_coords, feed_idx, self.cur, end)
                        self.cur = end
                        continue

                    # now we have center and radius
                    cx, cy = center

                    r = radius
                    if r <= 1e-12:
                        append_segment(feed_coords, feed_idx, self.cur, end)
                        self.cur = end
                        continue

                    # compute start and end angles
                    start_ang = math.atan2(self.cur[1] - cy, self.cur[0] - cx)
                    end_ang = math.atan2(end[1] - cy, end[0] - cx)
                    # compute sweep based on direction
                    if is_ccw:
                        sweep = end_ang - start_ang
                        if sweep <= 0:
                            sweep += 2 * math.pi
                    else:
                        sweep = end_ang - start_ang
                        if sweep >= 0:
                            sweep -= 2 * math.pi

                    # choose segment density: ~5° per segment or more for large arcs
                    seg_angle = math.radians(5.0)
                    nseg = max(1, int(math.ceil(abs(sweep) / seg_angle)))
                    z0 = self.cur[2]
                    z1 = end[2]
                    for i in range(1, nseg + 1):
                        ang = start_ang + sweep * (i / float(nseg))
                        x = cx + r * math.cos(ang)
                        y = cy + r * math.sin(ang)
                        z = z0 + (z1 - z0) * (i / float(nseg))
                        new_pt = (x, y, z)
                        append_segment(feed_coords, feed_idx, self.cur, new_pt)
                        self.cur = new_pt

                    # ensure final endpoint exact
                    if (abs(self.cur[0]-end[0]) > 1e-9) or (abs(self.cur[1]-end[1]) > 1e-9) or (abs(self.cur[2]-end[2]) > 1e-9):
                        append_segment(feed_coords, feed_idx, self.cur, end)
                        self.cur = end

                elif up.startswith("G40"):
                    self.comp_mode = comp.G40
                elif up.startswith("G41"):
                    self.comp_mode = comp.G41
                elif up.startswith("G42"):
                    self.comp_mode = comp.G42

                elif up.startswith("G80"):
                    self.mem.current_cycle = None

                elif up.startswith("G81"):
                    up.removeprefix("G81")
                    tokens = up.split(" ")
                    d = dict()
                    for t in tokens:
                        if t.upper().startswith("X"):
                            d["X"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("Y"):
                            d["Y"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("Z"):
                            d["Z"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("R"):
                            d["R"] = float(t[1:])
                    self.mem.current_cycle = {"type": 81, "Z": d["Z"], "R": d["R"]}
                    executeCycle()

                elif up.startswith("G83"):
                    up.removeprefix("G83")
                    tokens = up.split(" ")
                    d = dict()
                    for t in tokens:
                        if t.upper().startswith("X"):
                            d["X"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("Y"):
                            d["Y"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("Z"):
                            d["Z"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("R"):
                            d["R"] = float(t[1:])
                        if t.upper().startswith("Q"):
                            d["Q"] = float(t[1:])
                            if d["Q"] <= 0:
                                raise ValueError()
                    self.mem.current_cycle = {"type": 83, "Z": d["Z"], "R": d["R"], "Q": d["Q"]}
                    executeCycle()

                elif up.startswith("G84"):
                    # tapping cycle
                    code = int(up[1:3])
                    up = up[3:]

                    tokens = up.split(" ")
                    d = dict()
                    for t in tokens:
                        if t.upper().startswith("X"):
                            d["X"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("Y"):
                            d["Y"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("Z"):
                            d["Z"] = float(t[1:]) if self.mem.absincMode == absinc.G90 else self.cur + float(t[1:])
                        if t.upper().startswith("R"):
                            d["R"] = float(t[1:])
                    if any(k in d for k in ['X', 'Y', 'Z']):  # TODO: Process Move with all [G81-G89] cycle
                        new = (d.get("X", self.cur[0]), d.get("Y", self.cur[1]), d.get("R"))
                        append_segment(rapid_coords, rapid_idx, self.cur, new)
                        self.cur = new
                    self.mem.current_cycle = {"type": 84, "Z": d["Z"], "R": d["R"]}
                    executeCycle()

                elif up.startswith("G90"):
                    self.absinc_mode = absinc.G90
                elif up.startswith("G91"):
                    self.absinc_mode = absinc.G91

                elif up.startswith("M30"):
                    # program end
                    break

                elif up[0].isalpha() and up.endswith(":"):
                    # label declaration
                    label = up[:-1]
                    # store label with current line number
                    self.mem.addLabel(label, self.line)

                elif up.startswith("REPEAT"):
                    # repeat command
                    parts = up.split()
                    label_begin = None
                    n_times = 1
                    label_end = None

                    if len(parts) == 2:  # REPEAT Start
                        label_begin = parts[1] if len(parts) > 1 else None
                        n_times = 1
                        if not label_begin in self.mem.labels:
                            raise repeatGcodeException("Invalid REPEAT syntax, label for start not found")
                    elif len(parts) == 3:  # REPEAT Start P=
                        label_begin = parts[1] if len(parts) > 1 else None

                        if not label_begin in self.mem.labels:
                            raise repeatGcodeException("Invalid REPEAT syntax, label for start not found")

                        if not parts[2].startswith("P="):
                            raise repeatGcodeException("Invalid REPEAT syntax, expected P= for number of times")

                        n_times = parts[2].removeprefix("P=")

                        if n_times.isdigit():
                            n_times = int(n_times)
                        elif n_times.startswith("R"):
                            var_name = "R{}".format(n_times[1:])
                            if var_name in self.mem.variables:
                                n_times = int(self.mem.variables[var_name])
                            else:
                                raise repeatGcodeException("Variable {} not defined for REPEAT".format(var_name))
                    elif len(parts) == 4:  # REPEAT Start End P=
                        label_begin = parts[1]

                        if not label_begin in self.mem.labels:
                            raise repeatGcodeException("Invalid REPEAT syntax, label for start not found")

                        label_end = parts[2]
                        if not label_end in self.mem.labels:
                            raise repeatGcodeException("Invalid REPEAT syntax, label for end not found")
                        if not parts[3].startswith("P="):
                            raise repeatGcodeException("Invalid REPEAT syntax, expected P= for number of times")

                        n_times = parts[3].removeprefix("P=")
                        if n_times.isdigit():
                            n_times = int(n_times)
                        elif n_times.startswith("R"):
                            var_name = "R{}".format(n_times[1:])
                            if var_name in self.mem.variables:
                                n_times = int(self.mem.variables[var_name])
                            else:
                                raise repeatGcodeException("Variable {} not defined for REPEAT".format(var_name))
                    else:
                        pass
                    # App.Console.PrintMessage("REPEAT command found: label={} times={}\n".format(label_begin, n_times))

                    if label_begin is not None and label_begin in self.mem.labels:
                        start_line = self.mem.labels[label_begin]
                        # App.Console.PrintMessage("REPEAT label {} found at line {}\n".format(label_begin, start_line))
                        for _ in range(n_times):
                            # reset line to start_line and process until we reach the label_end or original line

                            if label_end is not None and label_end in self.mem.labels:

                                saved_line = self.mem.labels[label_end] - 1
                                restore = self.line
                                self.line = start_line

                            else:
                                saved_line = self.line-1
                                self.line = start_line
                                restore = saved_line

                            self.mem.queue.append(saved_line)

                            processGcode()
                            self.line = restore  # restore original line after repeat
                            # App.Console.PrintMessage(f'sortie de boucle ligne {self.lines[self.line]}\n')
                        pass
                    else:
                        App.Console.PrintMessage("REPEAT label {} not found\n".format(label_begin))
                        raise Exception("REPEAT label {} not found".format(label_begin))

                elif up.startswith("R"):
                    # variable
                    # up.removeprefix("R")
                    number = int(up[1:up.index("=")])
                    value = float(up[up.index("=")+1:])
                    # if not hasattr(fp, "R{}".format(number)):
                    #     App.Console.PrintMessage("Adding property R{} to object\n".format(number))
                    try:
                        # fp.addProperty("App::PropertyFloat", "R{}".format(number), "Gcode", "Variable R{}".format(number))
                        # setattr(fp, "R{}".format(number), value)
                        self.mem.variables["R{}".format(number)] = value
                    except:
                        pass

                    pass

                elif up.startswith("(") or up.startswith(";"):
                    # comment line, ignore
                    pass
                elif any(t.upper().startswith(("X", "Y", "Z")) for t in ln.split()):
                    new = parse_xyz(ln, self.cur)
                    if self.mem.moveMode == "rapid":
                        append_segment(rapid_coords, rapid_idx, self.cur, new)
                    elif self.mem.moveMode == "feed":
                        append_segment(feed_coords, feed_idx, self.cur, new)
                    self.cur = new
                    if self.mem.current_cycle is not None:
                        executeCycle()
                else:

                    Log.baptDebug("Ignoring line: {}\n".format(ln))

        try:
            processGcode()
        except repeatGcodeException as e:
            Log.baptError("Error processing REPEAT command: {}".format(str(e)))

        # store coords for callbacks/picking
        self.rapid_coords = rapid_coords
        self.feed_coords = feed_coords

        # set rapid nodes
        self.rapid_lines.coordIndex.setValue(0)
        self.rapid_points.point.setValues(0, 0, [])
        if rapid_coords:
            self.rapid_points.point.setValues(0, len(rapid_coords), rapid_coords)
            self.rapid_lines.coordIndex.setValues(0, len(rapid_idx), rapid_idx)
            # set single color for rapid group from object's property
            color = getattr(self.Object.ViewObject, "Rapid", getattr(self.Object, "Rapid", (1.0, 0.0, 0.0)))
            self.rapid_color.rgb.setValues(0, 1, [color])
        else:
            # clear
            self.rapid_points.point.setValues(0, 0, [])
            self.rapid_lines.coordIndex.setValues(0, 0, [])

        # set feed nodes
        self.feed_lines.coordIndex.setValue(0)
        self.feed_points.point.setValues(0, 0, [])
        if feed_coords:
            self.feed_points.point.setValues(0, len(feed_coords), feed_coords)
            self.feed_lines.coordIndex.setValues(0, len(feed_idx), feed_idx)
            color = getattr(self.Object.ViewObject, "Feed", getattr(self.Object, "Feed", (0.0, 1.0, 0.0)))
            self.feed_color.rgb.setValues(0, 1, [color])
        else:
            self.feed_points.point.setValues(0, 0, [])
            self.feed_lines.coordIndex.setValues(0, 0, [])

    def setupContextMenu(self, vobj, menu):
        """Configuration du menu contextuel"""
        action = menu.addAction("Edit")
        action.triggered.connect(lambda: self.setEdit(vobj))

        action2 = menu.addAction("Simulate Toolpath")
        action2.triggered.connect(lambda: self.startSimulation(vobj))

        action_Toggle = QtGui.QAction(Gui.getIcon("Std_TransformManip.svg"), "Desactive Op" if vobj.Object.Active else "Active Op", menu)
        QtCore.QObject.connect(action_Toggle, QtCore.SIGNAL("triggered()"), lambda: self.ToggleOp(vobj))
        menu.addAction(action_Toggle)
        return True

    def ToggleOp(self, vobj):
        vobj.Object.Active = not vobj.Object.Active

    def setDeleteOnReject(self, val):
        self.deleteOnReject = val
        return self.deleteOnReject

    def setEdit(self, vobj):
        """Open the editor for the Gcode property"""
        # must be overrided
        raise Exception("Must be Overided")
        self.deleteOnReject = False

    def startSimulation(self, vobj):
        """Start the G-code simulation animation"""
        vp = vobj.Proxy
        # vp.animator = GcodeAnimator(vp)
        # vp.animator.load_paths(include_rapid=True)
        # vp.animator.start(speed_mm_s=20.0)

        control = GcodeAnimationControl([vobj.Proxy.Object])
        # control.show()
        Gui.Control.showDialog(control)

    def doubleClicked(self, vobj):
        self.setEdit(vobj)
        return True

    def getDisplayModes(self, obj):
        "Return a list of display modes."
        modes = ["Path"]
        return modes

    def getDefaultDisplayMode(self):
        "Return the name of the default display mode. It must be defined in getDisplayModes."
        return "Path"

    def setDisplayMode(self, mode):
        return mode
