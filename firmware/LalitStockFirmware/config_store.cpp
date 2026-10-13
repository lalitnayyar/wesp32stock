// Lalit Stock Application - NVS (Preferences) persistence for device configuration.
// Owner: Lalit Nayyar <consult@lalit.cloud>. Not financial advice. No warranty.
#include <LittleFS.h>
#include <Preferences.h>

#include "app_state.h"

static const char* NS = "lstock";

static void copyStr(char* dst, size_t n, const String& s, const char* def) {
  String v = s.length() ? s : String(def);
  strncpy(dst, v.c_str(), n - 1);
  dst[n - 1] = '\0';
}

void configDefaults(DeviceConfig& c) {
  c.rotation_enabled = CFG_ROTATION_ENABLED_DEFAULT;
  c.page_duration_s = CFG_PAGE_DURATION_S_DEFAULT;
  c.selected_page = CFG_SELECTED_PAGE_DEFAULT;
  c.reset_page_on_data = CFG_RESET_PAGE_ON_DATA_DEFAULT;
  c.fetch_interval_s = CFG_FETCH_INTERVAL_S_DEFAULT;
  c.heartbeat_interval_s = CFG_HEARTBEAT_INTERVAL_S_DEFAULT;
  c.ntp_interval_s = CFG_NTP_INTERVAL_S_DEFAULT;
  c.api_timeout_ms = CFG_API_TIMEOUT_MS_DEFAULT;
  c.rows_per_page = CFG_ROWS_PER_PAGE_DEFAULT;
  c.show_summary_page = CFG_SHOW_SUMMARY_PAGE_DEFAULT;
  c.show_benchmarks_page = CFG_SHOW_BENCHMARKS_PAGE_DEFAULT;
  strcpy(c.panel_profile, LS_PANEL_PROFILE);
  strcpy(c.timezone, CFG_TIMEZONE_DEFAULT);
  strcpy(c.posix_tz, CFG_POSIX_TZ_DEFAULT);
  strcpy(c.ntp_server, CFG_NTP_SERVER_DEFAULT);
  strcpy(c.device_name, "E-Paper");
  c.wifi_ssid[0] = c.wifi_pass[0] = c.api_url[0] = c.api_key[0] = c.admin_pass[0] = '\0';
  c.root_ca = "";
}

static int32_t clampInt(Preferences& p, const char* key, long mn, long mx, long def) {
  long v = p.getLong(key, def);
  return (int32_t)ls::validateInt(true, v, mn, mx, def).value;
}

