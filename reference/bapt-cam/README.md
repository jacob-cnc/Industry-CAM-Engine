# Bapt's CAM Workbench

This is a workbench for FreeCAD that adds CAM (Computer Aided Manufacturing) features.

Let me introduce myself: I'm Bapt.

In my professional life, I've been a programmer/machinist for 10 years now, working on various CNC machines (DMG, Huron, etc.) and in various programming languages ​​(Heidenhain, Siemens, etc.).

And in my personal life, I'm very interested in software programming.

Therefore, I wanted to develop software that would meet my needs, and I found FreeCAD to be a very good basis for developing my own MOD.

![Bapt's CAM Workbench Screenshot v0.0.1](/resources/image.bmp)

![Bapt's CAM Workbench Screenshot v0.0.3](/resources/Animation.gif)

![Bapt's CAM Workbench Screenshot v0.1.2](/resources/image3.png)

## Philosophy and goal

1. After working for several years on a numerically controlled machine and CAD software to create programs, I found that it was easier to first correctly create machining geometries before actually defining machining cycles. This is why in this project it is necessary to create "DrillGeometry" and "ContourGeometry" objects.

## TODO's

[ ] create an automatic drill recognition feature that will group all holes with the same diameter and create the corresponding "drillGeometry" objects
[ ] create an object "Path" who represent a gcode path and allows its visualization
    [ ] implement G41/G42 commands (ultime goal)
    [ ] implement M90/M91 commands
    
## Installation

1. Copy the folder `Bapt` into the `Mod` folder of your FreeCAD installation.
2. Restart FreeCAD.

## Usage

1. Select the `Bapt` workbench from the `Workbenches` dropdown menu.
2. Use the commands provided in the `Bapt` workbench.

## Commands

- ![](/resources/icons/BaptWorkbench.svg) `Bapt_CreateCamProject`: Create a new CAM project.
- ![](/resources/icons/Tree_HoleRecognition.svg) `Bapt_HoleRecognition`
- ![](/resources/icons/Tree_Drilling.svg)`Bapt_CreateDrillGeometry`: Create a new drill geometry.
- ![](/resources/icons/Tree_Drilling.svg)`Bapt_CreateDrillCycle`: Create a new drill cycle.
- ![](/resources/icons/Tree_Contour.svg)`Bapt_CreateContournageGeometry`: Create a new contournage geometry.
- ![](/resources/icons/Contournage.svg)`Bapt_CreateContournageCycle`: Create a new contournage cycle.
- ![](/resources/icons/Surfacage.svg)`Bapt_CreateSurfacageCycle`: Create a new surfacage cycle.
- ![](/resources/icons/PostProcess.svg)`Bapt_PostProcess`: PostProcess
- ![](/resources/icons/ProbeSurface.svg)`Bapt_ProbeSurface`: Probe
- `Bapt_CreateHotReload`: Hot reload the workbench.

## License

This workbench is released under the MIT license.
