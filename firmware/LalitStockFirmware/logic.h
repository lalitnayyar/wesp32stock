// Lalit Stock Application - ESP32 firmware pure logic (no Arduino dependencies; host-testable).
// Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973.
// Disclaimer: informational display only, not financial advice. Data may be delayed. No warranty.
//
// Mirrors backend/app/services/device_rules.py and frontend/src/sim/rules.ts.
// Verified against shared/test_vectors/*.json by firmware/test/host_test.cpp.
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "shared_contract.h"

namespace ls {

// ------------------------------------------------------------------ safe refresh

struct RefreshResult {
  int32_t requested_s;
  int32_t effective_s;
  int32_t min_safe_s;
  int32_t refresh_gap_s;  // minimum gap between two full refreshes (manual changes are queued behind it)
  bool clamped;
  bool fallback;
  bool verified;
  const PanelProfile* profile;  // nullptr when unknown
};

inline const PanelProfile* findProfile(const char* name) {
  if (!name) return nullptr;
  for (int i = 0; i < PANEL_PROFILE_COUNT; i++) {
    if (strcmp(PANEL_PROFILES[i].name, name) == 0) return &PANEL_PROFILES[i];
  }
  return nullptr;
}

inline RefreshResult computeRefresh(const char* profileName, int32_t requested_s) {
  RefreshResult r{};
  r.requested_s = requested_s;
  r.profile = findProfile(profileName);
  if (!r.profile) {
    r.min_safe_s = PANEL_FALLBACK_S;
    r.refresh_gap_s = PANEL_FALLBACK_S;
    r.fallback = true;
    r.verified = false;
  } else {
    // ceil(full_refresh_ms * (100 + margin) / 100 / 1000) using integer math
    uint64_t scaled = (uint64_t)r.profile->full_refresh_ms * (100u + r.profile->safety_margin_pct);
    r.refresh_gap_s = (int32_t)((scaled + 100000u - 1u) / 100000u);
    r.min_safe_s = r.refresh_gap_s + r.profile->min_dwell_s;
    r.verified = r.profile->verified;
  }
  r.effective_s = requested_s > r.min_safe_s ? requested_s : r.min_safe_s;
  r.clamped = r.effective_s != requested_s;
  return r;
}

inline void refreshReason(const RefreshResult& r, char* buf, size_t n) {
  if (r.fallback) {
    if (r.clamped)
      snprintf(buf, n, "Panel timing unknown: conservative fallback minimum of %ld s applied.", (long)r.min_safe_s);
    else
      snprintf(buf, n, "Panel timing unknown; requested %ld s is above the %ld s fallback minimum.",
               (long)r.requested_s, (long)r.min_safe_s);
  } else if (r.clamped) {
    snprintf(buf, n,
             "Requested %ld s is below the hardware-safe minimum of %ld s: a full refresh takes up to %g s "
             "(+%u%% margin) plus %u s minimum reading time.",
             (long)r.requested_s, (long)r.min_safe_s, r.profile->full_refresh_ms / 1000.0,
             (unsigned)r.profile->safety_margin_pct, (unsigned)r.profile->min_dwell_s);
  } else {
    snprintf(buf, n, "Requested %ld s is at or above the hardware-safe minimum of %ld s.", (long)r.requested_s,
             (long)r.min_safe_s);
  }
}

// ------------------------------------------------------------------ validation

// Strict integer parse: optional sign, digits only, no trailing characters, within long range.
inline bool parseIntStrict(const char* s, long* out) {
  if (!s || !*s) return false;
  char* end = nullptr;
  long v = strtol(s, &end, 10);
  if (end == s || *end != '\0') return false;
  if ((s[0] == '+' || s[0] == '-') && s[1] == '\0') return false;
  *out = v;
  return true;
}

struct IntCheck {
  long value;
  bool ok;
};

// isInt=false means the raw input was malformed (non-integer); the default is used.
inline IntCheck validateInt(bool isInt, long value, long minV, long maxV, long defV) {
  if (!isInt) return {defV, false};
  if (value < minV) return {minV, false};
  if (value > maxV) return {maxV, false};
  return {value, true};
}

inline IntCheck validateIntStr(const char* s, long minV, long maxV, long defV) {
  long v = 0;
  bool isInt = parseIntStrict(s, &v);
  return validateInt(isInt, v, minV, maxV, defV);
}

// ------------------------------------------------------------------ page rotation

// Rollover-safe: all comparisons use unsigned subtraction of millis() values.
struct PageRotator {
  uint8_t page = 1;
  uint8_t count = 1;
  bool enabled = true;
  uint32_t lastChangeMs = 0;
  uint32_t effectiveMs = 60000;

