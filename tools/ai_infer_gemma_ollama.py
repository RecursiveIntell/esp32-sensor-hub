#!/usr/bin/env python3
"""Ollama-backed AI endpoint for ESP32 sensor hub.

Default model is gemma4:12b because the ESP32 proof should escalate sensor
context to the GTX 1070 box rather than run the real model on-device.

Routes:
  GET  /health
  POST /infer         -> JSON response after Ollama completes
  POST /infer_stream  -> text/plain token stream for OLED display
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RECEIPTS_PATH = Path(__file__).resolve().parents[1] / "ai_receipts.jsonl"

def append_ai_receipt(receipt):
    RECEIPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(receipt, separators=(",", ":"), sort_keys=True) + "\n")

DEFAULT_MODEL = "gemma4:12b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def compact_sensor_context(payload):
    sensors = payload.get("sensors") if isinstance(payload.get("sensors"), dict) else None
    return {
        "device_id": payload.get("device_id"),
        "temperature_c": payload.get("temperature_c"),
        "humidity_pct": payload.get("humidity_pct"),
        "heat_index_c": payload.get("heat_index_c"),
        "status": payload.get("status"),
        "wifi_rssi": payload.get("wifi_rssi"),
        "uptime_ms": payload.get("uptime_ms"),
        "free_heap": payload.get("free_heap"),
        "ip": payload.get("ip"),
        "sensors": sensors,
    }


def extract_user_prompt(payload):
    ai_req = payload.get("ai_request") or {}
    raw = ai_req.get("raw_body")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            prompt = parsed.get("prompt") or parsed.get("question") or parsed.get("message")
            if prompt:
                return str(prompt)
        except json.JSONDecodeError:
            return raw.strip()
    prompt = payload.get("prompt") or payload.get("question") or payload.get("message")
    if prompt:
        return str(prompt)
    return (
        "Analyze these room sensor readings. Respond in 1-3 short lines for a 128x64 OLED. "
        "Mention temperature, humidity, comfort/risk, and one practical recommendation."
    )


def build_messages(payload):
    sensor = compact_sensor_context(payload)
    user_prompt = extract_user_prompt(payload)
    return [
        {
            "role": "system",
            "content": (
                "You are the local AI tier for an ESP32 physical-world sensor node. "
                "Use the sensor context as evidence. Be short, practical, and explicit. "
                "If the data is missing or stale, say so. Do not invent sensor readings. "
                "The response may be streamed to a tiny OLED, so avoid markdown and keep it compact."
            ),
        },
        {
            "role": "user",
            "content": (
                "Sensor context JSON:\n"
                + json.dumps(sensor, separators=(",", ":"), sort_keys=True)
                + "\n\nOperator request:\n"
                + user_prompt
            ),
        },
    ]


def ollama_json(ollama_url, path, body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        ollama_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_stream_lines(ollama_url, path, body, timeout=180):
    req = urllib.request.Request(
        ollama_url.rstrip("/") + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            yield json.loads(line)


def list_models(ollama_url, timeout=10):
    data = ollama_json(ollama_url, "/api/tags", None, timeout)
    return [m.get("name") for m in data.get("models", [])]


def model_available(ollama_url, model):
    try:
        return model in list_models(ollama_url)
    except Exception:
        return False


def infer_with_ollama(payload, model, ollama_url, timeout=180, num_predict=160):
    started = time.time()
    messages = build_messages(payload)
    req = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }
    data = ollama_json(ollama_url, "/api/chat", req, timeout)
    msg = data.get("message") or {}
    return {
        "ok": True,
        "model_backend": "ollama",
        "model": model,
        "received_unix": started,
        "elapsed_ms": round((time.time() - started) * 1000.0, 2),
        "sensor_context": compact_sensor_context(payload),
        "response": msg.get("content", ""),
        "ollama_done_reason": data.get("done_reason"),
        "prompt_eval_count": data.get("prompt_eval_count"),
        "eval_count": data.get("eval_count"),
    }


def iter_ollama_content(payload, model, ollama_url, timeout=180, num_predict=96):
    messages = build_messages(payload)
    req = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "num_predict": num_predict,
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }
    for item in ollama_stream_lines(ollama_url, "/api/chat", req, timeout=timeout):
        msg = item.get("message") or {}
        content = msg.get("content") or ""
        if content:
            yield content
        if item.get("done"):
            break


class AiHandler(BaseHTTPRequestHandler):
    model = DEFAULT_MODEL
    ollama_url = DEFAULT_OLLAMA_URL
    request_timeout: int = 180
    num_predict: int = 160

    def _send(self, code, obj):
        body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            return json.loads(raw) if raw else {}, None
        except json.JSONDecodeError as e:
            return None, str(e)

    def do_GET(self):
        if self.path == "/health":
            available = model_available(self.ollama_url, self.model)
            return self._send(
                200 if available else 503,
                {
                    "ok": available,
                    "role": "gemma_ollama_ai_endpoint",
                    "model": self.model,
                    "ollama_url": self.ollama_url,
                    "model_available": available,
                    "routes": ["GET /health", "POST /infer", "POST /infer_stream"],
                },
            )
        return self._send(404, {"error": "not_found", "routes": ["GET /health", "POST /infer", "POST /infer_stream"]})

    def do_POST(self):
        if self.path not in ("/infer", "/infer_stream"):
            return self._send(404, {"error": "not_found"})

        payload, err = self._read_json_body()
        if err:
            return self._send(400, {"ok": False, "error": "bad_json", "detail": err})

        if self.path == "/infer_stream":
            return self._stream_infer(payload)

        try:
            result = infer_with_ollama(
                payload,
                self.model,
                self.ollama_url,
                timeout=self.request_timeout,
                num_predict=self.num_predict,
            )
            append_ai_receipt({
                "schema": "ri_esp_ai_receipt_v1",
                "received_unix": result.get("received_unix"),
                "model": result.get("model"),
                "model_backend": result.get("model_backend"),
                "elapsed_ms": result.get("elapsed_ms"),
                "device_id": (payload or {}).get("device_id"),
                "proof": (payload or {}).get("proof"),
                "sensor_context": result.get("sensor_context"),
                "response": result.get("response"),
                "prompt_eval_count": result.get("prompt_eval_count"),
                "eval_count": result.get("eval_count"),
            })
            return self._send(200, result)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            return self._send(e.code, {"ok": False, "error": "ollama_http_error", "model": self.model, "detail": detail})
        except Exception as e:
            return self._send(503, {"ok": False, "error": "ollama_unavailable", "model": self.model, "detail": str(e)})

    def _stream_infer(self, payload):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for chunk in iter_ollama_content(
                payload,
                self.model,
                self.ollama_url,
                timeout=self.request_timeout,
                num_predict=self.num_predict,
            ):
                data = chunk.encode("utf-8", errors="replace")
                self.wfile.write(data)
                self.wfile.flush()
            self.wfile.write(b"\n")
            self.wfile.flush()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            try:
                self.wfile.write(("\n[ollama_http_error %s] %s\n" % (e.code, detail)).encode("utf-8", errors="replace"))
                self.wfile.flush()
            except Exception:
                pass
        except Exception as e:
            try:
                self.wfile.write(("\n[ollama_unavailable] %s\n" % e).encode("utf-8", errors="replace"))
                self.wfile.flush()
            except Exception:
                pass

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=os.environ.get("AI_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("AI_PORT", "8090")))
    p.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL))
    p.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL))
    p.add_argument("--timeout", type=int, default=int(os.environ.get("OLLAMA_TIMEOUT", "180")))
    p.add_argument("--num-predict", type=int, default=int(os.environ.get("OLLAMA_NUM_PREDICT", "160")))
    args = p.parse_args()

    AiHandler.model = args.model
    AiHandler.ollama_url = args.ollama_url
    AiHandler.request_timeout = args.timeout
    AiHandler.num_predict = args.num_predict

    srv = ThreadingHTTPServer((args.host, args.port), AiHandler)
    print(
        f"Gemma/Ollama AI endpoint listening on http://{args.host}:{args.port} "
        f"model={args.model} ollama={args.ollama_url}",
        flush=True,
    )
    srv.serve_forever()


if __name__ == "__main__":
    main()
