#!/usr/bin/env bash
# =============================================================================
# Lalit Stock Application - interactive operations utility
# Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973
# Disclaimer: informational software only, NOT financial advice. Market data may be
# delayed, incomplete or inaccurate. Provided without warranty of any kind.
#
# Usage:  ./manage.sh                 interactive menu
#         ./manage.sh <command> [-y]  non-interactive (see ./manage.sh help)
# Exit codes: 0 ok, 1 failure, 2 usage error, 3 missing prerequisite, 4 aborted by user
# =============================================================================
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: do not rewrite /api/... arguments into paths

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env"
BACKUP_DIR="$ROOT/backups"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/manage.log"
ASSUME_YES=false
mkdir -p "$LOG_DIR"

if [[ -t 1 ]]; then B=$'\e[1m'; R=$'\e[31m'; G=$'\e[32m'; Y=$'\e[33m'; N=$'\e[0m'; else B=""; R=""; G=""; Y=""; N=""; fi

log()  { printf '%s [%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" "$2" >>"$LOG_FILE"; }
info() { printf '%s\n' "${G}==>${N} $*"; log INFO "$*"; }
warn() { printf '%s\n' "${Y}WARN:${N} $*" >&2; log WARN "$*"; }
die()  { printf '%s\n' "${R}ERROR:${N} $*" >&2; log ERROR "$*"; exit "${2:-1}"; }

confirm() {  # confirm "question" -> 0 yes / 1 no
  $ASSUME_YES && return 0
  local ans
  read -r -p "$1 [y/N] " ans || return 1
  [[ "$ans" =~ ^[Yy]([Ee][Ss])?$ ]]
}

confirm_word() {  # destructive actions require typing a word
  $ASSUME_YES && return 0
  local ans
  read -r -p "$1 Type '$2' to continue: " ans || return 1
  [[ "$ans" == "$2" ]]
}

DC=()
compose() {
  if [[ ${#DC[@]} -eq 0 ]]; then
    if docker compose version >/dev/null 2>&1; then DC=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then DC=(docker-compose)
    else die "Docker Compose not found. Run: ./manage.sh check" 3; fi
  fi
  # The shell value overrides .env, so LAN_ADDRESS=auto reaches Caddy as a real IP.
  lan_ip >/dev/null  # resolve once in this shell (cached in LAN_IP)
  LAN_ADDRESS="$LAN_IP" "${DC[@]}" --env-file .env "$@"   # relative: we always run from the repo root
}

env_get() {  # env_get KEY -> value from .env (no sourcing, no eval)
  [[ -f "$ENV_FILE" ]] || return 0
  local line
  line="$(grep -E "^$1=" "$ENV_FILE" | tail -n1 || true)"
  line="${line#*=}"
  line="${line%%#*}"
  line="${line%"${line##*[![:space:]]}"}"
  printf '%s' "$line"
}

env_set() {  # env_set KEY VALUE (safe in-place update)
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  if grep -qE "^$key=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' "$ENV_FILE" >"$tmp"
  else
    cat "$ENV_FILE" >"$tmp"; printf '%s=%s\n' "$key" "$val" >>"$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
}

rand() { # rand LENGTH
  if command -v openssl >/dev/null 2>&1; then openssl rand -base64 64 | tr -dc 'A-Za-z0-9' | head -c "$1"
  else LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; fi
}

require_env() { [[ -f "$ENV_FILE" ]] || die "No .env file. Run: ./manage.sh env" 3; }

site_url() { local s; s="$(env_get SITE_ADDRESS)"; s="${s%%,*}"; s="${s:-localhost}"; [[ "$s" == :* ]] && echo "http://localhost${s}" || echo "https://${s}"; }  # first of a comma-separated list

detect_lan_ip() {  # IPv4 of the interface that holds the default route (Linux, macOS, Git Bash on Windows)
  local ip="" ifc
  if command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')"
  elif command -v powershell.exe >/dev/null 2>&1; then
    ip="$(powershell.exe -NoProfile -Command '$r = Get-NetRoute -DestinationPrefix 0.0.0.0/0 -ErrorAction SilentlyContinue | Sort-Object { $_.RouteMetric + (Get-NetIPInterface -InterfaceIndex $_.ifIndex -AddressFamily IPv4).InterfaceMetric } | Select-Object -First 1; if ($r) { (Get-NetIPAddress -InterfaceIndex $r.ifIndex -AddressFamily IPv4 | Select-Object -First 1).IPAddress }' 2>/dev/null | tr -d '\r')"
  elif command -v route >/dev/null 2>&1 && command -v ipconfig >/dev/null 2>&1; then
    ifc="$(route -n get default 2>/dev/null | awk '/interface:/ {print $2}')"
    [[ -n "$ifc" ]] && ip="$(ipconfig getifaddr "$ifc" 2>/dev/null)"
  fi
  [[ -z "$ip" ]] && ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [[ "$ip" =~ ^[0-9]+(\.[0-9]+){3}$ ]] && printf '%s' "$ip"
  return 0
}

LAN_IP=""
lan_ip() {  # LAN_ADDRESS from .env; empty or "auto" = detect now (follows DHCP changes); fallback 127.0.0.1
  if [[ -z "$LAN_IP" ]]; then
    LAN_IP="$(env_get LAN_ADDRESS)"
    [[ -z "$LAN_IP" || "$LAN_IP" == auto ]] && LAN_IP="$(detect_lan_ip)"
    LAN_IP="${LAN_IP:-127.0.0.1}"
  fi
  printf '%s' "$LAN_IP"
}
lan_url() { local s; s="$(lan_ip)"; [[ "$s" != 127.0.0.1 ]] && echo "https://${s}"; return 0; }

# ----------------------------------------------------------------------------- 1
cmd_check() {
  local ok=0
  info "Checking prerequisites"
  for c in docker curl; do
    if command -v "$c" >/dev/null 2>&1; then echo "  ${G}✓${N} $c: $($c --version 2>/dev/null | head -n1)"; else echo "  ${R}✗${N} $c missing"; ok=3; fi
  done
  if docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1; then echo "  ${G}✓${N} docker compose"; else echo "  ${R}✗${N} docker compose plugin missing"; ok=3; fi
  if docker info >/dev/null 2>&1; then echo "  ${G}✓${N} docker daemon reachable"; else echo "  ${R}✗${N} docker daemon not reachable (is Docker running / are you in the docker group?)"; ok=3; fi
  command -v openssl >/dev/null 2>&1 && echo "  ${G}✓${N} openssl" || echo "  ${Y}!${N} openssl not found (secrets fall back to /dev/urandom)"
  for c in python3 node arduino-cli; do command -v "$c" >/dev/null 2>&1 && echo "  ${G}✓${N} $c (optional, for local tests)" || echo "  ${Y}-${N} $c not found (optional)"; done
  [[ -f "$ENV_FILE" ]] && echo "  ${G}✓${N} .env present" || echo "  ${Y}!${N} .env missing (run: ./manage.sh env)"
  if [[ $ok -ne 0 ]]; then
    warn "Install Docker Engine + Compose plugin: https://docs.docker.com/engine/install/ (Hostinger VPS: Ubuntu packages)"
    return $ok
  fi
  info "Prerequisites OK"
}

# ----------------------------------------------------------------------------- 2
cmd_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ROOT/.env.example" "$ENV_FILE"; chmod 600 "$ENV_FILE" 2>/dev/null || true
    info "Created .env from .env.example"
    cmd_secrets --only-missing
  fi
  if $ASSUME_YES || [[ ! -t 0 ]]; then return 0; fi
  local key cur new
  echo "  LAN_ADDRESS: 'auto' detects this machine's IP at every start (detected now: $(detect_lan_ip || true)); or enter a fixed IP."
  for key in APP_ENV SITE_ADDRESS LAN_ADDRESS ACME_EMAIL MARKET_PROVIDER ADMIN_USERNAME HTTP_PORT HTTPS_PORT DEVICE_LAN_BIND DEVICE_LAN_PORT; do
    cur="$(env_get "$key")"
    read -r -p "  $key [$cur]: " new || true
    [[ -n "$new" ]] && env_set "$key" "$new"
  done
  if [[ -z "$(env_get ADMIN_PASSWORD)" ]] || confirm "Set a new initial admin password?"; then
    local p1 p2
    read -r -s -p "  ADMIN_PASSWORD (min 12 chars, blank = generate): " p1; echo
    if [[ -z "$p1" ]]; then p1="$(rand 20)"; echo "  Generated admin password: ${B}$p1${N}  (store it safely)"
    else read -r -s -p "  Repeat: " p2; echo; [[ "$p1" == "$p2" ]] || die "Passwords do not match" 2; fi
    [[ ${#p1} -ge 12 ]] || die "Password must be at least 12 characters" 2
    env_set ADMIN_PASSWORD "$p1"
  fi
  info ".env updated (secrets redacted in: ./manage.sh diag)"
}

# ----------------------------------------------------------------------------- 3
cmd_secrets() {
  require_env
  local only_missing=false; [[ "${1:-}" == "--only-missing" ]] && only_missing=true
  for key in APP_SECRET_KEY POSTGRES_PASSWORD; do
    if [[ -n "$(env_get "$key")" ]]; then
      $only_missing && continue
      if [[ "$key" == "POSTGRES_PASSWORD" ]]; then warn "Changing POSTGRES_PASSWORD after first start requires changing it inside the database too; skipped"; continue; fi
      confirm "Regenerate $key? Existing sessions and encrypted AI keys will become invalid." || continue
    fi
    env_set "$key" "$(rand 48)"
    info "Generated $key"
  done
  if [[ -z "$(env_get ADMIN_PASSWORD)" ]]; then
    local p; p="$(rand 20)"; env_set ADMIN_PASSWORD "$p"
    info "Generated initial admin password: ${B}$p${N} (shown once; change it after first login)"
  fi
}

# ----------------------------------------------------------------------------- 4..9
cmd_build()   { require_env; info "Building images"; compose build --pull; }
cmd_start()   { require_env; info "Starting services"; compose up -d; cmd_status; echo; info "Web UI: $(site_url)   API docs: $(site_url)/api/docs"; [[ -z "$(lan_url)" ]] || info "LAN:    $(lan_url)"; }
cmd_stop()    { require_env; info "Stopping services"; compose stop; }
cmd_restart() { require_env; info "Restarting services"; compose up -d; compose restart; }  # up -d first applies a changed .env / LAN IP
cmd_status()  { require_env; compose ps; }
cmd_logs()    { require_env; compose logs -f --tail=200 "${@}"; }

# ----------------------------------------------------------------------------- 10
cmd_health() {
  require_env
  local fail=0 out
  info "Health checks"
  local i
  for i in $(seq 1 12); do  # allow up to ~60 s for a (re)starting backend
    out="$(compose exec -T backend curl -fsS http://localhost:8000/api/health/ready 2>&1)" && break
    sleep 5
  done
  if [[ "$out" == *'"ready"'* ]]; then echo "  ${G}✓${N} backend ready: $out"; else echo "  ${R}✗${N} backend: $out"; fail=1; fi
  if compose exec -T db pg_isready -U "$(env_get POSTGRES_USER)" >/dev/null 2>&1; then echo "  ${G}✓${N} database accepting connections"; else echo "  ${R}✗${N} database"; fail=1; fi
  local url; url="$(site_url)"
  if curl -fsSk --max-time 10 "$url/api/health" >/dev/null 2>&1; then echo "  ${G}✓${N} web/proxy $url"; else echo "  ${R}✗${N} web/proxy $url"; fail=1; fi
  return $fail
}

# ----------------------------------------------------------------------------- 11
cmd_migrate() { require_env; info "Running database migrations (idempotent)"; compose exec -T backend alembic upgrade head; compose exec -T backend alembic current; }

# ----------------------------------------------------------------------------- 12 / 19
api_admin() {  # api_admin METHOD PATH [JSON] - runs inside the backend container, uses ADMIN creds
  compose exec -T -e M="$1" -e P="$2" -e BODY="${3:-}" backend python - <<'PY'
import os, sys, httpx
c = httpx.Client(base_url="http://localhost:8000")
r = c.post("/api/v1/auth/login", json={"username": os.environ.get("ADMIN_USERNAME", "admin"), "password": os.environ.get("ADMIN_PASSWORD", "")})
if r.status_code != 200:
    sys.exit(f"admin login failed ({r.status_code}); ADMIN_PASSWORD in .env must match the admin password")
# Session cookies are Secure (HTTPS-only); inside the container we talk plain HTTP, so send them explicitly.
h = {"X-CSRF-Token": r.json()["csrf_token"], "Content-Type": "application/json",
     "Cookie": "; ".join(f"{k}={v}" for k, v in r.cookies.items())}
c.cookies.clear()
r = c.request(os.environ["M"], os.environ["P"], headers=h, content=os.environ.get("BODY") or None)
print(r.status_code, r.text)
sys.exit(0 if r.status_code < 400 else 1)
PY
}
cmd_seed() { require_env; info "Loading optional demo data"; api_admin POST /api/v1/demo/seed '{}'; }
cmd_reset() {
  require_env
  echo "1) Remove demo data only   2) Reset ALL application data (portfolios, stocks, devices, keys)   3) Cancel"
  local ch; if $ASSUME_YES; then ch="${RESET_CHOICE:-1}"; else read -r -p "Choice: " ch; fi
  case "$ch" in
    1) confirm "Remove all demo portfolios, demo stocks and their transactions?" || exit 4
       api_admin POST /api/v1/demo/remove '{"confirm": true}' ;;
    2) confirm_word "This deletes ALL portfolios, transactions, stocks, devices and API keys (users/settings kept). Back up first!" RESET || exit 4
       cmd_backup
       compose exec -T backend python -c "from app.core.db import SessionLocal; from app.services.seed import reset_application_data as r; s=SessionLocal(); r(s); print('application data reset')" ;;
    *) info "Cancelled"; exit 4 ;;
  esac
}

# ----------------------------------------------------------------------------- 13 / 14
cmd_backup() {
  require_env
  mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR" 2>/dev/null || true
  local f; f="$BACKUP_DIR/lalitstock_$(date +%Y%m%d_%H%M%S).sql.gz"
  info "Creating backup $f"
  compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' | gzip >"$f"
  [[ -s "$f" ]] || die "Backup is empty"
  gzip -t "$f" || die "Backup archive is corrupt"
  info "Backup OK ($(du -h "$f" | cut -f1)). Store copies off-server; .env is NOT included (back it up separately and securely)."
}

cmd_restore() {
  require_env
  local f="${1:-}"
  if [[ -z "$f" ]]; then
    mapfile -t files < <(ls -1t "$BACKUP_DIR"/*.sql.gz 2>/dev/null || true)
    [[ ${#files[@]} -gt 0 ]] || die "No backups found in $BACKUP_DIR"
    local i=1; for x in "${files[@]}"; do echo "  $i) $(basename "$x")  $(du -h "$x" | cut -f1)"; i=$((i+1)); done
    local n; read -r -p "Restore which backup? " n
    [[ "$n" =~ ^[0-9]+$ && $n -ge 1 && $n -le ${#files[@]} ]] || die "Invalid selection" 2
    f="${files[$((n-1))]}"
  fi
  [[ -f "$f" ]] || die "Backup not found: $f" 2
  gzip -t "$f" || die "Backup archive is corrupt"
  warn "Restoring REPLACES the current database with $(basename "$f")."
  confirm_word "A safety backup of the current state is taken first." RESTORE || exit 4
  cmd_backup
  compose stop backend
  gunzip -c "$f" | compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null
  compose start backend
  cmd_migrate
  info "Restore complete"
}

# ----------------------------------------------------------------------------- 15
cmd_update() {
  require_env
  confirm "Back up, pull latest source (git, fast-forward only), rebuild and restart?" || exit 4
  cmd_backup
  if [[ -d .git ]]; then
    git diff --quiet || die "Uncommitted local changes; commit or stash them first"
    git pull --ff-only
  else warn "Not a git checkout; skipping source update"; fi
  compose pull db web 2>/dev/null || true
  compose build --pull
  compose up -d
  cmd_migrate
  cmd_health || warn "Health check reported problems; previous backup is in $BACKUP_DIR"
}

# ----------------------------------------------------------------------------- 16
cmd_open() {
  lan_ip >/dev/null
  local url; url="$(site_url)"
  echo "Web UI:   $url"; echo "API docs: $url/api/docs"; echo "Health:   $url/api/health"
  [[ -z "$(lan_url)" ]] || echo "LAN:      $(lan_url)  (other devices will warn about the internal CA certificate)"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then open "$url" || true
  elif command -v cmd.exe >/dev/null 2>&1; then cmd.exe /c start "" "$url" >/dev/null 2>&1 || true; fi
}

# ----------------------------------------------------------------------------- 17
cmd_test() {
  local which="${1:-all}" fail=0
  if [[ "$which" == all || "$which" == backend ]]; then
    info "Backend tests (pytest, fixture provider, SQLite)"
    if [[ -x backend/.venv/bin/python || -x backend/.venv/Scripts/python ]]; then
      local py=backend/.venv/bin/python; [[ -x $py ]] || py=backend/.venv/Scripts/python
      (cd backend && "../$py" -m pytest -q) || fail=1
    else
      docker build -q -f backend/Dockerfile --build-arg INSTALL_DEV=true -t lalitstock-backend-test . >/dev/null &&
        docker run --rm lalitstock-backend-test python -m pytest -q || fail=1
    fi
  fi
  if [[ "$which" == all || "$which" == frontend ]]; then
    info "Frontend/simulator tests (vitest + type check)"
    if command -v npm >/dev/null 2>&1; then (cd frontend && { [[ -d node_modules ]] || npm ci; } && npx tsc -b && npx vitest run) || fail=1
    else docker run --rm -v "$ROOT:/w" -w /w/frontend node:22-alpine sh -c "npm ci && npx tsc -b && npx vitest run" || fail=1; fi
  fi
  if [[ "$which" == all || "$which" == firmware ]]; then
    info "Firmware logic host tests (g++)"
    if command -v g++ >/dev/null 2>&1; then bash firmware/test/run_host_tests.sh || fail=1; else warn "g++ not found; skipped"; fi
    if command -v arduino-cli >/dev/null 2>&1; then
      info "Firmware compile check (esp32:esp32:esp32, min_spiffs)"
      arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=min_spiffs firmware/LalitStockFirmware || fail=1
    else warn "arduino-cli not found; firmware compile skipped (see docs/ESP32_SETUP.md)"; fi
  fi
  [[ $fail -eq 0 ]] && info "All selected tests passed" || die "Some tests failed"
}

# ----------------------------------------------------------------------------- 18
cmd_diag() {
  info "Configuration (secrets redacted)"
  if [[ -f "$ENV_FILE" ]]; then
    sed -E 's/^((APP_SECRET_KEY|POSTGRES_PASSWORD|ADMIN_PASSWORD)[^=]*)=.+$/\1=[REDACTED]/' "$ENV_FILE" | grep -vE '^\s*(#|$)'
  else echo "  (no .env)"; fi
  echo; info "Versions"
  docker --version 2>/dev/null || true
  compose version 2>/dev/null || true
  [[ -d .git ]] && echo "git: $(git rev-parse --short HEAD 2>/dev/null) $(git status --porcelain | wc -l | tr -d ' ') uncommitted" || true
  echo; info "LAN address"; echo "  LAN_ADDRESS=$(env_get LAN_ADDRESS) -> $(lan_ip)"
  echo; info "Services"; compose ps 2>/dev/null || true
  echo; info "Disk"; df -h "$ROOT" | tail -n1
  echo; info "Backups"; ls -1t "$BACKUP_DIR" 2>/dev/null | head -n5 || echo "  none"
  echo; info "Recent backend errors"; compose logs --tail=300 backend 2>/dev/null | grep -E '"level": "(ERROR|WARNING)"' | tail -n10 || true
}

# ----------------------------------------------------------------------------- 20
cmd_help() {
  cat <<EOF
${B}Lalit Stock Application - manage.sh${N}
Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973

Usage: ./manage.sh [command] [-y]      (no command = interactive menu; -y = assume yes)

  check            Install/check prerequisites          health       Run health checks
  env              Create or edit .env                   migrate      Run database migrations
  secrets          Generate missing secrets              seed         Load optional demo data
  build            Build images                          backup       Create timestamped DB backup
  start|stop       Start / stop services                 restore [F]  Restore a backup (confirms)
  restart          Restart services                      update       Back up, pull, rebuild, restart
  status           Service status                        open         Show/open web & API URLs
  logs [svc]       Follow logs                           test [backend|frontend|firmware|all]
  diag             Diagnostics (secrets redacted)        reset        Remove demo data / reset data (confirms)
  help             This help

Exit codes: 0 ok, 1 failure, 2 usage, 3 missing prerequisite, 4 aborted.
Log file: logs/manage.log

${Y}Disclaimer:${N} this software is informational only and is NOT financial advice. Market data
may be delayed, incomplete, inaccurate or unavailable; AI output may be wrong. You are
responsible for credentials, security, backups, licensing and provider terms.
Provided without warranty of fitness, availability or investment performance.
EOF
}

menu() {
  while true; do
    cat <<EOF

${B}Lalit Stock Application${N} - operations menu
  1) Install/check prerequisites     11) Run database migrations
  2) Create/edit environment         12) Seed optional demo data
  3) Generate secrets                13) Create database backup
  4) Build images                    14) Restore a backup
  5) Start services                  15) Update images/source safely
  6) Stop services                   16) Open web/API URLs
  7) Restart services                17) Run backend/frontend/firmware tests
  8) View service status             18) Diagnostics (secrets redacted)
  9) Follow logs                     19) Remove demo data / reset data
 10) Run health checks               20) Help / about / disclaimer, then exit
  q) Quit
EOF
    local c; read -r -p "Select: " c || exit 0
    case "$c" in
      1) cmd_check || true ;; 2) cmd_env ;; 3) cmd_secrets ;; 4) cmd_build ;; 5) cmd_start ;; 6) cmd_stop ;;
      7) cmd_restart ;; 8) cmd_status ;; 9) cmd_logs || true ;; 10) cmd_health || true ;; 11) cmd_migrate ;;
      12) cmd_seed || true ;; 13) cmd_backup ;; 14) cmd_restore ;; 15) cmd_update ;; 16) cmd_open ;;
      17) cmd_test || true ;; 18) cmd_diag ;; 19) (cmd_reset) || true ;; 20) cmd_help; exit 0 ;;
      q|Q) exit 0 ;; *) warn "Unknown choice: $c" ;;
    esac
  done
}

main() {
  local args=()
  for a in "$@"; do case "$a" in -y|--yes) ASSUME_YES=true ;; *) args+=("$a") ;; esac; done
  set -- "${args[@]+"${args[@]}"}"
  local cmd="${1:-}"; shift || true
  log INFO "command: ${cmd:-menu} $*"
  case "$cmd" in
    "") menu ;;
    check) cmd_check ;; env) cmd_env ;; secrets) cmd_secrets "$@" ;; build) cmd_build ;; start|up) cmd_start ;;
    stop) cmd_stop ;; restart) cmd_restart ;; status|ps) cmd_status ;; logs) cmd_logs "$@" ;; health) cmd_health ;;
    migrate) cmd_migrate ;; seed) cmd_seed ;; backup) cmd_backup ;; restore) cmd_restore "$@" ;; update) cmd_update ;;
    open|urls) cmd_open ;; test) cmd_test "$@" ;; diag) cmd_diag ;; reset) cmd_reset ;; help|-h|--help|about) cmd_help ;;
    *) cmd_help; exit 2 ;;
  esac
}

trap 'log ERROR "failed at line $LINENO: $BASH_COMMAND"' ERR
main "$@"
