@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem =============================================================================
rem Lalit Stock Application - interactive ESP32 flashing wizard (Windows)
rem Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973
rem Disclaimer: informational software only, NOT financial advice.
rem
rem Asks for the E-Paper module, what to flash and the serial port, then runs
rem firmware\flash.bat (Lalit Stock firmware) or upload.bat (display test).
rem Non-interactive equivalents:  firmware\flash.bat COM3 420_bwr   /   upload.bat COM3 420_bwr
rem =============================================================================

set "ARDUINO_CLI=arduino-cli"
where arduino-cli >nul 2>&1
if errorlevel 1 set "ARDUINO_CLI=%LOCALAPPDATA%\arduino-cli\arduino-cli.exe"
if not exist "%ARDUINO_CLI%" if not "%ARDUINO_CLI%"=="arduino-cli" (
    echo arduino-cli was not found on PATH or at %LOCALAPPDATA%\arduino-cli\arduino-cli.exe
    echo Install it from https://arduino.github.io/arduino-cli/latest/installation/
    exit /b 1
)

echo.
echo ==================================================================
echo   Lalit Stock Application - ESP32 flashing wizard
echo   Informational display only. Not financial advice.
echo ==================================================================
echo.
echo Step 1/3 - Which E-Paper module is connected to the ESP32?
echo.
echo   1. WeAct 2.9in 4-colour       168 x 384 portrait    GDEY029F51H / JD79667  [hardware-verified]
echo   2. WeAct 4.2in black/white    400 x 300 landscape   GDEY042T81 / SSD1683   fast refresh, ~32 s pages
echo   3. WeAct 4.2in black/white/red 400 x 300 landscape  GDEY042Z98 / SSD1683   ~60 s pages
echo   4. WeAct 4.2in 4-colour       400 x 300 landscape   GDEY0420F51 / HX8717   ~66 s pages
echo.
echo   The module type is printed on the flex cable or the WeAct product page.
echo.
set "TRIES=0"
:ask_panel
set "SEL="
set /p "SEL=Select module [1-4, default 1]: "
if "%SEL%"=="" set "SEL=1"
if "%SEL%"=="1" (set "PANEL=290_4c" & set "PANEL_NAME=WeAct 2.9in 4-colour, 168x384")
if "%SEL%"=="2" (set "PANEL=420_bw" & set "PANEL_NAME=WeAct 4.2in black/white, 400x300")
if "%SEL%"=="3" (set "PANEL=420_bwr" & set "PANEL_NAME=WeAct 4.2in black/white/red, 400x300")
if "%SEL%"=="4" (set "PANEL=420_4c" & set "PANEL_NAME=WeAct 4.2in 4-colour, 400x300")
if not defined PANEL (
    echo   Please enter 1, 2, 3 or 4.
    call :retry || exit /b 2
    goto ask_panel
)

echo.
echo Step 2/3 - What do you want to flash?
echo.
echo   1. Lalit Stock firmware        normal use: setup portal, portfolio pages, admin page
echo   2. Display test (Hello World)  recommended first on a new module: checks wiring and driver
echo.
:ask_what
set "WHAT="
set /p "WHAT=Select [1-2, default 1]: "
if "%WHAT%"=="" set "WHAT=1"
if "%WHAT%"=="1" (set "SCRIPT=firmware\flash.bat" & set "WHAT_NAME=Lalit Stock firmware")
if "%WHAT%"=="2" (set "SCRIPT=upload.bat" & set "WHAT_NAME=Display test (Hello World)")
if not defined SCRIPT (
    echo   Please enter 1 or 2.
    call :retry || exit /b 2
    goto ask_what
)

echo.
echo Step 3/3 - Which serial port is the ESP32 on?
echo.
set "N=0"
set "PORTS_FILE=%TEMP%\lalitstock_ports.txt"
"%ARDUINO_CLI%" board list <nul >"%PORTS_FILE%" 2>nul
for /f "usebackq tokens=1,*" %%A in (`findstr /r /b /c:"COM[0-9]" "%PORTS_FILE%"`) do (
    set /a N+=1
    set "PORT_!N!=%%A"
    echo   !N!. %%A  %%B
)
del "%PORTS_FILE%" >nul 2>&1
if "%N%"=="0" echo   No serial ports detected. Plug in the ESP32 USB cable, or type the port name, e.g. COM3.
echo.
:ask_port
set "PICK="
set "PORT="
if "%N%"=="1" (
    set /p "PICK=Select port [1-%N% or a name like COM5, default 1]: "
    if "!PICK!"=="" set "PICK=1"
) else (
    set /p "PICK=Select port [1-%N% or a name like COM5]: "
)
if "%PICK%"=="" (
    call :retry || exit /b 2
    goto ask_port
)
if defined PORT_%PICK% (set "PORT=!PORT_%PICK%!") else (set "PORT=%PICK%")
echo %PORT%| findstr /r /i /b /c:"COM[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo   "%PORT%" is not a COM port. Enter a number from the list or a name like COM3.
    call :retry || exit /b 2
    goto ask_port
)

echo.
echo ------------------------------------------------------------------
echo   Module : %PANEL_NAME%   (build %PANEL%)
echo   Flash  : %WHAT_NAME%
echo   Port   : %PORT%
echo ------------------------------------------------------------------
echo   Close any serial monitor using %PORT%. If upload stalls at "Connecting...",
echo   hold the BOOT button on the ESP32 until it starts.
echo.
set "GO="
set /p "GO=Proceed? [Y/n]: "
if /i "%GO%"=="n" (
    echo Cancelled. Nothing was flashed.
    exit /b 0
)
if /i "%GO%"=="no" (
    echo Cancelled. Nothing was flashed.
    exit /b 0
)

call %SCRIPT% %PORT% %PANEL%
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo Flashing failed with exit code %RC%.
    exit /b %RC%
)
if "%WHAT%"=="2" (
    echo.
    echo If the screen shows HELLO WORLD, run this wizard again and choose the Lalit Stock firmware.
)
endlocal
exit /b 0

:retry
set /a TRIES+=1
if %TRIES% geq 5 (
    echo Too many invalid answers; nothing was flashed.
    exit /b 1
)
exit /b 0
