@echo off
REM Convert to WebP (85%% quality) WITHOUT cropping.
REM Drag a folder of photos onto this file, or double-click it and enter a path.
REM Requires Python (https://python.org) with the packages in requirements.txt installed:
REM   py -m pip install -r requirements.txt

setlocal

set "TARGET=%~1"
if "%TARGET%"=="" (
    set /p TARGET=Enter the full path to the folder of photos:
)

py "%~dp0jewelry_crop.py" "%TARGET%" --quality 85 --no-crop

echo.
pause
