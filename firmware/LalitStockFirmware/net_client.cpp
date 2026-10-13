// Lalit Stock Application - network task: Wi-Fi, authenticated dashboard fetch, heartbeat, NTP, cache.
// Owner: Lalit Nayyar <consult@lalit.cloud>. Not financial advice. No warranty.
//
// Runs on its own FreeRTOS task so a slow/blocked request never freezes page rotation.
// TLS: https URLs are always verified (custom root CA if configured, otherwise the built-in CA
// bundle). Certificate verification is never disabled.
#include <HTTPClient.h>
#include <LittleFS.h>
#include <NetworkClientSecure.h>
#include <WiFi.h>
#include <esp_sntp.h>
#include <esp_task_wdt.h>
#include <time.h>

#include "app_state.h"

static volatile bool s_fetchReq = true;
static volatile bool s_hbReq = false;
static SemaphoreHandle_t s_httpMutex;
static const char* CACHE_PATH = "/dash.json";

void netRequestFetch() { s_fetchReq = true; }
void netRequestHeartbeat() { s_hbReq = true; }

static void setError(const char* fmt, ...) {
  char buf[96];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof buf, fmt, ap);
  va_end(ap);
  Lock l;
  strlcpy(g_net.lastError, buf, sizeof g_net.lastError);
}

// "2026-10-12T10:05:00Z" -> epoch (UTC). Returns 0 on failure.
static time_t parseIsoUtc(const char* s) {
  int Y, M, D, h, m, sec;
  if (!s || sscanf(s, "%4d-%2d-%2dT%2d:%2d:%2d", &Y, &M, &D, &h, &m, &sec) != 6) return 0;
  Y -= M <= 2;
  long era = (Y >= 0 ? Y : Y - 399) / 400;
  unsigned yoe = (unsigned)(Y - era * 400);
  unsigned doy = (153 * (M + (M > 2 ? -3 : 9)) + 2) / 5 + D - 1;
  unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  long days = era * 146097 + (long)doe - 719468;
  return (time_t)(days * 86400L + h * 3600L + m * 60L + sec);
}

// Structural validation so a malformed/hostile response can never crash the renderer.
static bool validDashboard(JsonDocument& d, char* why, size_t n) {
  if ((d["v"] | 0) != 1) { strlcpy(why, "unsupported contract version", n); return false; }
  // Pages are laid out for one panel size; reject another layout (e.g. an old cache after reflashing).
  // Servers before 1.1 send no layout and only the 168x384 one.
  if (strcmp(d["layout"] | "168x384", L_ID) != 0) { strlcpy(why, "layout is not " L_ID, n); return false; }
  JsonArray pages = d["pages"];
  if (pages.isNull() || pages.size() < 1 || pages.size() > L_LIM_MAX_PAGES) { strlcpy(why, "bad page count", n); return false; }
  for (JsonObject p : pages) {
    JsonArray ops = p["ops"];
    if (ops.isNull() || ops.size() > L_LIM_MAX_OPS_PER_PAGE) { strlcpy(why, "bad ops", n); return false; }
    for (JsonArray op : ops) {
      const char* k = op[0] | "";
      if (!(k[0] == 'T' || k[0] == 'F' || k[0] == 'R' || k[0] == 'H') || k[1]) { strlcpy(why, "unknown op", n); return false; }
    }
  }
  if (!d["data_version"].is<const char*>()) { strlcpy(why, "missing data_version", n); return false; }
  return true;
}

static bool beginRequest(HTTPClient& http, NetworkClient*& client, const String& url) {
  if (url.startsWith("https://")) {
    auto* sc = new NetworkClientSecure();
    if (g_cfg.root_ca.length()) sc->setCACert(g_cfg.root_ca.c_str());
    else sc->useBuiltinCACertBundle();
    sc->setHandshakeTimeout((g_cfg.api_timeout_ms + 999) / 1000);
    client = sc;
  } else if (url.startsWith("http://")) {
    client = new NetworkClient();  // plain HTTP: LAN/development only, labelled INSECURE in the admin page
  } else {
    setError("API URL must start with https:// or http://");
    return false;
  }
  http.setConnectTimeout(g_cfg.api_timeout_ms);
  http.setTimeout(g_cfg.api_timeout_ms);
  http.setReuse(false);
  if (!http.begin(*client, url)) {
    setError("invalid API URL");
    return false;
  }
  http.addHeader("Authorization", String("Bearer ") + g_cfg.api_key);
  http.addHeader("Accept", "application/json");
  http.setUserAgent("LalitStock-ESP32/" FW_VERSION);
  return true;
}

