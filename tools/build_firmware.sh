#!/usr/bin/env bash
# =============================================================================
# Lalit Stock Application - build every ESP32 firmware variant for the web flasher
# Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973
# Disclaimer: informational software only, NOT financial advice.
#
# Builds <sketch> x <panel> x <wiring> with arduino-cli and writes, per variant,
# the four flash parts (bootloader 0x1000, partitions 0x8000, boot_app0 0xe000,
# app 0x10000) plus firmware/dist/manifest.json. The web container serves
# firmware/dist at /firmware/ for the "Flash ESP32" page (Web Serial + esptool-js).
#
# Usage: tools/build_firmware.sh [variant-filter]   e.g. tools/build_firmware.sh 420_bwr
#   ARDUINO_CLI=path  OUT=dir (default firmware/dist)  BUILD_CACHE=dir (default firmware/.build)  JOBS=n (default 2)
# Normally run through ./manage.sh firmware (uses a Docker builder when arduino-cli is not installed).
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-$ROOT/firmware/dist}"
CACHE="${BUILD_CACHE:-$ROOT/firmware/.build}"
JOBS="${JOBS:-2}"
FILTER="${1:-}"
ESP32_INDEX_URL="https://espressif.github.io/arduino-esp32/package_esp32_index.json"
CORE="esp32:esp32@3.3.12"
LIBS=("GxEPD2@1.6.9" "Adafruit GFX Library@1.12.6" "ArduinoJson@7.4.3")

native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

CLI="${ARDUINO_CLI:-}"
if [[ -z "$CLI" ]]; then
  for c in arduino-cli "$HOME/bin/arduino-cli" "$HOME/.local/bin/arduino-cli" "${LOCALAPPDATA:-/nonexistent}/arduino-cli/arduino-cli.exe"; do
    if command -v "$c" >/dev/null 2>&1 || [[ -x "$c" ]]; then CLI="$c"; break; fi
  done
fi
[[ -n "$CLI" ]] || { echo "arduino-cli not found. Install it, or run ./manage.sh firmware (Docker builder)." >&2; exit 3; }
PY="$(command -v python3 || command -v python || true)"
[[ -n "$PY" ]] || { echo "python3 is required to write the manifest." >&2; exit 3; }

echo "==> Checking ESP32 core and libraries"
if ! "$CLI" core list | grep -q "esp32:esp32 *3.3.12"; then
  "$CLI" core update-index --additional-urls "$ESP32_INDEX_URL"
  "$CLI" core install "$CORE" --additional-urls "$ESP32_INDEX_URL"
fi
installed="$("$CLI" lib list)"
for lib in "${LIBS[@]}"; do
  name="${lib%@*}"; ver="${lib#*@}"
  grep -qE "^${name// /[[:space:]]}[[:space:]]+${ver//./\\.}" <<<"$installed" || "$CLI" lib install "$lib"
done

# sketch-id|sketch dir|fqbn
SKETCHES=("firmware|$ROOT/firmware/LalitStockFirmware|esp32:esp32:esp32:PartitionScheme=min_spiffs"
          "test|$ROOT/ESP32_EPaper_Test|esp32:esp32:esp32")
PANELS=(290_4c 420_bw 420_bwr 420_4c)
WIRINGS=(standard uart2)

variants=()
for s in "${SKETCHES[@]}"; do
  for p in "${PANELS[@]}"; do
    for w in "${WIRINGS[@]}"; do
      id="${s%%|*}-$p-$w"
      [[ -z "$FILTER" || "$id" == *"$FILTER"* ]] && variants+=("$s|$p|$w")
    done
  done
done
((${#variants[@]})) || { echo "No variant matches '$FILTER'." >&2; exit 2; }
mkdir -p "$OUT" "$CACHE"

build_one() {
  local sid sdir fqbn panel wiring id bdir dest pname
  IFS='|' read -r sid sdir fqbn panel wiring <<<"$1"
  id="$sid-$panel-$wiring"
  bdir="$CACHE/$id"
  dest="$OUT/$id"
  pname="$(basename "$sdir")"
  local flags="-DLS_PANEL=LS_PANEL_${panel^^} -DLS_WIRING=LS_WIRING_${wiring^^}"
  if ! "$CLI" compile --fqbn "$fqbn" --build-property "compiler.cpp.extra_flags=$flags" \
      --build-path "$(native "$bdir")" "$(native "$sdir")" >"$bdir.log" 2>&1; then
    echo "  FAILED $id (see $bdir.log)" >&2
    tail -20 "$bdir.log" >&2
    return 1
  fi
  mkdir -p "$dest"
  cp -f "$bdir/$pname.ino.bootloader.bin" "$dest/bootloader.bin"
  cp -f "$bdir/$pname.ino.partitions.bin" "$dest/partitions.bin"
  cp -f "$bdir/boot_app0.bin" "$dest/boot_app0.bin"
  cp -f "$bdir/$pname.ino.bin" "$dest/app.bin"
  echo "  built $id ($(wc -c <"$dest/app.bin") bytes)"
}

echo "==> Building ${#variants[@]} variant(s) with $JOBS job(s) into $OUT"
fail=0
running=0
for v in "${variants[@]}"; do
  build_one "$v" &
  running=$((running + 1))
  if ((running >= JOBS)); then wait -n || fail=1; running=$((running - 1)); fi
done
while ((running > 0)); do wait -n || fail=1; running=$((running - 1)); done
((fail == 0)) || { echo "Some builds failed; manifest not updated." >&2; exit 1; }

echo "==> Writing manifest"
FW_VERSION="$(grep -oE '#define FW_VERSION "[^"]+"' "$ROOT/firmware/LalitStockFirmware/app_state.h" | cut -d'"' -f2)"
COMMIT="$(git -c safe.directory='*' -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
"$PY" - "$(native "$OUT")" "$(native "$ROOT/shared/panel_profiles.json")" "$FW_VERSION" "$COMMIT" <<'PYEOF'
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

out, profiles_path, version, commit = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
profiles = json.loads(profiles_path.read_text(encoding="utf-8"))["profiles"]
by_build = {p["build"]: (name, p) for name, p in profiles.items() if p.get("build")}
PARTS = [("bootloader.bin", 0x1000), ("partitions.bin", 0x8000), ("boot_app0.bin", 0xE000), ("app.bin", 0x10000)]
targets = []
for d in sorted(p for p in out.iterdir() if p.is_dir()):
    sketch, rest = d.name.split("-", 1)
    build, wiring = rest.rsplit("-", 1)
    if build not in by_build or not all((d / f).exists() for f, _ in PARTS):
        continue
    profile, prof = by_build[build]
    parts = []
    for f, addr in PARTS:
        data = (d / f).read_bytes()
        parts.append({"path": f"{d.name}/{f}", "offset": addr, "size": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()})
    targets.append({"id": d.name, "sketch": sketch, "build": build, "profile": profile,
                    "module": prof.get("module", prof["label"]), "wiring": wiring, "parts": parts})
manifest = {"name": "Lalit Stock Application ESP32 firmware", "version": version, "commit": commit,
            "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "chip": "ESP32", "targets": targets,
            "note": "Not financial advice. Parts are flashed at their offsets; NVS settings at 0x9000 are kept unless erased."}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"  manifest: {len(targets)} target(s), firmware {version} ({commit})")
PYEOF
