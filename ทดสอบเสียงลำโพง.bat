@echo off
setlocal
cd /d "%~dp0"
title K-ROOM one-speaker test
cmd /k powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_speaker.ps1"
endlocal
