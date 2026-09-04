#!/usr/bin/env python3
"""
test_run_loop.py - Unit tests for the EvaluatorLoopEngine in scripts/run_loop.py.

Tests:
  1. Happy path: immediate acceptance on Iteration 1 (Node 5A).
  2. Auto-repair loop: fixable link defect fails Iteration 1 -> patches in 5B/5C -> passes Iteration 2.
  3. Escalation ceiling: unfixable defect exhausts max_iterations and routes to Node 5D.
  4. Receipt generation: validates immutable JSON receipt structure and metrics.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_loop import EvaluatorLoopEngine


class TestEvaluatorLoopEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_happy_path_immediate_accept(self):
        """A flawless skill should pass Node 4 Oracle on Iteration 1 and route to Node 5A."""
        skill_dir = self.base_path / "flawless-skill"
        skill_dir.mkdir()
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        (refs_dir / "guide.md").write_text("# Guide\nExemplary reference content.", encoding="utf-8")

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: flawless-skill
description: Use when validating flawless evaluator loop execution. Do not use for other tasks.
---

# Flawless Skill

Refer to [Guide](references/guide.md) for details.
""",
            encoding="utf-8",
        )

        receipts_dir = skill_dir / ".audit_receipts"
        scorecard_file = skill_dir / "scorecard.md"

        engine = EvaluatorLoopEngine(
            skill_dir=skill_dir,
            target_score=95,
            max_iterations=3,
            auto_fix=True,
            receipt_dir=receipts_dir,
            scorecard_path=scorecard_file,
            verbose=False,
        )

        receipt = engine.run()

        self.assertEqual(receipt["final_status"], "COMPLETED")
        self.assertEqual(receipt["terminal_result"]["verdict"], "ACCEPT")
        self.assertEqual(receipt["terminal_result"]["status"], "COMPLETED")
        self.assertEqual(receipt["total_iterations"], 1)
        self.assertGreaterEqual(receipt["final_score"], 95)
        self.assertEqual(receipt["iterations_log"][0]["oracle_decision"], "ACCEPT")
        self.assertTrue(scorecard_file.exists())
        self.assertTrue(Path(receipt["receipt_file"]).exists())
        self.assertTrue(any(a["type"] == "scorecard" for a in receipt.get("generated_artifacts", [])))

    def test_auto_repair_loop(self):
        """A skill with a fixable broken link should fail iteration 1, auto-patch in 5B/5C, and pass iteration 2."""
        skill_dir = self.base_path / "repairable-skill"
        skill_dir.mkdir()
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()

        # Target file exists in references/
        (refs_dir / "target.md").write_text("# Target doc\nExisting content.", encoding="utf-8")

        # SKILL.md mistakenly links to target.md directly instead of references/target.md
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: repairable-skill
description: Use when testing auto repair loop functionality. Do not use otherwise.
---

# Repairable Skill

See [Target](target.md) for info.
""",
            encoding="utf-8",
        )

        engine = EvaluatorLoopEngine(
            skill_dir=skill_dir,
            target_score=95,
            max_iterations=3,
            auto_fix=True,
            apply_mutations=True,
            verbose=False,
        )

        receipt = engine.run()

        self.assertEqual(receipt["final_status"], "MUTATED")
        self.assertEqual(receipt["terminal_result"]["verdict"], "ACCEPT")
        self.assertEqual(receipt["terminal_result"]["status"], "MUTATED")
        self.assertEqual(receipt["total_iterations"], 2)
        self.assertEqual(receipt["iterations_log"][0]["oracle_decision"], "REVISE")
        self.assertGreater(len(receipt["iterations_log"][0]["patches_applied"]), 0)
        self.assertEqual(receipt["iterations_log"][1]["oracle_decision"], "ACCEPT")

        # Verify disk content was healed
        healed_content = skill_md.read_text(encoding="utf-8")
        self.assertIn("references/target.md", healed_content)

    def test_read_only_preview_default(self):
        """In default read-only mode, candidate repairs are verified in sandbox and previewed without mutating disk."""
        skill_dir = self.base_path / "preview-skill"
        skill_dir.mkdir()
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        (refs_dir / "target.md").write_text("# Target doc\nExisting content.", encoding="utf-8")

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: preview-skill
description: Use when testing read-only preview functionality. Do not use otherwise.
---

# Preview Skill

See [Target](target.md) for info.
""",
            encoding="utf-8",
        )

        engine = EvaluatorLoopEngine(
            skill_dir=skill_dir,
            target_score=95,
            max_iterations=3,
            auto_fix=True,
            apply_mutations=False,  # default read-only
            verbose=False,
        )

        receipt = engine.run()

        self.assertEqual(receipt["final_status"], "PREVIEWED")
        self.assertEqual(receipt["terminal_result"]["verdict"], "REVISE")
        self.assertEqual(receipt["terminal_result"]["status"], "PREVIEWED")
        self.assertIn("diff", receipt["terminal_result"])
        # Target file on disk must NOT have been changed
        self.assertIn("[Target](target.md)", skill_md.read_text(encoding="utf-8"))

    def test_max_iteration_escalation(self):
        """A skill with an unfixable defect should exhaust max iterations and route to Node 5D."""
        skill_dir = self.base_path / "unfixable-skill"
        skill_dir.mkdir()

        # SKILL.md links to completely nonexistent file that cannot be resolved
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: unfixable-skill
description: Use when verifying loop iteration ceiling escalation. Do not use otherwise.
---

# Unfixable Skill

See [Ghost](nowhere/ghost_file.md) for missing info.
""",
            encoding="utf-8",
        )

        engine = EvaluatorLoopEngine(
            skill_dir=skill_dir,
            target_score=95,
            max_iterations=2,
            auto_fix=True,
            verbose=False,
        )

        receipt = engine.run()

        self.assertEqual(receipt["final_status"], "ESCALATED")
        self.assertEqual(receipt["total_iterations"], 2)
        self.assertEqual(receipt["terminal_result"]["verdict"], "ESCALATE")
        self.assertEqual(receipt["terminal_result"]["status"], "ESCALATED")
        self.assertEqual(receipt["terminal_result"]["exhausted_iterations"], 2)
        self.assertTrue(len(receipt["terminal_result"]["blockers"]) > 0)

    def test_programmatic_read_only_default(self):
        """Programmatic instantiation must default apply_mutations to False, even if auto_fix is True."""
        skill_dir = self.base_path / "read-only-skill"
        skill_dir.mkdir()
        engine = EvaluatorLoopEngine(skill_dir=skill_dir, auto_fix=True)
        self.assertTrue(engine.auto_fix)
        self.assertFalse(engine.apply_mutations)


if __name__ == "__main__":
    unittest.main()
