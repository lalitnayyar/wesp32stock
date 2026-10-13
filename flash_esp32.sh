#!/usr/bin/env bash
# =============================================================================
# Lalit Stock Application - interactive ESP32 flashing wizard (Linux/macOS)
# Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973
# Disclaimer: informational software only, NOT financial advice.
#
# Asks for the E-Paper module, what to flash and the serial port, then runs
# firmware/flash.sh (Lalit Stock firmware) or upload.sh (display test).
# Non-interactive equivalents:  firmware/flash.sh /dev/ttyUSB0 420_bwr  /  ./upload.sh /dev/ttyUSB0 420_bwr
# =============================================================================
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ask() {  # ask PROMPT DEFAULT -> REPLY (fails when input is closed)
  local answer
  read -r -p "$1" answer || { echo; echo "No input; nothing was flashed." >&2; exit 2; }
  REPLY="${answer:-$2}"
}

echo
echo "=================================================================="
echo "  Lalit Stock Application - ESP32 flashing wizard"
echo "  Informational display only. Not financial advice."
echo "=================================================================="
echo
echo "Step 1/3 - Which E-Paper module is connected to the ESP32?"
echo
echo "  1. WeAct 2.9in 4-colour         168 x 384 portrait   GDEY029F51H / JD79667  [hardware-verified]"
echo "  2. WeAct 4.2in black/white      400 x 300 landscape  GDEY042T81 / SSD1683   fast refresh, ~32 s pages"
echo "  3. WeAct 4.2in black/white/red  400 x 300 landscape  GDEY042Z98 / SSD1683   ~60 s pages"
echo "  4. WeAct 4.2in 4-colour         400 x 300 landscape  GDEY0420F51 / HX8717   ~66 s pages"
echo
echo "  The module type is printed on the flex cable or the WeAct product page."
echo
while :; do
  ask "Select module [1-4, default 1]: " 1
  case "$REPLY" in
    1) PANEL=290_4c; PANEL_NAME="WeAct 2.9in 4-colour, 168x384"; break ;;
    2) PANEL=420_bw; PANEL_NAME="WeAct 4.2in black/white, 400x300"; break ;;
    3) PANEL=420_bwr; PANEL_NAME="WeAct 4.2in black/white/red, 400x300"; break ;;
    4) PANEL=420_4c; PANEL_NAME="WeAct 4.2in 4-colour, 400x300"; break ;;
    *) echo "  Please enter 1, 2, 3 or 4." ;;
  esac
done

echo
echo "Step 2/3 - What do you want to flash?"
echo
echo "  1. Lalit Stock firmware        normal use: setup portal, portfolio pages, admin page"
echo "  2. Display test (Hello World)  recommended first on a new module: checks wiring and driver"
echo
while :; do
  ask "Select [1-2, default 1]: " 1
  case "$REPLY" in
    1) SCRIPT="$HERE/firmware/flash.sh"; WHAT_NAME="Lalit Stock firmware"; break ;;
    2) SCRIPT="$HERE/upload.sh"; WHAT_NAME="Display test (Hello World)"; break ;;
    *) echo "  Please enter 1 or 2." ;;
  esac
done

echo
echo "Step 3/3 - Which serial port is the ESP32 on?"
echo
ports=()
for p in /dev/ttyUSB* /dev/ttyACM* /dev/cu.usbserial* /dev/cu.SLAB_USBtoUART* /dev/cu.wchusbserial*; do
  [[ -e "$p" ]] && ports+=("$p")
done
if ((${#ports[@]} == 0)); then
  echo "  No serial ports detected. Plug in the ESP32 USB cable, or type the port, e.g. /dev/ttyUSB0."
else
  for i in "${!ports[@]}"; do echo "  $((i + 1)). ${ports[$i]}"; done
fi
echo
while :; do
  ask "Select port [1-${#ports[@]} or a path, default 1]: " 1
  if [[ "$REPLY" =~ ^[0-9]+$ ]] && ((REPLY >= 1 && REPLY <= ${#ports[@]})); then PORT="${ports[$((REPLY - 1))]}"; break; fi
  if [[ "$REPLY" == /dev/* ]]; then PORT="$REPLY"; break; fi
  echo "  Enter a number from the list or a device path like /dev/ttyUSB0."
done

echo
echo "------------------------------------------------------------------"
echo "  Module : $PANEL_NAME   (build $PANEL)"
echo "  Flash  : $WHAT_NAME"
echo "  Port   : $PORT"
echo "------------------------------------------------------------------"
echo "  Close any serial monitor using $PORT. If upload stalls at \"Connecting...\","
echo "  hold the BOOT button on the ESP32 until it starts."
echo
ask "Proceed? [Y/n]: " y
case "$REPLY" in
  n|N|no|No|NO) echo "Cancelled. Nothing was flashed."; exit 0 ;;
esac

"$SCRIPT" "$PORT" "$PANEL"
if [[ "$WHAT_NAME" == Display* ]]; then
  echo
  echo "If the screen shows HELLO WORLD, run this wizard again and choose the Lalit Stock firmware."
fi
