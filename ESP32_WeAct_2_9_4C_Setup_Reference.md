# ESP32 + WeAct Studio 2.9-inch 4C E-Paper: Working Setup Reference

**Record date:** 12 October 2026 (Dubai)  
**Status:** Confirmed working. The display correctly renders `ESP32 TEST`, `HELLO WORLD`, `E-Paper Test`, and a yellow `Status: SUCCESS` line, with no wiring or layout issues, using the driver and sketch in this repository.  
**Purpose:** Reproduce the installation, wiring, and display test on a Windows PC, including use with a local CLI coding assistant.

> This document originally recorded an in-progress setup where the exact panel driver had not yet been confirmed. That has since been resolved — see [`README.md`](README.md) and [`ESP32_WeAct_2.9_EPaper.md`](ESP32_WeAct_2.9_EPaper.md) for the confirmed driver, sketch, and build/upload scripts (`upload.bat`, `push.bat`). This file is kept as a setup/verification reference.

## 1. Hardware inventory

| Component | Identification | Evidence |
|---|---|---|
| Controller | ESP32-WROOM-32 development board, USB-C | Photos of the board |
| Display | WeAct Studio **2.9-inch 4C** E-Paper Module | Original packaging label |
| Resolution | **168 × 384** pixels | Printed on display PCB |
| Communication | 4-wire SPI (`SDA`=MOSI, `SCL`=SCK) | Printed on display PCB |
| Power | 3.3 V logic; use ESP32 `3V3` supply | Display PCB markings |
| Cable | Eight-wire connector, Dupont ends | Photographs |
| Development host | Windows, Arduino IDE / Arduino CLI | Original setup workflow |

**4C** denotes a four-color panel. The photograph shows a red header, dark text and pale/yellowish text. Do not assume an RGB full-color panel. Confirm the exact four supported pigments and controller from the manufacturer's documentation before implementing color rendering.

## 2. Correct wiring: ESP32 board photographed by the user

These are the **actual wire colors at the display's 8-pin connector**, not generic wire color suggestions. Match the silkscreen labels, because cable colors can vary between batches.

| Cable color | E-Paper signal | ESP32 board label | GPIO in code |
|---|---|---|---|
| Purple | BUSY | D4 | 4 |
| Orange | RES (reset) | D26 | 26 |
| White | D/C (data/command) | D25 | 25 |
| Blue | CS (chip select) | D5 | 5 |
| Green | SCL (SPI clock) | D18 | 18 |
| Yellow | SDA (SPI MOSI) | D23 | 23 |
| Black | GND | GND | Ground |
| Red | VCC | 3V3 | 3.3 V supply |

**Pin 1 → Pin 8 on the E-Paper connector:** `BUSY, RES, D/C, CS, SCL, SDA, GND, VCC`. The printed board diagram and connector orientation take precedence over a generated illustration.

**Why D25/D26?** The actual ESP32 development board photograph clearly labels D25 and D26; earlier generated diagrams mistakenly referred to D16 and D17, which are not exposed/labeled on this board. The final *planned* configuration uses **D/C=D25 and RES=D26**. To reproduce the currently running firmware exactly, verify these assignments against its saved source.

**Safety:** Disconnect USB power before moving wires. Connect the display's VCC to **3V3**, never VIN or 5V for this setup. Avoid loose connections and exposed jumper ends shorting adjacent pins.

## 3. Visual record of the successful test

Photos of the working display, connector, cable, and packaging label were used during setup to confirm wiring and the "2.9 inch 4C" product label, but are not included in this repository.

## 4. Windows development setup

1. Install **Arduino IDE**: https://www.arduino.cc/en/software
2. In **File → Preferences → Additional Boards Manager URLs**, add:

   ```text
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```

3. In **Boards Manager**, install `esp32` by **Espressif Systems**.
4. Select **ESP32 Dev Module** under **Tools → Board**.
5. Install libraries using **Library Manager**:
   - `GxEPD2` by Jean-Marc Zingg
   - `Adafruit GFX Library` by Adafruit
6. Connect the ESP32 using a **data-capable USB-C cable**, select the Windows COM port, and set Serial Monitor to **115200 baud**.
7. Save a copy of the **known-good sketch**, including its panel driver class and library versions, before changing anything.

### GPIO constants for a fresh sketch

```cpp
#include <SPI.h>
#define EPD_BUSY  4
#define EPD_RST   26
#define EPD_DC    25
#define EPD_CS    5
#define EPD_SCK   18
#define EPD_MOSI  23

void setup() {
  Serial.begin(115200);
  SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  Serial.println("ESP32 SPI initialized");
  // Initialize the EXACT 2.9-inch 4C panel driver here.
}

void loop() {}
```