static String baseUrl() {
  String u = g_cfg.api_url;
  while (u.endsWith("/")) u.remove(u.length() - 1);
  return u;
}

// Performs one dashboard fetch. Returns true on success (200 or 304).
static bool doFetch(char* msg, size_t msgLen) {
  xSemaphoreTake(s_httpMutex, portMAX_DELAY);
  char since[16];
  {
    Lock l;
    g_net.fetchCount++;
    g_net.lastAttemptMs = millis();
    strlcpy(since, g_net.hasData && !g_net.fromCache ? g_net.dataVersion : "", sizeof since);
  }
  String url = baseUrl() + "/api/v1/device/dashboard?rows=" + g_cfg.rows_per_page +
               "&summary=" + (g_cfg.show_summary_page ? "true" : "false") +
               "&bench=" + (g_cfg.show_benchmarks_page ? "true" : "false") + "&panel=" LS_PANEL_PROFILE;
  if (since[0]) url += String("&since=") + since;

  HTTPClient http;
  NetworkClient* client = nullptr;
  bool ok = false;
  ApiState state = ApiState::ERR;
  if (beginRequest(http, client, url)) {
    esp_task_wdt_reset();
    int code = http.GET();
    esp_task_wdt_reset();
    if (code == 304) {
      ok = true;
      snprintf(msg, msgLen, "OK (unchanged, version %s)", since);
    } else if (code == 200) {
      int size = http.getSize();
      if (size > L_LIM_MAX_RESPONSE_BYTES) {
        snprintf(msg, msgLen, "response too large (%d bytes)", size);
      } else {
        String body = http.getString();
        if ((int)body.length() > L_LIM_MAX_RESPONSE_BYTES) {
          snprintf(msg, msgLen, "response too large");
        } else {
          auto* doc = new JsonDocument();
          DeserializationError e = deserializeJson(*doc, body);
          char why[48] = "";
          if (e) {
            snprintf(msg, msgLen, "invalid JSON: %s", e.c_str());
            delete doc;
          } else if (!validDashboard(*doc, why, sizeof why)) {
            snprintf(msg, msgLen, "invalid response: %s", why);
            delete doc;
          } else {
            ok = true;
            snprintf(msg, msgLen, "OK (%u pages, version %s)", (unsigned)(*doc)["pages"].size(),
                     (const char*)((*doc)["data_version"] | ""));
            time_t gen = parseIsoUtc((*doc)["generated_at"] | "");
            {
              Lock l;
              if (g_net.pending) delete g_net.pending;
              g_net.pending = doc;
              strlcpy(g_net.dataVersion, (*doc)["data_version"] | "", sizeof g_net.dataVersion);
              g_net.dataGeneratedEpoch = gen;
              g_net.hasData = true;
              g_net.fromCache = false;
            }
            File f = LittleFS.open(CACHE_PATH, "w");
            if (f) {
              f.print(body);
              f.close();
            }
          }
        }
      }
    } else if (code == 401 || code == 403) {
      snprintf(msg, msgLen, "HTTP %d: API key rejected (check key, scope, device binding)", code);
    } else if (code < 0) {
      state = ApiState::OFF;
      snprintf(msg, msgLen, "connection failed: %s", HTTPClient::errorToString(code).c_str());
    } else {
      snprintf(msg, msgLen, "HTTP %d", code);
    }
    http.end();
  }
  delete client;
  {
    Lock l;
    if (ok) {
      g_net.api = ApiState::OK;
      g_net.fetchOk++;
      g_net.okSinceBoot = true;
      g_net.lastOkMs = millis();
      g_net.lastOkEpoch = epdTimeValid() ? time(nullptr) : 0;
      g_net.lastError[0] = '\0';
    } else {
      g_net.api = state;
      strlcpy(g_net.lastError, msg, sizeof g_net.lastError);
    }
  }
  xSemaphoreGive(s_httpMutex);
  Serial.printf("[net] fetch: %s\n", msg);
  return ok;
}

