#!/usr/bin/env bash
# Builds and runs the firmware logic host tests (no hardware needed).
# Requires g++ (C++17) and the ArduinoJson library (header-only).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
AJ="${ARDUINOJSON_SRC:-}"
if [[ -z "$AJ" ]]; then
  for c in "$HOME/Arduino/libraries/ArduinoJson/src" "$HOME/Documents/Arduino/libraries/ArduinoJson/src" \
           "$HOME/OneDrive/Documents/Arduino/libraries/ArduinoJson/src" "/usr/include/ArduinoJson" "$HERE/.deps/ArduinoJson/src"; do
    [[ -f "$c/ArduinoJson.h" ]] && AJ="$c" && break
  done
fi
if [[ -z "$AJ" ]]; then
  echo "ArduinoJson not found; fetching v7.4.3 into $HERE/.deps" >&2
  mkdir -p "$HERE/.deps"
  git clone --depth 1 --branch v7.4.3 https://github.com/bblanchon/ArduinoJson.git "$HERE/.deps/ArduinoJson" >/dev/null
  AJ="$HERE/.deps/ArduinoJson/src"
fi
# Native Windows compilers (MinGW) need Windows-style paths when run from Git Bash/MSYS.
native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
OUT="$(native "${TMPDIR:-/tmp}")/ls_host_test$$"
g++ -std=c++17 -Wall -Wextra -O1 -I"$(native "$AJ")" "$(native "$HERE/host_test.cpp")" -o "$OUT"
"$OUT" "$(native "$ROOT")"
rm -f "$OUT" "$OUT.exe"
