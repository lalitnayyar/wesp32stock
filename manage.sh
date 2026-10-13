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
  # The web container mounts firmware/dist read-only; create it as this user, not as root via Docker.
  mkdir -p firmware/dist
  # SITE_ADDRESS set to the LAN IP itself would define the same Caddy site twice ("ambiguous site
  # definition"); the LAN_ADDRESS block already serves that IP, so give Caddy "localhost" instead.
  local site; site="$(env_get SITE_ADDRESS)"; site="${site:-localhost}"
  [[ "$site" == "$LAN_IP" ]] && site=localhost
  SITE_ADDRESS="$site" LAN_ADDRESS="$LAN_IP" "${DC[@]}" --env-file .env "$@"   # relative: we always run from the repo root
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

port_suffix() { [[ -z "$1" || "$1" == "$2" ]] || printf ':%s' "$1"; }  # port_suffix PORT DEFAULT -> "" or ":PORT"
https_suffix() { port_suffix "$(env_get HTTPS_PORT)" 443; }

site_url() {  # first of a comma-separated SITE_ADDRESS, with HTTPS_PORT appended when it is not 443
  local s; s="$(env_get SITE_ADDRESS)"; s="${s%%,*}"; s="${s:-localhost}"
  if [[ "$s" == :* ]]; then echo "http://localhost${s}"          # plain-HTTP mode, e.g. ":80"
  elif [[ "$s" == *:* ]]; then echo "https://${s}"               # explicit host:port
  else echo "https://${s}$(https_suffix)"; fi
}

# WSL2 in its default NAT mode puts Linux behind a private VM address (172.16-31.x) that only this
# Windows PC can reach; other LAN devices must use the Windows IP plus a port proxy (or mirrored mode).
is_wsl() { grep -qi microsoft /proc/version 2>/dev/null; }
wsl_nat() { is_wsl || return 1; [[ "$(wslinfo --networking-mode 2>/dev/null | tr -d '\r')" != mirrored ]]; }
wsl_vm_ip() { ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}'; }

windows_lan_ip() {  # IPv4 of the Windows interface with the best default route (Git Bash or WSL interop)
  command -v powershell.exe >/dev/null 2>&1 || return 0
  powershell.exe -NoProfile -Command '$r = Get-NetRoute -DestinationPrefix 0.0.0.0/0 -ErrorAction SilentlyContinue | Sort-Object { $_.RouteMetric + (Get-NetIPInterface -InterfaceIndex $_.ifIndex -AddressFamily IPv4).InterfaceMetric } | Select-Object -First 1; if ($r) { (Get-NetIPAddress -InterfaceIndex $r.ifIndex -AddressFamily IPv4 | Select-Object -First 1).IPAddress }' 2>/dev/null | tr -d '\r'
}

