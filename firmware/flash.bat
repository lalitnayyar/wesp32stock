@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem Lalit Stock Application - compile and flash the ESP32 E-Paper firmware, then open the serial monitor.
rem Owner: Lalit Nayyar. Not financial advice.
rem Usage: flash.bat [COMx]   (defaults to COM3)

set "FQBN=esp32:esp32:esp32:PartitionScheme=min_spiffs"
set "SKETCH=LalitStockFirmware"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=COM3"

set "ARDUINO_CLI=arduino-cli"
where arduino-cli >nul 2>&1
if errorlevel 1 set "ARDUINO_CLI=%LOCALAPPDATA%\arduino-cli\arduino-cli.exe"
if not exist "%ARDUINO_CLI%" if not "%ARDUINO_CLI%"=="arduino-cli" (
    echo arduino-cli was not found on PATH or at %LOCALAPPDATA%\arduino-cli\arduino-cli.exe
    exit /b 1
)

echo Checking ESP32 board support...
"%ARDUINO_CLI%" core list | findstr /i "esp32:esp32" >nul 2>&1
if errorlevel 1 (
    "%ARDUINO_CLI%" core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
    "%ARDUINO_CLI%" core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
)

echo Checking required libraries...
for %%L in ("GxEPD2" "Adafruit GFX Library" "ArduinoJson") do (
    "%ARDUINO_CLI%" lib list | findstr /i /c:%%L >nul 2>&1
    if errorlevel 1 "%ARDUINO_CLI%" lib install %%L
)

echo.
echo Compiling %SKETCH% for %FQBN%...
"%ARDUINO_CLI%" compile --fqbn %FQBN% %SKETCH%
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
