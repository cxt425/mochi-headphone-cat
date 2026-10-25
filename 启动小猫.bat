@echo off
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if errorlevel 1 (
    echo Python was not found.
    echo Please install Python 3.9 or newer from https://www.python.org/
    pause
    exit /b 1
)

python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo PySide6 is not installed.
    echo Please run: pip install PySide6
    pause
    exit /b 1
)

where pythonw.exe >nul 2>nul
if errorlevel 1 (
    start "" python.exe "%~dp0cat_pet.py"
) else (
    start "" pythonw.exe "%~dp0cat_pet.py"
)
exit /b 0
