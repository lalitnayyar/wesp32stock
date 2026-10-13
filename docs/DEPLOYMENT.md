# Deployment

Owner: Lalit Nayyar · consult@lalit.cloud. Not financial advice.

## Services (`docker-compose.yml`)

| Service | Image | Purpose |
|---|---|---|
| `db` | postgres:16-alpine | Data (volume `db_data`) |
| `backend` | built from `backend/Dockerfile` | FastAPI; runs `alembic upgrade head` on start; scheduler for quotes/history |
| `web` | built from `frontend/Dockerfile` | Caddy serving the React build and proxying `/api/*` to the backend; automatic HTTPS |

Health: `GET /api/health` (liveness), `GET /api/health/ready` (database + scheduler). `./manage.sh health` checks all three services.

## Local

```bash
./manage.sh env && ./manage.sh build && ./manage.sh start
```

- `SITE_ADDRESS=localhost` gives HTTPS through Caddy's internal CA. Trust it once with `docker compose exec web caddy trust`, or accept the browser warning.
- Other devices on the LAN reach the UI at `https://<pc-ip>/`. `LAN_ADDRESS=auto` is detected by `./manage.sh start`/`restart`; plain `docker compose` needs a fixed IP in `LAN_ADDRESS`. Browsers send no SNI for IP addresses, so the Caddyfile serves the IP in its own `tls internal` site block with `default_sni`.
- Development without Docker: `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && DATABASE_URL=sqlite:///./dev.db ADMIN_PASSWORD=... uvicorn app.main:app --reload`, plus `cd frontend && npm ci && npm run dev` (Vite proxies `/api` to `:8000`).
- ESP32 on your LAN during development: set `DEVICE_LAN_BIND=0.0.0.0` and `DEVICE_LAN_PORT=8000`, then use `http://<pc-ip>:8000` as the device API URL. This is plain HTTP, so use it for development only. The device admin page labels it **INSECURE HTTP**.

## Hostinger VPS (Ubuntu 22.04/24.04)

1. Point a DNS A/AAAA record (for example `stock.example.com`) at the VPS IP.
2. Install Docker Engine and the Compose plugin (https://docs.docker.com/engine/install/ubuntu/) and add your user to the `docker` group.
3. Open the firewall for 80/tcp and 443/tcp only (`ufw allow 80,443/tcp`). Do **not** expose 5432 or 8000. Keep `DEVICE_LAN_BIND=127.0.0.1`.
4. Copy the repository to the VPS (for example `git clone`), then:
   ```bash
   ./manage.sh env      # APP_ENV=production, SITE_ADDRESS=stock.example.com, ACME_EMAIL=you@domain
   ./manage.sh build && ./manage.sh start
   ./manage.sh health
   ```
   Caddy obtains a Let's Encrypt certificate automatically. In production the simulator is disabled unless `SIMULATOR_ENABLED=true`, and the backend refuses to start with a weak `APP_SECRET_KEY`.
5. Sign in at `https://stock.example.com`, change the admin password (Settings → Security), and remove `ADMIN_PASSWORD` from `.env` if you like (it is only used to create the first admin).
6. Schedule backups, for example with cron: `0 2 * * * cd /opt/lalitstock && ./manage.sh backup -y >> logs/cron.log 2>&1`, and copy `backups/` off the server.
7. Updates: `./manage.sh update` (backup → `git pull --ff-only` → rebuild → migrate → health check).

No code changes are needed between local and VPS. Only `.env` differs.

## Environment variables

See `.env.example`. Keep comments on their own lines (Compose may read inline text as part of a value). The important ones:

| Variable | Notes |
|---|---|
| `APP_SECRET_KEY` | ≥ 32 random characters. Signs sessions, peppers API-key hashes and derives the AI-credential encryption key. Rotating it invalidates sessions, device keys and stored AI keys. |
| `POSTGRES_PASSWORD` | Set before the first start. Changing it later also requires `ALTER USER` in Postgres. |
| `ADMIN_PASSWORD` | ≥ 12 characters. Creates the first admin only. |
| `MARKET_PROVIDER` | `yahoo` or `fixture`. |
| `SITE_ADDRESS` | Domain on a VPS. `localhost` locally. `:80` behind another TLS proxy. |
| `LAN_ADDRESS` | IP that LAN devices use (`https://<ip>/`, Caddy internal CA). `auto` (default) = detected by `manage.sh` on each start/restart; or a fixed IP. |
| `COOKIE_SECURE` | Keep `true` behind HTTPS. |

## Scaling notes

The backend is a modular monolith running a single instance. The rate limiter and the scheduler lock are in-process, so if you ever run more than one backend replica, move them to Postgres-backed equivalents first.
