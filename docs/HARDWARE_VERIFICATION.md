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

## Safe page duration

```
refresh_gap = ceil(25 000 ms × 1.20) = 30 s        (minimum time between two full refreshes)
min_safe    = refresh_gap + 30 s reading time = 60 s
effective   = max(requested, min_safe)              → requested 10 s ⇒ effective 60 s
```

Partial refresh is not used. It is no faster on this panel and is not used to work around four-colour limits. Unknown panels use a 180 s fallback.

## Still requires hardware-in-the-loop verification

- [ ] Flash `firmware/LalitStockFirmware` and confirm portrait rendering of all three fixture/live pages (layout, colours, arrows `0x1E`/`0x1F`).
- [ ] Measure the actual full-refresh duration on the device (shown as "last refresh ms" on the admin page) at room temperature and at the coldest and hottest expected temperatures.
- [ ] Manufacturer guidance on the minimum interval between colour full refreshes for GDEY029F51H (Good Display commonly recommends ≥ 180 s for colour panels). If confirmed, raise `min_dwell_s` in `shared/panel_profiles.json` and run `tools/gen_shared.py`.
- [ ] Long-run soak test (24 h at 60 s pages): check for ghosting, BUSY timeouts (admin page counter), heap stability and watchdog resets.
- [ ] BOOT-button recovery (5 s setup portal, 15 s factory reset).
- [ ] HTTPS against the production domain with the built-in CA bundle.
