# Hardware driver verification note

## Verified

| Fact | Evidence |
|---|---|
| Panel GDEY029F51H, controller JD79667, 4-colour (black/white/red/yellow), 168 × 384 | Hello World displayed correctly by `ESP32_EPaper_Test` on the owner's hardware |
| Driver `GxEPD2_4C<GxEPD2_290c_GDEY029F51H, HEIGHT>` | Same test. Monochrome `GxEPD2_BW` drivers are **not** compatible. |
| GPIO BUSY 4, RST 26, DC 25, CS 5, SCK 18, MOSI 23, 3V3 | Same test |
| Library versions | esp32 core 3.3.12, GxEPD2 1.6.9, Adafruit GFX 1.12.6 (ArduinoJson 7.4.3 for the application) |
| Full refresh time | GxEPD2 1.6.9 `src/epd4c/GxEPD2_290c_GDEY029F51H.h`: `full_refresh_time = 25000` ms ("e.g. 21428295us"), `partial_refresh_time = 25000` ms, `hasFastPartialUpdate = false` |
| Application firmware compiles | `arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=min_spiffs`: about 1.30 MB of 1.97 MB (66 %), about 69 KB of RAM used by globals |

## WeAct 4.2" 400 × 300 modules (driver sources only; not yet on hardware)

| Module | Driver (GxEPD2 1.6.9) | `full_refresh_time` | Palette | Buffer |
|---|---|---|---|---|
| 4.2" black/white, GDEY042T81 / SSD1683 | `GxEPD2_BW<GxEPD2_420_GDEY042T81, HEIGHT>` (`src/gdey/`) | 1200 ms (measured 1 140 000 µs in the source) | K W | full, 15 KB |
| 4.2" black/white/red, GDEY042Z98 / SSD1683 | `GxEPD2_3C<GxEPD2_420c_GDEY042Z98, HEIGHT/2>` (`src/gdey3c/`) | 25 000 ms (22 780 001 µs) | K W R | 2 × 7.5 KB, two-pass paging |
| 4.2" 4-colour, GDEY0420F51 / HX8717 | `GxEPD2_4C<GxEPD2_420c_GDEY0420F51, HEIGHT/2>` (`src/epd4c/`) | 30 000 ms (27 676 925 µs) | K W R Y | 15 KB, two-pass paging |

**Measured on the owner's 4.2" black/white/red module** (ESP32-WROOM-32, `uart2` wiring per `ESP32-Epaper-Wiring.png`, firmware 1.1.0): the setup screen refresh took 10 028 003 µs (`_Update_Fast`, GxEPD2's default fast full update for this panel). The profile keeps `full_refresh_ms = 25000` (the driver's timeout and the normal-update ceiling) until the full page set has been checked.

Wiring: either layout (standard D/C 25 / RES 26, or `uart2` D/C 17 / RES 16). All four firmware builds compile (`arduino-cli compile ... -DLS_PANEL=LS_PANEL_<BUILD>`): about 1.30 MB (66 %) of flash; globals 68.7 KB (2.9") and 67.5 KB (4.2"). Effective page durations for a 10 s request: 32 s, 60 s and 66 s. The profiles are marked `verified: false` until measured on a real module.

## Safe page duration

```
refresh_gap = ceil(25 000 ms × 1.20) = 30 s        (minimum time between two full refreshes)
min_safe    = refresh_gap + 30 s reading time = 60 s
effective   = max(requested, min_safe)              → requested 10 s ⇒ effective 60 s
```

Partial refresh is not used. It is no faster on this panel and is not used to work around four-colour limits. Unknown panels use a 180 s fallback.

## Still requires hardware-in-the-loop verification

4.2" modules (for each variant you own): run `flash_esp32` → *Display test*, then the firmware; confirm landscape orientation, colours (B/W shows no red/yellow), all three pages, and the "last refresh ms" against the table above. Then set `verified: true` (and adjust `full_refresh_ms` if needed) in `shared/panel_profiles.json` and run `tools/gen_shared.py`.

2.9" module:

- [ ] Flash `firmware/LalitStockFirmware` and confirm portrait rendering of all three fixture/live pages (layout, colours, arrows `0x1E`/`0x1F`).
- [ ] Measure the actual full-refresh duration on the device (shown as "last refresh ms" on the admin page) at room temperature and at the coldest and hottest expected temperatures.
- [ ] Manufacturer guidance on the minimum interval between colour full refreshes for GDEY029F51H (Good Display commonly recommends ≥ 180 s for colour panels). If confirmed, raise `min_dwell_s` in `shared/panel_profiles.json` and run `tools/gen_shared.py`.
- [ ] Long-run soak test (24 h at 60 s pages): check for ghosting, BUSY timeouts (admin page counter), heap stability and watchdog resets.
- [ ] BOOT-button recovery (5 s setup portal, 15 s factory reset).
- [ ] HTTPS against the production domain with the built-in CA bundle.
