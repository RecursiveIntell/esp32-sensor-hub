# ESP32 physical AI endpoint receipt work — 2026-07-01

Project: `/home/sikmindz/projects/esp32-sensor-hub`

## What shipped

Added the missing proof/receipt plumbing from the high-ROI plan.

### Firmware

`src/main.cpp` now emits a `proof` object in every sensor JSON payload:

- `schema`: `ri_esp_proof_receipt_v1`
- `event_id`: monotonic device-local counter
- `device_id`
- `timestamp_ms`
- `decision`: `local_only` or `forward_to_ai`
- `reason` / `route_reason`
- `sentinel_confidence`
- `ai_route`
- sensor snapshot

Route reasons implemented:

- `sensor_missing`
- `operator_request`
- `humidity_out_of_range`
- `temperature_out_of_range`
- `low_confidence`
- `anomaly_match`
- `schedule_tick`
- `local_confident`

The firmware already had the multi-sensor `sensors` object and Gemma/Ollama chat payload. This pass makes the route decision/proof explicit in the payload instead of relying on prose.

### Host receiver

`tools/sensor_receiver.py` now writes:

- raw readings: `sensor_readings.jsonl`
- normalized proof receipts: `esp32_receipts.jsonl`

New route:

- `GET /latest_receipt`

### AI endpoint

`tools/ai_infer_gemma_ollama.py` now writes AI receipts to:

- `ai_receipts.jsonl`

Receipt includes model, backend, elapsed time, device id, proof object, sensor context, response, and token counts.

### Semantic-memory ingester

New script:

- `tools/ingest_receipts_semantic.py`

Default dry-run prints fact text. Use `--post` to send selected receipts to semantic-memory HTTP `/add`, namespace `esp32-sensors`.

Example verified dry-run output:

```text
ESP32 sensor receipt: device=esp32-test observed_ms=123 decision=forward_to_ai reason=operator_request confidence=0.42 temp_c=29.5 humidity_pct=71 status=ok received_unix=1.
```

## Verification

Commands run:

```bash
cd /home/sikmindz/projects/esp32-sensor-hub
. .venv/bin/activate
python -m unittest discover -s tests -v
pio run -e esp32s3
```

Results:

- Python tests: 3 passed
- PlatformIO ESP32-S3 build: success
- Firmware size: RAM 46,900 / 327,680 bytes (14.3%); Flash 978,349 / 3,342,336 bytes (29.3%)

Reusable proof crate checks:

```bash
cd /home/sikmindz/projects/esp32-reusable
cargo test -p ri-esp-proof
source ~/export-esp.sh
cargo +esp check -p ri-esp-proof --target xtensa-esp32s3-none-elf -Z build-std=core,alloc
```

Results:

- ri-esp-proof host tests: 6 passed
- ESP32-S3 no_std target check: passed

## Claim boundary

Safe now:

- The ESP32/S3 sensor hub payloads include route/proof receipts.
- Host receiver logs receipt JSONL.
- Gemma/Ollama endpoint logs AI receipt JSONL.
- There is a dry-run/POST ingester path for semantic-memory promotion.
- ESP32-S3 firmware still builds with the added receipt payload.

Still not claimed:

- Live Gemma response from the currently connected ESP32 after this exact firmware build. Build verified, but I did not reflash sensor-hub firmware and hit `/ai` in this pass.
- Semantic-memory query answering over real humidity history; ingester path exists and dry-run was verified, but no live batch was posted in this pass.
