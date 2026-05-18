import BaptUtilities
import FreeCAD as App
import FreeCADGui as Gui
import Part

# source: https://github.com/FreeCAD/FreeCAD-macros/blob/master/Utility/HighlightCommon.FCMacro


class BaptHighlight:
    def __init__(self, obj):
        self.obj = obj

        if not hasattr(obj, "ObjectsToEnumerate"):
            obj.addProperty("App::PropertyLinkList", "ObjectsToEnumerate", "Highlight", "List of objects to highlight")

        obj.Proxy = self

    def onChanged(self, fp, prop):
        pass

    def execute(self, obj):

        # Ensure list of unique objects.
        object_list = []

        colli_grp = None  # Group object to group collisions.
        colli_max = 0  # Maximum collision volume.
        obj.Shape = Part.Shape()  # Clear shape of the feature.
        s = []
        for obj in obj.ObjectsToEnumerate:
            if ((obj not in object_list)
                    and hasattr(obj, 'Shape')
                    and hasattr(obj, 'getGlobalPlacement')
                    and hasattr(obj, 'Label')):
                object_list.append(obj)

        # Going through selected objects (object A).
        # App.Console.PrintMessage(f'{len(obj.ObjectsToEnumerate)}\n')
        App.Console.PrintMessage(f'{len(object_list)}\n')
        for i, object_a in enumerate(object_list):
            shape_a = object_a.Shape.copy()
            shape_a.Placement = object_a.getGlobalPlacement()
            label_a = object_a.Label

            # # Making selected objects transparent.
            # if change_transparency:
            #     try:
            #         object_a.ViewObject.Transparency = transparency
            #     except AttributeError:
            #         pass

            # Comparing object A with all
            # following ones in the list (object B).
            for object_b in object_list[(i + 1):]:

                shape_b = object_b.Shape.copy()
                shape_b.Placement = object_b.getGlobalPlacement()
                label_b = object_b.Label
                common = shape_a.common(shape_b)

                # Making selected objects transparent.
                # if change_transparency:
                #     try:
                #         object_b.ViewObject.Transparency = transparency
                #     except AttributeError:
                #         pass

                # If object A & object B have a collision
                # display a message with collision volume and
                # add a new representative shape in the group.
                if common.Volume > 1e-6:
                    App.Console.PrintMessage(
                        'Volume of the intersection between {} and {}: {:.3f} mm³\n'.format(
                            label_a,
                            label_b,
                            common.Volume))
                    colli_max = common.Volume if common.Volume > colli_max else colli_max
                    # if not colli_grp:
                    #     # Create group if it doesn't already exist.
                    #     colli_grp = doc.addObject('App::DocumentObjectGroup',
                    #                             'Collisions')
                    # intersection_object = doc.addObject(
                    #     'Part::Feature')
                    # intersection_object.Label = '{} - {}'.format(
                    #     label_a, label_b)
                    # intersection_object.Shape = common
                    # intersection_object.ViewObject.ShapeColor = (1.0, 0.0, 0.0, 1.0)
                    # colli_grp.addObject(intersection_object)
                    s.append(common)
                else:
                    # If no collision, just inform the user.
                    App.Console.PrintMessage(
                        'No intersection between {} and {}\n'.format(
                            label_a,
                            label_b))

        # If collisions have been found, commit the undo transaction and
        # give a summary (count + max value) to the user.
        obj.Shape = Part.Shape(s)
        if colli_grp:
            pass
            # doc.commitTransaction()
            # App.Console.PrintMessage(
            #     '{} collision(s) found between selected objects\nMaximum collision: {:.3f} mm³\n'.format(
            #         len(colli_grp.Group),
            #         colli_max))
            # doc.recompute()
        else:
            # If no collision has been found, just inform the user about it.
            # doc.abortTransaction()
            if len(object_list) >= 2:
                App.Console.PrintWarning('No collision found between selected objects\n')
            else:
                App.Console.PrintWarning('No suitable objects selected, select at least two objects\n')


class ViewProviderBaptHighlight:
    def __init__(self, obj):
        obj.Proxy = self

    def attach(self, obj):
        self.obj = obj.Object
        obj.ShapeColor = (1.0, 0.0, 0.0, 1.0)

    def updateData(self, fp, prop):
        pass

    def getDisplayModes(self, obj):
        modes = []
        return modes

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def getIcon(self):
        """Retourne l'icône"""
        return BaptUtilities.getIconPath("HighlightCommon.svg")


class CreateHighlightCommand:
    """Create Highlight object"""

    def GetResources(self):
        return {
            'MenuText': 'Highlight Collisions',
            'ToolTip': 'Create a Highlight object to detect and highlight collisions between selected objects',
            'Pixmap': BaptUtilities.getIconPath('BaptWorkbench.svg')
        }

    def IsActive(self):
        obj = Gui.activeView().getActiveObject("camproject")
        return obj is not None

    def Activated(self):
        doc = App.ActiveDocument
        project = Gui.activeView().getActiveObject("camproject")
        sel = Gui.Selection.getSelection()

        obj = doc.addObject("Part::FeaturePython", "Highlight_Collisions")
        doc.recompute()
        BaptHighlight(obj)
        if obj.ViewObject:
            ViewProviderBaptHighlight(obj.ViewObject)
        obj.ObjectsToEnumerate = sel
        doc.recompute()
        # Gui.ActiveDocument.setEdit(obj.Name)
