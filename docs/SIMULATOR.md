# Docker E-Paper simulator (testing only)

Open **E-Paper Simulator** in the web admin. The page is labelled **"Simulation mode — no physical E-Paper connected"**. It is a development and QA tool, not a second device type. It is enabled outside production; in production it is disabled unless `SIMULATOR_ENABLED=true`. All of its endpoints require an admin session.

## What it reproduces

- An exact **168 × 384** canvas, plus an enlarged copy (×1–×3, nearest-neighbour scaling, so no reflow). Both are drawn with the firmware's GFX font and the same draw-ops.
- The same payload as the device. **Fixture mode** uses `shared/fixtures/dashboard_3page.json` and needs no API key. **Live mode** builds exactly what `/api/v1/device/dashboard` would return for a chosen portfolio, authorised by your admin session.
- The same shared config schema, validation ranges, rotation state machine, refresh gate and safe-refresh calculation as the firmware (`frontend/src/sim/rules.ts`, tested against `shared/test_vectors`).
- Independent clocks: fetch timer (with the firmware's backoff), rotation timer, heartbeat counter and NTP. Diagnostics show that page changes never increase the fetch count.
- Every ESP32 admin setting: device ID and name, Wi-Fi SSID with a simulated scan, API URL, a masked API key (only a "key set" flag is stored), fetch interval, timeout, rotation, requested duration, selected page, rows, summary/benchmark pages, reset on new data, orientation, panel profile, timezone, POSIX TZ and NTP server.
- Controls: **Pause / Resume / Next page / Page 1 / Go to page N**, Save, Reload persisted, Test Wi-Fi, Test API, Restart simulation (like a reboot) and Reset simulator (asks for confirmation; clears simulator state only).
- Fault injection: Wi-Fi down, API offline, stale data, invalid response, NTP failure, and response delay (rotation keeps running during a delayed fetch).
- Refresh-safety demonstrations: `JD79667_GDEY029F51H` (10 s → 60 s, verified), `TEST_FAST_PANEL` (10 s accepted, simulation-only), and `UNKNOWN` (180 s fallback with a warning).

Simulator settings and events are stored in their own tables (`simulator_state`, `simulator_events`), separate from real devices. Secrets are redacted from events.

## What it does not reproduce

E-Paper ghosting, panel wear, power draw, real BUSY timing and thermal behaviour. The "simulated BUSY" badge only marks the nominal refresh window. Browser colours approximate the physical pigments. These remain hardware-in-the-loop checks (see [HARDWARE_VERIFICATION.md](HARDWARE_VERIFICATION.md)).
