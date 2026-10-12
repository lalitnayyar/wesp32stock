// Lalit Stock Application - ESP32 local administration page.
// Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973. Not financial advice. No warranty.
//
// Setup mode: protected WPA2 access point (password shown on the E-Paper), page at 192.168.4.1.
// Normal mode: http://<device-ip>/ protected with HTTP Basic auth (user "admin").
// Live page controls: Pause/Resume, Next page, Go to page N. Secrets are never sent back.
#include <WebServer.h>
#include <WiFi.h>
#include <esp_task_wdt.h>

#include "app_state.h"

static WebServer server(80);
static bool s_setup = false;
static uint32_t s_apStartedMs = 0;
static const uint32_t AP_TIMEOUT_MS = 15UL * 60UL * 1000UL;  // AP never stays up permanently

static const char PAGE[] PROGMEM = R"HTML(<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Lalit Stock E-Paper</title>
<style>body{font-family:system-ui,sans-serif;margin:0;background:#f4f4f2;color:#111}header{background:#b00;color:#fff;padding:10px 14px}
main{max-width:760px;margin:auto;padding:10px}section{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;margin:10px 0}
h2{font-size:16px;margin:0 0 8px}label{display:block;font-size:13px;margin:6px 0 2px}input,select{width:100%;padding:6px;box-sizing:border-box}
.row{display:grid;grid-template-columns:1fr 1fr;gap:8px}button{padding:8px 12px;margin:3px;border:0;border-radius:6px;background:#222;color:#fff;cursor:pointer}
button.alt{background:#666}button.warn{background:#b00}.kv{display:grid;grid-template-columns:170px 1fr;font-size:13px;gap:2px 8px}
.warn{color:#b00}.ok{color:#070}.box{background:#ffd;border:1px solid #cc0;padding:8px;border-radius:6px;font-size:13px}
#msg{position:sticky;top:0;background:#222;color:#fff;padding:6px 10px;display:none}footer{font-size:12px;color:#555;padding:10px;text-align:center}</style></head>
<body><header><b>Lalit Stock Application</b> &mdash; E-Paper device <span id="devid"></span> <span id="mode"></span></header><div id="msg"></div><main>
<section><h2>Page controls</h2>
<div class="kv"><span>Current page</span><b id="pg">-</b><span>Rotation</span><b id="rotst">-</b><span>Next automatic change</span><span id="nextc">-</span><span>Pending redraw</span><span id="pend">-</span></div>
<button id="bpause" onclick="ctl('pause')">Pause</button><button id="bresume" onclick="ctl('resume')">Resume</button>
<button onclick="ctl('next')">Next page</button>
<span style="display:inline-block;width:120px"><input id="gopage" type="number" min="1" placeholder="Page #"></span><button onclick="ctl('goto',document.getElementById('gopage').value)">Go to page</button>
<p style="font-size:12px">Manual changes are queued behind the panel refresh guard: a full refresh of this 4-colour panel takes about 21-25 s.</p></section>
<section><h2>Refresh safety</h2><div class="kv"><span>Requested page duration</span><b id="req">-</b>
<span>Effective hardware-safe duration</span><b id="eff">-</b><span>Panel profile</span><span id="prof">-</span></div><p id="reason" class="box"></p></section>
<section><h2>Status</h2><div class="kv" id="status"></div></section>
<section><h2>Settings</h2><form id="f" onsubmit="return save(event)">
<div class="row"><div><label>Device name</label><input name="device_name" maxlength="32"></div><div><label>Admin password (min 8; blank = keep)</label><input name="admin_pass" type="password" maxlength="64" autocomplete="new-password"></div></div>
<div class="row"><div><label>Wi-Fi SSID</label><input name="wifi_ssid" list="nets" maxlength="32"><datalist id="nets"></datalist></div><div><label>Wi-Fi password (blank = keep)</label><input name="wifi_pass" type="password" maxlength="64" autocomplete="new-password"></div></div>
<button type="button" class="alt" onclick="scan()">Scan networks</button><button type="button" class="alt" onclick="post('/api/test-wifi',fd())">Test Wi-Fi</button>
<label>Stock application API URL (https://...)</label><input name="api_url" maxlength="160" placeholder="https://stock.example.com">
<label>Device API key (blank = keep)</label><input name="api_key" type="password" maxlength="99" autocomplete="off">
<label>Custom root CA (PEM, optional; blank = keep, "-" = use built-in bundle)</label><input name="root_ca" type="password" autocomplete="off">
<button type="button" class="alt" onclick="post('/api/test-api',fd())">Test API</button>
<div class="row"><div><label>API fetch interval (s)</label><input name="fetch_interval_s" type="number"></div><div><label>API timeout (ms)</label><input name="api_timeout_ms" type="number"></div></div>
<div class="row"><div><label>Automatic page rotation</label><select name="rotation_enabled"><option value="1">On</option><option value="0">Off</option></select></div>
<div><label>Requested page duration (s, default 10)</label><input name="page_duration_s" type="number"></div></div>
<div class="row"><div><label>Rows per page</label><input name="rows_per_page" type="number"></div><div><label>Panel profile</label><select name="panel_profile"></select></div></div>
<div class="row"><div><label>Summary page</label><select name="show_summary_page"><option value="1">Show</option><option value="0">Hide</option></select></div>
<div><label>Benchmarks page</label><select name="show_benchmarks_page"><option value="1">Show</option><option value="0">Hide</option></select></div></div>
<div class="row"><div><label>Reset to page 1 on new data</label><select name="reset_page_on_data"><option value="0">No</option><option value="1">Yes</option></select></div>
<div><label>Heartbeat interval (s)</label><input name="heartbeat_interval_s" type="number"></div></div>
<div class="row"><div><label>Orientation</label><select name="orientation"><option>portrait</option></select></div><div><label>Timezone label</label><input name="timezone" maxlength="40"></div></div>
<div class="row"><div><label>POSIX TZ (Dubai: &lt;+04&gt;-4)</label><input name="posix_tz" maxlength="40"></div><div><label>NTP server</label><input name="ntp_server" maxlength="64"></div></div>
<button type="submit">Save</button><button type="button" class="alt" onclick="post('/api/restart',{})">Restart</button>
<button type="button" class="warn" onclick="if(prompt('Type RESET to erase all settings')==='RESET')post('/api/factory-reset',{confirm:'RESET'})">Factory reset</button></form></section>
</main><footer>Owner: Lalit Nayyar &middot; consult@lalit.cloud &middot; +971568391973<br>Not financial advice. Market data may be delayed or inaccurate. Provided without warranty.</footer>
<script>
const $=id=>document.getElementById(id);let cfgLoaded=false;
function show(t,bad){const m=$('msg');m.textContent=t;m.style.display='block';m.style.background=bad?'#b00':'#222';clearTimeout(m._t);m._t=setTimeout(()=>m.style.display='none',6000)}
async function post(u,data){const b=new URLSearchParams(data);const r=await fetch(u,{method:'POST',body:b});let j={};try{j=await r.json()}catch(e){}
show(j.message||(r.ok?'OK':'Error '+r.status),!r.ok);refresh();return j}
function fd(){const o={};new FormData($('f')).forEach((v,k)=>o[k]=v);return o}
function ctl(a,p){post('/api/control',p===undefined?{action:a}:{action:a,page:p})}
async function save(e){e.preventDefault();const j=await post('/api/config',fd());if(j.warnings&&Object.keys(j.warnings).length)show('Saved with corrections: '+Object.values(j.warnings).join('; '),true);loadCfg();return false}
async function scan(){show('Scanning...');const r=await fetch('/api/scan');const j=await r.json();$('nets').innerHTML=j.map(n=>`<option value="${n.ssid.replace(/"/g,'')}">${n.rssi} dBm</option>`).join('');show(j.length+' networks found')}
async function loadCfg(){const c=await (await fetch('/api/config')).json();const f=$('f');
$('f').panel_profile.innerHTML=c.panel_profiles.map(p=>`<option>${p}</option>`).join('');
for(const[k,v]of Object.entries(c.config)){if(f[k])f[k].value=typeof v==='boolean'?(v?'1':'0'):v}
for(const k of['wifi_pass','api_key','admin_pass','root_ca'])if(f[k]){f[k].value='';f[k].placeholder=c.secrets_set[k]?'(saved - leave blank to keep)':'(not set)'}cfgLoaded=true}
function kv(o){return Object.entries(o).map(([k,v])=>`<span>${k}</span><span>${v}</span>`).join('')}
async function refresh(){try{const s=await (await fetch('/api/status')).json();const r=s.rotation;
$('devid').textContent=s.device_id;$('mode').textContent=s.setup_mode?'(SETUP MODE)':'';
$('pg').textContent=`PAGE ${r.page}/${r.pages}`;$('rotst').innerHTML=r.enabled?'<span class=ok>Running</span>':'<span class=warn>Paused</span>';
$('bpause').disabled=!r.enabled;$('bresume').disabled=r.enabled;$('gopage').max=r.pages;
$('nextc').textContent=r.enabled&&r.pages>1?r.next_change_s+' s':'-';$('pend').textContent=r.drawing?'refreshing now':r.pending_draw?('in '+r.draw_in_s+' s'):'no';
$('req').textContent=r.requested_s+' s';$('eff').textContent=r.effective_s+' s'+(r.clamped?' (clamped)':'');
$('eff').className=r.clamped?'warn':'ok';$('prof').textContent=r.profile_label+(r.verified?' [verified]':' [unverified]');$('reason').textContent=r.reason;
$('status').innerHTML=kv({'Wi-Fi':s.wifi.connected?`${s.wifi.ssid} (${s.wifi.rssi} dBm, ${s.wifi.ip})`:'disconnected','API':s.api.state+(s.api.insecure_http?' (INSECURE HTTP)':''),
'Last error':s.api.last_error||'-','Data age':s.api.age_s<0?'-':s.api.age_s+' s'+(s.api.from_cache?' (cached)':''),'Data version':s.api.data_version||'-',
'Fetches (ok/total)':s.api.fetch_ok+'/'+s.api.fetch_count,'Display refreshes':s.display.refresh_count+' (last '+s.display.last_ms+' ms, busy timeouts '+s.display.busy_timeouts+')',
'Time sync (NTP)':s.ntp_ok?s.time:'not synced','Firmware':s.firmware,'Uptime':s.uptime_s+' s','Free heap':s.free_heap+' bytes'});
if(!cfgLoaded)loadCfg()}catch(e){}}
refresh();setInterval(refresh,3000);
</script></body></html>)HTML";

static bool authed() {
  if (g_cfg.admin_pass[0]) {
    if (!server.authenticate("admin", g_cfg.admin_pass)) {
      server.requestAuthentication(BASIC_AUTH, "LalitStock");
      return false;
    }
    return true;
  }
  if (s_setup) return true;  // first boot only: the setup AP itself is WPA2-protected
  server.send(403, "application/json", "{\"message\":\"admin password not set\"}");
  return false;
}

static void sendJson(int code, JsonDocument& d) {
  String out;
  serializeJson(d, out);
  server.sendHeader("Cache-Control", "no-store");
  server.send(code, "application/json", out);
}

static void sendMsg(int code, const String& msg) {
  JsonDocument d;
  d["message"] = msg;
  sendJson(code, d);
}

static void handleRoot() {
  if (!authed()) return;
  server.sendHeader("Cache-Control", "no-store");
  server.send_P(200, "text/html", PAGE);
}

static void handleStatus() {
  if (!authed()) return;
  uint32_t now = millis();
  JsonDocument d;
  d["device_id"] = g_deviceId;
  d["name"] = g_cfg.device_name;
  d["firmware"] = FW_VERSION;
  d["setup_mode"] = s_setup;
  d["uptime_s"] = now / 1000;
  d["free_heap"] = ESP.getFreeHeap();
  d["ntp_ok"] = epdTimeValid();
  if (epdTimeValid()) {
    time_t t = time(nullptr);
    struct tm tmv;
    localtime_r(&t, &tmv);
    char buf[32];
    strftime(buf, sizeof buf, "%Y-%m-%d %H:%M:%S", &tmv);
    d["time"] = buf;
  }
  JsonObject w = d["wifi"].to<JsonObject>();
  w["connected"] = WiFi.status() == WL_CONNECTED;
  w["ssid"] = g_cfg.wifi_ssid;
  w["rssi"] = WiFi.RSSI();
  w["ip"] = WiFi.localIP().toString();
  JsonObject a = d["api"].to<JsonObject>();
  {
    Lock l;
    a["state"] = g_net.api == ApiState::OK ? "OK" : g_net.api == ApiState::ERR ? "ERR" : "OFF";
    a["last_error"] = g_net.lastError;
    a["fetch_count"] = g_net.fetchCount;
    a["fetch_ok"] = g_net.fetchOk;
    a["heartbeat_ok"] = g_net.heartbeatOk;
    a["data_version"] = g_net.dataVersion;
    a["from_cache"] = g_net.fromCache;
    a["age_s"] = g_net.okSinceBoot ? (long)((now - g_net.lastOkMs) / 1000u) : -1L;
  }
  a["insecure_http"] = strncmp(g_cfg.api_url, "http://", 7) == 0;
  JsonObject r = d["rotation"].to<JsonObject>();
  const ls::RefreshResult& rr = g_ui.refresh;
  r["enabled"] = g_ui.rot.enabled;
  r["page"] = g_ui.rot.page;
  r["pages"] = g_ui.rot.count;
  r["requested_s"] = rr.requested_s;
  r["effective_s"] = rr.effective_s;
  r["min_safe_s"] = rr.min_safe_s;
  r["refresh_gap_s"] = rr.refresh_gap_s;
  r["clamped"] = rr.clamped;
  r["fallback"] = rr.fallback;
  r["verified"] = rr.verified;
  r["profile"] = g_cfg.panel_profile;
  r["profile_label"] = rr.profile ? rr.profile->label : "Unknown panel/driver";
  char reason[220];
  ls::refreshReason(rr, reason, sizeof reason);
  r["reason"] = reason;
  r["next_change_s"] = (g_ui.rot.msUntilNext(now) + 999) / 1000;
  r["pending_draw"] = g_ui.pendingDraw;
  r["draw_in_s"] = (g_ui.gate.msUntilAllowed(now) + 999) / 1000;
  r["drawing"] = g_ui.drawing;
  JsonObject disp = d["display"].to<JsonObject>();
  disp["refresh_count"] = g_ui.refreshCount;
  disp["last_ms"] = g_ui.lastRefreshMs;
  disp["busy_timeouts"] = g_ui.busyTimeouts;
  sendJson(200, d);
}

static String queuedNote() {
  uint32_t wait = g_ui.gate.msUntilAllowed(millis());
  if (g_ui.drawing) return " (panel is refreshing; will apply after the current refresh)";
  if (wait) return String(" (queued: panel refresh guard, applies in ") + ((wait + 999) / 1000) + " s)";
  return "";
}

static void handleControl() {
  if (!authed()) return;
  String action = server.arg("action");
  uint32_t now = millis();
  if (action == "pause") {
    g_ui.rot.pause();
    g_cfg.rotation_enabled = false;
    configSaveRuntime(false, g_ui.rot.page);
    sendMsg(200, "Rotation paused on page " + String(g_ui.rot.page));
  } else if (action == "resume") {
    g_ui.rot.resume(now);
    g_cfg.rotation_enabled = true;
    configSaveRuntime(true, g_ui.rot.page);
    sendMsg(200, "Rotation resumed; next change in " + String(g_ui.refresh.effective_s) + " s");
  } else if (action == "next") {
    if (g_ui.rot.next(now)) g_ui.pendingDraw = true;
    configSaveRuntime(g_ui.rot.enabled, g_ui.rot.page);
    sendMsg(200, "Showing page " + String(g_ui.rot.page) + "/" + String(g_ui.rot.count) + queuedNote());
  } else if (action == "goto") {
    ls::IntCheck c = ls::validateIntStr(server.arg("page").c_str(), 1, g_ui.rot.count, 0);
    bool err = !c.ok;
    if (!err && g_ui.rot.gotoPage(c.value, now, &err)) g_ui.pendingDraw = true;
    if (err) {
      sendMsg(400, "Page must be a whole number between 1 and " + String(g_ui.rot.count));
      return;
    }
    configSaveRuntime(g_ui.rot.enabled, g_ui.rot.page);
    sendMsg(200, "Showing page " + String(g_ui.rot.page) + "/" + String(g_ui.rot.count) + queuedNote());
  } else {
    sendMsg(400, "Unknown action");
  }
}

static void handleGetConfig() {
  if (!authed()) return;
  JsonDocument d;
  JsonObject c = d["config"].to<JsonObject>();
  c["device_name"] = g_cfg.device_name;
  c["wifi_ssid"] = g_cfg.wifi_ssid;
  c["api_url"] = g_cfg.api_url;
  c["rotation_enabled"] = g_cfg.rotation_enabled;
  c["page_duration_s"] = g_cfg.page_duration_s;
  c["selected_page"] = g_ui.rot.page;
  c["reset_page_on_data"] = g_cfg.reset_page_on_data;
  c["fetch_interval_s"] = g_cfg.fetch_interval_s;
  c["heartbeat_interval_s"] = g_cfg.heartbeat_interval_s;
  c["api_timeout_ms"] = g_cfg.api_timeout_ms;
  c["rows_per_page"] = g_cfg.rows_per_page;
  c["show_summary_page"] = g_cfg.show_summary_page;
  c["show_benchmarks_page"] = g_cfg.show_benchmarks_page;
  c["orientation"] = "portrait";
  c["panel_profile"] = g_cfg.panel_profile;
  c["timezone"] = g_cfg.timezone;
  c["posix_tz"] = g_cfg.posix_tz;
  c["ntp_server"] = g_cfg.ntp_server;
  JsonObject s = d["secrets_set"].to<JsonObject>();  // never the secret values themselves
  s["wifi_pass"] = g_cfg.wifi_pass[0] != 0;
  s["api_key"] = g_cfg.api_key[0] != 0;
  s["admin_pass"] = g_cfg.admin_pass[0] != 0;
  s["root_ca"] = g_cfg.root_ca.length() > 0;
  JsonArray p = d["panel_profiles"].to<JsonArray>();
  for (int i = 0; i < PANEL_PROFILE_COUNT; i++)
    if (!PANEL_PROFILES[i].simulation_only) p.add(PANEL_PROFILES[i].name);
  p.add("UNKNOWN");
  sendJson(200, d);
}

static void setStr(const char* name, char* dst, size_t n, bool keepIfBlank, JsonObject warn) {
  if (!server.hasArg(name)) return;
  String v = server.arg(name);
  v.trim();
  if (keepIfBlank && v.length() == 0) return;
  if (v.length() >= n) {
    warn[name] = "too long; not changed";
    return;
  }
  strlcpy(dst, v.c_str(), n);
}

static void setInt(const char* name, int32_t& dst, long mn, long mx, long def, JsonObject warn) {
  if (!server.hasArg(name)) return;
  ls::IntCheck c = ls::validateIntStr(server.arg(name).c_str(), mn, mx, def);
  if (!c.ok) warn[name] = String("invalid value '") + server.arg(name) + "'; using " + c.value;
  dst = (int32_t)c.value;
}

static void setBool(const char* name, bool& dst) {
  if (server.hasArg(name)) dst = server.arg(name) == "1" || server.arg(name) == "true";
}

static void handlePostConfig() {
  if (!authed()) return;
  JsonDocument d;
  JsonObject warn = d["warnings"].to<JsonObject>();
  DeviceConfig before = g_cfg;
  setStr("device_name", g_cfg.device_name, sizeof g_cfg.device_name, false, warn);
  setStr("wifi_ssid", g_cfg.wifi_ssid, sizeof g_cfg.wifi_ssid, false, warn);
  setStr("wifi_pass", g_cfg.wifi_pass, sizeof g_cfg.wifi_pass, true, warn);
  setStr("api_url", g_cfg.api_url, sizeof g_cfg.api_url, false, warn);
  setStr("api_key", g_cfg.api_key, sizeof g_cfg.api_key, true, warn);
  if (server.hasArg("admin_pass") && server.arg("admin_pass").length()) {
    if (server.arg("admin_pass").length() < 8) warn["admin_pass"] = "must be at least 8 characters; not changed";
    else setStr("admin_pass", g_cfg.admin_pass, sizeof g_cfg.admin_pass, true, warn);
  }
  if (server.hasArg("root_ca") && server.arg("root_ca").length()) {
    String ca = server.arg("root_ca");
    if (ca == "-") g_cfg.root_ca = "";
    else if (ca.indexOf("BEGIN CERTIFICATE") >= 0 && ca.length() < 3800) g_cfg.root_ca = ca;
    else warn["root_ca"] = "not a PEM certificate (or too long); not changed";
  }
  setBool("rotation_enabled", g_cfg.rotation_enabled);
  setInt("page_duration_s", g_cfg.page_duration_s, CFG_PAGE_DURATION_S_MIN, CFG_PAGE_DURATION_S_MAX, CFG_PAGE_DURATION_S_DEFAULT, warn);
  setInt("fetch_interval_s", g_cfg.fetch_interval_s, CFG_FETCH_INTERVAL_S_MIN, CFG_FETCH_INTERVAL_S_MAX, CFG_FETCH_INTERVAL_S_DEFAULT, warn);
  setInt("heartbeat_interval_s", g_cfg.heartbeat_interval_s, CFG_HEARTBEAT_INTERVAL_S_MIN, CFG_HEARTBEAT_INTERVAL_S_MAX, CFG_HEARTBEAT_INTERVAL_S_DEFAULT, warn);
  setInt("api_timeout_ms", g_cfg.api_timeout_ms, CFG_API_TIMEOUT_MS_MIN, CFG_API_TIMEOUT_MS_MAX, CFG_API_TIMEOUT_MS_DEFAULT, warn);
  setInt("rows_per_page", g_cfg.rows_per_page, CFG_ROWS_PER_PAGE_MIN, CFG_ROWS_PER_PAGE_MAX, CFG_ROWS_PER_PAGE_DEFAULT, warn);
  setBool("show_summary_page", g_cfg.show_summary_page);
  setBool("show_benchmarks_page", g_cfg.show_benchmarks_page);
  setBool("reset_page_on_data", g_cfg.reset_page_on_data);
  if (server.hasArg("panel_profile")) {
    String p = server.arg("panel_profile");
    const PanelProfile* prof = ls::findProfile(p.c_str());
    if ((prof && !prof->simulation_only) || p == "UNKNOWN") strlcpy(g_cfg.panel_profile, p.c_str(), sizeof g_cfg.panel_profile);
    else warn["panel_profile"] = "unsupported or simulation-only profile; not changed";
  }
  if (server.hasArg("orientation") && server.arg("orientation") != "portrait") warn["orientation"] = "only portrait is supported";
  setStr("timezone", g_cfg.timezone, sizeof g_cfg.timezone, false, warn);
  setStr("posix_tz", g_cfg.posix_tz, sizeof g_cfg.posix_tz, false, warn);
  setStr("ntp_server", g_cfg.ntp_server, sizeof g_cfg.ntp_server, false, warn);
  if (g_cfg.api_url[0] && strncmp(g_cfg.api_url, "https://", 8) != 0 && strncmp(g_cfg.api_url, "http://", 7) != 0) {
    warn["api_url"] = "must start with https:// (or http:// for LAN testing); not changed";
    strlcpy(g_cfg.api_url, before.api_url, sizeof g_cfg.api_url);
  }
  configSave(g_cfg);
  // apply immediately where safe
  applyRefreshPolicy();
  if (g_cfg.rotation_enabled != g_ui.rot.enabled) {
    if (g_cfg.rotation_enabled) g_ui.rot.resume(millis());
    else g_ui.rot.pause();
  }
  bool restart = strcmp(before.wifi_ssid, g_cfg.wifi_ssid) || strcmp(before.wifi_pass, g_cfg.wifi_pass) ||
                 strcmp(before.posix_tz, g_cfg.posix_tz) || strcmp(before.ntp_server, g_cfg.ntp_server) ||
                 (s_setup && configProvisioned(g_cfg));
  bool refetch = strcmp(before.api_url, g_cfg.api_url) || strcmp(before.api_key, g_cfg.api_key) ||
                 before.rows_per_page != g_cfg.rows_per_page || before.show_summary_page != g_cfg.show_summary_page ||
                 before.show_benchmarks_page != g_cfg.show_benchmarks_page;
  if (refetch && !s_setup) netRequestFetch();
  d["needs_restart"] = restart;
  d["message"] = restart ? "Saved. Restart to apply network settings." : "Saved and applied.";
  d["effective_s"] = g_ui.refresh.effective_s;
  sendJson(200, d);
}

static void handleScan() {
  if (!authed()) return;
  int n = WiFi.scanNetworks();
  JsonDocument d;
  JsonArray a = d.to<JsonArray>();
  for (int i = 0; i < n && i < 20; i++) {
    JsonObject o = a.add<JsonObject>();
    o["ssid"] = WiFi.SSID(i);
    o["rssi"] = WiFi.RSSI(i);
    o["secure"] = WiFi.encryptionType(i) != WIFI_AUTH_OPEN;
  }
  WiFi.scanDelete();
  sendJson(200, d);
}

static void handleTestWifi() {
  if (!authed()) return;
  if (!s_setup) {
    if (WiFi.status() == WL_CONNECTED)
      sendMsg(200, "Connected to " + WiFi.SSID() + " (" + WiFi.RSSI() + " dBm), IP " + WiFi.localIP().toString());
    else sendMsg(503, "Wi-Fi not connected");
    return;
  }
  String ssid = server.arg("wifi_ssid");
  String pass = server.arg("wifi_pass").length() ? server.arg("wifi_pass") : String(g_cfg.wifi_pass);
  if (!ssid.length()) {
    sendMsg(400, "Enter an SSID first");
    return;
  }
  WiFi.mode(WIFI_AP_STA);
  WiFi.begin(ssid.c_str(), pass.c_str());
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(250);
    esp_task_wdt_reset();
  }
  if (WiFi.status() == WL_CONNECTED) sendMsg(200, "Wi-Fi OK: IP " + WiFi.localIP().toString() + ", " + WiFi.RSSI() + " dBm");
  else sendMsg(502, "Could not connect to '" + ssid + "' (check password / 2.4 GHz)");
}

static void handleTestApi() {
  if (!authed()) return;
  DeviceConfig saved = g_cfg;
  if (s_setup) {  // test the values typed into the form without saving them
    if (server.arg("api_url").length()) strlcpy(g_cfg.api_url, server.arg("api_url").c_str(), sizeof g_cfg.api_url);
    if (server.arg("api_key").length()) strlcpy(g_cfg.api_key, server.arg("api_key").c_str(), sizeof g_cfg.api_key);
  }
  char msg[96];
  bool ok = netTestApi(msg, sizeof msg);
  if (s_setup) g_cfg = saved;
  sendMsg(ok ? 200 : 502, String(ok ? "API OK: " : "API test failed: ") + msg);
}

static void handleRestart() {
  if (!authed()) return;
  sendMsg(200, "Restarting...");
  delay(500);
  ESP.restart();
}

static void handleFactoryReset() {
  if (!authed()) return;
  if (server.arg("confirm") != "RESET") {
    sendMsg(400, "Confirmation required");
    return;
  }
  configFactoryReset();
  sendMsg(200, "All settings erased. Restarting into setup mode...");
  delay(500);
  ESP.restart();
}

void webStart(bool setupMode) {
  s_setup = setupMode;
  if (setupMode) {
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(g_ui.setupSsid, g_ui.setupPass);
    s_apStartedMs = millis();
    Serial.printf("[web] setup AP '%s' password '%s' at %s\n", g_ui.setupSsid, g_ui.setupPass,
                  WiFi.softAPIP().toString().c_str());
  }
  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/status", HTTP_GET, handleStatus);
  server.on("/api/control", HTTP_POST, handleControl);
  server.on("/api/config", HTTP_GET, handleGetConfig);
  server.on("/api/config", HTTP_POST, handlePostConfig);
  server.on("/api/scan", HTTP_GET, handleScan);
  server.on("/api/test-wifi", HTTP_POST, handleTestWifi);
  server.on("/api/test-api", HTTP_POST, handleTestApi);
  server.on("/api/restart", HTTP_POST, handleRestart);
  server.on("/api/factory-reset", HTTP_POST, handleFactoryReset);
  server.onNotFound([]() { server.send(404, "text/plain", "Not found"); });
  server.begin();
}

void webLoop() {
  server.handleClient();
  // The setup AP shuts itself down after 15 minutes if the device is already provisioned.
  if (s_setup && configProvisioned(g_cfg) && millis() - s_apStartedMs > AP_TIMEOUT_MS) {
    Serial.println("[web] setup AP timeout; restarting into normal mode");
    ESP.restart();
  }
}