static void doHeartbeat() {
  JsonDocument d;
  {
    Lock l;
    d["firmware"] = FW_VERSION;
    d["rssi"] = constrain(g_net.rssi, -127, 0);
    d["uptime_s"] = millis() / 1000;
    d["api_status"] = g_net.api == ApiState::OK ? "OK" : g_net.api == ApiState::ERR ? "ERR" : "OFF";
    d["data_version"] = g_net.dataVersion;
    d["fetch_count"] = g_net.fetchCount;
    d["last_error"] = g_net.lastError;
  }
  d["page"] = g_ui.rot.page;
  d["pages"] = g_ui.rot.count;
  d["rotation_enabled"] = g_ui.rot.enabled;
  d["requested_s"] = g_ui.refresh.requested_s;
  d["effective_s"] = g_ui.refresh.effective_s;
  d["panel_profile"] = g_cfg.panel_profile;
  d["free_heap"] = ESP.getFreeHeap();
  d["refresh_count"] = g_ui.refreshCount;
  d["ntp_ok"] = epdTimeValid();
  String body;
  serializeJson(d, body);

  xSemaphoreTake(s_httpMutex, portMAX_DELAY);
  HTTPClient http;
  NetworkClient* client = nullptr;
  if (beginRequest(http, client, baseUrl() + "/api/v1/device/heartbeat")) {
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(body);
    if (code == 200) {
      Lock l;
      g_net.heartbeatOk++;
    } else {
      Serial.printf("[net] heartbeat HTTP %d\n", code);
    }
    http.end();
  }
  delete client;
  xSemaphoreGive(s_httpMutex);
}

bool netTestApi(char* msg, size_t n) {
  if (WiFi.status() != WL_CONNECTED) {
    strlcpy(msg, "Wi-Fi not connected", n);
    return false;
  }
  return doFetch(msg, n);
}

bool netLoadCache() {
  File f = LittleFS.open(CACHE_PATH, "r");
  if (!f) return false;
  if (f.size() > L_LIM_MAX_RESPONSE_BYTES) {
    f.close();
    return false;
  }
  auto* doc = new JsonDocument();
  DeserializationError e = deserializeJson(*doc, f);
  f.close();
  char why[48];
  if (e || !validDashboard(*doc, why, sizeof why)) {
    delete doc;
    LittleFS.remove(CACHE_PATH);
    return false;
  }
  Lock l;
  g_net.pending = doc;
  g_net.hasData = true;
  g_net.fromCache = true;
  strlcpy(g_net.dataVersion, (*doc)["data_version"] | "", sizeof g_net.dataVersion);
  g_net.dataGeneratedEpoch = parseIsoUtc((*doc)["generated_at"] | "");
  return true;
}

static void ensureWifi() {
  static uint32_t lastBegin = 0;
  static bool timeConfigured = false;
  bool up = WiFi.status() == WL_CONNECTED;
  if (!up && (lastBegin == 0 || millis() - lastBegin > 20000)) {
    lastBegin = millis();
    WiFi.mode(WIFI_STA);
    WiFi.setHostname(g_deviceId.c_str());
    WiFi.begin(g_cfg.wifi_ssid, g_cfg.wifi_pass);
    Serial.printf("[net] connecting to Wi-Fi '%s'\n", g_cfg.wifi_ssid);
  }
  if (up && !timeConfigured) {
    sntp_set_sync_interval((uint32_t)g_cfg.ntp_interval_s * 1000u);
    configTzTime(g_cfg.posix_tz, g_cfg.ntp_server, "time.google.com");
    timeConfigured = true;
  }
  Lock l;
  g_net.wifi = up;
  g_net.rssi = up ? WiFi.RSSI() : 0;
  if (!up) g_net.api = ApiState::OFF;
}

static void netTask(void*) {
  esp_task_wdt_add(nullptr);
  uint32_t lastFetch = 0, lastHb = 0, failures = 0;
  bool fetchedOnce = false;
  char msg[96];
  for (;;) {
    esp_task_wdt_reset();
    ensureWifi();
    uint32_t now = millis();
    bool wifi = WiFi.status() == WL_CONNECTED;
    uint32_t interval = (uint32_t)g_cfg.fetch_interval_s * 1000u;
    if (failures) {  // retry failed fetches sooner with exponential backoff, never faster than 30 s
      uint32_t backoff = 30000u << (failures > 5 ? 5 : failures - 1);
      if (backoff < interval) interval = backoff;
    }
    if (wifi && (s_fetchReq || !fetchedOnce || now - lastFetch >= interval)) {
      s_fetchReq = false;
      fetchedOnce = true;
      lastFetch = now;
      failures = doFetch(msg, sizeof msg) ? 0 : failures + 1;
    }
    if (wifi && (s_hbReq || now - lastHb >= (uint32_t)g_cfg.heartbeat_interval_s * 1000u)) {
      s_hbReq = false;
      lastHb = now;
      doHeartbeat();
    }
    g_ui.ntpOk = epdTimeValid();
    vTaskDelay(pdMS_TO_TICKS(250));
  }
}

void netStart() {
  s_httpMutex = xSemaphoreCreateMutex();
  xTaskCreatePinnedToCore(netTask, "net", 12288, nullptr, 1, nullptr, 0);
}
