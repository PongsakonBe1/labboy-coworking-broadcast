@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0labboy_coworking_broadcast.exe" (
    if not exist "%~dp0room_speaker_monitor.exe" (
        echo The bundled room_speaker_monitor.exe is missing. Rebuild the EXE package.
        pause
        exit /b 1
    )
    start "" "%~dp0labboy_coworking_broadcast.exe"
    exit /b 0
)
where py.exe >nul 2>nul
if errorlevel 1 goto no_python
py -3 -c "import customtkinter, PIL, webview, pystray" >nul 2>nul
if errorlevel 1 goto install_gui
where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pyw.exe -3 "%~dp0labboy_coworking_broadcast.py"
    exit /b 0
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0labboy_coworking_broadcast.py"
    exit /b 0
)
echo Python for Windows was not found. Please install Python first.
pause
endlocal
exit /b 1

:install_gui
echo The GUI packages are missing from Python 3.
echo Run the setup BAT file in this folder, then reopen this shortcut.
pause
endlocal
exit /b 1

:no_python
echo Python Launcher py.exe was not found. Install Python, then try again.
pause
endlocal
exit /b 1
