#!/usr/bin/env python3
"""Hard verification for sensor-policy -> ESP32-S3 local-language bridge.

Validates without an OLED by checking the exact text that firmware would put on
OLED (`oled_text`) plus the real S3 serial receipt when --s3-port is provided.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
RECEIVER_PATH = ROOT / "tools" / "sensor_receiver.py"

spec = importlib.util.spec_from_file_location("sensor_receiver", RECEIVER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot import {RECEIVER_PATH}")
sensor_receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sensor_receiver)

CASES = [
    {
        "name": "proof_override_hot_humid",
        "payload": {
            "device_id": "case-proof-hot-humid",
            "uptime_ms": 1000,
            "status": "ok",
            "temperature_c": 31.0,
            "temperature_f": 87.8,
            "humidity_pct": 72.0,
            "heat_index_f": 94.0,
            "sensors": {"dht": {"valid": True, "temperature_c": 31.0, "temperature_f": 87.8, "humidity_pct": 72.0, "last_read_ms": 900}},
            "proof": {"schema": "ri_esp_proof_receipt_v1", "event_id": 1, "device_id": "case-proof-hot-humid", "timestamp_ms": 1000, "decision": "forward_to_ai", "route_reason": "temperature_and_humidity_out_of_range", "local_language_prompt": "high heat and humidity. action is "},
        },
        "prompt": "high heat and humidity. action is ",
        "output": "escalate.",
    },
    {
        "name": "derived_missing_sensor",
        "payload": {"device_id": "case-missing", "uptime_ms": 2000, "status": "sensor_read_failed", "temperature_c": None, "temperature_f": None, "humidity_pct": None, "sensors": {"dht": {"valid": False}}},
        "prompt": "missing sensor. action is ",
        "output": "no claim.",
    },
    {
        "name": "derived_stale_sensor",
        "payload": {"device_id": "case-stale", "uptime_ms": 500000, "status": "ok", "temperature_c": 22.0, "temperature_f": 71.6, "humidity_pct": 42.0, "sensors": {"dht": {"valid": True, "temperature_c": 22.0, "temperature_f": 71.6, "humidity_pct": 42.0, "last_read_ms": 100000}}},
        "prompt": "stale data. action is ",
        "output": "wait for fresh data.",
    },
    {
        "name": "derived_hot_humid",
        "payload": {"device_id": "case-hot-humid", "uptime_ms": 3000, "status": "ok", "temperature_c": 31.0, "temperature_f": 87.8, "humidity_pct": 70.0, "sensors": {"dht": {"valid": True, "temperature_c": 31.0, "temperature_f": 87.8, "humidity_pct": 70.0, "last_read_ms": 2900}}},
        "prompt": "high heat and humidity. action is ",
        "output": "escalate.",
    },
    {
        "name": "derived_hot",
        "payload": {"device_id": "case-hot", "uptime_ms": 4000, "status": "ok", "temperature_c": 28.5, "temperature_f": 83.3, "humidity_pct": 45.0, "sensors": {"dht": {"valid": True, "temperature_c": 28.5, "temperature_f": 83.3, "humidity_pct": 45.0, "last_read_ms": 3900}}},
        "prompt": "hot room. action is ",
        "output": "check airflow.",
    },
    {
        "name": "derived_humid",
        "payload": {"device_id": "case-humid", "uptime_ms": 5000, "status": "ok", "temperature_c": 23.0, "temperature_f": 73.4, "humidity_pct": 67.0, "sensors": {"dht": {"valid": True, "temperature_c": 23.0, "temperature_f": 73.4, "humidity_pct": 67.0, "last_read_ms": 4900}}},
        "prompt": "humid room. action is ",
        "output": "ventilate.",
    },
    {
        "name": "derived_cold_unsupported_safe",
        "payload": {"device_id": "case-cold", "uptime_ms": 5500, "status": "ok", "temperature_c": 14.0, "temperature_f": 57.2, "humidity_pct": 45.0, "sensors": {"dht": {"valid": True, "temperature_c": 14.0, "temperature_f": 57.2, "humidity_pct": 45.0, "last_read_ms": 5400}}},
        "prompt": "safe action is ",
        "output": "no claim without evidence.",
    },
    {
        "name": "derived_dry_unsupported_safe",
        "payload": {"device_id": "case-dry", "uptime_ms": 5700, "status": "ok", "temperature_c": 22.0, "temperature_f": 71.6, "humidity_pct": 22.0, "sensors": {"dht": {"valid": True, "temperature_c": 22.0, "temperature_f": 71.6, "humidity_pct": 22.0, "last_read_ms": 5600}}},
        "prompt": "safe action is ",
        "output": "no claim without evidence.",
    },
    {
        "name": "derived_normal",
        "payload": {"device_id": "case-normal", "uptime_ms": 6000, "status": "ok", "temperature_c": 22.0, "temperature_f": 71.6, "humidity_pct": 45.0, "sensors": {"dht": {"valid": True, "temperature_c": 22.0, "temperature_f": 71.6, "humidity_pct": 45.0, "last_read_ms": 5900}}},
        "prompt": "normal room. action is ",
        "output": "log receipt.",
    },
]

EXTRA_S3_PROMPTS = [
    ("safe action is ", "no claim without evidence."),
    ("local first means ", "decide before cloud."),
]


def assert_eq(got, exp, label, failures):
    if got != exp:
        failures.append({"label": label, "expected": exp, "got": got})


def run_policy_unit_tests():
    failures = []
    rows = []
    for case in CASES:
        got_prompt, source = sensor_receiver.canonical_policy_prompt(case["payload"])
        got_output = sensor_receiver.CANONICAL_OUTPUTS.get(got_prompt)
        assert_eq(got_prompt, case["prompt"], case["name"] + ":prompt", failures)
        assert_eq(got_output, case["output"], case["name"] + ":static_output", failures)
        rows.append({"case": case["name"], "prompt": got_prompt, "output": got_output, "source": source})
    return {"ok": not failures, "failures": failures, "rows": rows}


def run_static_bridge_tests():
    failures = []
    rows = []
    for case in CASES:
        receipt = sensor_receiver.local_language_from_payload(case["payload"], s3_port=None, s3_timeout_s=1)
        assert_eq(receipt["policy_prompt"], case["prompt"], case["name"] + ":bridge_prompt", failures)
        assert_eq(receipt["local_language"]["output"], case["output"], case["name"] + ":bridge_output", failures)
        assert_eq(receipt["oled_text"], case["output"], case["name"] + ":oled_text", failures)
        rows.append({"case": case["name"], "prompt": receipt["policy_prompt"], "output": receipt["local_language"]["output"], "oled_text": receipt["oled_text"]})
    return {"ok": not failures, "failures": failures, "rows": rows}


def run_real_s3_prompt_tests(port: str, rounds: int, timeout_s: float):
    failures = []
    rows = []
    prompts = [(c["prompt"], c["output"]) for c in CASES]
    # Deduplicate prompts while preserving order, then add non-policy trained prompts.
    dedup = []
    seen = set()
    for item in prompts + EXTRA_S3_PROMPTS:
        if item[0] not in seen:
            dedup.append(item)
            seen.add(item[0])
    for r in range(rounds):
        for prompt, expected in dedup:
            started = time.time()
            receipt = sensor_receiver.query_s3_serial(port, prompt, timeout_s)
            elapsed = round(time.time() - started, 3)
            got = receipt.get("output")
            if got != expected or not receipt.get("passed"):
                failures.append({"round": r + 1, "prompt": prompt, "expected": expected, "got": got, "receipt": receipt})
            rows.append({"round": r + 1, "prompt": prompt, "expected": expected, "got": got, "elapsed_s": elapsed, "receipt_elapsed_ms": receipt.get("elapsed_ms"), "chars_per_sec": receipt.get("chars_per_sec")})
    return {"ok": not failures, "failures": failures, "rows": rows, "rounds": rounds, "unique_prompts": len(dedup)}


def run_http_tests(port: int, use_s3_port: str | None, timeout_s: float):
    failures = []
    rows = []
    sensor_receiver.Handler.s3_port = use_s3_port
    sensor_receiver.Handler.s3_timeout_s = timeout_s
    srv = ThreadingHTTPServer(("127.0.0.1", port), sensor_receiver.Handler)
    actual_port = srv.server_address[1]
    thread = Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        for case in CASES:
            req = urllib.request.Request(
                f"http://127.0.0.1:{actual_port}/api/local_language",
                data=json.dumps(case["payload"]).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=max(timeout_s + 5, 15)) as resp:
                data = json.loads(resp.read())
            assert_eq(data["policy_prompt"], case["prompt"], case["name"] + ":http_prompt", failures)
            assert_eq(data["local_language"]["output"], case["output"], case["name"] + ":http_output", failures)
            assert_eq(data["oled_text"], case["output"], case["name"] + ":http_oled", failures)
            rows.append({"case": case["name"], "prompt": data["policy_prompt"], "output": data["local_language"]["output"], "oled_text": data["oled_text"], "source": data["local_language"].get("source")})
    finally:
        srv.shutdown()
        srv.server_close()
    return {"ok": not failures, "failures": failures, "rows": rows, "used_s3": bool(use_s3_port)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s3-port", default=None)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--timeout-s", type=float, default=20.0)
    ap.add_argument("--http-real-s3", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "sensor_policy_s3_hard_test_receipt.json"))
    args = ap.parse_args()

    result = {
        "schema": "ri_sensor_policy_s3_hard_test_v1",
        "started_unix": time.time(),
        "policy_unit": run_policy_unit_tests(),
        "static_bridge": run_static_bridge_tests(),
        "real_s3_prompts": None,
        "http_bridge": None,
    }
    if args.s3_port:
        result["real_s3_prompts"] = run_real_s3_prompt_tests(args.s3_port, args.rounds, args.timeout_s)
    result["http_bridge"] = run_http_tests(0, args.s3_port if args.http_real_s3 else None, args.timeout_s)
    result["finished_unix"] = time.time()
    sections = [result["policy_unit"], result["static_bridge"], result["http_bridge"]]
    if result["real_s3_prompts"] is not None:
        sections.append(result["real_s3_prompts"])
    result["ok"] = all(s and s.get("ok") for s in sections)
    out = Path(args.out)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "ok": result["ok"],
        "out": str(out),
        "policy_cases": len(result["policy_unit"]["rows"]),
        "static_bridge_cases": len(result["static_bridge"]["rows"]),
        "http_cases": len(result["http_bridge"]["rows"]),
        "real_s3_queries": 0 if result["real_s3_prompts"] is None else len(result["real_s3_prompts"]["rows"]),
        "failures": [s.get("failures") for s in sections if s.get("failures")],
    }, indent=2, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
