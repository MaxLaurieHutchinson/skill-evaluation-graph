#!/usr/bin/env python3
"""
test_audit_skill.py - Unit test suite for audit_skill.py
"""

import tempfile
import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from audit_skill import audit_skill, format_markdown_report, AuditReport


class TestAuditSkill(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_valid_skill(self):
        skill_dir = self.base_path / "sample-skill"
        skill_dir.mkdir()
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()

        ref_file = refs_dir / "details.md"
        ref_file.write_text("# Details\nSome content", encoding="utf-8")

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: sample-skill
description: Use when needing to test valid skill logic. Do not use for unrelated tasks.
---

# Sample Skill

See [Details](references/details.md) for more information.
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        self.assertTrue(report.is_valid_structure)
        self.assertTrue(report.frontmatter_valid)
        self.assertTrue(report.name_matches_dir)
        self.assertEqual(len(report.broken_links), 0)
        self.assertFalse(any(f.severity == "ERROR" for f in report.findings))

        # Test markdown report generation
        md_report = format_markdown_report(report)
        self.assertIn("Skill Audit Report: `sample-skill`", md_report)
        self.assertIn("100 / 100", md_report)

    def test_broken_link_detection(self):
        skill_dir = self.base_path / "broken-links-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: broken-links-skill
description: Use when testing broken links.
---

# Broken Links Skill

See [Missing Reference](references/missing.md) and [Missing Script](scripts/missing.py).
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        self.assertTrue(report.is_valid_structure)
        self.assertEqual(len(report.broken_links), 2)
        link_errors = [f for f in report.findings if f.category == "LINKS" and f.severity == "ERROR"]
        self.assertEqual(len(link_errors), 2)

    def test_invalid_name_and_mismatch(self):
        skill_dir = self.base_path / "actual-dir-name"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: Invalid_Name_UpperCase
description: Use when testing invalid naming.
---

# Test
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        self.assertFalse(report.name_matches_dir)
        name_errors = [f for f in report.findings if f.category == "FRONTMATTER" and f.severity == "ERROR"]
        self.assertTrue(any("lowercase alphanumeric" in f.message for f in name_errors))

    def test_placeholder_detection(self):
        skill_dir = self.base_path / "placeholder-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: placeholder-skill
description: Use when testing placeholder detection. Do not use otherwise.
---

# Placeholder Skill

TODO: Finish this section later.
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        placeholder_notices = [f for f in report.findings if f.category == "CONTENT"]
        self.assertTrue(len(placeholder_notices) > 0)

    def test_sdo_workflow_summarization_warning(self):
        skill_dir = self.base_path / "sdo-violation-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: sdo-violation-skill
description: Use when executing plans - dispatches subagent per task with two-stage review between tasks.
---

# SDO Violation Skill
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        sdo_warnings = [f for f in report.findings if f.category == "FRONTMATTER" and "SDO anti-pattern" in f.message]
        self.assertEqual(len(sdo_warnings), 1)

    def test_discipline_skill_anti_rationalization_warning(self):
        skill_dir = self.base_path / "tdd-discipline-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: tdd-discipline-skill
description: Use when writing test-driven code. Do not use otherwise.
---

# TDD Discipline Skill

Follow red-green-refactor cycle.
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        discipline_warnings = [f for f in report.findings if f.category == "STEERING" and "Rationalization Table" in f.message]
        self.assertEqual(len(discipline_warnings), 1)

    def test_manifest_validation(self):
        skill_dir = self.base_path / "manifest-test-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: manifest-test-skill
description: Use when validating cross-harness manifests. Do not use otherwise.
---

# Manifest Test Skill
"""
        skill_md.write_text(content, encoding="utf-8")

        # Invalid gemini-extension.json
        (skill_dir / "gemini-extension.json").write_text('{"missing_name": true}', encoding="utf-8")

        report = audit_skill(skill_dir)
        harness_errors = [f for f in report.findings if f.category == "HARNESS" and f.severity == "ERROR"]
        self.assertTrue(len(harness_errors) > 0)

    def test_pii_local_path_detection(self):
        skill_dir = self.base_path / "pii-leak-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: pii-leak-skill
description: Use when testing privacy leaks. Do not use otherwise.
---

# PII Skill
Local path: C:\\Users\\developer_bob\\secrets\\data.txt
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        privacy_warnings = [f for f in report.findings if f.category == "PRIVACY" and f.severity == "WARNING"]
        self.assertEqual(len(privacy_warnings), 1)
        self.assertIn("developer_bob", privacy_warnings[0].message)

    def test_unstandardized_docs_dir_warning(self):
        skill_dir = self.base_path / "docs-dir-skill"
        skill_dir.mkdir()
        (skill_dir / "docs").mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: docs-dir-skill
description: Use when testing unstandardized docs directory. Do not use otherwise.
---

# Docs Dir Skill
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        structure_warnings = [f for f in report.findings if f.category == "STRUCTURE" and "docs/" in f.message]
        self.assertEqual(len(structure_warnings), 1)

    def test_code_fence_links_ignored(self):
        skill_dir = self.base_path / "fence-links-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: fence-links-skill
description: Use when testing code fence link bypass. Do not use otherwise.
---

# Fence Links Skill

Here is code:
```markdown
[NonExistentFile](non-existent-target.md)
```
"""
        skill_md.write_text(content, encoding="utf-8")

        report = audit_skill(skill_dir)
        self.assertEqual(len(report.broken_links), 0)

    def test_codex_manifest_and_marketplace_validation(self):
        skill_dir = self.base_path / "codex-test-skill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        content = """---
name: codex-test-skill
description: Use when validating codex manifests. Do not use otherwise.
---

# Codex Test Skill
"""
        skill_md.write_text(content, encoding="utf-8")

        codex_dir = skill_dir / ".codex-plugin"
        codex_dir.mkdir()
        (codex_dir / "plugin.json").write_text('{"missing_name": true}', encoding="utf-8")

        mkt_dir = skill_dir / ".agents" / "plugins"
        mkt_dir.mkdir(parents=True)
        (mkt_dir / "marketplace.json").write_text('{"missing_plugins": true}', encoding="utf-8")

        report = audit_skill(skill_dir)
        harness_errors = [f for f in report.findings if f.category == "HARNESS" and f.severity == "ERROR"]
        codex_errs = [f for f in harness_errors if ".codex-plugin" in f.message or "marketplace.json" in f.message]
        self.assertEqual(len(codex_errs), 2)


if __name__ == "__main__":
    unittest.main()