detect_lan_ip() {  # IPv4 of the interface that holds the default route (Linux, macOS, Git Bash, WSL)
  local ip="" ifc
  if wsl_nat; then
    ip="$(windows_lan_ip)"   # the address LAN devices actually see; reached via the port proxy below
  fi
  if [[ -n "$ip" ]]; then :
  elif command -v ip >/dev/null 2>&1; then
    ip="$(wsl_vm_ip)"
  elif command -v powershell.exe >/dev/null 2>&1; then
    ip="$(windows_lan_ip)"
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
lan_url() { local s; s="$(lan_ip)"; [[ "$s" != 127.0.0.1 ]] && echo "https://${s}$(https_suffix)"; return 0; }

app_url() {  # the URL to show and probe: the LAN IP when the site is local, otherwise SITE_ADDRESS (a domain)
  local s l; s="$(site_url)"; l="$(lan_url)"
  if [[ -n "$l" && "$s" =~ ^https?://(localhost|127\.0\.0\.1)(:|$) ]]; then echo "$l"; else echo "$s"; fi
}

wsl_mirrored_hint() {  # mirrored mode: the IP needs host loopback (this PC) and a Hyper-V firewall rule (LAN)
  local p="$(env_get HTTPS_PORT)" h="$(env_get HTTP_PORT)"
  echo "    WSL2 mirrored mode. To use the IP from this PC, add to %UserProfile%\\.wslconfig:"
  echo "        [experimental]"
  echo "        hostAddressLoopback=true"
  echo "      then 'wsl --shutdown' (stops all WSL apps) and './manage.sh start'."
  echo "    For other LAN devices, allow the ports in the Hyper-V firewall (admin PowerShell):"
  echo "        New-NetFirewallHyperVRule -Name LalitStock -DisplayName 'Lalit Stock' -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts ${p:-443},${h:-80} -Action Allow"
}

wsl_hint() {  # how to reach a WSL2 (NAT mode) deployment from other LAN devices, e.g. a phone or the ESP32
  wsl_nat || return 0
  local win vm p ports=()
  win="$(lan_ip)"; vm="$(wsl_vm_ip)"
  for p in "$(env_get HTTPS_PORT)" "$(env_get HTTP_PORT)"; do ports+=("${p:-}"); done
  [[ -z "${ports[0]}" ]] && ports[0]=443; [[ -z "${ports[1]}" ]] && ports[1]=80
  [[ "$(env_get DEVICE_LAN_BIND)" == 0.0.0.0 ]] && ports+=("$(env_get DEVICE_LAN_PORT)")
  echo
  warn "WSL2 NAT networking detected (Linux VM address ${vm:-unknown}). This PC: $(site_url)"
  echo "  Other LAN devices need either:"
  echo "   a) mirrored networking (recommended): add to %UserProfile%\\.wslconfig"
  echo "        [wsl2]"
  echo "        networkingMode=mirrored"
  echo "      then run 'wsl --shutdown' in Windows and './manage.sh start' again; or"
  echo "   b) a port proxy (admin PowerShell; re-run after each WSL restart, the VM address changes):"
  for p in "${ports[@]}"; do
    [[ -n "$p" ]] || continue
    echo "        netsh interface portproxy add v4tov4 listenaddress=$win listenport=$p connectaddress=$vm connectport=$p"
  done
  echo "        New-NetFirewallRule -DisplayName 'Lalit Stock' -Direction Inbound -Protocol TCP -LocalPort $(IFS=,; echo "${ports[*]}") -Action Allow"
}

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
cmd_start()   { require_env; info "Starting services"; compose up -d; cmd_status; echo; print_urls; wsl_hint; }

print_urls() {
  lan_ip >/dev/null  # resolve once in this shell (cached in LAN_IP)
  local url; url="$(app_url)"
  echo "Web UI:   $url"; echo "API docs: $url/api/docs"; echo "Health:   $url/api/health"
  [[ "$url" == "$(site_url)" ]] || echo "(This PC also: $(site_url). Other devices will warn about the internal CA certificate.)"
}
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
  lan_ip >/dev/null
  local url local_url; url="$(app_url)"; local_url="$(site_url)"
  if curl -fsSk --max-time 10 "$url/api/health" >/dev/null 2>&1; then echo "  ${G}✓${N} web/proxy $url"
  elif [[ "$url" != "$local_url" ]] && curl -fsSk --max-time 10 "$local_url/api/health" >/dev/null 2>&1; then
    echo "  ${Y}!${N} web/proxy $local_url OK, but $url is not reachable from here"
    if wsl_nat; then echo "    (WSL2 NAT mode: enable mirrored networking or the port proxy; see ./manage.sh open)"
    elif is_wsl; then wsl_mirrored_hint; fi
  else echo "  ${R}✗${N} web/proxy $url"; fail=1; fi
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
# Source repository; override with REPO_URL / REPO_BRANCH in .env or the environment.
REPO_URL_DEFAULT="https://github.com/lalitnayyar/wesp32stock.git"
repo_url()    { local v; v="${REPO_URL:-$(env_get REPO_URL)}"; printf '%s' "${v:-$REPO_URL_DEFAULT}"; }
repo_branch() { local v; v="${REPO_BRANCH:-$(env_get REPO_BRANCH)}"; printf '%s' "${v:-main}"; }
# Runs in $ROOT (the script cd's there; no -C, which Git Bash would pass to git.exe unconverted).
# safe.directory, for these calls only: WSL checkouts under /mnt/c belong to another uid and git refuses them.
g() { git -c safe.directory='*' "$@"; }

PULL_SELF_CHANGED=false
cmd_pull() {  # fetch the latest code from GitHub and fast-forward; never touches .env, backups or logs
  command -v git >/dev/null 2>&1 || die "git not found (Ubuntu/WSL: sudo apt install git)" 3
  local url branch old new stamp
  url="$(repo_url)"; branch="$(repo_branch)"; stamp="$(date +%Y%m%d_%H%M%S)"
  info "Source: $url ($branch)"

  if [[ ! -d "$ROOT/.git" ]]; then
    warn "This folder is not a git checkout (copied or unzipped files)."
    confirm "Connect it to $url and replace the code with the latest $branch? (.env, backups and logs are kept)" || exit 4
    mkdir -p "$BACKUP_DIR"
    tar -czf "$BACKUP_DIR/source_before_pull_$stamp.tar.gz" -C "$ROOT" --exclude=./backups --exclude=./logs \
      --exclude=node_modules --exclude=.venv --exclude=__pycache__ --exclude=./.git . \
      && info "Saved current files to backups/source_before_pull_$stamp.tar.gz"
    g init -q
    g remote add origin "$url"
    g fetch --quiet origin "$branch" || die "Cannot fetch $url ($branch). Check the network or REPO_URL."
    g checkout -q -f -B "$branch" "origin/$branch"
    g branch -q --set-upstream-to="origin/$branch" "$branch"
    PULL_SELF_CHANGED=true
    info "Now tracking $url ($branch) at $(g log -1 --format='%h %s')"
    return 0
  fi

  if g remote get-url origin >/dev/null 2>&1; then
    [[ "$(g remote get-url origin)" == "$url" ]] || warn "origin is $(g remote get-url origin) (expected $url); using origin"
  else
    g remote add origin "$url"
  fi
  g fetch --quiet origin "$branch" || die "Cannot fetch origin/$branch. Check the network or REPO_URL."
  old="$(g rev-parse HEAD)"
  if [[ -z "$(g rev-list "HEAD..origin/$branch")" ]]; then info "Already up to date ($(g log -1 --format='%h %s'))"; return 0; fi

  echo "Incoming changes:"; g log --oneline --no-decorate "HEAD..origin/$branch" | sed 's/^/  /'
  if [[ -n "$(g status --porcelain --untracked-files=no)" ]]; then
    warn "You have local edits to tracked files:"; g status --short --untracked-files=no | sed 's/^/  /'
    confirm "Stash them (kept safely; restore later with 'git stash pop') and continue?" || exit 4
    g stash push -q -m "manage.sh pull $stamp" && info "Local edits stashed as 'manage.sh pull $stamp'"
  fi
  [[ "$(g rev-parse --abbrev-ref HEAD)" == "$branch" ]] || g checkout -q "$branch"
  g merge --ff-only -q "origin/$branch" \
    || die "Local commits diverge from origin/$branch. Resolve manually (git status / git log), then re-run." 1
  new="$(g rev-parse HEAD)"
  info "Updated $(g log -1 --format=%h "$old") -> $(g log -1 --format='%h %s' "$new")"
  g diff --stat "$old" "$new" | tail -n1 | sed 's/^/  /'
  g diff --quiet "$old" "$new" -- manage.sh || PULL_SELF_CHANGED=true
  if g diff --quiet "$old" "$new" -- backend frontend deploy shared docker-compose.yml; then
    info "No container changes; a rebuild is not required."
  else
    info "Container sources changed; run './manage.sh update' (or build + restart) to apply."
  fi
}

redeploy() {  # rebuild images and restart on the code that is checked out now
  compose pull db 2>/dev/null || true
  compose build --pull
  compose up -d
  cmd_migrate
  cmd_health || warn "Health check reported problems; previous backup is in $BACKUP_DIR"
  print_urls
}

cmd_update() {
  require_env
  confirm "Back up the database, pull the latest code from GitHub, rebuild and restart?" || exit 4
  cmd_backup
  cmd_pull
  # bash reads scripts lazily: if this file was replaced, continue in the new version.
  if $PULL_SELF_CHANGED; then info "manage.sh was updated; continuing with the new version"; exec bash "$ROOT/manage.sh" _redeploy -y; fi
  redeploy
}

# ----------------------------------------------------------------------------- 16
cmd_open() {
  print_urls
  wsl_hint
  local url; url="$(app_url)"
  wsl_nat && url="$(site_url)"  # in NAT mode the IP only works after the port proxy / mirrored mode
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
  echo; info "LAN address"; echo "  LAN_ADDRESS=$(env_get LAN_ADDRESS) -> $(lan_ip)   Web UI: $(app_url)   This PC: $(site_url)"
  is_wsl && echo "  WSL networking: $(wslinfo --networking-mode 2>/dev/null | tr -d '\r' || echo 'unknown (assume nat)')"
  echo; info "Services"; compose ps 2>/dev/null || true
  echo; info "Disk"; df -h "$ROOT" | tail -n1
  echo; info "Backups"; ls -1t "$BACKUP_DIR" 2>/dev/null | head -n5 || echo "  none"
  echo; info "Recent backend errors"; compose logs --tail=300 backend 2>/dev/null | grep -E '"level": "(ERROR|WARNING)"' | tail -n10 || true
}

# ----------------------------------------------------------------------------- 21
cmd_uninstall() {
  require_env
  cat <<EOF
Uninstall levels (source code, .env and backups/ are always kept):
  1) Remove containers and network        data kept; ./manage.sh start brings it back
  2) Also remove the application images   data kept; needs ./manage.sh build again
  3) Also DELETE ALL DATA                 database, certificates, Caddy state (backup taken first)
  4) Cancel
