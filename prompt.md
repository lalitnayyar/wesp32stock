# Lalit Stock Application — Master Development Prompt

**Document purpose:** Authoritative implementation specification for a production-oriented stock portfolio monitoring platform with a Docker-hosted administration application and a lightweight ESP32 E-Paper client.

**Project owner:** Lalit Nayyar  
**Email:** consult@lalit.cloud  
**Phone:** +971568391973  
**Default timezone:** `Asia/Dubai`

> **Disclaimer:** This specification is an engineering brief, not financial advice. Market data may be delayed, incomplete, inaccurate, rate-limited, or unavailable. AI output is informational and may be wrong. The implementer and operator are responsible for credentials, network security, backups, licensing, provider terms, and validating all financial information before relying on it. The software is provided without a guarantee of fitness, uninterrupted availability, or investment performance.

## 1. Role and objective

Act as a senior full-stack architect, embedded-systems engineer, DevOps engineer, cybersecurity specialist, and AI application developer.

Build an actual working, modular application called **Lalit Stock Application**, not a mock-data prototype. It has three integrated components:

1. Docker backend: portfolio administration, market data, analytics, AI integration, authentication, device management, and APIs.
2. Responsive web administration dashboard: stocks, holdings, transactions, settings, API keys, AI providers, benchmarks, and ESP32 devices.
3. Lightweight ESP32 firmware: Wi-Fi client, authenticated dashboard consumer, local configuration portal, and portrait renderer for a WeAct Studio four-color E-Paper display.

Start with local Docker Compose and preserve a straightforward path to deployment on a Hostinger VPS without substantial code changes. Use modular architecture, documented APIs, migrations, automated tests, security controls, and deployment documentation.

## 2. Confirmed hardware profile

| Component | Required specification |
|---|---|
| Microcontroller | ESP32-WROOM-32 |
| Development board | ESP32 Dev Module |
| Connectivity | 2.4 GHz Wi-Fi |
| Programming interface | USB-C |
| Display | WeAct Studio 2.9-inch 4C E-Paper |
| Resolution | 168 × 384 pixels |
| Color | Four-color |
| Interface | SPI |
| Orientation | Portrait |
| Refresh strategy | Full refresh by default; partial refresh only after verifying exact panel support |
| Framework | Arduino ESP32 |
| Candidate library | GxEPD2 or another verified compatible driver |

### Confirmed wiring

| Wire color | E-Paper signal | ESP32 GPIO |
|---|---|---:|
| Red | VCC | 3V3 |
| Black | GND | GND |
| Yellow | SDA/MOSI | GPIO 23 |
| Green | SCL/SCK | GPIO 18 |
| Blue | CS | GPIO 5 |
| White | D/C | GPIO 25 |
| Orange | RES | GPIO 26 |
| Purple | BUSY | GPIO 4 |

The existing hardware has successfully displayed a Hello World test screen. Preserve the mapping above, operate the panel at 3.3 V, and provide a display-only test before the complete application. Verify the exact controller and four-color driver; do not assume a monochrome driver is compatible. Use a logical canvas of 168 × 384 pixels, compact fonts, bounded buffers, and careful text alignment.

## 3. Recommended technology and deployment architecture

Use the following unless a justified alternative is technically superior:

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Database | PostgreSQL |
| ORM/migrations | SQLAlchemy and Alembic |
| Market data | Provider abstraction with Yahoo Finance/yfinance initially |
| Scheduling | APScheduler or equivalent persistent, observable scheduler |
| Admin auth | Secure sessions or JWT with appropriate refresh/revocation controls |
| Device auth | Scoped, hashed API keys |
| AI | OpenAI, DeepSeek, Ollama through one provider interface |
| Firmware | Arduino ESP32, ArduinoJson, Preferences, WiFi, HTTPClient, TLS, SPI |
| Containers | Docker Compose |
| Reverse proxy | Caddy with HTTPS |
| API docs | OpenAPI/Swagger |
| Logs | Structured JSON with secret redaction |
| Tests | Pytest, frontend tests, API contract tests, firmware build verification |

Prefer a modular monolith initially. Do not introduce Kubernetes, Redis, Kafka, or unnecessary microservices without a demonstrated need.

```text
Internet → HTTPS/Caddy → React admin UI + FastAPI → PostgreSQL
                                      ↓
                           authenticated REST API
                                      ↓
                           ESP32 → SPI → 2.9-inch 4C E-Paper
```

