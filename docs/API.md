# API overview

The interactive OpenAPI documentation is at `/api/docs` (ReDoc at `/api/redoc`, schema at `/api/openapi.json`). Errors always have the shape:

```json
{"error": {"status": 422, "message": "Validation failed", "details": [{"loc": ["body", "name"], "message": "..."}]}}
```

## Authentication

| Client | Mechanism |
|---|---|
| Admin UI | `POST /api/v1/auth/login` sets an HttpOnly `ls_session` cookie (JWT; revocable server-side session) and an `ls_csrf` cookie. Every non-GET request must send `X-CSRF-Token: <ls_csrf>`. Logins are limited to 10/min per IP. |
| ESP32 device | `Authorization: Bearer lsk_<prefix>_<secret>`. Only an HMAC of the key is stored. Keys are scoped (`device:dashboard`, `device:heartbeat`), bound to one device, can expire, are rate-limited (default 30/min per key) and every request is written to the access log. |

## Device endpoints

```http
GET /api/v1/device/dashboard?rows=8&summary=true&bench=true&since=<data_version>
Authorization: Bearer <DEVICE_API_KEY>
Accept: application/json
```

Returns the compact render contract ([RENDER_CONTRACT.md](RENDER_CONTRACT.md)), or `304` when `since` equals the current `data_version`. The server always uses the device's **assigned portfolio**. Query parameters can only narrow the display options.

```http
POST /api/v1/device/heartbeat
{"firmware":"1.0.0","rssi":-61,"uptime_s":3600,"api_status":"OK","data_version":"5dd71974ca86","page":2,"pages":3,
 "rotation_enabled":true,"requested_s":10,"effective_s":60,"panel_profile":"JD79667_GDEY029F51H",
 "free_heap":180000,"fetch_count":30,"refresh_count":61,"ntp_ok":true,"last_error":""}
```

## Admin endpoints (summary)

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/password`, `GET /auth/sessions`, `POST /auth/sessions/{id}/revoke` |
| Stocks | `GET/POST /stocks`, `POST /stocks/validate`, `GET/PUT/DELETE /stocks/{id}`, `POST /stocks/{id}/refresh`, `GET /stocks/{id}/history` |
| Benchmarks | `GET/POST /benchmarks`, `PUT/DELETE /benchmarks/{id}` |
| Portfolios | `GET/POST /portfolios`, `GET/PUT/DELETE /portfolios/{id}`, `GET /portfolios/{id}/summary`, `GET /portfolios/{id}/history` |
| Ledger | `GET/POST /portfolios/{id}/transactions`, `PUT/DELETE /transactions/{id}` (each write re-validates the whole ledger and is audited) |
| Brokers | `GET/POST /brokers`, `PUT/DELETE /brokers/{id}` |
| Analytics | `GET /analytics/overview` |
| Market data | `GET /market/status`, `POST /market/refresh`, `POST /market/history` |
| Settings | `GET/PUT /settings` (quote interval, timeouts, retries, backoff, market-hours optimisation, stale threshold, heartbeat timeout, device rate limit, timezone) |
| Devices | `GET/POST /devices`, `PUT/DELETE /devices/{id}`, `GET /devices/{id}/preview` |
| API keys | `GET/POST /api-keys`, `GET /api-keys/scopes`, `POST /api-keys/{id}/revoke`, `POST /api-keys/{id}/rotate`, `GET /api-keys/{id}/logs`, `GET /access-logs` |
| AI | `GET/POST /ai/providers`, `PUT/DELETE /ai/providers/{id}`, `POST /ai/providers/{id}/test`, `POST /ai/insights` |
| Simulator (dev/test) | `GET /simulator/contract`, `GET/PUT /simulator/config`, `PUT /simulator/runtime`, `GET /simulator/fixture`, `GET /simulator/dashboard`, `GET /simulator/refresh-check`, `GET/POST /simulator/events`, `POST /simulator/reset` |
| System | `GET /api/health`, `GET /api/health/ready`, `GET /about`, `GET /audit`, `POST /demo/seed`, `POST /demo/remove` |

All admin paths are prefixed with `/api/v1`. Money values are returned as decimal **strings** to preserve precision.
