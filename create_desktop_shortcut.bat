@echo off
:: Creates a desktop shortcut for Industry CAM Engine on Windows
:: Run once: double-click this file

set SHORTCUT=%USERPROFILE%\Desktop\Industry CAM Engine.lnk
set TARGET=pythonw.exe
set ARGS=-m gui.main_window
set WORKDIR=c:\Users\jhonick\linuxcnc\Industry CAM Engine

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.Arguments = '%ARGS%'; $s.WorkingDirectory = '%WORKDIR%'; $s.Description = 'Industry CAM Engine - CNC Lathe CAM'; $s.Save()"

echo Desktop shortcut created: %SHORTCUT%
pause
