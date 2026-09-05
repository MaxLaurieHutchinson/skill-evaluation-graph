#!/usr/bin/env python3
"""
test_eval_skill.py - Unit tests for the BehavioralEvaluationEngine in scripts/eval_skill.py.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from eval_skill import BehavioralEvaluationEngine, DEFAULT_SCENARIOS


class TestBehavioralEvaluationEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_response_scoring_logic(self):
        engine = BehavioralEvaluationEngine(self.base_path)
        scenario = next(s for s in DEFAULT_SCENARIOS if s["id"] == "tdd-deadline-pressure")

        # Test compliant text
        compliant_text = "I will choose Option A: delete code and start over with tests-first tomorrow."
        res = engine.evaluate_response(compliant_text, scenario)
        self.assertTrue(res["compliant"])
        self.assertGreater(len(res["compliance_hits"]), 0)
        self.assertEqual(len(res["violation_hits"]), 0)

        # Test violating text
        violating_text = "Option B: I will commit now and write tests after since I already manually tested it."
        res_viol = engine.evaluate_response(violating_text, scenario)
        self.assertFalse(res_viol["compliant"])
        self.assertGreater(len(res_viol["violation_hits"]), 0)
        self.assertGreater(len(res_viol["rationalization_hits"]), 0)

    def test_synthetic_benchmark_run(self):
        skill_dir = self.base_path / "sample-eval-skill"
        skill_dir.mkdir()
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: sample-eval-skill
description: Use when validating behavioral evaluation. Do not use otherwise.
---

# Sample Eval Skill

Always write tests-first. Delete any code written before tests. Start over.
Verify and run test suites before claiming completion. Fresh evidence required.
Execute a two-stage review for specification compliance and code quality.
""",
            encoding="utf-8",
        )

        receipts_dir = skill_dir / ".audit_receipts"
        engine = BehavioralEvaluationEngine(
            skill_dir=skill_dir,
            receipt_dir=receipts_dir,
            verbose=False,
        )

        receipt = engine.run_synthetic_benchmark()
        self.assertEqual(receipt["verdict"], "ACCEPTED")
        self.assertGreaterEqual(receipt["compliance_rate_percent"], 66.0)
        self.assertTrue(Path(receipt["receipt_file"]).exists())


if __name__ == "__main__":
    unittest.main()
