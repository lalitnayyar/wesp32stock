@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem Compiles and uploads ESP32_EPaper_Test to the ESP32 board, then opens the serial monitor.
rem Usage: upload.bat [COMx] [PANEL]   (defaults: COM3, 290_4c)
rem   PANEL  290_4c | 420_bw | 420_bwr | 420_4c   (WeAct 2.9in 4-colour, or WeAct 4.2in 400x300 variants)

set "FQBN=esp32:esp32:esp32"
set "SKETCH=ESP32_EPaper_Test"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=COM3"
set "PANEL=%~2"
if "%PANEL%"=="" set "PANEL=290_4c"
set "LS_PANEL="
if /i "%PANEL%"=="290_4c" set "LS_PANEL=LS_PANEL_290_4C"
if /i "%PANEL%"=="420_bw" set "LS_PANEL=LS_PANEL_420_BW"
if /i "%PANEL%"=="420_bwr" set "LS_PANEL=LS_PANEL_420_BWR"
if /i "%PANEL%"=="420_4c" set "LS_PANEL=LS_PANEL_420_4C"
if "%LS_PANEL%"=="" (
    echo Unknown panel "%PANEL%". Use 290_4c, 420_bw, 420_bwr or 420_4c.
    exit /b 2
)

set "ARDUINO_CLI=arduino-cli"
where arduino-cli >nul 2>&1
if errorlevel 1 set "ARDUINO_CLI=%LOCALAPPDATA%\arduino-cli\arduino-cli.exe"
if not exist "%ARDUINO_CLI%" if not "%ARDUINO_CLI%"=="arduino-cli" (
    echo arduino-cli was not found on PATH or at %LOCALAPPDATA%\arduino-cli\arduino-cli.exe
    echo Install it from https://arduino.github.io/arduino-cli/latest/installation/
    exit /b 1
)

echo Checking ESP32 board support...
"%ARDUINO_CLI%" core list | findstr /i "esp32:esp32" >nul 2>&1
if errorlevel 1 (
    echo Installing ESP32 board support - first-time setup...
    "%ARDUINO_CLI%" core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
    "%ARDUINO_CLI%" core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
)

echo Checking required libraries...
"%ARDUINO_CLI%" lib list | findstr /i "GxEPD2" >nul 2>&1
if errorlevel 1 (
    echo Installing GxEPD2 and Adafruit GFX Library - first-time setup...
    "%ARDUINO_CLI%" lib install GxEPD2 "Adafruit GFX Library"
)

echo.
echo Compiling %SKETCH% for %FQBN%, panel %PANEL%...
"%ARDUINO_CLI%" compile --fqbn %FQBN% --build-property "compiler.cpp.extra_flags=-DLS_PANEL=%LS_PANEL%" %SKETCH%
if errorlevel 1 (
    echo Compile failed.
    exit /b 1
)

echo.
echo Uploading to %PORT%...
"%ARDUINO_CLI%" upload -p %PORT% --fqbn %FQBN% %SKETCH%
if errorlevel 1 (
    echo Upload failed. If it stalls at "Connecting...", hold BOOT on the ESP32 until upload starts.
    echo Also make sure the Serial Monitor is closed so the port is free.
    exit /b 1
)

echo.
echo Upload complete. Opening serial monitor on %PORT% (Ctrl+C to exit)...
"%ARDUINO_CLI%" monitor -p %PORT% -c baudrate=115200

endlocal
