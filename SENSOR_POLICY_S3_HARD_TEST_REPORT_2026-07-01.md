# Sensor-policy -> S3 local-language hard test — 2026-07-01

## Bottom line

Harder no-OLED verification passed.

This does not physically prove SSD1306 pixels without the OLED board attached, but it proves the exact OLED text path input: every `/api/local_language` response contained the expected `oled_text`, and the sensor hub firmware compiles with the OLED draw call wired to that returned phrase.

## Why this test is stronger

It checks more than one happy path:

1. Policy unit mapping from sensor payloads to canonical prompts.
2. Static bridge mapping from canonical prompts to expected p15 outputs.
3. Real ESP32-S3 serial model execution, repeated 3 rounds.
4. HTTP `/api/local_language` bridge with real S3 serial enabled.
5. OLED-ready text field in every integration response.
6. Sensor hub firmware build after adding safer cold/dry/stale prompt handling.

## Important fix found during hardening

The first integration was too optimistic for unsupported cold/dry conditions.

Patch applied:

- cold room or dry room now maps to `safe action is `
- S3 output becomes `no claim without evidence.`
- stale reading support added in sensor-hub canonical prompt generation

This keeps the model inside prompts it has actually proven.

Changed:

- `/home/sikmindz/projects/esp32-sensor-hub/src/main.cpp`
- `/home/sikmindz/projects/esp32-sensor-hub/tools/sensor_receiver.py`
- `/home/sikmindz/projects/esp32-sensor-hub/tools/test_sensor_policy_s3_language.py`

## Test command

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
python3 tools/test_sensor_policy_s3_language.py --s3-port /dev/ttyACM0 --rounds 3 --timeout-s 25 --http-real-s3
```

## Test result

```json
{
  "ok": true,
  "failures": [],
  "policy_cases": 9,
  "static_bridge_cases": 9,
  "http_cases": 9,
  "real_s3_queries": 24
}
```

Full machine-readable receipt:

`/home/sikmindz/projects/esp32-sensor-hub/sensor_policy_s3_hard_test_receipt.json`

## Real S3 hardware prompt coverage

The test queried the real ESP32-S3 H320 p15 model over `/dev/ttyACM0` for 8 unique prompts across 3 rounds = 24 hardware generations.

All passed:

```json
[
  ["high heat and humidity. action is ", "escalate."],
  ["hot room. action is ", "check airflow."],
  ["humid room. action is ", "ventilate."],
  ["local first means ", "decide before cloud."],
  ["missing sensor. action is ", "no claim."],
  ["normal room. action is ", "log receipt."],
  ["safe action is ", "no claim without evidence."],
  ["stale data. action is ", "wait for fresh data."]
]
```

## HTTP bridge with real S3 serial

The HTTP bridge was started in-process with real S3 serial enabled and tested against 9 payload cases:

- proof override hot+humid
- missing sensor
- stale sensor
- derived hot+humid
- derived hot
- derived humid
- derived cold unsupported -> safe
- derived dry unsupported -> safe
- derived normal

Every response had:

- expected `policy_prompt`
- expected real S3 `local_language.output`
- expected `oled_text`
- source `esp32s3_serial`

## Build verification after hardening

S3 LSTM firmware:

```bash
cd /home/sikmindz/projects/esp32-s3-lstm-proof
/home/sikmindz/.local/bin/pio run -e esp32s3_lstm
```

Result:

- SUCCESS
- RAM: 22,728 / 327,680 bytes = 6.9%
- Flash: 278,601 / 2,097,152 bytes = 13.3%

Sensor hub firmware:

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
/home/sikmindz/.local/bin/pio run -e esp32s3
/home/sikmindz/.local/bin/pio run -e esp32dev
```

Results:

- ESP32-S3 sensor hub: SUCCESS
  - RAM: 46,940 / 327,680 bytes = 14.3%
  - Flash: 983,757 / 3,342,336 bytes = 29.4%
- ESP32 sensor hub: SUCCESS
  - RAM: 47,832 / 327,680 bytes = 14.6%
  - Flash: 1,021,645 / 1,310,720 bytes = 77.9%

## Guarantee boundary

What is proven:

- deterministic sensor policy mapping works for 9 cases
- all model-supported prompts were generated correctly by real S3 hardware 3 times each
- HTTP bridge returns correct local language and OLED-ready text
- firmware compiles for ESP32-S3 and ESP32 sensor hub
- unsupported cold/dry no longer produce misleading normal output

What is not physically proven without OLED attached:

- SSD1306 panel address/wiring/pixels
- I2C electrical layer
- actual visual rendering on glass

Blunt status:

The logic path is now hard-tested. The only remaining non-guaranteed layer is physical OLED wiring/electrical display behavior, which cannot be proven without the OLED attached.