## 4. Portfolio and stock administration

### Stock master

Support create, edit, search, activate, deactivate, and symbol validation. Store stock ID, ticker, company, exchange, market, currency, sector, industry, country, provider, active status, last update, and data-quality status. Support NYSE, NASDAQ, Dubai Financial Market, Abu Dhabi Securities Exchange, NASDAQ Dubai, and other Yahoo-supported exchanges. Handle exchange suffixes and unsupported symbols explicitly.

### Portfolios, brokers, and ledger

Support multiple portfolios and brokerage accounts. Each transaction must support buy, sell, dividends, splits, fees, deposits/withdrawals where relevant, and audited manual adjustments. Calculate holdings from the ledger rather than storing only one purchase price and quantity. Support multiple purchases at different prices and document average-cost accounting initially, with a path to FIFO.

Use decimal-safe financial arithmetic. Store purchase date, price, quantity, currency, fees, cost basis, current price, market value, unrealized P/L, unrealized P/L percentage, daily change, daily change percentage, and notes.

### Analytics and benchmarks

Calculate per-holding and portfolio-level metrics, including market value, invested capital, unrealized and daily P/L, allocation, currency and sector exposure, active holdings, data freshness, best/worst performers, and configurable comparisons such as S&P 500, NASDAQ Composite, DFM General Index, and FTSE ADX General Index. Keep benchmark performance separate from portfolio returns and use only supported provider symbols.

## 5. Market-data engine

Use Yahoo Finance initially behind a replaceable provider interface. Retrieve current and previous-close prices, daily absolute/percentage changes, currency, market hours/status, provider timestamp, cached prices, and historical records.

The default backend quote refresh is **60 seconds**, configurable in the web administration interface. Expose timeout, retry attempts, market-hours optimization, historical-data, and stale-price-warning settings. Poll centrally; never make one Yahoo request per ESP32 device.

Distinguish last poll, last successful quote, quote timestamp, freshness, and market open/closed status. Implement retries with exponential backoff and retain the last valid quote when unavailable. Clearly label delayed or stale data.

## 6. Web administration dashboard

Provide a desktop/mobile-responsive interface with:

- Dashboard: portfolio value, today’s gain/loss, unrealized gain/loss, chart, market status, active stocks, devices, data health, and AI status.
- Portfolios: portfolios, holdings, transactions, brokers.
- Stocks: master, add/edit, prices, history.
- Analytics: performance, benchmarks, AI insights.
- E-Paper Devices: registered devices, configuration, display layout, status.
- API Management: keys, creation, permissions, access logs.
- AI Settings: Ollama, DeepSeek, OpenAI, test connection.
- Settings: general, market data, refresh intervals, security, backup/restore, and disclaimer/about information.

## 7. Secure API-key management

Allow administrators to generate cryptographically secure keys, name and bind them to devices, assign scopes, set expiration, rotate, revoke, inspect last use, and review access logs. Display the full key only once and persist only a secure hash. Use HTTPS, rate limiting, authorization scopes, audit logging, key redaction, and separate admin/device authentication.

The device endpoint should be equivalent to:

```http
GET /api/v1/device/dashboard
Authorization: Bearer <DEVICE_API_KEY>
Accept: application/json
```

The server must authorize the device’s assigned portfolio and display configuration.

## 8. AI integration

Implement a provider-independent interface for Ollama, DeepSeek, and OpenAI. Store credentials securely, never return or log complete keys, and provide a Test Connection action that validates configuration, credentials, model availability, performs a small request, measures latency, and returns a clear result.

Support portfolio summaries, daily market summaries, contributor analysis, concentration warnings, unusual-movement explanations, comparisons, natural-language questions, and risk observations. Backend calculations are authoritative; AI must receive concise verified data and must distinguish facts from interpretation. Do not run inference on the ESP32.

## 9. ESP32 device management and firmware

Give each device a unique ID and track name, firmware, heartbeat, last fetch, Wi-Fi RSSI, uptime, API status, data version, assigned portfolio, and display settings. Define online/offline using a configurable heartbeat timeout.

The firmware must connect to Wi-Fi, authenticate, fetch compact JSON, parse safely, render the portrait dashboard, cache the last good response, handle failures, report health, use NTP, and avoid unnecessary refreshes. Use Preferences/nonvolatile storage for settings. Use bounded JSON/buffers, network timeouts, a watchdog where appropriate, and certificate validation for HTTPS. Never silently disable TLS verification.

