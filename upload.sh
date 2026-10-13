#!/usr/bin/env bash
# Lalit Stock Application - compile and upload the display-only ESP32_EPaper_Test sketch, then open the serial monitor.
# Owner: Lalit Nayyar. Not financial advice.
# Linux/macOS counterpart of upload.bat.
# Usage: ./upload.sh [PORT]   (default: first /dev/ttyUSB* or /dev/ttyACM*; NO_MONITOR=1 skips the monitor)
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/esp32_flash.sh
source "$HERE/tools/esp32_flash.sh"

esp32_flash "$HERE/ESP32_EPaper_Test" "esp32:esp32:esp32" "${1:-}" \
  "GxEPD2" "Adafruit GFX Library"
