@echo off
title Logo to STL Tool 8.2 EXE Builder
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --onefile --windowed --name "Logo to STL Tool 8.2" --hidden-import=shapely --hidden-import=trimesh logo_inlay_app.py
echo Done: dist\Logo to STL Tool 8.2.exe
pause
