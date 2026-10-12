# ESP32 + WeAct Studio 2.9-inch E-Paper: CLI Test Guide

## Hardware

- Controller: ESP32-WROOM-32 development board, USB-C, using **ESP32 Dev Module** board profile.
- E-Paper adapter: WeAct Studio 2.9-inch **4-color** module, **168 × 384** pixels, SPI.
- **Panel controller confirmed:** panel **GDEY029F51H**, controller **JD79667** (4-color: black/white/red/yellow). GxEPD2 driver class: `GxEPD2_290c_GDEY029F51H` (used via `GxEPD2_4C.h`), not the black/white `GxEPD2_BW` template.
- The ESP32 photographed has **no D16 or D17 labels**, so this guide uses GPIO25 and GPIO26 instead.
- ESP32 through-hole pads may require soldered header pins for reliable jumper-wire connections.

## Wiring

**Disconnect USB power before wiring.** Wire colors below correspond to the cable colors identified in the user's photos; always verify using the labels on the display connector, not color alone.

| Actual wire color | E-Paper label | ESP32 board label | GPIO |
|---|---|---|---|
| Red | VCC | 3V3 | 3.3 V power |
| Black | GND | GND | Ground |
| Yellow | SDA (SPI MOSI) | D23 | 23 |
| Green | SCL (SPI SCK) | D18 | 18 |
| Blue | CS | D5 | 5 |
| White | D/C | D25 | 25 |
| Orange | RES | D26 | 26 |
| Purple | BUSY | D4 | 4 |

**Use 3V3 only, not VIN or 5V.** The module's printed notes describe different supply configurations, but 3.3 V is the safe choice for this ESP32 setup.

## Windows setup

1. Install Arduino IDE from the official Arduino website.
2. Under **File → Preferences → Additional Boards Manager URLs**, add:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. In **Boards Manager**, install **esp32 by Espressif Systems**.
4. Select **Tools → Board → ESP32 Dev Module** and the correct COM port.
5. In **Library Manager**, install **GxEPD2** and **Adafruit GFX Library**.
6. Connect the ESP32 using a data-capable USB-C cable.

## Example sketch: `ESP32_EPaper_Test.ino`

Panel GDEY029F51H (controller JD79667) is a 4-color (black/white/red/yellow) panel, so the sketch uses the `GxEPD2_4C` template and the `GxEPD2_290c_GDEY029F51H` driver class, not the black/white `GxEPD2_BW` template used for most other 2.9" panels.

```cpp
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
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.fillRect(0, 0, display.width(), 30, GxEPD_RED);
    display.setTextColor(GxEPD_WHITE);
    display.setCursor(10, 20);
    display.print("ESP32 TEST");
    display.setTextColor(GxEPD_BLACK);
    display.setFont(&FreeSansBold12pt7b);
    display.setCursor(10, 65);
    display.print("HELLO WORLD");
    display.setFont();
    display.setCursor(10, 90);
    display.print("E-Paper Test");
    display.setTextColor(GxEPD_YELLOW);
    display.setCursor(10, 105);
    display.print("Status: SUCCESS");
    display.drawRect(2, 35, display.width() - 4,
                     display.height() - 38, GxEPD_BLACK);
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
```

## Compile and upload from a local CLI

Install **Arduino CLI**, then run in PowerShell (adjust `COM5` to the port on your machine):

```powershell
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install GxEPD2 "Adafruit GFX Library"
arduino-cli board list
```

Create a directory named `ESP32_EPaper_Test`, save the sketch above inside it as `ESP32_EPaper_Test.ino`, then:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 ESP32_EPaper_Test
arduino-cli upload -p COM5 --fqbn esp32:esp32:esp32 ESP32_EPaper_Test
arduino-cli monitor -p COM5 -c baudrate=115200
```

If uploading stalls at `Connecting...`, hold **BOOT** until the upload starts. Close Serial Monitor before uploading if the port is busy.

## Expected serial diagnostics

```text
ESP32 E-PAPER TEST
Initializing E-Paper...
Drawing test screen...
Display update command completed
```

The display should show a red header, **HELLO WORLD**, **E-Paper Test**, and a yellow **Status: SUCCESS** line. A few screen flashes during refresh are normal.

## Troubleshooting

| Symptom | Check |
|---|---|
| No COM port | USB data cable, Windows USB-to-UART driver, USB connection |
| Upload fails | COM port, ESP32 Dev Module profile, BOOT button |
| Blank screen | 3V3/GND, MOSI/SCK, CS/DC/RST/BUSY |
| Stuck busy / "Busy Timeout!" in serial log | Wrong driver class selected (confirm `GxEPD2_290c_GDEY029F51H` is in use, not a `GxEPD2_BW` driver) |
| Garbled image | Incorrect geometry or rotation |
