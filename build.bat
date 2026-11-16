@echo off
rem Builds dist\OcarinaTranslator.exe (single file, no Python needed to run it).
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name OcarinaTranslator ^
  --collect-all vgamepad ^
  --collect-all sounddevice ^
  --collect-all soundcard ^
  --exclude-module scipy --exclude-module matplotlib --exclude-module pandas ^
  app.py
echo.
echo Built: %~dp0dist\OcarinaTranslator.exe