## 10. ESP32 local administration page

On first boot without valid settings, start a temporary protected setup AP such as `LalitStock-Setup-001`, serve `192.168.4.1`, collect Wi-Fi and stock-app settings, test connectivity, save, and restart into normal mode. Require authentication for subsequent settings access, do not leave AP mode enabled permanently, and provide physical-button recovery.

The page must configure:

- Wi-Fi SSID/password and network scan.
- Stock application API URL and device API key.
- Independent API fetch interval in seconds.
- Portrait orientation and dashboard options.
- Automatic page rotation on/off.
- Requested page duration in seconds, default **10 seconds**.
- Optional page order/content settings where supported.
- Live page controls (act immediately, no restart required):
  - **Pause / Resume** automatic rotation (the paused state is persisted and survives reboot).
  - **Next page** — advance one page (wraps from N to 1).
  - **Go to page** — jump to a specific page number `1..N`; out-of-range or malformed input is rejected with a clear message.
  - Show the current page, total pages, paused/running state, and time until the next scheduled page change.
  - Manual page changes still obey the hardware-safe refresh guard: if a refresh is in progress or the minimum interval since the last full refresh has not elapsed, queue the change and report when it will be applied instead of forcing an unsafe refresh.
- Test Wi-Fi, test API, save, restart, and factory-reset/recovery actions.

Never display stored passwords or API keys in plaintext after initial entry.

## 11. Automatic sequential E-Paper pagination — mandatory

Because the four-color E-Paper is a full-page display, implement pagination rather than smooth scrolling.

### Functional behavior

1. Automatic page rotation is enabled by default.
2. The requested default page duration is **10 seconds**.
3. The administrator can set the duration in whole seconds from the ESP32 administration page.
4. Rotation proceeds sequentially: page 1, page 2, …, page N, then wraps to page 1.
5. Show a visible page indicator such as `PAGE 1/3` on every page.
6. Do not scroll text or partially reveal a page; each page is a complete, readable layout.
7. If rotation is disabled, remain on the selected page until changed or restarted.
8. If there is only one page, display `PAGE 1/1` and do not redraw repeatedly without a content change.
9. A page change must not trigger a market-data request.
10. A successful data fetch must update the cached model without resetting the current page unless explicitly configured.
11. On reboot, restore rotation enabled/disabled state, requested duration, and selected page from nonvolatile storage; clamp an invalid page to page 1.
12. If the configured page count changes, safely wrap or clamp the page index and continue.
13. The ESP32 administration page (and the simulator) provide **Pause/Resume**, **Next page**, and **Go to page N** controls (see section 10). Pausing keeps the current page on screen; resuming restarts the page timer from zero rather than refreshing immediately. A manual page change resets the rotation timer so the chosen page is shown for a full effective duration.

### Verified panel refresh timing (hardware evidence)

GxEPD2 1.6.9, `src/epd4c/GxEPD2_290c_GDEY029F51H.h` (panel GDEY029F51H, controller JD79667) declares `full_refresh_time = 25000` ms (measured ≈ 21.4 s) and `partial_refresh_time = 25000` ms, with `hasFastPartialUpdate = false`. A full refresh therefore takes longer than the requested 10 seconds and partial refresh offers no speed benefit. The 10-second request is **not hardware-safe** on this panel and must be clamped to a considerable, readable interval:

`effective = max(requested, ceil(full_refresh_time × (1 + safety_margin)) + minimum_dwell)`

with defaults `safety_margin = 20 %` and `minimum_dwell = 30 s`, giving an effective minimum of **60 seconds**. If the panel profile is unknown, use a conservative fallback of **180 seconds**. Manufacturer guidance on minimum intervals between color full refreshes (commonly ≥ 180 s for Good Display color panels) is not yet verified for this exact panel; mark it as a hardware-in-the-loop item.

### Independent schedules

Maintain separate timers/state machines for:

- API polling/fetch interval, configured independently by the user.
- Page-rotation interval, configured in seconds on the ESP32.
- Heartbeat/health reporting.
- NTP/time synchronization.

The implementation must not block rotation while a network request is pending, and must not fetch data merely because the display advanced. Handle `millis()` rollover or use a robust elapsed-time abstraction.

### Safe full-refresh validation and enforcement

