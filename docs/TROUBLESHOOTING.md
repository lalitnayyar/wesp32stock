# Troubleshooting

## Server

| Symptom | Check |
|---|---|
| `docker compose` cannot connect | Start Docker Desktop / the docker service, then run `./manage.sh check` |
| Image build fails with `CERTIFICATE_VERIFY_FAILED` | An antivirus or proxy is inspecting TLS. Export its root CA to `deploy/extra-ca/*.crt` (see the README there) and rebuild. Never disable verification. |
| All quotes fail with `KeyError: 'currentTradingPeriod'` or similar | Yahoo changed its responses. Update `yfinance` in `backend/requirements.txt` and run `./manage.sh update`. |
| Quotes `rate_limited` | Increase the quote refresh interval and backoff in Settings. Polling is central, so devices never call Yahoo. |
| Cannot sign in on a fresh install (no admin user) | Set `ADMIN_PASSWORD` (≥ 12 characters) in `.env` before the first start, then `./manage.sh restart`. |
| Backend exits with "APP_SECRET_KEY must be set" | In production the key must be ≥ 32 random characters: `./manage.sh secrets`. |
| Browser warns about the certificate on `https://localhost` | Caddy's local CA: `docker compose exec web caddy trust`, or accept the warning. |
| A value from `.env` is ignored or wrong | Comments must be on their own line, not after a value. |
| Logged out immediately over plain HTTP | `COOKIE_SECURE=true` requires HTTPS. Set it to false only for plain-HTTP development. |
| Benchmark cannot be activated | The symbol failed provider validation. Check it with Stocks → Validate. |

## Telegram bot

| Symptom | Check |
|---|---|
| Status `starting / error`, `Unauthorized` | Wrong or revoked token. Paste a new one from @BotFather and Save. |
| `Conflict: terminated by other getUpdates request` | Another program or install polls the same token. Use one token per server. |
| Error mentions a webhook | Open `https://api.telegram.org/bot<token>/deleteWebhook` once. |
| "This chat is not authorised" | Add the shown chat ID under Settings → Telegram bot → Allowed chat IDs. |
| `Telegram unreachable` | No outbound HTTPS to api.telegram.org, or a TLS-inspecting antivirus whose root CA is missing from `deploy/extra-ca/`. |
| AI provider test: `Unsupported parameter: 'max_tokens'` | Fixed: run `./manage.sh update` (OpenAI gpt-5 models need `max_completion_tokens`). |

## ESP32

| Symptom | Check |
|---|---|
| Upload stuck at `Connecting...` | Hold BOOT until the upload starts. Close the serial monitor. |
| `Sketch too big` | Use `PartitionScheme=min_spiffs` (`firmware\flash.bat` does this). |
| Blank screen | Wiring, 3V3, and the 4C driver. Run `upload.bat` (Hello World) first. |
| `API:ERR` + "API key rejected" | The key is revoked/expired, lacks a scope, or isn't bound to a registered device. Create keys from the device's row in **E-Paper Devices**, which binds them automatically. |
| `API:OFF` | Wi-Fi is down or the server is unreachable. Check the URL and DNS. HTTPS needs a valid certificate (or a custom root CA). |
| Wi-Fi OK, `API OFF`, fetches `0/0`, NTP not synced | Still in setup mode: Wi-Fi, API URL, API key and admin password must all be saved before the network task starts. |
| `connection failed: connection refused` | Server port not reachable: set `DEVICE_LAN_BIND=0.0.0.0` and restart; on WSL2 mirrored mode add the Hyper-V firewall rule (see the README). **Test API checks the saved settings**: Save, then test. |
| LAN API URL | `http://<pc-ip>:<DEVICE_LAN_PORT>` (e.g. `http://192.168.68.135:8174`), with no path. The base URL returns 404 in a browser by design. `/api/health` returns ok. |
| `NO TIME SYNC` in the header | NTP is blocked. Check the NTP server setting and outbound UDP 123. |
| Pages change every 60 s although 10 s was requested | Expected: the effective hardware-safe duration (see the admin page reason). |
| Manual "Next page" appears later | It is queued behind the 30 s refresh guard or an ongoing ~21 s refresh. |
| Old image remains after unplugging | Normal E-Paper behaviour. |
| Forgot the device admin password | Hold BOOT for 15 s to factory reset. |
