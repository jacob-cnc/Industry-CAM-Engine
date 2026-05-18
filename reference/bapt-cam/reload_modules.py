import FreeCAD as App
import importlib
import sys


def reload_modules():
    """Recharge les modules du workbench Bapt"""
    try:
        # Liste des modules à recharger
        modules_to_reload = [
            "BaptGeometry",
            "BaptContourTaskPanel",

        ]

        # Recharger chaque module
        for module_name in modules_to_reload:
            if module_name in sys.modules:
                App.Console.PrintMessage(f"Rechargement du module {module_name}...\n")
                importlib.reload(sys.modules[module_name])
            else:
                App.Console.PrintMessage(f"Chargement initial du module {module_name}...\n")
                __import__(module_name)

        App.Console.PrintMessage("Tous les modules ont été rechargés avec succès!\n")
        return True
    except Exception as e:
        App.Console.PrintError(f"Erreur lors du rechargement des modules: {str(e)}\n")
        return False


# Exécuter le rechargement lorsque ce script est exécuté directement
if __name__ == "__main__":
    reload_modules()
