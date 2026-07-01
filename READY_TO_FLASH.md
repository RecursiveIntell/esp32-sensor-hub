# ESP32 temp/humidity + OLED + Gemma4 flash readiness

Date: 2026-06-30

## Voltage reality

Both regular ESP32 and ESP32-S3 GPIO are 3.3V logic.

A typical 1 inch SSD1306 I2C OLED usually works from 3.3V and is safe on ESP32/S3. Some OLED breakout boards accept 5V power because they include a regulator, but the I2C pullups may still be tied to VCC. If VCC is 5V and the board pulls SDA/SCL to 5V, that is unsafe for ESP32 and ESP32-S3 GPIO.

Safe wiring order:

1. Try OLED VCC at 3.3V first.
2. If OLED only works at 5V, use a bidirectional I2C level shifter or make sure SDA/SCL pullups go to 3.3V, not 5V.
3. Switching from ESP32 to ESP32-S3 does not magically make 5V I2C safe; S3 is also 3.3V logic. The S3 is still preferred here because it is the better future target and we have known safe I2C pins.

## Built firmware targets

Project:

- `/home/sikmindz/projects/esp32-sensor-hub`

Regular ESP32 target:

- PlatformIO env: `esp32dev`
- Detected port: `/dev/ttyUSB0`
- Detected chip: ESP32-D0WDQ6
- MAC: `c8:c9:a3:d6:2a:18`
- binary: `/home/sikmindz/projects/esp32-sensor-hub/.pio/build/esp32dev/firmware.bin`

ESP32-S3 target:

- PlatformIO env: `esp32s3`
- Board profile: `freenove_esp32_s3_wroom` (8MB Flash / 8MB PSRAM profile)
- Detected port: `/dev/ttyACM0`
- Detected chip: ESP32-S3 QFN56, embedded PSRAM 8MB
- MAC: `94:a9:90:d2:41:f4`
- binary: `/home/sikmindz/projects/esp32-sensor-hub/.pio/build/esp32s3/firmware.bin`

## Wiring expected by current config

Regular ESP32 (`esp32dev`):

OLED SSD1306 I2C:

- VCC -> 3.3V first. Use level shifter if VCC must be 5V.
- GND -> GND
- SDA -> GPIO21
- SCL -> GPIO22
- address -> `0x3C`
- size -> `128x64`

DHT:

- DATA -> GPIO4
- VCC -> 3.3V
- GND -> GND
- type -> `DHT22` currently

ESP32-S3 (`esp32s3`):

OLED SSD1306 I2C:

- VCC -> 3.3V first. Use level shifter if VCC must be 5V.
- GND -> GND
- SDA -> GPIO21
- SCL -> GPIO47
- address -> `0x3C`
- size -> `128x64`

DHT:

- DATA -> GPIO4
- VCC -> 3.3V
- GND -> GND
- type -> `DHT22` currently

S3 note: do not use GPIO8/GPIO9 for I2C on N16R8/N8R8-style modules; those are commonly tied to octal PSRAM.

## Network / AI config

Current config file:

- `/home/sikmindz/projects/esp32-sensor-hub/include/config.h`

Current settings:

- WiFi SSID: `purplemama`
- primary/secondary passwords configured
- sensor receiver: `http://192.168.50.181:8088/api/sensor`
- Gemma final JSON endpoint: `http://192.168.50.69:8090/infer`
- Gemma streaming OLED endpoint: `http://192.168.50.69:8090/infer_stream`
- automatic AI interval: `300000 ms` = 5 minutes
- stream max time: `120000 ms` = 2 minutes

## Behavior after flash

On boot:

1. Initializes OLED.
2. Connects to `purplemama` using primary then secondary password.
3. Starts HTTP server on port 80.
4. Reads DHT sensor.
5. Displays device/WiFi/IP/RSSI/heap/temp/humidity/heat-index/post/AI status.
6. Posts sensor JSON to the receiver every `POST_MS`.
7. Every `AI_INTERVAL_MS`, sends rich sensor/device context to GTX Gemma4 via `/infer_stream`.
8. Writes incoming Gemma text to OLED while tokens arrive.

Manual ESP32 routes:

- `GET /status`
- `GET /sensors`
- `POST /ai`
- `POST /ai/stream`

## GTX/Gemma endpoint

On the GTX 1070 machine, run:

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
OLLAMA_MODEL=gemma4:12b tools/run_gemma_ai.sh
```

Health:

```bash
curl http://127.0.0.1:8090/health
```

Streaming route test from any LAN box that can reach it:

```bash
curl -N -X POST http://192.168.50.69:8090/infer_stream \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"manual-test","temperature_c":25.2,"humidity_pct":70,"heat_index_c":26,"status":"ok"}'
```

## Flash commands

Regular ESP32 on `/dev/ttyUSB0`:

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
. .venv/bin/activate
pio run -e esp32dev -t upload --upload-port /dev/ttyUSB0
```

ESP32-S3 on `/dev/ttyACM0`:

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
. .venv/bin/activate
pio run -e esp32s3 -t upload --upload-port /dev/ttyACM0
```

Helper script:

```bash
tools/flash.sh esp32dev /dev/ttyUSB0
tools/flash.sh esp32s3 /dev/ttyACM0
```

Monitor:

```bash
pio device monitor -p /dev/ttyUSB0 -b 115200
pio device monitor -p /dev/ttyACM0 -b 115200
```

## Verification already run

- `python3 -m py_compile tools/ai_infer_gemma_ollama.py tests/test_ai_infer_gemma_ollama.py` passed.
- `python3 -m unittest discover -s tests -p 'test_*.py' -v` passed: 3 tests.
- `pio run -e esp32dev` passed.
- `pio run -e esp32s3` passed.
- Fake-Ollama `/infer_stream` integration test passed and emitted: `Temp looks stable. Humidity is high.`
- `pio device list` found `/dev/ttyUSB0` and `/dev/ttyACM0`.
- esptool identified `/dev/ttyUSB0` as ESP32 and `/dev/ttyACM0` as ESP32-S3.

## Claim boundary

Ready to flash either target now.

Not yet verified on physical OLED/DHT after this code change until flashed and observed over serial/OLED.