  void init(uint8_t pageCount, uint8_t selected, bool rotationEnabled, uint32_t effMs, uint32_t now) {
    count = pageCount < 1 ? 1 : pageCount;
    page = (selected < 1 || selected > count) ? 1 : selected;
    enabled = rotationEnabled;
    effectiveMs = effMs;
    lastChangeMs = now;
  }

  uint32_t msUntilNext(uint32_t now) const {
    if (!enabled || count <= 1) return 0;
    uint32_t elapsed = now - lastChangeMs;
    return elapsed >= effectiveMs ? 0 : effectiveMs - elapsed;
  }

  // Automatic rotation. Returns true when the page changed (redraw required).
  bool tick(uint32_t now) {
    if (!enabled || count <= 1) return false;
    if ((uint32_t)(now - lastChangeMs) < effectiveMs) return false;
    page = (uint8_t)(page % count + 1);
    lastChangeMs = now;
    return true;
  }

  bool next(uint32_t now) {
    uint8_t before = page;
    page = (uint8_t)(page % count + 1);
    lastChangeMs = now;
    return page != before;
  }

  // Returns true when the page changed; sets *error for out-of-range targets.
  bool gotoPage(long target, uint32_t now, bool* error) {
    if (target < 1 || target > count) {
      if (error) *error = true;
      return false;
    }
    if (error) *error = false;
    uint8_t before = page;
    page = (uint8_t)target;
    lastChangeMs = now;
    return page != before;
  }

  void pause() { enabled = false; }

  void resume(uint32_t now) {
    enabled = true;
    lastChangeMs = now;  // restart the timer; do not refresh immediately
  }

  bool setCount(uint8_t n, uint32_t now) {
    count = n < 1 ? 1 : n;
    if (page > count) {
      page = 1;
      lastChangeMs = now;
      return true;
    }
    return false;
  }

  // New dashboard data arrived (content changed): always redraw; optionally go back to page 1.
  bool onData(bool resetToFirst, uint32_t now) {
    if (resetToFirst && page != 1) {
      page = 1;
      lastChangeMs = now;
    }
    return true;
  }
};

// Gate that prevents full refreshes closer together than the panel-safe gap.
struct RefreshGate {
  bool everRefreshed = false;
  uint32_t lastStartMs = 0;
  uint32_t gapMs = 30000;

