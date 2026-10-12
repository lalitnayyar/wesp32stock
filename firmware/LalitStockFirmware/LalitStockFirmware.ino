// Lalit Stock Application - ESP32 E-Paper client firmware
// Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973
// Hardware: ESP32-WROOM-32 (ESP32 Dev Module) + WeAct Studio 2.9" 4-colour E-Paper
//           (168x384, panel GDEY029F51H, controller JD79667, GxEPD2_290c_GDEY029F51H).
// Disclaimer: informational display only - NOT financial advice. Market data may be delayed,
// incomplete or inaccurate. Provided without warranty of any kind.
//
// Independent schedules (all millis()-rollover safe):
//   * page rotation / redraw  - this loop (effective hardware-safe interval, see logic.h)
//   * API fetch + heartbeat   - network task on core 0 (net_client.cpp)
//   * NTP                     - SNTP background sync (ntp_interval_s)
// A page change never triggers a fetch and a slow fetch never blocks rotation.
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_random.h>
#include <esp_task_wdt.h>

#include "app_state.h"

DeviceConfig g_cfg;
NetState g_net;
UiState g_ui;
SemaphoreHandle_t g_mutex;
JsonDocument* g_dash = nullptr;
String g_deviceId;

static const uint32_t WDT_TIMEOUT_MS = 60000;  // > worst-case 50 s GxEPD2 BUSY wait; fed in busy callback
static ApiState s_drawnApi = ApiState::OFF;
static bool s_drawnOnce = false;

static void initWatchdog() {
  esp_task_wdt_config_t c = {};
  c.timeout_ms = WDT_TIMEOUT_MS;
  c.idle_core_mask = 0;
  c.trigger_panic = true;
  if (esp_task_wdt_reconfigure(&c) != ESP_OK) esp_task_wdt_init(&c);
  esp_task_wdt_add(nullptr);
}

static void makeIdentity() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char id[16];
  snprintf(id, sizeof id, "LS-%02X%02X%02X", mac[3], mac[4], mac[5]);
  g_deviceId = id;
  snprintf(g_ui.setupSsid, sizeof g_ui.setupSsid, "LalitStock-Setup-%02X%02X", mac[4], mac[5]);
  const char* alphabet = "abcdefghjkmnpqrstuvwxyz23456789";  // no look-alike characters
  for (int i = 0; i < 12; i++) g_ui.setupPass[i] = alphabet[esp_random() % 31];
  g_ui.setupPass[12] = '\0';
}

static bool consumeForceSetupFlag() {
  Preferences p;
  p.begin("lsboot", false);
  bool f = p.getBool("setup", false);
  if (f) p.remove("setup");
  p.end();
  return f;
}

static void requestSetupOnNextBoot() {
  Preferences p;
  p.begin("lsboot", false);
  p.putBool("setup", true);
  p.end();
}

static void showSetupScreen() {
  char l1[40], l2[40], l3[40];
  snprintf(l1, sizeof l1, "%s", g_ui.setupSsid);
  snprintf(l2, sizeof l2, "%s", g_ui.setupPass);
  snprintf(l3, sizeof l3, "Device: %s", g_deviceId.c_str());
  const char* lines[] = {"Join this Wi-Fi network:", l1, "", "Wi-Fi password:", l2, "", "Then open in a browser:",
                         "http://192.168.4.1", "", l3, "", "Setup closes after 15 min", "once configured.", "",
                         "Hold BOOT 15 s to erase", "all settings."};
  epdDrawMessage("SETUP MODE", lines, sizeof lines / sizeof lines[0]);
}