The 10-second value is a requested default, not permission to exceed panel limits. At startup and when settings are saved, firmware must determine the effective safe full-refresh interval using the verified panel/driver specification and a conservative configurable safety margin.

- Validate the requested interval against the panel’s documented full-refresh timing, busy completion, thermal/power considerations, and any recommended minimum between full refreshes.
- If 10 seconds is safe, use 10 seconds as the effective interval.
- If 10 seconds is unsafe or cannot be verified, enforce a safe minimum or conservative fallback; never perform unsafe repeated full refreshes merely to honor the request.
- Persist the requested value, but use the effective safe value for scheduling.
- Show both values on the ESP32 admin page: **Requested page duration**, **Effective hardware-safe duration**, and a clear validation warning/reason.
- Expose the same values in device diagnostics and document the panel-specific evidence used.
- If the driver supports partial refresh, use it only after verification; do not use partial refresh to bypass an unknown four-color panel limitation.
- Avoid unnecessary redraws when content and page are unchanged.

### Page content

Design for exactly 168 × 384 portrait pixels. The dashboard header must include “Lalit Stock Application”, current date/time, last successful refresh, Wi-Fi status, API status, and market status. Stock pages must show ticker, current price, daily up/down state, daily percentage, and compact professional benchmark/portfolio metrics in readable tables. Use Dubai time by default, with NTP synchronization. On network failure, show cached data age and offline status rather than blanking the display.

## 12. Docker-based E-Paper simulator — testing only

Add a browser-based E-Paper simulation client to the Docker application. This is a development and QA tool, not a replacement for the ESP32 firmware and not a second production device type. It must be enabled and accessed from the web administration application, with a clear **Simulation mode — no physical E-Paper connected** label.

### Simulator goals

The simulator must reproduce the complete ESP32 experience before hardware deployment:

- A browser version of the ESP32 local administration page.
- An exact portrait preview at **168 × 384 logical pixels** using the same page model, fields, layout rules, colors, typography constraints, and page numbering as the firmware.
- A larger browser preview that scales the exact portrait canvas without changing its layout.
- A side-by-side configuration/preview workflow so changes can be tested immediately.
- The same dashboard output that the ESP32 would receive from `/api/v1/device/dashboard`.
- The same page count, page ordering, selected page, cached data, connection indicators, and rotation behavior as the firmware contract.

Do not create a separate mock dashboard with unrelated fields. The simulator must consume the shared device configuration schema and the same compact dashboard response/fixture used by firmware tests. Where the browser cannot reproduce hardware behavior exactly, show a clear simulation note.

### Simulated ESP32 administration features

Expose all settings required by the ESP32 local administration page:

- Device ID and device name.
- Wi-Fi SSID, signal strength, connected/disconnected state, and simulated network scan.
- Stock application API URL and device API-key entry with secret masking.
- API fetch interval in seconds, last fetch, last successful fetch, API connected/offline state, timeout, and cached-data age.
- Portrait orientation and dashboard visibility options.
- Automatic page rotation enabled/disabled, selected page, page order, and requested duration in seconds with default **10 seconds**.
- Requested page duration, effective hardware-safe duration, validation status, warning text, and the panel/driver assumption used by validation.
- Simulated NTP/timezone settings using `Asia/Dubai` by default.
- Test Wi-Fi, test API connection, save configuration, reload persisted configuration, restart simulation, and reset configuration.
- Simulated firmware version, uptime, heartbeat, last displayed data version, and device diagnostics.
- Explicit simulation controls for online/offline API, stale data, delayed response, invalid response, and NTP failure so failure displays can be verified.

Use the same validation rules as firmware for numeric ranges, invalid values, safe minimums, and page-index clamping. Persist simulator settings in the Docker application’s development/test storage, clearly separated from real device configuration. Never send simulator credentials to a physical device and never require a real API key for fixture mode.

### Simulated E-Paper output

The simulator must render the same output rules as the ESP32:

