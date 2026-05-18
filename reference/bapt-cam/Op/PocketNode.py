import FreeCAD as App
import Part
from utils.Contour import shiftWire


class noeud:
    """
    Docstring for noeud
    """

    def __init__(self, depth: int, j: int, wires: list[Part.Wire] = []):
        self.depth: int = depth
        self.j: int = j
        self.children: list['noeud'] = []
        self.wires: Part.Wire = wires
        self.hasChangend: bool = False
        self.visited: bool = False  # Marqueur pour le parcours

    def addChild(self, child: 'noeud'):
        self.children.append(child)

    def __repr__(self):
        return f"noeud({self.depth},{self.j}, {type(self.wires)} )"

    def printTree(self, level=0):
        print("  " * level + repr(self))
        for child in self.children:
            child.printTree(level + 1)

    def getWiresOrdonned(self):
        try:
            w = []
            w.append(self.wires)
            for child in self.children:
                w.append(child.getWiresOrdonned())
            return w
        except Exception as e:
            App.Console.PrintError(f"getWiresOrdonned erreur: {e}\n")
            return []

    def getWires(self):
        try:
            w = []
            w.append(self.wires)
            for child in self.children:
                w.extend(child.getWires())
            return w
        except Exception as e:
            App.Console.PrintError(f"getWires erreur: {e}\n")
            return []

    def isCCW(self):
        # Vérifie si le wire est dans le sens trigonométrique
        try:
            firstflipped = False
            if not self.wires.isClosed():
                raise ValueError("La wire n'est pas fermée.")
            area = 0.0
            for i, edge in enumerate(self.wires.Edges):

                if edge.Vertexes[-1].Point.distanceToPoint(self.wires.Edges[(i+1) % len(self.wires.Edges)].Vertexes[0].Point) < 1e-6 or \
                        edge.Vertexes[-1].Point.distanceToPoint(self.wires.Edges[(i+1) % len(self.wires.Edges)].Vertexes[-1].Point) < 1e-6:
                    # edge est dans le bon sens
                    # App.Console.PrintMessage(f'bon sens\n')
                    v1 = edge.Vertexes[0].Point
                    v2 = edge.Vertexes[-1].Point
                else:
                    if i == 0:
                        firstflipped = True
                    # edge est dans le sens inverse
                    # App.Console.PrintMessage(f'sens inverse\n')
                    v1 = edge.Vertexes[-1].Point
                    v2 = edge.Vertexes[0].Point

                area += (v1.x - v2.x) * (v1.y + v2.y)
                # App.Console.PrintMessage(f'area = {area}\n')
            return (area > 0)
        except Exception as e:
            # App.Console.PrintError(f"isCCW erreur: {e}\n")
            return True

    def shiftWire(self, new_start_point: App.Vector) -> Part.Wire:
        """reconstruit le wire en commençant par new_start_point"""
        first_edge = []
        next_edges = []

        self.wires = shiftWire(self.wires, new_start_point)
        self.hasChangend = True
        return self.wires
