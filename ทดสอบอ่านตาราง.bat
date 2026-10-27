@echo off
setlocal
cd /d "%~dp0"
title K-ROOM - Safe Read Test

echo Safe test only: this file will NOT send commands to speakers.
echo It loads the schedule once and prints the bookings it can read.
echo.

where py.exe >nul 2>nul
if errorlevel 1 goto no_python

py room_speaker_monitor.py --once
if errorlevel 1 echo The test ended with an error. Read the message above.
goto keep_open

:no_python
echo Python Launcher py.exe was not found. Run the installer first.

:keep_open
echo.
echo Type EXIT and press Enter to close this window.
cmd /k
endlocal
