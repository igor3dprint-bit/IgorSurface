@echo off
rem IgorSurface installer: copies the add-in into Fusion's AddIns folder (Windows).
set "SRC=%~dp0IgorSurface"
if not exist "%SRC%\IgorSurface.py" (echo Pasta IgorSurface nao encontrada ao lado deste arquivo. & pause & exit /b 1)
set "DST=%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\IgorSurface"
robocopy "%SRC%" "%DST%" /MIR /XD __pycache__ /NFL /NDL /NJH /NJS >nul
if %ERRORLEVEL% GEQ 8 (echo Falhou a copia. & pause & exit /b 1)
echo IgorSurface instalado em:
echo   %DST%
echo.
echo No Fusion: Utilities ^> Add-Ins ^> aba Add-Ins ^> IgorSurface ^> Run
echo Marque "Run on Startup" para ele ligar sozinho.
pause
