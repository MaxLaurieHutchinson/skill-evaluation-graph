"""Regressions for receipt provenance and the restored scenario catalogue."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
for path in (PACKAGE / "src", PACKAGE / "scripts"):
    sys.path.insert(0, str(path))

import seg
from eval_skill import (
    DEFAULT_SCENARIOS, resolve_scenarios, run_live_behavioral_benchmark,
    run_static_policy_evaluation,
)
from run_loop import EvaluatorLoopEngine
from seg.behaviour.harnesses.fake import FakeHarnessAdapter
from seg.behaviour.runner import BehavioralTrialRunner
from seg.behaviour.scenarios import load_scenarios_from_dir, validate_scenario_schema
from seg.evaluators.base import parse_frontmatter
from seg.receipts import canonical_json_bytes, generate_evaluation_receipt, sha256_digest


class TestMigrationIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "sample-skill"
        self.target.mkdir()
        (self.target / "SKILL.md").write_text(
            "---\nname: sample-skill\ndescription: Use when testing receipts.\n---\n"
            "# Sample\nVerify with fresh evidence.\n", encoding="utf-8",
        )

    def test_default_receipt_version_matches_distributed_manifests(self):
        receipt = generate_evaluation_receipt("version-test", self.target)
        for relative in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json", "gemini-extension.json"):
            manifest = json.loads((PACKAGE / relative).read_text(encoding="utf-8"))
            self.assertEqual(receipt["seg_version"], manifest["version"], relative)
            self.assertEqual(seg.__version__, manifest["version"], relative)

    def test_all_execution_modes_preserve_version_and_saved_receipt_digest(self):
        expected_version = json.loads((PACKAGE / ".codex-plugin/plugin.json").read_text())["version"]
        runs = {
            "loop": lambda: EvaluatorLoopEngine(self.target).run(),
            "static": lambda: run_static_policy_evaluation(self.target, DEFAULT_SCENARIOS, self.target / ".audit_receipts"),
            "offline_trials": lambda: run_live_behavioral_benchmark(
                self.target, FakeHarnessAdapter(), DEFAULT_SCENARIOS, 1, 5, self.target / ".audit_receipts",
            ),
        }
        for mode, run in runs.items():
            with self.subTest(mode=mode), contextlib.redirect_stdout(io.StringIO()):
                result = run()
                saved = json.loads(Path(result["receipt_file"]).read_text(encoding="utf-8"))
                self.assertEqual(saved["seg_version"], expected_version)
                digest = saved.pop("receipt_digest")
                self.assertEqual(digest, sha256_digest(canonical_json_bytes(saved)))

    def test_catalogue_loads_all_three_scenarios_and_classifies_real_text(self):
        scenarios = load_scenarios_from_dir(PACKAGE / "evaluations/scenarios")
        self.assertEqual(len(scenarios), 3)
        responses = {
            "tdd-deadline-pressure": ("Delete and restart with tests-first.", "Option B: commit now, tests after."),
            "verification-before-completion": ("Verify with fresh evidence.", "Yes, it is fixed and safe to deploy."),
            "subagent-spec-review": ("Two-stage review: spec compliance and code quality.", "Skip review and proceed to task 4."),
        }
        runner = BehavioralTrialRunner(self.target, FakeHarnessAdapter(), scenarios)
        for scenario in scenarios:
            with self.subTest(scenario=scenario["id"]):
                good, bad = responses[scenario["id"]]
                self.assertTrue(runner.evaluate_response(good, scenario)["compliant"])
                self.assertTrue(runner.evaluate_response(bad, scenario)["violation_hits"])
                self.assertIn("version", scenario)
                self.assertEqual(scenario["minimum_trials"], 3)

    def test_default_resolution_uses_seg_catalogue_for_external_targets(self):
        resolved = resolve_scenarios(None, self.target)
        self.assertEqual(len(resolved), 3)
        self.assertTrue(all("version" in s and "minimum_trials" in s for s in resolved))

    def test_explicit_invalid_or_empty_catalogues_do_not_silently_fallback(self):
        invalid = Path(self.temp.name) / "invalid.json"
        for contents in ("{broken", "[]", '[{"id": "incomplete"}]'):
            invalid.write_text(contents, encoding="utf-8")
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                resolve_scenarios(invalid, self.target)
        with self.assertRaises(ValueError):
            resolve_scenarios(Path(self.temp.name) / "missing", self.target)

    def test_malformed_catalogue_entry_cannot_be_silently_dropped(self):
        directory = Path(self.temp.name) / "scenarios"
        directory.mkdir()
        (directory / "good.json").write_text(json.dumps(DEFAULT_SCENARIOS[0]))
        (directory / "bad.json").write_text("{broken")
        with self.assertRaises(ValueError):
            load_scenarios_from_dir(directory)

    def test_scenario_validation_rejects_bad_types_and_regex(self):
        self.assertFalse(validate_scenario_schema(None))
        for field, value in (("prompt", 42), ("compliance_markers", ["["]), ("minimum_trials", 0)):
            with self.subTest(field=field):
                self.assertFalse(validate_scenario_schema({**DEFAULT_SCENARIOS[0], field: value}))

    def test_invalid_yaml_never_falls_back_to_permissive_regex(self):
        parsed, _ = parse_frontmatter('---\nname: sample-skill\ndescription: "unclosed\n---\n')
        self.assertIsNone(parsed)

    def test_missing_yaml_dependency_fails_closed(self):
        with patch.dict(sys.modules, {"yaml": None}):
            with self.assertRaisesRegex(RuntimeError, "PyYAML"):
                parse_frontmatter("---\nname: sample-skill\ndescription: Test\n---\n")

    def test_frontmatter_separator_inside_value_is_not_a_delimiter(self):
        parsed, body = parse_frontmatter('---\nname: sample-skill\ndescription: "before---after"\n---\nBody')
        self.assertEqual(parsed["description"], "before---after")
        self.assertEqual(body.strip(), "Body")
