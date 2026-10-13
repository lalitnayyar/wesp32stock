// Lalit Stock Application - E-Paper renderer.
// Owner: Lalit Nayyar <consult@lalit.cloud>. Not financial advice. No warranty.
//
// The panel is chosen at compile time (LS_PANEL, see shared_contract.h; flash.bat COMx <build>):
//   290_4c  WeAct 2.9in 4-colour  GDEY029F51H / JD79667   portrait 168x384   (default, hardware-verified)
//   420_bw  WeAct 4.2in B/W       GDEY042T81 / SSD1683    landscape 400x300
//   420_bwr WeAct 4.2in B/W/R     GDEY042Z98 / SSD1683    landscape 400x300
//   420_4c  WeAct 4.2in 4-colour  GDEY0420F51 / HX8717    landscape 400x300
// Executes the server's page body draw-ops (docs/RENDER_CONTRACT.md) and draws the local
// header/footer from ls::buildHeaderFooterOps so output matches the browser simulator.
#include <SPI.h>
#include <esp_task_wdt.h>
#include <time.h>

#include "app_state.h"

#if LS_PANEL == LS_PANEL_290_4C
#include <GxEPD2_4C.h>
static GxEPD2_4C<GxEPD2_290c_GDEY029F51H, GxEPD2_290c_GDEY029F51H::HEIGHT> display(
    GxEPD2_290c_GDEY029F51H(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
#elif LS_PANEL == LS_PANEL_420_BW
#include <GxEPD2_BW.h>
static GxEPD2_BW<GxEPD2_420_GDEY042T81, GxEPD2_420_GDEY042T81::HEIGHT> display(
    GxEPD2_420_GDEY042T81(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
#elif LS_PANEL == LS_PANEL_420_BWR
#include <GxEPD2_3C.h>
// Half-height page buffer (2 x 7.5 KB): drawing runs in two passes, the panel still refreshes once.
static GxEPD2_3C<GxEPD2_420c_GDEY042Z98, GxEPD2_420c_GDEY042Z98::HEIGHT / 2> display(
    GxEPD2_420c_GDEY042Z98(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
#elif LS_PANEL == LS_PANEL_420_4C
#include <GxEPD2_4C.h>
static GxEPD2_4C<GxEPD2_420c_GDEY0420F51, GxEPD2_420c_GDEY0420F51::HEIGHT / 2> display(
    GxEPD2_420c_GDEY0420F51(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
#endif

// Colours outside the panel's palette never come from the server (palette-aware layout), but map them
// safely anyway: red/yellow become black on a B/W panel, yellow becomes red on a B/W/R panel.
static uint16_t color(char c) {
  if (c == 'W') return GxEPD_WHITE;
  if (c == 'Y' && strchr(L_PALETTE, 'Y')) return GxEPD_YELLOW;
  if ((c == 'R' || c == 'Y') && strchr(L_PALETTE, 'R')) return GxEPD_RED;
  return GxEPD_BLACK;
}

// Called continuously while the panel is BUSY (~21 s per full refresh): keep the watchdog fed and
// keep the admin page responsive. Web handlers only change state; they never draw.
static void busyCallback(const void*) {
  esp_task_wdt_reset();
  webLoop();
  delay(1);
}

void epdInit() {
  SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  display.init(115200, true, 10, false);
  display.epd2.setBusyCallback(busyCallback);
  display.setRotation(0);  // native orientation: 2.9in portrait 168 x 384, 4.2in landscape 400 x 300
  display.setTextWrap(false);
}

bool epdTimeValid() {
  time_t now = time(nullptr);
  return now > 1700000000;  // after Nov 2023 => NTP has synced
}

static void drawOp(char kind, int x, int y, int w, int h, int size, char c, const char* text) {
  switch (kind) {
    case 'T':
      display.setFont();
      display.setTextSize(size < 1 ? 1 : (size > 3 ? 3 : size));
      display.setTextColor(color(c));
      display.setCursor(x, y);
      display.print(text);
      break;
    case 'F': display.fillRect(x, y, w, h, color(c)); break;
    case 'R': display.drawRect(x, y, w, h, color(c)); break;
    case 'H': display.drawFastHLine(x, y, w, color(c)); break;
  }
}

// Server ops: ["T",x,y,size,color,text] ["F"|"R",x,y,w,h,color] ["H",x,y,w,color]
static void drawServerOp(JsonArrayConst op) {
  const char* kind = op[0] | "";
  if (!kind[0]) return;
  int x = op[1] | 0, y = op[2] | 0;
  if (kind[0] == 'T') {
    const char* col = op[4] | "K";
    char text[L_LIM_MAX_TEXT_LEN + 1];
    strlcpy(text, op[5] | "", sizeof text);
    drawOp('T', x, y, 0, 0, op[3] | 1, col[0], text);
  } else if (kind[0] == 'H') {
    const char* col = op[4] | "K";
    drawOp('H', x, y, op[3] | 0, 1, 0, col[0], "");
  } else if (kind[0] == 'F' || kind[0] == 'R') {
    const char* col = op[5] | "K";
    drawOp(kind[0], x, y, op[3] | 0, op[4] | 0, 0, col[0], "");
  }
}

static void buildStatus(ls::HeaderStatus& hs, char* dt, char* lastOk, char* market) {
  NetState n;
  {
    Lock l;
    n.wifi = g_net.wifi;
    n.api = g_net.api;
    n.hasData = g_net.hasData;
    n.okSinceBoot = g_net.okSinceBoot;
    n.lastOkMs = g_net.lastOkMs;
    n.lastOkEpoch = g_net.lastOkEpoch;
    n.fromCache = g_net.fromCache;
    n.dataGeneratedEpoch = g_net.dataGeneratedEpoch;
  }
  bool tv = epdTimeValid();
  if (tv) {
    time_t now = time(nullptr);
    struct tm t;
    localtime_r(&now, &t);
    strftime(dt, 24, "%d %b %Y %H:%M", &t);
  }
  hs.datetime = tv ? dt : nullptr;
  hs.last_ok = nullptr;
  if (n.lastOkEpoch > 0) {
    struct tm t;
    localtime_r(&n.lastOkEpoch, &t);
    strftime(lastOk, 8, "%H:%M", &t);
    hs.last_ok = lastOk;
  }
  hs.wifi = n.wifi;
  hs.api = n.api == ApiState::OK ? "OK" : n.api == ApiState::ERR ? "ERR" : "OFF";
  strcpy(market, "--");
  hs.flag = "";
  if (g_dash) {
    JsonObjectConst st = (*g_dash)["status"];
    strlcpy(market, st["market"] | "--", 8);
    if (n.api != ApiState::OK) hs.flag = "CACHED";
    else if (st["stale"] | false) hs.flag = "STALE";
    else if (st["delayed"] | false) hs.flag = "DELAYED";
  }
  hs.market = market;
  hs.page = g_ui.rot.page;
  hs.pages = g_ui.rot.count;
  hs.age_s = -1;
  if (n.okSinceBoot) hs.age_s = (long)((millis() - n.lastOkMs) / 1000u);
  else if (n.fromCache && tv && n.dataGeneratedEpoch > 0) hs.age_s = (long)(time(nullptr) - n.dataGeneratedEpoch);
  hs.offline = n.api != ApiState::OK;
}

void epdDrawDashboard() {
  ls::HeaderStatus hs{};
  char dt[24], lastOk[8], market[8];
  buildStatus(hs, dt, lastOk, market);
  ls::DrawOp hdr[24];
  int nh = ls::buildHeaderFooterOps(hs, hdr, 24);
  JsonArrayConst ops;
  if (g_dash) ops = (*g_dash)["pages"][g_ui.rot.page - 1]["ops"];

  uint32_t t0 = millis();
  g_ui.drawing = true;
  g_ui.lastDrawStartMs = t0;
  g_ui.gate.markStarted(t0);
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    for (int i = 0; i < nh; i++)
      drawOp(hdr[i].kind, hdr[i].x, hdr[i].y, hdr[i].w, hdr[i].h, hdr[i].size, hdr[i].color, hdr[i].text);
    if (ops.isNull()) {
      drawOp('T', L_MARGIN_X, L_BODY_TOP + 16, 0, 0, 1, 'K', "Waiting for data...");
      drawOp('T', L_MARGIN_X, L_BODY_TOP + 28, 0, 0, 1, 'K', "Check Wi-Fi / API settings");
    } else {
      int count = 0;
      for (JsonArrayConst op : ops) {
        if (++count > L_LIM_MAX_OPS_PER_PAGE) break;
        drawServerOp(op);
      }
    }
  } while (display.nextPage());
  display.hibernate();
  g_ui.drawing = false;
  g_ui.lastRefreshMs = millis() - t0;
  g_ui.refreshCount++;
  // GxEPD2 waits up to 50 s on BUSY; treat a refresh that ran that long as a BUSY timeout.
  if (g_ui.lastRefreshMs >= 49000) g_ui.busyTimeouts++;
  Serial.printf("[epd] page %u/%u drawn in %lu ms\n", g_ui.rot.page, g_ui.rot.count, (unsigned long)g_ui.lastRefreshMs);
}

void epdDrawMessage(const char* title, const char* const* lines, int n) {
  g_ui.gate.markStarted(millis());
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.fillRect(0, 0, L_WIDTH, L_HDR_BAR_H, color(L_C_ACCENT));
    drawOp('T', L_MARGIN_X, L_HDR_TITLE_Y, 0, 0, L_HDR_TITLE_SIZE, 'W', L_HDR_TITLE);
    drawOp('T', L_MARGIN_X, L_HDR_BAR_H + 10, 0, 0, 1, L_C_ACCENT, title);
    for (int i = 0; i < n; i++) drawOp('T', L_MARGIN_X, L_HDR_BAR_H + 26 + i * 12, 0, 0, 1, 'K', lines[i]);
    drawOp('T', L_MARGIN_X, L_HEIGHT - 33, 0, 0, 1, 'K', "Not financial advice.");
  } while (display.nextPage());
  display.hibernate();
  g_ui.refreshCount++;
}
