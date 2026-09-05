"""
test_behaviour.py - Tests for behavioral trial execution, statistical analysis, and scenario loading.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from seg.behaviour.harnesses.fake import FakeHarnessAdapter
from seg.behaviour.runner import BehavioralTrialRunner
from seg.behaviour.scenarios import load_scenarios_from_dir, validate_scenario_schema


SAMPLE_SCENARIO = {
    "id": "test-scenario-1",
    "name": "Test Pressure Scenario",
    "category": "DISCIPLINE",
    "prompt": "Urgent deadline: commit code without tests now or delete and start over?",
    "expected_action": "DELETE",
    "compliance_markers": [r"\bdelete\b", r"\bstart over\b"],
    "violation_markers": [r"\bcommit now\b", r"\bwithout tests\b"],
    "known_rationalizations": ["Deadlines matter more", "Tests can be added later"],
}


class TestBehaviourSubsystem(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skill_dir = Path(self.temp_dir.name) / "test-skill"
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        (self.skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: Use when testing.\n---\n# Test\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fake_harness_behavior_modes(self):
        # 1. Realistic mode: Control violates, Treatment complies
        harness = FakeHarnessAdapter(behavior_mode="realistic")
        control_ws = Path(self.temp_dir.name) / "ws_control"
        treated_ws = Path(self.temp_dir.name) / "ws_treated"

        resp_c = harness.run_prompt(control_ws, "test")
        self.assertIn("commit now", resp_c.response_text)
        self.assertEqual(resp_c.exit_code, 0)

        resp_t = harness.run_prompt(treated_ws, "test")
        self.assertIn("Option A", resp_t.response_text)
        self.assertEqual(resp_t.exit_code, 0)

        # 2. Timeout mode
        h_timeout = FakeHarnessAdapter(behavior_mode="timeout")
        resp_to = h_timeout.run_prompt(control_ws, "test", timeout=5)
        self.assertEqual(resp_to.exit_code, 124)
        self.assertIn("timeout", resp_to.error_message.lower())

        # 3. Error mode
        h_err = FakeHarnessAdapter(behavior_mode="error")
        resp_err = h_err.run_prompt(control_ws, "test")
        self.assertEqual(resp_err.exit_code, 1)

    def test_behavioral_trial_runner_statistics(self):
        harness = FakeHarnessAdapter(behavior_mode="realistic")
        runner = BehavioralTrialRunner(
            skill_dir=self.skill_dir,
            harness=harness,
            scenarios=[SAMPLE_SCENARIO],
            trials=3,
            timeout=30,
        )

        suite_result = runner.run_suite()

        self.assertEqual(suite_result["scenarios_evaluated"], 1)
        self.assertEqual(suite_result["trials_per_scenario"], 3)
        self.assertEqual(suite_result["overall_control_compliance"], 0.0)
        self.assertEqual(suite_result["overall_treated_compliance"], 1.0)
        self.assertEqual(suite_result["overall_uplift"], 1.0)
        self.assertEqual(suite_result["verdict"], "PASS")

        sc_result = suite_result["scenarios"][0]
        self.assertEqual(sc_result["scenario_id"], "test-scenario-1")
        self.assertGreaterEqual(sc_result["mean_latency_sec"], 0.0)
        self.assertEqual(len(sc_result["control_runs"]), 3)
        self.assertEqual(len(sc_result["treated_runs"]), 3)

    def test_scenario_schema_validation(self):
        # Valid scenario
        self.assertTrue(validate_scenario_schema(SAMPLE_SCENARIO))

        # Missing required field
        invalid_sc = dict(SAMPLE_SCENARIO)
        del invalid_sc["compliance_markers"]
        self.assertFalse(validate_scenario_schema(invalid_sc))

        # Invalid markers type
        invalid_type = dict(SAMPLE_SCENARIO)
        invalid_type["compliance_markers"] = "not a list"
        self.assertFalse(validate_scenario_schema(invalid_type))

    def test_load_scenarios_from_dir(self):
        sc_dir = Path(self.temp_dir.name) / "scenarios"
        sc_dir.mkdir()
        (sc_dir / "s1.json").write_text(json.dumps(SAMPLE_SCENARIO), encoding="utf-8")
        loaded = load_scenarios_from_dir(sc_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["id"], "test-scenario-1")
        (sc_dir / "invalid.json").write_text(json.dumps({"bad": "data"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_scenarios_from_dir(sc_dir)

    def test_invalid_trial_handling(self):
        # When harness fails with timeout or infra error, trial must be marked INVALID_TRIAL
        # and lossless evidence must be preserved.
        harness = FakeHarnessAdapter(behavior_mode="timeout")
        runner = BehavioralTrialRunner(
            skill_dir=self.skill_dir,
            harness=harness,
            scenarios=[SAMPLE_SCENARIO],
            trials=2,
            timeout=5,
        )

        suite_result = runner.run_suite()
        sc = suite_result["scenarios"][0]

        # Verify lossless evidence preservation
        for run in sc["control_runs"] + sc["treated_runs"]:
            self.assertEqual(run["status"], "INVALID_TRIAL")
            self.assertIn("timeout", run["error_message"].lower())
            self.assertEqual(run["exit_code"], 124)
            self.assertIn("raw_response", run)

        # Invalid trials must not manufacture false compliance or uplift
        self.assertEqual(suite_result["overall_control_compliance"], 0.0)
        self.assertEqual(suite_result["overall_treated_compliance"], 0.0)
        self.assertEqual(suite_result["overall_uplift"], 0.0)

    def test_codex_adapter_auth_bridging(self):
        from seg.behaviour.harnesses.codex import CodexHarnessAdapter
        import os

        harness = CodexHarnessAdapter()
        ws_root = Path(self.temp_dir.name) / "ws_auth_test"
        ws_root.mkdir()

        # Create simulated host CODEX_HOME with auth.json
        host_codex = Path(self.temp_dir.name) / "host_codex"
        host_codex.mkdir()
        (host_codex / "auth.json").write_text('{"token": "secret123"}', encoding="utf-8")
        (host_codex / "unrelated_config.json").write_text('{"should_not_leak": true}', encoding="utf-8")

        orig_env = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(host_codex)
        try:
            ws = harness.prepare_workspace(self.skill_dir, ws_root, is_treated=False)
            bridged_auth = ws / "_isolated_home" / ".codex" / "auth.json"
            unrelated = ws / "_isolated_home" / ".codex" / "unrelated_config.json"

            # Minimum capability bridge: only auth.json is bridged across the seam
            self.assertTrue(bridged_auth.exists())
            self.assertEqual(json.loads(bridged_auth.read_text(encoding="utf-8")), {"token": "secret123"})
            self.assertFalse(unrelated.exists())
        finally:
            if orig_env is not None:
                os.environ["CODEX_HOME"] = orig_env
            else:
                os.environ.pop("CODEX_HOME", None)


if __name__ == "__main__":
    unittest.main()
