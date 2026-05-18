from BaptPath import GcodeAnimator, GcodeEditorTaskPanel
import BaptUtilities
import FreeCAD as App
import FreeCADGui as Gui
from utils import Log
from Op.BaseOp import baseOp, baseOpViewProviderProxy


class pathOp(baseOp):
    def __init__(self, obj):
        App.Console.PrintMessage("Initializing path object proxy for: {}\n".format(__class__.__name__))
        super().__init__(obj)
        self.Type = "Path"

        obj.Proxy = self

        self.installToolProp(obj)

    def installAttachment(self, obj):
        obj.addProperty("App::PropertyPlacement", "Placement", "Base", "Description for tooltip")
        # obj.addExtension('App::GeoFeatureGroupExtensionPython')
        obj.addExtension('Part::AttachExtensionPython')

    def execute(self, obj):

        if hasattr(obj, "AttachmentSupport"):
            pass
            # obj.positionBySupport()

        return super().execute(obj)

    def onChanged(self, fp, prop):
        return
        return super().onChanged(fp, prop)

    def onDocumentRestored(self, obj):
        """Appelé lors de la restauration du document"""
        App.Console.PrintMessage("Restoring document for object: {}\n".format(obj.Name))
        self.__init__(obj)


class pathOpViewProviderProxy(baseOpViewProviderProxy):
    def __init__(self, vobj):
        App.Console.PrintMessage("Initializing path view provider proxy for: {}\n".format(__class__.__name__))
        super().__init__(vobj)

        self.Object = vobj.Object
        vobj.Proxy = self

    def attach(self, vobj):
        App.Console.PrintMessage("Attaching view provider proxy to object: {}\n".format(__class__.__name__))
        self.Object = vobj.Object
        return super().attach(vobj)

    # def setupContextMenu(self, vobj, menu):
    #     return super().setupContextMenu(vobj, menu)

    def getDefaultDisplayMode(self):
        return super().getDefaultDisplayMode()

    def setDisplayMode(self, mode):
        return super().setDisplayMode(mode)

    def getDisplayModes(self, vobj):
        return super().getDisplayModes(vobj)

    def getIcon(self):
        if not self.Object.Active:
            return BaptUtilities.getIconPath("operation_disabled.svg")

    def setEdit(self, vobj):
        # return super().setEdit(vobj)
        taskPanel = GcodeEditorTaskPanel(vobj.Object)
        Gui.Control.showDialog(taskPanel)

        return True


def create():
    doc = App.ActiveDocument
    if doc is None:
        doc = App.newDocument()
    obj = doc.addObject("App::FeaturePython", "Test")

    baseOp(obj)
    # obj.Gcode ="G0 X0 Y-20 Z50\nG0 Z2\nG1 Z0 F500\nG1 Y-10\nG3 X-10 Y0 I-10 J0\nG1 X-48\nG2 X-50 Y2 I0 J2\nG1 Y20\nG91\nG1 X5\nG0 Z50\nREPEAT LABEL1 P=2\n"

    obj.Gcode = "R1=10\nG0 X0 Y0 Z10\nG1 Z0 F500\nLABEL1:\nG91\nG1 Z-2\nG90\nG1 X10 Y0\nG1 X10 Y10\nG1 X0 Y10\nG1 X0 Y0\nREPEAT LABEL1 P=R1\nG0 Z10\n"
    baseOpViewProviderProxy(obj.ViewObject)

    vp = obj.ViewObject.Proxy
    vp.animator = GcodeAnimator(vp)
    vp.animator.load_paths(include_rapid=True)

    vp.animator.start(speed_mm_s=20.0)

    doc.recompute()
