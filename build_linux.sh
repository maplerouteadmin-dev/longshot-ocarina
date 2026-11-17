#!/usr/bin/env bash
# Builds dist/OcarinaTranslator (single file) on Linux. EXPERIMENTAL -- see README "Linux (experimental)".
set -euo pipefail
cd "$(dirname "$0")"
python3 -m PyInstaller --noconfirm --onefile --windowed --name OcarinaTranslator \
  --add-data "icon.png:." \
  --collect-all sounddevice \
  --collect-all soundcard \
  --hidden-import gamepad_linux \
  --exclude-module vgamepad --exclude-module pymem --exclude-module gamepad_win \
  --exclude-module scipy --exclude-module matplotlib --exclude-module pandas \
  app.py
echo
echo "Built: $(pwd)/dist/OcarinaTranslator"
