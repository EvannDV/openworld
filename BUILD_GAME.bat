@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title AETHERWILD - Construction du jeu
REM ===========================================================================================
REM  AETHERWILD : double-clique ce fichier. Il compile, prepare le monde et produit Aetherwild.exe
REM  Prerequis : Unreal Engine 5.6 (Epic Games Launcher) + Visual Studio 2022 "Developpement C++ de jeux"
REM  Duree : 1 a 3 heures la premiere fois (compilation des shaders). Le resultat : Build\Windows\Aetherwild.exe
REM ===========================================================================================
set "PROJ=%~dp0Aetherwild.uproject"
set "LOG=%~dp0Saved\BUILD_GAME.log"
if not exist "%~dp0Saved" mkdir "%~dp0Saved"
echo [%date% %time%] Debut > "%LOG%"

REM --- 1. Trouver Unreal Engine
if defined UE_ROOT goto :found
for %%V in (5.6 5.7 5.5 5.8) do (
  for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\EpicGames\Unreal Engine\%%V" /v InstalledDirectory 2^>nul ^| find "InstalledDirectory"') do (
    if not defined UE_ROOT set "UE_ROOT=%%b"
  )
)
if not defined UE_ROOT if exist "C:\Program Files\Epic Games\UE_5.6\Engine" set "UE_ROOT=C:\Program Files\Epic Games\UE_5.6"
if not defined UE_ROOT (
  echo ERREUR : Unreal Engine introuvable. Installe UE 5.6 via l'Epic Games Launcher,
  echo ou definis la variable UE_ROOT ^(ex. set UE_ROOT=D:\Epic\UE_5.6^).
  pause & exit /b 1
)
:found
echo Unreal Engine : %UE_ROOT%
echo UE_ROOT=%UE_ROOT% >> "%LOG%"

REM --- 2. Compiler le jeu + l'editeur
echo.
echo [1/3] Compilation du code C++ ...
call "%UE_ROOT%\Engine\Build\BatchFiles\Build.bat" AetherwildEditor Win64 Development -Project="%PROJ%" -WaitMutex -NoHotReloadFromIDE >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERREUR de compilation : envoie le fichier Saved\BUILD_GAME.log pour correction.
  pause & exit /b 1
)

REM --- 3. Preparer le monde dans l'editeur (terrain, materiaux, assets, vegetation, creatures)
echo [2/3] Preparation du monde ^(l'editeur va s'ouvrir puis se fermer tout seul^) ...
"%UE_ROOT%\Engine\Binaries\Win64\UnrealEditor.exe" "%PROJ%" -ExecutePythonScript="%~dp0Tools\Unreal\build_all.py" -unattended -nosplash >> "%LOG%" 2>&1
type "%~dp0Saved\build_all_status.txt" >> "%LOG%" 2>nul
findstr /c:"RESULTAT : SUCCES" "%~dp0Saved\build_all_status.txt" >nul
if errorlevel 1 (
  echo ATTENTION : la preparation du monde a rencontre un probleme ^(voir Saved\build_all_status.txt^). Le packaging continue.
)

REM --- 4. Packager l'executable
echo [3/3] Creation de l'executable ^(cuisson des assets et shaders : long la premiere fois^) ...
call "%UE_ROOT%\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun -project="%PROJ%" -noP4 -platform=Win64 -clientconfig=Shipping -build -cook -stage -pak -iostore -compressed -prereqs -archive -archivedirectory="%~dp0Build" -utf8output >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERREUR de packaging : envoie le fichier Saved\BUILD_GAME.log pour correction.
  pause & exit /b 1
)
echo.
echo ===============================================================
echo  TERMINE : %~dp0Build\Windows\Aetherwild.exe
echo ===============================================================
start "" "%~dp0Build\Windows"
pause
