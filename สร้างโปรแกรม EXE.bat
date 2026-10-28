@echo off
setlocal
cd /d "%~dp0"
title LabBoy Coworking - Build EXE

where py.exe >nul 2>nul
if errorlevel 1 goto no_python

echo Installing build dependencies...
py -3 -m pip install -r "%~dp0requirements-build.txt"
if errorlevel 1 goto build_failed

echo.
echo Building the room monitor executable...
py -3 -m PyInstaller --noconfirm --clean --onefile --name room_speaker_monitor --runtime-hook "%~dp0pyinstaller_hooks\monitor_utf8_stdio.py" --distpath "%~dp0build\release" --workpath "%~dp0build\monitor" --specpath "%~dp0build" --add-data "%~dp0room_devices.example.json;." "%~dp0room_speaker_monitor.py"
if errorlevel 1 goto build_failed

echo Checking Thai UTF-8 output from the packaged monitor without audio...
py -3 "%~dp0tests\smoke_monitor_exe.py"
if errorlevel 1 goto build_failed

echo.
echo Building the desktop WebView executable...
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name labboy_coworking_broadcast --icon "%~dp0labboy-coworking-broadcast.ico" --distpath "%~dp0build\release" --workpath "%~dp0build\gui" --specpath "%~dp0build" --add-data "%~dp0logo_broadcast.png;." --add-data "%~dp0labboy-coworking-broadcast.ico;." --add-data "%~dp0fonts;fonts" --add-data "%~dp0web;web" --add-data "%~dp0room_devices.example.json;." --collect-all customtkinter --collect-all webview --collect-submodules pystray --hidden-import web_ui "%~dp0labboy_coworking_broadcast.py"
if errorlevel 1 goto build_failed

echo.
echo Build complete. Both EXE files are in build\release:
echo   labboy_coworking_broadcast.exe
echo   room_speaker_monitor.exe
echo Close the current app and run the update BAT file to install this build.
goto keep_open

:no_python
echo Python Launcher py.exe was not found. Install Python for building the EXE.
goto keep_open

:build_failed
echo Build failed. Read the error output above before sharing the EXE.

:keep_open
echo.
echo Press any key to close this window.
pause >nul
endlocal