1. Render every page in an exact 168 × 384 portrait viewport.
2. Show `PAGE 1/N` (or the equivalent current-page indicator) on every page.
3. Rotate page 1 through page N sequentially and wrap to page 1.
4. Never use smooth scrolling or reveal partial pages.
5. Keep API polling, page rotation, heartbeat, and time synchronization on independent schedules.
6. Do not increase API request count when a page rotates.
7. Preserve the current page when new data arrives unless an explicit setting resets it.
8. Restore enabled/disabled rotation, duration, selected page, and configuration after simulator restart.
9. Show the same header: Lalit Stock Application, current date/time, last refresh, Wi-Fi status, API status, and market status.
10. Show the same stock fields, current prices, daily up/down status, percentages, portfolio summary, and professional benchmark table fields as the firmware.
11. Show cached data age and offline status when simulated connectivity fails; do not replace the dashboard with a blank screen.
12. Visually distinguish the four display colors and show a legend or simulation note explaining that browser colors approximate the physical panel.

The simulator must provide controls to pause/resume rotation, advance to the next page, return to page 1, change the requested duration, and inspect the effective interval. Manual controls are for testing and must not alter the firmware requirements.

### Safe-refresh simulation

The simulator must run the same safe full-refresh validation logic and display both requested and effective intervals. It must demonstrate at least these cases:

- 10 seconds accepted when the verified panel profile permits it.
- 10 seconds rejected or clamped when it is below the configured safe minimum.
- Unknown panel/driver profile producing a conservative fallback and visible warning.
- A page transition being scheduled independently from a simulated API request.

The simulator must not claim that a browser redraw reproduces E-Paper wear, ghosting, power use, BUSY timing, or thermal behavior. Those remain hardware-in-the-loop concerns.

### Simulator API and architecture

Implement the simulator as a Docker-served web module using the same backend contracts as the real device where practical. Provide fixture mode for deterministic tests and live mode for reading the authenticated dashboard endpoint. Keep simulator-only controls behind a development/test authorization boundary and disable them or protect them strongly in production deployments.

Record simulation events such as page changes, configuration saves, simulated fetches, validation warnings, and connection-state changes in development logs without recording secrets. Provide a reset action that clears only simulator state and requires confirmation if it would remove saved test configuration.

## 13. Interactive `manage.sh`

Create an executable, documented, interactive shell utility for the complete Docker application lifecycle. It must detect prerequisites, use safe quoting, return meaningful exit codes, log actions, and require explicit confirmation for destructive operations. Include at least these menu capabilities:

1. Install/check prerequisites
2. Create or edit environment configuration
3. Generate secrets
4. Build images
5. Start services
6. Stop services
7. Restart services
8. View service status
9. Follow logs
10. Run health checks
11. Run database migrations
12. Seed optional demo data
13. Create database backup
14. Restore a selected backup
15. Update images/source safely
16. Open web/API URLs
17. Run backend/frontend/firmware tests
18. Show configuration and deployment diagnostics with secrets redacted
19. Remove demo data or reset application data only after confirmation
20. Help/about/disclaimer and exit

Support non-interactive documented options where useful for VPS automation, but retain a safe interactive mode. Backups must be timestamped and restoration must warn clearly.

## 14. Documentation and attribution requirements

Create/update `README.md`, deployment documentation, API documentation, ESP32 setup/configuration documentation, troubleshooting, backup/restore instructions, and a hardware driver verification note. Explain automatic pagination, requested versus effective refresh interval, safe enforcement, persistence, and independent schedules.

Include the owner name, email, phone, and the disclaimer in source-code headers where appropriate, the web About/footer area, `manage.sh` help output, `prompt.md`, and `README.md`. Do not expose secrets or imply investment advice. Document the exact firmware/library/controller assumptions and mark unverified hardware facts explicitly.

## 15. Acceptance tests

### Backend and web

- Portfolio CRUD, transaction ledger, average-cost calculations, fees, sales, dividends, and splits are tested with decimal-safe values.
- Quote provider success, stale data, rate limiting, unavailable symbols, retry/backoff, and market-hours behavior are tested.
- Configurable 60-second backend refresh is persisted and observable.
- API keys are generated securely, shown once, hashed at rest, scoped, rate-limited, revocable, rotatable, expiry-aware, and absent from logs/responses.
- Admin authentication, authorization, audit logs, AI-provider credential redaction, and Test Connection behavior are tested.
- OpenAPI documentation and error responses are consistent.

### ESP32 pagination and refresh safety

