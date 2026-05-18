import FreeCAD as App
import FreeCADGui as Gui


class PointSelectionObserver:
    def __init__(self, callback):
        self.callback = callback
        self.active = False

    def enable(self):
        """Activer l'observer"""
        self.active = True
        Gui.Selection.addObserver(self)
        App.Console.PrintMessage("Observer activé. Cliquez sur un point de la pièce.\n")

    def disable(self):
        """Désactiver l'observer"""
        self.active = False
        Gui.Selection.removeObserver(self)
        App.Console.PrintMessage("Observer désactivé.\n")

    def addSelection(self, document, object, element, position):
        """Appelé quand l'utilisateur sélectionne quelque chose"""
        if not self.active:
            return

        # Récupérer les coordonnées du point sélectionné
        point = App.Vector(position[0], position[1], position[2])
        App.Console.PrintMessage(f"Point sélectionné: {point.x}, {point.y}, {point.z}\n")

        # Appeler le callback avec le point
        self.callback(point)

        # Désactiver l'observer après la sélection
        self.disable()
