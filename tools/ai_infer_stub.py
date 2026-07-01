#!/usr/bin/env python3
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "role": "ai_infer_stub"})
        return self._send(404, {"error": "not_found", "routes": ["GET /health", "POST /infer"]})

    def do_POST(self):
        if self.path != "/infer":
            return self._send(404, {"error": "not_found"})
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            return self._send(400, {"error": "bad_json", "detail": str(e)})
        sensor_summary = {
            "temperature_c": payload.get("temperature_c"),
            "humidity_pct": payload.get("humidity_pct"),
            "status": payload.get("status"),
        }
        # Replace this file with a real GTX 1070-backed inference server later.
        return self._send(200, {
            "ok": True,
            "model_backend": "stub_replace_with_gtx1070_inference",
            "received_unix": time.time(),
            "sensor_context": sensor_summary,
            "response": "AI stub received ESP32 sensor context. Real inference belongs on the GTX 1070 machine."
        })

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args), flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8090)
    args = p.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AI inference stub listening on http://{args.host}:{args.port}", flush=True)
    srv.serve_forever()