- Default configuration is rotation enabled with requested duration 10 seconds.
- A three-page fixture renders page indicators `1/3`, `2/3`, `3/3` in order.
- The next transition from page N wraps to page 1.
- Rotation disabled prevents automatic transitions.
- Admin page Pause/Resume, Next page, and Go to page N work immediately, persist the paused state across reboot, reject out-of-range page numbers, and never force a refresh faster than the effective safe interval.
- With the verified JD79667 profile, a requested 10 s duration yields an effective 60 s duration and a visible warning citing the 25 s full-refresh time.
- One-page configuration stays at `1/1` without needless redraws.
- Requested duration, enabled state, and selected page survive reboot using nonvolatile storage.
- Invalid, zero, negative, oversized, or malformed settings are rejected or clamped safely.
- Requested interval and effective safe interval are distinct and visible.
- A panel-safe minimum is enforced when 10 seconds is too short or the panel timing is unknown.
- The warning explains why the effective value differs from the requested value.
- API polling and page rotation use independent clocks: page transitions do not increase fetch count, and a delayed fetch does not freeze rotation.
- Busy-pin completion, timeouts, Wi-Fi loss, API failure, cached data, NTP failure, and watchdog recovery are tested.
- Firmware compiles for the selected ESP32 board and the verified four-color driver; a hardware-in-the-loop display test is documented.

### Docker simulator

- Simulator administration exposes every ESP32 configuration setting and labels itself as testing/simulation only.
- The exact 168 × 384 portrait preview uses the same page data, page order, page indicators, and layout contract as the firmware.
- A larger preview scales the exact portrait canvas without reflowing or changing its logical layout.
- A three-page fixture displays `PAGE 1/3`, `PAGE 2/3`, `PAGE 3/3` in order and wraps to page 1.
- Simulator rotation defaults to enabled with requested duration 10 seconds and supports pause, resume, next-page, go-to-page-N, and page-one controls matching the ESP32 admin page.
- Simulator settings persist across reload/restart, including selected page, rotation state, duration, and safe-refresh warning.
- Simulator API polling and page rotation remain independent; page changes do not create extra fetches.
- Simulated offline, stale, delayed, invalid-response, and NTP-failure states match the firmware’s visible status behavior.
- Simulator displays requested and effective refresh intervals and applies the same minimum/clamping rules as firmware.
- Simulator fixture mode works without a real API key and never exposes or logs credentials.
- Simulator-only controls cannot change real ESP32 configuration and are protected or disabled in production.

### Deployment and operations

- Docker Compose starts cleanly from documented steps.
- `manage.sh` menu actions work, destructive actions confirm, diagnostics redact secrets, backups can be created/restored, and migrations are repeatable.
- Caddy/TLS, environment configuration, health endpoints, logs, and Hostinger deployment steps are documented.
- README, prompt, web UI, scripts, and code carry the required disclaimer/attribution where applicable.

## 16. Delivery sequence

Implement in this order:

1. Confirm hardware driver and display-only Hello World test.
2. Scaffold repository, Docker Compose, environment handling, database, migrations, health endpoints, and `manage.sh`.
3. Implement stock master, portfolios, transaction ledger, market-data provider, caching, scheduler, and analytics.
4. Implement authentication, scoped API keys, device registration, and OpenAPI endpoints.
5. Implement responsive web administration and AI provider settings/tests.
6. Implement the Docker E-Paper simulator using the shared ESP32 configuration schema, renderer contract, fixtures, independent timers, and simulation controls.
7. Implement ESP32 Wi-Fi/configuration portal, secure API client, persistence, dashboard renderer, independent timers, pagination, and safe refresh enforcement.
8. Add automated tests, firmware build/hardware tests, simulator tests, backups, observability, security review, documentation, and Hostinger deployment validation.

At every stage, preserve the confirmed GPIO mapping, four-color panel requirement, portrait dimensions, financial-data disclaimer, and requested-versus-effective E-Paper refresh behavior.

## Suggested instruction to a coding agent

> Read `prompt.md` completely before changing files. Implement the Lalit Stock Application according to every requirement, preserving the verified ESP32 hardware profile and all security/disclaimer requirements. Treat E-Paper pagination as page rotation, not scrolling. Implement the Docker-based E-Paper simulator as a testing-only client that mirrors every ESP32 setting and output using the shared schema and exact 168 × 384 preview. Implement the ESP32 admin settings with rotation enabled by default, requested 10-second duration, persistence, sequential wraparound, independent API polling, visible page numbers, and hardware-safe full-refresh validation that exposes both requested and effective intervals. Run and report the backend, simulator, and firmware acceptance tests and document any hardware fact that still requires physical verification.