// BOOT button: hold 5 s -> restart into the setup portal; hold 15 s -> factory reset.
static void handleRecoveryButton() {
  static uint32_t pressedAt = 0;
  bool down = digitalRead(RECOVERY_BUTTON) == LOW;
  uint32_t now = millis();
  if (down && pressedAt == 0) pressedAt = now ? now : 1;
  if (down && pressedAt && now - pressedAt >= 15000) {
    Serial.println("[btn] factory reset");
    const char* lines[] = {"All settings erased.", "Restarting into setup..."};
    epdDrawMessage("FACTORY RESET", lines, 2);
    configFactoryReset();
    ESP.restart();
  }
  if (!down && pressedAt) {
    if (now - pressedAt >= 5000) {
      Serial.println("[btn] entering setup portal");
      requestSetupOnNextBoot();
      ESP.restart();
    }
    pressedAt = 0;
  }
}

// Take a dashboard handed over by the network task (or loaded from cache).
static void consumePendingData(uint32_t now) {
  JsonDocument* doc = nullptr;
  {
    Lock l;
    doc = g_net.pending;
    g_net.pending = nullptr;
  }
  if (!doc) return;
  String oldVer = g_dash ? String((*g_dash)["data_version"] | "") : String();
  String newVer = (*doc)["data_version"] | "";
  delete g_dash;
  g_dash = doc;
  uint8_t pages = (uint8_t)(*g_dash)["pages"].size();
  if (g_ui.rot.setCount(pages, now)) g_ui.pendingDraw = true;
  if (newVer != oldVer && g_ui.rot.onData(g_cfg.reset_page_on_data, now)) g_ui.pendingDraw = true;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\nLalit Stock Application firmware " FW_VERSION " - not financial advice");
  pinMode(RECOVERY_BUTTON, INPUT_PULLUP);
  g_mutex = xSemaphoreCreateMutex();
  initWatchdog();
  if (!LittleFS.begin(true)) Serial.println("[fs] LittleFS mount failed; cache disabled");
  configLoad(g_cfg);
  WiFi.mode(WIFI_STA);
  makeIdentity();
  applyRefreshPolicy();
  g_ui.rot.init(1, (uint8_t)g_cfg.selected_page, g_cfg.rotation_enabled, g_ui.rot.effectiveMs, millis());
  char reason[220];
  ls::refreshReason(g_ui.refresh, reason, sizeof reason);
  Serial.printf("[cfg] requested %lds effective %lds: %s\n", (long)g_ui.refresh.requested_s,
                (long)g_ui.refresh.effective_s, reason);
  epdInit();

  bool forceSetup = consumeForceSetupFlag();
  g_ui.setupMode = forceSetup || !configProvisioned(g_cfg);
  if (g_ui.setupMode) {
    webStart(true);
    showSetupScreen();
    return;
  }
  uint8_t savedPage = (uint8_t)g_cfg.selected_page;
  if (netLoadCache()) {
    consumePendingData(millis());
    // restore the persisted page after the cached page count is known (clamped to 1 if invalid)
    bool err = false;
    g_ui.rot.gotoPage(savedPage, millis(), &err);
  }
  netStart();
  webStart(false);
  g_ui.pendingDraw = true;
}

void loop() {
  esp_task_wdt_reset();
  webLoop();
  handleRecoveryButton();
  if (g_ui.setupMode) {
    delay(5);
    return;
  }
  uint32_t now = millis();
  consumePendingData(now);
  if (g_ui.rot.tick(now)) g_ui.pendingDraw = true;

  ApiState api;
  {
    Lock l;
    api = g_net.api;
  }
  // Redraw once when connectivity status changes so OFFLINE / cached-data age becomes visible.
  if (s_drawnOnce && api != s_drawnApi) g_ui.pendingDraw = true;

  if (g_ui.pendingDraw && g_ui.gate.canRefresh(now)) {
    g_ui.pendingDraw = false;
    s_drawnApi = api;
    s_drawnOnce = true;
    if ((int32_t)g_ui.rot.page != g_cfg.selected_page) {
      g_cfg.selected_page = g_ui.rot.page;
      configSaveRuntime(g_ui.rot.enabled, g_ui.rot.page);
    }
    epdDrawDashboard();
    // The panel refresh blocks ~21 s; restart the page timer so every page gets its full dwell.
    g_ui.rot.lastChangeMs = millis();
  }
  delay(20);
}