  bool canRefresh(uint32_t now) const { return !everRefreshed || (uint32_t)(now - lastStartMs) >= gapMs; }
  uint32_t msUntilAllowed(uint32_t now) const {
    if (canRefresh(now)) return 0;
    return gapMs - (uint32_t)(now - lastStartMs);
  }
  void markStarted(uint32_t now) {
    everRefreshed = true;
    lastStartMs = now;
  }
};

// ------------------------------------------------------------------ header/footer draw-ops

struct DrawOp {
  char kind;  // 'T' text, 'F' filled rect, 'R' outline rect, 'H' horizontal line
  int16_t x, y, w, h;
  uint8_t size;
  char color;  // 'K','W','R','Y'
  char text[L_LIM_MAX_TEXT_LEN + 1];
};

struct HeaderStatus {
  const char* datetime;  // nullptr = no time sync
  const char* last_ok;   // "HH:MM" or nullptr
  bool wifi;
  const char* api;     // "OK" | "ERR" | "OFF"
  const char* market;  // e.g. "OPEN"
  const char* flag;    // "" | "STALE" | "CACHED" | "DELAYED"
  int page, pages;
  long age_s;  // < 0 = unknown
  bool offline;
};

inline void formatAge(long s, char* buf, size_t n) {
  if (s < 60) snprintf(buf, n, "%lds", s);
  else if (s < 3600) snprintf(buf, n, "%ldm", s / 60);
  else if (s < 172800) snprintf(buf, n, "%ldh", s / 3600);
  else snprintf(buf, n, "%ldd", s / 86400);
}

inline void addText(DrawOp* out, int& n, int max, int x, int y, char color, const char* text, uint8_t size = 1) {
  if (n >= max) return;
  DrawOp& o = out[n++];
  o.kind = 'T';
  o.x = x;
  o.y = y;
  o.w = o.h = 0;
  o.size = size;
  o.color = color;
  strncpy(o.text, text, L_LIM_MAX_TEXT_LEN);
  o.text[L_LIM_MAX_TEXT_LEN] = '\0';
}

inline void addRect(DrawOp* out, int& n, int max, char kind, int x, int y, int w, int h, char color) {
  if (n >= max) return;
  DrawOp& o = out[n++];
  o.kind = kind;
  o.x = x;
  o.y = y;
  o.w = w;
  o.h = h;
  o.size = 0;
  o.color = color;
  o.text[0] = '\0';
}

inline int rightX(const char* text, int size = 1) {
  return L_WIDTH - L_MARGIN_X - (int)strlen(text) * L_CHAR_W * size;
}

// Builds header ops followed by footer ops. Body ops come from the server. Positions come from the
// compiled panel's layout and colours from its palette roles (L_C_*), so the 2.9in 4-colour output is
// unchanged and 4.2in black/white or black/white/red panels never receive a colour they cannot show.
inline int buildHeaderFooterOps(const HeaderStatus& s, DrawOp* out, int max) {
  int n = 0;
  char buf[48];
  addRect(out, n, max, 'F', 0, 0, L_WIDTH, L_HDR_BAR_H, L_C_ACCENT);
  addText(out, n, max, L_MARGIN_X, L_HDR_TITLE_Y, 'W', L_HDR_TITLE, L_HDR_TITLE_SIZE);
  if (s.datetime) addText(out, n, max, L_MARGIN_X, L_HDR_DATETIME_Y, 'K', s.datetime);
  else addText(out, n, max, L_MARGIN_X, L_HDR_DATETIME_Y, L_C_NEG, "NO TIME SYNC");
  snprintf(buf, sizeof buf, "Upd %s", s.last_ok ? s.last_ok : "--:--");
  addText(out, n, max, L_HDR_UPD_X, L_HDR_STATUS_Y, 'K', buf);
  addText(out, n, max, L_HDR_WIFI_X, L_HDR_STATUS_Y, s.wifi ? 'K' : L_C_NEG, s.wifi ? "WiFi:OK" : "WiFi:--");
  snprintf(buf, sizeof buf, "API:%s", s.api);
  addText(out, n, max, L_HDR_API_X, L_HDR_STATUS_Y, strcmp(s.api, "OK") == 0 ? 'K' : L_C_NEG, buf);
  snprintf(buf, sizeof buf, "Mkt:%s", s.market && *s.market ? s.market : "--");
  addText(out, n, max, L_HDR_MARKET_X, L_HDR_MARKET_Y, 'K', buf);
  if (s.flag && *s.flag) {
    int w = (int)strlen(s.flag) * L_CHAR_W + 4;
    int x = L_WIDTH - L_MARGIN_X - w;
    addRect(out, n, max, 'F', x, L_HDR_MARKET_Y - 2, w, 11, L_C_FLAG_BG);
    addText(out, n, max, x + 2, L_HDR_MARKET_Y, L_C_FLAG_FG, s.flag);
  }
  addRect(out, n, max, 'H', 0, L_HDR_SEP_Y, L_WIDTH, 1, 'K');
  addRect(out, n, max, 'H', 0, L_FOOTER_SEP_Y, L_WIDTH, 1, 'K');
  snprintf(buf, sizeof buf, "PAGE %d/%d", s.page, s.pages);
  addText(out, n, max, L_MARGIN_X, L_FOOTER_TEXT_Y, 'K', buf);
  char age[16];
  if (s.age_s >= 0) formatAge(s.age_s, age, sizeof age);
  else strcpy(age, "--");
  snprintf(buf, sizeof buf, s.offline ? "OFFLINE %s" : "Age %s", age);
  addText(out, n, max, rightX(buf), L_FOOTER_TEXT_Y, s.offline ? L_C_NEG : 'K', buf);
  return n;
}

}  // namespace ls
