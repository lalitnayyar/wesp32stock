// ESP32 + WeAct Studio E-Paper test sketch (Hello World).
// See ESP32_WeAct_2.9_EPaper.md for wiring and setup instructions.
//
// Panels (choose with -DLS_PANEL=..., which upload.bat / upload.sh set from their PANEL argument):
//   LS_PANEL_290_4C  WeAct 2.9" 4-colour, 168 x 384, GDEY029F51H / JD79667 (confirmed on hardware, default)
//   LS_PANEL_420_BW  WeAct 4.2" black/white, 400 x 300, GDEY042T81 / SSD1683
//   LS_PANEL_420_BWR WeAct 4.2" black/white/red, 400 x 300, GDEY042Z98 / SSD1683
//   LS_PANEL_420_4C  WeAct 4.2" 4-colour, 400 x 300, GDEY0420F51 / HX8717
// All modules use the same 8-pin header and the same ESP32 pins below.

#include <SPI.h>

#define LS_PANEL_290_4C 1
#define LS_PANEL_420_BW 2
#define LS_PANEL_420_BWR 3
#define LS_PANEL_420_4C 4
#ifndef LS_PANEL
#define LS_PANEL LS_PANEL_290_4C
#endif

#define EPD_BUSY  4
#define EPD_RST   26
#define EPD_DC    25
#define EPD_CS    5
#define EPD_SCK   18
#define EPD_MOSI  23

#if LS_PANEL == LS_PANEL_290_4C
#include <GxEPD2_4C.h>
GxEPD2_4C<GxEPD2_290c_GDEY029F51H, GxEPD2_290c_GDEY029F51H::HEIGHT> display(
  GxEPD2_290c_GDEY029F51H(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
#define PANEL_NAME "2.9in 4-colour"
#define COLOR_ACCENT GxEPD_RED
#define COLOR_OK GxEPD_YELLOW
#elif LS_PANEL == LS_PANEL_420_BW
#include <GxEPD2_BW.h>
GxEPD2_BW<GxEPD2_420_GDEY042T81, GxEPD2_420_GDEY042T81::HEIGHT> display(
  GxEPD2_420_GDEY042T81(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
#define PANEL_NAME "4.2in black/white"
#define COLOR_ACCENT GxEPD_BLACK
#define COLOR_OK GxEPD_BLACK
#elif LS_PANEL == LS_PANEL_420_BWR
#include <GxEPD2_3C.h>
GxEPD2_3C<GxEPD2_420c_GDEY042Z98, GxEPD2_420c_GDEY042Z98::HEIGHT / 2> display(
  GxEPD2_420c_GDEY042Z98(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
#define PANEL_NAME "4.2in black/white/red"
#define COLOR_ACCENT GxEPD_RED
#define COLOR_OK GxEPD_RED
#elif LS_PANEL == LS_PANEL_420_4C
#include <GxEPD2_4C.h>
GxEPD2_4C<GxEPD2_420c_GDEY0420F51, GxEPD2_420c_GDEY0420F51::HEIGHT / 2> display(
  GxEPD2_420c_GDEY0420F51(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
#define PANEL_NAME "4.2in 4-colour"
#define COLOR_ACCENT GxEPD_RED
#define COLOR_OK GxEPD_YELLOW
#else
#error "Unknown LS_PANEL"
#endif
// After the driver include, so arduino-cli has already picked up Adafruit GFX (which contains Fonts/).
#include <Fonts/FreeSansBold12pt7b.h>

void drawTestScreen() {
  Serial.println("Drawing test screen...");
  // Landscape on every panel: the 2.9in is natively portrait (168 x 384) and is rotated to 384 x 168 so the
  // bold heading does not wrap; the 4.2in panels are natively landscape (400 x 300).
  display.setRotation(display.width() < display.height() ? 1 : 0);
  display.setTextWrap(false);
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.fillRect(0, 0, display.width(), 36, COLOR_ACCENT);
    display.setTextColor(GxEPD_WHITE);
    display.setCursor(10, 25);
    display.print("ESP32 TEST");

    display.setTextColor(GxEPD_BLACK);
    display.setFont(&FreeSansBold12pt7b);
    display.setCursor(10, 80);
    display.print("HELLO WORLD");
    display.setFont();

    display.setCursor(10, 110);
    display.print("E-Paper Test: " PANEL_NAME);

    display.setTextColor(COLOR_OK);
    display.setCursor(10, 130);
    display.print("Status: SUCCESS");

    display.drawRect(2, 40, display.width() - 4,
                     display.height() - 44, GxEPD_BLACK);
  } while (display.nextPage());
  Serial.println("Display update command completed");
  display.hibernate();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("ESP32 E-PAPER TEST (" PANEL_NAME ")");
  SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  Serial.println("Initializing E-Paper...");
  display.init(115200);
  drawTestScreen();
}

void loop() {
  // E-Paper retains its image; no continuous refresh required.
}
