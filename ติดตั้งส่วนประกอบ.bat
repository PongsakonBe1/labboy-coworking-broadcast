@echo off
setlocal
cd /d "%~dp0"
title K-ROOM - Install Requirements

echo K-ROOM speaker monitor setup
echo.

where py.exe >nul 2>nul
if errorlevel 1 goto no_python

echo [1/1] Installing Python packages, WebView UI, Pillow, and system tray support...
py -3 -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto install_failed

echo.
echo Setup completed. The app uses Microsoft Edge WebView2 Runtime for its interface.
echo If the window does not open, install the Microsoft Edge WebView2 Runtime.
goto keep_open

:no_python
echo Python Launcher py.exe was not found.
echo Install Python for Windows, then run this installer again.
goto keep_open

:install_failed
echo Python package installation failed.
echo Check your internet connection and Python installation.
goto keep_open

:keep_open
echo.
echo This window will stay open. Type EXIT and press Enter to close it.
cmd /k
endlocal

