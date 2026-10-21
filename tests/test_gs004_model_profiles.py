from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from ground_space.worker_process import ollama_proposal
from ground_space.workers import PERFORMANCE_PRESETS


class GS004ModelProfileTests(unittest.TestCase):
    def task(self, **changes):
        payload = {"request_type": "explanation", "prompt": "Explain a queue",
                   "model": "qwen3.5:4b", "performance": "balanced"}
        payload.update(changes)
        return {"task_id": "GS004-MOCK", "correlation_id": "gs004-mock",
                "payload": payload}

    def test_model_and_profile_are_transmitted_to_ollama(self):
        for profile, details in PERFORMANCE_PRESETS.items():
            with self.subTest(profile=profile):
                def responder(request, timeout):
                    body = json.loads(request.data.decode("utf-8"))
                    self.assertEqual("qwen3.5:4b", body["model"])
                    self.assertEqual(details["num_predict"], body["options"]["num_predict"])
                    self.assertEqual(details["num_ctx"], body["options"]["num_ctx"])
                    self.assertLessEqual(timeout, details["timeout_seconds"])
                    response = {"response": "Working proposal",
                                "eval_count": 80, "eval_duration": 2_000_000_000}
                    return io.BytesIO(json.dumps(response).encode("utf-8"))

                with patch("ground_space.worker_process.urllib.request.urlopen", side_effect=responder):
                    result = ollama_proposal(
                        {"endpoint": "http://127.0.0.1:11434",
                         "model": "qwen3.5:4b",
                         "request_timeout_seconds": 235},
                        self.task(performance=profile),
                    )["result"]
                self.assertEqual("qwen3.5:4b", result["model"])
                self.assertEqual(profile, result["performance"])
                self.assertEqual(40.0, result["tokens_per_second"])
                self.assertEqual(2.0, result["generation_seconds"])
                self.assertTrue(result["proposal_only"])

    def test_injected_model_and_invalid_profiles_are_denied(self):
        specification = {"endpoint": "http://127.0.0.1:11434", "model": "qwen3.5:4b"}
        with self.assertRaises(ValueError):
            ollama_proposal(specification, self.task(model="granite4:3b"))
        with self.assertRaises(ValueError):
            ollama_proposal(specification, self.task(performance="unlimited"))
        with self.assertRaises(ValueError):
            ollama_proposal({"endpoint": "http://example.com", "model": "qwen3.5:4b"}, self.task())

    def test_legacy_gs002_payload_without_selected_model_still_works(self):
        task = self.task()
        task["payload"].pop("model")
        fake = {"response": "Legacy response"}
        with patch("ground_space.worker_process.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(fake).encode("utf-8"))):
            result = ollama_proposal({"endpoint": "http://127.0.0.1:11434",
                                      "model": "qwen2.5-coder:3b"}, task)["result"]
        self.assertEqual("qwen2.5-coder:3b", result["model"])
        self.assertIsNone(result["tokens_per_second"])


if __name__ == "__main__":
    unittest.main()
