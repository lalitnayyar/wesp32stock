# Lalit Stock Application - ESP32 firmware builder for the web flasher (./manage.sh firmware).
# Owner: Lalit Nayyar <consult@lalit.cloud>. Not financial advice.
# Build context: deploy/ (for extra-ca). Pinned toolchain = the verified one: esp32 core 3.3.12,
# GxEPD2 1.6.9, Adafruit GFX 1.12.6, ArduinoJson 7.4.3. First build downloads about 1 GB.
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl python3 git bash \
 && rm -rf /var/lib/apt/lists/*

# Optional extra root CAs for TLS-inspecting networks (deploy/extra-ca/*.crt); verification stays on.
COPY extra-ca/ /usr/local/share/ca-certificates/extra/
RUN find /usr/local/share/ca-certificates/extra -type f ! -name '*.crt' -delete; update-ca-certificates

ENV ARDUINO_DIRECTORIES_DATA=/opt/arduino/data \
    ARDUINO_DIRECTORIES_USER=/opt/arduino/user \
    ARDUINO_DIRECTORIES_DOWNLOADS=/opt/arduino/staging \
    ARDUINO_BOARD_MANAGER_ADDITIONAL_URLS=https://espressif.github.io/arduino-esp32/package_esp32_index.json

RUN curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=/usr/local/bin sh \
 && arduino-cli core update-index \
 && arduino-cli core install esp32:esp32@3.3.12 \
 && arduino-cli lib install "GxEPD2@1.6.9" "Adafruit GFX Library@1.12.6" "ArduinoJson@7.4.3" \
 && rm -rf /opt/arduino/staging \
 && chmod -R a+rwX /opt/arduino

# The repository is mounted at /repo; builds run as the calling user (HOME=/tmp for caches).
WORKDIR /repo
CMD ["bash", "tools/build_firmware.sh"]