**This is a safe starting-point configuration, not a complete E-Paper rendering sketch.** The correct driver for this panel is confirmed: `GxEPD2_290c_GDEY029F51H` (via `GxEPD2_4C.h`), not the black/white `GxEPD2_290_T94_V2` class tried earlier, which caused "Busy Timeout!" errors on this hardware. See `ESP32_EPaper_Test/ESP32_EPaper_Test.ino` for the complete working sketch.

## 5. Arduino CLI: repeatable build and upload

Install Arduino CLI from https://arduino.github.io/arduino-cli/latest/installation/ and open PowerShell.

```powershell
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install GxEPD2
arduino-cli lib install "Adafruit GFX Library"
arduino-cli board list
```

Once the correct four-color sketch is saved as `EPaperTest/EPaperTest.ino`, and `arduino-cli board list` shows the ESP32 port:

```powershell
# Replace COM5 with the port detected on your own PC.
arduino-cli compile --fqbn esp32:esp32:esp32 .\EPaperTest
arduino-cli upload -p COM5 --fqbn esp32:esp32:esp32 .\EPaperTest
arduino-cli monitor -p COM5 -c baudrate=115200
```

If uploading stalls at `Connecting...`, hold **BOOT** during connection and release once the upload begins. The display may flash during a normal E-Paper full refresh.

## 6. Reinstallation verification checklist

- [ ] Confirm packaging: **WeAct Studio 2.9 inch 4C**, display PCB **168×384**.
- [ ] Power unplugged while wiring.
- [ ] Confirm all eight signals by **connector silkscreen**, not cable color alone.
- [ ] Confirm `VCC→3V3` and `GND→GND`.
- [ ] Confirm `SDA→D23`, `SCL→D18`, `CS→D5`.
- [x] Confirm `D/C→D25`, `RES→D26`, `BUSY→D4` for the documented GPIO plan.
- [x] Confirm the **actual working sketch** uses the same GPIO definitions.
- [x] Record the exact **4C panel driver class** and library versions — `GxEPD2_290c_GDEY029F51H`, see section 8.
- [x] Select **ESP32 Dev Module**, correct COM port and upload.
- [x] Verify `ESP32 TEST`, `HELLO WORLD`, and status text appear.
- [x] Source is saved in this repository (`ESP32_EPaper_Test/ESP32_EPaper_Test.ino`).

## 7. Troubleshooting

| Symptom | Check |
|---|---|
| No COM port | USB-C data cable, Windows USB serial driver, Device Manager |
| Upload stuck | Correct COM port, BOOT button, cable, board selection |
| ESP32 powered but screen blank | VCC/GND, CS/SCK/MOSI, D/C/RES/BUSY, correct **4C** panel driver |
| Image corrupted or colors wrong | Exact panel driver and color-plane handling |
| BUSY timeout | BUSY wiring, power stability, driver mismatch |
| Works intermittently | Loose Dupont leads, exposed pins, inadequate connections |
| Old image remains after unplugging | **Normal E-Paper behavior**: image is retained without power |

## 8. Confirmed configuration facts

```text
Sketch / repository:             this repo, ESP32_EPaper_Test/ESP32_EPaper_Test.ino
Arduino ESP32 core version:      esp32:esp32 3.3.12
GxEPD2 version:                  1.6.9
Adafruit GFX version:            1.12.6
Exact panel controller:          JD79667
Exact display driver class:      GxEPD2_290c_GDEY029F51H (via GxEPD2_4C.h)
D/C GPIO in working code:        25
RESET GPIO in working code:      26
BUSY GPIO in working code:       4
CS / SCK / MOSI GPIO:            5 / 18 / 23
Windows COM port (varies by PC): COM3 on the machine this was verified on
Four pigments supported:         Black, White, Red, Yellow
```

## 9. Reproducing this setup on another machine

> This is a **WeAct Studio 2.9-inch 4C, 168×384** panel, controller JD79667. Use `GxEPD2_4C.h` with driver class `GxEPD2_290c_GDEY029F51H` — not a generic monochrome 2.9-inch driver. The working sketch is `ESP32_EPaper_Test/ESP32_EPaper_Test.ino` in this repository; run `upload.bat [COMx]` to compile and flash it (it installs the ESP32 core and required libraries on first run).

---

**Bottom line:** Hardware output and driver are both confirmed. The working sketch, GPIO mapping, and exact 4-color driver are saved in this repository.
