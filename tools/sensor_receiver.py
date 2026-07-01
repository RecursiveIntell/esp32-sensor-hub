#!/usr/bin/env python3
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sensor_readings.jsonl"
RECEIPTS = ROOT / "esp32_receipts.jsonl"
LOCAL_LANGUAGE_RECEIPTS = ROOT / "esp32_s3_local_language_receipts.jsonl"
INTEGRATION_RECEIPTS = ROOT / "sensor_policy_s3_language_receipts.jsonl"

CONTRACT_PATH = ROOT / "contracts" / "sensor_policy_s3_local_language_v1.json"

FALLBACK_CANONICAL_OUTPUTS = {
    "hot room. action is ": "check airflow.",
    "missing sensor. action is ": "no claim.",
    "stale data. action is ": "wait for fresh data.",
    "high heat and humidity. action is ": "escalate.",
    "humid room. action is ": "ventilate.",
    "normal room. action is ": "log receipt.",
    "safe action is ": "no claim without evidence.",
    "local first means ": "decide before cloud.",
}

def load_canonical_outputs(path: Path = CONTRACT_PATH) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        prompts = data.get("prompts", [])
        loaded = {row["prompt"]: row["output"] for row in prompts if isinstance(row, dict) and "prompt" in row and "output" in row}
        return loaded or dict(FALLBACK_CANONICAL_OUTPUTS)
    except Exception:
        return dict(FALLBACK_CANONICAL_OUTPUTS)

CANONICAL_OUTPUTS = load_canonical_outputs()

def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, separators=(",", ":"), sort_keys=True) + "\n")

def latest_jsonl(path: Path):
    if not path.exists():
        return None
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None

def receipt_from_payload(payload: dict, received_unix: float):
    proof = payload.get("proof")
    if not isinstance(proof, dict):
        return None
    return {
        "schema": "ri_esp_sensor_receipt_v1",
        "received_unix": received_unix,
        "device_id": payload.get("device_id") or proof.get("device_id"),
        "observed_ms": proof.get("timestamp_ms") or payload.get("uptime_ms"),
        "proof": proof,
        "sensors": payload.get("sensors", {}),
        "status": payload.get("status"),
        "wifi_rssi": payload.get("wifi_rssi"),
        "ip": payload.get("ip"),
    }

def _number(x):
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None

def canonical_policy_prompt(payload: dict) -> tuple[str, str]:
    proof = payload.get("proof") if isinstance(payload.get("proof"), dict) else {}
    prompt = proof.get("local_language_prompt")
    if isinstance(prompt, str) and prompt in CANONICAL_OUTPUTS:
        return prompt, "proof.local_language_prompt"

    status = payload.get("status")
    raw_sensors = payload.get("sensors")
    sensors = raw_sensors if isinstance(raw_sensors, dict) else {}
    raw_dht = sensors.get("dht")
    dht = raw_dht if isinstance(raw_dht, dict) else {}
    valid = dht.get("valid", payload.get("status") == "ok")
    temp_f = _number(payload.get("temperature_f"))
    humidity = _number(payload.get("humidity_pct"))
    if temp_f is None:
        temp_c = _number(payload.get("temperature_c"))
        if temp_c is None:
            temp_c = _number(dht.get("temperature_c"))
        if temp_c is not None:
            temp_f = temp_c * 9.0 / 5.0 + 32.0
    if humidity is None:
        humidity = _number(dht.get("humidity_pct"))

    if not valid or status == "sensor_read_failed" or temp_f is None or humidity is None:
        return "missing sensor. action is ", "derived.sensor_missing"

    age_ms = _number(dht.get("last_read_ms"))
    uptime = _number(payload.get("uptime_ms"))
    if age_ms is not None and uptime is not None and uptime > age_ms and (uptime - age_ms) > 120_000:
        return "stale data. action is ", "derived.stale_reading"

    hot = temp_f >= 82.0
    cold = temp_f <= 60.0
    humid = humidity >= 65.0
    dry = humidity <= 25.0
    if hot and humid:
        return "high heat and humidity. action is ", "derived.hot_humid"
    if hot:
        return "hot room. action is ", "derived.hot"
    if humid:
        return "humid room. action is ", "derived.humid"
    if cold or dry:
        return "safe action is ", "derived.unsupported_cold_or_dry"
    return "normal room. action is ", "derived.normal"

def parse_s3_receipt_line(line: str):
    marker = "S3_LANGUAGE_RECEIPT "
    if marker not in line:
        return None
    raw = line.split(marker, 1)[1].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None

def query_s3_serial(port: str, prompt: str, timeout_s: float, baud: int = 115200):
    import serial
    started = time.time()
    with serial.Serial(port, baud, timeout=0.2) as ser:
        ser.reset_input_buffer()
        ser.write(("PROMPT:" + prompt + "\n").encode("utf-8"))
        ser.flush()
        lines = []
        while time.time() - started < timeout_s:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                lines.append(line)
            receipt = parse_s3_receipt_line(line)
            if receipt:
                receipt["source"] = "esp32s3_serial"
                receipt["serial_port"] = port
                receipt["serial_elapsed_s"] = round(time.time() - started, 3)
                return receipt
    raise TimeoutError(f"no S3_LANGUAGE_RECEIPT from {port} within {timeout_s}s; recent_lines={lines[-5:]}")

