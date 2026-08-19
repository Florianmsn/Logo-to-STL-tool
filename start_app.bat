@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Logo to STL Tool 9.0

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD (
    where python3 >nul 2>nul
    if not errorlevel 1 (
        python3 -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python3"
    )
)
if not defined PYTHON_CMD (
    echo ERROR: Python was not found.
    echo Run build_exe.bat for detailed installation hints.
    pause
    exit /b 1
)

%PYTHON_CMD% logo_inlay_app.py
if errorlevel 1 (
    echo.
    echo The application exited with an error.
    pause
)
