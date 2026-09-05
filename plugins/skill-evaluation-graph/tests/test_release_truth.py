"""test_release_truth.py - Regression tests for evidence-bounded public release claims."""

from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT_DIR = Path(__file__).parent.parent
SRC_DIR = ROOT_DIR / "src"
SCRIPT_DIR = ROOT_DIR / "scripts"
for path in (SRC_DIR, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class TestReleaseTruth(unittest.TestCase):
    def test_authoritative_spec_provenance_uses_current_sources(self):
        from seg.evaluators.portability import (
            CODEX_MKT_URL,
            CODEX_PLUGIN_URL,
            GEMINI_CLI_SPEC_URL,
        )

        openai_spec = (
            "https://github.com/openai/plugins/blob/main/"
            ".agents/skills/plugin-creator/references/plugin-json-spec.md"
        )
        self.assertEqual(CODEX_PLUGIN_URL, openai_spec)
        self.assertEqual(CODEX_MKT_URL, openai_spec)
        self.assertEqual(GEMINI_CLI_SPEC_URL, "https://geminicli.com/docs/extensions/reference/")

    def test_gemini_extension_is_classified_as_gemini_cli_not_antigravity_plugin(self):
        from seg.evaluators.portability import PortabilityEvaluatorNode

        with tempfile.TemporaryDirectory() as td:
            skill_dir = Path(td) / "release-truth-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: release-truth-skill\n"
                "description: Audits release truth. Use when validating release claims.\n"
                "---\n",
                encoding="utf-8",
            )
            (skill_dir / "GEMINI.md").write_text("See SKILL.md\n", encoding="utf-8")
            (skill_dir / "gemini-extension.json").write_text(
                json.dumps(
                    {
                        "name": "release-truth-skill",
                        "version": "1.0.0",
                        "description": "Release truth test fixture.",
                        "contextFileName": "GEMINI.md",
                    }
                ),
                encoding="utf-8",
            )

            result = PortabilityEvaluatorNode().execute(skill_dir, {})
            packaging = result.metrics.get("packaging_evidence", {})
            self.assertEqual(packaging.get("Google Gemini CLI"), "Manifest Validated")
            # Antigravity compatibility comes from the Agent Skills standard, not gemini-extension.json.
            self.assertEqual(packaging.get("Google Antigravity"), "Agent Skill Compatible")

    def test_scorecard_does_not_infer_full_rubric_scores_from_static_proxies(self):
        from audit_skill import AuditReport, generate_scorecard
        from seg.models import OracleDecision, OracleVerdict

        report = AuditReport(
            skill_name="release-truth-skill",
            skill_dir="./release-truth-skill",
            is_valid_structure=True,
            frontmatter_valid=True,
            name_matches_dir=True,
            line_count_skill_md=120,
            estimated_tokens_skill_md=1400,
            description_length_chars=180,
            description_word_count=28,
            total_files=8,
            static_quality_score=100,
            oracle_decision=OracleDecision(verdict=OracleVerdict.ACCEPT),
        )

        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "scorecard.md"
            generate_scorecard(report, target)
            text = target.read_text(encoding="utf-8")

        self.assertEqual(
            text.count("| NOT EVALUATED | 5 / 5 |"),
            6,
            "Rubric pillar scores must stay NOT EVALUATED until the full pillar is measured.",
        )

    def test_readme_uses_supported_install_surfaces_and_single_workflow(self):
        readme = (ROOT_DIR.parents[1] / "README.md").read_text(encoding="utf-8")
        repo_url = "https://github.com/MaxLaurieHutchinson/skill-evaluation-graph"

        self.assertNotIn("The 7-Phase Audit Lifecycle", readme)
        self.assertNotIn(f"agy plugin install {repo_url}", readme)
        self.assertNotIn(f"gemini extensions install {repo_url}", readme)
        self.assertIn(
            f"gemini skills install {repo_url} --path plugins/skill-evaluation-graph",
            readme,
        )
        self.assertIn("actions/workflows/test.yml/badge.svg", readme)


if __name__ == "__main__":
    unittest.main()
