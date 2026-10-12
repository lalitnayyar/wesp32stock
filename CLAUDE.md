# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Lalit Stock Application** (spec: `prompt.md`, the authoritative brief; `prompt_ver1.md` is an older revision, do not implement from it). It has three integrated parts: a FastAPI backend, a React admin UI with a browser E-Paper simulator, and ESP32 firmware for a WeAct 2.9" 4-colour E-Paper. They are run via Docker Compose behind Caddy. Owner attribution (Lalit Nayyar, consult@lalit.cloud, +971568391973) and the not-financial-advice disclaimer must appear in source headers, the web About/footer, `manage.sh help` and the README (`prompt.md` §14).

## Commands

```bash
./manage.sh                         # interactive ops menu; ./manage.sh help for subcommands (-y = assume yes)
./manage.sh build|start|stop|health|logs|backup|restore|seed|diag
./manage.sh test [backend|frontend|firmware|all]

# backend (Windows venv path shown; use .venv/bin on Linux)
cd backend && .venv/Scripts/python -m pytest -q
cd backend && .venv/Scripts/python -m pytest -q tests/test_api.py::test_api_key_scope_revoke_expiry_rotate
cd backend && .venv/Scripts/alembic revision --autogenerate -m "msg"   # then replace app.models.TZDateTime(...) with sa.DateTime(timezone=True) in the generated file

# frontend
cd frontend && npm run dev          # Vite on :5173, proxies /api -> localhost:8000
cd frontend && npx tsc -b && npx vitest run

# firmware
bash firmware/test/run_host_tests.sh                                   # g++ host tests of logic.h
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=min_spiffs firmware/LalitStockFirmware
firmware\flash.bat COM3                                                # compile + flash + monitor (Windows)
upload.bat COM3                                                        # display-only Hello World test sketch

python tools/gen_shared.py [--check] [--font <glcdfont.c>]             # regenerate derived shared files
```

Backend tests use SQLite and `MARKET_PROVIDER=fixture` (see `backend/tests/conftest.py`); set `TEST_DATABASE_URL` to run against Postgres.

## Architecture: the shared device contract

The cross-cutting design: ESP32 behaviour is defined once in `shared/` and implemented three times, and all three implementations must agree:

- `shared/device_config.json` (settings, defaults, ranges), `panel_profiles.json` (refresh timing), `layout.json` (168×384 canvas, header/footer positions, limits), `test_vectors/*.json` (refresh safety, validation, rotation state machine, exact header/footer draw-ops).
- Implementations: `backend/app/services/device_rules.py` (Python), `frontend/src/sim/rules.ts` (TypeScript simulator), `firmware/LalitStockFirmware/logic.h` (C++, host-testable). Each has tests that load the same vectors (`backend/tests/test_rules_and_dashboard.py`, `frontend/src/sim/rules.test.ts`, `firmware/test/host_test.cpp`).
- Generated files: `firmware/LalitStockFirmware/shared_contract.h`, `shared/fixtures/dashboard_3page.json` (from `portfolio_fixture.json` via the backend page builder), and `shared/glcdfont.json`. Never hand-edit them; run `tools/gen_shared.py`. A backend test fails if they are stale.
- Rendering: the **server paginates and lays out page bodies as draw-ops** (`backend/app/services/dashboard.py`; op format in `docs/RENDER_CONTRACT.md`). The firmware (`epaper.cpp`) and the simulator (`frontend/src/sim/render.ts`, a pixel replica of the Adafruit GFX classic font) just execute the ops. Header and footer (clock, Wi-Fi/API status, `PAGE n/N`, age/OFFLINE) are built locally by `buildHeaderFooterOps` / `headerFooterOps`. Changing the layout means changing `layout.json` and/or the builder, plus the header vectors.

## Hardware facts and refresh safety (do not change without re-verification)

- Panel GDEY029F51H / controller JD79667, 4-colour, portrait 168×384. Driver `GxEPD2_4C<GxEPD2_290c_GDEY029F51H, HEIGHT>`; monochrome `GxEPD2_BW` is incompatible. GPIO BUSY 4, RST 26, DC 25, CS 5, SCK 18, MOSI 23, 3V3 only. Verified with esp32 core 3.3.12, GxEPD2 1.6.9, Adafruit GFX 1.12.6, ArduinoJson 7.4.3.
- A full refresh takes up to 25 s (GxEPD2 `full_refresh_time`). The requested default page duration is 10 s (spec), but the effective duration is `max(requested, ceil(25×1.2)+30) = 60 s`, and manual page changes queue behind a 30 s refresh gate. Unknown profiles use a 180 s fallback. Both the requested and effective values must stay visible everywhere.
- Firmware needs the `min_spiffs` partition scheme (about 1.3 MB app). API fetch and heartbeat run on a separate FreeRTOS task (`net_client.cpp`); page rotation runs in `loop()`; a page change must never trigger a fetch. The GxEPD2 busy callback feeds the 60 s watchdog and services the admin web server. Web handlers must only change state, never draw.

## Backend notes

- `app/services/ledger.py`: holdings are always replayed from transactions (average cost, Decimal). Every transaction write re-validates the full ledger (`_check_ledger`).
- Market data goes through the `MarketDataProvider` interface (`services/market/`). `service.poll_once` is the single central poller (scheduler and manual refresh share a lock). Stale/unavailable states live on `Stock.data_quality`.
- Money is returned as decimal strings. Timestamps use the `TZDateTime` TypeDecorator (UTC-aware on SQLite too).
- Admin auth is a cookie JWT + server-side `AdminSession` + CSRF header (`X-CSRF-Token`). Device auth is HMAC-hashed `lsk_<prefix>_<secret>` keys with scopes and device binding (`core/security.py`). Keep the two separate.
- Errors are always `{"error": {"status", "message", "details?"}}` (handlers in `main.py`).

## Environment gotchas (this Windows machine)

- AVG antivirus intercepts TLS. Containers trust its root via `deploy/extra-ca/*.crt` (git-ignored); never disable verification. On the host, yfinance/curl_cffi fails for the same reason, so test live Yahoo inside the backend container.
- `manage.sh` exports `MSYS_NO_PATHCONV=1` (Git Bash otherwise rewrites `/api/...` arguments) and passes `--env-file .env` relatively. Scripts that hand paths to native Windows tools must convert them (see `native()` in `firmware/test/run_host_tests.sh`).
- `.env` comments must be on their own lines (Compose reads inline text after an empty value as the value).
- Session cookies are `Secure`; in-container scripts must forward cookies manually over plain HTTP (see `api_admin` in `manage.sh`).
- `https://localhost` uses Caddy's internal CA. For browser automation use the Vite dev server (`http://localhost:5173`) against the running backend.