EOF
  local ch; if $ASSUME_YES; then ch="${UNINSTALL_LEVEL:-1}"; else read -r -p "Choice: " ch; fi
  case "$ch" in
    1) confirm "Stop and remove all Lalit Stock containers?" || exit 4
       compose down --remove-orphans ;;
    2) confirm "Stop and remove containers, network and the application images?" || exit 4
       compose down --remove-orphans --rmi all
       docker image rm lalitstock-backend-test >/dev/null 2>&1 || true ;;
    3) confirm_word "This permanently deletes the database (portfolios, transactions, devices, API keys) and all certificates." DELETE || exit 4
       if compose ps --status running --services 2>/dev/null | grep -qx db; then cmd_backup
       else warn "Database is not running; no final backup taken"; confirm "Continue without a backup?" || exit 4; fi
       compose down --remove-orphans --rmi all --volumes
       docker image rm lalitstock-backend-test >/dev/null 2>&1 || true ;;
    *) info "Cancelled"; exit 4 ;;
  esac
  info "Uninstalled (level $ch). Kept: source, .env, $BACKUP_DIR. To remove everything: delete this folder ($ROOT)."
}

# ----------------------------------------------------------------------------- 20
# ----------------------------------------------------------------------------- 23
cmd_firmware() {  # build every ESP32 variant (module x wiring x firmware/test) for the "Flash ESP32" page
  mkdir -p "$ROOT/firmware/dist" "$ROOT/firmware/.build"
  local mode="auto" args=()
  for a in "$@"; do case "$a" in --docker) mode=docker ;; --local) mode=local ;; *) args+=("$a") ;; esac; done
  if [[ "$mode" != docker ]] && command -v arduino-cli >/dev/null 2>&1; then
    info "Building with the local arduino-cli (JOBS=${JOBS:-2})"
    bash "$ROOT/tools/build_firmware.sh" "${args[@]+"${args[@]}"}"
  else
    [[ "$mode" == local ]] && die "arduino-cli is not installed; drop --local to use the Docker builder" 3
    command -v docker >/dev/null 2>&1 || die "Docker is required for the firmware builder. Run: ./manage.sh check" 3
    info "Building the firmware builder image (first time downloads the ESP32 toolchain, about 1 GB)"
    docker build -q -f "$ROOT/deploy/firmware-builder/Dockerfile" -t lalitstock-fwbuilder "$ROOT/deploy" >/dev/null
    info "Compiling all variants in the builder container (JOBS=${JOBS:-2}; a few minutes)"
    docker run --rm -v "$ROOT:/repo" -w /repo --user "$(id -u):$(id -g)" -e HOME=/tmp -e JOBS="${JOBS:-2}" \
      lalitstock-fwbuilder bash tools/build_firmware.sh "${args[@]+"${args[@]}"}"
  fi
  ok "Firmware ready in firmware/dist. Open the web admin -> Flash ESP32 (Chrome/Edge) to flash a board."
}

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
  restart          Restart services                      update       Back up, pull from GitHub, rebuild, restart
  pull             Pull latest code from GitHub (no rebuild; keeps .env, backups, logs)
  status           Service status                        open         Show/open web & API URLs
  logs [svc]       Follow logs                           test [backend|frontend|firmware|all]
  diag             Diagnostics (secrets redacted)        reset        Remove demo data / reset data (confirms)
  uninstall        Remove containers / images / data (levels, confirms)
  firmware [f]     Build ESP32 firmware files for the web flasher (Flash ESP32 page); f filters, e.g. 420_bwr
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
                                     21) Uninstall / remove application
                                     22) Pull latest code from GitHub (no rebuild)
                                     23) Build ESP32 firmware for the web flasher
  q) Quit