def local_language_from_payload(payload: dict, *, s3_port: str | None, s3_timeout_s: float):
    prompt, prompt_source = canonical_policy_prompt(payload)
    if s3_port:
        try:
            local = query_s3_serial(s3_port, prompt, s3_timeout_s)
        except Exception as e:
            local = {
                "schema": "ri_esp32s3_local_language_v1",
                "source": "esp32s3_serial_error_static_fallback",
                "prompt": prompt,
                "output": CANONICAL_OUTPUTS[prompt],
                "error": str(e),
                "passed": False,
            }
    else:
        local = {
            "schema": "ri_esp32s3_local_language_v1",
            "source": "host_canonical_p15_lookup",
            "prompt": prompt,
            "output": CANONICAL_OUTPUTS[prompt],
            "stop_rule": "period_or_newline_or_48_chars",
            "passed": True,
        }

    receipt = {
        "schema": "ri_sensor_policy_to_s3_language_integration_v1",
        "received_unix": time.time(),
        "device_id": payload.get("device_id") or payload.get("proof", {}).get("device_id"),
        "policy_prompt_source": prompt_source,
        "policy_prompt": prompt,
        "local_language": local,
        "sensor_proof": payload.get("proof"),
        "sensor_status": payload.get("status"),
        "raw_sensor": {
            "temperature_c": payload.get("temperature_c"),
            "temperature_f": payload.get("temperature_f"),
            "humidity_pct": payload.get("humidity_pct"),
            "heat_index_f": payload.get("heat_index_f"),
        },
        "oled_text": local.get("output"),
    }
    return receipt

class Handler(BaseHTTPRequestHandler):
    s3_port = None
    s3_timeout_s = 12.0

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {
                "ok": True,
                "sink": str(OUT),
                "receipts": str(RECEIPTS),
                "local_language_receipts": str(LOCAL_LANGUAGE_RECEIPTS),
                "integration_receipts": str(INTEGRATION_RECEIPTS),
                "s3_port": self.s3_port,
            })
        if self.path == "/latest":
            latest = latest_jsonl(OUT)
            return self._send(200, latest) if latest else self._send(404, {"error": "no_readings_yet"})
        if self.path == "/latest_receipt":
            latest = latest_jsonl(RECEIPTS)
            return self._send(200, latest) if latest else self._send(404, {"error": "no_receipts_yet"})
        if self.path == "/latest_local_language":
            latest = latest_jsonl(INTEGRATION_RECEIPTS)
            return self._send(200, latest) if latest else self._send(404, {"error": "no_local_language_yet"})
        return self._send(404, {"error": "not_found", "routes": ["GET /health", "GET /latest", "GET /latest_receipt", "GET /latest_local_language", "POST /api/sensor", "POST /api/local_language"]})

    def do_POST(self):
        if self.path not in ("/api/sensor", "/api/local_language"):
            return self._send(404, {"error": "not_found"})
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            return self._send(400, {"error": "bad_json", "detail": str(e)})
        received_unix = time.time()

        if self.path == "/api/sensor":
            payload["received_unix"] = received_unix
            append_jsonl(OUT, payload)
            receipt = receipt_from_payload(payload, received_unix)
            if receipt:
                append_jsonl(RECEIPTS, receipt)
            print(json.dumps({"reading": payload, "receipt": receipt}, indent=2), flush=True)
            return self._send(200, {"ok": True, "stored": str(OUT), "receipt_stored": bool(receipt), "receipts": str(RECEIPTS)})

        integration = local_language_from_payload(payload, s3_port=self.s3_port, s3_timeout_s=self.s3_timeout_s)
        append_jsonl(LOCAL_LANGUAGE_RECEIPTS, integration["local_language"])
        append_jsonl(INTEGRATION_RECEIPTS, integration)
        print(json.dumps({"integration": integration}, indent=2), flush=True)
        return self._send(200, {"ok": True, **integration})

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args), flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8088)
    p.add_argument("--s3-port", default=None, help="Optional ESP32-S3 serial port. If set, POST /api/local_language sends PROMPT:<prompt> to real S3 firmware.")
    p.add_argument("--s3-timeout-s", type=float, default=12.0)
    args = p.parse_args()
    Handler.s3_port = args.s3_port
    Handler.s3_timeout_s = args.s3_timeout_s
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"sensor receiver listening on http://{args.host}:{args.port}; writing {OUT}; receipts {RECEIPTS}; local_language {INTEGRATION_RECEIPTS}; s3_port={args.s3_port}", flush=True)
    srv.serve_forever()
