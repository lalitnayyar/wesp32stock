// ESP32 + WeAct Studio 2.9" E-Paper test sketch.
// See ESP32_WeAct_2.9_EPaper.md for wiring and setup instructions.
//
// Confirmed panel: WeAct Studio 2.9" 4-color module, 168 x 384, panel
// GDEY029F51H, controller JD79667 -> GxEPD2 driver class GxEPD2_290c_GDEY029F51H.

#include <SPI.h>
#include <GxEPD2_4C.h>
#include <Fonts/FreeSansBold12pt7b.h>

#define EPD_BUSY  4
#define EPD_RST   26
#define EPD_DC    25
#define EPD_CS    5
#define EPD_SCK   18
#define EPD_MOSI  23

GxEPD2_4C<GxEPD2_290c_GDEY029F51H, GxEPD2_290c_GDEY029F51H::HEIGHT> display(
  GxEPD2_290c_GDEY029F51H(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY)
);

void drawTestScreen() {
  Serial.println("Drawing test screen...");
  // Panel is natively portrait (168 x 384); rotate to landscape (384 x 168)
  // so there is enough horizontal room for the bold heading not to wrap.
  display.setRotation(1);
  display.setTextWrap(false);
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.fillRect(0, 0, display.width(), 36, GxEPD_RED);
    display.setTextColor(GxEPD_WHITE);
    display.setCursor(10, 25);
    display.print("ESP32 TEST");

    display.setTextColor(GxEPD_BLACK);
    display.setFont(&FreeSansBold12pt7b);
    display.setCursor(10, 80);
    display.print("HELLO WORLD");
    display.setFont();

    display.setCursor(10, 110);
    display.print("E-Paper Test");

    display.setTextColor(GxEPD_YELLOW);
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
  Serial.println("ESP32 E-PAPER TEST");
  SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  Serial.println("Initializing E-Paper...");
  display.init(115200);
  drawTestScreen();
}

void loop() {
  // E-Paper retains its image; no continuous refresh required.
}
