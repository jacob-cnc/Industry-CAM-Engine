# based on file "Path/Op/Gui/Base.py" and
# src/Mod/CAM/Path/Base/Gui/Util.py
import FreeCAD as App
import FreeCADGui as Gui
import PySide.QtGui as QtGui
import PySide.QtCore as QtCore
from utils import Log

DEBUG = False


class BQuantitySpinBox(QtCore.QObject):
    def __init__(self, obj, prop, widget=None):
        super().__init__()
        # try:
        self.obj = obj
        self.prop = prop
        if widget is not None:
            self.widget = widget
        else:
            self.widget = Gui.UiLoader().createWidget("Gui::QuantitySpinBox")
        self.attach(obj, prop)

    def attach(self, obj, prop):
        # App.Console.PrintMessage(f'Attach\n')
        # self.widget.setProperty("unit", "mm")
        attr = self.getProperty(obj, prop)  # getattr(obj, prop) semble etre equivalent
        if attr is not None:
            if hasattr(attr, "Value"):
                self.widget.setProperty("unit", attr.getUserPreferred()[2])

                self.widget.setProperty("rawValue", attr.Value)
            else:
                self.widget.setProperty("rawValue", attr)
        # self.widget.setProperty("Value", a)
            # if widget is  not None:
            if True:
                self.widget.setProperty("binding", "%s.%s" % (obj.Name, prop))
            else:
                Gui.ExpressionBinding(self.widget).bind(obj, prop)
        else:
            pass
            # self.widget.setProperty("exprSet", "true")
        # self.widget.style().unpolish(self.widget)
        # self.widget.ensurePolished()
        # Gui.ExpressionBinding(self.recouvrement).bind(self.obj,"Recouvrement")
        self.widget.installEventFilter(self)
        # self.widget.textChanged.connect(lambda: self.onWidgetValueChanged())
        self.widget.valueChanged.connect(lambda: self.updateValue())
        # except Exception as e:
        #     App.Console.PrintError("BQuantitySpinBox __init__ error: {}\n".format(e))

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.FocusIn:
            self.updateWidget()
        return False

    def getProperty(self, obj, prop):
        """getProperty(obj, prop) ... answer obj's property defined by its canonical name."""
        o, attr, name = self._getProperty(obj, prop)
        return attr

    def _getProperty(self, obj, prop):
        o = obj
        attr = obj
        name = None
        for name in prop.split("."):
            o = attr
            if not hasattr(o, name):
                break
            attr = getattr(o, name)

        if o == attr:
            # Path.Log.debug(translate("PathGui", "%s has no property %s (%s)") % (obj.Label, prop, name))
            return (None, None, None)

        # Path.Log.debug("found property %s of %s (%s: %s)" % (prop, obj.Label, name, attr))
        # App.Console.PrintMessage(f'found property {prop} of {obj.Label} ({name}: {attr})\n')
        return (o, attr, name)

    def updateWidget(self):
        expr = self._hasExpression()
        attr = self.getProperty(self.obj, self.prop)  # getattr(obj, prop) semble etre equivalent

        # self.widget.setProperty("rawValue", getattr(self.obj, self.prop))
        if attr is not None:
            if hasattr(attr, "Value"):
                self.widget.setProperty("unit", attr.getUserPreferred()[2])
                self.widget.setProperty("rawValue", attr.Value)
                # Log.baptDebug(f'update Widget {self.obj.Name}.{self.prop} Value={attr.Value} unit={attr.getUserPreferred()[2]}\n')
            else:
                self.widget.setProperty("rawValue", attr)
            self.widget.setProperty("binding", "%s.%s" % (self.obj.Name, self.prop))
            # Gui.ExpressionBinding(self.widget).bind(self.obj, self.prop)

        if expr:
            self.widget.setProperty("exprSet", "true")
            self.widget.style().unpolish(self.widget)
            self.widget.ensurePolished()
        else:
            self.widget.setProperty("exprSet", "false")
            self.widget.style().unpolish(self.widget)
            self.widget.ensurePolished()
        self.widget.update()

    def getWidget(self):
        return self.widget

    def updateValue(self):
        value = self.widget.property("rawValue")
        o, attr, name = self._getProperty(self.obj, self.prop)
        attrValue = attr.Value if hasattr(attr, "Value") else attr

        if DEBUG:
            Log.baptDebug(f'update Value current {attrValue} new {value}\n')
            Log.baptDebug(f'update Value o {o} attr {attr} name {name}\n')

        if attrValue != value:
            self.updateProperty()

            if o and name:
                if type(attr) == int:
                    value = int(value)
                setattr(o, name, value)
        # if hasattr(self.obj, self.prop):
        #     App.Console.PrintMessage(f'update Value hasattr\n')
        #     value = self.widget.property("rawValue")
        #     setattr(self.obj, self.prop, value)
        # # except Exception as e:
        # #     App.Console.PrintError("BQuantitySpinBox updateValue error: {}\n".format(e))

    def onWidgetValueChanged(self):
        App.Console.PrintMessage(f'Widget Value Changed\n')
        if hasattr(self.obj, self.prop):
            App.Console.PrintMessage(f'Widget Value Changed hasattr\n')
            value = self.widget.property("rawValue")
            setattr(self.obj, self.prop, value)
        # self.widget.editingFinished.emit()

    def updateProperty(self):
        return
        value = self.widget.property("rawValue")
        setattr(self.obj, self.prop, value)
        self.widget.update()
        pass

    def _hasExpression(self):
        for prop, exp in self.obj.ExpressionEngine:
            if prop == self.prop:
                return exp
        return None

    def setValue(self, value):
        attr = self.getProperty(self.obj, self.prop)
        if hasattr(self.obj, self.prop):
            setattr(self.obj, self.prop, value)
            self.updateWidget()
        # except Exception as e:
        #     App.Console.PrintError("BQuantitySpinBox setValue error: {}\n".format(e))
