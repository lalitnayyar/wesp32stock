# ESP32 firmware: setup and configuration

Owner: Lalit Nayyar · consult@lalit.cloud. Not financial advice.

## Hardware

ESP32-WROOM-32 (board profile *ESP32 Dev Module*) + one of four WeAct Studio E-Paper modules:

| # | WeAct Studio module | Resolution | Colours | Panel / controller | GxEPD2 driver | Firmware build | Effective page time (10 s requested) |
|---|---|---|---|---|---|---|---|
| 1 | **2.9" 4-colour** (default) | 168 × 384 portrait | black, white, red, yellow | GDEY029F51H / JD79667 | `GxEPD2_290c_GDEY029F51H` | `290_4c` | 60 s · **hardware-verified** |
| 2 | **4.2" black/white** | 400 × 300 landscape | black, white | GDEY042T81 / SSD1683 | `GxEPD2_420_GDEY042T81` | `420_bw` | 32 s (≈1.2 s refresh) |
| 3 | **4.2" black/white/red** | 400 × 300 landscape | black, white, red | GDEY042Z98 / SSD1683 | `GxEPD2_420c_GDEY042Z98` | `420_bwr` | 60 s (≈25 s refresh) |
| 4 | **4.2" 4-colour** | 400 × 300 landscape | black, white, red, yellow | GDEY0420F51 / HX8717 | `GxEPD2_420c_GDEY0420F51` | `420_4c` | 66 s (≈30 s refresh) |

Only the 2.9" module is verified on hardware so far; the 4.2" timings come from the GxEPD2 1.6.9 driver sources (see [HARDWARE_VERIFICATION.md](HARDWARE_VERIFICATION.md)). Two wiring layouts are supported (3V3 only; BUSY → GPIO4, CS → GPIO5, SCL/SCK → GPIO18, SDA/MOSI → GPIO23 in both):

- **standard** (default): RES → GPIO26, D/C → GPIO25.
- **uart2**: RES → RX2 (GPIO16), D/C → TX2 (GPIO17), as in [../ESP32-Epaper-Wiring.png](../ESP32-Epaper-Wiring.png). Not for WROVER boards (PSRAM uses GPIO16/17).

The wiring is compiled in with `-DLS_WIRING=LS_WIRING_STANDARD|LS_WIRING_UART2` (wizard step 2, or the third argument of the flash scripts) and printed at boot as `[hw] panel ..., wiring ...`. Full table: [../ESP32_WeAct_2.9_EPaper.md](../ESP32_WeAct_2.9_EPaper.md). Run the display-only test first: `upload.bat COM3 <build>` or the wizard's *Display test* option.

## Build and flash

**Interactive:** `flash_esp32.bat` (Windows) or `./flash_esp32.sh` (Linux/macOS) asks for the module (1-4), firmware or display test, and the serial port (detected ports are listed), shows a summary, and asks before flashing. Five invalid answers or closed input cancel without flashing.

**Direct:**

```bat
firmware\flash.bat COM3              :: 2.9in 4-colour (default)
firmware\flash.bat COM3 420_bwr      :: 4.2in black/white/red; also 420_bw, 420_4c
firmware\flash.bat COM3 420_bwr uart2 :: same, wired D/C -> TX2 (17), RES -> RX2 (16)
```

On Linux/macOS: `firmware/flash.sh [/dev/ttyUSB0] [build]` (port auto-detected if omitted or ""; needs `dialout` group membership; `NO_MONITOR=1` skips the monitor).

The module is a compile-time choice: the scripts pass `-DLS_PANEL=LS_PANEL_<BUILD>` (via `compiler.cpp.extra_flags`), which selects the GxEPD2 driver in `epaper.cpp` and the layout, palette and timing block in the generated `shared_contract.h`. The device sends its panel (`&panel=<profile>`) with every dashboard request, so the server returns pages laid out for that panel, and it rejects pages for another layout. Reflashing a board with a different module build is safe: a cached dashboard for the old layout is discarded and the panel timing profile resets to the new module.

