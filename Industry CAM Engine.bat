@echo off
cd /d "c:\Users\jhonick\linuxcnc\Industry CAM Engine"

:: Clear Python bytecode cache to ensure latest code runs
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

python -m gui.main_window
pause
