@echo off
title Logo Inlay Tool 7.5 EXE Builder
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --onefile --windowed --name "Logo Inlay Tool 7.5" --hidden-import=shapely --hidden-import=trimesh logo_inlay_app.py
echo Done: dist\Logo Inlay Tool 7.5.exe
pause
