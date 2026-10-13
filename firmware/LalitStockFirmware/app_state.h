// Lalit Stock Application - ESP32 firmware shared state.
// Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973. Not financial advice. No warranty.
#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

#include "logic.h"

#define FW_VERSION "1.1.0"

// ---- E-Paper panel: driver chosen with LS_PANEL (see epaper.cpp and shared_contract.h).
// Wiring (compile time, LS_WIRING; flash_esp32 wizard or flash.bat COMx <build> <wiring>):
//   1 standard  BUSY 4, RES 26, D/C 25, CS 5, SCK 18, MOSI 23   (confirmed on the WeAct 2.9" 4C)
//   2 uart2     BUSY 4, RES 16 (RX2), D/C 17 (TX2), CS 5, SCK 18, MOSI 23   (ESP32-Epaper-Wiring.png)
// GPIO16/17 are free on ESP32-WROOM-32 DevKits; on WROVER boards they are used by PSRAM, so use standard there.
#define LS_WIRING_STANDARD 1
#define LS_WIRING_UART2 2
#ifndef LS_WIRING
#define LS_WIRING LS_WIRING_STANDARD
#endif
#define EPD_BUSY 4
#if LS_WIRING == LS_WIRING_UART2
#define EPD_RST 16
#define EPD_DC 17
#define LS_WIRING_NAME "uart2 (RES 16, D/C 17)"
#elif LS_WIRING == LS_WIRING_STANDARD
#define EPD_RST 26
#define EPD_DC 25
#define LS_WIRING_NAME "standard (RES 26, D/C 25)"
#else
#error "Unknown LS_WIRING: use LS_WIRING_STANDARD or LS_WIRING_UART2"
#endif
#define EPD_CS 5
#define EPD_SCK 18
#define EPD_MOSI 23
#define RECOVERY_BUTTON 0  // BOOT button: hold 5 s = setup portal, hold 15 s = factory reset

struct DeviceConfig {
  // shared contract fields (shared/device_config.json)
  bool rotation_enabled;
  int32_t page_duration_s;  // requested
  int32_t selected_page;
  bool reset_page_on_data;
  int32_t fetch_interval_s;
  int32_t heartbeat_interval_s;
  int32_t ntp_interval_s;
  int32_t api_timeout_ms;
  int32_t rows_per_page;
  bool show_summary_page;
  bool show_benchmarks_page;
  char panel_profile[32];
  char timezone[CFG_TIMEZONE_MAXLEN + 1];
  char posix_tz[CFG_POSIX_TZ_MAXLEN + 1];
  char ntp_server[CFG_NTP_SERVER_MAXLEN + 1];
  // device-only fields
  char device_name[33];
  char wifi_ssid[33];
  char wifi_pass[65];
  char api_url[161];
  char api_key[100];
  char admin_pass[65];
  String root_ca;  // optional PEM; empty = built-in CA bundle
};

enum class ApiState : uint8_t { OFF, OK, ERR };

// State written by the network task and read by the UI loop (guarded by g_mutex).
struct NetState {
  bool wifi = false;
  int32_t rssi = 0;
  ApiState api = ApiState::OFF;
  bool hasData = false;
  bool fromCache = false;       // current data loaded from flash, no successful fetch yet
  uint32_t lastOkMs = 0;        // millis() of last successful fetch (valid if okSinceBoot)
  bool okSinceBoot = false;
  time_t lastOkEpoch = 0;       // wall time of last success (0 = unknown)
  time_t dataGeneratedEpoch = 0;
  uint32_t lastAttemptMs = 0;
  uint32_t fetchCount = 0;      // network fetch attempts (never incremented by page changes)
  uint32_t fetchOk = 0;
  uint32_t heartbeatOk = 0;
  char lastError[96] = "";
  char dataVersion[16] = "";
  JsonDocument* pending = nullptr;  // new dashboard handed from net task to UI loop
};

struct UiState {
  ls::PageRotator rot;
  ls::RefreshGate gate;
  ls::RefreshResult refresh{};
  bool pendingDraw = true;
  uint32_t refreshCount = 0;
  uint32_t busyTimeouts = 0;
  uint32_t lastRefreshMs = 0;     // duration of the last refresh
  uint32_t lastDrawStartMs = 0;
  bool drawing = false;
  bool setupMode = false;
  bool ntpOk = false;
  char setupSsid[33] = "";
  char setupPass[17] = "";
};

extern DeviceConfig g_cfg;
extern NetState g_net;
extern UiState g_ui;
extern SemaphoreHandle_t g_mutex;
extern JsonDocument* g_dash;  // current dashboard (UI loop only)
extern String g_deviceId;

struct Lock {
  Lock() { xSemaphoreTake(g_mutex, portMAX_DELAY); }
  ~Lock() { xSemaphoreGive(g_mutex); }
};

// config_store.cpp
void configDefaults(DeviceConfig& c);
void configLoad(DeviceConfig& c);
void configSave(const DeviceConfig& c);
void configSaveRuntime(bool rotationEnabled, int32_t selectedPage);
void configFactoryReset();
bool configProvisioned(const DeviceConfig& c);
void applyRefreshPolicy();  // recompute effective interval from g_cfg

// epaper.cpp
void epdInit();
void epdDrawDashboard();
void epdDrawMessage(const char* title, const char* const* lines, int n);
bool epdTimeValid();

// net_client.cpp
void netStart();
void netRequestFetch();
void netRequestHeartbeat();
bool netTestApi(char* msg, size_t n);
bool netLoadCache();

// web_admin.cpp
void webStart(bool setupMode);
void webLoop();
