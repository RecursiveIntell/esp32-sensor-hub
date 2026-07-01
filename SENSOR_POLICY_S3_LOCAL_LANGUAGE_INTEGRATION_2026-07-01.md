# Sensor-policy -> ESP32-S3 local-language integration — 2026-07-01

## Bottom line

Implemented and hardware-verified the next ROI step:

sensor reading/proof -> deterministic canonical policy prompt -> ESP32-S3 H320 p15 local language -> receipt -> OLED-ready phrase.

This keeps the correct boundary: policy is deterministic; the S3 model only phrases the already-decided local status/action.

## Changed files

Sensor hub:

- `/home/sikmindz/projects/esp32-sensor-hub/src/main.cpp`
- `/home/sikmindz/projects/esp32-sensor-hub/tools/sensor_receiver.py`
- `/home/sikmindz/projects/esp32-sensor-hub/include/config.h`
- `/home/sikmindz/projects/esp32-sensor-hub/include/config.h.example`

S3 LSTM firmware:

- `/home/sikmindz/projects/esp32-s3-lstm-proof/src/main.cpp`

## Sensor hub changes

Firmware now adds local-language routing fields to each proof receipt:

- `proof.local_language_model = "esp32s3_h320_p15"`
- `proof.local_language_prompt = <canonical prompt>`

Canonical prompt mapping:

- missing sensor -> `missing sensor. action is `
- hot + humid -> `high heat and humidity. action is `
- hot -> `hot room. action is `
- humid -> `humid room. action is `
- otherwise -> `normal room. action is `

Firmware now POSTs each reading to:

`LOCAL_LANGUAGE_URL = http://192.168.50.181:8088/api/local_language`

and displays the returned local phrase on the SSD1306 OLED with title:

`S3 local language`

Status screen now shows:

- POST code
- S3/local-language code
- latest S3 phrase

## Receiver changes

`tools/sensor_receiver.py` now exposes:

- `GET /health`
- `GET /latest`
- `GET /latest_receipt`
- `GET /latest_local_language`
- `POST /api/sensor`
- `POST /api/local_language`

Run without real S3 serial for deterministic host lookup:

```bash
python3 tools/sensor_receiver.py --host 0.0.0.0 --port 8088
```

Run with real ESP32-S3 local model over serial:

```bash
python3 tools/sensor_receiver.py --host 0.0.0.0 --port 8088 --s3-port /dev/ttyACM0 --s3-timeout-s 15
```

Receipt files:

- raw readings: `/home/sikmindz/projects/esp32-sensor-hub/sensor_readings.jsonl`
- sensor proofs: `/home/sikmindz/projects/esp32-sensor-hub/esp32_receipts.jsonl`
- S3 local-language receipts: `/home/sikmindz/projects/esp32-sensor-hub/esp32_s3_local_language_receipts.jsonl`
- full integration receipts: `/home/sikmindz/projects/esp32-sensor-hub/sensor_policy_s3_language_receipts.jsonl`

## S3 LSTM firmware changes

The S3 firmware still runs the p15 benchmark receipt at boot.

It now also accepts serial prompt commands after boot:

```text
PROMPT:<canonical prompt>
```

Example:

```text
PROMPT:high heat and humidity. action is 
```

It returns:

```text
S3_LANGUAGE_RECEIPT {...}
```

Receipt schema:

`ri_esp32s3_local_language_v1`

Fields include:

- firmware variant
- weights SHA256
- model profile
- prompt
- generated output
- generated chars
- elapsed ms
- chars/sec
- stop rule
- passed

## Verification receipts

### 1. S3 LSTM firmware build

Command:

```bash
/home/sikmindz/.local/bin/pio run -e esp32s3_lstm
```

Result:

- SUCCESS
- RAM: 22,728 / 327,680 bytes = 6.9%
- Flash app: 278,601 / 2,097,152 bytes = 13.3%

### 2. Sensor hub firmware builds

Command:

```bash
/home/sikmindz/.local/bin/pio run -e esp32s3
/home/sikmindz/.local/bin/pio run -e esp32dev
```

Results:

- ESP32-S3 sensor hub: SUCCESS
  - RAM: 46,940 / 327,680 bytes = 14.3%
  - Flash: 983,629 / 3,342,336 bytes = 29.4%
- ESP32 sensor hub: SUCCESS
  - RAM: 47,832 / 327,680 bytes = 14.6%
  - Flash: 1,021,529 / 1,310,720 bytes = 77.9%

### 3. S3 firmware flashed to hardware

Command:

```bash
/home/sikmindz/.local/bin/pio run -t upload --upload-port /dev/ttyACM0
```

Result:

- SUCCESS
- detected ESP32-S3 revision v0.2
- MAC: `94:a9:90:d2:41:f4`
- firmware image hash verified

### 4. Boot benchmark still works after serial-interface patch

Hardware boot emitted:

- firmware variant: `p15_curated_h320_stopped_utility`
- weights SHA256: `fb042c0aa011475e0a31d2c5d271dde57c504aa1bdcdb02ecd3ce0010ebf2b7a`
- 17.2043 tok/s
- 58.12 ms/token
- stopped output still includes:
  - `high heat and humidity. action is ` -> `escalate.`

### 5. Real S3 local-language command receipt

Command sent to `/dev/ttyACM0`:

```text
PROMPT:high heat and humidity. action is 
```

S3 returned:

```json
{
  "schema": "ri_esp32s3_local_language_v1",
  "firmware_variant": "p15_curated_h320_stopped_utility",
  "weights_sha256": "fb042c0aa011475e0a31d2c5d271dde57c504aa1bdcdb02ecd3ce0010ebf2b7a",
  "model_profile": "curated_status_h320_all_int8",
  "prompt": "high heat and humidity. action is ",
  "output": "escalate.",
  "generated_chars": 9,
  "elapsed_ms": 1883,
  "chars_per_sec": 4.7796,
  "stop_rule": "period_or_newline_or_48_chars",
  "passed": true
}
```

### 6. End-to-end receiver integration test with real S3 serial

Server:

```bash
python3 tools/sensor_receiver.py --host 127.0.0.1 --port 18088 --s3-port /dev/ttyACM0 --s3-timeout-s 15
```

Posted sample sensor proof:

- device: `test-esp32-node`
- temperature: 31.0 C / 87.8 F
- humidity: 72%
- route reason: `temperature_and_humidity_out_of_range`
- prompt: `high heat and humidity. action is `

Returned summary:

```json
{
  "ok": true,
  "prompt": "high heat and humidity. action is ",
  "output": "escalate.",
  "source": "esp32s3_serial",
  "passed": true,
  "elapsed_ms": 1883,
  "receipt_schema": "ri_sensor_policy_to_s3_language_integration_v1"
}
```

Integration receipt written to:

`/home/sikmindz/projects/esp32-sensor-hub/sensor_policy_s3_language_receipts.jsonl`

## Boundary

KEEP:

- deterministic sensor policy owns the decision
- S3 H320 p15 owns short local phrase generation
- receiver stores receipts
- OLED shows the local phrase

DO NOT claim:

- autonomous policy correctness by the model
- chatbot behavior
- generalized reasoning
- production readiness

This is now a physical AI endpoint demo path, not just a model benchmark.
