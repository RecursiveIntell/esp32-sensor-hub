# ESP32 Sensor Hub

Firmware + local receiver for an ESP32 that:

- connects to WiFi SSID `purplemama`
- reads a temp/humidity sensor
- displays live values on a 1 inch I2C OLED
- sends JSON sensor readings to a computer over HTTP
- exposes local ESP32 HTTP endpoints for status and AI forwarding
- periodically sends rich sensor/device context to the GTX 1070 Gemma4 endpoint
- streams the Gemma response back onto the OLED as text arrives
- is structured so more sensors can be added later without rewriting the whole sketch

## Assumed hardware

Default firmware target:

- ESP32 dev board: `esp32dev` PlatformIO target
- Temp/humidity sensor: DHT22 on GPIO4
- OLED: 1 inch SSD1306 I2C, 128x64, address 0x3C
- I2C pins: SDA GPIO21, SCL GPIO22

If the sensor is DHT11, change `DHT_TYPE` in `include/config.h`.
If the OLED is 128x32, change `OLED_HEIGHT` to 32.
If this is an ESP32-S3 N16R8 board, do NOT use GPIO8/9 for I2C; use safe pins like GPIO21 plus GPIO47 if exposed.

## Files

- `platformio.ini` - PlatformIO build config
- `include/config.h.example` - copy to `include/config.h`, add WiFi password and server IPs
- `src/main.cpp` - ESP32 firmware
- `tools/sensor_receiver.py` - local computer HTTP receiver for sensor readings
- `tools/ai_infer_stub.py` - simple fake AI endpoint for plumbing tests
- `tools/ai_infer_gemma_ollama.py` - real Ollama-backed AI endpoint, default model `gemma4:12b`
- `tools/run_gemma_ai.sh` - launches the Gemma/Ollama endpoint on port 8090
- `tools/check_gemma_ai.sh` - verifies Ollama and the configured model are reachable
- `tools/pull_gemma_model.sh` - pulls the configured Ollama model on the GTX box
- `tools/gemma_ai.env.example` - environment template for the Gemma endpoint
- `docs/architecture.md` - use cases and expansion plan
- `docs/wiring.md` - wiring notes

## Setup

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
cp include/config.h.example include/config.h
# edit include/config.h and set WIFI_PASSWORD plus the computer LAN IP
```

Install PlatformIO if needed:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install platformio
```

Build:

```bash
. .venv/bin/activate
pio run
```

Flash:

```bash
. .venv/bin/activate
pio run -t upload --upload-port /dev/ttyUSB0
# or /dev/ttyACM0 depending on board
```

Monitor:

```bash
pio device monitor -b 115200
```

## Run the receiver on the computer

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
python3 tools/sensor_receiver.py --host 0.0.0.0 --port 8088
```

Test from the computer:

```bash
curl -X POST http://127.0.0.1:8088/api/sensor \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"test","temperature_c":22.1,"humidity_pct":44.2}'
```

The ESP32 posts to `HUB_POST_URL` from `include/config.h`. I set the initial receiver to this machine's current LAN IP, `192.168.50.181:8088`, and the future GTX 1070 inference stub to `192.168.50.69:8090`.

## ESP32 local endpoints

Once booted, the serial monitor prints the ESP32 IP address.

- `GET /status` - current device/sensor/network status
- `GET /sensors` - latest sensor payload JSON
- `POST /ai` - forwards sensor context plus request JSON to `AI_INFER_URL`, waits for final JSON, and shows the response on OLED
- `POST /ai/stream` - forwards sensor context to `AI_STREAM_URL` and streams text back onto the OLED while Gemma generates it

The firmware also automatically calls `AI_STREAM_URL` every `AI_INTERVAL_MS` using `AI_PROMPT`, as long as WiFi and the sensor are healthy.

Example:

```bash
curl http://ESP32_IP/status
curl http://ESP32_IP/sensors
curl -X POST http://ESP32_IP/ai -H 'Content-Type: application/json' -d '{"prompt":"what does this room condition imply?"}'
curl -X POST http://ESP32_IP/ai/stream -H 'Content-Type: application/json' -d '{"prompt":"give a short OLED-ready room status"}'
```

## Gemma/Ollama AI endpoint

Default target model: `gemma4:12b` via Ollama on the GTX 1070 machine.

Run:

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
OLLAMA_MODEL=gemma4:12b tools/run_gemma_ai.sh
```

Health check:

```bash
curl http://127.0.0.1:8090/health
```

Test inference:

```bash
curl -X POST http://127.0.0.1:8090/infer \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"esp32-proof-01","temperature_c":29.5,"humidity_pct":71,"heat_index_c":31,"status":"ok","ai_request":{"raw_body":"{\"prompt\":\"Should I ventilate the room?\"}"}}'
```

Important: this machine currently has Ollama installed, but `gemma4:12b` must exist locally on the GTX box (`ollama list`) or be pulled before the endpoint can serve it.

Setup/check on the GTX box:

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
cp tools/gemma_ai.env.example .env
# optional: edit .env, then source it
set -a; . ./.env; set +a

tools/pull_gemma_model.sh
tools/check_gemma_ai.sh
```

Current local receipt from this machine: `ollama list` works, but `gemma4:12b` is not installed here; `gemma4:e2b` is installed and was used only for endpoint plumbing verification. `nvidia-smi` could not communicate with the NVIDIA driver in this environment, so GTX acceleration was not verified here.

## AI endpoint intent

The ESP32 should not run the real model. Path:

1. ESP32 collects live sensor context.
2. Computer/server with GTX 1070 runs inference.
3. Client asks ESP32 `/ai` or server directly.
4. ESP32 forwards the request plus latest sensor values to the GTX server.
5. GTX server returns result; ESP32 can display a short status on OLED and return JSON.
6. Every `AI_INTERVAL_MS`, ESP32 also calls `/infer_stream` and writes incoming Gemma text to the OLED while tokens arrive.

For the current configured target:

- `AI_INFER_URL`: `http://192.168.50.69:8090/infer`
- `AI_STREAM_URL`: `http://192.168.50.69:8090/infer_stream`
- default model on that server: `gemma4:12b`

This keeps the ESP32 as the physical-world sensor/edge endpoint and the GPU box as the inference backend.
