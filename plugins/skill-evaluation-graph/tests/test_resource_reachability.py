"""Regression tests for SEG resource reachability evidence."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from seg.evaluators.links_syntax import LinksSyntaxEvaluatorNode


class TestResourceReachability(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skill_path = Path(self.temp_dir.name) / "test-reachability-skill"
        self.skill_path.mkdir(parents=True, exist_ok=True)
        self.node = LinksSyntaxEvaluatorNode()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _struct_findings(self):
        result = self.node.execute(self.skill_path, {})
        return [finding for finding in result.findings if finding.rule_id == "STRUCT-001"], result

    def test_inline_code_path_counts_as_resource_reference(self):
        references = self.skill_path / "references"
        references.mkdir()
        (references / "quality-rubric.md").write_text("# Quality rubric\n", encoding="utf-8")
        (self.skill_path / "SKILL.md").write_text(
            "---\nname: test-reachability-skill\ndescription: Use when testing.\n---\n\n"
            "Before scoring, read `references/quality-rubric.md`.\n",
            encoding="utf-8",
        )
        findings, result = self._struct_findings()
        self.assertFalse(any(f.file == "references/quality-rubric.md" for f in findings))
        self.assertEqual(result.metrics.get("orphaned_files_count"), 0)

    def test_plain_text_path_counts_as_resource_reference(self):
        references = self.skill_path / "references"
        references.mkdir()
        (references / "failure-modes.md").write_text("# Failure modes\n", encoding="utf-8")
        (self.skill_path / "SKILL.md").write_text(
            "---\nname: test-reachability-skill\ndescription: Use when testing.\n---\n\n"
            "Load references/failure-modes.md before reviewing failures.\n",
            encoding="utf-8",
        )
        findings, _ = self._struct_findings()
        self.assertFalse(any(f.file == "references/failure-modes.md" for f in findings))

    def test_script_invocation_counts_as_resource_reference(self):
        scripts = self.skill_path / "scripts"
        scripts.mkdir()
        (scripts / "run_evals.py").write_text("print('ok')\n", encoding="utf-8")
        (self.skill_path / "CLAUDE.md").write_text(
            "Run `python scripts/run_evals.py` before reporting results.\n",
            encoding="utf-8",
        )
        (self.skill_path / "SKILL.md").write_text(
            "---\nname: test-reachability-skill\ndescription: Use when testing.\n---\n",
            encoding="utf-8",
        )
        findings, _ = self._struct_findings()
        self.assertFalse(any(f.file == "scripts/run_evals.py" for f in findings))

    def test_python_import_is_reachable_transitively_from_referenced_script(self):
        scripts = self.skill_path / "scripts"
        scripts.mkdir()
        (scripts / "run_evals.py").write_text(
            "from lint_message import lint_message\n\nprint(lint_message('hello'))\n",
            encoding="utf-8",
        )
        (scripts / "lint_message.py").write_text(
            "def lint_message(message):\n    return message\n",
            encoding="utf-8",
        )
        (self.skill_path / "CLAUDE.md").write_text(
            "Run `python scripts/run_evals.py` before reporting results.\n",
            encoding="utf-8",
        )
        (self.skill_path / "SKILL.md").write_text(
            "---\nname: test-reachability-skill\ndescription: Use when testing.\n---\n",
            encoding="utf-8",
        )
        findings, _ = self._struct_findings()
        self.assertFalse(any(f.file == "scripts/run_evals.py" for f in findings))
        self.assertFalse(any(f.file == "scripts/lint_message.py" for f in findings))

    def test_genuine_unresolved_resource_remains_informational_and_cautious(self):
        references = self.skill_path / "references"
        references.mkdir()
        (references / "unused.md").write_text("# Unused\n", encoding="utf-8")
        (self.skill_path / "SKILL.md").write_text(
            "---\nname: test-reachability-skill\ndescription: Use when testing.\n---\n",
            encoding="utf-8",
        )
        findings, _ = self._struct_findings()
        finding = next(f for f in findings if f.file == "references/unused.md")
        self.assertEqual(finding.severity, "INFO")
        self.assertIn("could not establish", finding.message.lower())
        self.assertNotIn("delete if unused", finding.suggestion.lower())

    def test_unreachable_reference_cannot_make_another_resource_reachable(self):
        references = self.skill_path / "references"
        references.mkdir()
        (references / "unreachable-a.md").write_text(
            "Read `references/unreachable-b.md`.\n",
            encoding="utf-8",
        )
        (references / "unreachable-b.md").write_text("# Unreachable B\n", encoding="utf-8")
        (self.skill_path / "SKILL.md").write_text(
            "---\nname: test-reachability-skill\ndescription: Use when testing.\n---\n",
            encoding="utf-8",
        )
        findings, _ = self._struct_findings()
        unresolved = {finding.file for finding in findings}
        self.assertIn("references/unreachable-a.md", unresolved)
        self.assertIn("references/unreachable-b.md", unresolved)

    def test_jpo_style_topology_has_no_false_orphans(self):
        references = self.skill_path / "references"
        scripts = self.skill_path / "scripts"
        references.mkdir()
        scripts.mkdir()

        reference_names = [
            "terminology.md",
            "reasoning-model.md",
            "quality-rubric.md",
            "failure-modes.md",
            "voice-and-examples.md",
            "surfaces.md",
            "research-and-verification.md",
            "prompt-template.md",
        ]
        for name in reference_names:
            (references / name).write_text(f"# {name}\n", encoding="utf-8")

        (scripts / "validate_package.py").write_text("print('ok')\n", encoding="utf-8")
        (scripts / "lint_message.py").write_text(
            "def lint_message(message):\n    return message\n",
            encoding="utf-8",
        )
        (scripts / "run_evals.py").write_text(
            "from lint_message import lint_message\n\nprint(lint_message('hello'))\n",
            encoding="utf-8",
        )

        reference_lines = "\n".join(f"* `{f'references/{name}'}`" for name in reference_names)
        (self.skill_path / "SKILL.md").write_text(
            "---\nname: test-reachability-skill\ndescription: Use when testing.\n---\n\n" + reference_lines + "\n",
            encoding="utf-8",
        )
        (self.skill_path / "CLAUDE.md").write_text(
            "Run `python scripts/validate_package.py .`.\n"
            "Run `python scripts/run_evals.py .`.\n",
            encoding="utf-8",
        )

        findings, result = self._struct_findings()
        self.assertEqual(findings, [])
        self.assertEqual(result.metrics.get("orphaned_files_count"), 0)
        self.assertEqual(result.metrics.get("resource_reference_count"), 11)
        relations = {item["relation"] for item in result.evidence[0]["resource_references"]}
        self.assertTrue({"inline_path", "script_invocation", "python_import"}.issubset(relations))


if __name__ == "__main__":
    unittest.main()
