#!/usr/bin/env python3
"""Promote selected ESP32 receipt JSONL records into semantic-memory.

Default is dry-run. Use --post to call the local warm semantic-memory HTTP server.
"""
import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = [ROOT / "esp32_receipts.jsonl", ROOT / "ai_receipts.jsonl"]

def iter_jsonl(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)

def fact_from_receipt(r: dict) -> str | None:
    schema = r.get("schema")
    if schema == "ri_esp_sensor_receipt_v1":
        proof = r.get("proof") or {}
        sensors = r.get("sensors") or {}
        dht = sensors.get("dht") or sensors.get("dht22") or {}
        return (
            f"ESP32 sensor receipt: device={r.get('device_id')} observed_ms={r.get('observed_ms')} "
            f"decision={proof.get('decision')} reason={proof.get('route_reason') or proof.get('reason')} "
            f"confidence={proof.get('sentinel_confidence')} temp_c={dht.get('temperature_c')} "
            f"humidity_pct={dht.get('humidity_pct')} status={r.get('status')} received_unix={r.get('received_unix')}."
        )
    if schema == "ri_esp_ai_receipt_v1":
        proof = r.get("proof") or {}
        ctx = r.get("sensor_context") or {}
        response = (r.get("response") or "").replace("\n", " ")[:240]
        return (
            f"ESP32 AI receipt: device={r.get('device_id')} model={r.get('model')} "
            f"elapsed_ms={r.get('elapsed_ms')} decision={proof.get('decision')} "
            f"reason={proof.get('route_reason') or proof.get('reason')} temp_c={ctx.get('temperature_c')} "
            f"humidity_pct={ctx.get('humidity_pct')} response={response!r}."
        )
    return None

def post_fact(http_url: str, content: str, namespace: str):
    body = json.dumps({"content": content, "namespace": namespace, "source": "esp32 receipt ingester"}).encode("utf-8")
    req = urllib.request.Request(http_url.rstrip("/") + "/add", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="*", type=Path, default=DEFAULT_FILES)
    p.add_argument("--namespace", default="esp32-sensors")
    p.add_argument("--http-url", default="http://127.0.0.1:1738")
    p.add_argument("--post", action="store_true", help="POST facts to semantic-memory /add; default dry-run prints facts")
    p.add_argument("--limit", type=int, default=25)
    args = p.parse_args()

    count = 0
    for path in args.files:
        for receipt in iter_jsonl(path) or []:
            fact = fact_from_receipt(receipt)
            if not fact:
                continue
            count += 1
            if count > args.limit:
                return
            if args.post:
                print(json.dumps(post_fact(args.http_url, fact, args.namespace), sort_keys=True))
            else:
                print(fact)

if __name__ == "__main__":
    main()
