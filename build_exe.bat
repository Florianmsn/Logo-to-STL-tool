@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Logo to STL Tool 9.0 EXE Builder

echo.
echo ============================================
echo   Logo to STL Tool 9.0 - EXE Builder
echo ============================================
echo.

rem ------------------------------------------------------------
rem Find a real Python installation.
rem Prefer the Windows Python Launcher because "python.exe"
rem may only be the Microsoft Store App Execution Alias.
rem ------------------------------------------------------------
set "PYTHON_CMD="

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; print(sys.executable)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; print(sys.executable)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    where python3 >nul 2>nul
    if not errorlevel 1 (
        python3 -c "import sys; print(sys.executable)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python3"
    )
)

if not defined PYTHON_CMD goto :NO_PYTHON

echo Python found:
%PYTHON_CMD% -c "import sys; print('  ' + sys.executable); print('  Python ' + sys.version.split()[0])"
echo.

rem ------------------------------------------------------------
rem Make sure pip is available.
rem ------------------------------------------------------------
%PYTHON_CMD% -m pip --version >nul 2>nul
if errorlevel 1 (
    echo pip was not found. Trying to install/repair pip...
    %PYTHON_CMD% -m ensurepip --upgrade
    if errorlevel 1 goto :PIP_FAILED
)

echo Installing/updating required packages...
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :REQUIREMENTS_FAILED

echo.
echo Checking PyInstaller...
%PYTHON_CMD% -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is missing. Installing it...
    %PYTHON_CMD% -m pip install pyinstaller
    if errorlevel 1 goto :PYINSTALLER_FAILED
)

rem ------------------------------------------------------------
rem Remove an old EXE first so a failed build can never look
rem successful just because an older file is still in dist.
rem ------------------------------------------------------------
if exist "dist\Logo to STL Tool 9.0.exe" (
    echo Removing old EXE...
    del /q "dist\Logo to STL Tool 9.0.exe"
)

echo.
echo Building EXE...
%PYTHON_CMD% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "Logo to STL Tool 9.0" ^
    --hidden-import=shapely ^
    --hidden-import=trimesh ^
    logo_inlay_app.py

if errorlevel 1 goto :BUILD_FAILED

if not exist "dist\Logo to STL Tool 9.0.exe" goto :BUILD_FAILED

echo.
echo ============================================
echo   BUILD SUCCESSFUL
echo ============================================
echo.
echo Created:
echo   %~dp0dist\Logo to STL Tool 9.0.exe
echo.
pause
exit /b 0


:NO_PYTHON
echo.
echo ============================================
echo   ERROR: Python was not found
echo ============================================
echo.
echo The builder checked:
echo   py -3
echo   python
echo   python3
echo.
echo Please install a 64-bit Python 3 version from python.org.
echo During installation, enable:
echo   "Add python.exe to PATH"
echo   and preferably
echo   "Install launcher for all users"
echo.
echo If Python is already installed, Windows may be using the
echo Microsoft Store App Execution Alias instead of the real Python.
echo You can disable the python.exe / python3.exe aliases under:
echo   Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo.
pause
exit /b 1


:PIP_FAILED
echo.
echo ERROR: pip could not be installed or repaired.
echo.
pause
exit /b 2


:REQUIREMENTS_FAILED
echo.
echo ERROR: Installing requirements.txt failed.
echo Check the messages above for the package that caused the problem.
echo.
pause
exit /b 3


:PYINSTALLER_FAILED
echo.
echo ERROR: PyInstaller could not be installed.
echo.
pause
exit /b 4


:BUILD_FAILED
echo.
echo ============================================
echo   ERROR: EXE build failed
echo ============================================
echo.
echo No successful new EXE was created.
echo Check the messages above for the actual PyInstaller error.
echo.
pause
exit /b 5
