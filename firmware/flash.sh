#!/usr/bin/env bash
# Lalit Stock Application - compile and flash the ESP32 E-Paper firmware, then open the serial monitor.
# Owner: Lalit Nayyar. Not financial advice.
# Linux/macOS counterpart of flash.bat.
# Usage: firmware/flash.sh [PORT] [PANEL]
#   PORT   default: first /dev/ttyUSB* or /dev/ttyACM* (pass "" to auto-detect and still choose a panel)
#   PANEL  290_4c (default, WeAct 2.9in 4-colour) | 420_bw | 420_bwr | 420_4c (WeAct 4.2in 400x300)
#   NO_MONITOR=1 skips the serial monitor.
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../tools/esp32_flash.sh
source "$HERE/../tools/esp32_flash.sh"

panel="$(printf '%s' "${2:-290_4c}" | tr '[:upper:]' '[:lower:]')"
case "$panel" in
  290_4c) panel=290_4C ;;
  420_bw) panel=420_BW ;;
  420_bwr) panel=420_BWR ;;
  420_4c) panel=420_4C ;;
  *) echo "Unknown panel '${2:-}'. Use 290_4c, 420_bw, 420_bwr or 420_4c." >&2; exit 2 ;;
esac
echo "Building for panel $panel"
ESP32_BUILD_FLAGS="-DLS_PANEL=LS_PANEL_$panel" \
  esp32_flash "$HERE/LalitStockFirmware" "esp32:esp32:esp32:PartitionScheme=min_spiffs" "${1:-}" \
  "GxEPD2" "Adafruit GFX Library" "ArduinoJson"
