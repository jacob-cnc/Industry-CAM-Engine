@echo off
setlocal enabledelayedexpansion

echo Creation du lien symbolique pour le dossier examples...

:: Définir les chemins
:: set "SOURCE_DIR=%~dp0examples"
set "SOURCE_DIR=%~dp0"
set "SOURCE_DIR=%SOURCE_DIR:~0,-1%"
::set "TARGET_DIR=%APPDATA%\FreeCAD\v1-2\Mod\Bapt_CAM"
set "TARGET_DIR=%APPDATA%\FreeCAD\Mod\Bapt_CAM"

:: Vérifier que le dossier source existe
if not exist "%SOURCE_DIR%" (
    echo ERREUR: Le dossier source n'existe pas: %SOURCE_DIR%
    pause
    exit /b 1
)

:: Créer le dossier parent si nécessaire
if not exist "%APPDATA%\FreeCAD\Mod" (
    echo Creation du dossier %APPDATA%\FreeCAD\Mod
    mkdir "%APPDATA%\FreeCAD\Mod"
)


:: Créer le dossier parent si nécessaire
if not exist "%APPDATA%\FreeCAD\v1-1\Mod" (
    echo Creation du dossier %APPDATA%\FreeCAD\v1-1\Mod
    mkdir "%APPDATA%\FreeCAD\v1-1\Mod"
)

:: Supprimer le lien existant s'il existe
if exist "%TARGET_DIR%" (
    echo Suppression du lien existant...
    rmdir "%TARGET_DIR%" 2>nul
)

:: Créer le lien symbolique
echo Creation du lien symbolique...
echo Source: %SOURCE_DIR%
echo Cible:  %TARGET_DIR%

mklink /D "%TARGET_DIR%" "%SOURCE_DIR%"

if %ERRORLEVEL% == 0 (
    echo.
    echo ✓ Lien symbolique créé avec succès!
    echo Les exemples sont maintenant accessibles dans FreeCAD via:
    echo %TARGET_DIR%
) else (
    echo.
    echo ✗ Erreur lors de la création du lien symbolique.
    echo Assurez-vous d'exécuter ce script en tant qu'administrateur.
)

echo.
pause