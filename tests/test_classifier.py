"""Verify assessments of input strings; fixture commands are never executed."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from app.classifier import assess_command


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "commands.json"


class ClassifierTests(unittest.TestCase):
    def test_labelled_inputs(self):
        cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 20)

        for case in cases:
            with self.subTest(name=case["name"]):
                result = assess_command(case["command"])
                self.assertEqual(result["category"], case["category"])
                self.assertEqual(result["decision"], case["decision"])
                self.assertEqual(
                    set(result), {"category", "risk_score", "decision", "reasons"}
                )
                self.assertIsInstance(result["risk_score"], int)
                self.assertGreaterEqual(result["risk_score"], 0)
                self.assertLessEqual(result["risk_score"], 100)
                self.assertTrue(result["reasons"])
                self.assertTrue(all(isinstance(reason, str) for reason in result["reasons"]))

    def test_cli_emits_json_for_one_input(self):
        # Only the classifier Python module runs; the proposed command is stdin data.
        for proposed, expected in (("uptime\n", "ALLOW"), ("rm -rf /\n", "BLOCK")):
            with self.subTest(proposed=proposed):
                process = subprocess.run(
                    [sys.executable, "-m", "app.classifier"],
                    input=proposed,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                self.assertEqual(process.stderr, "")
                self.assertEqual(json.loads(process.stdout)["decision"], expected)

    def test_cli_without_input_blocks(self):
        process = subprocess.run(
            [sys.executable, "-m", "app.classifier"],
            input="",
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout)["decision"], "BLOCK")

    def test_cli_does_not_allow_multiline_input(self):
        for proposed in ("uptime\nrm -rf /\n", "uptime\n\n"):
            with self.subTest(proposed=proposed):
                process = subprocess.run(
                    [sys.executable, "-m", "app.classifier"],
                    input=proposed,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                result = json.loads(process.stdout)
                self.assertEqual(result["category"], "UNKNOWN")
                self.assertEqual(result["decision"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