EOF
    local c; read -r -p "Select: " c || exit 0
    case "$c" in
      1) cmd_check || true ;; 2) cmd_env ;; 3) cmd_secrets ;; 4) cmd_build ;; 5) cmd_start ;; 6) cmd_stop ;;
      7) cmd_restart ;; 8) cmd_status ;; 9) cmd_logs || true ;; 10) cmd_health || true ;; 11) cmd_migrate ;;
      12) cmd_seed || true ;; 13) cmd_backup ;; 14) cmd_restore ;; 15) cmd_update ;; 16) cmd_open ;;
      17) cmd_test || true ;; 18) cmd_diag ;; 19) (cmd_reset) || true ;; 20) cmd_help; exit 0 ;; 21) (cmd_uninstall) || true ;; 22) (cmd_pull) || true ;; 23) (cmd_firmware) || true ;;
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
    migrate) cmd_migrate ;; seed) cmd_seed ;; backup) cmd_backup ;; restore) cmd_restore "$@" ;; update) cmd_update ;; pull) cmd_pull ;; _redeploy) redeploy ;;
    firmware|fw) cmd_firmware "$@" ;;
    open|urls) cmd_open ;; test) cmd_test "$@" ;; diag) cmd_diag ;; reset) cmd_reset ;; uninstall|remove) cmd_uninstall ;; help|-h|--help|about) cmd_help ;;
    *) cmd_help; exit 2 ;;
  esac
}

trap 'log ERROR "failed at line $LINENO: $BASH_COMMAND"' ERR
main "$@"
