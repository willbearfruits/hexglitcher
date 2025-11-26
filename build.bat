@echo off
REM HexGlitcher Build Script for Windows

echo ========================================
echo HexGlitcher Build Script
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

REM Run the build script
python build.py

echo.
echo Build complete! Check the dist\ folder for output.
pause