void configLoad(DeviceConfig& c) {
  configDefaults(c);
  Preferences p;
  if (!p.begin(NS, true)) return;  // first boot: namespace absent
  c.rotation_enabled = p.getBool("rot", c.rotation_enabled);
  c.page_duration_s = clampInt(p, "dur", CFG_PAGE_DURATION_S_MIN, CFG_PAGE_DURATION_S_MAX, CFG_PAGE_DURATION_S_DEFAULT);
  c.selected_page = clampInt(p, "page", CFG_SELECTED_PAGE_MIN, CFG_SELECTED_PAGE_MAX, CFG_SELECTED_PAGE_DEFAULT);
  c.reset_page_on_data = p.getBool("rstpg", c.reset_page_on_data);
  c.fetch_interval_s = clampInt(p, "fetch", CFG_FETCH_INTERVAL_S_MIN, CFG_FETCH_INTERVAL_S_MAX, CFG_FETCH_INTERVAL_S_DEFAULT);
  c.heartbeat_interval_s = clampInt(p, "hb", CFG_HEARTBEAT_INTERVAL_S_MIN, CFG_HEARTBEAT_INTERVAL_S_MAX, CFG_HEARTBEAT_INTERVAL_S_DEFAULT);
  c.ntp_interval_s = clampInt(p, "ntpi", CFG_NTP_INTERVAL_S_MIN, CFG_NTP_INTERVAL_S_MAX, CFG_NTP_INTERVAL_S_DEFAULT);
  c.api_timeout_ms = clampInt(p, "tmo", CFG_API_TIMEOUT_MS_MIN, CFG_API_TIMEOUT_MS_MAX, CFG_API_TIMEOUT_MS_DEFAULT);
  c.rows_per_page = clampInt(p, "rows", CFG_ROWS_PER_PAGE_MIN, CFG_ROWS_PER_PAGE_MAX, CFG_ROWS_PER_PAGE_DEFAULT);
  c.show_summary_page = p.getBool("sum", c.show_summary_page);
  c.show_benchmarks_page = p.getBool("bench", c.show_benchmarks_page);
  copyStr(c.panel_profile, sizeof c.panel_profile, p.getString("panel", ""), LS_PANEL_PROFILE);
  copyStr(c.timezone, sizeof c.timezone, p.getString("tz", ""), CFG_TIMEZONE_DEFAULT);
  copyStr(c.posix_tz, sizeof c.posix_tz, p.getString("ptz", ""), CFG_POSIX_TZ_DEFAULT);
  copyStr(c.ntp_server, sizeof c.ntp_server, p.getString("ntp", ""), CFG_NTP_SERVER_DEFAULT);
  copyStr(c.device_name, sizeof c.device_name, p.getString("name", ""), "E-Paper");
  copyStr(c.wifi_ssid, sizeof c.wifi_ssid, p.getString("ssid", ""), "");
  copyStr(c.wifi_pass, sizeof c.wifi_pass, p.getString("wpass", ""), "");
  copyStr(c.api_url, sizeof c.api_url, p.getString("url", ""), "");
  copyStr(c.api_key, sizeof c.api_key, p.getString("key", ""), "");
  copyStr(c.admin_pass, sizeof c.admin_pass, p.getString("admin", ""), "");
  c.root_ca = p.getString("ca", "");
  p.end();
  // The timing profile must match the compiled panel (e.g. after reflashing a 2.9in board with a 4.2in
  // build); UNKNOWN stays allowed and applies the conservative fallback.
  if (strcmp(c.panel_profile, LS_PANEL_PROFILE) != 0 && strcmp(c.panel_profile, "UNKNOWN") != 0)
    strcpy(c.panel_profile, LS_PANEL_PROFILE);
}

void configSave(const DeviceConfig& c) {
  Preferences p;
  p.begin(NS, false);
  p.putBool("rot", c.rotation_enabled);
  p.putLong("dur", c.page_duration_s);
  p.putLong("page", c.selected_page);
  p.putBool("rstpg", c.reset_page_on_data);
  p.putLong("fetch", c.fetch_interval_s);
  p.putLong("hb", c.heartbeat_interval_s);
  p.putLong("ntpi", c.ntp_interval_s);
  p.putLong("tmo", c.api_timeout_ms);
  p.putLong("rows", c.rows_per_page);
  p.putBool("sum", c.show_summary_page);
  p.putBool("bench", c.show_benchmarks_page);
  p.putString("panel", c.panel_profile);
  p.putString("tz", c.timezone);
  p.putString("ptz", c.posix_tz);
  p.putString("ntp", c.ntp_server);
  p.putString("name", c.device_name);
  p.putString("ssid", c.wifi_ssid);
  p.putString("wpass", c.wifi_pass);
  p.putString("url", c.api_url);
  p.putString("key", c.api_key);
  p.putString("admin", c.admin_pass);
  p.putString("ca", c.root_ca);
  p.end();
}

// Called on rotation pause/resume and page changes. Only writes when the value changed
// (NVS wear-levels; one small entry per change is well within flash endurance).
void configSaveRuntime(bool rotationEnabled, int32_t selectedPage) {
  Preferences p;
  p.begin(NS, false);
  if (p.getBool("rot", !rotationEnabled) != rotationEnabled) p.putBool("rot", rotationEnabled);
  if (p.getLong("page", -1) != selectedPage) p.putLong("page", selectedPage);
  p.end();
}

void configFactoryReset() {
  Preferences p;
  p.begin(NS, false);
  p.clear();
  p.end();
  LittleFS.remove("/dash.json");
}

bool configProvisioned(const DeviceConfig& c) {
  return c.wifi_ssid[0] && c.api_url[0] && c.api_key[0] && c.admin_pass[0];
}

void applyRefreshPolicy() {
  g_ui.refresh = ls::computeRefresh(g_cfg.panel_profile, g_cfg.page_duration_s);
  g_ui.rot.effectiveMs = (uint32_t)g_ui.refresh.effective_s * 1000u;
  g_ui.gate.gapMs = (uint32_t)g_ui.refresh.refresh_gap_s * 1000u;
}