This installs the ESP32 core and the GxEPD2, Adafruit GFX and ArduinoJson libraries if they are missing, compiles with `PartitionScheme=min_spiffs` (the firmware is about 1.3 MB, which does not fit the default 1.25 MB app partition), uploads, and opens the serial monitor at 115200. Manual equivalent:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=min_spiffs firmware/LalitStockFirmware
arduino-cli upload -p COM3 --fqbn esp32:esp32:esp32:PartitionScheme=min_spiffs firmware/LalitStockFirmware
```

Verified with esp32 core 3.3.12, GxEPD2 1.6.9, Adafruit GFX 1.12.6 and ArduinoJson 7.4.3. All four builds compile at about 1.30 MB (66 %) with about 67-69 KB of RAM used by globals. `shared_contract.h` is generated from `shared/*.json` by `tools/gen_shared.py`; do not edit it by hand.

## Server side first

In the web admin, open **E-Paper Devices → Register device**. Use the device ID shown on the setup screen (for example `LS-A1B2C3`), choose the same **E-Paper module** you flashed, assign a portfolio, then click **New API key** and copy the key (it is shown only once).

## First boot: setup portal

With no valid settings, the device:

1. Starts a temporary **WPA2-protected** access point `LalitStock-Setup-XXXX`. A random password is shown on the E-Paper and printed on serial.
2. Serves the admin page at **http://192.168.4.1**.
3. Lets you scan Wi-Fi, enter the SSID/password, the stock API URL (`https://stock.example.com`) and the device API key, set an **admin password** (≥ 8 characters, used for later access), and use **Test Wi-Fi**, **Test API** and **Save**. It then restarts into normal mode.

The access point never stays up permanently: when the device is configured, setup mode closes after 15 minutes.

## Normal operation: admin page

Open `http://<device-ip>/`. HTTP Basic auth applies with user `admin` and your admin password. The IP is shown in your router and on serial. The page shows:

- **Page controls:** **Pause / Resume** rotation, **Next page**, **Go to page N**. Changes apply immediately and persist across reboot. If the panel is refreshing, or the minimum gap between full refreshes (30 s) hasn't passed, the change is queued and the page tells you when it will appear.
- **Refresh safety:** the requested page duration (default 10 s), the effective hardware-safe duration (60 s on this panel) and the reason.
- **Status:** Wi-Fi/RSSI, API state, last error, data age (cached or not), data version, fetch counts, display refresh count and timing, BUSY timeouts, NTP time, firmware, uptime and free heap.
- **Settings:** Wi-Fi, API URL and key, optional custom root CA, fetch interval, timeout, rotation on/off, requested duration, rows per page, summary/benchmark pages, reset-to-page-1 on new data, heartbeat interval, panel profile, timezone label, POSIX TZ (Dubai `<+04>-4`) and NTP server. Stored secrets are never shown. Leave a secret field blank to keep it.
- **Test Wi-Fi, Test API, Save, Restart, Factory reset** (factory reset requires typing `RESET`).

## Physical recovery (BOOT button, GPIO0)

| Hold | Action |
|---|---|
| 5 s, then release | Restart into the setup portal. Settings are kept, and the admin password is required if one is set. |
| 15 s | Factory reset (erases all settings and the cached dashboard), then setup mode |

## Behaviour summary

- Independent schedules: page rotation (UI loop), API fetch + heartbeat (network task on core 0, with backoff of 30 s × 2ⁿ on failure, capped at the fetch interval), NTP (SNTP), and the watchdog (60 s, fed during the ~21 s BUSY wait). A page change never causes a fetch.
- The last good dashboard is cached in LittleFS and shown at boot (`CACHED`) until a fetch succeeds. On failure the footer shows `OFFLINE <age>` and the cached data stays on screen.
- Responses are size-limited (24 KB), structurally validated, and rejected without touching the display if invalid.
- TLS: `https` is always verified, against the built-in CA bundle or your custom root CA. `http://` works for LAN development only and is labelled insecure. Verification is never silently disabled.
- The device admin page itself is served over plain HTTP on the LAN (an ESP32 limitation). Use it only on trusted networks.
