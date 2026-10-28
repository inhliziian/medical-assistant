"""Offline test of the validate -> one repair -> failed policy in Provider.extract().

A fake provider replays scripted answers, so no API, no Ollama, no cost. Run: make test  (or python -m unittest)"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from medassist.providers.base import REPAIR_MESSAGE, Provider, RunConfig  # noqa: E402

GOOD = json.dumps(json.loads((ROOT / "data/golden/004.json").read_text(encoding="utf-8")))
BAD_JSON = '{"patient_age": null, "patient_sex": "male", '            # cut off mid-object
BAD_SCHEMA = GOOD.replace('"male"', '"m"')                              # enum violation


class FakeProvider(Provider):
    """Answers (or raises) in the order given; records every conversation it was sent."""

    def __init__(self, script: list, **cfg):
        super().__init__(RunConfig(name="fake", provider="fake", kind="fake", model="fake-1",
                                   price_input_per_mtok=1.0, price_output_per_mtok=10.0, max_retries=1, **cfg))
        self.script = list(script)
        self.calls: list[list[dict]] = []

    def _call(self, instructions, messages):
        self.calls.append([dict(m) for m in messages])
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, 1000, 100, {"stop_reason": "end_turn"}


class RepairPolicy(unittest.TestCase):
    def setUp(self):
        # no backoff sleeps in tests
        self.sleep = mock.patch("medassist.providers.base.time.sleep", lambda s: None)
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()

    def test_valid_first_answer_is_ok_with_one_call(self):
        p = FakeProvider([GOOD])
        r = p.extract("sys", "doc")
        self.assertEqual(r.status, "ok")
        self.assertTrue(r.valid)
        self.assertFalse(r.repair_attempted)
        self.assertEqual(len(p.calls), 1)
        self.assertEqual(r.validation_errors, [])
        self.assertAlmostEqual(r.cost_usd, (1000 * 1.0 + 100 * 10.0) / 1e6)

    def test_invalid_then_valid_is_repaired(self):
        p = FakeProvider([BAD_SCHEMA, GOOD])
        r = p.extract("sys", "doc")
        self.assertEqual(r.status, "repaired")
        self.assertTrue(r.valid)
        self.assertTrue(r.repair_attempted)
        self.assertEqual(len(p.calls), 2)
        self.assertEqual(len(r.validation_errors), 1)
        self.assertIn("schema:", r.validation_errors[0])
        # the repair conversation: original doc, the bad answer as assistant turn, the error as user turn
        repair = p.calls[1]
        self.assertEqual([m["role"] for m in repair], ["user", "assistant", "user"])
        self.assertEqual(repair[0]["content"], "doc")
        self.assertEqual(repair[1]["content"], BAD_SCHEMA)
        self.assertIn(r.validation_errors[0], repair[2]["content"])
        self.assertTrue(repair[2]["content"].startswith(REPAIR_MESSAGE.split("\n")[0]))
        # tokens and cost cover both calls
        self.assertEqual((r.input_tokens, r.output_tokens), (2000, 200))
        self.assertEqual(r.extra["first_answer"], BAD_SCHEMA)

    def test_invalid_twice_is_failed_and_stops(self):
        p = FakeProvider([BAD_JSON, BAD_SCHEMA, GOOD])   # a third answer exists but must never be requested
        r = p.extract("sys", "doc")
        self.assertEqual(r.status, "failed")
        self.assertFalse(r.valid)
        self.assertEqual(len(p.calls), 2)
        self.assertEqual(len(r.validation_errors), 2)
        self.assertIn("json:", r.validation_errors[0])
        self.assertIn("schema:", r.validation_errors[1])
        self.assertEqual(r.validation_error, r.validation_errors[1])
        self.assertIsNotNone(r.parsed)   # the last parseable JSON is kept for error analysis

    def test_empty_answer_gets_the_repair(self):
        p = FakeProvider(["", GOOD])
        r = p.extract("sys", "doc")
        self.assertEqual(r.status, "repaired")
        self.assertEqual(p.calls[1][1]["content"], "(empty answer)")

    def test_transport_retry_is_not_a_repair(self):
        p = FakeProvider([TimeoutError("read timeout"), GOOD])
        r = p.extract("sys", "doc")
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.transport_retries, 1)
        self.assertFalse(r.repair_attempted)
        self.assertEqual(r.attempts, 2)

    def test_transport_failure_after_retries_is_error(self):
        p = FakeProvider([TimeoutError("t1"), TimeoutError("t2")])   # max_retries=1 -> two attempts
        r = p.extract("sys", "doc")
        self.assertEqual(r.status, "error")
        self.assertFalse(r.valid)
        self.assertIn("TimeoutError", r.error)
        self.assertEqual(r.validation_errors, [])
        self.assertIsNone(r.cost_usd)

    def test_transport_failure_during_repair_is_error_not_failed(self):
        p = FakeProvider([BAD_SCHEMA, TimeoutError("t1"), TimeoutError("t2")])
        r = p.extract("sys", "doc")
        self.assertEqual(r.status, "error")
        self.assertTrue(r.repair_attempted)
        self.assertEqual(r.validation_errors[0][:7], "schema:")

    def test_result_logs_model_and_sampling_params(self):
        p = FakeProvider([GOOD], params={"effort": "low", "constrained": False})
        r = p.extract("sys", "doc").to_dict()
        self.assertEqual(r["model"], "fake-1")
        self.assertEqual(r["params"], {"effort": "low", "constrained": False})
        self.assertEqual(r["status"], "ok")


if __name__ == "__main__":
    unittest.main()
