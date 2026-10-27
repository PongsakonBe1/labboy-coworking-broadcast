@echo off
setlocal
cd /d "%~dp0"
title LabBoy Coworking - Update
if not exist "%~dp0build\release\labboy_coworking_broadcast.exe" goto missing
if not exist "%~dp0build\release\room_speaker_monitor.exe" goto missing
echo Close LabBoy first, including its system tray icon.
echo This updater keeps your settings, password, log, and audio history.
echo.
pause
tasklist /FI "IMAGENAME eq room_speaker_monitor.exe" /FO CSV /NH | find /I "room_speaker_monitor.exe" >nul
if not errorlevel 1 goto running
tasklist /FI "IMAGENAME eq labboy_coworking_broadcast.exe" /FO CSV /NH | find /I "labboy_coworking_broadcast.exe" >nul
if not errorlevel 1 goto running
copy /Y "%~dp0build\release\room_speaker_monitor.exe" "%~dp0room_speaker_monitor.exe" >nul
if errorlevel 1 goto failed
copy /Y "%~dp0build\release\labboy_coworking_broadcast.exe" "%~dp0labboy_coworking_broadcast.exe" >nul
if errorlevel 1 goto failed
echo Update complete. Open your usual Desktop shortcut.
goto done
:running
echo LabBoy is still running. Choose Exit from the tray menu, then retry.
goto done
:missing
echo Release files are missing. Run the EXE build script first.
goto done
:failed
echo Update failed. Close the current app and retry.
:done
echo.
pause
endlocal
