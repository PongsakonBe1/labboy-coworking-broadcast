@echo off
setlocal
cd /d "%~dp0"
title LabBoy Coworking - Update
if not exist "%~dp0build\release\labboy_coworking_broadcast.exe" goto missing
if not exist "%~dp0build\release\room_speaker_monitor.exe" goto missing
if not exist "%~dp0update_app.ps1" goto missing
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_app.ps1"
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" exit /b 0
if "%RESULT%"=="2" exit /b 0
echo Update did not complete. Read the dialog for details.
goto done
:missing
echo Release files are missing. Run the EXE build script first.
goto done
:done
echo.
pause
endlocal
