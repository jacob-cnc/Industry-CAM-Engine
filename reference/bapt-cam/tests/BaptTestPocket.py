import FreeCAD as App
import FreeCADGui as Gui
import Part
import unittest
from Op.PocketNode import noeud
from utils.Contour import getFirstPoint, shiftWire

class TestNode(unittest.TestCase):
    def test01(self):
        """
        chekk if the node is CCW
        
        :param self: 
        """
        edges =[
            Part.makeLine(App.Vector(0,0,0), App.Vector(10,0,0)), 
            Part.makeLine(App.Vector(10,0,0), App.Vector(10,10,0)), 
            Part.makeLine(App.Vector(10,10,0), App.Vector(0,10,0)),
            Part.makeLine(App.Vector(0,10,0), App.Vector(0,0,0)),
        ]
        # bonSens = determineEdgeOrientation(wire)

        wire = Part.Wire(edges)
        n = noeud(0,0,wire)
        self.assertEqual(n.isCCW(), True)

    def test02(self):
        """
        chekk if the node is CCW even with reversed edges
        
        :param self:
        """
        edges =[
            Part.makeLine(App.Vector(0,0,0), App.Vector(10,0,0)), 
            Part.makeLine(App.Vector(10,10,0), App.Vector(10,0,0)), 
            Part.makeLine(App.Vector(10,10,0), App.Vector(0,10,0)),
            Part.makeLine(App.Vector(0,10,0), App.Vector(0,0,0)),
        ]
        # bonSens = determineEdgeOrientation(wire)

        wire = Part.Wire(edges)
        n = noeud(0,0,wire)
        self.assertEqual(n.isCCW(), True)

class TestShiftWire(unittest.TestCase):
    def test01(self):
        """
        test shiftWire function
        
        :param self: 
        """
        edges =[
            Part.makeLine(App.Vector(0,0,0), App.Vector(10,0,0)), 
            Part.makeLine(App.Vector(10,0,0), App.Vector(10,10,0)), 
            Part.makeLine(App.Vector(10,10,0), App.Vector(0,10,0)),
            Part.makeLine(App.Vector(0,10,0), App.Vector(0,0,0)),
        ]
        wire = Part.Wire(edges)
        new_start_point = App.Vector(5,10,0)
        new_wire = shiftWire(wire, new_start_point)
        new_edges = new_wire.Edges

        for  i, edge in enumerate(new_edges):
            print(f"Edge {i}: {edge.Vertexes[0].Point} to {edge.Vertexes[-1].Point}")

        self.assertEqual(len(new_edges), len(edges)+1)
        self.assertEqual(new_edges[0].Vertexes[0].Point.isEqual(new_start_point, 1e-6), True)

    def test02(self):

        edges =[
            Part.makeLine(App.Vector(0,0,0), App.Vector(10,0,0)), 
            Part.makeCircle(5,App.Vector(10,5,0),App.Vector(0,0,1),270,0),
            Part.makeLine(App.Vector(15,5,0), App.Vector(15,20,0)), 
            Part.makeLine(App.Vector(15,20,0), App.Vector(0,20,0)),
            Part.makeLine(App.Vector(0,20,0), App.Vector(0,0,0)),
        ]

        wire = Part.Wire(edges)
        
        new_start_point = App.Vector(10,5,0) + 5 * App.Vector(1,-1,0).normalize()  # Point at -45 degrees on the circle 
        App.Console.PrintMessage(f'test02 new_start_point = {new_start_point}\n')

        new_wire = shiftWire(wire, new_start_point)
        new_edges = new_wire.Edges
        self.assertEqual(len(new_edges), len(edges)+1)
        self.assertEqual(new_edges[0].Vertexes[getFirstPoint(new_edges)].Point.isEqual(new_start_point, 1e-6), True)

    def test03(self):
        App.Console.PrintMessage(f'Test 03\n')
        edges =[
            Part.makeLine(App.Vector(0,0,0), App.Vector(10,0,0)), 
            Part.makeCircle(5,App.Vector(10,-5,0),App.Vector(0,0,1),0,90),
            Part.makeLine(App.Vector(15,-5,0), App.Vector(15,-20,0)), 
            Part.makeLine(App.Vector(15,-20,0), App.Vector(0,-20,0)),
            Part.makeLine(App.Vector(0,-20,0), App.Vector(0,0,0)),
        ]

        wire = Part.Wire(edges)
        self.assertTrue(wire.isClosed())
        new_start_point = App.Vector(10,-5,0) + 5 * App.Vector(1,1,0).normalize()  # Point at -45 degrees on the circle 
        App.Console.PrintMessage(f'test03 new_start_point = {new_start_point}\n')

        new_wire = shiftWire(wire, new_start_point)
        new_edges = new_wire.Edges
        self.assertEqual(len(new_edges), len(edges)+1)
        self.assertEqual(new_edges[0].Vertexes[getFirstPoint(new_edges)].Point.isEqual(new_start_point, 1e-6), True)


