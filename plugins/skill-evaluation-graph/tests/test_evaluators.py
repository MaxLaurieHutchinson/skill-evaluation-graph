"""
test_evaluators.py - Unit tests for all 7 independent SEG evaluator nodes.
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

from seg.evaluators.schema import SchemaEvaluatorNode
from seg.evaluators.trigger_routing import TriggerRoutingEvaluatorNode
from seg.evaluators.links_syntax import LinksSyntaxEvaluatorNode
from seg.evaluators.tokens import TokensEvaluatorNode
from seg.evaluators.safety_privacy import SafetyPrivacyEvaluatorNode
from seg.evaluators.portability import PortabilityEvaluatorNode
from seg.evaluators.behaviour_policy import BehaviourPolicyEvaluatorNode
from seg.models import FindingKind


class TestEvaluatorNodes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skill_path = Path(self.temp_dir.name) / "test-eval-skill"
        self.skill_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_evaluator(self):
        node = SchemaEvaluatorNode()
        res_missing = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "SPEC-001" for f in res_missing.findings))

        skill_md = self.skill_path / "SKILL.md"
        skill_md.write_text("No frontmatter here", encoding="utf-8")
        res_bad_fm = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "SPEC-002" for f in res_bad_fm.findings))

        skill_md.write_text("---\nname: Bad Name!\ndescription: A test.\n---\n", encoding="utf-8")
        res_bad_name = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "SPEC-004" for f in res_bad_name.findings))

        long_name = "a" * 65
        skill_md.write_text(f"---\nname: {long_name}\ndescription: A test.\n---\n", encoding="utf-8")
        res_long_name = node.execute(self.skill_path, {})
        spec_005 = [f for f in res_long_name.findings if f.rule_id == "SPEC-005"]
        self.assertEqual(len(spec_005), 1)
        self.assertEqual(spec_005[0].severity, "ERROR")
        self.assertEqual(spec_005[0].kind, FindingKind.SPECIFICATION_ERROR)
        self.assertIn("agentskills", spec_005[0].source_url)

        long_desc = "d" * 1025
        skill_md.write_text(f"---\nname: test-eval-skill\ndescription: {long_desc}\n---\n", encoding="utf-8")
        res_long_desc = node.execute(self.skill_path, {})
        spec_008 = [f for f in res_long_desc.findings if f.rule_id == "SPEC-008"]
        self.assertEqual(len(spec_008), 1)
        self.assertEqual(spec_008[0].severity, "ERROR")
        self.assertEqual(spec_008[0].kind, FindingKind.SPECIFICATION_ERROR)

        skill_md.write_text("---\nname: mismatched-name\ndescription: Use when testing schema.\n---\n", encoding="utf-8")
        res_mismatch = node.execute(self.skill_path, {})
        spec_006 = [f for f in res_mismatch.findings if f.rule_id == "SPEC-006"]
        self.assertEqual(len(spec_006), 1)
        self.assertEqual(spec_006[0].severity, "ERROR")
        self.assertEqual(spec_006[0].kind, FindingKind.SPECIFICATION_ERROR)

        node_with_alias = SchemaEvaluatorNode(allowed_name_aliases={"mismatched-name"})
        res_alias = node_with_alias.execute(self.skill_path, {})
        self.assertFalse(any(f.rule_id == "SPEC-006" for f in res_alias.findings))

        skill_md.write_text("---\nname: test-eval-skill\ndescription: Test.\ncompatibility: 12345\n---\n", encoding="utf-8")
        res_compat_type = node.execute(self.skill_path, {})
        spec_009 = [f for f in res_compat_type.findings if f.rule_id == "SPEC-009"]
        self.assertEqual(len(spec_009), 1)
        self.assertEqual(spec_009[0].kind, FindingKind.SPECIFICATION_ERROR)

        skill_md.write_text(f"---\nname: test-eval-skill\ndescription: Test.\ncompatibility: {'x' * 501}\n---\n", encoding="utf-8")
        res_compat_len = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "SPEC-009" for f in res_compat_len.findings))

        skill_md.write_text("---\nname: test-eval-skill\ndescription: Test.\nmetadata: not-a-dict\n---\n", encoding="utf-8")
        res_meta_type = node.execute(self.skill_path, {})
        spec_010 = [f for f in res_meta_type.findings if f.rule_id == "SPEC-010"]
        self.assertEqual(len(spec_010), 1)
        self.assertEqual(spec_010[0].kind, FindingKind.SPECIFICATION_ERROR)

        skill_md.write_text("---\nname: test-eval-skill\ndescription: Test.\nmetadata:\n  author: 123\n---\n", encoding="utf-8")
        res_meta_val = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "SPEC-010" for f in res_meta_val.findings))

        skill_md.write_text("---\nname: test-eval-skill\ndescription: Test.\nallowed-tools:\n  - Bash\n---\n", encoding="utf-8")
        res_tools = node.execute(self.skill_path, {})
        spec_011 = [f for f in res_tools.findings if f.rule_id == "SPEC-011"]
        self.assertEqual(len(spec_011), 1)
        self.assertEqual(spec_011[0].kind, FindingKind.SPECIFICATION_ERROR)

        valid_extended = (
            "---\n"
            "name: test-eval-skill\n"
            "description: Use when testing schema.\n"
            "compatibility: Python 3.9+\n"
            "metadata:\n"
            "  author: max\n"
            "  version: 1.0.0\n"
            "allowed-tools: Bash ReadFile\n"
            "---\n"
        )
        skill_md.write_text(valid_extended, encoding="utf-8")
        res_valid = node.execute(self.skill_path, {})
        self.assertFalse(any(f.severity == "ERROR" for f in res_valid.findings))
        self.assertEqual(res_valid.metrics.get("name"), "test-eval-skill")
        self.assertEqual(res_valid.metrics.get("compatibility"), "Python 3.9+")
        self.assertEqual(res_valid.metrics.get("metadata"), {"author": "max", "version": "1.0.0"})
        self.assertEqual(res_valid.metrics.get("allowed-tools"), "Bash ReadFile")

    def test_trigger_routing_evaluator(self):
        node = TriggerRoutingEvaluatorNode()
        skill_md = self.skill_path / "SKILL.md"
        skill_md.write_text("---\nname: test-eval-skill\ndescription: This skill does things.\n---\n", encoding="utf-8")
        res = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "ROUTE-001" for f in res.findings))

        skill_md.write_text("---\nname: test-eval-skill\ndescription: Use when coding - dispatches parallel subagents with two-stage review.\n---\n", encoding="utf-8")
        res_sdo = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "ANTI-010" for f in res_sdo.findings))

        skill_md.write_text("---\nname: test-eval-skill\ndescription: Use when deploying. Do not use for testing.\n---\n", encoding="utf-8")
        res_clean = node.execute(self.skill_path, {})
        self.assertFalse(any(f.severity == "WARNING" for f in res_clean.findings))

    def test_links_syntax_evaluator(self):
        node = LinksSyntaxEvaluatorNode()
        skill_md = self.skill_path / "SKILL.md"
        content = (
            "---\nname: test-eval-skill\ndescription: Use when testing.\n---\n\n"
            "See [Missing](missing_file.md)\n\n"
            "```python\nprint('unclosed fence')\n\n"
            "TODO: Finish this section\n"
        )
        skill_md.write_text(content, encoding="utf-8")
        res = node.execute(self.skill_path, {})
        rule_ids = [f.rule_id for f in res.findings]
        self.assertIn("LINK-001", rule_ids)
        self.assertIn("SYN-002", rule_ids)
        self.assertIn("CONTENT-001", rule_ids)

    def test_tokens_evaluator(self):
        node = TokensEvaluatorNode()
        skill_md = self.skill_path / "SKILL.md"
        skill_md.write_text("---\nname: test-eval-skill\ndescription: Test.\n---\n\n" + ("word " * 300), encoding="utf-8")
        res = node.execute(self.skill_path, {})
        self.assertGreater(res.metrics.get("skill_md_tokens", 0), 0)
        self.assertIn("profiles", res.evidence[0])

    def test_safety_privacy_evaluator(self):
        node = SafetyPrivacyEvaluatorNode()
        skill_md = self.skill_path / "SKILL.md"
        content = (
            "---\nname: test-eval-skill\ndescription: Test.\n---\n\n"
            "Path: C:\\Users\\johndoe\\secrets.txt\n"
            "Run: rm -rf /\n"
        )
        skill_md.write_text(content, encoding="utf-8")
        res = node.execute(self.skill_path, {})
        rule_ids = [f.rule_id for f in res.findings]
        self.assertIn("PRIV-001", rule_ids)
        self.assertIn("SAFE-001", rule_ids)
        self.assertFalse(res.metrics.get("safety_passed", True))
        self.assertFalse(res.metrics.get("privacy_passed", True))

    def test_portability_evaluator(self):
        node = PortabilityEvaluatorNode()
        skill_md = self.skill_path / "SKILL.md"
        skill_md.write_text("---\nname: test-eval-skill\ndescription: Test.\n---\n", encoding="utf-8")

        codex_dir = self.skill_path / ".codex-plugin"
        codex_dir.mkdir(parents=True, exist_ok=True)
        (codex_dir / "plugin.json").write_text(json.dumps({"name": "test", "version": "1.0.0"}), encoding="utf-8")

        res = node.execute(self.skill_path, {})
        self.assertEqual(res.metrics.get("packaging_evidence", {}).get("OpenAI Codex"), "Manifest Validated")
        self.assertEqual(res.metrics.get("harness_capabilities", {}).get("OpenAI Codex"), "Adapter Available")
        self.assertEqual(res.metrics.get("harness_status", {}).get("OpenAI Codex"), "Manifest Validated")
        self.assertEqual(res.metrics.get("packaging_evidence", {}).get("Agent Skills Standard"), "Manifest Validated")
        self.assertEqual(res.metrics.get("packaging_evidence", {}).get("Google Antigravity"), "Agent Skill Compatible")

        (codex_dir / "plugin.json").write_text(json.dumps({"missing_name_field": True}), encoding="utf-8")
        res_invalid = node.execute(self.skill_path, {})
        self.assertEqual(res_invalid.metrics.get("harness_status", {}).get("OpenAI Codex"), "Manifest Invalid")
        self.assertTrue(any(f.rule_id == "HARN-006" for f in res_invalid.findings))

    def test_marketplace_schema_validation(self):
        node = PortabilityEvaluatorNode()
        skill_md = self.skill_path / "SKILL.md"
        skill_md.write_text("---\nname: test-eval-skill\ndescription: Test.\n---\n", encoding="utf-8")

        plugin_dir = self.skill_path / "plugins" / "test-plugin"
        codex_dir = plugin_dir / ".codex-plugin"
        codex_dir.mkdir(parents=True, exist_ok=True)
        (codex_dir / "plugin.json").write_text(json.dumps({"name": "test-plugin", "version": "1.0.0"}), encoding="utf-8")

        root_codex_dir = self.skill_path / ".codex-plugin"
        root_codex_dir.mkdir(parents=True, exist_ok=True)
        (root_codex_dir / "plugin.json").write_text(json.dumps({"name": "test-plugin", "version": "1.0.0"}), encoding="utf-8")

        mkt_dir = self.skill_path / ".agents" / "plugins"
        mkt_dir.mkdir(parents=True, exist_ok=True)

        mkt_invalid_path = {
            "plugins": [{
                "name": "test-plugin",
                "category": "Developer Tools",
                "source": {"source": "local", "path": "./"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
            }]
        }
        (mkt_dir / "marketplace.json").write_text(json.dumps(mkt_invalid_path), encoding="utf-8")
        res = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "MKT-007" for f in res.findings))

        mkt_missing_name = {
            "plugins": [{
                "category": "Developer Tools",
                "source": {"source": "local", "path": "./plugins/test-plugin"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
            }]
        }
        (mkt_dir / "marketplace.json").write_text(json.dumps(mkt_missing_name), encoding="utf-8")
        res = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "MKT-004" for f in res.findings))

        mkt_invalid_cat = {
            "plugins": [{
                "name": "test-plugin",
                "category": "InvalidCategoryName",
                "source": {"source": "local", "path": "./plugins/test-plugin"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
            }]
        }
        (mkt_dir / "marketplace.json").write_text(json.dumps(mkt_invalid_cat), encoding="utf-8")
        res = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "MKT-015" for f in res.findings))

        mkt_invalid_auth = {
            "plugins": [{
                "name": "test-plugin",
                "category": "Developer Tools",
                "source": {"source": "local", "path": "./plugins/test-plugin"},
                "policy": {"installation": "AVAILABLE", "authentication": "NOT_REQUIRED"}
            }]
        }
        (mkt_dir / "marketplace.json").write_text(json.dumps(mkt_invalid_auth), encoding="utf-8")
        res = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "MKT-011" for f in res.findings))

        mkt_invalid_src = {
            "plugins": [{
                "name": "test-plugin",
                "category": "Developer Tools",
                "source": {"source": "git", "path": "./plugins/test-plugin"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"}
            }]
        }
        (mkt_dir / "marketplace.json").write_text(json.dumps(mkt_invalid_src), encoding="utf-8")
        res = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "MKT-006" for f in res.findings))

        mkt_mismatched_name = {
            "plugins": [{
                "name": "different-plugin-name",
                "category": "Developer Tools",
                "source": {"source": "local", "path": "./plugins/test-plugin"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
            }]
        }
        (mkt_dir / "marketplace.json").write_text(json.dumps(mkt_mismatched_name), encoding="utf-8")
        res = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id in ("MKT-013", "MKT-014") for f in res.findings))

        mkt_valid = {
            "plugins": [{
                "name": "test-plugin",
                "category": "Developer Tools",
                "source": {"source": "local", "path": "./plugins/test-plugin"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
            }]
        }
        (mkt_dir / "marketplace.json").write_text(json.dumps(mkt_valid), encoding="utf-8")
        res = node.execute(self.skill_path, {})
        mkt_errors = [f for f in res.findings if f.rule_id and f.rule_id.startswith("MKT-")]
        self.assertEqual(len(mkt_errors), 0)

    def test_behaviour_policy_evaluator(self):
        node = BehaviourPolicyEvaluatorNode()
        skill_md = self.skill_path / "SKILL.md"
        skill_md.write_text("---\nname: my-parser\ndescription: Use when parsing logs. Do not use otherwise.\n---\n", encoding="utf-8")
        res_non_disc = node.execute(self.skill_path, {})
        self.assertFalse(any(f.rule_id == "STEER-001" for f in res_non_disc.findings))

        skill_md.write_text("---\nname: tdd-enforcer\ndescription: Use when enforcing test-driven discipline.\n---\n", encoding="utf-8")
        res_disc = node.execute(self.skill_path, {})
        self.assertTrue(any(f.rule_id == "STEER-001" for f in res_disc.findings))

        table_content = (
            "---\nname: tdd-enforcer\ndescription: Use when enforcing test-driven discipline.\n---\n\n"
            "## Anti-Rationalization Table\n"
            "| Excuse | Reality |\n"
            "|:---|:---|\n"
            "| Tests after are enough | Tests first are required |\n\n"
            "## Red Flags - STOP\n"
            "- Writing implementation before tests\n"
        )
        skill_md.write_text(table_content, encoding="utf-8")
        res_healed = node.execute(self.skill_path, {})
        self.assertFalse(any(f.rule_id == "STEER-001" for f in res_healed.findings))
        self.assertFalse(any(f.rule_id == "STEER-002" for f in res_healed.findings))


if __name__ == "__main__":
    unittest.main()
