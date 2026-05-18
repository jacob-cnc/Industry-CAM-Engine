import FreeCAD as App


def create_tool_obj(id=0, name="New Tool", diameter=10.0, speed=1000.0, feed=500.0):
    new_tool = App.ActiveDocument.addObject("Part::Cylinder", f"T{id} {name}")
    new_tool.addProperty("App::PropertyInteger", "Id", "Tool", "Tool ID").Id = id
    new_tool.addProperty("App::PropertyString", "Name", "Tool", "Tool Name").Name = name
    new_tool.addProperty("App::PropertySpeed", "Speed", "Tool", "Tool Speed").Speed = f"{speed} mm/min"
    new_tool.addProperty("App::PropertySpeed", "Feed", "Tool", "Tool Feed").Feed = f"{feed} mm/min"
    new_tool.Radius = diameter / 2.0
    return new_tool
