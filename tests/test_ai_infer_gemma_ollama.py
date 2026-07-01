#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import sys
import unittest
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "ai_infer_gemma_ollama.py"
spec = importlib.util.spec_from_file_location("ai_infer_gemma_ollama", MODULE_PATH)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
mod_any: Any = mod


class GemmaEndpointTests(unittest.TestCase):
    def test_build_messages_includes_sensor_context_and_prompt(self):
        payload = {
            "device_id": "esp32-proof-01",
            "temperature_c": 29.5,
            "humidity_pct": 71.0,
            "heat_index_c": 31.0,
            "status": "ok",
            "ai_request": {"raw_body": json.dumps({"prompt": "Should I ventilate the room?"})},
        }

        messages = mod.build_messages(payload)

        self.assertEqual(messages[0]["role"], "system")
        user = messages[1]["content"]
        self.assertIn('"device_id":"esp32-proof-01"', user)
        self.assertIn('"temperature_c":29.5', user)
        self.assertIn("Should I ventilate the room?", user)

    def test_raw_text_prompt_is_preserved_when_not_json(self):
        payload = {"ai_request": {"raw_body": "plain operator request"}}
        self.assertEqual(mod.extract_user_prompt(payload), "plain operator request")

    def test_infer_with_ollama_wraps_response_from_fake_backend(self):
        calls = []

        def fake_ollama_json(url, path, body=None, timeout=120):
            calls.append((url, path, body, timeout))
            return {
                "message": {"content": "Ventilate if humidity keeps rising."},
                "done_reason": "stop",
                "prompt_eval_count": 33,
                "eval_count": 8,
            }

        old = mod_any.ollama_json
        mod_any.ollama_json = fake_ollama_json
        try:
            out = mod.infer_with_ollama(
                {"temperature_c": 29.5, "humidity_pct": 71.0, "status": "ok"},
                "gemma4:12b",
                "http://ollama.test",
                timeout=9,
                num_predict=32,
            )
        finally:
            mod_any.ollama_json = old

        self.assertTrue(out["ok"])
        self.assertEqual(out["model"], "gemma4:12b")
        self.assertEqual(out["model_backend"], "ollama")
        self.assertIn("Ventilate", out["response"])
        self.assertEqual(calls[0][1], "/api/chat")
        self.assertEqual(calls[0][2]["model"], "gemma4:12b")
        self.assertEqual(calls[0][2]["options"]["num_predict"], 32)


if __name__ == "__main__":
    unittest.main()
