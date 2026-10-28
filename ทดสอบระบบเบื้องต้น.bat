@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title LabBoy - Safe Basic Checks
where py.exe >nul 2>nul
if errorlevel 1 goto no_python
py -3 "%~dp0tests\run_basic_checks.py"
if errorlevel 1 echo Some checks failed. Read the report path above.
goto done
:no_python
echo These developer checks require Python and the existing project dependencies.
echo The normal LabBoy EXE does not require Python.
:done
echo.
echo Press any key to close this window.
pause >nul
endlocal
