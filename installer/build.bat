@echo off
rem Builds dist\IgorSurface-Setup.exe (needs Python + PyInstaller + Pillow). Run from the repo root.
python -m PyInstaller --noconfirm --onefile --windowed --name IgorSurface-Setup ^
  --specpath build --icon %CD%IgorSurface\resources\quadPatch\32x32@2x.png ^
  --add-data "%CD%IgorSurface;IgorSurface" --distpath dist --workpath build installer\installer.py
