#!/usr/bin/env bash
# =============================================================================
# Lalit Stock Application - shared compile + upload helper for the ESP32 (Linux/macOS)
# Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973
# Disclaimer: informational software only, NOT financial advice.
#
# Sourced by firmware/flash.sh and upload.sh (the Linux counterparts of flash.bat / upload.bat).
#   esp32_flash SKETCH_DIR FQBN PORT LIB...
# PORT may be empty: the first /dev/ttyUSB* or /dev/ttyACM* is used.
# Set NO_MONITOR=1 to skip the serial monitor after a successful upload.
# =============================================================================

ESP32_INDEX_URL="https://espressif.github.io/arduino-esp32/package_esp32_index.json"

esp32_detect_port() {
  local p
  for p in /dev/ttyUSB* /dev/ttyACM* /dev/cu.usbserial* /dev/cu.SLAB_USBtoUART* /dev/cu.wchusbserial*; do
    [[ -e "$p" ]] && { printf '%s' "$p"; return 0; }
  done
  return 1
}

esp32_flash() {
  local sketch="$1" fqbn="$2" port="$3"; shift 3
  local cli=arduino-cli
  if ! command -v arduino-cli >/dev/null 2>&1; then
    if [[ -x "$HOME/bin/arduino-cli" ]]; then cli="$HOME/bin/arduino-cli"
    elif [[ -x "$HOME/.local/bin/arduino-cli" ]]; then cli="$HOME/.local/bin/arduino-cli"
    else
      echo "arduino-cli was not found on PATH, in ~/bin or in ~/.local/bin." >&2
      echo "Install it: curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=~/.local/bin sh" >&2
      return 3
    fi
  fi

  if [[ -z "$port" ]]; then
    port="$(esp32_detect_port)" || { echo "No ESP32 serial port found (/dev/ttyUSB*, /dev/ttyACM*). Plug in the board or pass the port." >&2; return 3; }
    echo "Using detected port $port"
  fi
  [[ -e "$port" ]] || { echo "Port $port does not exist. Available: $(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | tr '\n' ' ')" >&2; return 3; }
  if [[ ! -w "$port" ]]; then
    echo "No write access to $port. Add yourself to the serial group, then log out and back in:" >&2
    echo "  sudo usermod -aG dialout \"\$USER\"    (Arch: uucp)" >&2
    return 3
  fi

  echo "Checking ESP32 board support..."
  if ! "$cli" core list | grep -qi "esp32:esp32"; then
    echo "Installing ESP32 board support - first-time setup..."
    "$cli" core update-index --additional-urls "$ESP32_INDEX_URL"
    "$cli" core install esp32:esp32 --additional-urls "$ESP32_INDEX_URL"
  fi

  echo "Checking required libraries..."
  local lib installed; installed="$("$cli" lib list)"
  for lib in "$@"; do
    grep -qiF "$lib" <<<"$installed" || "$cli" lib install "$lib"
  done

  echo
  echo "Compiling $(basename "$sketch") for $fqbn..."
  "$cli" compile --fqbn "$fqbn" "$sketch" || { echo "Compile failed." >&2; return 1; }

  echo
  echo "Uploading to $port..."
  if ! "$cli" upload -p "$port" --fqbn "$fqbn" "$sketch"; then
    echo "Upload failed. If it stalls at \"Connecting...\", hold BOOT on the ESP32 until upload starts." >&2
    echo "Also make sure no serial monitor (screen, minicom, Arduino IDE) holds the port." >&2
    return 1
  fi

  echo
  if [[ "${NO_MONITOR:-0}" == 1 ]]; then echo "Upload complete."; return 0; fi
  echo "Upload complete. Opening serial monitor on $port (Ctrl+C to exit)..."
  "$cli" monitor -p "$port" -c baudrate=115200
}
