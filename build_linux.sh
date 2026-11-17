#!/usr/bin/env bash
# Builds dist/OcarinaTranslator (single file) on Linux. EXPERIMENTAL -- see README "Linux (experimental)".
set -euo pipefail
cd "$(dirname "$0")"
python3 -m PyInstaller --noconfirm --onefile --windowed --name OcarinaTranslator \
  --add-data "icon.png:." --add-data "games:games" \
  --collect-all sounddevice \
  --collect-all soundcard \
  --hidden-import gamepad_linux --hidden-import PIL._tkinter_finder \
  --exclude-module vgamepad --exclude-module pymem --exclude-module gamepad_win \
  --exclude-module scipy --exclude-module matplotlib --exclude-module pandas \
  app.py
echo
echo "Built: $(pwd)/dist/OcarinaTranslator"
