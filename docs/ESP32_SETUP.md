# ESP32 firmware: setup and configuration

Owner: Lalit Nayyar · consult@lalit.cloud. Not financial advice.

## Hardware (verified)

ESP32-WROOM-32 (board profile *ESP32 Dev Module*) + WeAct Studio 2.9" 4-colour E-Paper, 168 × 384, panel GDEY029F51H, controller JD79667. Wiring (3V3 only): BUSY → GPIO4, RES → GPIO26, D/C → GPIO25, CS → GPIO5, SCL/SCK → GPIO18, SDA/MOSI → GPIO23. Full table: [../ESP32_WeAct_2.9_EPaper.md](../ESP32_WeAct_2.9_EPaper.md). Run the display-only test first: `upload.bat COM3`.

## Build and flash

```bat
firmware\flash.bat COM3
```

This installs the ESP32 core and the GxEPD2, Adafruit GFX and ArduinoJson libraries if they are missing, compiles with `PartitionScheme=min_spiffs` (the firmware is about 1.3 MB, which does not fit the default 1.25 MB app partition), uploads, and opens the serial monitor at 115200. Manual equivalent:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=min_spiffs firmware/LalitStockFirmware
arduino-cli upload -p COM3 --fqbn esp32:esp32:esp32:PartitionScheme=min_spiffs firmware/LalitStockFirmware
```

Verified with esp32 core 3.3.12, GxEPD2 1.6.9, Adafruit GFX 1.12.6 and ArduinoJson 7.4.3. `shared_contract.h` is generated from `shared/*.json` by `tools/gen_shared.py`; do not edit it by hand.

## Server side first

In the web admin, open **E-Paper Devices → Register device**. Use the device ID shown on the setup screen (for example `LS-A1B2C3`), assign a portfolio, then click **New API key** and copy the key (it is shown only once).

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
