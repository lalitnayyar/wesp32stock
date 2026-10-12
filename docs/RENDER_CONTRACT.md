# Dashboard render contract (v1)

The same contract is used by the ESP32 firmware, the browser simulator and the device preview. The sources of truth are in `shared/`:

| File | Purpose |
|---|---|
| `device_config.json` | Device settings, defaults and validation ranges |
| `panel_profiles.json` | Refresh-safety timing per panel |
| `layout.json` | Canvas size, header/footer positions, limits |
| `fixtures/portfolio_fixture.json` → `fixtures/dashboard_3page.json` | Deterministic 3-page fixture (generated) |
| `glcdfont.json` | Adafruit GFX classic 5×7 font, so the simulator draws identical pixels (generated) |
| `test_vectors/*.json` | Shared tests for refresh safety, validation, rotation and header ops |

## Payload

```json
{
  "v": 1,
  "data_version": "5dd71974ca86",
  "generated_at": "2026-10-12T10:05:00Z",
  "tz": "Asia/Dubai",
  "device": {"id": "LS-001", "name": "Desk"},
  "status": {"market": "OPEN", "stale": true, "delayed": true, "provider": "yahoo", "quote_age_s": 2400},
  "pages": [{"k": "summary", "ops": [["T", 3, 56, 1, "R", "PORTFOLIO"], ...]}, ...],
  "disclaimer": "Not financial advice. ..."
}
```

`data_version` is a hash of the page content and status flags (not of timestamps). Devices send it back as `since=` and get a `304` when nothing changed.

## Coordinate system

Portrait, 168 × 384 px, origin top-left. Font: Adafruit GFX classic 5×7 glyphs in a 6×8 cell per size unit, with a transparent background. The text cursor `y` is the top of the cell. Colours: `K` black, `W` white, `R` red, `Y` yellow. Arrows use code points `0x1E` (▲) and `0x1F` (▼).

| Op | Format |
|---|---|
| Text | `["T", x, y, size, color, text]` (size 1–3, text ≤ 28 characters) |
| Filled rectangle | `["F", x, y, w, h, color]` |
| Outline rectangle | `["R", x, y, w, h, color]` |
| Horizontal line | `["H", x, y, w, color]` |

## Who draws what

- **Server:** the page bodies, inside `y ∈ [54, 364]`. Pagination (summary → holdings pages of 4–8 rows → benchmarks, max 8 pages) happens on the server, so every client shows the same page count and order.
- **Device / simulator:** the header (red title bar, date/time, `Upd HH:MM`, `WiFi:OK|--`, `API:OK|ERR|OFF`, `Mkt:<state>`, and a yellow flag `STALE` / `CACHED` / `DELAYED`) and the footer (`PAGE n/N`, plus `Age <t>` or a red `OFFLINE <t>`). Only the device knows this state. Both implementations are checked against `shared/test_vectors/header_cases.json`.

## Limits enforced by the firmware

24 KB response, at most 8 pages, at most 96 ops per page, contract version 1, known op kinds only. A response that violates any limit is rejected and the cached dashboard stays on screen.
