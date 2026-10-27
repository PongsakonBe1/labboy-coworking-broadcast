@echo off
setlocal
cd /d "%~dp0"
title K-ROOM Room Speaker Monitor
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_room_speaker_monitor.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Startup failed with exit code %RESULT%. Send a screenshot of this window for help.
echo Press any key to close this window.
pause >nul
endlocal
exit /b %RESULT%
